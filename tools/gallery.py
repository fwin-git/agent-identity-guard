"""Render every agent-identity-guard CLI state to one HTML page, and refresh the samples in the docs.

    python3 tools/gallery.py                 writes build/gallery/gallery.html
    python3 tools/gallery.py --update-docs   also rewrites each sample under a <!-- sample: … --> marker
                                             in README.md and docs/*.md with the fresh output

Each scenario runs for real in its own throwaway home (with .claude / .codex as needed), in a pseudo-
terminal so the colors are what a terminal shows. A stand-in `codex` on PATH answers the hook-trust
question with the state a scenario needs; your real agents and config are never touched.
Identity used everywhere: Jane Doe, jane.doe@example.com, +44 20 7946 0958, git email jane@work.example.
macOS and Linux only (it needs pty).
"""
from __future__ import annotations

import html
import json
import os
import pty
import re
import select
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "build" / "gallery"
WORK = OUT / "homes"
COLUMNS = "92"
EMAIL = "jane.doe@example.com"

FAKE_CODEX = r'''#!/usr/bin/python3
import json, os, sys
if sys.argv[1:2] == ["app-server"]:
    status = os.environ.get("FAKE_CODEX_TRUST", "untrusted")
    home = os.environ["HOME"]
    for line in sys.stdin:
        message = json.loads(line)
        if message.get("id") == 1:
            print(json.dumps({"id": 1, "result": {}}), flush=True)
        elif message.get("id") == 2:
            hooks = [{"key": f"{home}/.codex/hooks.json:{name}:0:0", "eventName": event, "trustStatus": status}
                     for name, event in (("pre_tool_use", "preToolUse"), ("session_start", "sessionStart"))]
            print(json.dumps({"id": 2, "result": {"data": [{"cwd": home, "hooks": hooks, "warnings": [], "errors": []}]}}), flush=True)
'''


# --- sandboxes --------------------------------------------------------------------------------------


def sandbox(name: str, claude: bool = True, codex: bool = True, codex_trust: str = "untrusted", sessions: str = "") -> Path:
    home = WORK / name
    shutil.rmtree(home, ignore_errors=True)
    (home / "bin").mkdir(parents=True)
    (home / "gitconfig").write_text("[user]\n\temail = jane@work.example\n")
    if claude:
        (home / ".claude").mkdir()
    if codex:
        (home / ".codex").mkdir()
        stub = home / "bin" / "codex"
        stub.write_text(FAKE_CODEX)
        stub.chmod(0o755)
    (home / "trust").write_text(codex_trust)
    if sessions:
        write_sessions(home, sessions)
    return home


def write_sessions(home: Path, kind: str) -> None:
    """Past transcripts: 'leaks' (some sent, some blocked), 'blocked' (only blocked tries), 'clean'."""
    def claude_session(name: str, calls: list, blocked_ids: tuple = ()) -> None:
        path = home / ".claude" / "projects" / "-home-jane-project" / f"{name}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = []
        for i, (stamp, command) in enumerate(calls):
            lines.append({"type": "assistant", "timestamp": stamp, "message": {"content": [
                {"type": "tool_use", "id": f"{name}-{i}", "name": "Bash", "input": {"command": command}}]}})
            if f"{name}-{i}" in blocked_ids:
                lines.append({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": f"{name}-{i}",
                              "content": "PreToolUse:Bash hook error: identity-guard blocked this Bash call: ..."}]}})
        path.write_text("".join(json.dumps(line) + "\n" for line in lines))

    harmless = [("2026-09-01T09:00:00Z", "ls -la"), ("2026-09-01T09:01:00Z", "git status")]
    if kind == "clean":
        claude_session("s1", harmless)
        return
    leak = f'curl -s -A "research-bot/1.0 (contact: {EMAIL})" https://api.example.org/search?q=otters'
    if kind == "leaks":
        claude_session("s1", harmless + [("2026-09-02T10:%02d:00Z" % m, leak) for m in range(9)])
        claude_session("s2", [("2026-09-14T16:20:00Z", f'DATA_CONTACT="{EMAIL}" ./crawl.sh'),
                              ("2026-09-14T16:22:00Z", 'gh issue create --title "Crash" --body "Reported by Jane Doe"'),
                              ("2026-10-21T08:00:00Z", f'curl "https://docs.example.net/feedback?from={EMAIL}"')])
        claude_session("s3", [("2026-10-24T11:00:00Z", leak), ("2026-10-24T11:01:00Z", leak)], ("s3-0", "s3-1"))
        codex = home / ".codex" / "sessions" / "2026" / "10" / "01" / "rollout.jsonl"
        if (home / ".codex").exists():
            codex.parent.mkdir(parents=True, exist_ok=True)
            codex.write_text(json.dumps({"timestamp": "2026-10-01T12:00:00Z", "payload": {
                "type": "function_call", "name": "exec_command", "call_id": "c1",
                "arguments": json.dumps({"cmd": "ssh build.example.net 'echo deployed by Jane Doe'"})}}) + "\n")
    if kind == "blocked":
        claude_session("s1", harmless + [("2026-10-24T11:00:00Z", leak), ("2026-10-24T11:05:00Z", leak)], ("s1-2", "s1-3"))


