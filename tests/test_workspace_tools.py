import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from assistant_desktop.desktop_tools import DesktopToolError
from assistant_desktop.workspace_tools import (
    copy_workspace_file,
    create_workspace_directory,
    delete_workspace_file,
    list_workspace,
    move_workspace_file,
    read_workspace_file,
    resolve_workspace_path,
    mcp_permission_enabled,
    run_allowed_command,
    search_workspace,
    validate_workspace_tool,
    write_workspace_file,
)


class WorkspaceToolTests(unittest.TestCase):
    def test_mcp_mutation_permissions_default_to_disabled(self):
        for permission in (
            "file_write",
            "file_delete",
            "memory_write",
            "memory_delete",
            "memory_clear",
            "browser_automation",
            "system_commands",
        ):
            with self.subTest(permission=permission):
                with patch.dict("os.environ", {}, clear=True):
                    self.assertFalse(mcp_permission_enabled(permission))

        with patch.dict(
            "os.environ",
            {"ASSISTANT_MCP_ALLOW_FILE_WRITE": "true"},
            clear=True,
        ):
            self.assertTrue(mcp_permission_enabled("file_write"))

    def test_read_write_list_and_delete_are_confined_to_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_workspace_file(root, "notes.txt", "Xin chào")

            self.assertEqual(read_workspace_file(root, "notes.txt"), "Xin chào")
            self.assertEqual(
                list_workspace(root),
                [{"name": "notes.txt", "type": "file"}],
            )
            self.assertEqual(
                search_workspace(root, "chào"),
                [{"path": "notes.txt", "line": 1, "text": "Xin chào"}],
            )
            delete_workspace_file(root, "notes.txt")
            self.assertFalse((root / "notes.txt").exists())

    def test_create_copy_and_move_files_within_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace_directory(root, "notes")
            (root / "notes" / "original.txt").write_text("nội dung", encoding="utf-8")

            copy_workspace_file(root, "notes/original.txt", "notes/copy.txt")
            move_workspace_file(root, "notes/copy.txt", "notes/renamed.txt")

            self.assertEqual(
                read_workspace_file(root, "notes/renamed.txt"),
                "nội dung",
            )
            with self.assertRaises(DesktopToolError):
                copy_workspace_file(
                    root, "notes/original.txt", "notes/renamed.txt"
                )

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

    def test_workspace_commands_use_the_configured_workspace_and_fixed_arguments(self):
        completed = type(
            "Completed",
            (),
            {"stdout": "Ran 2 tests", "stderr": "", "returncode": 0},
        )()
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(
                "os.environ", {"ASSISTANT_WORKSPACE": directory}, clear=True
            ):
                with patch(
                    "assistant_desktop.workspace_tools.subprocess.run",
                    return_value=completed,
                ) as run:
                    self.assertEqual(
                        run_allowed_command("workspace_tests"), "Ran 2 tests"
                    )
            self.assertEqual(
                run.call_args.args[0][1:],
                ("-m", "unittest", "discover", "-s", "tests"),
            )
            self.assertEqual(run.call_args.kwargs["cwd"], Path(directory))
            self.assertFalse(run.call_args.kwargs["shell"])


if __name__ == "__main__":
    unittest.main()
