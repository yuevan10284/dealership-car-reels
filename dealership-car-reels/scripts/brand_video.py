#!/usr/bin/env python3
"""Burn the dealership's branding, captions, an end card and a music bed onto a raw clip.

  brand_video.py --input raw.mp4 --style ../styles/heartfelt.json \
                 --vehicle "2026 Honda CR-V" --out final.mp4 [--copy copy.json] [--dealer slug]

Text is rendered with Pillow (many ffmpeg builds have no drawtext filter) and composited
with ffmpeg overlay + alpha fades. Timings come from the style JSON; the logo, dealer name
and address come from the dealer profile (see setup_dealer.py). --copy supplies per-car
wording: {"captions": [["line", ...], ...], "headline": ["line", ...]}.
"""
import argparse
import json
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from common import SKILL, load_dealer

W, H = 1080, 1920
MAX_TEXT_W = 960
WHITE = (255, 255, 255, 255)
SOFT = (255, 255, 255, 225)

# First font file that exists wins. (path, {weight: face index}).
FONTS = [
    ("/System/Library/Fonts/Avenir Next.ttc", {"bold": 0, "demi": 2, "medium": 5, "heavy": 8}),
    ("/System/Library/Fonts/HelveticaNeue.ttc", {"bold": 1, "demi": 1, "medium": 0, "heavy": 1}),
    ("/System/Library/Fonts/Helvetica.ttc", {"bold": 1, "demi": 1, "medium": 0, "heavy": 1}),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", {}),
    ("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", {}),
    ("C:/Windows/Fonts/arialbd.ttf", {}),
]
FONT_PATH, FONT_FACES = next(((p, f) for p, f in FONTS if Path(p).exists()), (None, {}))


def font(size, weight):
    if not FONT_PATH:
        return ImageFont.load_default(size)
    return ImageFont.truetype(FONT_PATH, size, index=FONT_FACES.get(weight, 0))


def fit(text, size, weight, tracking=0):
    """Largest font <= size that keeps the line inside the safe width."""
    while size > 20:
        f = font(size, weight)
        if f.getlength(text) + tracking * (len(text) - 1) <= MAX_TEXT_W:
            return f
        size -= 2
    return font(size, weight)


def gradient(top_alpha, bottom_alpha, y0, y1):
    strip = Image.new("L", (1, y1 - y0))
    for y in range(y1 - y0):
        t = y / max(1, y1 - y0 - 1)
        strip.putpixel((0, y), int(top_alpha + (bottom_alpha - top_alpha) * t))
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    black = Image.new("RGBA", (W, y1 - y0), (0, 0, 0, 255))
    black.putalpha(strip.resize((W, y1 - y0)))
    img.paste(black, (0, y0))
    return img


def text_layer(lines):
    """lines: (text, font, y, fill, tracking). Centered with a soft drop shadow."""
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for text, f, y, fill, tracking in lines:
        widths = [f.getlength(c) + tracking for c in text]
        x = (W - (sum(widths) - tracking)) / 2
        for c, w in zip(text, widths):
            ImageDraw.Draw(shadow).text((x, y + 3), c, font=f, fill=(0, 0, 0, 210))
            ImageDraw.Draw(layer).text((x, y), c, font=f, fill=fill)
            x += w
    return Image.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(9)), layer)


