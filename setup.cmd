@echo off
rem One-command guided setup for agent-identity-guard on Windows: setup.cmd
rem Finds a Python 3.9+ (the py launcher first) and runs the installer's guided mode, which asks for your
rem details, installs the hooks for Claude Code and Codex, and checks the result. Run it again to add details.
setlocal
cd /d "%~dp0"
set "PYTHON="
py -3 -c "import sys; sys.exit(sys.version_info < (3, 9))" >nul 2>nul && set "PYTHON=py -3"
if not defined PYTHON ( python -c "import sys; sys.exit(sys.version_info < (3, 9))" >nul 2>nul && set "PYTHON=python" )
if not defined PYTHON ( python3 -c "import sys; sys.exit(sys.version_info < (3, 9))" >nul 2>nul && set "PYTHON=python3" )
if not defined PYTHON (
  echo agent-identity-guard needs Python 3.9 or newer. Install it from https://www.python.org/downloads/ 1>&2
  echo ^(tick "Add python.exe to PATH" or keep the py launcher^), then run setup.cmd again. 1>&2
  exit /b 1
)
%PYTHON% install.py --guided %*
exit /b %errorlevel%
