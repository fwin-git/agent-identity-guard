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


class GuidedSetupTests(unittest.TestCase):
    """./setup.sh with scripted answers, in a throwaway home with Claude Code only (no Codex query)."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        (self.home / ".claude").mkdir()
        session = self.home / ".claude" / "projects" / "p" / "s.jsonl"  # one past session, so the audit is offered
        session.parent.mkdir(parents=True)
        session.write_text(json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "ls"}}]}}) + "\n")
        gitconfig = self.home / "gitconfig"
        gitconfig.write_text("[user]\n\temail = jane.work@example.org\n")
        self.env = {**os.environ, "HOME": str(self.home), "USER": "demo", "GIT_CONFIG_GLOBAL": str(gitconfig)}
        for name in ("CLAUDE_CONFIG_DIR", "CODEX_HOME", "CLAUDE_CODE_USER_EMAIL"):
            self.env.pop(name, None)
        self.config_file = self.home / ".identity-guard" / "config.json"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_setup(self, *answers: str, script: str = "setup.sh") -> subprocess.CompletedProcess:
        command = [str(INSTALL.parent / "setup.sh")] if script == "setup.sh" else [sys.executable, str(INSTALL), "--guided"]
        return subprocess.run(command, input="\n".join(answers) + "\n", capture_output=True, text=True, env=self.env, timeout=120)

    def config(self) -> dict:
        return json.loads(self.config_file.read_text())

    def test_first_run_asks_validates_and_installs(self) -> None:
        done = self.run_setup(
            "Jane Testperson", "",          # full name, also the surname alone
            "jt", "demo", "",               # other names; the login name is refused
            "jane@example.org", "nope", "",  # emails; the second is refused
            "n", "",                        # not the git email; yes the Claude Code account email
            "+44 20 7946 0958", "12", "",   # phones; the second is refused
            "",                             # nothing else
            "",                             # install now
            "n",                            # no audit
        )
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        out = done.stdout
        self.assertIn("can't be used", out)
        self.assertIn("doesn't look like an email address", out)
        self.assertIn("needs at least 6 digits", out)
        self.assertIn("Your git email is jane.work@example.org", out)
        markers = self.config()["markers"]
        self.assertEqual(markers["names"], ["Jane Testperson", "Testperson", "jt"])
        self.assertEqual(markers["emails"], ["jane@example.org"])
        self.assertEqual(markers["phones"], ["+44 20 7946 0958"])
        self.assertEqual(markers["other"], [])
        self.assertFalse(self.config()["auto_markers"]["git_email"])
        self.assertTrue(self.config()["auto_markers"]["claude_code_account_email"])
        self.assertEqual(oct(self.config_file.stat().st_mode & 0o777), "0o600")
        settings = json.loads((self.home / ".claude" / "settings.json").read_text())
        self.assertIn("identity_guard.py", settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"])
        self.assertLess(out.index("Summary"), out.index("Installed"))
        self.assertLess(out.index("Installed"), out.index("Claude Code  protected"))  # then the status
        self.assertLess(out.index("Claude Code  protected"), out.index("Look back"))  # then the audit offer
        self.assertIn("reads your 1 past", out)
        self.assertIn("Run it any time:", out)  # declined: says how to run it later
        self.assertLess(out.index("Look back"), out.index("Done."))  # the closing line comes last
        self.assertNotIn("One more step", out)  # no Codex here, so nothing to approve
        self.assertNotIn("\033[", out)  # no colors outside a terminal

    def test_second_run_adds_on_top(self) -> None:
        self.run_setup("Jane Testperson", "", "", "jane@example.org", "", "n", "", "", "", "", "n")
        done = self.run_setup("", "", "second@example.org", "", "", "", "", "", "", "", script="install.py")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("Already in your config", done.stdout)
        self.assertIn("Scanned 1 Claude Code and 0 Codex tool calls", done.stdout)  # Enter accepts the audit
        self.assertEqual(self.config()["markers"]["emails"], ["jane@example.org", "second@example.org"])
        self.assertEqual(self.config()["markers"]["names"], ["Jane Testperson", "Testperson"])
        self.assertFalse(self.config()["auto_markers"]["git_email"])  # the earlier answer is the new default

    def test_saying_no_changes_nothing(self) -> None:
        done = self.run_setup("Jane Testperson", "", "", "", "", "", "", "", "n", script="install.py")
        self.assertEqual(done.returncode, 1)
        self.assertIn("Nothing was changed", done.stdout)
        self.assertFalse((self.home / ".identity-guard").exists())
        self.assertFalse((self.home / ".claude" / "settings.json").exists())

    def test_running_out_of_input_changes_nothing(self) -> None:
        done = self.run_setup("Jane Testperson", script="install.py")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("nothing was changed", done.stdout + done.stderr)
        self.assertFalse((self.home / ".identity-guard").exists())


if __name__ == "__main__":
    unittest.main()