def env_for(home: Path, **extra: str) -> dict:
    env = {key: value for key, value in os.environ.items()
           if key not in ("CLAUDE_CODE_USER_EMAIL", "CLAUDE_CONFIG_DIR", "CODEX_HOME", "NO_COLOR", "IDENTITY_GUARD_CONFIG")}
    env.update(HOME=str(home), USERPROFILE=str(home), USER="jane", GIT_CONFIG_GLOBAL=str(home / "gitconfig"), TERM="xterm-256color",
               COLUMNS=COLUMNS, PATH=f"{home / 'bin'}:/usr/bin:/bin", FAKE_CODEX_TRUST=(home / "trust").read_text())
    env.update(extra)
    return env


def quiet_install(home: Path, *flags: str) -> None:
    subprocess.run(["/usr/bin/python3", str(REPO / "install.py"), *flags], env=env_for(home), cwd=REPO,
                   capture_output=True, text=True, check=True)


def demo_install(home: Path) -> None:
    quiet_install(home, "--name", "Jane Doe", "--name", "Doe", "--email", EMAIL, "--phone", "+44 20 7946 0958")


def record_trust(home: Path) -> None:
    (home / ".codex" / "config.toml").write_text("".join(
        f'[hooks.state."{home}/.codex/hooks.json:{name}:0:0"]\ntrusted_hash = "sha256:demo"\n\n'
        for name in ("pre_tool_use", "session_start")))


# --- running ----------------------------------------------------------------------------------------

PROMPT_END = re.compile(r"(›|\+|>) $")


def run(home: Path, argv: list, answers: list = None, env: dict = None, timeout: float = 60) -> str:
    """Run argv in a pseudo-terminal, typing each answer when a prompt (› or +) is waiting. Returns the screen text."""
    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(REPO)
        os.execve(argv[0], argv, env or env_for(home))
    output, pending, deadline = b"", list(answers or []), time.time() + timeout
    while time.time() < deadline:
        ready, _, _ = select.select([fd], [], [], 0.15)
        if ready:
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                break
            if not chunk:
                break
            output += chunk
            continue
        visible = re.sub(r"\x1b\[[\d;]*[A-Za-z]", "", output.decode(errors="replace")).rstrip("\n").split("\n")[-1]
        if pending and PROMPT_END.search(visible.replace("\r", "")):
            answer = pending.pop(0)
            os.write(fd, answer.encode() if answer in ("\x03", "\x04") else (answer + "\n").encode())
    os.waitpid(pid, 0)
    text = output.decode(errors="replace").replace("\r\n", "\n")
    text = "\n".join(line.split("\r")[-1] for line in text.split("\n"))  # what a terminal shows after \r redraws
    return text.replace(str(home), "~").replace(str(REPO), "~/agent-identity-guard")


def guard(home: Path, *args: str, env: dict = None) -> str:
    return run(home, ["/usr/bin/python3", str(home / ".identity-guard" / "identity_guard.py"), *args], env=env)


def hook(home: Path, tool: str, tool_input: dict, raw: str = None) -> str:
    event = raw if raw is not None else json.dumps({"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input,
                                                     "session_id": "3f2a9c1e-demo", "cwd": "/home/jane/project"})
    done = subprocess.run(["/usr/bin/python3", str(home / ".identity-guard" / "identity_guard.py")], input=event,
                          capture_output=True, text=True, env=env_for(home, TERM="dumb"))
    return json.dumps(json.loads(done.stdout), indent=2, ensure_ascii=False) if done.stdout.strip() else "(no output: the call goes ahead)"


