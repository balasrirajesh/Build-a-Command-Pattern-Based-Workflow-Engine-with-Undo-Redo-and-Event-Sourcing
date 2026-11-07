from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from models import AppState, Task


class Command(ABC):
    """
    Abstract base interface for all commands (Command Pattern).
    Every command must implement:
      - execute(state): Applies the change to the given application state.
      - undo(state): Reverts the change made by execute.
      - to_dict(): Serializes the command for persistent logging (Event Sourcing).
    """

    @abstractmethod
    def execute(self, state: AppState) -> None:
        """Executes the command against the application state."""
        pass

    @abstractmethod
    def undo(self, state: AppState) -> None:
        """Reverts the command, restoring state to its previous condition."""
        pass

    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        """Serializes the command into a dictionary suitable for JSON logging."""
        pass


class UpdateDocumentCommand(Command):
    """
    Updates the document content.
    Stores previousContent and newContent to allow reversible undo/redo.
    """

    def __init__(self, previous_content: str, new_content: str):
        self.previous_content = previous_content
        self.new_content = new_content

    def execute(self, state: AppState) -> None:
        state.document.content = self.new_content

    def undo(self, state: AppState) -> None:
        state.document.content = self.previous_content

    def to_dict(self) -> Dict[str, Any]:
        return {
            "command_type": "UpdateDocumentCommand",
            "payload": {
                "previous_content": self.previous_content,
                "new_content": self.new_content,
            },
        }


class AddTaskCommand(Command):
    """
    Adds a new task to the task list.
    Undo removes the added task by its ID.
    """

    def __init__(self, task: Task):
        self.task = task

    def execute(self, state: AppState) -> None:
        # Check if task already exists in state to prevent duplicate addition during replay
        existing = state.get_task(self.task.id)
        if not existing:
            state.add_task(self.task.copy())

    def undo(self, state: AppState) -> None:
        state.remove_task(self.task.id)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "command_type": "AddTaskCommand",
            "payload": {
                "id": self.task.id,
                "text": self.task.text,
                "completed": self.task.completed,
            },
        }


class CompleteTaskCommand(Command):
    """
    Toggles completion status of a task.
    Saves the previous status so that undo restores the exact original status.
    """

    def __init__(self, task_id: str):
        self.task_id = task_id
        self.previous_status: Optional[bool] = None

    def execute(self, state: AppState) -> None:
        task = state.get_task(self.task_id)
        if task:
            self.previous_status = task.completed
            task.completed = not task.completed

    def undo(self, state: AppState) -> None:
        task = state.get_task(self.task_id)
        if task and self.previous_status is not None:
            task.completed = self.previous_status

    def to_dict(self) -> Dict[str, Any]:
        return {
            "command_type": "CompleteTaskCommand",
            "payload": {
                "task_id": self.task_id,
            },
        }


class DeleteTaskCommand(Command):
    """
    Deletes a task from the list.
    Applies the Memento Pattern: stores a full snapshot of the task (and its index)
    before deletion, allowing undo to restore the task exactly as it was.
    """

    def __init__(self, task: Task, index: Optional[int] = None):
        self.task = task.copy()
        self.index = index

    def execute(self, state: AppState) -> None:
        # Find index before deleting so we can restore at the exact location
        for idx, t in enumerate(state.tasks):
            if t.id == self.task.id:
                self.index = idx
                # Keep latest state of task as memento
                self.task = t.copy()
                break
        state.remove_task(self.task.id)

    def undo(self, state: AppState) -> None:
        # Restore task using the memento snapshot
        existing = state.get_task(self.task.id)
        if not existing:
            restored = self.task.copy()
            if self.index is not None and 0 <= self.index <= len(state.tasks):
                state.tasks.insert(self.index, restored)
            else:
                state.add_task(restored)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "command_type": "DeleteTaskCommand",
            "payload": {
                "task": self.task.to_dict(),
                "index": self.index,
            },
        }


class BulkDeleteTasksCommand(Command):
    """
    Composite Command (Composite Pattern):
    Groups multiple DeleteTaskCommand instances into a single atomic action.
    - execute: runs each child delete command in order.
    - undo: runs each child delete command in REVERSE order.
    A single undo restores all tasks removed in this bulk operation.
    """

    def __init__(self, commands: List[DeleteTaskCommand]):
        self.commands: List[DeleteTaskCommand] = commands

    def execute(self, state: AppState) -> None:
        for cmd in self.commands:
            cmd.execute(state)

    def undo(self, state: AppState) -> None:
        # Undo in reverse order to preserve original positions
        for cmd in reversed(self.commands):
            cmd.undo(state)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "command_type": "BulkDeleteTasksCommand",
            "payload": {
                "commands": [cmd.to_dict() for cmd in self.commands],
            },
        }


def deserialize_command(data: Dict[str, Any]) -> Command:
    """
    Factory function that reconstructs a Command instance from its serialized JSON dictionary.
    Used during startup state reconstruction (Event Sourcing).
    """
    cmd_type = data.get("command_type")
    payload = data.get("payload", {})

    if cmd_type == "UpdateDocumentCommand":
        return UpdateDocumentCommand(
            previous_content=payload.get("previous_content", ""),
            new_content=payload.get("new_content", ""),
        )

    elif cmd_type == "AddTaskCommand":
        task = Task(
            id=payload["id"],
            text=payload["text"],
            completed=payload.get("completed", False),
        )
        return AddTaskCommand(task=task)

    elif cmd_type == "CompleteTaskCommand":
        return CompleteTaskCommand(task_id=payload["task_id"])

    elif cmd_type == "DeleteTaskCommand":
        task_data = payload.get("task")
        if not task_data:
            # Fallback if payload itself represents the task
            task_data = payload
        task = Task(
            id=task_data["id"],
            text=task_data["text"],
            completed=task_data.get("completed", False),
        )
        return DeleteTaskCommand(task=task, index=payload.get("index"))

    elif cmd_type == "BulkDeleteTasksCommand":
        child_raw_cmds = payload.get("commands", [])
        child_cmds = [
            deserialize_command(child_raw)  # type: ignore
            for child_raw in child_raw_cmds
        ]
        return BulkDeleteTasksCommand(commands=child_cmds)

    else:
        raise ValueError(f"Unknown command type: {cmd_type}")

