# Tinkerbelle, Part 2 build: handoff notes

CS 5424 Lab 1 Part 2 (Giorgi Samushia, Shuning Liu). A wizard-of-oz light: one browser page is
the *wizard* (keyboard), every other page on the same server is a *light* (the projector). The
light draws a field of about 1400 painted flowers on a canvas. People approach, touch, swipe and
flick; the wizard presses keys to match. Touched flowers burst into petals that drift, bounce off
other people's petals, and fly home. Gestures play harp chords over a drone pad.

Server: `python tinker.py` (Flask + Socket.IO, port 5001; venv in
`~/studies/cs5424-idd/repos/tinkerbelle-newnewUI/.venv`). Light: `http://<ip>:5001/?mode=blobs&season=cherry`,
click Tinkerbelle once (fullscreen + audio unlock). Wizard: `http://<ip>:5001/`, click Wizard.

## File map

- `static/index.js`   everything: layout, lifecycle, gestures, petals, tint buckets, sweeps, sound, captions, record mode
- `static/solo.js`    the take script (`SOLO_SCRIPT`), the captions (`CAPTIONS`), P/Esc to run/cancel
- `static/petals/`    artwork from the Claude Design sheet: `<species>-{a,b,c}.svg` and `<species>-centre.svg`,
                      greyscale + alpha, 256 px, petal up, base at (128,250). `gen-petals.js` regenerates them.
- `static/sounds/`    optional `ambient.mp3`, `tap.mp3`, `swipe.mp3` (any of mp3/ogg/wav/m4a); the light lists the
                      folder via `/sounds` at load. Missing files fall back to the synth. B toggles files/synth.
- `templates/index.html`  both pages; colour keys are `<tinker-button>` elements; wizard legend and preview
- `tinker.py`         relays every socket event to all pages; `/sounds` lists the sound folder

## Light URL parameters (defaults)

Field: `count` 1400, `cover` 0.85, `seed` 7, `season` cherry|summer|autumn, `tone` season base,
`exposure` 1.6, `gather` 12 s, `wave` 0.3, `bump` 0.7, `dir` right, `point` 50,50, `fade` 12 s,
`seasonfade` 20 s, `fps` 0 (overlay off), `debug` 0.
Look: `look` lights|paper (default lights) sets `blend edge pool grad vein halo band wide fog fogsize centre`;
lights = additive 2 0 paletip 0 0 70 110 0 1 lit; paper = layered 2 0.3 darkbase 0.5 0.5 45 70 0 1.5 matte.
Any of those names overrides on its own. `sat` lo,hi and `full`, `pale` set the saturation classes.
Sound: `sfx` 0.35, `amb` 0.6, `reverb` 0.5. Captions: `captions=off`. Record: `record=1`, `end` seconds.
Wizard URL: `point`, `point2` (start values; clicking the preview sets them), `aspect` w:h.

## Wizard keys

- Colours: 1 2 (emerald, violet, 6 s) · 7 8 3 4 (bud green, soft pink, magenta, gold) · 5 6 (teal, blue) ·
  G whole-field warm · K resting violet · 0 black. All fade over `fade` s as a sweep (below).
- Gestures at the touch point: Space tap · arrows swipe · Enter flick · D drag · H hold · A approach · L leave.
  Shift + any = at the second point. Tap/swipe kill within 11% of the wall, flick along a 45% line.
- S next season (sweep over `seasonfade`) · T age the field 40 s over 3 s · R reset to full bloom over 2 s ·
  Z pause/resume aging · M/N pad on/off · B files/synth · [ ] exposure ±0.1 · P/Esc run/cancel the take.
- Keys match on `event.code`; Shift only selects the second point. Colour fades run on the light, so a
  background wizard tab cannot stall them.

## How the field works

- Layout: seeded value noise, ridged so gaps are thin channels; `cover` sets the covered fraction.
  A floor of tiny dim flowers (10%) goes everywhere. Sizes: most 3-5% of wall height, 6% large, 15% tiny.
