"""scripts/ensure_llm.py の起動結果判定を検証する。"""

import importlib.util
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "ensure_llm.py"
SPEC = importlib.util.spec_from_file_location("ensure_llm", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
ensure_llm = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ensure_llm)


class ParseStartActionTests(unittest.TestCase):
    def test_truth_table(self):
        cases = (
            ("HERMES_LLAMA_SERVER_ACTION=started\n", "started"),
            (
                "starting server\n"
                "HERMES_LLAMA_SERVER_ACTION=reused\n"
                "ready\n",
                "reused",
            ),
            ("", None),
            ("LLM_STATUS: started\n", None),
            ("HERMES_LLAMA_SERVER_ACTION=unknown\n", None),
            (
                "HERMES_LLAMA_SERVER_ACTION=started\n"
                "HERMES_LLAMA_SERVER_ACTION=reused\n",
                None,
            ),
        )

        for stdout, expected in cases:
            with self.subTest(stdout=stdout):
                self.assertEqual(ensure_llm.parse_start_action(stdout), expected)


class EnsureTests(unittest.TestCase):
    def _call_ensure(self, *, returncode=0, stdout="", exists=True):
        def run_start(command, **_kwargs):
            action_index = command.index("-ActionFile") + 1
            Path(command[action_index]).write_text(stdout, encoding="utf-8")
            return subprocess.CompletedProcess(command, returncode)

        with (
            patch.object(Path, "exists", return_value=exists),
            patch.object(
                ensure_llm.subprocess, "run", side_effect=run_start
            ) as run,
            patch.object(
                ensure_llm, "wait_until_ready", return_value=True
            ) as wait,
            patch.object(ensure_llm, "write_marker") as marker,
        ):
            actual = ensure_llm.ensure()
        return actual, run, wait, marker

    def test_started_writes_marker_and_waits_until_ready(self):
        actual, run, wait, marker = self._call_ensure(
            stdout="HERMES_LLAMA_SERVER_ACTION=started\n"
        )

        self.assertTrue(actual)
        run.assert_called_once()
        args, kwargs = run.call_args
        self.assertIn("-ActionFile", args[0])
        self.assertIs(kwargs["stdout"], subprocess.DEVNULL)
        self.assertIs(kwargs["stderr"], subprocess.DEVNULL)
        self.assertNotIn("capture_output", kwargs)
        action_index = args[0].index("-ActionFile") + 1
        self.assertFalse(Path(args[0][action_index]).exists())
        wait.assert_called_once_with(240)
        marker.assert_called_once_with()

    def test_reused_waits_without_writing_marker(self):
        actual, run, wait, marker = self._call_ensure(
            stdout="HERMES_LLAMA_SERVER_ACTION=reused\n"
        )

        self.assertTrue(actual)
        run.assert_called_once()
        wait.assert_called_once_with(240)
        marker.assert_not_called()

    def test_missing_unknown_or_duplicate_sentinel_fails_without_waiting(self):
        for stdout in (
            "",
            "HERMES_LLAMA_SERVER_ACTION=unknown\n",
            "HERMES_LLAMA_SERVER_ACTION=started\n"
            "HERMES_LLAMA_SERVER_ACTION=reused\n",
        ):
            with self.subTest(stdout=stdout):
                actual, run, wait, marker = self._call_ensure(stdout=stdout)

                self.assertFalse(actual)
                run.assert_called_once()
                wait.assert_not_called()
                marker.assert_not_called()

    def test_nonzero_return_code_fails_without_waiting(self):
        actual, run, wait, marker = self._call_ensure(
            returncode=1,
            stdout="HERMES_LLAMA_SERVER_ACTION=started\n",
        )

        self.assertFalse(actual)
        run.assert_called_once()
        wait.assert_not_called()
        marker.assert_not_called()

    def test_temporary_file_creation_failure_does_not_invoke_subprocess(self):
        with (
            patch.object(Path, "exists", return_value=True),
            patch.object(
                ensure_llm.tempfile,
                "NamedTemporaryFile",
                side_effect=OSError("disk unavailable"),
            ),
            patch.object(ensure_llm.subprocess, "run") as run,
        ):
            self.assertFalse(ensure_llm.ensure())

        run.assert_not_called()

    def test_timeout_removes_action_file_and_fails_without_waiting(self):
        action_paths = []

        def time_out(command, **_kwargs):
            action_index = command.index("-ActionFile") + 1
            action_path = Path(command[action_index])
            action_path.write_text(
                "HERMES_LLAMA_SERVER_ACTION=started\n", encoding="utf-8"
            )
            action_paths.append(action_path)
            raise subprocess.TimeoutExpired(command, 120)

        with (
            patch.object(Path, "exists", return_value=True),
            patch.object(ensure_llm.subprocess, "run", side_effect=time_out),
            patch.object(ensure_llm, "wait_until_ready") as wait,
            patch.object(ensure_llm, "write_marker") as marker,
        ):
            self.assertFalse(ensure_llm.ensure())

        self.assertEqual(len(action_paths), 1)
        self.assertFalse(action_paths[0].exists())
        wait.assert_not_called()
        marker.assert_not_called()

    def test_missing_script_does_not_invoke_subprocess(self):
        actual, run, wait, marker = self._call_ensure(exists=False)

        self.assertFalse(actual)
        run.assert_not_called()
        wait.assert_not_called()
        marker.assert_not_called()


if __name__ == "__main__":
    unittest.main()
