# Limits and compatibility

[README](../README.md) · [Setup](setup.md) · [Configuration](configuration.md) · [How it works](how-it-works.md) · [Commands](commands.md) · **Limits** · [Development](development.md)

## What it doesn't catch

agent-identity-guard stops agents that are being helpful to sites. It isn't a sandbox:

- **Indirection:** a value read from a file (`curl -A "$(cat contact.txt)"`), a script whose code isn't in
  the command (`python fetch.py`), or an encoded value (base64, split strings).
- **Content sent by reference:** `scp notes.txt host:` when only the file contains your name.
- **Things outside tool calls:** tool results, what you send to the model providers themselves, prompts
  handed to subagents, and connector message bodies (on purpose, see [How it works](how-it-works.md#the-rules)).
- **Hosted tools that never reach local hooks,** such as a provider-side web search. In the Codex setup
  this was tested with, web search ran locally as `webrun` and was checked.
- **Desktop control,** like typing into native apps through computer use.
- **Your own commands,** and anything after an agent edits its settings to switch the hook off.
- **Codex before you approve the hook:** Codex skips it until then. `doctor` shows the status.

## Known false alarms

- A command that only *mentions* run-time identity sources as text next to a URL counts as reading them.
  An example is a script passed inline to an interpreter that contains `whoami /upn` or
  `$CLAUDE_CODE_USER_EMAIL` as strings. Write such a script to a file with the file-editing tool and run
  the file instead.

- A shell command that *unsets* `$CLAUDE_CODE_USER_EMAIL` (`env -u CLAUDE_CODE_USER_EMAIL …`) next to a
  URL is treated as reading it.
- A script passed inline to an interpreter (`python3 - <<EOF … EOF`) that writes your name next to a URL
  into a local file counts as a network command. Writing the file with the file-editing tool instead
  avoids it, and the block message says so.

## Tested with

- Claude Code (desktop app, October 2026) and Codex CLI 0.153 and 0.164.
- Python 3.9 (macOS system Python), 3.11, 3.12 and 3.13 on macOS.
- The test suite runs on every push on Windows, macOS and Linux (GitHub Actions), with Python 3.9 or 3.10
  and 3.13. On Windows, CI also checks that `setup.cmd` finds Python and stops cleanly. That covers the
  guard, the installer, the guided setup and the Codex status check (against a stand-in `codex`).
- Not yet tried with real agents on Windows. The hook commands follow the documented formats: Claude
  Code's direct launch (an executable plus arguments) and Codex's `commandWindows`, whose only documented
  example uses the `py` launcher. If an agent on Windows doesn't run the hook, `doctor` and the agent's own
  hook list (`/hooks`) will show it; please report it.
