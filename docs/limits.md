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

- A shell command that *unsets* `$CLAUDE_CODE_USER_EMAIL` (`env -u CLAUDE_CODE_USER_EMAIL …`) next to a
  URL is treated as reading it.
- A script passed inline to an interpreter (`python3 - <<EOF … EOF`) that writes your name next to a URL
  into a local file counts as a network command. Writing the file with the file-editing tool instead
  avoids it, and the block message says so.

## Tested with

- Claude Code (desktop app, October 2026) and Codex CLI 0.153 and 0.164.
- Python 3.9 (macOS system Python), 3.11, 3.12 and 3.13 on macOS. Linux should work the same.
- Windows is untested. The doctor's Codex check needs `select` on pipes, which Windows lacks; there it
  falls back to the approval recorded in Codex's config.
