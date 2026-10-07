#!/usr/bin/env python3
"""The Negotiating Alarm, Lab 3 Part 2.

The alarm beeps and tells you straight away that you can ask it for more time.
You get at most five minutes, and only if you repeat the deal back: "N minutes,
then I drink the water". Until you repeat it, the beeping continues. The snooze
itself is silent. If the glass has not moved by the end, the device plays your
own promise back to you and then keeps asking (what day is it, hand on the
device) until one task is done. No more snoozes.

    python negotiating_alarm.py                  # alarm fires now, real timings
    python negotiating_alarm.py --speed 20       # snoozes 20x shorter, for demos
    python negotiating_alarm.py --alarm-in 90    # fire 90 seconds from now
    python negotiating_alarm.py --sensor-test    # print pad readings, no dialogue

Sensors (MPR121 capacitive board over Qwiic):
  water pad  a glass of water sits on copper tape clipped to this pad. "Drank
             the water" means the reading changed from what it was when the
             alarm fired, either direction, so it does not matter whether the
             glass was there at boot.
  hand pads  bare pads on top of the device. "Hand on the device" means any of
             them reads a touch.
"""

import argparse
import re
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import sherpa_onnx
import sounddevice as sd
import soundfile as sf
from faster_whisper import WhisperModel
from piper import PiperVoice

from alarm_policy import DAYS, NUMBER_WORDS, make_policy

SAMPLE_RATE = 16000
LAB_DIR = Path(__file__).resolve().parent.parent
DEFAULT_VAD = LAB_DIR / "models" / "silero_vad.onnx"
DEFAULT_VOICE = LAB_DIR / "voices" / "en_US-lessac-medium.onnx"
CLIPS_DIR = Path(__file__).resolve().parent / "promises"

# Timings, all in seconds except MAX_SNOOZE.
ALARM_LISTEN = 6   # how long it listens between rounds of beeping
LIFT_HOLD = 1.0    # off the pad this long counts as a lift at all
DRINK_HOLD = 3.0   # off the pad this long counts as drinking
FAKE_LIFT_LINES = [
    "That was a lift, not a sip.",
    "Up and down. I saw that.",
    "The water has to go in you.",
    "Nice try. Drink it.",
]
ANSWER_WAIT = 15   # how long it waits for the deal to be repeated back
MAX_SNOOZE = 5     # minutes. Ask for less and you get what you asked for.


# --- speech -----------------------------------------------------------------

class Speaker:
    def __init__(self, voice_path: Path) -> None:
        self.voice = PiperVoice.load(str(voice_path))

    def say(self, text: str) -> None:
        print(f"DEVICE: {text}", flush=True)
        for chunk in self.voice.synthesize(text):
            sd.play(np.frombuffer(chunk.audio_int16_bytes, dtype=np.int16),
                    samplerate=chunk.sample_rate)
            sd.wait()


class Listener:
    """One utterance at a time, with a deadline. The window is timed from the
    moment listen() is called, which is right after the device stops speaking."""

    def __init__(self, vad_model: Path, whisper_model: str, min_silence: float) -> None:
        self.recognizer = WhisperModel(whisper_model, device="cpu", compute_type="int8")
        self.config = sherpa_onnx.VadModelConfig()
        self.config.silero_vad.model = str(vad_model)
        self.config.silero_vad.min_silence_duration = min_silence
        self.config.sample_rate = SAMPLE_RATE

    def listen(self, seconds: float, until=None):
        """Returns (text, samples) or (None, None) on timeout. `until` is an
        optional callable polled between reads; if it returns True we stop
        early and return ("<sensor>", None)."""
        vad = sherpa_onnx.VoiceActivityDetector(self.config, buffer_size_in_seconds=30)
        window = self.config.silero_vad.window_size
        deadline = time.monotonic() + seconds
        buffer = np.empty(0, dtype=np.float32)
        per_read = int(0.1 * SAMPLE_RATE)
        print(f"        [listening {seconds}s]", flush=True)
        with sd.InputStream(channels=1, dtype="float32", samplerate=SAMPLE_RATE) as stream:
            while time.monotonic() < deadline:
                if until is not None and until():
                    return "<sensor>", None
                chunk, _ = stream.read(per_read)
                buffer = np.concatenate([buffer, chunk.reshape(-1)])
                while len(buffer) > window:
                    vad.accept_waveform(buffer[:window])
                    buffer = buffer[window:]
                if not vad.empty():
                    samples = np.array(vad.front.samples, dtype=np.float32)
                    vad.pop()
                    segments, _ = self.recognizer.transcribe(samples, beam_size=1)
                    text = " ".join(s.text.strip() for s in segments).strip()
                    print(f"HEARD:  {text!r}", flush=True)
                    return text, samples
        print("HEARD:  (nothing)", flush=True)
        return None, None


