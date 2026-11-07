import copy
import os
import tempfile
import pytest

from models import AppState, Task
from commands import (
    UpdateDocumentCommand,
    AddTaskCommand,
    CompleteTaskCommand,
    DeleteTaskCommand,
    BulkDeleteTasksCommand,
)
from processor import CommandProcessor


@pytest.fixture
def clean_processor():
    """Provides a fresh AppState and CommandProcessor with a temporary log file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_file = os.path.join(tmpdir, "test_log.jsonl")
        state = AppState()
        processor = CommandProcessor(state=state, log_path=log_file)
        yield state, processor, log_file


def test_contract_update_document(clean_processor):
    """
    Contract test for UpdateDocumentCommand:
    1. Capture state before command.
    2. Execute command via CommandProcessor.
    3. Assert state changed as expected.
    4. Call undo() via CommandProcessor.
    5. Assert state is identical to initial state.
    """
    state, processor, _ = clean_processor

    # Step 1: Capture state before
    before_state = copy.deepcopy(state.to_dict())
    assert before_state["document"]["content"] == ""

    # Step 2: Execute command
    cmd = UpdateDocumentCommand(previous_content="", new_content="Hello World")
    processor.execute_command(cmd)

    # Step 3: Assert state changed
    assert state.document.content == "Hello World"
    assert state.to_dict() != before_state

    # Step 4: Call undo
    processor.undo()

    # Step 5: Assert state returned to identical initial state
    assert state.to_dict() == before_state
    assert state.document.content == ""


def test_contract_add_task(clean_processor):
    """
    Contract test for AddTaskCommand:
    undo(execute(AddTaskCommand)) == initial_state
    """
    state, processor, _ = clean_processor

    before_state = copy.deepcopy(state.to_dict())
    assert len(before_state["tasks"]) == 0

    task = Task(id="task-1", text="Learn Design Patterns", completed=False)
    cmd = AddTaskCommand(task=task)
    processor.execute_command(cmd)

    # State changed
    assert len(state.tasks) == 1
    assert state.tasks[0].id == "task-1"
    assert state.tasks[0].text == "Learn Design Patterns"

    # Undo reverts
    processor.undo()
    assert state.to_dict() == before_state
    assert len(state.tasks) == 0


def test_contract_complete_task(clean_processor):
    """
    Contract test for CompleteTaskCommand:
    undo(execute(CompleteTaskCommand)) == initial_state
    """
    state, processor, _ = clean_processor

    task = Task(id="task-toggle", text="Complete me", completed=False)
    state.add_task(task)

    before_state = copy.deepcopy(state.to_dict())
    assert before_state["tasks"][0]["completed"] is False

    cmd = CompleteTaskCommand(task_id="task-toggle")
    processor.execute_command(cmd)

    # State changed
    assert state.tasks[0].completed is True

    # Undo reverts
    processor.undo()
    assert state.to_dict() == before_state
    assert state.tasks[0].completed is False


def test_contract_delete_task_memento(clean_processor):
    """
    Contract test for DeleteTaskCommand (Memento Pattern):
    undo(execute(DeleteTaskCommand)) == initial_state
    """
    state, processor, _ = clean_processor

    task = Task(id="task-del", text="Task to delete", completed=True)
    state.add_task(task)

    before_state = copy.deepcopy(state.to_dict())
    assert len(before_state["tasks"]) == 1

    cmd = DeleteTaskCommand(task=task.copy())
    processor.execute_command(cmd)

    # State changed
    assert len(state.tasks) == 0

    # Undo restores from memento
    processor.undo()
    assert state.to_dict() == before_state
    assert len(state.tasks) == 1
    assert state.tasks[0].id == "task-del"
    assert state.tasks[0].completed is True


def test_contract_bulk_delete_tasks_composite(clean_processor):
    """
    Contract test for BulkDeleteTasksCommand (Composite Pattern):
    undo(execute(BulkDeleteTasksCommand)) == initial_state
    A single undo restores all deleted tasks in reverse order.
    """
    state, processor, _ = clean_processor

    t1 = Task(id="t1", text="Task 1", completed=False)
    t2 = Task(id="t2", text="Task 2", completed=True)
    t3 = Task(id="t3", text="Task 3", completed=False)
    state.add_task(t1)
    state.add_task(t2)
    state.add_task(t3)

    before_state = copy.deepcopy(state.to_dict())
    assert len(before_state["tasks"]) == 3

    # Bulk delete t1 and t2
    del1 = DeleteTaskCommand(task=t1.copy())
    del2 = DeleteTaskCommand(task=t2.copy())
    bulk_cmd = BulkDeleteTasksCommand(commands=[del1, del2])

    processor.execute_command(bulk_cmd)

    # State changed: only t3 remains
    assert len(state.tasks) == 1
    assert state.tasks[0].id == "t3"

    # Single undo restores both t1 and t2
    processor.undo()
    assert state.to_dict() == before_state
    assert len(state.tasks) == 3
    assert [t.id for t in state.tasks] == ["t1", "t2", "t3"]

