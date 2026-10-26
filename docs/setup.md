# Setup

[README](../README.md) · **Setup** · [Configuration](configuration.md) · [How it works](how-it-works.md) · [Commands](commands.md) · [Limits](limits.md) · [Development](development.md)

## Guided setup

macOS and Linux:

```bash
git clone https://github.com/fwin-git/agent-identity-guard.git && ./agent-identity-guard/setup.sh
```

Windows, in PowerShell or cmd:

```powershell
git clone https://github.com/fwin-git/agent-identity-guard.git; .\agent-identity-guard\setup.cmd
```

`setup.sh` (`setup.cmd` on Windows, which tries the `py` launcher first) finds a Python 3.9 or newer and
starts `install.py --guided`. The whole session below used a
made-up identity (Jane Doe), with Claude Code and Codex installed and a few earlier sessions that leaked.
Press Enter to skip any question.

<!-- sample: Guided setup/First run, Codex still to approve -->
```
┌  agent-identity-guard  setup
│
│  Stops Claude Code and Codex from sending your name, email, phone number or
│  other details to other machines. Your answers stay on this computer, in
│  ~/.identity-guard/config.json, readable only by you. Press Enter to skip any
│  question.
│
✔  Found Claude Code and Codex CLI
│
◆  Your full name  step 1 of 5
│  As people write it, e.g. Jane Doe.
│  › Jane Doe
│
◆  Also block "Doe" on its own?  (Y/n)
│  Say no if it is a common word in your work.
│  ›
│
◆  Other names, nicknames or handles  step 2 of 5
│  One per line, empty line to finish.
│  + jdoe42
│  +
│
◆  Your email addresses  step 3 of 5
│  Private and work, one per line, empty line to finish.
│  + jane.doe@example.com
│  +
│
◆  Your git email is jane@work.example. Treat it as yours too?  (Y/n)
│  ›
│
◆  Treat the email you sign in to Claude Code with as yours too?  (Y/n)
│  ›
│
◆  Phone numbers  step 4 of 5
│  Any format, e.g. +44 20 7946 0958. One per line, empty line to finish.
│  + +44 20 7946 0958
│  +
│
◆  Anything else that identifies you  step 5 of 5
│  Street address, customer or ID numbers. One per line, empty line to finish.
│  +
│
◇  Summary
│  Names     Jane Doe · Doe · jdoe42
│  Emails    jane.doe@example.com
│            + your git email jane@work.example
│            + your Claude Code account email
│  Phones    +44 20 7946 0958
│  Other     none
│  Agents    Claude Code, Codex CLI
│  Saved in  ~/.identity-guard
│
◆  Install now?  (Y/n)
│  ›
│
◇  Installed
│  ✔ Guard        copied to ~/.identity-guard/identity_guard.py
│  ✔ Config       created ~/.identity-guard/config.json (5 changes)
│  ✔ Claude Code  updated ~/.claude/settings.json
│  ✔ Codex CLI    updated ~/.codex/hooks.json
│
◇  Status  asking Codex for its hook status
│  ✔ Config       ~/.identity-guard/config.json
│  ✔ Your details 2 emails · 3 names · 1 phone number
│                 j***@example.com, j***@work.example
│                 J*** D**, D**, j*****
│                 *********958
│                 also your git email and your Claude Code account email, read on every call
│  ✔ Claude Code  protected
│  ▲ Codex CLI    waiting for your approval
│                 → start `codex`, type /hooks, and trust identity-guard (both hooks)
│  ✔ Session note agents learn the rule when a session starts (Claude Code, Codex CLI)
│  ● Log          0 blocked calls · ~/.identity-guard/guard.log
│
╭─ Look back: did agents already send your details? ───────────────────────────────╮
│                                                                                  │
│  The guard protects you from now on. The audit reads your 4 past sessions of     │
│  Claude Code and Codex on this computer, nothing leaves it, and shows which      │
│  calls carried your details and where they went. It can take a minute or two.    │
│                                                                                  │
╰──────────────────────────────────────────────────────────────────────────────────╯
│
◆  Run the audit now?  (Y/n)
│  ›
│
│  Scanned 17 tool calls (16 Claude Code, 1 Codex)
│
│  ✖ 13 calls sent your details out  2026-09-02 → 2026-10-21
│  ✔ 2 more calls tried and the guard blocked them
│
│  Where they went
│         9  api.example.org
│         3  (no URL in the call)
│         1  docs.example.net
│
│  The guard blocks these from now on. --details lists each call with its transcript.
│
╭─ ▲ One more step: approve the hook in Codex ─────────────────────────────────────╮
│                                                                                  │
│  Codex skips new hooks until you approve them. Until you do, Codex can still     │
│  send your details.                                                              │
│                                                                                  │
│    1. Start Codex      codex                                                     │
│    2. Open the hooks   /hooks                                                    │
│    3. Trust            identity-guard (both of its hooks)                        │
│                                                                                  │
│  Then check: /usr/bin/python3 ~/.identity-guard/identity_guard.py doctor         │
│                                                                                  │
╰──────────────────────────────────────────────────────────────────────────────────╯

└  Done. Claude Code is protected now; Codex is once you approve the hook.
   Try it   /usr/bin/python3 ~/.identity-guard/identity_guard.py check 'curl -A "bot (jane.doe@example.com)" https://example.org'
   Change   run ./setup.sh again, or edit ~/.identity-guard/config.json
```