- Each flower rolls species (cherry, daisy, mum, star; mix per season), one of 3 shared petal
  arrangements, rotation, squash (20%), size, lifespan (100-200 s on the field clock), a hue offset
  (the clump's lean from a second noise field, ±6°), a saturation class (pale/mid/full) and a lightness jitter.
- Life: bud 10 s, bloom, wither 22 s, then a new flower buds at once. Touched flowers instead scatter
  their real petals; each petal leaves for home between 0.6 and 1.6 × `gather` and flies 4-7 s; the
  flower crossfades back in as petals land. Petals only collide with petals from other gestures,
  never in their first 1.5 s. A flying petal that crosses a living flower makes it flare, and the
  flare hops to two neighbours per 150 ms keeping `wave` of its strength.
- Colour sweeps: every flower carries its own HCL tone. A key picks a random origin; each flower starts
  after a delay by distance (spread over 60% of `fade`) and runs its own slow-in slow-out fade in the rest.

## Tint buckets (the fade-performance fix)

A flower's colour is quantized (hue ≈ band/12, chroma 25, lightness 20) and every flower with the same
(colour, species, arrangement, blur, resolution) draws one shared tinted canvas, taken from pools
made at startup (1400 × 64 px, 400 × 128, 100 × 256, 320 halos) and recycled when unused. Retints are
queued and capped at 40 per frame; a flower keeps drawing its last clean bucket until its new one is
ready, and the overlay prints `tints`, `retint/s`, `q` and `overflow` (should stay 0).

## The two caches

1. `shapeCache`: greyscale composed flowers per (species, arrangement, blur, resolution), built from
   the petal art on first use, squash applied at draw time. 2. Tint buckets above: shape × colour.
Centres are cached once per species (`buildCentreCache`) and composited at draw time. Petal art is
rasterized at 256 and 64 px and cropped to its alpha bounds; the nearer raster is used per petal.

## Sound

Pad: A2 root ×2 detuned, E3 triangle, B3 sine, A3 triangle → lowpass 1.2 kHz → breath swell (0.1 Hz)
+ four LFOs (0.03/0.045/0.07/0.11 Hz on cutoff, detune, level, pan) → shared room. Harp: Karplus-Strong
rendered offline per pitch (lowpassed burst, 3 kHz loop filter, T60 3.5 s), A major pentatonic, broken
chords 60-90 ms apart rising for tap/swipe, falling for flick, root from x. Room: 5 s generated
impulse in a convolver, wet = `reverb`. All audio passes through `masterOut`, which record mode taps.

## The take and record mode

`SOLO_SCRIPT` in solo.js (ms, action): 0:00 reset + pad on · 0:20 approach 30,50 · 0:28 tap · 0:34 swipe
right · 0:40 leave · 1:15 approach 25,50 and 75,50 · 1:23 tap 25,50 then flick left from 75,50 at +0.5 s ·
1:35 leave · 2:05 summer · 2:30 end. `CAPTIONS` sits above it; captions draw on the canvas during a take
(2% wall height, 70% off-white, 5 s each). P on any page starts the take everywhere.
`record=1` on the light: all UI hidden, cursor off, canvas fixed at 0,0 sized to the window; one click →
3 s countdown → the take runs while `canvas.captureStream(60)` + the audio master record to a VP9/Opus
webm at 24 Mb/s; the take's end downloads `storyboard-demo.webm`. Convert with
`~/studies/cs5424-idd/labs/lab1/convert-take.sh ~/Downloads/storyboard-demo.webm` (pads to even size, h264+aac).

## Renders and test harness (studies repo, not this one)

`~/studies/cs5424-idd/labs/lab1/renders/` holds every 1x render from the build (look comparisons,
close-ups, sweeps, captions, record fit). `~/studies/cs5424-idd/labs/lab1/tools/` holds the headless
Chrome scripts (`lib.mjs` + one per check; see its README). Headless fps is software rendering: a floor.

## Not done yet

- No real take recorded; the Part 2 video, storyboard and README sections (remix, reflections) are unwritten.
- Petal-flower collisions still let one petal hit several flowers along its path; `wave` tames the spread.
- `grad`, `pool`, `vein` only affect the drawn fallback petals, not the artwork.
- The `mode=glow` and plain-colour lights still exist but get one whole-page fade, not the sweep.
- Sound is measured, not listened to, from this side. Cover proxy reads 0.79 for `cover=0.85`.
- Files in `static/sounds/` would bypass the shared reverb (HTMLAudio, not Web Audio).
