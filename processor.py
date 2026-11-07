import json
import os
from typing import List, Optional
from models import AppState
from commands import Command, deserialize_command


class CommandProcessor:
    """
    Central service of the workflow engine.
    Orchestrates command execution, maintains undo/redo history stacks,
    and manages the append-only command log (Event Sourcing).
    """

    def __init__(self, state: AppState, log_path: str = "./data/command_log.jsonl"):
        self.state: AppState = state
        self.log_path: str = log_path
        self.undo_stack: List[Command] = []
        self.redo_stack: List[Command] = []

    def execute_command(self, command: Command, is_replay: bool = False) -> None:
        """
        Executes a command against state.
        If is_replay is False (normal user action):
          - pushes command onto undo_stack
          - clears redo_stack (new action invalidates redo history)
          - appends the serialized command to the persistent JSONL log
        """
        command.execute(self.state)

        if not is_replay:
            self.undo_stack.append(command)
            self.redo_stack.clear()
            self._append_to_log(command)

    def undo(self) -> Optional[Command]:
        """
        Reverts the most recently executed command.
        Pops from undo_stack, invokes command.undo(), and pushes to redo_stack.
        Returns None if undo_stack is empty.
        """
        if not self.undo_stack:
            return None

        command = self.undo_stack.pop()
        command.undo(self.state)
        self.redo_stack.append(command)
        return command

    def redo(self) -> Optional[Command]:
        """
        Re-applies the most recently undone command.
        Pops from redo_stack, invokes command.execute(), and pushes back to undo_stack.
        Returns None if redo_stack is empty.
        """
        if not self.redo_stack:
            return None

        command = self.redo_stack.pop()
        command.execute(self.state)
        self.undo_stack.append(command)
        return command

    def replay_history(self) -> int:
        """
        Reads the command log line-by-line and re-executes each command.
        Does NOT push to undo_stack or re-append to the log.
        Reconstructs the exact state that existed before shutdown/restart.
        Returns the number of replayed commands.
        """
        if not os.path.exists(self.log_path):
            return 0

        replayed_count = 0
        with open(self.log_path, "r", encoding="utf-8") as f:
            for line in f:
                line_str = line.strip()
                if not line_str:
                    continue
                try:
                    data = json.loads(line_str)
                    command = deserialize_command(data)
                    self.execute_command(command, is_replay=True)
                    replayed_count += 1
                except Exception as err:
                    print(f"[CommandProcessor] Failed to replay line: {line_str}. Error: {err}")

        return replayed_count

    def _append_to_log(self, command: Command) -> None:
        """
        Appends a serialized command as a single JSON line to the persistent log file.
        Ensures parent directory exists and data is flushed immediately.
        """
        parent_dir = os.path.dirname(self.log_path)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)

        entry = command.to_dict()
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
            f.flush()

