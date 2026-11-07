import json
import os
import tempfile
import pytest
from fastapi.testclient import TestClient

from main import app, processor, state
from models import AppState
from processor import CommandProcessor


@pytest.fixture(autouse=True)
def setup_clean_environment():
    """Resets global state and isolates the command log for each test."""
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_log = os.path.join(tmpdir, "test_command_log.jsonl")
        
        # Reset state and processor
        state.document.content = ""
        state.tasks.clear()
        processor.state = state
        processor.log_path = temp_log
        processor.undo_stack.clear()
        processor.redo_stack.clear()
        
        yield temp_log


def test_core_req_5_get_state_initial_empty():
    """Requirement 5: GET /state returns the initial, empty state."""
    client = TestClient(app)
    res = client.get("/state")
    assert res.status_code == 200
    assert res.json() == {
        "document": {
            "content": ""
        },
        "tasks": []
    }


def test_core_req_6_update_document():
    """Requirement 6: POST /action/document/update modifies document content."""
    client = TestClient(app)
    res = client.post("/action/document/update", json={"content": "new document content"})
    assert res.status_code == 200

    state_res = client.get("/state")
    assert state_res.status_code == 200
    assert state_res.json()["document"]["content"] == "new document content"


def test_core_req_7_add_task():
    """Requirement 7: POST /action/tasks/add correctly adds a task and returns it."""
    client = TestClient(app)
    res = client.post("/action/tasks/add", json={"text": "My new task"})
    assert res.status_code == 200
    task_data = res.json()
    assert "id" in task_data
    assert task_data["text"] == "My new task"
    assert task_data["completed"] is False

    state_res = client.get("/state")
    tasks = state_res.json()["tasks"]
    assert len(tasks) == 1
    assert tasks[0]["id"] == task_data["id"]
    assert tasks[0]["text"] == "My new task"
    assert tasks[0]["completed"] is False


def test_core_req_8_undo_task_addition():
    """Requirement 8: POST /action/undo reverts the addition of a task."""
    client = TestClient(app)
    # Add task
    client.post("/action/tasks/add", json={"text": "task to undo"})
    assert len(client.get("/state").json()["tasks"]) == 1

    # Undo
    undo_res = client.post("/action/undo")
    assert undo_res.status_code == 200

    # Tasks list should now be empty
    assert client.get("/state").json()["tasks"] == []


def test_core_req_9_redo_task_addition():
    """Requirement 9: POST /action/redo re-applies an undone task addition."""
    client = TestClient(app)
    client.post("/action/tasks/add", json={"text": "task to redo"})
    client.post("/action/undo")
    assert client.get("/state").json()["tasks"] == []

    # Redo
    redo_res = client.post("/action/redo")
    assert redo_res.status_code == 200

    tasks = client.get("/state").json()["tasks"]
    assert len(tasks) == 1
    assert tasks[0]["text"] == "task to redo"


def test_core_req_10_empty_undo_redo_no_op():
    """
    Requirement 10: Attempting undo or redo when stacks are empty
    must return 200 OK without altering state or causing an error.
    """
    client = TestClient(app)
    initial_state = client.get("/state").json()

    # Undo on empty stack
    undo_res = client.post("/action/undo")
    assert undo_res.status_code == 200
    assert client.get("/state").json() == initial_state

    # Redo on empty stack
    redo_res = client.post("/action/redo")
    assert redo_res.status_code == 200
    assert client.get("/state").json() == initial_state


def test_core_req_11_bulk_delete_tasks():
    """Requirement 11: Bulk delete removes multiple tasks in a single operation."""
    client = TestClient(app)
    t1 = client.post("/action/tasks/add", json={"text": "Task 1"}).json()
    t2 = client.post("/action/tasks/add", json={"text": "Task 2"}).json()
    t3 = client.post("/action/tasks/add", json={"text": "Task 3"}).json()

    res = client.post("/action/tasks/bulk-delete", json={"taskIds": [t1["id"], t2["id"]]})
    assert res.status_code == 200

    tasks = client.get("/state").json()["tasks"]
    assert len(tasks) == 1
    assert tasks[0]["id"] == t3["id"]


def test_core_req_12_undo_bulk_delete_single_step():
    """
    Requirement 12: Undoing a bulk delete action must restore all deleted tasks
    in a single undo step.
    """
    client = TestClient(app)
    t1 = client.post("/action/tasks/add", json={"text": "Task 1"}).json()
    t2 = client.post("/action/tasks/add", json={"text": "Task 2"}).json()
    t3 = client.post("/action/tasks/add", json={"text": "Task 3"}).json()

    before_state = client.get("/state").json()
    assert len(before_state["tasks"]) == 3

    # Bulk delete 2 tasks
    client.post("/action/tasks/bulk-delete", json={"taskIds": [t1["id"], t2["id"]]})
    assert len(client.get("/state").json()["tasks"]) == 1

    # Single undo
    undo_res = client.post("/action/undo")
    assert undo_res.status_code == 200

    after_undo_state = client.get("/state").json()
    assert after_undo_state == before_state
    assert len(after_undo_state["tasks"]) == 3


def test_core_req_3_and_4_persistence_and_replay():
    """
    Requirement 3: Performing an action creates and appends to persistent command log file.
    Requirement 4: Application restores state from command log upon restart/replay.
    """
    client = TestClient(app)
    log_file = processor.log_path

    # Perform action
    res = client.post("/action/tasks/add", json={"text": "Persist me"})
    assert res.status_code == 200
    task_id = res.json()["id"]

    client.post("/action/document/update", json={"content": "Persisted document content"})

    # Check that log file exists and contains valid JSON lines
    assert os.path.exists(log_file)
    with open(log_file, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    assert len(lines) == 2
    entry1 = json.loads(lines[0])
    assert entry1["command_type"] == "AddTaskCommand"
    assert entry1["payload"]["text"] == "Persist me"
    assert entry1["payload"]["id"] == task_id

    entry2 = json.loads(lines[1])
    assert entry2["command_type"] == "UpdateDocumentCommand"
    assert entry2["payload"]["new_content"] == "Persisted document content"

    # Simulate restart: create new empty state and replay from the exact same log
    new_state = AppState()
    new_processor = CommandProcessor(state=new_state, log_path=log_file)
    assert new_state.to_dict() == {"document": {"content": ""}, "tasks": []}

    replayed = new_processor.replay_history()
    assert replayed == 2
    assert new_state.document.content == "Persisted document content"
    assert len(new_state.tasks) == 1
    assert new_state.tasks[0].id == task_id
    assert new_state.tasks[0].text == "Persist me"

