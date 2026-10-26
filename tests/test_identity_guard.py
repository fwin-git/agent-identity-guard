"""identity_guard.py with a made-up identity. Run: python3 -m unittest discover -s tests -v"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

GUARD = Path(__file__).resolve().parent.parent / "identity_guard.py"
EMAIL = "jane.testperson@example.org"
PHONE = "+44 20 7946 0958"
CONFIG = {
    "markers": {
        "emails": [EMAIL],
        "names": ["Jane Testperson", "Testperson", "tester"],
        "phones": [PHONE],
        "other": ["42 Example Street"],
    },
    "auto_markers": {"claude_code_account_email": False, "git_email": False},
    "ignore": [],
    "local_hosts": ["*.home.arpa"],
}


class GuardTestCase(unittest.TestCase):
    config: dict = CONFIG

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.config_file = Path(cls.tmp.name) / "config.json"
        cls.config_file.write_text(json.dumps({**cls.config, "log_file": "guard.log"}))
        cls.env = {
            **os.environ,
            "IDENTITY_GUARD_CONFIG": str(cls.config_file),
            "USER": "tester",
            "CLAUDE_CONFIG_DIR": str(Path(cls.tmp.name) / "claude"),  # keep doctor/audit off the real setup
            "CODEX_HOME": str(Path(cls.tmp.name) / "codex"),
        }

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def run_guard(self, tool: str, tool_input: dict, stdin: str | None = None) -> dict:
        payload = stdin if stdin is not None else json.dumps({"tool_name": tool, "tool_input": tool_input, "session_id": "test"})
        done = subprocess.run([sys.executable, str(GUARD)], input=payload, capture_output=True, text=True, env=self.env, timeout=20)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout) if done.stdout.strip() else {}

    def cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(GUARD), *args], capture_output=True, text=True, env=self.env, timeout=60)

    def assertDenied(self, tool: str, tool_input: dict) -> dict:
        out = self.run_guard(tool, tool_input)
        self.assertEqual(out.get("hookSpecificOutput", {}).get("permissionDecision"), "deny", (tool, tool_input))
        self.assertNotIn(EMAIL, json.dumps(out))  # the reason never repeats the value
        return out

    def assertAllowed(self, tool: str, tool_input: dict) -> None:
        self.assertEqual(self.run_guard(tool, tool_input), {}, (tool, tool_input))


class HttpTests(GuardTestCase):
    def test_shell_requests_carrying_identity_are_denied(self) -> None:
        for command in [
            f'curl -s -A "research-bot/1.0 (contact: {EMAIL})" "https://api.example.org/search"',
            'UA="Bot (Jane Testperson)"; curl -A "$UA" https://archives.example.net/api.php',
            f'PIPELINE_HTTP_CONTACT="{EMAIL}" uv run crawler',
            'curl -A "bot ($CLAUDE_CODE_USER_EMAIL)" https://example.org',
            'curl -H "From: $(git config user.email)" https://example.org',
            f"python3 - <<'EOF'\nimport urllib.request\nreq = urllib.request.Request(url, headers={{'User-Agent': 'x ({EMAIL})'}})\nEOF",
            'curl "https://example.org/search?q=jane.testperson%40example.org"',
            'curl "https://example.org/u/jane_testperson"',
            f'curl -A "{EMAIL}" "http://[broken" https://example.org',
            'E=$(git config user.email); curl -A "bot ($E)" https://example.org',
            "python3 - <<'EOF'\nimport os, urllib.request\nme = os.environ['CLAUDE_CODE_USER_EMAIL']\n"
            "urllib.request.urlopen(urllib.request.Request('https://example.org', headers={'From': me}))\nEOF",
            "cat <<EOF | curl -d @- https://example.org\nname: Jane Testperson\nEOF",
            f"cat > fetch.sh <<'EOF'\ncurl -A 'bot ({EMAIL})' \"$1\"\nEOF",
            'curl -d "phone=+44-20-7946 0958" https://forms.example.com',
            'curl -d "phone=0044 20 7946 0958" https://forms.example.com',
            'curl "https://maps.example.com/?q=42+Example+Street"',
            f"node -e \"require('axios').post('https://hooks.example.net', {{who: '{EMAIL}'}})\"",
        ]:
            self.assertDenied("Bash", {"command": command})

    def test_shell_commands_without_outgoing_identity_are_allowed(self) -> None:
        for command in [
            'curl -s -A "research-bot/1.0" https://api.example.org/search',
            f"git log --author={EMAIL} --oneline",
            "grep -rn -A 3 Testperson docs/",
            f"curl -d '{{\"email\": \"{EMAIL}\"}}' http://127.0.0.1:3000/signup",
            f'curl -A "{EMAIL}" http://nas.home.arpa:8080/',
            "echo $CLAUDE_CODE_USER_EMAIL",
            "curl -O https://cdn.example.com/avatars/jane.png",
            "git clone https://github.com/tester/project.git",
            "git config user.name 2>/dev/null; gh api user --jq .login",
            "mkdir -p fastlane && cat > fastlane/Appfile <<'EOF'\nteam_id \"ABC\" # Jane Testperson (personal)\nEOF\n"
            "cat > fastlane/Fastfile <<'EOF'\n# docs: https://docs.fastlane.tools\nEOF",
            "cat > LICENSE <<EOF\nCopyright (c) 2026 Jane Testperson\nhttps://opensource.org/licenses/MIT\nEOF",
            "curl -d 'order=44207946095812' https://shop.example.com",  # the phone's digits inside a longer number
        ]:
            self.assertAllowed("Bash", {"command": command})


class ChannelTests(GuardTestCase):
    def test_other_channels_carrying_identity_are_denied(self) -> None:
        for command in [
            'gh issue create -R someone/repo --title bug --body "reported by Jane Testperson"',
            f'gh pr comment 12 --body "ping {EMAIL}"',
            'ssh build.example.net "echo Jane Testperson >> visitors.txt"',
            'BatchMode=yes ssh -o ConnectTimeout=1 host.example.net "echo Jane Testperson"',
            'bash -c "ssh host.example.net \'echo Jane Testperson\'"',
            "scp notes.txt deploy@host.example.net:/srv/Jane_Testperson.txt",
            'rsync -az "Jane Testperson/" deploy@host.example.net:/srv/backup/',
            'printf "hi from Jane Testperson" | nc paste.example.net 9999',
            f"socat - TCP:paste.example.net:9999 <<< '{EMAIL}'",
            f'echo "from {EMAIL}" | mail -s hello someone@example.com',
            "dig jane-testperson.collector.example.net",
            "nslookup jane.testperson.collector.example.net",
            "ping -c 1 jane-testperson.example.net",
            "python3 -c \"import socket; socket.create_connection(('x.example.net', 80)).send(b'Jane Testperson')\"",
            f"python3 - <<'EOF'\nimport smtplib\nsmtplib.SMTP('mx.example.net').sendmail('{EMAIL}', ['a@b.c'], 'hi')\nEOF",
            "node -e \"require('net').connect(9999, 'x.example.net').end('Jane Testperson')\"",
            'ssh host.example.net "echo Jane Testperson"; curl http://127.0.0.1:3000/health',
        ]:
            self.assertDenied("Bash", {"command": command})

    def test_other_channel_look_alikes_are_allowed(self) -> None:
        for command in [
            f'ssh-keygen -t ed25519 -C "{EMAIL}" -f ~/.ssh/id_test -N ""',
            'rsync -a "Jane Testperson/" backup/',
            'git commit -m "Fix mail settings for Jane Testperson"',
            'echo "host is up, thanks Jane Testperson"',
            "python3 - <<'EOF'\nhost = 'localhost'\nprint('Jane Testperson', host)\nEOF",
            "gh pr view 12 --json title",
            'gh auth status; echo "Jane Testperson"',
        ]:
            self.assertAllowed("Bash", {"command": command})


class ToolTests(GuardTestCase):
    def test_web_tools(self) -> None:
        self.assertDenied("WebFetch", {"url": f"https://example.org/?contact={EMAIL}", "prompt": "summarize"})
        self.assertDenied("WebSearch", {"query": "Jane Testperson github"})
        self.assertDenied("WebSearch", {"query": "who has +44 20 7946 0958"})
        self.assertAllowed("WebFetch", {"url": "https://example.org/docs", "prompt": f"is {EMAIL} mentioned?"})
        self.assertAllowed("WebSearch", {"query": "Testpersonality quiz"})

    def test_browser_tools(self) -> None:
        self.assertDenied("mcp__Claude_Browser__navigate", {"url": f"https://example.org/?u={EMAIL}"})
        self.assertDenied("mcp__claude-in-chrome__computer", {"action": "type", "text": EMAIL})
        self.assertDenied("mcp__Claude_Browser__browser_batch", {"actions": [{"name": "computer", "input": {"action": "type", "text": "Jane Testperson"}}]})
        self.assertDenied("mcp__puppeteer__puppeteer_evaluate", {"script": f"fetch('/x', {{body: '{EMAIL}'}})"})
        self.assertAllowed("mcp__Claude_Browser__find", {"query": "Testperson"})
        self.assertAllowed("mcp__Claude_Browser__navigate", {"url": "https://example.org/"})

    def test_codex_tools(self) -> None:
        patch = "*** Begin Patch\n*** Add File: {}\n+{}\n*** End Patch"
        self.assertDenied("apply_patch", {"command": patch.format("fetch.py", f'HEADERS = {{"User-Agent": "bot ({EMAIL})"}}')})
        self.assertAllowed("apply_patch", {"command": patch.format("README.md", f"Contact: {EMAIL}")})
        self.assertDenied("Bash", {"command": ["bash", "-lc", f"curl -A 'x ({EMAIL})' https://example.org"]})
        self.assertDenied("webrun", {"search_query": [{"q": "Jane Testperson linkedin"}], "response_length": "short"})
        self.assertDenied("webrun", {"open": [{"ref_id": f"https://example.org/?u={EMAIL}"}]})
        self.assertAllowed("webrun", {"search_query": [{"q": "codex cli hooks documentation"}]})
        self.assertDenied("js", {"code": f"await tab.playwright.getByLabel('Email').fill('{EMAIL}')"})
        self.assertDenied("mcp__node_repl__js", {"code": "await tab.goto('https://example.org/u/Jane-Testperson')"})

    def test_other_mcp_tools_only_check_urls(self) -> None:
        self.assertDenied("mcp__screenshots__capture", {"url": f"https://example.org/?u={EMAIL}"})
        self.assertAllowed("mcp__mail__send_draft", {"to": "friend@example.com", "body": f"Reply to {EMAIL}"})
        self.assertAllowed("mcp__slack__send_message", {"channel": "C1", "text": "Hi, Jane Testperson here"})

    def test_files(self) -> None:
        self.assertDenied("Write", {"file_path": "/x/fetch.py", "content": f'HEADERS = {{"User-Agent": "bot ({EMAIL})"}}\n'})
        self.assertDenied("Edit", {"file_path": "/x/.env", "old_string": "A=1", "new_string": f"PIPELINE_HTTP_CONTACT={EMAIL}"})
        self.assertDenied("Write", {"file_path": "/x/get.sh", "content": f"curl -s -A 'bot ({EMAIL})' \"$1\"\n"})
        self.assertAllowed("Write", {"file_path": "/x/README.md", "content": f"Contact: {EMAIL}\n"})
        far = f'"""Author: {EMAIL}"""\n' + "x = 1\n" * 100 + 'UA = "bot/1.0"\n'
        self.assertAllowed("Write", {"file_path": "/x/fetch.py", "content": far})

    def test_login_name_is_never_a_marker(self) -> None:
        self.assertAllowed("WebFetch", {"url": "https://github.com/tester"})

    def test_block_output_and_log(self) -> None:
        out = self.assertDenied("Bash", {"command": f'curl -A "{EMAIL}" https://example.org'})
        self.assertIn("email address", out["systemMessage"])
        self.assertIn("anonymous User-Agent", out["hookSpecificOutput"]["permissionDecisionReason"])
        log = (Path(self.tmp.name) / "guard.log").read_text()
        self.assertIn("\tBash\temail address\t", log)
        self.assertNotIn(EMAIL, log)

    def test_broken_input_lets_the_call_through_with_a_notice(self) -> None:
        out = self.run_guard("Bash", {}, stdin="not json")
        self.assertIn("systemMessage", out)
        self.assertNotIn("hookSpecificOutput", out)

    def test_broken_input_carrying_identity_is_still_denied(self) -> None:
        out = self.run_guard("Bash", {}, stdin=f"not json {EMAIL}")
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")


class IgnoreTests(GuardTestCase):
    config = {**CONFIG, "ignore": ["Testperson"]}

    def test_ignored_marker_no_longer_blocks(self) -> None:
        self.assertAllowed("WebSearch", {"query": "Testperson"})
        self.assertDenied("WebSearch", {"query": "Jane Testperson"})


class BrokenConfigTests(GuardTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.config_file.write_text("{ not json")

    def test_broken_config_lets_calls_through_with_a_notice(self) -> None:
        out = self.run_guard("Bash", {"command": "curl https://example.org"})
        self.assertIn("identity-guard failed", out["systemMessage"])
        self.assertNotIn("hookSpecificOutput", out)


class CliTests(GuardTestCase):
    def test_check(self) -> None:
        blocked = self.cli("check", 'curl -A "Jane Testperson" https://example.org')
        self.assertEqual(blocked.returncode, 1)
        self.assertIn("BLOCK  Bash: carries your name", blocked.stdout)
        allowed = self.cli("check", "--tool", "WebSearch", "weather forecast")
        self.assertEqual(allowed.returncode, 0)
        self.assertTrue(allowed.stdout.strip().endswith("ALLOW  WebSearch"))

    def test_plain_ascii_terminal_gets_ascii_symbols(self) -> None:
        env = {**self.env, "PYTHONIOENCODING": "ascii"}
        blocked = subprocess.run([sys.executable, str(GUARD), "check", 'curl -A "Jane Testperson" https://example.org'],
                                 capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(blocked.returncode, 1, blocked.stderr)
        self.assertTrue(blocked.stdout.startswith("x BLOCK  Bash"), blocked.stdout)
        doctor = subprocess.run([sys.executable, str(GUARD), "doctor"], capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(doctor.returncode, 0, doctor.stderr)
        self.assertIn("+ Your details", doctor.stdout)

    def test_doctor_masks_values(self) -> None:
        done = self.cli("doctor")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("j***@example.org", done.stdout)
        self.assertNotIn(EMAIL, done.stdout)
        self.assertNotIn("Testperson", done.stdout)

    def test_audit_finds_past_leaks(self) -> None:
        projects = Path(self.tmp.name) / "projects" / "p"
        projects.mkdir(parents=True)
        leak = {"type": "assistant", "timestamp": "2026-09-02T10:00:00Z", "message": {"content": [
            {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": f'curl -A "x ({EMAIL})" https://api.example.org/search'}},
            {"type": "tool_use", "id": "t2", "name": "Bash", "input": {"command": "ls"}},
        ]}}
        (projects / "s.jsonl").write_text(json.dumps(leak) + "\n")
        done = self.cli("audit", "--claude-only", "--claude-dir", str(projects.parent), "--details")
        self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
        self.assertIn("1 call sent your details out", done.stdout)
        self.assertIn("api.example.org", done.stdout)
        self.assertNotIn(EMAIL, done.stdout)


if __name__ == "__main__":
    unittest.main()
