#!/usr/bin/env python3
"""Set up a dealership once: read its name, address and logo from its website.

  setup_dealer.py https://www.exampletoyota.com        # create a profile from the website
  setup_dealer.py --dealer example-toyota --address "1 Main St, Austin, TX 78701"
  setup_dealer.py --dealer example-toyota --logo 3      # use logo candidate number 3
  setup_dealer.py --dealer example-toyota --logo 2 --logo-with-name yes   # badge + name
  setup_dealer.py --dealer example-toyota --logo ~/Downloads/logo.png --logo-style white
  setup_dealer.py --list                                # profiles that exist
  setup_dealer.py --use example-toyota                  # make it the default

Every run rewrites the profile and a preview image showing how the branding will look.
Anything the website did not give up can be passed as a flag; nothing is required but a name.
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urljoin, urlparse

from PIL import Image, ImageDraw

import brand_video
from common import HOME, dealer_dir, default_slug, get, json_ld, ld_types, list_dealers, slugify, unescape

BUSINESS = {"AutoDealer", "AutomotiveBusiness", "LocalBusiness", "Organization", "Store",
            "MotorcycleDealer", "AutoRepair", "Corporation"}
# Images that say "logo" but are not the dealership's: trust badges and website vendors.
VENDOR_RE = re.compile(r"carfax|autocheck|award|badge|bbb|payment|social|facebook|instagram|youtube|"
                       r"dealeron|dealer\.com|dealerinspire|dealersocket|cdk|sokal|foxdealer|overfuel|"
                       r"dealereprocess|carnow|capitalone|kbb|edmunds|cargurus", re.I)
ADDRESS_RE = re.compile(
    r"\b(\d{1,6} [A-Za-z0-9 .'#-]{3,40}?),?\s+([A-Za-z .'-]{2,30}),\s*([A-Z]{2})\.?\s+(\d{5})(?:-\d{4})?\b")


def text_of(value):
    return re.sub(r"\s+", " ", value).strip() if isinstance(value, str) else ""


def find_business(html):
    """(name, address, city) from the page's structured data, as far as it goes."""
    name = address = city = ""
    nodes = [n for n in json_ld(html) if BUSINESS & set(ld_types(n))]
    nodes.sort(key=lambda n: "AutoDealer" not in ld_types(n))
    for n in nodes:
        name = name or text_of(n.get("name"))
        addr = n.get("address")
        addr = addr[0] if isinstance(addr, list) and addr else addr
        if not address and isinstance(addr, dict) and addr.get("streetAddress"):
            street, town = text_of(addr.get("streetAddress")), text_of(addr.get("addressLocality"))
            region, code = text_of(addr.get("addressRegion")), text_of(str(addr.get("postalCode", "")))
            address = ", ".join(p for p in (street, town, f"{region} {code}".strip()) if p)
            city = ", ".join(p for p in (town, region) if p)
        elif not address and isinstance(addr, str):
            address = text_of(addr)
    if not name:
        m = re.search(r'property=["\']og:site_name["\'][^>]*content=["\']([^"\']+)', html, re.I) or \
            re.search(r'content=["\']([^"\']+)["\'][^>]*property=["\']og:site_name', html, re.I)
        name = text_of(m.group(1)) if m else ""
    if not name:
        m = re.search(r"<title>([^<]*)", html, re.I)
        parts = [p.strip() for p in re.split(r"[|–—]| - ", m.group(1))] if m else []
        parts = [p for p in parts if p and not re.search(r"for sale|new &|dealer in|serving", p, re.I)]
        name = min(parts, key=len) if parts else ""
    if not address:
        visible = re.sub(r"<[^>]+>", " ", re.sub(r"<(script|style)\b.*?</\1>", " ", html, flags=re.S | re.I))
        m = ADDRESS_RE.search(re.sub(r"\s+", " ", visible)) or ADDRESS_RE.search(html)
        if m:
            address = f"{m.group(1).strip()}, {m.group(2).strip()}, {m.group(3)} {m.group(4)}"
            city = f"{m.group(2).strip()}, {m.group(3)}"
    return name, address, city