In a terminal the steps, symbols and panels are in color. The look-back panel is cyan, and Enter starts
the audit. The Codex panel is yellow and appears only while Codex still needs approving. If there are no
past sessions, the look-back is skipped.

The setup copies `identity_guard.py` to `~/.identity-guard/`, so the clone can be moved or deleted
afterwards. It writes your answers to `~/.identity-guard/config.json`, readable only by you, and adds two
hooks to each agent:
- **`PreToolUse`** checks each tool call. In Claude Code (`~/.claude/settings.json`) it runs for shell,
  web, file and MCP tools; in Codex (`~/.codex/hooks.json`) for every tool.
- **`SessionStart`** adds the [session note](how-it-works.md#at-session-start-the-note), so agents
  know the rule before a site pushes back.

On Windows, Claude Code starts the guard's Python directly, without a shell. Codex gets one command that
works in both cmd and PowerShell: the `py` launcher, then the quoted path to the guard.

On Windows, `~` means your user folder (`%USERPROFILE%`).

Each settings file gets a `.bak` copy before it changes, and other hooks in it stay as they are.

### Entries it refuses

The setup says why and lets you correct the entry:
- a name or detail that's too short
- an email without a domain
- a phone number with fewer than six digits
- your login name, which appears in every file path, so it would match everywhere

<!-- sample: Guided setup/Entries it refuses -->
```
┌  agent-identity-guard  setup
│
│  Stops Claude Code and Codex from sending your name, email, phone number or
│  other details to other machines. Your answers stay on this computer, in
│  ~/.identity-guard/config.json, readable only by you. Press Enter to skip any
│  question.
│
✔  Found Claude Code
│
◆  Your full name  step 1 of 5
│  As people write it, e.g. Jane Doe.
│  › J
│  ✖ too short; try again, or press Enter to skip
│  › jane
│  ✖ 'jane' is your login name, which is in every file path, so it can't be used; try again, or press Enter to skip
│  › jd
│
◆  Other names, nicknames or handles  step 2 of 5
│  One per line, empty line to finish.
│  +
│
◆  Your email addresses  step 3 of 5
│  Private and work, one per line, empty line to finish.
│  + jane@
│  ✖ doesn't look like an email address; not added
│  + jane.doe@example.com
│  +
│
◆  Your git email is jane@work.example. Treat it as yours too?  (Y/n)
│  ›
│
◆  Treat the email you sign in to Claude Code with as yours too?  (Y/n)
│  ›
│
◆  Phone numbers  step 4 of 5
│  Any format, e.g. +44 20 7946 0958. One per line, empty line to finish.
│  + 12 34
│  ✖ needs at least 6 digits; not added
│  +
│
◆  Anything else that identifies you  step 5 of 5
│  Street address, customer or ID numbers. One per line, empty line to finish.
│  + abc
│  ✖ needs at least 4 characters; not added
│  +
│
◇  Summary
│  Names     jd
│  Emails    jane.doe@example.com
│            + your git email jane@work.example
│            + your Claude Code account email
│  Phones    none
│  Other     none
│  Agents    Claude Code
│  Saved in  ~/.identity-guard
│
◆  Install now?  (Y/n)
│  › n
│
└  Nothing was changed.
```

### Running it again

Run `./setup.sh` again any time. It keeps what you entered before and adds new answers on top, and your
earlier yes/no answers become the defaults. To remove an entry, edit `config.json`.

<!-- sample: Guided setup/Running it again -->
```
┌  agent-identity-guard  setup
│
│  Stops Claude Code and Codex from sending your name, email, phone number or
│  other details to other machines. Your answers stay on this computer, in
│  ~/.identity-guard/config.json, readable only by you. Press Enter to skip any
│  question.
│
✔  Found Claude Code
│  Already in your config: 2 names, 1 email, 1 phone number. New answers are added; edit the file to remove entries.
│
◆  Your full name  step 1 of 5
│  As people write it, e.g. Jane Doe.
│  ›
│
◆  Other names, nicknames or handles  step 2 of 5
│  One per line, empty line to finish.
│  +
│
◆  Your email addresses  step 3 of 5
│  Private and work, one per line, empty line to finish.
│  + jane@second.example
│  +
│
◆  Your git email is jane@work.example. Treat it as yours too?  (Y/n)
│  ›
│
◆  Treat the email you sign in to Claude Code with as yours too?  (Y/n)
│  ›
│
◆  Phone numbers  step 4 of 5
│  Any format, e.g. +44 20 7946 0958. One per line, empty line to finish.
│  +
│
◆  Anything else that identifies you  step 5 of 5
│  Street address, customer or ID numbers. One per line, empty line to finish.
│  +
│
◇  Summary
│  Names     Jane Doe · Doe
│  Emails    jane.doe@example.com · jane@second.example
│            + your git email jane@work.example
│            + your Claude Code account email
│  Phones    +44 20 7946 0958
│  Other     none
│  Agents    Claude Code
│  Saved in  ~/.identity-guard
│
◆  Install now?  (Y/n)
│  ›
│
◇  Installed
│  ✔ Guard        copied to ~/.identity-guard/identity_guard.py
│  ✔ Config       updated ~/.identity-guard/config.json (1 change)
│  ✔ Claude Code  unchanged ~/.claude/settings.json
│
◇  Status
│  ✔ Config       ~/.identity-guard/config.json
│  ✔ Your details 3 emails · 2 names · 1 phone number
│                 j***@example.com, j***@second.example, j***@work.example
│                 J*** D**, D**
│                 *********958
│                 also your git email and your Claude Code account email, read on every call
│  ✔ Claude Code  protected
│  ● Codex CLI    not installed
│  ✔ Session note agents learn the rule when a session starts (Claude Code)
│  ● Log          0 blocked calls · ~/.identity-guard/guard.log
│
╭─ Look back: did agents already send your details? ───────────────────────────────╮
│                                                                                  │
│  The guard protects you from now on. The audit reads your 1 past session of      │
│  Claude Code and Codex on this computer, nothing leaves it, and shows which      │
│  calls carried your details and where they went. It can take a minute or two.    │
│                                                                                  │
╰──────────────────────────────────────────────────────────────────────────────────╯
│
◆  Run the audit now?  (Y/n)
│  › n
│
│  Run it any time: /usr/bin/python3 ~/.identity-guard/identity_guard.py audit
│
└  Done. Your details are guarded in Claude Code.
   Try it   /usr/bin/python3 ~/.identity-guard/identity_guard.py check 'curl -A "bot (jane@second.example)" https://example.org'
   Change   run ./setup.sh again, or edit ~/.identity-guard/config.json
```

## Approving the hook in Codex

Codex runs a hook only after you approve it once. Until then, Codex can still send your details:

1. Start `codex`
2. Type `/hooks`
3. Trust **identity-guard**, both of its hooks (tool calls and session start)

`identity_guard.py doctor` asks Codex itself for the hook's status: approved (`protected`), `waiting for
your approval`, or `changed since you approved it`. Codex asks again whenever `~/.codex/hooks.json`
changes, for example when you reinstall into another folder. Updating `identity_guard.py` itself
doesn't need a new approval.

## Install without questions

For scripts and dotfiles, `install.py` takes your details as flags (each one repeatable) and asks nothing:

```bash
python3 install.py --name "Jane Doe" --name "Doe" --email jane.doe@example.com --phone "+44 20 7946 0958"
```

<!-- sample: install.py (no questions)/Install with flags -->
```
✔ Guard        copied to ~/.identity-guard/identity_guard.py
✔ Config       created ~/.identity-guard/config.json (2 changes)
✔ Claude Code  updated ~/.claude/settings.json (backup settings.json.bak)
✔ Codex CLI    updated ~/.codex/hooks.json

● List what identifies you in ~/.identity-guard/config.json, or run ./setup.sh for guided questions.
▲ Codex runs new hooks only once you approve them: start `codex`, type /hooks, trust identity-guard (both of its hooks).
● Check the setup: /usr/bin/python3 ~/.identity-guard/identity_guard.py doctor
```

| Flag | What it does |
|---|---|
| `--name`, `--email`, `--phone`, `--other` | add to the config (repeatable). An existing config is never overwritten, only added to. |
| `--dry-run` | shows what would change, changes nothing |
| `--agents claude`, `codex`, `both` | picks the agents instead of detecting `~/.claude` and `~/.codex` |
| `--prefix DIR` | installs somewhere other than `~/.identity-guard` |
| `--python PATH` | the Python the hook runs with. The default is `/usr/bin/python3` when it's 3.9+, because it works without shell profiles or version managers. |

If an agent's settings file isn't valid JSON, the installer leaves it alone and says so:

<!-- sample: install.py (no questions)/Agent settings file broken -->
```
✔ Guard        copied to ~/.identity-guard/identity_guard.py
✔ Config       created ~/.identity-guard/config.json (1 change)
✖ Claude Code  skipped ~/.claude/settings.json: not valid JSON (Expecting property name enclosed in double quotes: line 1 column 18 (char 17)); fix it and run again
✔ Codex CLI    updated ~/.codex/hooks.json

● List what identifies you in ~/.identity-guard/config.json, or run ./setup.sh for guided questions.
▲ Codex runs new hooks only once you approve them: start `codex`, type /hooks, trust identity-guard (both of its hooks).
● Check the setup: /usr/bin/python3 ~/.identity-guard/identity_guard.py doctor
```

## Uninstall

```bash
python3 install.py --uninstall            # remove both hooks from Claude Code and Codex
python3 install.py --uninstall --purge    # also delete ~/.identity-guard (config and log)
```

On Windows, use `py install.py …` instead of `python3 install.py …`.

<!-- sample: install.py (no questions)/Uninstall and purge -->
```
✔ Claude Code  updated ~/.claude/settings.json (backup settings.json.bak)
✔ Codex CLI    updated ~/.codex/hooks.json (backup hooks.json.bak)
✔ Install      deleted ~/.identity-guard
```
