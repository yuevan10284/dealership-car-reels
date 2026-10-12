#!/usr/bin/env python3
"""Pull a vehicle's photos and basic facts from a dealership listing page.

  fetch_listing.py --find "cr-v hybrid"             # search the dealer's sitemap for listings
  fetch_listing.py <listing-url> --out <dir>        # download photos + listing.json + contact sheet
  fetch_listing.py --image-urls urls.txt --vehicle "2026 Honda CR-V" --out <dir>   # URLs read in a browser
  fetch_listing.py --html saved.html <listing-url> --out <dir>         # page saved from a browser
  fetch_listing.py --photos <folder> --vehicle "2026 Honda CR-V" --out <dir>   # photos you already have

Works from the page's structured data and image URLs, so it is not tied to one website
platform. Many dealer sites refuse scripted requests; for those, read the gallery image
URLs in a real browser (--image-urls), save the page (--html), or use photos on disk (--photos).
--vin, --stock and --color fill in facts the page did not give up.
"""
import argparse
import hashlib
import io
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

from PIL import Image

from common import get, json_ld, ld_types, load_dealer, unescape

MAKES = ("Acura|Alfa Romeo|Aston Martin|Audi|Bentley|BMW|Buick|Cadillac|Chevrolet|Chrysler|Dodge|Ferrari|"
         "FIAT|Fisker|Ford|Genesis|GMC|Honda|Hyundai|INEOS|INFINITI|Jaguar|Jeep|Kia|Lamborghini|Land Rover|"
         "Lexus|Lincoln|Lotus|Lucid|Maserati|Mazda|McLaren|Mercedes-Benz|MINI|Mitsubishi|Nissan|Polestar|"
         "Porsche|Ram|Rivian|Rolls-Royce|Scout|Subaru|Tesla|Toyota|Volkswagen|Volvo")
NAME_RE = re.compile(rf"\b((?:19|20)\d{{2}})\s+({MAKES})\s+([A-Za-z0-9][\w.-]*(?:\s+[\w.-]+){{0,5}})", re.I)
VIN_RE = re.compile(r"\b([A-HJ-NPR-Z0-9]{17})\b")
IMG_RE = re.compile(r"""(?<![\w.:/])((?:(?:https?:)?//|/(?!/))[^\s"'<>\\),]+?\.(?:jpe?g|png|webp)(?:\?[^\s"'<>\\),]*)?)""", re.I)
JUNK_RE = re.compile(r"logo|icon|sprite|badge|banner|placeholder|avatar|carfax|award|button|favicon|"
                     r"coming-?soon|no-?image|stock-?photo|spinner|payment|social|flag", re.I)
INVENTORY_HOSTS = re.compile(r"homenetiol|dealer\.com|dealerinspire|dealeron|cdk|vauto|dealereprocess|"
                             r"autotrader|carsforsale|dealercarsearch|spincar|impel|evoximages|"
                             r"overfuel|sokal|foxdealer|teamvelocity|cloudfront|imgix", re.I)
SIZE_RE = re.compile(r"(?<!\w)(\d{1,4})x(\d{1,4})(?!\w)")


def vehicle_node(html):
    """The page's vehicle structured data. Sites often split it across a Vehicle and a
    Product node, so merge them, first value for each field winning."""
    merged = {}
    for n in json_ld(html):
        if {"Vehicle", "Car", "Product", "Motorcycle"} & set(ld_types(n)):
            for key, value in n.items():
                if value and key not in merged:
                    merged[key] = value
    return merged


def plain(value):
    if isinstance(value, dict):
        value = value.get("name") or value.get("@value") or ""
    return re.sub(r"\s+", " ", str(value)).strip() if value else ""


