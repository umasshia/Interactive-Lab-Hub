# Part 2: what changed in the Tinkerbelle fork

Commits `c213cdc` through `5fa64b7` on `Fall2026` (Sep 7 and 8, 2026), after the Part 1 work ending at `f5d2eea` and the Part 2 prep commit `0af038f`. Details in `tinkerbelle/NOTES.md`.

Peer feedback items from the Prep section, referenced below:

- F1: would a first-time visitor know they can approach, tap, or swing
- F2: what happens if two people touch or flick in different places at the same time
- F3: how to detect the hand's position and gesture without a wizard
- F4: add sound or more actions
- F5: add an emotional or practical function
- Kept: the field keeps moving when nobody is interacting

## Interaction

- Tap, swipe and flick kill the flowers at the touch point; each flower's own petals detach with their position, angle, size and colour. (F4)
- Tap clears a hole 11% of the wall width; flick a line 12% long and 5% wide; sizes scale with the square root of 1400 over the flower count. (F4)
- Swipe is a swing: the hand travels 40% of the wall width from the point in 1.1 s, flowers in a 6% band burst as it passes, and their petals are thrown along the swing. (F4)
- Tap petals burst outward at 7 to 16% of the long edge per second plus 6% per second toward the wall centre; swing petals at 9 to 20% along the swing; flick petals downwind at 12 to 24%. (F2)
- Petals drift and tumble for a coast of 1.2 s, then fall at 1% per second and rock; motion integrates real elapsed time with a 50 ms cap. (none)
- Each petal leaves for home between 0.6 and 1.6 times `gather` (default 12 s), flies 4 to 7 s on an eased path, and the same flower crossfades back in as its petals land, with a flare when the last one lands. (none)
- Petals collide with petals from other gestures only, never in their first 1.5 s; contact at 0.25 of combined length, restitution 0.6, one resolution per pair per 250 ms, a flash on contact (`bump`). (F2)
- A flying petal that crosses a living flower makes it flare for about 1.5 s; the flare hops to two neighbours every 150 ms, keeping `wave` (default 0.3) of its strength. (F4)
- Approach is local: flowers within 20% of the wall width drift toward the point over 2 s, twinkle for 4 s, and warm toward rose; leave releases over 2 s. The Part 1 whole-field warm shift moved to G, the resting colour to K. (F1)
- Two touch points: every gesture, approach and leave can land at a second point with Shift, so two people at two places are two keypresses. (F2)
- Each flower slot lives on a field clock: bud 10 s, bloom, wither 22 s, then a new flower with a fresh species, size, shape and colour buds in the same slot; T ages the field 40 s, R resets to full bloom, Z pauses aging. (Kept)
- Drag carries flowers with the hand; hold gathers them toward it; both release without killing. (F4)

## Sound

- Tap, swipe and flick play a broken harp chord: three or four notes of A major pentatonic 60 to 90 ms apart, rising for tap and swipe, falling for flick, root chosen by the touch point's x across the wall. (F4)
- Harp notes are Karplus-Strong strings rendered offline per pitch, ringing about 3.5 s, so gestures a moment apart sound as a chord. (F2)
- Ambient bed: a synth pad (A2 root, fifth, ninth, four slow LFOs, a breath swell) or `static/sounds/ambient.mp3`, which is Pixabay's "Uplifting Pad Texture"; M and N switch it on and off. (F4)
- An ambient file is decoded at page load into a Web Audio buffer and looped through the audio master; if present it is the default source, and B switches to the synth. (none)
- Harp and synth pad pass through a shared 5 s convolution room (`reverb`); the file pad goes to the master dry. (none)
- Volumes: `sfx` 0.35, `amb` 0.6. (none)

## Look

- Petals and centres are SVG artwork from a Claude Design sheet: three petal drawings and one centre per species, greyscale with alpha, rasterized at 256 and 64 px and tinted per flower. (none)
- Four species: cherry (5 to 6 petals), daisy (18 to 22), chrysanthemum (24 to 32 over three rings), star (8 to 10); each season has its own species mix. (none)
- Field of 1400 flowers laid out by ridged value noise into drifts with thin dark channels, `cover` 0.85, plus a floor of tiny dim flowers everywhere; most flowers 3 to 5% of the wall height, 15% tiny, 6% large. (none)
- Three seasons, S key: cherry (pink, white, peach, magenta), summer (leaf green with pink, orange, gold), autumn (gold, rust, crimson, deep purple); each flower rolls a hue offset in a narrow band or one of the season's outlier hues, and a saturation class. (none)
- A season change sweeps across the field from a random origin over `seasonfade` 15 s, re-rolling each flower's palette as the sweep reaches it; colour keys sweep the same way over `fade` 12 s. (none)
- Two looks: `look=lights` (additive) and `look=paper` (layered with halos and matte centres); each drawing property overrides on the URL. (none)
- Exposure: a brightness multiplier on flower alpha and lightness, default 1.8, stepped by `[` and `]`. (none)
- Performance: one cached bitmap per living flower, shared greyscale shapes per species and arrangement, shared tinted canvases keyed by quantized colour from pools made at startup, at most 40 retints per frame. (none)

## Wizard

- The wizard page shows a preview rectangle of the wall in the light's aspect; clicking it sets the touch point, shift-clicking the second, both shown as dots; `point` and `point2` on the URL are start values. (F2)
- Gestures carry the wizard's touch point to every light page; a light without one falls back to its own `point`. (none)
- Keys match on the physical key code; Shift only selects the second point. (none)
- A key legend panel on the wizard page lists every key. (none)
- Colour fades run on the light pages from a target, duration and easing sent once, so a background wizard tab cannot stall them. (none)
- Sound source toggle B, pad on and off M and N, exposure `[` and `]`, season S, field T, R, Z, take P and Esc. (none)

## Tooling

- Record mode (`record=1`): all UI hidden, cursor off, canvas sized to the window; one click, a 3 s countdown, then the take runs while the canvas at 60 fps and the audio master record to a VP9/Opus webm at 24 Mb/s, downloaded as `storyboard-demo.webm` when the take ends. (none)
- Record mode waits up to 15 s for the ambient file to decode before the countdown. (none)
- Take script (`solo.js`): a timed list of actions run by P on any page, 3:20 long, covering both storyboards: one tap, two simultaneous taps, one swing, two simultaneous swings, with two season changes. (none)
- Captions during a take drawn on the canvas as film subtitles: pale yellow italic at 3% of the wall height, black outline and drop shadow, 5 s each or a per-caption hold, half-second fades. (none)
- `convert-take.sh` in the studies repo converts the webm to h264/aac and pads to an even size. (none)
- Headless Chrome harness in the studies repo (`labs/lab1/tools/`): scripts for stills of a URL, close-ups, the wizard legend over the socket, fades, sweeps, full-field stats, fps, record-mode fit, a record-mode take, petals per gesture, one still per season, stills of the take at given seconds, and the sound layer on load plus a 20 s audio recording. (none)
- Renders in `labs/lab1/renders/`: look comparisons, close-ups, sweeps, captions, record fit, one still per season, and stills of the take at 0:24, 0:59, 1:01, 1:30, 1:49, 2:24, 2:26 and 2:55. (none)
- Handoff notes in `tinkerbelle/NOTES.md`. (none)

## Not addressed

- F3 (hand detection without a wizard) and F5 (an emotional or practical function): no change in the fork.
