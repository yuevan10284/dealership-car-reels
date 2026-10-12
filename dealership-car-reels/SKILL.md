---
name: dealership-car-reels
description: Turn any vehicle on a car dealership's lot into three branded 10-second vertical reels (1080x1920) — "heartfelt" (warm family story), "sky-drop" (the car falls from the sky and lands), and "exploded" (the car bursts into floating parts and reassembles). Works for any dealership - a one-time setup reads the dealer's name, address and logo from its website. Pulls the real listing photos, generates each clip with Higgsfield Seedance 2.5 using those photos as references, then adds the dealer's logo, a hook, captions written for that car, a music bed and an end card with the address. Use this whenever the user wants a reel, video or social content for a car, truck or SUV at a dealership, names a model, stock number, VIN or listing URL, says "set up car reels for <website>", asks to add or switch dealerships, or follows up to change captions, re-run a style, or redo a clip.
---

# Dealership Car Reels

One car in, three finished reels out, for any dealership. Each reel is a 10 s, 9:16 Higgsfield
clip of the exact car from the listing photos, finished with:

- the dealership's logo at the top and on the end card
- a big hook line on screen from the very first frame
- two more captions and an end-card headline, all written for that specific car
- a music bed for the style, mixed under the clip's own sound effects
- the dealership's address

| Style | What happens | Tone |
|---|---|---|
| `heartfelt` | A child sprints through the grass to the car, parent catches up, cabin, drive-off into the sunset, set in the dealer's own local landscape | Warm, family |
| `sky-drop` | The car is already falling in frame one, slams onto a salt flat in a dust shockwave, drives off | Punchy, fun |
| `exploded` | Studio shot: the car snaps apart into floating parts, hangs, clicks back together | Premium, precise |

Default is all three. If the user names one style, make only that one.

Everything in this folder is generic: `scripts/`, `styles/*.json` (video prompt, default captions,
timings), `music/` (one bed per style). Everything about a particular dealership lives outside it,
in `~/.car-reels/dealers/<slug>/` (`dealer.json`, `logo.png`), so updating the skill never touches it.

```bash
S=~/.claude/skills/dealership-car-reels/scripts
```

## Start here, every time

```bash
python3 $S/check_setup.py
```

It lists what is ready and prints the fix for anything missing. Install missing tools yourself
(`brew install ffmpeg`, `pip3 install pillow`, `npm i -g @higgsfield/cli`). Two things only the
user can do: `higgsfield auth login` (it opens their browser — ask them to type `! higgsfield auth
login`), and buying Higgsfield credits. If no workspace is selected, run `higgsfield workspace
list` and `higgsfield workspace set <id>`.

If it reports no dealership profile, do the first-time setup below before anything else.

## First-time setup for a dealership

The goal is that the user gives you one thing — their website — and confirms once. Do not send
them a questionnaire.

**1. Run the setup on their website.**

```bash
python3 $S/setup_dealer.py https://www.exampletoyota.com
```

It reads the name, address and logo from the site and writes the profile, a `preview.jpg`
(how the branding will look on a bright frame and on the end card) and `logo-candidates.jpg`
(every logo image it found, numbered, on light and dark).

**2. If the site refuses the script** (many dealer sites sit behind bot protection and answer 403
or an empty "Loading…" page), get the same three facts another way, in this order:

- With a browser tool: open the homepage and read them from the page. This snippet returns the
  name, address and logo image URLs:
  ```js
  (() => { const ld = [...document.querySelectorAll('script[type="application/ld+json"]')].map(s => { try { return JSON.parse(s.textContent) } catch (e) { return null } }).flat().filter(Boolean);
    const biz = ld.flatMap(n => n['@graph'] || [n]).find(n => /AutoDealer|LocalBusiness|Organization/.test([].concat(n['@type']).join())) || {}; const a = biz.address || {};
    return JSON.stringify({ title: document.title, name: biz.name, address: [a.streetAddress, a.addressLocality, [a.addressRegion, a.postalCode].filter(Boolean).join(' ')].filter(Boolean).join(', '),
      logos: [...new Set([...document.images].filter(i => /logo/i.test(i.outerHTML) && i.naturalWidth > 60).map(i => i.currentSrc.split('?')[0]))].slice(0, 8) }, null, 1) })()
  ```
