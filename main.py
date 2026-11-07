import os
import uuid
from contextlib import asynccontextmanager
from typing import List

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field, ConfigDict

from models import AppState, Task
from commands import (
    UpdateDocumentCommand,
    AddTaskCommand,
    CompleteTaskCommand,
    DeleteTaskCommand,
    BulkDeleteTasksCommand,
)
from processor import CommandProcessor


# Initialize the singleton application state and processor
state = AppState()
log_path = os.getenv("COMMAND_LOG_PATH", "./data/command_log.jsonl")
processor = CommandProcessor(state=state, log_path=log_path)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application startup and shutdown lifecycle.
    On startup, reconstruct the application state from the command log
    without appending back to the log or adding replay steps to undo history.
    """
    processor.replay_history()
    yield


app = FastAPI(
    title="Workflow Engine with Undo/Redo and Event Sourcing",
    description="A workflow state engine using Command, Memento, and Composite patterns.",
    version="1.0.0",
    lifespan=lifespan,
)


# --- Request DTOs ---

class DocumentUpdateRequest(BaseModel):
    content: str


class AddTaskRequest(BaseModel):
    text: str


class BulkDeleteRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    taskIds: List[str] = Field(..., alias="taskIds")


# --- System & Inspection Endpoints ---

@app.get("/health", status_code=status.HTTP_200_OK)
def health_check():
    """Simple health check endpoint returning 200 OK."""
    return {"status": "healthy"}


@app.get("/state", status_code=status.HTTP_200_OK)
def get_state():
    """
    Returns the current in-memory state of the document and tasks list.
    When clean, document content is empty and tasks is an empty array.
    """
    return state.to_dict()


# --- Action Endpoints ---

@app.post("/action/document/update", status_code=status.HTTP_200_OK)
def update_document(payload: DocumentUpdateRequest):
    """
    Updates document content, recording previous content for reversible undo.
    """
    previous_content = state.document.content
    command = UpdateDocumentCommand(
        previous_content=previous_content,
        new_content=payload.content,
    )
    processor.execute_command(command)
    return {"message": "Document updated successfully"}


@app.post("/action/tasks/add", status_code=status.HTTP_200_OK)
def add_task(payload: AddTaskRequest):
    """
    Creates and adds a new task, returning the newly created Task object.
    """
    task = Task(
        id=str(uuid.uuid4()),
        text=payload.text,
        completed=False,
    )
    command = AddTaskCommand(task=task)
    processor.execute_command(command)
    return task.to_dict()


@app.post("/action/tasks/complete/{task_id}", status_code=status.HTTP_200_OK)
def complete_task(task_id: str):
    """
    Toggles completion status for the specified task.
    """
    task = state.get_task(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task with id '{task_id}' not found",
        )
    command = CompleteTaskCommand(task_id=task_id)
    processor.execute_command(command)
    return {"message": f"Task '{task_id}' completion toggled"}


@app.post("/action/tasks/delete/{task_id}", status_code=status.HTTP_200_OK)
def delete_task(task_id: str):
    """
    Deletes a single task using the Memento pattern to retain state for undo.
    """
    task = state.get_task(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task with id '{task_id}' not found",
        )
    # The command captures the task's full state (Memento) upon creation
    command = DeleteTaskCommand(task=task.copy())
    processor.execute_command(command)
    return {"message": f"Task '{task_id}' deleted"}


@app.post("/action/tasks/bulk-delete", status_code=status.HTTP_200_OK)
def bulk_delete_tasks(payload: BulkDeleteRequest):
    """
    Deletes multiple tasks atomically as a single Composite command.
    """
    child_commands = []
    for tid in payload.taskIds:
        existing = state.get_task(tid)
        if existing:
            child_commands.append(DeleteTaskCommand(task=existing.copy()))

    composite_command = BulkDeleteTasksCommand(commands=child_commands)
    processor.execute_command(composite_command)
    return {"message": f"Bulk deleted {len(child_commands)} tasks"}


@app.post("/action/undo", status_code=status.HTTP_200_OK)
def undo():
    """
    Reverts the most recent command. If undo stack is empty, performs a no-op 200 OK.
    """
    undone = processor.undo()
    if undone is None:
        return {"message": "Undo stack is empty; no action taken"}
    return {"message": "Action undone successfully"}


@app.post("/action/redo", status_code=status.HTTP_200_OK)
def redo():
    """
    Re-applies the most recently undone command. If redo stack is empty, performs a no-op 200 OK.
    """
    redone = processor.redo()
    if redone is None:
        return {"message": "Redo stack is empty; no action taken"}
    return {"message": "Action redone successfully"}


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)

