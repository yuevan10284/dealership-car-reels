#!/usr/bin/env python3
"""Report what is ready and what is missing, with the command that fixes each gap.

  check_setup.py        # exits 0 when everything needed to make a reel is in place
"""
import shutil
import subprocess
import sys

from common import default_slug, list_dealers

missing = []


def line(ok, label, fix=""):
    print(("ok       " if ok else "MISSING  ") + label + ("" if ok or not fix else f"\n         fix: {fix}"))
    if not ok:
        missing.append(label)


line(bool(shutil.which("ffmpeg")), "ffmpeg", "brew install ffmpeg   (Linux: sudo apt install ffmpeg)")
try:
    import PIL  # noqa: F401
    line(True, "Pillow (Python imaging)")
except ImportError:
    line(False, "Pillow (Python imaging)", "pip3 install pillow")

cli = shutil.which("higgsfield")
line(bool(cli), "Higgsfield CLI", "npm i -g @higgsfield/cli")
if cli:
    try:
        p = subprocess.run(["higgsfield", "account", "status"], capture_output=True, text=True, timeout=40)
        status = (p.stdout + p.stderr).strip().splitlines()
        ok = p.returncode == 0
        fix = "higgsfield auth login   (the user runs this; it opens a browser)"
        if not ok and "workspace" in " ".join(status).lower():
            fix = "higgsfield workspace list, then higgsfield workspace set <id>"
        line(ok, "Higgsfield account" + (f": {status[-1]}" if ok and status else ""), fix)
    except Exception as e:
        line(False, f"Higgsfield account ({e})", "higgsfield auth login")

dealers = list_dealers()
line(bool(dealers), "dealership profile" + (f": {', '.join(dealers)} (default: {default_slug()})" if dealers else ""),
     "setup_dealer.py <dealership website>")

print("\nReady." if not missing else f"\n{len(missing)} thing(s) to fix before making reels.")
sys.exit(1 if missing else 0)
