"""install.py against a throwaway home folder. Run: python3 -m unittest discover -s tests -v"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

INSTALL = Path(__file__).resolve().parent.parent / "install.py"


class InstallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        (self.home / ".claude").mkdir()
        (self.home / ".codex").mkdir()
        self.settings = self.home / ".claude" / "settings.json"
        self.settings.write_text(json.dumps({
            "model": "opus",
            "hooks": {"PreToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "~/bin/other-hook.sh"}]},
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "/usr/bin/python3 /old/place/identity-guard.py"}]},
            ]},
        }))
        self.env = {**os.environ, "HOME": str(self.home)}
        self.env.pop("CLAUDE_CONFIG_DIR", None)
        self.env.pop("CODEX_HOME", None)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def install(self, *args: str) -> str:
        done = subprocess.run([sys.executable, str(INSTALL), *args], capture_output=True, text=True, env=self.env, timeout=60)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return done.stdout

    def ours(self, path: Path) -> list:
        groups = json.loads(path.read_text()).get("hooks", {}).get("PreToolUse", [])
        return [h for g in groups for h in g["hooks"] if "identity_guard" in h["command"] or "identity-guard" in h["command"]]

    def test_install_merges_replaces_old_entry_and_is_idempotent(self) -> None:
        self.install("--name", "Jane Testperson", "--email", "jane@example.org")
        settings = json.loads(self.settings.read_text())
        self.assertEqual(settings["model"], "opus")
        commands = [h["command"] for g in settings["hooks"]["PreToolUse"] for h in g["hooks"]]
        self.assertIn("~/bin/other-hook.sh", commands)
        self.assertEqual(len(self.ours(self.settings)), 1)
        self.assertIn(".identity-guard/identity_guard.py", self.ours(self.settings)[0]["command"])
        self.assertTrue((self.home / ".claude" / "settings.json.bak").exists())
        codex = self.home / ".codex" / "hooks.json"
        self.assertEqual(json.loads(codex.read_text())["hooks"]["PreToolUse"][0]["matcher"], "*")
        config = json.loads((self.home / ".identity-guard" / "config.json").read_text())
        self.assertEqual(config["markers"]["names"], ["Jane Testperson"])
        self.assertEqual(config["markers"]["emails"], ["jane@example.org"])
        self.assertEqual(config["markers"]["phones"], [])  # the example's sample values are not copied
        self.assertEqual(oct((self.home / ".identity-guard" / "config.json").stat().st_mode & 0o777), "0o600")
        again = self.install("--name", "Jane Testperson")
        self.assertIn("unchanged", again)
        self.assertIn("kept", again)
        self.assertEqual(len(self.ours(self.settings)), 1)

    def test_dry_run_changes_nothing(self) -> None:
        before = self.settings.read_text()
        out = self.install("--dry-run", "--name", "Jane Testperson")
        self.assertIn("would update", out)
        self.assertEqual(self.settings.read_text(), before)
        self.assertFalse((self.home / ".identity-guard").exists())
        self.assertFalse((self.home / ".codex" / "hooks.json").exists())

    def test_uninstall_keeps_other_hooks(self) -> None:
        self.install()
        self.install("--uninstall", "--purge")
        self.assertEqual(self.ours(self.settings), [])
        commands = [h["command"] for g in json.loads(self.settings.read_text())["hooks"]["PreToolUse"] for h in g["hooks"]]
        self.assertEqual(commands, ["~/bin/other-hook.sh"])
        self.assertNotIn("hooks", json.loads((self.home / ".codex" / "hooks.json").read_text()))
        self.assertFalse((self.home / ".identity-guard").exists())


if __name__ == "__main__":
    unittest.main()
