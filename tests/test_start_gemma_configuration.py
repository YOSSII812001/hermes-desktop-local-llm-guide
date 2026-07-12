import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class GemmaCheckpointConfigurationTests(unittest.TestCase):
    def test_start_script_disables_and_matches_context_checkpoints(self):
        script = (ROOT / "scripts" / "start-gemma-llama-server.ps1").read_text(
            encoding="utf-8"
        )

        self.assertIn("[int]$ContextCheckpoints = 0", script)
        self.assertIn(
            '"--ctx-checkpoints", [string]$ContextCheckpoints', script
        )
        self.assertIn(
            '-Name "--ctx-checkpoints" '
            '-ExpectedValue ([string]$ContextCheckpoints)',
            script,
        )

    def test_desktop_launcher_requires_and_propagates_same_value(self):
        script = (
            ROOT / "scripts" / "start-hermes-desktop-with-local-llm.ps1"
        ).read_text(encoding="utf-8")

        self.assertIn("[int]$ExpectedContextCheckpoints = 0", script)
        self.assertIn(
            '-Name "--ctx-checkpoints" '
            '-ExpectedValue ([string]$ExpectedContextCheckpoints)',
            script,
        )
        self.assertIn(
            "-ContextCheckpoints $ExpectedContextCheckpoints", script
        )


if __name__ == "__main__":
    unittest.main()