def logo_urls(html, base):
    """Likely logo image URLs, best guesses first."""
    urls = []

    def add(u):
        if isinstance(u, dict):
            u = u.get("url") or u.get("contentUrl")
        if isinstance(u, str) and u.strip() and not u.startswith("data:"):
            full = urljoin(base, unescape(u.strip()))
            if full not in urls:
                urls.append(full)

    for n in json_ld(html):
        if BUSINESS & set(ld_types(n)):
            add(n.get("logo"))
    for tag in re.findall(r"<img\b[^>]*>", html, re.I):
        if not re.search(r"logo", tag, re.I) or re.search(VENDOR_RE, tag):
            continue
        for attr in ("src", "data-src", "data-lazy-src", "data-original"):
            m = re.search(rf'\b{attr}=["\']([^"\']+)', tag, re.I)
            if m:
                add(m.group(1))
    return urls


def rasterize(data, dest):
    """Save downloaded logo bytes as a PNG. SVGs go through rsvg-convert or macOS Quick Look."""
    if b"<svg" in data[:2000].lower():
        with tempfile.TemporaryDirectory() as d:
            svg = Path(d) / "logo.svg"
            svg.write_bytes(data)
            if shutil.which("rsvg-convert"):
                subprocess.run(["rsvg-convert", "-w", "1200", str(svg), "-o", str(dest)], check=True)
                return
            if shutil.which("qlmanage"):
                subprocess.run(["qlmanage", "-t", "-s", "1200", "-o", d, str(svg)],
                               check=True, capture_output=True)
                Image.open(Path(d) / "logo.svg.png").save(dest)
                return
        raise ValueError("SVG logo and no converter available")
    with tempfile.NamedTemporaryFile(suffix=".img") as f:
        f.write(data)
        f.flush()
        Image.open(f.name).convert("RGBA").save(dest)


def collect_logos(html, base, folder):
    """Download logo candidates into folder as 1.png, 2.png, …; return their paths."""
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    kept = []
    for url in logo_urls(html, base)[:12]:
        dest = folder / f"{len(kept) + 1}.png"
        try:
            rasterize(get(url, binary=True, timeout=20), dest)
            w, h = Image.open(dest).size
            if w < 60 or h < 16 or not 0.8 <= w / h <= 14:
                raise ValueError("wrong shape for a logo")
        except Exception:
            dest.unlink(missing_ok=True)
            continue
        kept.append(dest)
        if len(kept) == 8:
            break
    return kept