SETUP = [str(REPO / "setup.sh")]
INSTALL = ["/usr/bin/python3", str(REPO / "install.py")]
FULL_ANSWERS = ["Jane Doe", "", "jdoe42", "", EMAIL, "", "", "", "+44 20 7946 0958", "", "", ""]


# --- scenarios --------------------------------------------------------------------------------------


def scenarios() -> list:
    """(section, title, when you see it, command shown, output, kind)"""
    out = []

    def add(section: str, title: str, when: str, command: str, text: str, kind: str = "term") -> None:
        out.append((section, title, when, command, text, kind))
        print(f"  {section} / {title}", flush=True)

    # setup
    h = sandbox("setup-full", sessions="leaks")
    add("Guided setup", "First run, Codex still to approve",
        "Both agents installed. You answer the questions, the audit finds earlier leaks, and Codex still needs the hook approved.",
        "./setup.sh", run(h, SETUP, FULL_ANSWERS + ["", ""]))

    h = sandbox("setup-claude-only", codex=False, sessions="clean")
    add("Guided setup", "First run, Claude Code only, nothing leaked",
        "Only Claude Code is installed, so there is no Codex step, and the audit finds nothing.",
        "./setup.sh", run(h, SETUP, ["Jane Doe", "", "", EMAIL, "", "", "", "", "", "", "", ""]))

    h = sandbox("setup-approved", sessions="clean", codex_trust="trusted")
    record_trust(h)
    add("Guided setup", "Codex already approved",
        "Running setup again after you approved the hook in Codex: no extra step, everything is guarded.",
        "./setup.sh", run(h, SETUP, ["Jane Doe", "", "", EMAIL, "", "", "", "", "", "", "", "n"]))

    h = sandbox("setup-rerun", codex=False, sessions="clean")
    demo_install(h)
    add("Guided setup", "Running it again",
        "Your config already has details. New answers are added on top; the questions about the same details are skipped.",
        "./setup.sh", run(h, SETUP, ["", "", "jane@second.example", "", "", "", "", "", "", "n"]))

    h = sandbox("setup-refusals", codex=False)
    add("Guided setup", "Entries it refuses",
        "Your login name (it is in every path), an email without a domain, a too-short phone number, a too-short detail.",
        "./setup.sh", run(h, SETUP, ["J", "jane", "jd", "", "jane@", EMAIL, "", "", "", "12 34", "", "abc", "", "n"]))

    h = sandbox("setup-declined", codex=False)
    add("Guided setup", "Saying no at the end", "You answer everything but decline to install: nothing is changed.",
        "./setup.sh", run(h, SETUP, ["Jane Doe", "", "", "", "", "", "", "", "n"]))

    h = sandbox("setup-nothing", codex=False)
    add("Guided setup", "Installing without any details",
        "You skip every question: the summary warns that only your git or Claude Code email will be caught.",
        "./setup.sh", run(h, SETUP, ["", "", "", "", "", "", "", "n"]))

    h = sandbox("setup-no-agents", claude=False, codex=False)
    add("Guided setup", "Neither agent installed", "Neither ~/.claude nor ~/.codex exists and you decline to set up anyway.",
        "./setup.sh", run(h, SETUP, ["n"]))

    h = sandbox("setup-eof", codex=False)
    add("Guided setup", "Input ends early (Ctrl-D)", "The answers run out before the end: nothing is changed.",
        "./setup.sh", run(h, SETUP, ["Jane Doe", "\x04"]))

    h = sandbox("setup-ctrl-c", codex=False)
    add("Guided setup", "Stopped with Ctrl-C", "You interrupt the setup.", "./setup.sh", run(h, SETUP, ["\x03"]))

    h = sandbox("setup-ascii", codex=False, sessions="clean")
    add("Guided setup", "Terminal without Unicode",
        "The terminal can't show Unicode (here PYTHONIOENCODING=ascii): ASCII symbols and frames instead.",
        "./setup.sh", run(h, SETUP, ["Jane Doe", "", "", EMAIL, "", "", "", "", "", "", "", "n"],
                          env=env_for(h, PYTHONIOENCODING="ascii")))

    # doctor
    for trust, title, when in [
        ("trusted", "All set", "Both agents protected, Codex approved."),
        ("untrusted", "Codex waiting for approval", "Installed, but not yet approved in Codex's /hooks."),
        ("modified", "Codex hook changed since approval", "hooks.json changed after you approved it, so Codex skips the hook."),
        ("managed", "Codex approved by policy", "An administrator's managed config trusts the hook."),
    ]:
        h = sandbox(f"doctor-{trust}", codex_trust=trust)
        demo_install(h)
        add("doctor", title, when, "identity_guard.py doctor", guard(h, "doctor"))

    h = sandbox("doctor-no-codex-answer", codex_trust="trusted")
    demo_install(h)
    record_trust(h)
    (h / "bin" / "codex").unlink()
    add("doctor", "Codex can't be asked", "`codex` isn't on PATH, but Codex's config records your approval.",
        "identity_guard.py doctor", guard(h, "doctor"))

    h = sandbox("doctor-claude-only", codex=False)
    demo_install(h)
    add("doctor", "Only Claude Code installed", "Codex isn't installed on this computer.", "identity_guard.py doctor", guard(h, "doctor"))

    h = sandbox("doctor-unprotected")
    demo_install(h)
    (h / ".claude" / "settings.json").write_text("{}\n")
    (h / ".codex" / "hooks.json").write_text("{}\n")
    add("doctor", "Agents installed but not protected", "The hook entries were removed from the agents' settings.",
        "identity_guard.py doctor", guard(h, "doctor"))

    h = sandbox("doctor-no-details", codex=False)
    quiet_install(h)
    cfg = json.loads((h / ".identity-guard" / "config.json").read_text())
    cfg["auto_markers"] = {"claude_code_account_email": False, "git_email": False}
    (h / ".identity-guard" / "config.json").write_text(json.dumps(cfg))
    add("doctor", "No details listed", "The config lists nothing and the automatic emails are off.", "identity_guard.py doctor",
        guard(h, "doctor"))

    h = sandbox("doctor-missing", codex=False)
    demo_install(h)
    (h / ".identity-guard" / "config.json").unlink()
    add("doctor", "Config missing", "config.json was deleted; only the automatic emails are left.", "identity_guard.py doctor",
        guard(h, "doctor"))

    h = sandbox("doctor-broken", codex=False)
    demo_install(h)
    (h / ".identity-guard" / "config.json").write_text('{"markers": {"emails": ["jane.doe@example.com",]}')
    add("doctor", "Config broken", "config.json isn't valid JSON.", "identity_guard.py doctor", guard(h, "doctor"))

    h = sandbox("doctor-ascii", codex_trust="untrusted")
    demo_install(h)
    add("doctor", "Terminal without Unicode", "ASCII symbols instead of ✔ ▲ ✖.", "identity_guard.py doctor",
        guard(h, "doctor", env=env_for(h, PYTHONIOENCODING="ascii")))

    h = sandbox("doctor-nocolor", codex_trust="untrusted")
    demo_install(h)
    add("doctor", "NO_COLOR set", "Same layout, no colors.", "NO_COLOR=1 identity_guard.py doctor",
        guard(h, "doctor", env=env_for(h, NO_COLOR="1")))

    # check
    h = sandbox("check", codex=False)
    demo_install(h)
    checks = [
        ("Bash", f'curl -A "research-bot/1.0 (contact: {EMAIL})" https://api.example.org/search'),
        ("Bash", "curl -A research-bot/1.0 https://api.example.org/search"),
        ("Bash", 'gh issue create --title "Crash" --body "Reported by Jane Doe"'),
        ("Bash", "dig jane-doe.collector.example.net"),
        ("Bash", 'ssh build.example.net "echo deployed by Jane Doe"'),
        ("Bash", 'curl -d "phone=0044 20 7946-0958" https://forms.example.com'),
        ("Bash", 'curl -A "bot ($(git config user.email))" https://api.example.org'),
        ("Bash", f"curl -d email={EMAIL} http://localhost:3000/signup"),
        ("Bash", f'ssh-keygen -t ed25519 -C "{EMAIL}"'),
        ("Bash", 'git commit -m "Fix mail settings for Jane Doe"'),
        ("WebSearch", "Jane Doe home address"),
        ("WebSearch", "weather forecast"),
        ("WebFetch", f"https://forms.example.com/?contact={EMAIL}"),
        ("Write", f'HEADERS = {{"User-Agent": "scraper ({EMAIL})"}}'),
        ("Write", f"# Maintainer: Jane Doe <{EMAIL}>"),
        ("apply_patch", f"*** Begin Patch\n*** Add File: .env\n+CRAWLER_CONTACT={EMAIL}\n*** End Patch"),
        ("webrun", "Jane Doe linkedin"),
        ("mcp__Claude_Browser__computer", json.dumps({"action": "type", "text": EMAIL})),
        ("mcp__fetch__fetch", json.dumps({"url": "https://api.example.org/search", "headers": {"User-Agent": f"bot ({EMAIL})"}})),
        ("mcp__http__request", json.dumps({"method": "POST", "url": "https://forms.example.com/signup", "body": f"email={EMAIL}"})),
        ("mcp__slack__send_message", json.dumps({"channel": "C1", "text": "Hi, Jane Doe here"})),
    ]
    lines = []
    for tool, text in checks:
        shown = text.replace("\n", "\\n")
        result = run(h, ["/usr/bin/python3", str(h / ".identity-guard" / "identity_guard.py"), "check", "--tool", tool, text])
        lines.append(f"\x1b[90m$ identity_guard.py check{'' if tool == 'Bash' else ' --tool ' + tool} {shlex.quote(shown)}\x1b[0m\n{result.strip()}")
    add("check", "Every kind of call", "Try a command or tool input against your config, the way the hook would judge it. "
        "Exit code 1 for BLOCK, 0 for ALLOW.", "", "\n\n".join(lines))
    add("check", "Terminal without Unicode", "ASCII symbols.", "identity_guard.py check 'dig jane-doe.collector.example.net'",
        guard(h, "check", "dig jane-doe.collector.example.net", env=env_for(h, PYTHONIOENCODING="ascii")))

    # audit
    h = sandbox("audit-leaks", sessions="leaks")
    demo_install(h)
    add("audit", "Earlier leaks found", "Past sessions sent your details; some later tries were already blocked.",
        "identity_guard.py audit", guard(h, "audit"))
    add("audit", "Each call (--details)", "The same audit, one line per call with its transcript.",
        "identity_guard.py audit --details", guard(h, "audit", "--details"))
    h = sandbox("audit-blocked", codex=False, sessions="blocked")
    demo_install(h)
    add("audit", "Only blocked tries", "Agents tried, but the guard blocked every one.", "identity_guard.py audit", guard(h, "audit"))
    h = sandbox("audit-clean", codex=False, sessions="clean")
    demo_install(h)
    add("audit", "Nothing found", "No past call carried your details.", "identity_guard.py audit", guard(h, "audit"))
    h = sandbox("audit-no-details", codex=False, sessions="clean")
    quiet_install(h)
    cfg = json.loads((h / ".identity-guard" / "config.json").read_text())
    cfg["auto_markers"] = {"claude_code_account_email": False, "git_email": False}
    (h / ".identity-guard" / "config.json").write_text(json.dumps(cfg))
    add("audit", "No details listed", "There is nothing to look for yet.", "identity_guard.py audit", guard(h, "audit"))

    # install.py with flags
    h = sandbox("flags")
    (h / ".claude" / "settings.json").write_text('{"model": "opus"}\n')
    add("install.py (no questions)", "Install with flags", "For scripts and dotfiles: details as flags, no questions.",
        'python3 install.py --name "Jane Doe" --email jane.doe@example.com',
        run(h, INSTALL + ["--name", "Jane Doe", "--email", EMAIL]))
    add("install.py (no questions)", "Running it again", "Nothing new to add or register.",
        'python3 install.py --name "Jane Doe"', run(h, INSTALL + ["--name", "Jane Doe"]))
    h2 = sandbox("flags-dry")
    add("install.py (no questions)", "Dry run", "Shows what would change and changes nothing.",
        "python3 install.py --dry-run --name \"Jane Doe\"", run(h2, INSTALL + ["--dry-run", "--name", "Jane Doe"]))
    h3 = sandbox("flags-broken")
    (h3 / ".claude" / "settings.json").write_text('{"model": "opus",}\n')
    add("install.py (no questions)", "Agent settings file broken", "~/.claude/settings.json isn't valid JSON, so it is left alone.",
        "python3 install.py --name \"Jane Doe\"", run(h3, INSTALL + ["--name", "Jane Doe"]))
    h4 = sandbox("flags-none", claude=False, codex=False)
    add("install.py (no questions)", "Neither agent installed", "Nothing to register with.", "python3 install.py",
        run(h4, INSTALL))
    add("install.py (no questions)", "Uninstall", "Removes the hooks; other hooks in the settings stay.",
        "python3 install.py --uninstall", run(h, INSTALL + ["--uninstall"]))
    demo_install(h)
    add("install.py (no questions)", "Uninstall and purge", "Also deletes ~/.identity-guard with your config and log.",
        "python3 install.py --uninstall --purge", run(h, INSTALL + ["--uninstall", "--purge"]))

    # hook
    h = sandbox("hook", codex=False)
    demo_install(h)
    command = f'curl -A "research-bot/1.0 (contact: {EMAIL})" https://api.example.org/search'
    decision = hook(h, "Bash", {"command": command})
    reason = json.loads(decision)["hookSpecificOutput"]["permissionDecisionReason"]
    notice = json.loads(decision)["systemMessage"]
    add("Hook (during agent work)", "What the agent sees in Claude Code", "The tool call is refused; this becomes the tool's error.",
        "", f"PreToolUse:Bash hook error: {reason}", "plain")
    add("Hook (during agent work)", "What the agent sees in Codex", "Codex shows the same reason after its own prefix.",
        "", f"Command blocked by PreToolUse hook: {reason}. Command: {command}", "plain")
    add("Hook (during agent work)", "What you see", "One line in the app.", "", notice, "plain")
    log = (h / ".identity-guard" / "guard.log").read_text().strip().replace(str(h), "~")
    add("Hook (during agent work)", "The block log", "~/.identity-guard/guard.log: time, agent, session, tool, kind, folder; "
        "never the content.", "", log, "plain")
    add("Hook (during agent work)", "Raw hook output (blocked)", "What the hook prints for the agent to read.",
        "echo '{…curl with your email…}' | identity_guard.py", decision, "plain")
    add("Hook (during agent work)", "Raw hook output (allowed)", "Nothing at all: the call goes ahead.",
        "echo '{…ls -la…}' | identity_guard.py", hook(h, "Bash", {"command": "ls -la"}), "plain")
    (h / ".identity-guard" / "config.json").write_text("{ broken")
    add("Hook (during agent work)", "Config broken: call let through", "A broken config never freezes the agent; you see this on each call.",
        "", hook(h, "Bash", {"command": "ls -la"}), "plain")
    add("Hook (during agent work)", "Guard failed, identity still caught", "Even when the event can't be parsed, a call containing your "
        "automatic email (here the git email) is refused.", "", hook(h, "", {}, raw="not json jane@work.example"), "plain")
    return out


