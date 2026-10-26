# Commands

[README](../README.md) · [Setup](setup.md) · [Configuration](configuration.md) · [How it works](how-it-works.md) · **Commands** · [Limits](limits.md) · [Development](development.md)

`identity_guard.py` is short for `python3 ~/.identity-guard/identity_guard.py`. Without arguments it
runs as the hook and reads the tool call from stdin.

All commands use the same terminal look:
- `✔` fine, `▲` needs you, `✖` blocked or broken, `●` information
- colors only in a terminal, never with `NO_COLOR` or `TERM=dumb`
- ASCII symbols (`+ ! x *`) where the terminal can't show Unicode

## doctor

Shows your setup and anything that needs you, with the fix right under it. For Codex it asks Codex
itself whether the hook is approved, so what it says is what Codex will do. It exits with 1 when
something is broken.

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
│  ✔ Codex CLI    protected
│  ● Log          0 blocked calls · ~/.identity-guard/guard.log
│
└  ✔ All set. The guard checks every tool call for your details.
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

| Row | States |
|---|---|
| Config | `✔` found · `▲` missing · `✖` can't be read |
| Your details | `✔` counts, with the values masked · `✖` none listed |
| Claude Code | `✔` protected · `▲` installed, but not protected · `●` not installed |
| Codex CLI | `✔` protected (also "trusted by policy") · `▲` waiting for your approval · `▲` changed since you approved it · `▲` installed, but not protected · `●` not installed |
| Log | `●` how many calls were blocked, or off |

When `codex` can't be asked (not on PATH), `doctor` falls back to the approval recorded in Codex's
`config.toml`:

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
│  ✔ Codex CLI    protected
│                 approval recorded; Codex couldn't be asked to confirm
│  ● Log          0 blocked calls · ~/.identity-guard/guard.log
│
└  ✔ All set. The guard checks every tool call for your details.
```

## check

Runs a command, or with `--tool` any tool input, through your config the way the hook would judge it. It
exits with 1 for BLOCK and 0 for ALLOW. `--tool` takes `Bash`, `WebSearch`, `WebFetch`, `Write`,
`apply_patch` or `webrun`; for any other tool name, pass the tool input as JSON. Pass `-` to read the
text from stdin.

```
$ identity_guard.py check 'curl -A "research-bot/1.0 (contact: jane.doe@example.com)" https://api.example.org/search'
✖ BLOCK  Bash: carries your email address in a command that reaches another machine or sets request headers

$ identity_guard.py check 'curl -A research-bot/1.0 https://api.example.org/search'
✔ ALLOW  Bash

$ identity_guard.py check 'gh issue create --title "Crash" --body "Reported by Jane Doe"'
✖ BLOCK  Bash: carries your name in a command that reaches another machine or sets request headers

$ identity_guard.py check 'dig jane-doe.collector.example.net'
✖ BLOCK  Bash: carries your name in a command that reaches another machine or sets request headers

$ identity_guard.py check 'ssh build.example.net "echo deployed by Jane Doe"'
✖ BLOCK  Bash: carries your name in a command that reaches another machine or sets request headers

$ identity_guard.py check 'curl -d "phone=0044 20 7946-0958" https://forms.example.com'
✖ BLOCK  Bash: carries your phone number in a command that reaches another machine or sets request headers

$ identity_guard.py check 'curl -A "bot ($(git config user.email))" https://api.example.org'
✖ BLOCK  Bash: carries your identity (read at run time) in a command that reaches another machine or sets request headers

$ identity_guard.py check 'curl -d email=jane.doe@example.com http://localhost:3000/signup'
✔ ALLOW  Bash

$ identity_guard.py check 'ssh-keygen -t ed25519 -C "jane.doe@example.com"'
✔ ALLOW  Bash

$ identity_guard.py check 'git commit -m "Fix mail settings for Jane Doe"'
✔ ALLOW  Bash

$ identity_guard.py check --tool WebSearch 'Jane Doe home address'
✖ BLOCK  WebSearch: carries your name in a web search query

$ identity_guard.py check --tool WebSearch 'weather forecast'
✔ ALLOW  WebSearch

$ identity_guard.py check --tool WebFetch 'https://forms.example.com/?contact=jane.doe@example.com'
✖ BLOCK  WebFetch: carries your email address in a fetched URL

$ identity_guard.py check --tool Write 'HEADERS = {"User-Agent": "scraper (jane.doe@example.com)"}'
✖ BLOCK  Write: carries your email address next to a User-Agent, header or contact variable in a file

$ identity_guard.py check --tool Write '# Maintainer: Jane Doe <jane.doe@example.com>'
✔ ALLOW  Write