def candidate_sheet(paths, out):
    """All logo candidates, numbered, on light and dark halves so any colour shows up."""
    row, sheet = 150, Image.new("RGB", (900, 150 * max(1, len(paths))), (235, 235, 235))
    draw = ImageDraw.Draw(sheet)
    draw.rectangle([480, 0, 900, sheet.height], fill=(30, 30, 30))
    for i, p in enumerate(paths):
        img = Image.open(p).convert("RGBA")
        img.thumbnail((360, 110))
        for x in (70, 510):
            sheet.paste(img, (x, i * row + (row - img.height) // 2), img)
        draw.text((18, i * row + 60), str(i + 1), fill=(0, 0, 0), font=brand_video.font(34, "bold"))
    sheet.save(out, quality=90)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("site", nargs="?", help="the dealership's website")
    ap.add_argument("--dealer", help="slug of an existing profile to change")
    ap.add_argument("--name")
    ap.add_argument("--address", help="one line, as it should appear on the end card")
    ap.add_argument("--city", help='e.g. "Austin, TX"')
    ap.add_argument("--scenery", help="local landscape for the heartfelt style, e.g. "
                                      '"a Hill Country overlook with live oaks and limestone"')
    ap.add_argument("--logo", help="candidate number, image file, image URL, or 'none' for text only")
    ap.add_argument("--logo-style", choices=["auto", "asis", "white", "plate-white", "plate-dark"])
    ap.add_argument("--logo-with-name", choices=["yes", "no"],
                    help="write the dealership name beside the logo (for a bare manufacturer badge)")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--use", metavar="SLUG", help="make this profile the default")
    a = ap.parse_args()

    if a.list:
        for slug in list_dealers():
            print(("* " if slug == default_slug() else "  ") + slug)
        if not list_dealers():
            print("No dealerships set up yet.")
        return
    if a.use:
        if a.use not in list_dealers():
            sys.exit(f"No profile named '{a.use}'. Have: {', '.join(list_dealers()) or 'none'}")
        (HOME / "default").write_text(a.use)
        print(f"Default dealership is now {a.use}")
        return

    notes, html, dealer = [], "", {}
    if a.site:
        site = a.site if "//" in a.site else "https://" + a.site
        site = f"{urlparse(site).scheme}://{urlparse(site).netloc}"
        try:
            html = get(site)
        except Exception as e:
            if not (a.name and a.address and a.logo):
                notes.append(f"{site} refuses scripted requests ({str(e)[-40:]}). Read the name, address "
                             "and logo from the site in a browser and pass --name, --address and --logo.")
        name, address, city = find_business(html) if html else ("", "", "")
        name = a.name or name or urlparse(site).netloc.replace("www.", "").split(".")[0].title()
        slug = a.dealer or slugify(name)
        old = dealer_dir(slug) / "dealer.json"
        dealer = json.loads(old.read_text()) if old.exists() else {}
        dealer.update({k: v for k, v in dict(slug=slug, name=name, site=site, address=address, city=city).items()
                       if v or k not in dealer})
    elif a.dealer:
        path = dealer_dir(a.dealer) / "dealer.json"
        if not path.exists():
            sys.exit(f"No profile named '{a.dealer}'. Have: {', '.join(list_dealers()) or 'none'}")
        dealer = json.loads(path.read_text())
    else:
        ap.error("give the dealership's website, or --dealer SLUG to change an existing profile")

    for key in ("name", "address", "city", "scenery"):
        if getattr(a, key):
            dealer[key] = getattr(a, key)
    if a.logo_style:
        dealer["logo_style"] = a.logo_style
    if a.logo_with_name:
        dealer["logo_with_name"] = a.logo_with_name == "yes"
    folder = dealer_dir(dealer["slug"])
    folder.mkdir(parents=True, exist_ok=True)
    cand_dir = folder / "logo-candidates"

    if html:
        found = collect_logos(html, dealer["site"], cand_dir)
        if found:
            candidate_sheet(found, folder / "logo-candidates.jpg")
            if not a.logo and not dealer.get("logo"):
                shutil.copy(found[0], folder / "logo.png")
                dealer["logo"] = "logo.png"
        elif not dealer.get("logo"):
            notes.append("No logo image found on the site; the dealership name will be shown as text. "
                         "Pass --logo <file or URL> to add one.")
    if a.logo:
        if a.logo == "none":
            dealer.pop("logo", None)
        else:
            try:
                if a.logo.isdigit():
                    shutil.copy(cand_dir / f"{a.logo}.png", folder / "logo.png")
                elif "//" in a.logo:
                    rasterize(get(a.logo, binary=True), folder / "logo.png")
                else:
                    rasterize(Path(a.logo).expanduser().read_bytes(), folder / "logo.png")
                dealer["logo"] = "logo.png"
            except Exception as e:
                sys.exit(f"Could not use that logo: {e}")

    for key, why in (("address", "the end card will show no address"),
                     ("scenery", "the heartfelt style will use a generic hillside")):
        if not dealer.get(key):
            notes.append(f"No {key} yet — {why}. Pass --{key} to set it.")
    (folder / "dealer.json").write_text(json.dumps(dealer, indent=2) + "\n")
    if not default_slug() or len(list_dealers()) == 1:
        (HOME / "default").write_text(dealer["slug"])

    dealer["_dir"] = folder
    brand_video.preview(dealer, folder / "preview.jpg")
    style = ""
    if dealer.get("logo"):
        style = brand_video.prepare_logo(folder / dealer["logo"], dealer.get("logo_style", "auto"))[1]
    del dealer["_dir"]
    print(json.dumps(dealer, indent=2))
    print(f"\nprofile:  {folder / 'dealer.json'}")
    print(f"preview:  {folder / 'preview.jpg'}   <- look at this")
    if (folder / "logo-candidates.jpg").exists():
        print(f"logos:    {folder / 'logo-candidates.jpg'}   <- numbered candidates found on the site")
    print("logo:     " + (f"logo.png, shown as '{style}'" if style else "none (dealership name as text)"))
    print(f"default:  {default_slug()}")
    for n in notes:
        print("NOTE: " + n)


if __name__ == "__main__":
    main()