# --- page -------------------------------------------------------------------------------------------

COLORS = {"1": "font-weight:700", "2": "opacity:.62", "31": "color:var(--red)", "32": "color:var(--green)",
          "33": "color:var(--yellow)", "36": "color:var(--cyan)", "90": "color:var(--gray)"}


def to_html(text: str) -> str:
    text = re.sub(r"\x1b\[(?:2K|\?[\d;]*[hl])", "", text)
    escaped = html.escape(text)
    depth = 0

    def span(match: re.Match) -> str:
        nonlocal depth
        codes = match.group(1).split(";")
        if codes == ["0"]:
            closing, depth = "</span>" * depth, 0
            return closing
        depth += 1
        return '<span style="' + ";".join(COLORS.get(c, "") for c in codes) + '">'

    body = re.sub(r"\x1b\[([\d;]+)m", span, escaped)
    return body + "</span>" * depth


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def page(items: list) -> str:
    sections: dict = {}
    for item in items:
        sections.setdefault(item[0], []).append(item)
    nav = "".join(f'<li><a href="#{slug(s)}">{html.escape(s)}</a><span>{len(v)}</span></li>' for s, v in sections.items())
    cards = []
    for section, entries in sections.items():
        cards.append(f'<h2 id="{slug(section)}">{html.escape(section)}</h2>')
        for _, title, when, command, text, kind in entries:
            cmd = f'<div class="cmd">$ {html.escape(command)}</div>' if command else ""
            body = to_html(text.rstrip("\n")) if kind == "term" else html.escape(text)
            cards.append(f'<section class="card"><h3>{html.escape(title)}</h3><p>{html.escape(when)}</p>{cmd}'
                         f'<pre class="{kind}">{body}</pre></section>')
    return f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>agent-identity-guard: every output</title>
