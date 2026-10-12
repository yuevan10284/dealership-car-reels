#!/bin/sh
# Installs the dealership-car-reels skill for Claude Code and the tools it needs.
# Safe to run again: it only adds what is missing.
set -e

REPO="$(cd "$(dirname "$0")" && pwd)"
SKILLS="$HOME/.claude/skills"
say() { printf '\n%s\n' "$1"; }

say "1/4  Linking the skill into Claude Code"
mkdir -p "$SKILLS"
if [ -e "$SKILLS/dealership-car-reels" ] && [ ! -L "$SKILLS/dealership-car-reels" ]; then
  echo "     $SKILLS/dealership-car-reels already exists and is not a link; leaving it alone."
else
  ln -sfn "$REPO/dealership-car-reels" "$SKILLS/dealership-car-reels"
  echo "     ok"
fi

say "2/4  ffmpeg (video assembly)"
if command -v ffmpeg >/dev/null 2>&1; then
  echo "     ok"
elif command -v brew >/dev/null 2>&1; then
  brew install ffmpeg
else
  echo "     MISSING. Install it: macOS 'brew install ffmpeg' (get brew at https://brew.sh), Linux 'sudo apt install ffmpeg'."
fi

say "3/4  Pillow (captions and logos)"
if python3 -c "import PIL" >/dev/null 2>&1; then
  echo "     ok"
else
  python3 -m pip install --user pillow || echo "     MISSING. Install it: pip3 install pillow"
fi

say "4/4  Higgsfield CLI (video generation)"
if command -v higgsfield >/dev/null 2>&1; then
  echo "     ok"
elif command -v npm >/dev/null 2>&1; then
  npm i -g @higgsfield/cli
else
  echo "     MISSING. Install Node.js from https://nodejs.org, then run: npm i -g @higgsfield/cli"
fi

cat <<'EOF'

Done. Two things left, both one-time:

  1. Sign in to Higgsfield (opens a browser tab):
       higgsfield auth login

  2. Open Claude Code (restart it if it was already open) and say:
       set up car reels for <your dealership's website>

After that, ask for reels any time:
       make the three reels for the 2026 CR-V Hybrid
EOF
