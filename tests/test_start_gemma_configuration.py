import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class GemmaCheckpointConfigurationTests(unittest.TestCase):
    def test_runtime_defaults_use_validated_b9637_build(self):
        scripts = [
            ROOT / "scripts" / "start-gemma-llama-server.ps1",
            ROOT / "scripts" / "stop-gemma-llama-server.ps1",
            ROOT / "scripts" / "start-hermes-desktop-with-local-llm.ps1",
            ROOT / "scripts" / "watch-hermes-process-and-stop-gemma.ps1",
        ]

        for path in scripts:
            script = path.read_text(encoding="utf-8")
            self.assertIn("llama.cpp-b9637-cuda-12.4", script, path.name)
            self.assertNotIn("llama.cpp-b9498-cuda-12.4", script, path.name)

    def test_start_script_disables_and_matches_context_checkpoints(self):
        script = (ROOT / "scripts" / "start-gemma-llama-server.ps1").read_text(
            encoding="utf-8"
        )

        self.assertIn("[int]$ContextCheckpoints = 0", script)
        self.assertIn("[int]$ContextSize = 65536", script)
        self.assertIn(
            '"--ctx-checkpoints", [string]$ContextCheckpoints', script
        )
        self.assertIn(
            '-Name "--ctx-checkpoints" '
            '-ExpectedValue ([string]$ContextCheckpoints)',
            script,
        )
        self.assertIn(
            '-Name "--ctx-size" '
            '-ExpectedValue ([string]$ContextSize)',
            script,
        )

    def test_desktop_launcher_requires_and_propagates_same_value(self):
        script = (
            ROOT / "scripts" / "start-hermes-desktop-with-local-llm.ps1"
        ).read_text(encoding="utf-8")

        self.assertIn("[int]$ExpectedContextCheckpoints = 0", script)
        self.assertIn("[int]$ExpectedContextSize = 65536", script)
        self.assertIn(
            '-Name "--ctx-checkpoints" '
            '-ExpectedValue ([string]$ExpectedContextCheckpoints)',
            script,
        )
        self.assertIn(
            "-ContextCheckpoints $ExpectedContextCheckpoints", script
        )
        self.assertIn("-ContextSize $ExpectedContextSize", script)


if __name__ == "__main__":
    unittest.main()
