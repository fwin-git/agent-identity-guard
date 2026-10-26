"""install.py against a throwaway home folder. Run: python3 -m unittest discover -s tests -v"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path, PureWindowsPath

REPO = Path(__file__).resolve().parent.parent
INSTALL = REPO / "install.py"
sys.path.insert(0, str(REPO))
import install  # noqa: E402  (the module under test, for its pure functions)

FAKE_CODEX = """import json, os, sys
from pathlib import Path
hooks_file = Path.home() / ".codex" / "hooks.json"
status = os.environ.get("FAKE_CODEX_TRUST", "untrusted")
for line in sys.stdin:
    message = json.loads(line)
    if message.get("id") == 1:
        print(json.dumps({"id": 1, "result": {}}), flush=True)
    elif message.get("id") == 2:
        hooks = [{"key": f"{hooks_file}:{name}:0:0", "eventName": event, "trustStatus": status}
                 for name, event in (("pre_tool_use", "preToolUse"), ("session_start", "sessionStart"))]
        print(json.dumps({"id": 2, "result": {"data": [{"cwd": str(Path.home()), "hooks": hooks}]}}), flush=True)
"""


def home_env(home: Path, **extra: str) -> dict:
    """An environment whose home folder is `home` on every platform (HOME on macOS/Linux, USERPROFILE on Windows)."""
    env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home), "PYTHONIOENCODING": "utf-8", **extra}
    for name in ("CLAUDE_CONFIG_DIR", "CODEX_HOME", "CLAUDE_CODE_USER_EMAIL", "IDENTITY_GUARD_CONFIG"):
        env.pop(name, None)
    return env


def guard_entries(path: Path, event: str) -> list:
    groups = json.loads(path.read_text()).get("hooks", {}).get(event, [])
    return [h for g in groups for h in g["hooks"] if "identity_guard" in json.dumps(h) or "identity-guard.py" in json.dumps(h)]


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
        self.env = home_env(self.home)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def install(self, *args: str) -> str:
        done = subprocess.run([sys.executable, str(INSTALL), *args], capture_output=True, text=True, encoding="utf-8", errors="replace", env=self.env, timeout=60)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return done.stdout

    def ours(self, path: Path) -> list:
        return guard_entries(path, "PreToolUse")

    def test_install_merges_replaces_old_entry_and_is_idempotent(self) -> None:
        self.install("--name", "Jane Testperson", "--email", "jane@example.org")
        settings = json.loads(self.settings.read_text())
        self.assertEqual(settings["model"], "opus")
        commands = [h["command"] for g in settings["hooks"]["PreToolUse"] for h in g["hooks"]]
        self.assertIn("~/bin/other-hook.sh", commands)
        self.assertEqual(len(self.ours(self.settings)), 1)
        self.assertIn("identity_guard.py", json.dumps(self.ours(self.settings)[0]))
        self.assertEqual(len(guard_entries(self.settings, "SessionStart")), 1)  # the session note
        self.assertTrue((self.home / ".claude" / "settings.json.bak").exists())
        codex = self.home / ".codex" / "hooks.json"
        self.assertEqual(json.loads(codex.read_text())["hooks"]["PreToolUse"][0]["matcher"], "*")
        self.assertEqual(len(guard_entries(codex, "SessionStart")), 1)
        config = json.loads((self.home / ".identity-guard" / "config.json").read_text())
        self.assertEqual(config["markers"]["names"], ["Jane Testperson"])
        self.assertEqual(config["markers"]["emails"], ["jane@example.org"])
        self.assertEqual(config["markers"]["phones"], [])  # the example's sample values are not copied
        if os.name != "nt":  # Windows has no permission bits; the user folder's own permissions keep it private
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
        self.assertNotIn("SessionStart", json.loads(self.settings.read_text())["hooks"])
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
        self.env = home_env(self.home, USER="demo", GIT_CONFIG_GLOBAL=str(gitconfig))
        self.config_file = self.home / ".identity-guard" / "config.json"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_setup(self, *answers: str, script: str = "setup.sh") -> subprocess.CompletedProcess:
        if script == "setup.sh":
            command = ["cmd", "/c", str(REPO / "setup.cmd")] if os.name == "nt" else [str(REPO / "setup.sh")]
        else:
            command = [sys.executable, str(INSTALL), "--guided"]
        return subprocess.run(command, input="\n".join(answers) + "\n", capture_output=True, text=True, encoding="utf-8", errors="replace", env=self.env, timeout=120)

    def config(self) -> dict:
        return json.loads(self.config_file.read_text())

    def test_first_run_asks_validates_and_installs(self) -> None:
        done = self.run_setup(
            "J", "Jane Testperson", "",     # full name (the first try is refused), also the surname alone
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
        self.assertIn("too short; try again", out)
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
        if os.name != "nt":
            self.assertEqual(oct(self.config_file.stat().st_mode & 0o777), "0o600")
        settings = json.loads((self.home / ".claude" / "settings.json").read_text())
        self.assertIn("identity_guard.py", json.dumps(settings["hooks"]["PreToolUse"][0]["hooks"][0]))  # command or, on Windows, args
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
        self.assertIn("Scanned 1 tool call (1 Claude Code, 0 Codex)", done.stdout)  # Enter accepts the audit
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


class WindowsCommandTests(unittest.TestCase):
    script = PureWindowsPath(r"C:\Users\Jane Doe\.identity-guard\identity_guard.py")

    def test_claude_starts_python_directly_on_windows(self) -> None:
        entries = install.hook_entries(r"C:\Python313\python.exe", self.script, windows=True, py_launcher="py -3.13")
        self.assertEqual(entries["claude"], {"command": r"C:\Python313\python.exe", "args": [str(self.script)]})

    def test_codex_gets_a_command_for_cmd_and_powershell(self) -> None:
        entries = install.hook_entries(r"C:\Python313\python.exe", self.script, windows=True, py_launcher="py -3.13")
        expected = r'py -3.13 "C:\Users\Jane Doe\.identity-guard\identity_guard.py"'
        self.assertEqual(entries["codex"], {"command": expected, "commandWindows": expected})

    def test_without_the_py_launcher_a_path_with_spaces_is_quoted(self) -> None:
        entries = install.hook_entries(r"C:\Program Files\Python313\python.exe", self.script, windows=True, py_launcher="")
        self.assertTrue(entries["codex"]["command"].startswith('"C:\\Program Files\\Python313\\python.exe" "'))

    def test_posix_gets_a_quoted_command_line(self) -> None:
        entries = install.hook_entries("/usr/bin/python3", "/home/jane doe/.identity-guard/identity_guard.py", windows=False)
        self.assertEqual(entries["claude"]["command"], "/usr/bin/python3 '/home/jane doe/.identity-guard/identity_guard.py'")
        self.assertEqual(entries["claude"], entries["codex"])

    def test_exec_form_entries_are_recognized_as_ours(self) -> None:
        import identity_guard
        self.assertTrue(identity_guard.is_guard_entry({"command": r"C:\Py\python.exe", "args": [str(self.script)]}))
        self.assertTrue(identity_guard.is_guard_entry({"command": "x", "commandWindows": f'py -3 "{self.script}"'}))
        self.assertFalse(identity_guard.is_guard_entry({"command": "~/bin/other-hook.sh"}))


class CodexTrustTests(unittest.TestCase):
    """doctor asks a stand-in `codex app-server` for the trust status of both hooks (also on Windows)."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        (self.home / ".codex").mkdir()
        bin_dir = self.home / "bin"
        bin_dir.mkdir()
        (bin_dir / "fake_codex.py").write_text(FAKE_CODEX)
        if os.name == "nt":
            (bin_dir / "codex.cmd").write_text(f'@"{sys.executable}" "{bin_dir / "fake_codex.py"}" %*\r\n')
        else:
            wrapper = bin_dir / "codex"
            wrapper.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{bin_dir / "fake_codex.py"}" "$@"\n')
            wrapper.chmod(0o755)
        self.path = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
        subprocess.run([sys.executable, str(INSTALL), "--agents", "codex", "--email", "jane@example.org"],
                       env=home_env(self.home, PATH=self.path), capture_output=True, text=True, encoding="utf-8", errors="replace", check=True, timeout=60)

    def tearDown(self) -> None:
        for _ in range(20):  # Windows can take a moment to release a just-ended process's files
            try:
                self.tmp.cleanup()
                return
            except PermissionError:
                time.sleep(0.25)

    def doctor(self, trust: str) -> str:
        guard = self.home / ".identity-guard" / "identity_guard.py"
        done = subprocess.run([sys.executable, str(guard), "doctor"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
                              env=home_env(self.home, PATH=self.path, FAKE_CODEX_TRUST=trust))
        return done.stdout

    def test_both_hooks_trusted(self) -> None:
        out = self.doctor("trusted")
        self.assertIn("Codex CLI    protected", out)
        self.assertIn("Session note", out)

    def test_waiting_for_approval(self) -> None:
        out = self.doctor("untrusted")
        self.assertIn("Codex CLI    waiting for your approval", out)
        self.assertIn("trust identity-guard (both hooks)", out)

    def test_changed_since_approval(self) -> None:
        self.assertIn("changed since you approved it", self.doctor("modified"))


if __name__ == "__main__":
    unittest.main()