def spell(n: int) -> str:
    return {v: k for k, v in NUMBER_WORDS.items()}.get(n, str(n))


# --- sensors ----------------------------------------------------------------

class Sensors:
    """Wraps the MPR121. If the board is missing, every check reports 'not done'
    and the alarm still runs, so the dialogue can be tested on its own."""

    def __init__(self, water_pad: int, hand_pads: list[int], water_delta: int,
                 bed_pad: int = 1) -> None:
        self.water_pad, self.hand_pads, self.water_delta = water_pad, hand_pads, water_delta
        self.bed_pad = bed_pad
        self.cap = None
        try:
            import board, busio, adafruit_mpr121
            self.cap = adafruit_mpr121.MPR121(busio.I2C(board.SCL, board.SDA))
        except Exception as e:  # noqa: BLE001
            print(f"WARNING: no MPR121 ({e}); sensor checks will always be 'not done'")
        self._lock = threading.Lock()
        self._thread = None
        self._hand = False
        time.sleep(0.3)  # the chip's first reading after wake-up is 0
        self.reset_water()

    def water_reading(self) -> int:
        return self.cap.filtered_data(self.water_pad) if self.cap else 0

    def reset_water(self) -> None:
        """Call with the glass sitting on the pad. Lifting is measured from here."""
        with self._lock:
            self.water_baseline = self.water_reading()
            self._above_since = None
            self._lifted = False
            self.fake_lifts = 0

    def start_watching(self) -> None:
        """Read the pads 20 times a second on a background thread, so a drink
        taken while the device is talking or playing audio is still seen. All
        I2C access happens on this thread once it starts."""
        if self.cap is None or self._thread is not None:
            return
        self._thread = threading.Thread(target=self._watch, daemon=True)
        self._thread.start()

    def _watch(self) -> None:
        while True:
            reading = self.water_reading()
            hand = any(self.cap[i].value for i in self.hand_pads)
            now = time.monotonic()
            with self._lock:
                self._hand = hand
                if self._lifted:
                    pass
                elif reading - self.water_baseline >= self.water_delta:
                    if self._above_since is None:
                        self._above_since = now
                    elif now - self._above_since >= DRINK_HOLD:
                        self._lifted = True
                elif self._above_since is not None:
                    # Glass came back down. Measured on the bench: lifting
                    # RAISES the reading ~20, a hand LOWERS it ~40, so only a
                    # rise counts. A lift too short to drink is a fake.
                    if now - self._above_since >= LIFT_HOLD:
                        self.fake_lifts += 1
                        print(f"        [fake lift: {now - self._above_since:.1f}s]",
                              flush=True)
                    self._above_since = None
            time.sleep(0.05)

    def water_done(self) -> bool:
        """True once the glass has been off the pad for DRINK_HOLD seconds.
        Stays true: putting the glass back after drinking is expected."""
        with self._lock:
            return self._lifted

    def take_fake_lifts(self) -> int:
        """How many too-short lifts happened since the last call."""
        with self._lock:
            n, self.fake_lifts = self.fake_lifts, 0
            return n

    def hand_done(self) -> bool:
        if self.cap is None:
            return False
        if self._thread is None:
            return any(self.cap[i].value for i in self.hand_pads)
        with self._lock:
            return self._hand

    def _sample(self, seconds: float = 3.0) -> tuple[float, int, int]:
        vals = []
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            vals.append(self.water_reading())
            time.sleep(0.05)
        return sum(vals) / len(vals), min(vals), max(vals)

    def calibrate(self) -> None:
        """Guided measurement of the water pad. Each step: set it up, press
        Enter, keep still for three seconds while it measures."""
        steps = [
            ("on", "Put the glass ON the pad. Take your hands away."),
            ("lifted", "Lift the glass and hold it in the air, about 20 cm above the pad."),
            ("touch", "Put the glass back ON the pad and keep your hand wrapped around it."),
            ("on_again", "Take your hand away. Leave the glass ON the pad."),
            ("away", "Move the glass off the pad onto the bare desk, hands away."),
        ]
        results = {}
        print("Water pad calibration. Follow each step, then press Enter.\n")
        for key, instruction in steps:
            input(f"{instruction}\n  Press Enter when ready... ")
            print("  measuring, keep still...", flush=True)
            results[key] = self._sample()
            mean, lo, hi = results[key]
            print(f"  {key:9s} mean {mean:6.1f}   range {lo}-{hi}\n", flush=True)

        on = (results["on"][0] + results["on_again"][0]) / 2
        print("Summary, relative to glass on the pad:")
        for key in ["lifted", "away", "touch"]:
            print(f"  {key:9s} {results[key][0] - on:+6.1f}")
        lift = min(results["lifted"][0], results["away"][0]) - on
        noise = max(hi - lo for _, lo, hi in results.values())
        print(f"\n  smallest lift signal {lift:+.1f}, worst noise band {noise}")
        if lift <= 0:
            print("  Lifting does not raise the reading. Paste this to Claude.")
        else:
            print(f"  suggested --water-delta {max(1, round(lift / 2))}"
                  f" (half the lift signal; current {self.water_delta})")
        if results["touch"][0] - on >= lift / 2 > 0:
            print("  WARNING: a hand on the glass also looks like a lift.")

    def test(self) -> None:
        print(f"water pad {self.water_pad} baseline {self.water_baseline}, "
              f"delta needed {self.water_delta}. Ctrl-C to stop.")
        while True:
            hand = [i for i in self.hand_pads if self.cap[i].value] if self.cap else []
            bed = self.cap.filtered_data(self.bed_pad) if self.cap else 0
            print(f"water {self.water_reading():4d}  rise "
                  f"{self.water_reading() - self.water_baseline:+4d}  "
                  f"bed {bed:4d}  hand touched {hand}", flush=True)
            time.sleep(0.25)


