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
from typing import Callable, Optional, Tuple

import identity_guard as ig

HERE = Path(__file__).resolve().parent
CLAUDE_MATCHER = "Bash|PowerShell|WebFetch|WebSearch|Write|Edit|MultiEdit|NotebookEdit|mcp__.*"
CODEX_MATCHER = "*"
MARKER_FLAGS = {"name": "names", "email": "emails", "phone": "phones", "other": "other"}
AGENT_NAMES = {"claude": "Claude Code", "codex": "Codex CLI"}


def found_agents() -> list:
    return [agent for agent, home in (("claude", ig.claude_home()), ("codex", ig.codex_home())) if home.exists()]


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


def update_hooks_file(path: Path, entry_group: Optional[dict], dry_run: bool) -> Tuple[str, str]:
    """Put entry_group into the file's hooks.PreToolUse (None removes ours). Returns (tone, what happened)."""
    try:
        data = json.loads(path.read_text()) if path.exists() else {}
    except ValueError as error:
        return "fail", f"skipped {ig.tilde(path)}: not valid JSON ({error}); fix it and run again"
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
        return "ok", f"unchanged {ig.tilde(path)}"
    if dry_run:
        return "info", f"would update {ig.tilde(path)}"
    if path.exists():
        shutil.copy2(path, path.with_name(path.name + ".bak"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new_text)
    return "ok", f"updated {ig.tilde(path)}" + (f" (backup {path.name}.bak)" if old_text else "")


def read_config(prefix: Path) -> Optional[dict]:
    path = prefix / "config.json"
    return json.loads(path.read_text()) if path.exists() else None


def write_config(prefix: Path, additions: dict, dry_run: bool, auto: Optional[dict] = None) -> Tuple[str, str]:
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
        return "ok", f"kept {ig.tilde(path)} (no changes)"
    note = f" ({ig.plural(changed, 'change')})" if changed else ""
    if dry_run:
        return "info", f"would {'create' if created else 'update'} {ig.tilde(path)}{note}"
    prefix.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n")
    os.chmod(path, 0o600)  # it lists personal details
    return "ok", f"{'created' if created else 'updated'} {ig.tilde(path)}{note}"


def install(prefix: Path, agents: list, python: str, additions: dict, dry_run: bool, auto: Optional[dict] = None) -> list:
    """Copy the guard, write the config, register the hooks. Returns (tone, label, what happened) per part."""
    script = prefix / "identity_guard.py"
    command = f"{shlex.quote(python)} {shlex.quote(str(script))}"
    if dry_run:
        steps = [("info", "Guard", f"would copy to {ig.tilde(script)}")]
    else:
        prefix.mkdir(parents=True, exist_ok=True)
        shutil.copy2(HERE / "identity_guard.py", script)
        os.chmod(script, 0o755)
        steps = [("ok", "Guard", f"copied to {ig.tilde(script)}")]
    tone, text = write_config(prefix, additions, dry_run, auto)
    steps.append((tone, "Config", text))
    if "claude" in agents:
        group = {"matcher": CLAUDE_MATCHER, "hooks": [{"type": "command", "command": command, "timeout": 10}]}
        tone, text = update_hooks_file(ig.claude_home() / "settings.json", group, dry_run)
        steps.append((tone, "Claude Code", text))
    if "codex" in agents:
        group = {"matcher": CODEX_MATCHER, "hooks": [
            {"type": "command", "command": command, "timeout": 10, "statusMessage": "identity-guard"}]}
        tone, text = update_hooks_file(ig.codex_home() / "hooks.json", group, dry_run)
        steps.append((tone, "Codex CLI", text))
    return steps


# --- guided setup -----------------------------------------------------------------------------------


class Stopped(Exception):
    """The answers ran out (EOF) before the setup finished."""


class Prompter:
    """Questions on the rail: a heading per question, a dim hint, and the answer after a prompt mark."""

    def __init__(self, ui: ig.Ui) -> None:
        self.ui = ui

    def say(self, text: str = "") -> None:
        print(self.ui.rail(text))

    def heading(self, title: str, hint: str = "", step: str = "") -> None:
        print(self.ui.head("ask", title, step))
        for line in self.ui.wrap(hint) if hint else []:
            self.say(self.ui(line, "dim"))

    def read(self, mark: str) -> str:
        try:
            return input(self.ui.rail(self.ui(mark, "cyan")) + " ").strip()
        except EOFError:
            print()
            raise Stopped()

    def text(self, title: str, hint: str = "", step: str = "", valid: Optional[Callable[[str], Optional[str]]] = None) -> str:
        """One answer; a refused one is explained and asked again (Enter still skips)."""
        self.heading(title, hint, step)
        while True:
            answer = self.read(self.ui.sym["prompt"])
            problem = valid(answer) if valid and answer else None
            if not problem:
                self.say()
                return answer
            self.say(f"{self.ui.mark('fail')} {self.ui(problem + '; try again, or press Enter to skip', 'red')}")

    def yes(self, title: str, hint: str = "", default: bool = True) -> bool:
        self.heading(f"{title}  {self.ui('(Y/n)' if default else '(y/N)', 'dim')}", hint)
        while True:
            answer = self.read(self.ui.sym["prompt"]).lower()
            if answer in ("", "y", "yes", "j", "ja", "n", "no", "nein"):
                self.say()
                return default if not answer else answer in ("y", "yes", "j", "ja")
            self.say(self.ui("Please answer y or n.", "yellow"))

    def many(self, title: str, hint: str, step: str, valid: Callable[[str], Optional[str]]) -> list:
        """Entries one per line until an empty line. valid() returns a reason to refuse, or None."""
        self.heading(title, hint, step)
        values: list = []
        while True:
            value = self.read("+")
            if not value:
                self.say()
                return values
            problem = valid(value)
            if problem:
                self.say(f"{self.ui.mark('fail')} {self.ui(problem + '; not added', 'red')}")
            elif value not in values:
                values.append(value)


def git_email() -> str:
    try:
        return subprocess.run(["git", "config", "--global", "user.email"], capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def past_sessions() -> int:
    """How many Claude Code and Codex transcripts this computer has (what audit would read)."""
    roots = [ig.claude_home() / "projects", ig.codex_home() / "sessions", ig.codex_home() / "archived_sessions"]
    return sum(1 for root in roots if root.exists() for _ in root.rglob("*.jsonl"))


def guided(args: argparse.Namespace) -> int:
    ui = ig.Ui()
    ask = Prompter(ui)
    prefix = Path(args.prefix).expanduser().resolve()
    login = (os.environ.get("USER") or getpass.getuser()).strip().lower()
    existing = read_config(prefix) or {}
    have = {kind: list((existing.get("markers") or {}).get(kind) or []) for kind in MARKER_FLAGS.values()}
    auto_now = {"claude_code_account_email": True, "git_email": True, **{
        k: bool(v) for k, v in (existing.get("auto_markers") or {}).items() if not k.startswith("_")}}

    def new(kind: str, value: str) -> Optional[str]:
        if value.lower() == login:
            return f"'{value}' is your login name, which is in every file path, so it can't be used"
        return "already in your config" if value in have[kind] else None

    def valid_name(value: str) -> Optional[str]:
        return "too short" if len(value) < 2 else new("names", value)

    def valid_email(value: str) -> Optional[str]:
        return "doesn't look like an email address" if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", value) else new("emails", value)

    def valid_phone(value: str) -> Optional[str]:
        return "needs at least 6 digits" if len(re.sub(r"\D", "", value)) < 6 else new("phones", value)

    def valid_other(value: str) -> Optional[str]:
        return "needs at least 4 characters" if len(value) < 4 else new("other", value)

    print(ui.head("start", "agent-identity-guard", "setup"))
    ask.say()
    for line in ui.wrap(f"Stops Claude Code and Codex from sending your name, email, phone number or other details to "
                        f"other machines. Your answers stay on this computer, in {ig.tilde(prefix / 'config.json')}, "
                        "readable only by you. Press Enter to skip any question."):
        ask.say(line)
    ask.say()

    agents = found_agents()
    if agents:
        print(f"{ui.mark('ok')}  {ui('Found ' + ' and '.join(AGENT_NAMES[a] for a in agents), 'bold')}")
    else:
        if not ask.yes("Found neither Claude Code nor Codex. Set up for both anyway?", default=False):
            print(f"{ui(ui.sym['end'], 'gray')}  Nothing to protect yet. Install Claude Code or Codex, then run ./setup.sh again.")
            return 1
        agents = ["claude", "codex"]
    if any(have.values()):
        counts = ", ".join(ig.plural(len(v), ig.KIND_WORDS[k]) for k, v in have.items() if v)
        ask.say(ui(f"Already in your config: {counts}. New answers are added; edit the file to remove entries.", "dim"))
    ask.say()

    names: list = []
    full = ask.text("Your full name", "As people write it, e.g. Jane Doe.", "step 1 of 5", valid_name)
    if full:
        names.append(full)
        words = full.split()
        surname = words[-1] if len(words) > 1 else ""
        if len(surname) >= 2 and not new("names", surname) and ask.yes(
                f'Also block "{surname}" on its own?', "Say no if it is a common word in your work."):
            names.append(surname)
    names += [n for n in ask.many("Other names, nicknames or handles", "One per line, empty line to finish.",
                                  "step 2 of 5", valid_name) if n not in names]

    emails = ask.many("Your email addresses", "Private and work, one per line, empty line to finish.", "step 3 of 5", valid_email)
    auto = dict(auto_now)
    found_git = git_email()
    if found_git and found_git not in emails and found_git not in have["emails"]:
        auto["git_email"] = ask.yes(f"Your git email is {found_git}. Treat it as yours too?", default=auto_now["git_email"])
    if "claude" in agents:
        auto["claude_code_account_email"] = ask.yes("Treat the email you sign in to Claude Code with as yours too?",
                                                    default=auto_now["claude_code_account_email"])

    phones = ask.many("Phone numbers", "Any format, e.g. +44 20 7946 0958. One per line, empty line to finish.",
                      "step 4 of 5", valid_phone)
    other = ask.many("Anything else that identifies you", "Street address, customer or ID numbers. One per line, "
                     "empty line to finish.", "step 5 of 5", valid_other)

    additions = {kind: values for kind, values in
                 (("names", names), ("emails", emails), ("phones", phones), ("other", other)) if values}
    print(ui.head("done", "Summary"))
    for kind, label in (("names", "Names"), ("emails", "Emails"), ("phones", "Phones"), ("other", "Other")):
        values = have[kind] + additions.get(kind, [])
        extra = []
        if kind == "emails":
            if auto["git_email"] and found_git:
                extra.append(f"+ your git email {found_git}")
            if auto["claude_code_account_email"] and "claude" in agents:
                extra.append("+ your Claude Code account email")
        lines = [f" {ui.sym['dot']} ".join(values)] if values else []
        lines += [ui(e, "dim") for e in extra]
        for i, line in enumerate(lines or [ui("none", "dim")]):
            ask.say(ui((label if i == 0 else "").ljust(10), "bold") + line)
    ask.say(ui("Agents".ljust(10), "bold") + ", ".join(AGENT_NAMES[a] for a in agents))
    ask.say(ui("Saved in".ljust(10), "bold") + ig.tilde(prefix))
    if not any(have.values()) and not additions:
        ask.say(ui("Without any details the guard only catches your git or Claude Code email.", "yellow"))
    ask.say()
    if not ask.yes("Install now?"):
        print(f"{ui(ui.sym['end'], 'gray')}  Nothing was changed.")
        return 1

    python = pick_python(args.python)
    steps = install(prefix, agents, python, additions, False, auto)
    print(ui.head("done", "Installed"))
    for tone, label, text in steps:
        ask.say(ui.row(tone, label, text))
    ask.say()

    os.environ["IDENTITY_GUARD_CONFIG"] = str(prefix / "config.json")  # check the config just written
    print(ui.head("done", "Status", "asking Codex for its hook status" if "codex" in agents else ""), flush=True)
    checks = ig.doctor_checks(ui)
    for line in ig.render_checks(ui, checks):
        ask.say(line)
    ask.say()

    script = prefix / "identity_guard.py"
    run = f"{shlex.quote(python)} {ig.tilde(script)}"
    sessions = past_sessions()
    if sessions:
        print(ui.box("Look back: did agents already send your details?", [
            *ui.wrap(f"The guard protects you from now on. The audit reads your {ig.plural(sessions, 'past session')} "
                     "of Claude Code and Codex on this computer, nothing leaves it, and shows which calls carried "
                     "your details and where they went. It can take a minute or two.", 2)], "cyan"))
        ask.say()
        if ask.yes("Run the audit now?"):
            subprocess.run([python, str(script), "audit", "--embedded"])
            ask.say()
        else:
            ask.say(ui(f"Run it any time: {run} audit", "dim"))
            ask.say()

    codex = next((c for c in checks if c.label == "Codex CLI"), None)
    if codex is not None and codex.tone == "warn" and "/hooks" in codex.fix:
        print(ui.box(f"{ui.sym['warn']} One more step: approve the hook in Codex", [
            *ui.wrap("Codex skips new hooks until you approve them. Until you do, Codex can still send your details.", 2),
            "",
            f"  1. Start Codex      {ui('codex', 'bold')}",
            f"  2. Open the hooks   {ui('/hooks', 'bold')}",
            f"  3. Trust            {ui('identity-guard', 'bold')}",
            "",
            ui(f"Then check: {run} doctor", "dim"),
        ]))
        print()
        done = "Claude Code is protected now; Codex is once you approve the hook." if "claude" in agents else \
            "Installed. Codex is protected once you approve the hook."
    else:
        done = "Your details are guarded in " + " and ".join(AGENT_NAMES[a] for a in agents) + "."
    print(f"{ui(ui.sym['end'], 'gray')}  {ui('Done.', 'bold', 'green')} {done}")
    example = (emails or have["emails"] or ["jane.doe@example.com"])[0]
    print(f"   {ui('Try it', 'bold')}   {run} check 'curl -A \"bot ({example})\" https://example.org'")
    print(f"   {ui('Change', 'bold')}   run ./setup.sh again, or edit {ig.tilde(prefix / 'config.json')}")
    return 0


# --- flags ------------------------------------------------------------------------------------------


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
    ig.replace_unprintable()
    ui = ig.Ui()
    end = ui(ui.sym["end"], "gray")
    if args.guided:
        try:
            return guided(args)
        except Stopped:
            print(f"{end}  {ui.mark('fail')} No answer, so nothing was changed.")
            return 1
        except KeyboardInterrupt:
            print(f"\n{end}  Stopped; nothing more was changed.")
            return 130

    prefix = Path(args.prefix).expanduser().resolve()
    if args.agents == "auto":
        agents = found_agents()
    else:
        agents = ["claude", "codex"] if args.agents == "both" else [a.strip() for a in args.agents.split(",")]
    if not agents:
        sys.exit("Found neither ~/.claude nor ~/.codex; pass --agents claude,codex to install anyway.")

    if args.uninstall:
        steps = []
        if "claude" in agents:
            steps.append(("Claude Code", *update_hooks_file(ig.claude_home() / "settings.json", None, args.dry_run)))
        if "codex" in agents:
            steps.append(("Codex CLI", *update_hooks_file(ig.codex_home() / "hooks.json", None, args.dry_run)))
        if args.purge and prefix.exists():
            steps.append(("Install", "info" if args.dry_run else "ok", f"{'would delete' if args.dry_run else 'deleted'} {ig.tilde(prefix)}"))
            if not args.dry_run:
                shutil.rmtree(prefix)
        for label, tone, text in steps:
            print(ui.row(tone, label, text))
        return 0

    python = pick_python(args.python)
    additions = {MARKER_FLAGS[flag]: getattr(args, flag) for flag in MARKER_FLAGS if getattr(args, flag)}
    for tone, label, text in install(prefix, agents, python, additions, args.dry_run):
        print(ui.row(tone, label, text))
    run = f"{shlex.quote(python)} {ig.tilde(prefix / 'identity_guard.py')}"
    print()
    print(f"{ui.mark('info')} List what identifies you in {ig.tilde(prefix / 'config.json')}, or run ./setup.sh for guided questions.")
    if "codex" in agents:
        print(f"{ui.mark('warn')} {ui('Codex runs new hooks only once you approve them: start `codex`, type /hooks, trust identity-guard.', 'bold', 'yellow')}")
    print(f"{ui.mark('info')} Check the setup: {run} doctor")
    return 0


if __name__ == "__main__":
    sys.exit(main())
