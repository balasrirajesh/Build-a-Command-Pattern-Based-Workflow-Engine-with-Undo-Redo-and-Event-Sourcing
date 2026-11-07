from typing import List, Optional, Dict, Any


class Document:
    """
    Represents the document in our application.
    It contains a single string property: content.
    Initially, content is an empty string ("").
    """
    def __init__(self, content: str = ""):
        self.content: str = content

    def to_dict(self) -> Dict[str, Any]:
        """Converts the Document object into a plain Python dictionary for JSON output."""
        return {
            "content": self.content
        }


class Task:
    """
    Represents a single Task in our application.
    Each task has:
      - id: A unique string identifier (e.g. UUID).
      - text: The task description text.
      - completed: Boolean flag (True or False) indicating if the task is done.
    """
    def __init__(self, id: str, text: str, completed: bool = False):
        self.id: str = id
        self.text: str = text
        self.completed: bool = completed

    def copy(self) -> "Task":
        """
        Creates an exact duplicate snapshot of this task (Memento Pattern).
        This ensures that if the task in state changes later, this snapshot remains untouched.
        """
        return Task(
            id=self.id,
            text=self.text,
            completed=self.completed
        )

    def to_dict(self) -> Dict[str, Any]:
        """Converts the Task object into a plain Python dictionary for JSON output."""
        return {
            "id": self.id,
            "text": self.text,
            "completed": self.completed
        }


class AppState:
    """
    Holds the complete in-memory state of the application:
      1. document: An instance of Document
      2. tasks: A list of Task instances
    """
    def __init__(self):
        self.document: Document = Document()
        self.tasks: List[Task] = []

    def get_task(self, task_id: str) -> Optional[Task]:
        """Finds and returns a task by its unique id. Returns None if not found."""
        for task in self.tasks:
            if task.id == task_id:
                return task
        return None

    def add_task(self, task: Task) -> None:
        """Appends a new task to the end of our task list."""
        self.tasks.append(task)

    def remove_task(self, task_id: str) -> Optional[Task]:
        """
        Removes a task with the given id from our task list.
        Returns the removed task, or None if it was not found.
        """
        for index, task in enumerate(self.tasks):
            if task.id == task_id:
                return self.tasks.pop(index)
        return None

    def to_dict(self) -> Dict[str, Any]:
        """
        Converts the entire application state into a clean dictionary.
        Matches the required initial state:
        {
            "document": {
                "content": ""
            },
            "tasks": []
        }
        """
        return {
            "document": self.document.to_dict(),
            "tasks": [task.to_dict() for task in self.tasks]
        }

