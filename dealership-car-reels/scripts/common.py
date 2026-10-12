"""Shared helpers: fetching pages, reading JSON-LD, and the dealer profiles.

Dealer profiles live outside the skill folder (default ~/.car-reels) so updating the skill
with `git pull` never touches them:

  ~/.car-reels/default                    slug of the dealership used when none is named
  ~/.car-reels/dealers/<slug>/dealer.json name, site, address, scenery, logo settings
  ~/.car-reels/dealers/<slug>/logo.png    the logo used in the videos
"""
import json
import os
import re
import subprocess
import sys
import urllib.request
import warnings
from pathlib import Path

# Pillow warns about palette PNGs with transparency; they are converted to RGBA anyway.
warnings.filterwarnings("ignore", category=UserWarning, module="PIL")

SKILL = Path(__file__).resolve().parent.parent
HOME = Path(os.environ.get("CAR_REELS_HOME", Path.home() / ".car-reels"))
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126 Safari/537.36"
)


def get(url, binary=False, timeout=45):
    """Fetch a URL as a browser would. Falls back to curl, which some dealer sites accept
    when they reject Python's TLS fingerprint."""
    headers = {"User-Agent": UA, "Accept": "*/*" if binary else "text/html,application/xhtml+xml,*/*",
               "Accept-Language": "en-US,en;q=0.9"}
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as r:
            data = r.read()
    except Exception as first:
        p = subprocess.run(["curl", "-sSL", "--compressed", "--fail", "--max-time", str(timeout),
                            "-A", UA, "-H", "Accept-Language: en-US,en;q=0.9", url], capture_output=True)
        if p.returncode != 0:
            raise RuntimeError(f"could not fetch {url}: {first}") from first
        data = p.stdout
    return data if binary else data.decode("utf-8", "replace")


def unescape(html):
    """Undo the escaping that hides URLs inside inline JSON and attributes."""
    for a, b in (("\\/", "/"), ("\\u002F", "/"), ("\\u002f", "/"), ("\\u0026", "&"),
                 ("&amp;", "&"), ("&#x2F;", "/"), ("&#x2B;", "+"), ("&quot;", '"')):
        html = html.replace(a, b)
    return html


def json_ld(html):
    """Every JSON-LD object on the page, flattened (lists and @graph unpacked)."""
    out = []

    def walk(node):
        if isinstance(node, list):
            for n in node:
                walk(n)
        elif isinstance(node, dict):
            out.append(node)
            walk(node.get("@graph", []))

    for block in re.findall(r"<script[^>]*application/ld\+json[^>]*>(.*?)</script>", html, re.S | re.I):
        try:
            walk(json.loads(block.strip(), strict=False))
        except ValueError:
            continue
    # Some sites split one entity across nodes and link them with {"@id": ...}; join them up.
    by_id = {n["@id"]: n for n in out if "@id" in n and len(n) > 1}
    for n in out:
        for key, value in n.items():
            if isinstance(value, dict) and set(value) == {"@id"} and value["@id"] in by_id:
                n[key] = by_id[value["@id"]]
    return out


def ld_types(node):
    t = node.get("@type", [])
    return [t] if isinstance(t, str) else list(t)


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "dealer"


def dealer_dir(slug):
    return HOME / "dealers" / slug


def list_dealers():
    root = HOME / "dealers"
    return sorted(p.parent.name for p in root.glob("*/dealer.json")) if root.exists() else []


def default_slug():
    f = HOME / "default"
    slug = f.read_text().strip() if f.exists() else ""
    if slug and (dealer_dir(slug) / "dealer.json").exists():
        return slug
    found = list_dealers()
    return found[0] if len(found) == 1 else None


def load_dealer(slug=None):
    """The named dealer profile, or the default one. Exits with setup instructions if none."""
    slug = slug or default_slug()
    if not slug:
        have = list_dealers()
        if have:
            sys.exit("Several dealerships are set up; pass --dealer with one of: " + ", ".join(have))
        sys.exit("No dealership is set up yet. Run: setup_dealer.py <dealership website>")
    path = dealer_dir(slug) / "dealer.json"
    if not path.exists():
        sys.exit(f"No dealership profile named '{slug}'. Set up: {', '.join(list_dealers()) or 'none'}")
    dealer = json.loads(path.read_text())
    dealer["_dir"] = path.parent
    return dealer
