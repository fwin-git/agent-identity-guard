#!/usr/bin/env python3
"""Install agent-identity-guard for Claude Code and Codex CLI, or remove it.

    python3 install.py --name "Jane Doe" --email jane@example.com    install, adding markers
    python3 install.py --dry-run                                      show what would change
    python3 install.py --uninstall [--purge]                          remove the hooks [and ~/.identity-guard]

Copies identity_guard.py into the install folder (default ~/.identity-guard), creates config.json there
if it is missing (never overwrites it; --name/--email/--phone/--other add to it), and registers a
PreToolUse hook in ~/.claude/settings.json and ~/.codex/hooks.json, replacing earlier identity-guard
entries and keeping a .bak of each file it changes. Codex then asks you to trust the hook once (/hooks).
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent
CLAUDE_MATCHER = "Bash|PowerShell|WebFetch|WebSearch|Write|Edit|MultiEdit|NotebookEdit|mcp__.*"
CODEX_MATCHER = "*"
MARKER_FLAGS = {"name": "names", "email": "emails", "phone": "phones", "other": "other"}


def claude_home() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude").expanduser()


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex").expanduser()


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


def write_config(prefix: Path, additions: dict, dry_run: bool) -> str:
    path = prefix / "config.json"
    if path.exists():
        config = json.loads(path.read_text())
        created = False
    else:  # the example's comments, without its example values
        config = json.loads((HERE / "config.example.json").read_text())
        for kind in MARKER_FLAGS.values():
            config["markers"][kind] = []
        created = True
    added = 0
    for kind, values in additions.items():
        current = config.setdefault("markers", {}).setdefault(kind, [])
        for value in values:
            if value not in current:
                current.append(value)
                added += 1
    if not created and not added:
        return f"kept {path}"
    if dry_run:
        return f"would {'create' if created else 'update'} {path}" + (f" (+{added} marker(s))" if added else "")
    prefix.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n")
    os.chmod(path, 0o600)  # it lists personal details
    return f"{'created' if created else 'updated'} {path}" + (f" (+{added} marker(s))" if added else "")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--prefix", default="~/.identity-guard", help="install folder (default ~/.identity-guard)")
    parser.add_argument("--agents", default="auto", help="claude, codex, both or auto (whichever is installed)")
    parser.add_argument("--python", help="python3 the hook runs with (default /usr/bin/python3 when it is 3.9+)")
    for flag, kind in MARKER_FLAGS.items():
        parser.add_argument(f"--{flag}", action="append", default=[], metavar="VALUE", help=f"add to markers.{kind} (repeatable)")
    parser.add_argument("--dry-run", action="store_true", help="show what would change, change nothing")
    parser.add_argument("--uninstall", action="store_true", help="remove the hooks from Claude Code and Codex")
    parser.add_argument("--purge", action="store_true", help="with --uninstall: also delete the install folder (config and log)")
    args = parser.parse_args()

    prefix = Path(args.prefix).expanduser().resolve()
    if args.agents == "auto":
        agents = [a for a, home in (("claude", claude_home()), ("codex", codex_home())) if home.exists()]
    else:
        agents = ["claude", "codex"] if args.agents == "both" else [a.strip() for a in args.agents.split(",")]
    if not agents:
        sys.exit("Found neither ~/.claude nor ~/.codex; pass --agents claude,codex to install anyway.")

    report = []
    if args.uninstall:
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
    script = prefix / "identity_guard.py"
    command = f"{shlex.quote(python)} {shlex.quote(str(script))}"
    if args.dry_run:
        report.append(f"would copy identity_guard.py to {script}")
    else:
        prefix.mkdir(parents=True, exist_ok=True)
        shutil.copy2(HERE / "identity_guard.py", script)
        os.chmod(script, 0o755)
        report.append(f"copied identity_guard.py to {script}")
    additions = {MARKER_FLAGS[flag]: getattr(args, flag) for flag in MARKER_FLAGS if getattr(args, flag)}
    report.append(write_config(prefix, additions, args.dry_run))
    if "claude" in agents:
        group = {"matcher": CLAUDE_MATCHER, "hooks": [{"type": "command", "command": command, "timeout": 10}]}
        report.append(update_hooks_file(claude_home() / "settings.json", group, args.dry_run))
    if "codex" in agents:
        group = {"matcher": CODEX_MATCHER, "hooks": [
            {"type": "command", "command": command, "timeout": 10, "statusMessage": "identity-guard"}]}
        report.append(update_hooks_file(codex_home() / "hooks.json", group, args.dry_run))
    print("\n".join(report))
    print(f"\nNext:\n  1. List what identifies you in {prefix / 'config.json'} (names, emails, phones, other).")
    if "codex" in agents:
        print("  2. Codex runs new hooks only once you trust them: start `codex`, type /hooks, trust identity-guard.")
    print(f"  3. Check the setup: {shlex.quote(python)} {shlex.quote(str(script))} doctor")
    return 0


if __name__ == "__main__":
    sys.exit(main())
