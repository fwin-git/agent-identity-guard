# Configuration

[README](../README.md) · [Setup](setup.md) · **Configuration** · [How it works](how-it-works.md) · [Commands](commands.md) · [Limits](limits.md) · [Development](development.md)

Your details live in `~/.identity-guard/config.json`, or in the file named by `IDENTITY_GUARD_CONFIG`.
The setup creates it readable only by you. Keys that start with `_` are comments. Changes apply on the
next tool call; nothing needs restarting.

```json
{
  "markers": {
    "emails": ["jane.doe@example.com", "jdoe@work.example"],
    "names": ["Jane Doe", "Doe"],
    "phones": ["+44 20 7946 0958", "020 7946 0958"],
    "other": ["42 Example Street", "janedoe1990"]
  },
  "auto_markers": {
    "claude_code_account_email": true,
    "git_email": true
  },
  "ignore": [],
  "local_hosts": ["*.home.arpa", "192.168.1.*"],
  "log_file": "guard.log",
  "session_note": true
}
```

| Key | What it does |
|---|---|
| `markers.emails` | Matched as written, ignoring case. URL-encoded forms (`jane.doe%40example.com`) match too. |
| `markers.names` | Whole words, ignoring case, with any of space `.` `_` `-` `+` between the words, so `Jane Doe` also catches `jane.doe`, `Jane_Doe` and `jane-doe.example.net`. Add your surname on its own to catch it anywhere. Avoid a first name that is also an everyday word or a name in your code. At least 2 characters. |
| `markers.phones` | Digits with any of space `(` `)` `.` `-` `/` between them. A number written with `+` or `00` also matches with either prefix or none. A longer number that merely contains the digits doesn't match. Add the national form (`020 …`) as a separate entry. At least 6 digits. |
| `markers.other` | Anything else, matched as written ignoring case, with any whitespace between words: a street address, a handle, a customer number. At least 4 characters. |
| `auto_markers.claude_code_account_email` | Also treat the email Claude Code signs you in with as yours. Claude Code passes it to the hook as `CLAUDE_CODE_USER_EMAIL`. |
| `auto_markers.git_email` | Also treat `git config --global user.email` as yours, read on every call. |
| `ignore` | Values never treated as identity. Your login name is always ignored, because it's in every home path. |
| `local_hosts` | Extra host patterns (fnmatch globs) that count as your own machines; requests there may carry your details. Always local: `localhost`, `127.*`, `::1`, `0.0.0.0`, `*.localhost`, `*.local`, `*.test`, `*.internal` and hosts without a dot. |
| `log_file` | Where blocked calls are logged, relative to the config file. `""` turns logging off. The log records time, agent, session, tool, kind of detail and folder, never the content. |
| `session_note` | `true` (the default) adds a short note to the agent's context when a session starts: never identify you to sites, use an anonymous User-Agent, back off on HTTP 429, or ask you. It contains none of your details. `false` turns it off; the hook stays registered and adds nothing, so Codex doesn't ask for a new approval. |

`./setup.sh` and `install.py --name/--email/--phone/--other` add to this file, and neither ever
overwrites it. `identity_guard.py doctor` shows what's in effect, with values masked:

<!-- sample: doctor/All set -->
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
│  ✔ Session note agents learn the rule when a session starts (Claude Code, Codex CLI)
│  ● Log          0 blocked calls · ~/.identity-guard/guard.log
│
└  ✔ All set. The guard checks every tool call for your details.
```

If the file is missing or isn't valid JSON, `doctor` says so, and the hook falls back to your
automatic emails. See [How it works](how-it-works.md#when-something-goes-wrong).
