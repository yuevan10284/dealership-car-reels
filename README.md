# Dealership Car Reels

A Claude skill that turns any vehicle on your lot into three branded 10-second vertical reels
(1080x1920), ready for Instagram Reels, TikTok or YouTube Shorts. It works for any dealership:
you give it your website once, and it picks up your name, address and logo.

| Style | What happens | Tone |
|---|---|---|
| `heartfelt` | A child sprints through the grass to the car, parent catches up, cabin, drive-off into the sunset, in scenery that looks like your area | Warm, family |
| `sky-drop` | The car is already falling in frame one, slams onto a salt flat in a dust shockwave, drives off | Punchy, fun |
| `exploded` | Studio shot: the car snaps apart into floating parts, then clicks back together | Premium, precise |

For each car, the skill:

1. Pulls the real listing photos and details (model, colour, VIN, stock number) from your website.
2. Generates each clip with Higgsfield (Seedance 2.5), using the photos as references so the car matches.
3. Writes a hook and captions for that specific car, so no two posts read the same.
4. Adds your logo, a music bed for the style, and an end card with your address.

## Get started (about 5 minutes)

You need a Mac, [Claude Code](https://claude.com/claude-code), and a
[Higgsfield](https://higgsfield.ai) account with credits.

**1. Install.** Paste this into Terminal:

```bash
git clone https://github.com/yuevan10284/dealership-car-reels.git ~/dealership-car-reels && ~/dealership-car-reels/install.sh
```

The installer links the skill into Claude Code and installs what is missing (ffmpeg, Pillow, the
Higgsfield CLI). It uses Homebrew and npm if you have them, and tells you what to install if not.

**2. Sign in to Higgsfield.** This opens a browser tab:

```bash
higgsfield auth login
```

**3. Tell Claude your website.** Open Claude Code (restart it if it was already open) and say:

```
set up car reels for www.yourdealership.com
```

Claude reads your name, address and logo from the site, shows you a preview of the branding, and
asks you to confirm. That is the whole setup.

**4. Ask for a car.**

```
make the three reels for the 2026 CR-V Hybrid
make a sky-drop reel for stock H4821
do the reels for https://www.yourdealership.com/new/…<listing page>
```

Claude tells you the credit cost up front, generates the clips (a few minutes each), checks them,
and saves everything to `~/Desktop/car-reels/<dealership>/<stock>/`.

Follow-ups work too: "change the last caption to …", "redo the exploded one", "just the heartfelt
style for this car".

## If your website blocks the setup

Many dealership websites sit behind bot protection and refuse automated requests. In testing,
only 2 of 7 dealer sites could be read directly. When yours can't, Claude falls back in this order:

1. It opens your site in your browser (with the Claude in Chrome extension, if you have it) and
   reads the same details from the page.
2. It asks you for what it couldn't get: a logo file, your address, or a folder of the car's photos.

Photos you export from your inventory tool or take on your phone work as well as the website's:
save them in a folder and say "make the reels from the photos in ~/Downloads/crv, it's a 2026
Honda CR-V".

## More than one store

Run the setup once per website ("set up car reels for www.oursecondstore.com"). Then name the
store when you ask: "make the reels for the Tacoma at the Austin store".

## Cost

Each person spends their own Higgsfield credits. Quotes from October 2026, per 10-second clip:

| Setting | Credits per clip | Full set of 3 |
|---|---|---|
| 1080p (default) | 120 | 360 |
| 720p | 70 | 210 |
| 480p or draft | 30 | 90 |

On the Plus plan ($49/month for 1,000 credits) that is roughly $5 to $6 per 1080p video, or about
$15 to $18 per car. A redo costs the same as a first take. Photo fetching, captions, logos, music
and branding are free. Ask Claude for "720p" to cut the cost by about 40%.

## Updating

The skill does not update itself. To get the latest version:

```bash
cd ~/dealership-car-reels && git pull
```

Your dealership profile is stored separately in `~/.car-reels/`, so updates never overwrite it.

## Customizing

Just ask Claude ("use this logo instead", "shorten the address", "put the logo on a white plate").
If you'd rather edit files:

| File | What it controls |
|---|---|
| `~/.car-reels/dealers/<your-store>/dealer.json` | Name, address, local scenery, logo treatment |
| `~/.car-reels/dealers/<your-store>/logo.png` | The logo used in the videos |
| `styles/heartfelt.json`, `styles/sky-drop.json`, `styles/exploded.json` | The video prompt, the fallback captions, and when each caption appears |
| `music/<style>.m4a` | The music bed for each style; replace with any track of 10 seconds or more |

To add a fourth style, copy one of the `styles/*.json` files, rewrite its `prompt`, `captions`
and `end_card`, add a music bed with the same name, and ask Claude for that style by name. Ask for
a "draft" first: it costs 30 credits instead of 120.

## Running the scripts yourself

Claude normally runs these for you, but they work on their own:

```bash
S=~/.claude/skills/dealership-car-reels/scripts

python3 $S/check_setup.py                                   # what is ready, what is missing
python3 $S/setup_dealer.py https://www.yourdealership.com   # create your profile
python3 $S/setup_dealer.py --dealer your-store --logo ~/Downloads/logo.png --address "1 Main St, Austin, TX 78701"

python3 $S/fetch_listing.py --find "cr-v hybrid"            # listing pages from your sitemap
python3 $S/fetch_listing.py "<listing-url>" --out ~/Desktop/car-reels/your-store/H4821
python3 $S/fetch_listing.py --photos ~/Downloads/crv --vehicle "2026 Honda CR-V" --out ~/Desktop/car-reels/your-store/H4821

python3 $S/prompt.py sky-drop --vehicle "blue 2026 Honda CR-V Sport Touring" \
  --look "canyon river blue paint, black honeycomb grille, black 19-inch wheels"

python3 $S/brand_video.py --input sky-drop-raw.mp4 --style $S/../styles/sky-drop.json \
  --vehicle "2026 Honda CR-V" --copy sky-drop-copy.json --out sky-drop-final.mp4
```

## What it won't put on screen

- **No prices, payments, rebates or "deal" wording** by default. Advertised prices need your own
  disclosure text, and the rules differ by state.
- **No spec or feature claims** (range, MPG, towing, warranty) unless you supply the figure.
- **"On the lot" / "just landed" lines** are only true while that car is in inventory.
- The people and scenery are AI-generated, and the exploded view is an illustration, not accurate
  engineering.

Review every video before posting. Use it only for a dealership you work for or are authorised to
promote; manufacturer logos come with the manufacturer's own usage rules. See
`dealership-car-reels/SKILL.md` for the full rules Claude follows.

## Troubleshooting

- **Anything missing** — run `python3 ~/.claude/skills/dealership-car-reels/scripts/check_setup.py`; it prints the fix.
- **"No workspace selected"** — run `higgsfield workspace list`, then `higgsfield workspace set <id>`.
- **"Session expired" / "Not authenticated"** — run `higgsfield auth login` again.
- **No photos found** — the site blocked the request or loads its gallery differently; give Claude a folder of photos instead.
- **Wrong logo** — say "show me the logo options" and pick one, or give Claude a logo file.
- **The car looks wrong in a clip** — ask Claude to redo that style; it costs the same as the first take.

---

Not affiliated with or endorsed by any vehicle manufacturer, dealership or Higgsfield. Logos belong
to their owners.
