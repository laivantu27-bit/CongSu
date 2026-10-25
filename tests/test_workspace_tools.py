import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from assistant_desktop.desktop_tools import DesktopToolError
from assistant_desktop.workspace_tools import (
    delete_workspace_file,
    list_workspace,
    read_workspace_file,
    resolve_workspace_path,
    run_allowed_command,
    validate_workspace_tool,
    write_workspace_file,
)


class WorkspaceToolTests(unittest.TestCase):
    def test_read_write_list_and_delete_are_confined_to_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_workspace_file(root, "notes.txt", "Xin chào")

            self.assertEqual(read_workspace_file(root, "notes.txt"), "Xin chào")
            self.assertEqual(
                list_workspace(root),
                [{"name": "notes.txt", "type": "file"}],
            )
            delete_workspace_file(root, "notes.txt")
            self.assertFalse((root / "notes.txt").exists())

    def test_rejects_traversal_and_directory_deletion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            root.mkdir()
            with self.assertRaises(DesktopToolError):
                resolve_workspace_path(root, "..\\outside.txt")
            with self.assertRaises(DesktopToolError):
                delete_workspace_file(root, ".")

    def test_write_tool_rejects_non_text_and_oversized_contents(self):
        with self.assertRaises(DesktopToolError):
            validate_workspace_tool(
                "workspace_write", {"path": "notes.txt", "content": 1}
            )
        with self.assertRaises(DesktopToolError):
            validate_workspace_tool(
                "workspace_write",
                {"path": "notes.txt", "content": "x" * 1_000_001},
            )
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(DesktopToolError):
                write_workspace_file(
                    directory,
                    "notes.txt",
                    "\ud800",
                )

    def test_allowed_command_uses_fixed_argv_without_a_shell(self):
        completed = type(
            "Completed",
            (),
            {"stdout": "Python 3.12", "stderr": "", "returncode": 0},
        )()
        with patch(
            "assistant_desktop.workspace_tools.subprocess.run",
            return_value=completed,
        ) as run:
            self.assertEqual(run_allowed_command("python_version"), "Python 3.12")
        self.assertEqual(
            run.call_args.args[0],
            ("python", "--version"),
        )
        self.assertFalse(run.call_args.kwargs["shell"])
        with self.assertRaises(DesktopToolError):
            run_allowed_command("powershell")


if __name__ == "__main__":
    unittest.main()