- Without one: a web search for the dealership gives the name and street address.
- Then pass what you found: `setup_dealer.py <site> --name "…" --address "…" --city "…" --logo <url>`.
- If the logo cannot be downloaded, ask the user to drop a logo file anywhere and give you the
  path (`--logo ~/Downloads/logo.png`), or go without one (`--logo none`): the dealership name is
  then set in clean type, which looks fine.

If a page shows a CAPTCHA or a "verify you are human" screen, do not try to get past it. Use the
other routes above or ask the user.

**3. Look at `preview.jpg` and `logo-candidates.jpg`, and fix what is off.**

- The logo should be the one that names the dealership. Sites often list the manufacturer badge,
  a parent auto group and the website vendor too. Pick by number: `--dealer <slug> --logo 2`.
- If the only good image is a bare manufacturer badge, add the name beside it:
  `--logo 2 --logo-with-name yes`.
- If the logo is hard to read on either background, force a treatment with `--logo-style`:
  `white` (recolour to white), `plate-white` / `plate-dark` (put it on a rounded plate), `asis`.
- If the address is long, shorten it to one line the way the dealership writes it.

**4. Set the local scenery** for the heartfelt style: one phrase describing a recognisable, real
kind of landscape near the dealership, based on its city. Keep it generic enough to be true
(a kind of place, not a named landmark):

```bash
python3 $S/setup_dealer.py --dealer example-toyota \
  --scenery "a Hill Country overlook with live oaks and limestone bluffs"
```

**5. Confirm once.** Show the user the preview image and the name and address in one short
message, and ask if it is right. Apply any correction with the same flags. That is the whole
setup; from then on they just ask for cars.

More than one dealership (an auto group): run the setup once per website. `--list` shows the
profiles, `--use <slug>` changes the default, and every script takes `--dealer <slug>`. When the
user names a store, pass its slug; when it is ambiguous, ask which store.

## Making reels for a car

Check the Higgsfield balance (shown by `check_setup.py`), tell the user the total for this run in
one line, and go ahead unless the balance is too low. Don't ask again per clip. Re-rolls cost the
same as a first take, so say so before redoing one.

### Cost (Seedance 2.5, 10 s, 9:16, with reference photos; checked October 2026)

| Setting | Credits per clip | Full set of 3 |
|---|---|---|
| 1080p (default) | 120 | 360 |
| 720p | 70 | 210 |
| `--draft true` (comes out 480p) | 30 | 90 |

Photo fetching, captions, logos, music and branding are free. Prices change, so confirm with
`higgsfield generate cost seedance_2_5 <same flags>` (free) before quoting a number. Use the 1080p
default unless the user asks for cheaper; 720p is the sensible saving for phone-only posting.

Drafts are for testing a changed prompt or a new style cheaply. A draft is a separate take: the
1080p version will not be the same footage, so don't promise "this exact clip, sharper".

### 1. Find the car and pull its photos

Work in `~/Desktop/car-reels/<dealer-slug>/<stock or VIN>/` unless the user names a folder.

```bash
python3 $S/fetch_listing.py --find "cr-v hybrid" --condition new     # listing URLs from the dealer's sitemap
python3 $S/fetch_listing.py "<listing-url>" --out <folder>
```

This writes `photos/01.jpg…`, `listing.json` (vehicle, colour, VIN, stock) and `contact-sheet.jpg`.
If the user gave only a model, pick a listing with real lot photos and say which one you used.

Dealer websites differ, so have the fallbacks ready. Use the first one that works:

1. **Listing URL** — as above. Works when the site serves its pages to scripts.
2. **Browser** — if the fetch says the site refused it or found too few photos, open the listing
   with a browser tool, open the photo gallery, and collect the image URLs:
   ```js
   [...new Set([...document.images].filter(i => i.naturalWidth >= 500 && i.naturalWidth / i.naturalHeight > 1).map(i => i.currentSrc))].join('\n')
   ```
   Save them to a text file, one per line, then:
   `fetch_listing.py --image-urls urls.txt --vehicle "2026 Honda CR-V" --vin … --stock … --color "…" <listing-url> --out <folder>`
   Read the year, make, model, colour, VIN and stock number off the page for those flags.