def plate(img, colour):
    """Put a logo on a rounded plate so it stays readable over any footage."""
    pad = max(14, img.height // 4)
    size = (img.width + pad * 2, img.height + pad * 2)
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(out).rounded_rectangle([0, 0, size[0] - 1, size[1] - 1], radius=pad, fill=colour + (255,))
    out.alpha_composite(img, (pad, pad))
    return out


def prepare_logo(path, style="auto"):
    """Make any logo file usable on video. Returns (image, style actually used).

    Styles: asis        light logo with a transparent background, used unchanged
            white       black or grey single-colour logo, recoloured white
            plate-white coloured logo, placed on a white rounded plate
            plate-dark  coloured logo with white parts, placed on a dark rounded plate
    "auto" picks one by looking at the pixels; a logo with no transparency keeps its own
    background colour as the plate.
    """
    img = Image.open(path).convert("RGBA")
    alpha = img.getchannel("A")
    if alpha.getextrema()[0] > 250:  # no transparency: trim the border, keep its own background
        bg = img.getpixel((2, 2))[:3]
        box = ImageChops.difference(img.convert("RGB"), Image.new("RGB", img.size, bg)).point(
            lambda v: 255 if v > 24 else 0).getbbox()
        img = img.crop(box) if box else img
        return plate(img, bg), "own-background"
    img = img.crop(alpha.point(lambda a: 255 if a > 16 else 0).getbbox())
    if style == "auto":
        small = img.resize((min(img.width, 200), max(1, min(img.height, 200))))
        px = [(r, g, b) for r, g, b, a in small.getdata() if a > 128] or [(255, 255, 255)]
        lum = [0.299 * r + 0.587 * g + 0.114 * b for r, g, b in px]
        light = sum(v > 180 for v in lum) / len(px)
        dark = sum(v < 90 for v in lum) / len(px)
        grey = sum(max(p) - min(p) < 40 for p in px) / len(px)
        if light > 0.85:
            style = "asis"
        elif grey > 0.85:  # black or grey single-colour artwork reads best in white
            style = "white"
        else:
            style = "plate-dark" if light > 0.25 else "plate-white"
    if style == "white":
        white = Image.new("RGBA", img.size, (255, 255, 255, 255))
        white.putalpha(img.getchannel("A"))
        img = white
    elif style == "plate-white":
        img = plate(img, (255, 255, 255))
    elif style == "plate-dark":
        img = plate(img, (17, 17, 17))
    return img, style


def load_logo(dealer, box):
    """The dealer's logo scaled to fit inside box (w, h), or None if there is no usable file."""
    name = dealer.get("logo")
    path = dealer["_dir"] / name if name else None
    if not path or not path.exists():
        return None
    try:
        img, _ = prepare_logo(path, dealer.get("logo_style", "auto"))
    except Exception as e:
        print(f"logo unusable ({path.name}): {e} — using the dealership name as text instead")
        return None
    if dealer.get("logo_with_name"):  # a bare manufacturer badge: set the dealership name beside it
        mark_h = 120
        img = img.resize((max(1, round(img.width * mark_h / img.height)), mark_h), Image.LANCZOS)
        f = font(64, "demi")
        text_w = round(f.getlength(dealer["name"]))
        lockup = Image.new("RGBA", (img.width + 36 + text_w, mark_h), (0, 0, 0, 0))
        lockup.alpha_composite(img, (0, 0))
        ImageDraw.Draw(lockup).text((img.width + 36, mark_h // 2), dealer["name"], font=f, fill=WHITE, anchor="lm")
        img = lockup
    scale = min(box[0] / img.width, box[1] / img.height)
    return img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.LANCZOS)


def paste_logo(canvas, logo, y):
    """Centered logo with a soft shadow so it holds up on bright footage."""
    x = (W - logo.width) // 2
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    black = Image.new("RGBA", logo.size, (0, 0, 0, 255))
    black.putalpha(logo.getchannel("A").point(lambda a: a * 190 // 255))
    shadow.paste(black, (x, y + 3))
    canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(9)))
    canvas.alpha_composite(logo, (x, y))


def wordmark(dealer):
    """Two short lines of text standing in for a logo: 'WINN KIA' / 'OF FREMONT'."""
    if dealer.get("wordmark"):
        return dealer["wordmark"]
    name = dealer["name"].upper()
    head, sep, tail = name.partition(" OF ")
    return [head, "OF " + tail] if sep else [name, ""]


def render(style, dealer, vehicle, copy, tmp):
    """Write overlay PNGs; return [(path, fade_in_at or None, fade_out_at or None)]."""
    layers = []
    fill = lambda t: t.format(vehicle=vehicle, VEHICLE=vehicle.upper())

    # Persistent header, kept below the Reels/TikTok top UI zone.
    img = gradient(150, 0, 0, 520)
    header = load_logo(dealer, (520, 104))
    if header:
        paste_logo(img, header, 228 + (104 - header.height) // 2)
    else:
        top, sub = wordmark(dealer)
        lines = [(top, fit(top, 58, "bold", 14), 232, WHITE, 14)]
        if sub:
            lines.append((sub, fit(sub, 26, "demi", 12), 312, SOFT, 12))
        img = Image.alpha_composite(img, text_layer(lines))
    img.save(tmp / "brand.png")
    layers.append((tmp / "brand.png", 0.2, None))

    # Captions, kept above the bottom UI zone. The first one is the hook: bigger, heavier,
    # and on screen from frame 0 with no fade-in, because the first second decides the view.
    base = gradient(0, 185, 1100, H)
    wording = copy.get("captions") or [c["lines"] for c in style["captions"]]
    for i, (cap, lines_in) in enumerate(zip(style["captions"], wording)):
        texts = [fill(t) for t in lines_in]
        hook = i == 0
        size, weight, step = (92, "heavy", 108) if hook else (64, "demi", 84)
        y0 = (1370 if hook else 1400) - (len(texts) - 1) * step // 2
        lines = [(t, fit(t, size, weight), y0 + j * step, WHITE, 0) for j, t in enumerate(texts)]
        p = tmp / f"cap{i}.png"
        Image.alpha_composite(base, text_layer(lines)).save(p)
        layers.append((p, None if hook else cap["start"], cap["end"]))

    # End card: kicker, headline, dealer logo (or name), address.
    end = style["end_card"]
    kicker = fill(end["kicker"])
    head = [fill(t) for t in (copy.get("headline") or end["headline"])]
    y = 1262 - (len(head) - 2) * 84
    lines = [(kicker, fit(kicker, 34, "demi", 8), y - 62, SOFT, 8)]
    lines += [(t, fit(t, 68, "demi"), y + j * 84, WHITE, 0) for j, t in enumerate(head)]
    address = dealer.get("address", "")
    if address:
        lines.append((address, fit(address, 36, "medium"), 1562, SOFT, 0))
    logo = load_logo(dealer, (700, 84))
    if not logo:
        lines.append((dealer["name"], fit(dealer["name"], 44, "bold"), 1484, WHITE, 0))
    img = Image.alpha_composite(gradient(0, 225, 950, H), text_layer(lines))
    ImageDraw.Draw(img).line([(W / 2 - 60, 1448), (W / 2 + 60, 1448)], fill=SOFT, width=2)
    if logo:
        paste_logo(img, logo, 1466 + (84 - logo.height) // 2)
    img.save(tmp / "end.png")
    layers.append((tmp / "end.png", end["start"], None))
    return layers


def preview(dealer, out):
    """Still image of the header + hook and the end card, for checking a new dealer profile."""
    style = json.loads((SKILL / "styles" / "sky-drop.json").read_text())
    with tempfile.TemporaryDirectory() as d:
        layers = {p.name: Image.open(p).convert("RGBA")
                  for p, _, _ in render(style, dealer, "2026 Sample Car", {}, Path(d))}
    panels = []
    for top, bottom, names in (((176, 196, 214), (120, 126, 112), ("brand.png", "cap0.png")),
                               ((70, 80, 96), (28, 30, 34), ("brand.png", "end.png"))):
        bg = Image.new("RGBA", (W, H))
        for y in range(H):  # a bright "sky" frame and a dark frame, the two extremes of real footage
            t = y / (H - 1)
            ImageDraw.Draw(bg).line([(0, y), (W, y)],
                                    fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)) + (255,))
        for n in names:
            bg = Image.alpha_composite(bg, layers[n])
        panels.append(bg.resize((W // 2, H // 2)))
    sheet = Image.new("RGB", (W + 20, H // 2), (255, 255, 255))
    sheet.paste(panels[0], (0, 0))
    sheet.paste(panels[1], (W // 2 + 20, 0))
    sheet.save(out, quality=90)


def probe(src, entries, stream=None):
    cmd = ["ffprobe", "-v", "error"] + (["-select_streams", stream] if stream else [])
    return subprocess.check_output(cmd + ["-show_entries", entries, "-of", "csv=p=0", src]).decode().strip()


def compose(src, out, layers, music):
    dur = float(probe(src, "format=duration"))
    has_audio = bool(probe(src, "stream=index", "a"))
    cmd = ["ffmpeg", "-loglevel", "error", "-y", "-i", src]
    # Scale first so drafts and 720p clips get the same overlay layout as 1080p ones.
    chain, last = [f"[0:v]scale={W}:{H}:flags=lanczos[base]"], "base"
    for i, (png, start, stop) in enumerate(layers, 1):
        cmd += ["-loop", "1", "-t", f"{dur + 0.1:.2f}", "-i", str(png)]
        f = f"[{i}:v]format=rgba"
        if start is not None:
            f += f",fade=t=in:st={start}:d=0.4:alpha=1"
        if stop is not None:
            f += f",fade=t=out:st={stop}:d=0.4:alpha=1"
        chain += [f + f"[o{i}]", f"[{last}][o{i}]overlay[v{i}]"]
        last = f"v{i}"
    chain.append(f"[{last}]format=yuv420p[v]")

    audio = ["-map", "0:a?", "-c:a", "copy"]
    if music:
        m = len(layers) + 1
        cmd += ["-stream_loop", "-1", "-i", str(music)]
        bed = f"[{m}:a]atrim=0:{dur:.2f},afade=t=out:st={dur - 0.8:.2f}:d=0.8"
        if has_audio:  # keep the clip's own sound effects on top of the music bed
            chain += [bed + ",volume=0.75[bed]", "[0:a]volume=1.0[sfx]",
                      "[sfx][bed]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[a]"]
        else:
            chain.append(bed + "[a]")
        audio = ["-map", "[a]", "-c:a", "aac", "-b:a", "192k"]

    cmd += ["-filter_complex", ";".join(chain), "-map", "[v]", *audio,
            "-c:v", "libx264", "-crf", "17", "-preset", "slow",
            "-t", f"{dur:.2f}", "-movflags", "+faststart", out]
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--style", required=True, help="path to a styles/*.json file")
    ap.add_argument("--vehicle", required=True, help='e.g. "2026 Honda CR-V"')
    ap.add_argument("--out", required=True)
    ap.add_argument("--copy", help="per-car captions/headline JSON (overrides the style's wording)")
    ap.add_argument("--music", help="music bed file; default is music/<style>.m4a; 'none' to skip")
    ap.add_argument("--dealer", help="dealer profile slug; default is the one set up as default")
    a = ap.parse_args()
    style = json.loads(Path(a.style).read_text())
    dealer = load_dealer(a.dealer)
    copy = json.loads(Path(a.copy).read_text()) if a.copy else {}
    music = None
    if a.music != "none":
        music = Path(a.music) if a.music else SKILL / "music" / f"{style['name']}.m4a"
        music = music if music.exists() else None
    with tempfile.TemporaryDirectory() as d:
        compose(a.input, a.out, render(style, dealer, a.vehicle, copy, Path(d)), music)
    print(a.out)