def read_facts(html, url):
    """Year/make/model, colour, VIN and stock number, from structured data then the title."""
    node = vehicle_node(html)
    title = re.search(r"<title>([^<]*)", html, re.I)
    title = unescape(title.group(1)).strip() if title else ""
    info = {"url": url, "page_title": title}
    name = plain(node.get("name"))
    m = NAME_RE.search(name) or NAME_RE.search(title) or NAME_RE.search(url.replace("-", " ").replace("/", " "))
    if m:
        year, make = m.group(1), m.group(2)
        model = plain(node.get("model")) or m.group(3).split()[0]
        if model.lower().startswith(make.lower()):
            model = model[len(make):].strip() or model
        trim = re.split(r"\s+(?:for sale|for|in|near|at)\b", m.group(3), flags=re.I)[0].strip()
        info.update(year=year, make=make, model=model, model_trim=trim,
                    vehicle=f"{year} {make} {model}")
    colour = plain(node.get("color")) or plain(node.get("vehicleExteriorColor"))
    if not colour:
        c = re.search(r'(?:exterior[ _-]?colou?r|ext\.? colou?r)["\'>:\s=]+([A-Z][A-Za-z -]{2,30})', html)
        colour = c.group(1).strip() if c else ""
    if colour:
        info["color"] = colour
    vin = plain(node.get("vehicleIdentificationNumber"))
    vin = vin or next(iter(VIN_RE.findall(url.upper()) + VIN_RE.findall(title)), "")
    if not vin:
        v = re.search(r'\bvin["\'>:\s=#]+([A-HJ-NPR-Z0-9]{17})\b', html, re.I)
        vin = v.group(1).upper() if v else ""
    if vin:
        info["vin"] = vin
    stock = plain(node.get("sku"))
    if not stock:
        s = re.search(r'stock\s*(?:number|no\.?|num|#)?\s*["\']?\s*[:=#]\s*["\']?\s*'
                      r'([A-Za-z0-9-]*\d[A-Za-z0-9-]*)', html, re.I)
        stock = s.group(1) if s else ""
    if stock:
        info["stock"] = stock
    cond = re.search(r"\b(new|used|certified|pre-owned)\b", title + " " + url, re.I)
    if cond:
        info["condition"] = cond.group(1).title()
    return info


def stem(url):
    """Identity of a photo regardless of which size variant the URL asks for."""
    path = SIZE_RE.sub("", urlparse(url).path)
    return urlparse(url).netloc + path


def bigger(url):
    """Ask for a larger rendition where the CDN's URL scheme is known; else unchanged."""
    if "homenetiol.com" in url:
        return SIZE_RE.sub("1920x1440", url, count=1)
    # Drop resize parameters (?width=400) so the CDN serves the original.
    return re.sub(r"(?<=[?&])(?:width|height|w|h|size|resize|fit|quality|q)=[^&]*&?", "", url).rstrip("?&")


def photo_urls(html, base, vin):
    """Gallery image URLs, best evidence first: structured data, then VIN-tagged URLs,
    then the image host that carries the most gallery-like pictures."""
    html = unescape(html)
    node = vehicle_node(html)
    listed = node.get("image", [])
    listed = [listed] if isinstance(listed, (str, dict)) else listed
    listed = [i.get("url") or i.get("contentUrl") if isinstance(i, dict) else i for i in listed]
    listed = [urljoin(base, i) for i in listed if isinstance(i, str) and i]

    found = []
    for u in IMG_RE.findall(html):
        u = urljoin(base, u)
        if u not in found and not JUNK_RE.search(urlparse(u).path):
            found.append(u)

    if len(listed) >= 4:
        pool = listed
    elif vin and sum(vin.lower() in u.lower() for u in found) >= 4:
        pool = [u for u in found if vin.lower() in u.lower()]
    else:
        hosts = {}
        for u in found:
            hosts.setdefault(urlparse(u).netloc, []).append(u)
        site = urlparse(base).netloc

        def score(host):
            return (len({stem(u) for u in hosts[host]})
                    + (25 if INVENTORY_HOSTS.search(host) else 0) - (10 if host == site else 0))

        pool = listed + (hosts[max(hosts, key=score)] if hosts else [])

    full = [u for u in pool if not re.search(r"thumb", urlparse(u).path, re.I)]
    pool = full if len(full) >= 3 else pool
    best = {}  # one URL per photo: the largest size variant seen
    for u in pool:
        size = SIZE_RE.search(urlparse(u).path)
        area = int(size.group(1)) * int(size.group(2)) if size else 0
        if stem(u) not in best or area > best[stem(u)][0]:
            best[stem(u)] = (area, u)
    return [u for _, u in best.values()]