3. **Photos from the user** — ask them to save or export the car's photos into a folder (their
   inventory tool or phone photos are fine), then
   `fetch_listing.py --photos <that folder> --vehicle "2026 Honda CR-V" --out <folder>`.

Again: never try to get past a CAPTCHA or bot check. Go to the next fallback.

### 2. Look at the photos

Read `contact-sheet.jpg`. Two things come out of this:

- **Reference set** — pick about six photos: front three-quarter, side, rear three-quarter, straight
  rear, straight front, and one interior. Skip close-ups of switches, window stickers and anything
  with a watermark banner across the car. If the listing only has studio or stock images (plain
  white background), they still work as references; tell the user the car has no lot photos yet.
- **The look** — one clause describing what makes this exact car recognisable: paint colour, grille,
  wheels, roof rails, lights, trim details. Describe only what the photos show. This goes into every
  prompt and is the main thing keeping the generated car faithful.

### 3. Write the captions for this car

Every car gets its own wording; identical captions on every post make the feed look automated.
For each style, write `<style>-copy.json` in the car's folder:

```json
{
  "captions": [
    ["DON'T BLINK."],
    ["The new CR-V Hybrid", "just landed."],
    ["And it's parked", "in Austin."]
  ],
  "headline": ["On the lot now.", "Come take a look."]
}
```

Three captions (the first is the hook) and a two-line end-card headline. Lines must be short: about
22 characters each, two lines at most per caption. The style's own captions in `styles/*.json` show
the intended rhythm and are the fallback if no copy file is passed.

**The hook is the line that matters.** It is on screen from frame zero, in large type, while the
most dramatic moment of the clip plays. Make it earn the next second:

- Six words or fewer. A question, a dare or an unfinished thought: "Who's riding with you?",
  "DON'T BLINK.", "WHAT'S INSIDE A TACOMA?"
- It should make sense with the first second of that style's footage (a child running, a car
  falling, a car bursting apart).
- Not the model name alone, not "Introducing…", not "Check this out".

For the rest, write the way someone at this dealership would talk about this particular car. Think
about who buys it — a three-row SUV, a work truck, a commuter EV and a first car each get different
lines — and name the life it fits rather than its features. Use the dealership's city or region
(from the profile) where it comes naturally. Follow the on-screen rules at the end of this file: no
prices, no specs, no claims you have not verified.

### 4. Generate the clips

Build each prompt from its style file, then generate. Run the styles in parallel as background
commands; each takes a few minutes.

```bash
P=$(python3 $S/prompt.py sky-drop --vehicle "blue 2026 Honda CR-V Sport Touring Hybrid" \
      --look "canyon river blue paint, gloss black honeycomb grille, black 19-inch wheels, black roof rails")
higgsfield generate create seedance_2_5 --prompt "$P" --mode omni_reference \
  --image photos/01.jpg --image photos/02.jpg --image photos/03.jpg \
  --image photos/04.jpg --image photos/08.jpg --image photos/09.jpg \
  --duration 10 --resolution 1080p --aspect_ratio 9:16 --wait --wait-timeout 20m
```

The command prints the result URL. Download it as `<style>-raw.mp4`. `prompt.py` fills in the
dealer's scenery for the heartfelt style (`--scenery "…"` overrides it for one clip).

Why the prompts are written the way they are, so edits keep what works:

- **Action in frame one.** Each prompt opens mid-action with no establishing shot, because viewers
  decide in the first second.
- **No on-screen text.** The branding step adds all text; text the video model draws comes out garbled.
- **Sound effects only, no music.** The music bed is added afterwards, and two music tracks clash.
- **Car in the upper two thirds.** The captions and end card sit in the lower third.
- **10 seconds.** The caption timings in each style file assume it.

### 5. Check each raw clip

Pull a strip of frames, including the first half second, and look at it before branding:

