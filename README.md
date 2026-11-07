# Workflow Engine with Undo/Redo & Event Sourcing

A robust, enterprise-grade state workflow engine built with Python, FastAPI, and classic Gang of Four (GoF) design patterns.

## Features

- **Command Pattern**: Encapsulates all state mutations as discrete command objects (`execute()` and `undo()`).
- **Memento Pattern**: Captures snapshots of entity states (e.g. before task deletion) to restore objects perfectly on undo without violating encapsulation.
- **Composite Pattern**: Bundles multi-entity actions (`BulkDeleteTasksCommand`) into atomic units where a single undo step restores all deleted items in reverse order.
- **Event Sourcing Persistence**: Appends every action to an immutable JSON Lines log (`command_log.jsonl`). Replays the log on startup to faithfully reconstruct the in-memory state.
- **Docker Ready**: Fully containerized with a Dockerfile, `docker-compose.yml`, volume persistence, and automatic container health checking.

---

## Architecture Overview

```
+-----------------------------------------------------------+
|                        API Layer                          |
|   POST /action/tasks/add     POST /action/tasks/delete    |
|   POST /action/tasks/bulk-delete                          |
|   POST /action/undo          POST /action/redo            |
|   GET  /state                GET  /health                 |
+-----------------------------+-----------------------------+
                              | Creates command
                              v
                   +---------------------+
                   |  Command Processor  |
                   +----------+----------+
                              |
       +----------------------+----------------------+
       |                      |                      |
       v                      v                      v
+--------------+      +--------------+      +------------------+
| In-Memory    |      | Undo / Redo  |      | Persistent Log   |
| Application  |      | Stacks       |      | command_log.jsonl|
| State        |      |              |      | (Event Sourcing) |
+--------------+      +--------------+      +------------------+
```

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Service healthcheck (200 OK) |
| `GET` | `/state` | Returns current in-memory document & tasks list |
| `POST` | `/action/document/update` | Updates document text content |
| `POST` | `/action/tasks/add` | Adds a task (`{"text": "..."}`) |
| `POST` | `/action/tasks/complete/{id}` | Toggles task completion status |
| `POST` | `/action/tasks/delete/{id}` | Deletes a task using Memento pattern |
| `POST` | `/action/tasks/bulk-delete` | Bulk deletes tasks atomically (Composite) |
| `POST` | `/action/undo` | Reverts last executed command (No-op on empty stack) |
| `POST` | `/action/redo` | Re-applies last undone command (No-op on empty stack) |

---

## Running with Docker Compose

To start the containerized service:

```bash
docker-compose up --build -d
```

Check health:
```bash
docker inspect --format='{{json .State.Health}}' workflow-engine
```

Restart container and verify state restoration:
```bash
docker-compose restart app
```

---

## Running Locally

1. Create and activate a virtual environment (optional):
```bash
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run the application:
```bash
python main.py
```

4. Run the contract tests:
```bash
pytest
```