$ identity_guard.py check --tool apply_patch '*** Begin Patch\n*** Add File: .env\n+CRAWLER_CONTACT=jane.doe@example.com\n*** End Patch'
✖ BLOCK  apply_patch: carries your email address next to a User-Agent, header or contact variable in a file

$ identity_guard.py check --tool webrun 'Jane Doe linkedin'
✖ BLOCK  webrun: carries your name in a web search query or opened URL

$ identity_guard.py check --tool mcp__Claude_Browser__computer '{"action": "type", "text": "jane.doe@example.com"}'
✖ BLOCK  mcp__Claude_Browser__computer: carries your email address in a browser action (URL, typed text, form value or script)

$ identity_guard.py check --tool mcp__fetch__fetch '{"url": "https://api.example.org/search", "headers": {"User-Agent": "bot (jane.doe@example.com)"}}'
✖ BLOCK  mcp__fetch__fetch: carries your email address in a request to another host (URL, headers or body)

$ identity_guard.py check --tool mcp__http__request '{"method": "POST", "url": "https://forms.example.com/signup", "body": "email=jane.doe@example.com"}'
✖ BLOCK  mcp__http__request: carries your email address in a request to another host (URL, headers or body)

$ identity_guard.py check --tool mcp__slack__send_message '{"channel": "C1", "text": "Hi, Jane Doe here"}'
✔ ALLOW  mcp__slack__send_message
```

## audit

Reads your past Claude Code transcripts (`~/.claude/projects`) and Codex sessions (`~/.codex/sessions`,
`archived_sessions`) and shows the calls that carried your details: how many went out and where. Calls
the guard already blocked are counted separately. Nothing leaves your computer, and the content of the
calls is never printed. It exits with 2 when something went out.

```
┌  agent-identity-guard  audit
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
└  The guard blocks these from now on. --details lists each call with its transcript.
```

`--details` lists each call with its time, agent, tool, kind of detail, destination and transcript:

```
┌  agent-identity-guard  audit
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
│  when              agent   tool          what                         destination, transcript
│  2026-09-02 10:00  claude  Bash          email address                api.example.org  ~/.claude/projects/-home-jane-project/s1.jsonl
│  2026-09-02 10:01  claude  Bash          email address                api.example.org  ~/.claude/projects/-home-jane-project/s1.jsonl
│  2026-09-02 10:02  claude  Bash          email address                api.example.org  ~/.claude/projects/-home-jane-project/s1.jsonl
│  2026-09-02 10:03  claude  Bash          email address                api.example.org  ~/.claude/projects/-home-jane-project/s1.jsonl
│  2026-09-02 10:04  claude  Bash          email address                api.example.org  ~/.claude/projects/-home-jane-project/s1.jsonl
│  2026-09-02 10:05  claude  Bash          email address                api.example.org  ~/.claude/projects/-home-jane-project/s1.jsonl
│  2026-09-02 10:06  claude  Bash          email address                api.example.org  ~/.claude/projects/-home-jane-project/s1.jsonl
│  2026-09-02 10:07  claude  Bash          email address                api.example.org  ~/.claude/projects/-home-jane-project/s1.jsonl
│  2026-09-02 10:08  claude  Bash          email address                api.example.org  ~/.claude/projects/-home-jane-project/s1.jsonl
│  2026-09-14 16:20  claude  Bash          email address                (no URL in the call)  ~/.claude/projects/-home-jane-project/s2.jsonl
│  2026-09-14 16:22  claude  Bash          name                         (no URL in the call)  ~/.claude/projects/-home-jane-project/s2.jsonl
│  2026-10-21 08:00  claude  Bash          email address                docs.example.net  ~/.claude/projects/-home-jane-project/s2.jsonl
│  2026-10-24 11:00  claude  Bash          email address                api.example.org (blocked)  ~/.claude/projects/-home-jane-project/s3.jsonl
│  2026-10-24 11:01  claude  Bash          email address                api.example.org (blocked)  ~/.claude/projects/-home-jane-project/s3.jsonl
│  2026-10-01 12:00  codex   Bash          name                         (no URL in the call)  ~/.codex/sessions/2026/10/01/rollout.jsonl
└  The guard blocks these from now on.
```

When nothing went out:

```
┌  agent-identity-guard  audit
│
│  Scanned 4 tool calls (4 Claude Code, 0 Codex)
│
└  ✔ Nothing went out. No past call sent your details; the guard blocked 2 calls that tried.
```

Options: `--claude-only`, `--codex-only`, `--claude-dir DIR`, `--codex-dir DIR`. On a terminal, long
histories show a progress counter. The guided setup offers the audit at the end.