```bash
ffmpeg -loglevel error -y -i sky-drop-raw.mp4 \
  -vf "select='eq(n,2)+eq(n,30)+eq(n,60)+eq(n,110)+eq(n,160)+eq(n,200)+eq(n,235)',scale=270:480,tile=7x1" \
  -frames:v 1 -fps_mode vfr sky-drop-frames.jpg
```

Check that the first frame already has the action in it, that the car matches the photos (colour,
wheels, grille, badge) and stays in frame, and that nothing is broken (melted wheels, wrong badge,
gibberish text, extra doors). `exploded` is the most likely to come out wrong. If a clip fails, tell
the user what is wrong and what a re-roll costs rather than quietly spending more credits.

If the key moment lands at a different time than the captions expect (for example the car touches
down at 2.5 s instead of 1.5 s), copy the style JSON into the car's folder, shift that caption's
`start` / `end`, and pass the copy to `--style`.

### 6. Add the logo, captions and music

```bash
python3 $S/brand_video.py --input sky-drop-raw.mp4 --style $S/../styles/sky-drop.json \
  --vehicle "2026 Honda CR-V" --copy sky-drop-copy.json --out sky-drop-final.mp4
```

- `--vehicle` is the short public name (year, make, model) for the end card.
- `--copy` is the per-car wording from step 3.
- `--dealer <slug>` picks a dealership other than the default.
- Music defaults to `music/<style>.m4a`, mixed under the clip's sound effects. Pass `--music <file>`
  to use another track or `--music none` to keep only the clip's own audio.
- Output is always 1080x1920, whatever resolution the clip was generated at.

Look at a few frames of the final file to confirm the logo and text are readable against the
footage, then open the finished videos for the user.

### 7. Report

Give the paths to the final files, the dealership, the stock number and listing used, credits
spent, the captions you wrote, and anything that looked off. Note that the people and scenery are
AI-generated and the clips have been checked as still frames, not watched with sound, unless you
did more.

## Rules for what goes on screen

These protect the dealership, so hold to them even when asked to move fast:

- **No prices, payments, APRs, rebates or "deal" wording by default.** Advertised prices carry
  disclosure requirements that differ by state. If the user wants a price on screen, take it from
  the live listing the same day, include the stock number or VIN, and tell the user it needs the
  dealership's own disclosure text before posting.
- **No spec or feature claims** (range, MPG, towing, seating, warranty) unless the user supplies
  the figure or you read it from the live listing or the manufacturer's site in this session.
- **"On the lot" / "just landed" lines** are only true while the car is in inventory, and not true
  for a car still in transit. The listing was live when you fetched it; say so, and mention it will
  go stale once the car sells.
- **The exploded view is an illustration.** The generated parts are not accurate engineering, so
  never label parts or use the clip to explain how the car works.
- **Logos and names come from the profile**, not from memory. Only make reels for a dealership the
  user works for or is authorised to promote; manufacturer logos have their own usage rules, which
  are the dealership's to follow.

## Changing the defaults

- **Music:** replace `music/<style>.m4a` with any 10 s or longer track. The current beds were
  generated with `higgsfield generate create sonilo_music --prompt "…" --duration 12 --wait`
  (under 1 credit each).
- **Dealer details:** re-run `setup_dealer.py --dealer <slug>` with the flag to change, or edit
  `~/.car-reels/dealers/<slug>/dealer.json`. A `"wordmark": ["LINE ONE", "LINE TWO"]` entry sets the
  text used when there is no logo.
- **A new style:** copy a `styles/*.json`, rewrite `prompt`, `captions` and `end_card`, add a music
  bed with the same name, and test it with `--draft true` before spending on 1080p. A prompt may
  use `{vehicle}`, `{look}` and `{scenery}`.

## Notes

- Captions use Avenir Next on macOS and fall back to Helvetica, DejaVu or Arial elsewhere. Text is
  drawn with Pillow and overlaid, because many ffmpeg builds lack the `drawtext` filter.
- Text stays out of the top ~220 px and bottom ~330 px so Reels and TikTok UI doesn't cover it.
- Tested on macOS. Linux should work (SVG logos need `rsvg-convert`); Windows is untested.