def save_photos(sources, out, max_photos, load):
    """Keep real vehicle photos (big enough, landscape-ish), as JPEG. Returns the count."""
    photos = out / "photos"
    photos.mkdir(parents=True, exist_ok=True)
    for old in photos.glob("*.jpg"):
        old.unlink()
    seen, n = set(), 0
    for src in sources:
        if n == max_photos:
            break
        try:
            data = load(src)
            digest = hashlib.md5(data).hexdigest()
            img = Image.open(io.BytesIO(data))
            img.load()
        except Exception:
            continue
        if digest in seen or img.width < 500 or not 1.0 <= img.width / img.height <= 2.1:
            continue
        seen.add(digest)
        n += 1
        img.convert("RGB").save(photos / f"{n:02d}.jpg", quality=92)
    return n


def contact_sheet(out, count):
    cols = 5
    rows = -(-count // cols)
    sheet = Image.new("RGB", (cols * 384, rows * 256), (20, 20, 20))
    for i, p in enumerate(sorted((out / "photos").glob("*.jpg"))):
        img = Image.open(p).convert("RGB")
        img.thumbnail((384, 256))
        sheet.paste(img, ((i % cols) * 384 + (384 - img.width) // 2, (i // cols) * 256 + (256 - img.height) // 2))
    sheet.save(out / "contact-sheet.jpg", quality=88)


def fetch(url, out, max_photos, html_file=None):
    html = Path(html_file).read_text(errors="replace") if html_file else get(url)
    info = read_facts(html, url)
    urls = photo_urls(html, url, info.get("vin", ""))

    def load(u):
        try:
            return get(bigger(u), binary=True, timeout=30)
        except Exception:
            return get(u, binary=True, timeout=30)

    count = save_photos(urls, out, max_photos, load)
    if count < 3:
        sys.exit(f"Only found {count} usable photo(s) on that page. The site may load its gallery with "
                 "scripts or block downloads. Open the listing in a browser and save the page "
                 "(then use --html), or save the photos to a folder (then use --photos).")
    finish(info, out, count)


def from_folder(folder, out, max_photos, vehicle):
    files = sorted(p for p in Path(folder).expanduser().iterdir()
                   if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".heic", ".avif"))
    count = save_photos(files, out, max_photos, lambda p: p.read_bytes())
    if not count:
        sys.exit(f"No usable photos in {folder} (need JPG/PNG/WebP at least 500 px wide, landscape).")
    info = {"source": str(folder)}
    m = NAME_RE.search(vehicle or "")
    if vehicle:
        info["vehicle"] = vehicle
    if m:
        info.update(year=m.group(1), make=m.group(2), model=m.group(3).split()[0])
    finish(info, out, count)


def from_urls(listfile, out, max_photos, vehicle, page_url):
    urls = [u.strip() for u in Path(listfile).expanduser().read_text().split() if "//" in u]
    urls = list(dict.fromkeys(u for u in urls if not JUNK_RE.search(urlparse(u).path)))

    def load(u):
        try:
            return get(bigger(u), binary=True, timeout=30)
        except Exception:
            return get(u, binary=True, timeout=30)

    count = save_photos(urls, out, max_photos, load)
    if not count:
        sys.exit("None of those URLs gave a usable photo (need at least 500 px wide, landscape). "
                 "Save the photos from the browser into a folder and use --photos instead.")
    info = {"url": page_url} if page_url else {}
    m = NAME_RE.search(vehicle or "")
    if vehicle:
        info["vehicle"] = vehicle
    if m:
        info.update(year=m.group(1), make=m.group(2), model=m.group(3).split()[0])
    finish(info, out, count)


EXTRA = {}  # facts given on the command line; they win over anything read from the page


def finish(info, out, count):
    info.update(EXTRA)
    info["photo_count"] = count
    (out / "listing.json").write_text(json.dumps(info, indent=2) + "\n")
    contact_sheet(out, count)
    print(json.dumps(info, indent=2))
    if "vehicle" not in info:
        print("NOTE: could not read the year/make/model; pass it yourself when branding (--vehicle).")


def find(query, site, condition, limit=15):
    """Search the site's sitemaps for listing pages matching the query (model, trim, stock, VIN).

    Each word of the query must appear in the URL, ignoring punctuation, so "f-150" matches
    ".../Ford-F+150-XLT-..." and "cr-v hybrid" matches ".../honda-cr-v-hybrid-...".
    """
    flat = lambda t: re.sub(r"[^a-z0-9]+", "", t.lower())
    words = [flat(w) for w in query.split() if flat(w)]
    other = {"new": r"used|certified|pre-?owned|cpo", "used": r"new"}.get(condition)
    queue, seen, hits = [], set(), []
    try:
        queue += re.findall(r"(?im)^sitemap:\s*(\S+)", get(urljoin(site, "/robots.txt"), timeout=20))
    except Exception:
        pass
    queue = queue or [urljoin(site, "/sitemap.xml")]
    while queue and len(seen) < 30 and len(hits) < 200:
        # Inventory sitemaps first: they are where the listing pages are.
        queue.sort(key=lambda u: not re.search(r"inventory|vehicle|vdp|new|used|detail", u, re.I))
        sm = queue.pop(0)
        if sm in seen:
            continue
        seen.add(sm)
        try:
            xml = get(sm, timeout=30)
        except Exception:
            continue
        for loc in re.findall(r"<loc>\s*(?:<!\[CDATA\[)?\s*([^<\]\s]+)", xml):
            loc = unescape(loc)
            if re.search(r"\.xml(\.gz)?(\?|$)", loc):
                queue.append(loc)
                continue
            path = urlparse(loc).path.lower()
            if loc in hits or not all(w in flat(path) for w in words):
                continue
            if other and re.search(rf"(?<![a-z])({other})(?![a-z])", path):
                continue
            hits.append(loc)
    # A VIN in the URL means one specific car; model and category pages go last.
    hits.sort(key=lambda u: not VIN_RE.search(urlparse(u).path.upper().replace("-", " ").replace("/", " ")))
    if not hits:
        sys.exit(f"No listings matching '{query}' in {site}'s sitemap. Open the dealer's inventory page "
                 "in a browser, find the car, and pass its listing URL instead.")
    for h in hits[:limit]:
        print(h)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("url", nargs="?", help="a vehicle listing page")
    ap.add_argument("--find", metavar="WORDS", help='search the dealer site, e.g. "cr-v hybrid" or a stock number')
    ap.add_argument("--condition", choices=["new", "used"])
    ap.add_argument("--dealer", help="dealer profile slug (for --find); default is the default profile")
    ap.add_argument("--site", help="website to search with --find, instead of the dealer profile's")
    ap.add_argument("--html", help="a listing page saved from the browser, for sites that block scripts")
    ap.add_argument("--photos", metavar="FOLDER", help="use photos already on disk")
    ap.add_argument("--image-urls", metavar="FILE", help="text file of gallery image URLs, one per line")
    ap.add_argument("--vehicle", help='year make model, for --photos / --image-urls, e.g. "2026 Honda CR-V"')
    ap.add_argument("--vin")
    ap.add_argument("--stock")
    ap.add_argument("--color")
    ap.add_argument("--out", default=".")
    ap.add_argument("--max-photos", type=int, default=20)
    a = ap.parse_args()
    out = Path(a.out).expanduser()
    EXTRA.update({k: v for k, v in (("vin", a.vin), ("stock", a.stock), ("color", a.color)) if v})
    if a.url and a.vehicle and (a.html or not (a.photos or a.image_urls)):
        EXTRA["vehicle"] = a.vehicle
    if a.find:
        find(a.find, a.site or load_dealer(a.dealer)["site"], a.condition)
    elif a.photos:
        out.mkdir(parents=True, exist_ok=True)
        from_folder(a.photos, out, a.max_photos, a.vehicle)
    elif a.image_urls:
        out.mkdir(parents=True, exist_ok=True)
        from_urls(a.image_urls, out, a.max_photos, a.vehicle, a.url)
    elif a.url or a.html:
        out.mkdir(parents=True, exist_ok=True)
        fetch(a.url or "", out, a.max_photos, a.html)
    else:
        ap.error("give a listing URL, --find WORDS, --image-urls FILE, --html FILE or --photos FOLDER")
