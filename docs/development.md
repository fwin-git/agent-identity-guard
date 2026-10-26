# Development

[README](../README.md) · [Setup](setup.md) · [Configuration](configuration.md) · [How it works](how-it-works.md) · [Commands](commands.md) · [Limits](limits.md) · **Development**

## Layout

| File | What it is |
|---|---|
| `identity_guard.py` | The hook and the `check`, `doctor` and `audit` commands, plus the terminal look they share. One file, standard library only, Python 3.9+. The installer copies it to `~/.identity-guard/`. |
| `install.py` | The installer: the guided setup (`--guided`), flag-based installs, `--uninstall`. It imports `identity_guard.py` for its look and its status checks. |
| `setup.sh` | Finds a Python 3.9+ and runs `install.py --guided`. |
| `config.example.json` | The config with comments; the installer starts new configs from it, without its sample values. |
| `tests/` | `test_identity_guard.py` (the rules, the hook output, the commands) and `test_install.py` (installs into throwaway home folders, including the guided setup with scripted answers). |

## Tests

```bash
python3 -m unittest discover -s tests -v
```

The tests use a made-up identity (`Jane Testperson`) and temporary folders. They never touch your real
config or agent settings, and never start Codex. Each rule has cases that must block and look-alikes
that must pass. Run them on the oldest supported Python too: `/usr/bin/python3` on macOS is 3.9.

## Trying changes

- `python3 identity_guard.py check '…'` with `IDENTITY_GUARD_CONFIG=/path/to/test-config.json` tries a
  rule without installing anything.
- To see the hook output, pipe a tool call into the script:

  ```bash
  echo '{"tool_name": "Bash", "tool_input": {"command": "curl -A \"bot (jane.doe@example.com)\" https://api.example.org"}}' \
    | IDENTITY_GUARD_CONFIG=/path/to/test-config.json python3 identity_guard.py
  ```

- After changing `identity_guard.py`, rerun `install.py` (or `./setup.sh`) to update your installed copy.
  Codex doesn't need a new approval for that.
