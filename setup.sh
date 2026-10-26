#!/usr/bin/env bash
# One-command guided setup for agent-identity-guard: ./setup.sh
# Finds a Python 3.9+ and runs the installer's guided mode, which asks for your details, installs the
# hook for Claude Code and Codex, and checks the result. Run it again any time to add details.
set -euo pipefail
cd "$(dirname "$0")"

for python in /usr/bin/python3 python3 python3.13 python3.12 python3.11 python3.10 python3.9; do
  if command -v "$python" >/dev/null 2>&1 \
    && "$python" -c 'import sys; sys.exit(sys.version_info < (3, 9))' >/dev/null 2>&1; then
    exec "$python" install.py --guided "$@"
  fi
done

echo "agent-identity-guard needs Python 3.9 or newer." >&2
echo "On macOS: xcode-select --install. On Linux: install python3 with your package manager." >&2
exit 1