# --- the alarm --------------------------------------------------------------

def beep(volume: float, seconds: float = 0.3, freq: int = 880) -> None:
    t = np.arange(int(seconds * 22050)) / 22050
    sd.play((np.sign(np.sin(2 * np.pi * freq * t)) * volume).astype(np.float32), 22050)
    sd.wait()


def snooze(seconds: float, speed: float, until=None, early_exit=True) -> bool:
    """Silent, not listening. Polls `until` (a sensor check); True if it fired.
    With early_exit=False the snooze always runs its full length and only
    reports afterwards whether the sensor fired at any point."""
    seconds = seconds / speed
    print(f"        [snooze {seconds:.0f}s]", flush=True)
    end = time.monotonic() + seconds
    fired = False
    while time.monotonic() < end:
        if until is not None and until():
            fired = True
            if early_exit:
                return True
        time.sleep(0.2)
    return fired


def run(speaker: Speaker, listener: Listener, sensors: Sensors, policy,
        speed: float, alarm_volume: float) -> None:
    today = DAYS[datetime.now().weekday()]
    ctx = {"today": today, "task": "water"}

    def say(text):
        if text:
            speaker.say(text)
            if hasattr(policy, "note"):
                policy.note("device", text)

    def hear(seconds, until=None):
        text, samples = listener.listen(seconds, until=until)
        if text and text != "<sensor>" and hasattr(policy, "note"):
            policy.note("person", text)
        return text, samples

    def beeps(n=3):
        for _ in range(n):
            beep(alarm_volume)
            time.sleep(0.15)

    def done(line="Good morning."):
        say(line)

    fakes_called = [0]

    def call_out_fakes():
        """If they lifted the glass and put it straight back, say so."""
        if sensors.take_fake_lifts():
            say(FAKE_LIFT_LINES[fakes_called[0] % len(FAKE_LIFT_LINES)])
            fakes_called[0] += 1

    started = time.monotonic()

    def situation(stage_attempts):
        ctx.update(attempts=stage_attempts,
                   elapsed=round(time.monotonic() - started),
                   glass_lifted=sensors.water_done())

    # 1. ALARM. Beep, and invite them to talk straight away: in Part E nobody
    #    knew the device listened, so the invitation is part of the alarm.
    say(f"It's {datetime.now().strftime('%-I:%M')}.")
    nudge, attempts = "Ask me for more time.", 0
    while True:
        beeps()
        if sensors.water_done():
            return done("You drank the water. Good morning.")
        say(nudge)
        text, _ = hear(ALARM_LISTEN, until=sensors.water_done)
        if text == "<sensor>" or sensors.water_done():
            return done("You drank the water. Good morning.")
        call_out_fakes()
        attempts += 1
        situation(attempts)
        d = policy.decide("open", text, ctx)
        if d["minutes"]:
            break
        nudge = d["reply"] or "Ask me for more time."

    # 2. THE DEAL. Never more than MAX_SNOOZE minutes, always for the water.
    minutes = max(1, min(MAX_SNOOZE, d["minutes"]))
    unit = f"minute{'s' if minutes > 1 else ''}"
    deal = f"{spell(minutes).capitalize()} {unit}. Then you drink the water."
    if d["minutes"] > MAX_SNOOZE:
        deal = f"Not {spell(d['minutes'])}. " + deal
    ctx["offer"] = deal
    say(deal + " Repeat it back to me.")

    # 3. REPEAT IT BACK, or the beeping continues. Their words are the promise.
    attempts = 0
    while True:
        text, samples = hear(ANSWER_WAIT, until=sensors.water_done)
        if text == "<sensor>" or sensors.water_done():
            return done("You drank the water. Good morning.")
        call_out_fakes()
        attempts += 1
        situation(attempts)
        d = policy.decide("promise", text, ctx)
        if d["action"] == "accept":
            break
        beeps()
        say(d["reply"] or "Repeat it back to me.")
    # The webcam-style USB mic records quietly, so the promise sounded far
    # away on playback. Peak-normalise it to near full scale.
    peak = float(np.max(np.abs(samples))) if samples is not None and len(samples) else 0.0
    promise = samples * (0.9 / peak) if peak > 0 else samples
    CLIPS_DIR.mkdir(exist_ok=True)
    sf.write(CLIPS_DIR / f"{datetime.now():%Y%m%d_%H%M%S}.wav", promise, SAMPLE_RATE)
    say("Recorded.")

    # 4. SNOOZE. Silent for its full length, whatever happens.
    if snooze(minutes * 60, speed, until=sensors.water_done, early_exit=False):
        return done("You drank the water. Good morning.")

    # 5. BUGGING. The deal is broken: no more snoozes, just tasks until one is done.
    if sensors.take_fake_lifts():
        say("You picked it up and put it back. That's not drinking.")
    else:
        say("You didn't drink the water.")
    print("DEVICE: [plays back the promise]", flush=True)
    sd.play(promise, SAMPLE_RATE)
    sd.wait()
    hear(10, until=sensors.water_done)
    if sensors.water_done():
        return done("You drank the water. Good morning.")
    call_out_fakes()

    ctx["task"] = "day"
    say("What day is it?")
    text, _ = hear(10)
    situation(1)
    d = policy.decide("check_day", text, ctx)
    if d["action"] == "task_done":
        say(d["reply"])
        return done("Correct. Good morning.")
    if text:
        say("It's not.")
        say(d["reply"])

    say("Hand on the device.")
    hear(5, until=sensors.hand_done)
    if sensors.hand_done():
        return done()
    print("DEVICE: [ALARM] hand on the device or Ctrl-C to stop", flush=True)
    while not sensors.hand_done():
        beep(alarm_volume)
        time.sleep(0.15)
    done()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--speed", type=float, default=1.0,
                   help="divide snoozes and grace by this; answer windows stay real")
    p.add_argument("--alarm-in", type=float, default=0, help="seconds until the alarm fires")
    p.add_argument("--model", default="base.en")
    p.add_argument("--min-silence", type=float, default=0.8)
    p.add_argument("--water-pad", type=int, default=0)
    p.add_argument("--hand-pads", type=int, nargs="+", default=[6, 7, 8, 9, 10, 11])
    p.add_argument("--bed-pad", type=int, default=1,
                   help="pad wired to the copper strip in the bed")
    p.add_argument("--water-delta", type=int, default=11,
                   help="rise in the water pad reading that counts as lifted "
                        "(run --calibrate to measure yours)")
    p.add_argument("--calibrate", action="store_true",
                   help="guided measurement of the water pad, no dialogue")
    p.add_argument("--policy", choices=["rules", "claude"], default="rules",
                   help="dialogue policy: keyword rules, or Claude (needs ANTHROPIC_API_KEY)")
    p.add_argument("--alarm-volume", type=float, default=0.9,
                   help="beep amplitude 0 to 1 (use 0.1 in a room full of people)")
    p.add_argument("--sensor-test", action="store_true")
    p.add_argument("--vad-model", type=Path, default=DEFAULT_VAD)
    p.add_argument("--voice", type=Path, default=DEFAULT_VOICE)
    args = p.parse_args()

    sensors = Sensors(args.water_pad, args.hand_pads, args.water_delta, args.bed_pad)
    if args.calibrate:
        sensors.calibrate()
        return
    if args.sensor_test:
        sensors.test()
        return

    for path, what in [(args.vad_model, "VAD model"), (args.voice, "Piper voice")]:
        if not path.is_file():
            sys.exit(f"{what} not found at {path}. Run ./setup.sh first.")
    print("Loading models...", flush=True)
    listener = Listener(args.vad_model, args.model, args.min_silence)
    speaker = Speaker(args.voice)
    policy = make_policy(args.policy)
    print(f"dialogue policy: {policy.name}", flush=True)

    if args.alarm_in:
        print(f"Alarm in {args.alarm_in:.0f}s. Put the glass on the pad now.", flush=True)
        time.sleep(args.alarm_in)
    sensors.reset_water()  # glass on the pad when the alarm fires
    sensors.start_watching()
    run(speaker, listener, sensors, policy, args.speed, args.alarm_volume)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
