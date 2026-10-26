# agent-identity-guard

Stops coding agents (Claude Code and Codex CLI) from sending your name, email address, phone number or
other personal details to websites and servers.

Websites ask automated clients to identify themselves: API policies want a contact address in the
User-Agent, 403 and 429 pages say "tell us who you are", sign-up forms ask for an email. A helpful agent
answers with the one identity it has: yours. agent-identity-guard is a hook both agents run before every
tool call. If the call would carry one of your details to another machine, it is refused before it runs,
the agent is told why, and you see a one-line notice.

## Install

```bash
git clone https://github.com/fwin-git/agent-identity-guard.git && ./agent-identity-guard/setup.sh
```

The guided setup:
- **Asks for your details** (names, emails, phone numbers, anything else). Press Enter to skip any question.
- **Installs the hook** for every agent it finds.
- **Checks the result,** and offers to look back through your past sessions for details that already went out.

Your details stay on your computer, in `~/.identity-guard/config.json`, readable only by you. Run
`./setup.sh` again any time to add more. It needs Python 3.9 or newer, which macOS and most Linux systems
have, and nothing else.

For scripts and dotfiles there is a no-questions install: `python3 install.py --name "Jane Doe" --email
jane.doe@example.com`. See [docs/setup.md](docs/setup.md).

## One more step for Codex

Codex runs a new hook only once you approve it. Until then, Codex can still send your details:

1. Start `codex`
2. Type `/hooks`
3. Trust **identity-guard**

The setup ends with this reminder while it's needed. Codex asks again whenever `~/.codex/hooks.json`
changes; updating the guard itself doesn't need a new approval.

## Check that it works

```bash
python3 ~/.identity-guard/identity_guard.py doctor
```

```
┌  agent-identity-guard  doctor
│
│  ✔ Config       ~/.identity-guard/config.json
│  ✔ Your details 2 emails · 2 names · 1 phone number
│                 j***@example.com, j***@work.example
│                 J*** D**, D**
│                 *********958
│                 also your git email and your Claude Code account email, read on every call
│  ✔ Claude Code  protected
│  ▲ Codex CLI    waiting for your approval
│                 → start `codex`, type /hooks, and trust identity-guard
│  ● Log          0 blocked calls · ~/.identity-guard/guard.log
│
└  ▲ 1 thing needs your attention: Codex CLI
```

`doctor` asks Codex itself whether the hook is approved, so what it says is what Codex will do.

## What gets checked

| Kind of call | Blocked when one of your details |
|---|---|
| **Shell commands**, in both agents | appears in a command that reaches another machine: http(s) URLs, curl and HTTP libraries, `gh`, ssh/scp/rsync, nc/socat, mail, DNS lookups, raw sockets. It's also blocked when your identity is read at run time (`git config user.email`, `$CLAUDE_CODE_USER_EMAIL`) and used in a request. |
| **File writes** (`Write`, `Edit`, Codex `apply_patch`) | sits next to a User-Agent, a request header or a `…_CONTACT=` variable |
| **Web search and web fetch** | is in the search terms or the URL. These tools take nothing else from the agent; Claude Code and Codex send their own User-Agent and headers. |
| **Browser automation** | is in a URL, typed text, a form value or a script |
| **MCP tools** | is anywhere in a call aimed at another host by URL, such as a fetch or HTTP tool (headers, body, parameters). In other calls, only inside a URL. |

These still pass:
- requests to localhost, or to hosts you mark as your own
- files written to disk, commit messages, and `ssh-keygen -C you@…`
- messages you send through connectors such as Slack or email, even when they mention a link

## When it blocks

The tool call doesn't run. The agent gets the reason and what to do instead: use an anonymous
User-Agent, back off when a site rate-limits, or ask you. Its turn continues.

You see one line, `identity-guard blocked a Bash call that would have sent your email address.`, and
`~/.identity-guard/guard.log` records the time, agent, tool and kind of detail, never the content. If
the guard itself fails, it still blocks any call containing one of your details, and lets everything
else through with a notice.

## Commands

`identity_guard.py` is short for `python3 ~/.identity-guard/identity_guard.py`.

| Command | What it does |
|---|---|
| `identity_guard.py doctor` | shows your setup and anything that needs you |
| `identity_guard.py check 'curl -A "bot (you@…)" https://…'` | tests a command (or, with `--tool`, any tool input): `✖ BLOCK` or `✔ ALLOW` |
| `identity_guard.py audit [--details]` | scans your past Claude Code and Codex sessions for calls that already sent your details |

## Limits

It stops agents that are being helpful to sites; it isn't a sandbox. It doesn't see:
- a value read from a file, or a script whose code isn't in the command
- encoded values
- tools that run on the provider's side and never reach local hooks

An agent with shell access could also edit its own settings to switch the hook off. The full list is in
[docs/limits.md](docs/limits.md).

## Docs

- [Setup](docs/setup.md): guided and no-questions install, the full setup session, Codex approval, uninstall
- [Configuration](docs/configuration.md): `config.json`, how names, emails and phone numbers are matched
- [How it works](docs/how-it-works.md): the hook, the rules per tool, what counts as reaching another machine, failure handling
- [Commands](docs/commands.md): `check`, `doctor` and `audit` with their outputs
- [Limits and compatibility](docs/limits.md): what it can't catch, tested versions
- [Development](docs/development.md): tests and layout

## Uninstall

```bash
python3 install.py --uninstall            # remove the hooks
python3 install.py --uninstall --purge    # also delete ~/.identity-guard (config and log)
```

## License

Public domain ([The Unlicense](LICENSE)): do whatever you want with it.