<style>
:root{{--bg:#111318;--panel:#1a1d24;--term:#0d0f13;--text:#d7dce5;--muted:#8b93a3;--line:#262a33;
--red:#ff7b85;--green:#7ee08f;--yellow:#ffd36e;--cyan:#68d5f0;--gray:#6b7383}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 -apple-system,BlinkMacSystemFont,sans-serif}}
header{{padding:28px 32px 8px}}h1{{margin:0;font-size:22px}}header p{{color:var(--muted);margin:6px 0 0;max-width:860px}}
.legend{{display:flex;gap:18px;flex-wrap:wrap;margin:14px 0 0;font:13px Menlo,monospace;color:var(--muted)}}
.legend b{{font-weight:700}}
.wrap{{display:grid;grid-template-columns:220px 1fr;gap:28px;padding:16px 32px 60px}}
nav{{position:sticky;top:16px;align-self:start}}nav ul{{list-style:none;margin:0;padding:0}}
nav li{{display:flex;justify-content:space-between;padding:6px 10px;border-radius:7px}}nav li:hover{{background:var(--panel)}}
nav a{{color:var(--text);text-decoration:none}}nav span{{color:var(--muted);font-size:12px}}
h2{{font-size:17px;margin:34px 0 12px;padding-top:8px;border-top:1px solid var(--line)}}h2:first-child{{margin-top:0;border:0}}
.card{{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin:0 0 16px}}
.card h3{{margin:0;font-size:15px}}.card p{{margin:4px 0 12px;color:var(--muted)}}
.cmd{{font:12.5px Menlo,monospace;color:var(--muted);margin:0 0 8px}}
pre{{margin:0;background:var(--term);border-radius:9px;padding:14px 16px;font:12.5px/1.5 Menlo,Monaco,monospace;overflow-x:auto;white-space:pre}}
pre.plain{{white-space:pre-wrap;color:#c8ceda}}
@media (max-width:820px){{.wrap{{grid-template-columns:1fr;padding:12px 16px}}nav{{position:static}}header{{padding:20px 16px 0}}}}
</style>
<header><h1>agent-identity-guard: every output</h1>
<p>Each block below is a real run in a throwaway home with a made-up identity (Jane Doe, jane.doe@example.com,
+44 20 7946 0958, git email jane@work.example), captured in a pseudo-terminal so the colors are what a terminal shows.
Codex's approval states come from a stand-in <code>codex</code> that answers with the state each scenario needs.</p>
<div class="legend"><span><b style="color:var(--green)">✔</b> fine</span><span><b style="color:var(--yellow)">▲</b> needs you</span>
<span><b style="color:var(--red)">✖</b> blocked / broken</span><span><b style="color:var(--gray)">●</b> info</span>
<span><b style="color:var(--cyan)">◆</b> question</span><span><b style="color:var(--green)">◇</b> step done</span></div></header>
<div class="wrap"><nav><ul>{nav}</ul></nav><main>{''.join(cards)}</main></div></html>"""


def update_docs(items: list) -> int:
    """Replace the code block after each <!-- sample: Section/Title --> marker with that scenario's fresh output."""
    samples = {f"{i[0]}/{i[1]}": "\n".join(line.rstrip() for line in re.sub(r"\x1b\[[\d;]*[A-Za-z]", "", i[4]).strip("\n").splitlines())
               for i in items}
    changed = 0
    for path in [REPO / "README.md", *sorted((REPO / "docs").glob("*.md"))]:
        lines, out, i = path.read_text().split("\n"), [], 0
        while i < len(lines):
            marker = re.match(r"^([ \t]*)<!-- sample: (.+?) -->$", lines[i])
            out.append(lines[i])
            i += 1
            if not marker:
                continue
            indent, key = marker.group(1), marker.group(2)
            if key not in samples:
                sys.exit(f"{path.name}: no scenario called {key!r}")
            start = i
            end = next(j for j in range(start + 1, len(lines)) if lines[j].strip() == "```")
            out += [indent + "```", *[(indent + line) if line else "" for line in samples[key].split("\n")], indent + "```"]
            changed += 1
            i = end + 1
        path.write_text("\n".join(out))
    return changed


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    items = scenarios()
    (OUT / "gallery.html").write_text(page(items))
    print(f"{len(items)} scenarios -> {OUT / 'gallery.html'}")
    if "--update-docs" in sys.argv:
        print(f"refreshed {update_docs(items)} sample(s) in README.md and docs/")
