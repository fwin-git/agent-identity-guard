#!/usr/bin/env python3
"""Install agent-identity-guard for Claude Code and Codex CLI, or remove it.

    ./setup.sh                                                        guided setup (asks, installs, checks)
    python3 install.py --name "Jane Doe" --email jane@example.com    install without questions, adding markers
    python3 install.py --dry-run                                      show what would change
    python3 install.py --uninstall [--purge]                          remove the hooks [and ~/.identity-guard]

Copies identity_guard.py into the install folder (default ~/.identity-guard), creates config.json there
if it is missing (never overwrites it; --name/--email/--phone/--other add to it), and registers a
PreToolUse hook in ~/.claude/settings.json and ~/.codex/hooks.json, replacing earlier identity-guard
entries and keeping a .bak of each file it changes. Codex then asks you to trust the hook once (/hooks).
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

HERE = Path(__file__).resolve().parent
CLAUDE_MATCHER = "Bash|PowerShell|WebFetch|WebSearch|Write|Edit|MultiEdit|NotebookEdit|mcp__.*"
CODEX_MATCHER = "*"
MARKER_FLAGS = {"name": "names", "email": "emails", "phone": "phones", "other": "other"}
AGENT_NAMES = {"claude": "Claude Code", "codex": "Codex CLI"}


def claude_home() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude").expanduser()


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex").expanduser()


def found_agents() -> list:
    return [agent for agent, home in (("claude", claude_home()), ("codex", codex_home())) if home.exists()]


def pick_python(requested: Optional[str]) -> str:
    """An absolute python3 (3.9+) the agents can start without a shell profile or version manager."""
    candidates = [requested] if requested else ["/usr/bin/python3", shutil.which("python3"), sys.executable]
    for candidate in filter(None, candidates):
        path = os.path.realpath(candidate)
        try:
            version = subprocess.run(
                [path, "-c", "import sys; print(sys.version_info >= (3, 9))"], capture_output=True, text=True, timeout=10
            ).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            continue
        if version == "True":
            return path
    sys.exit("identity-guard needs Python 3.9 or newer; pass one with --python")


def is_ours(entry: dict) -> bool:
    command = str(entry.get("command", ""))
    return "identity_guard.py" in command or "identity-guard.py" in command


def without_ours(groups: list) -> list:
    """PreToolUse groups with every identity-guard hook removed (and groups left empty dropped)."""
    kept = []
    for group in groups:
        hooks = [entry for entry in group.get("hooks") or [] if not is_ours(entry)]
        if hooks:
            kept.append({**group, "hooks": hooks})
        elif not group.get("hooks"):
            kept.append(group)
    return kept


def update_hooks_file(path: Path, entry_group: Optional[dict], dry_run: bool) -> str:
    """Put entry_group into the file's hooks.PreToolUse (None removes ours). Returns what happened."""
    try:
        data = json.loads(path.read_text()) if path.exists() else {}
    except ValueError as error:
        return f"skipped {path}: not valid JSON ({error}); fix it and run again"
    hooks = data.setdefault("hooks", {})
    groups = without_ours(hooks.get("PreToolUse") or [])
    if entry_group:
        groups.append(entry_group)
    if groups:
        hooks["PreToolUse"] = groups
    else:
        hooks.pop("PreToolUse", None)
    if not hooks:
        data.pop("hooks", None)
    new_text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    old_text = path.read_text() if path.exists() else ""
    if new_text == old_text:
        return f"unchanged {path}"
    if dry_run:
        return f"would update {path}"
    if path.exists():
        shutil.copy2(path, path.with_name(path.name + ".bak"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new_text)
    return f"updated {path}" + (f" (backup {path.name}.bak)" if old_text else "")


def read_config(prefix: Path) -> Optional[dict]:
    path = prefix / "config.json"
    return json.loads(path.read_text()) if path.exists() else None


def write_config(prefix: Path, additions: dict, dry_run: bool, auto: Optional[dict] = None) -> str:
    """Create config.json (from the example's comments, without its sample values) or add to it."""
    path = prefix / "config.json"
    config = read_config(prefix)
    created = config is None
    if config is None:
        config = json.loads((HERE / "config.example.json").read_text())
        for kind in MARKER_FLAGS.values():
            config["markers"][kind] = []
    changed = 0
    for kind, values in additions.items():
        current = config.setdefault("markers", {}).setdefault(kind, [])
        for value in values:
            if value not in current:
                current.append(value)
                changed += 1
    auto_markers = config.setdefault("auto_markers", {})
    for key, value in (auto or {}).items():
        if auto_markers.get(key, True) != value:
            auto_markers[key] = value
            changed += 1
    if not created and not changed:
        return f"kept {path}"
    note = f" (+{changed} change(s))" if changed else ""
    if dry_run:
        return f"would {'create' if created else 'update'} {path}{note}"
    prefix.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n")
    os.chmod(path, 0o600)  # it lists personal details
    return f"{'created' if created else 'updated'} {path}{note}"


def install(prefix: Path, agents: list, python: str, additions: dict, dry_run: bool, auto: Optional[dict] = None) -> list:
    """Copy the guard, write the config, register the hooks. Returns one line per step."""
    script = prefix / "identity_guard.py"
    command = f"{shlex.quote(python)} {shlex.quote(str(script))}"
    report = []
    if dry_run:
        report.append(f"would copy identity_guard.py to {script}")
    else:
        prefix.mkdir(parents=True, exist_ok=True)
        shutil.copy2(HERE / "identity_guard.py", script)
        os.chmod(script, 0o755)
        report.append(f"copied identity_guard.py to {script}")
    report.append(write_config(prefix, additions, dry_run, auto))
    if "claude" in agents:
        group = {"matcher": CLAUDE_MATCHER, "hooks": [{"type": "command", "command": command, "timeout": 10}]}
        report.append(update_hooks_file(claude_home() / "settings.json", group, dry_run))
    if "codex" in agents:
        group = {"matcher": CODEX_MATCHER, "hooks": [
            {"type": "command", "command": command, "timeout": 10, "statusMessage": "identity-guard"}]}
        report.append(update_hooks_file(codex_home() / "hooks.json", group, dry_run))
    return report


# --- guided setup -----------------------------------------------------------------------------------


def ask(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except EOFError:
        print()
        raise SystemExit("No answer, so nothing was changed.")


def ask_yes(prompt: str, default: bool = True) -> bool:
    while True:
        answer = ask(f"{prompt} {'[Y/n]' if default else '[y/N]'} ").lower()
        if not answer:
            return default
        if answer in ("y", "yes", "j", "ja"):
            return True
        if answer in ("n", "no", "nein"):
            return False


def ask_many(prompt: str, valid: Callable[[str], Optional[str]]) -> list:
    """Entries one per line until an empty line. valid() returns an error message, or None when fine."""
    print(prompt)
    values: list = []
    while True:
        value = ask("    + ")
        if not value:
            return values
        problem = valid(value)
        if problem:
            print(f"      {problem}; not added.")
        elif value not in values:
            values.append(value)


def git_email() -> str:
    try:
        return subprocess.run(["git", "config", "--global", "user.email"], capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def guided(args: argparse.Namespace) -> int:
    prefix = Path(args.prefix).expanduser().resolve()
    login = (os.environ.get("USER") or getpass.getuser()).strip().lower()
    existing = read_config(prefix) or {}
    have = {kind: list((existing.get("markers") or {}).get(kind) or []) for kind in MARKER_FLAGS.values()}
    auto_now = {"claude_code_account_email": True, "git_email": True, **{
        k: bool(v) for k, v in (existing.get("auto_markers") or {}).items() if not k.startswith("_")}}

    def new(kind: str, value: str) -> Optional[str]:
        if value.lower() == login:
            return f"'{value}' is your login name, which is in every file path, so it can't be a marker"
        if value in have[kind]:
            return "already in your config"
        return None

    def valid_name(value: str) -> Optional[str]:
        return "too short" if len(value) < 2 else new("names", value)

    def valid_email(value: str) -> Optional[str]:
        return "doesn't look like an email address" if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", value) else new("emails", value)

    def valid_phone(value: str) -> Optional[str]:
        return "needs at least 6 digits" if len(re.sub(r"\D", "", value)) < 6 else new("phones", value)

    def valid_other(value: str) -> Optional[str]:
        return "needs at least 4 characters" if len(value) < 4 else new("other", value)

    print("agent-identity-guard: guided setup\n")
    print("This stops Claude Code and Codex from sending your name, email, phone number or other details")
    print(f"to other machines. What you enter stays on this computer, in {prefix / 'config.json'},")
    print("readable only by you. Press Enter to skip a question.\n")

    agents = found_agents()
    if agents:
        print(f"Found: {', '.join(AGENT_NAMES[a] for a in agents)}.")
    elif ask_yes("Found neither Claude Code (~/.claude) nor Codex (~/.codex). Set up for both anyway?", False):
        agents = ["claude", "codex"]
    else:
        print("Nothing to protect yet; install Claude Code or Codex and run ./setup.sh again.")
        return 1
    if any(have.values()):
        counts = ", ".join(f"{len(v)} {k}" for k, v in have.items() if v)
        print(f"Already in your config: {counts}. What you add now comes on top; edit the file to remove entries.")
    print()

    names: list = []
    full = ask("1/5  Your full name as people write it (e.g. Jane Doe): ")
    if full:
        problem = valid_name(full)
        if problem:
            print(f"      {problem}; not added.")
        else:
            names.append(full)
            words = full.split()
            surname = words[-1] if len(words) > 1 else ""
            if len(surname) >= 2 and not new("names", surname) and ask_yes(
                f'      Also block "{surname}" on its own? Say no if it is a common word in your work.'
            ):
                names.append(surname)
    names += [n for n in ask_many("2/5  Other names, nicknames or handles you go by, one per line, empty line when done:", valid_name) if n not in names]

    emails = ask_many("3/5  Your email addresses (private and work), one per line, empty line when done:", valid_email)
    auto = dict(auto_now)
    found_git = git_email()
    if found_git and found_git not in emails and found_git not in have["emails"]:
        auto["git_email"] = ask_yes(f"      Your git email is {found_git}. Treat it as yours too?", auto_now["git_email"])
    if "claude" in agents:
        auto["claude_code_account_email"] = ask_yes(
            "      Treat the email you sign in to Claude Code with as yours too?", auto_now["claude_code_account_email"])

    phones = ask_many("4/5  Phone numbers in any format (e.g. +44 20 7946 0958), one per line, empty line when done:", valid_phone)
    other = ask_many("5/5  Anything else that identifies you (street address, customer or ID numbers), one per line:", valid_other)

    additions = {kind: values for kind, values in
                 (("names", names), ("emails", emails), ("phones", phones), ("other", other)) if values}
    print("\nSummary")
    for kind in ("names", "emails", "phones", "other"):
        values = have[kind] + additions.get(kind, [])
        extra = []
        if kind == "emails":
            if auto["git_email"] and found_git:
                extra.append(f"your git email {found_git}")
            if auto["claude_code_account_email"] and "claude" in agents:
                extra.append("your Claude Code account email")
        shown = ", ".join(values + [f"+ {e}" for e in extra]) or "none"
        print(f"  {kind:<7} {shown}")
    print(f"  install {prefix}, hook for {', '.join(AGENT_NAMES[a] for a in agents)}")
    if not any(have.values()) and not additions:
        print("\nWithout any details the guard only catches your git or Claude Code email.")
    if not ask_yes("\nInstall now?"):
        print("Nothing was changed.")
        return 1

    python = pick_python(args.python)
    print()
    print("\n".join(install(prefix, agents, python, additions, False, auto)))
    script = prefix / "identity_guard.py"
    run = f"{shlex.quote(python)} {shlex.quote(str(script))}"
    print("\nChecking the setup" + (" (asks Codex for the hook's status)" if "codex" in agents else "") + "...\n", flush=True)
    subprocess.run([python, str(script), "doctor"])

    print("\nNext")
    if "codex" in agents:
        print("  - Codex runs a new hook only once you approve it: start `codex`, type /hooks, trust identity-guard.")
    example = (emails or have["emails"] or ["jane.doe@example.com"])[0]
    print(f"  - Try it: {run} check 'curl -A \"bot ({example})\" https://example.org'")
    print(f"  - Change your details any time in {prefix / 'config.json'}, or run ./setup.sh again.")
    if ask_yes("\nScan your past Claude Code and Codex sessions for details that already went out? "
               "It reads only local transcripts and can take a minute.", False):
        print(flush=True)
        subprocess.run([python, str(script), "audit"])
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--guided", action="store_true", help="ask for your details step by step (what ./setup.sh runs)")
    parser.add_argument("--prefix", default="~/.identity-guard", help="install folder (default ~/.identity-guard)")
    parser.add_argument("--agents", default="auto", help="claude, codex, both or auto (whichever is installed)")
    parser.add_argument("--python", help="python3 the hook runs with (default /usr/bin/python3 when it is 3.9+)")
    for flag, kind in MARKER_FLAGS.items():
        parser.add_argument(f"--{flag}", action="append", default=[], metavar="VALUE", help=f"add to markers.{kind} (repeatable)")
    parser.add_argument("--dry-run", action="store_true", help="show what would change, change nothing")
    parser.add_argument("--uninstall", action="store_true", help="remove the hooks from Claude Code and Codex")
    parser.add_argument("--purge", action="store_true", help="with --uninstall: also delete the install folder (config and log)")
    args = parser.parse_args()
    if args.guided:
        try:
            return guided(args)
        except KeyboardInterrupt:
            print("\nStopped; nothing more was changed.")
            return 130

    prefix = Path(args.prefix).expanduser().resolve()
    if args.agents == "auto":
        agents = found_agents()
    else:
        agents = ["claude", "codex"] if args.agents == "both" else [a.strip() for a in args.agents.split(",")]
    if not agents:
        sys.exit("Found neither ~/.claude nor ~/.codex; pass --agents claude,codex to install anyway.")

    if args.uninstall:
        report = []
        if "claude" in agents:
            report.append(update_hooks_file(claude_home() / "settings.json", None, args.dry_run))
        if "codex" in agents:
            report.append(update_hooks_file(codex_home() / "hooks.json", None, args.dry_run))
        if args.purge and prefix.exists():
            report.append(f"would delete {prefix}" if args.dry_run else f"deleted {prefix}")
            if not args.dry_run:
                shutil.rmtree(prefix)
        print("\n".join(report))
        return 0

    python = pick_python(args.python)
    additions = {MARKER_FLAGS[flag]: getattr(args, flag) for flag in MARKER_FLAGS if getattr(args, flag)}
    print("\n".join(install(prefix, agents, python, additions, args.dry_run)))
    script = prefix / "identity_guard.py"
    print(f"\nNext:\n  1. List what identifies you in {prefix / 'config.json'} (names, emails, phones, other).")
    if "codex" in agents:
        print("  2. Codex runs new hooks only once you trust them: start `codex`, type /hooks, trust identity-guard.")
    print(f"  3. Check the setup: {shlex.quote(python)} {shlex.quote(str(script))} doctor")
    return 0


if __name__ == "__main__":
    sys.exit(main())
