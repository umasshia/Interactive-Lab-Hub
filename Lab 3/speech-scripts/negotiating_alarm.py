#!/usr/bin/env python3
"""The Negotiating Alarm, Lab 3 Part 2.

An alarm that never grants a snooze outright. It counters with less time plus
one small task, records my promise, and plays it back if I do not follow
through. Each rung halves the snooze and shortens how long it waits for an
answer. Silence, or anything it cannot map, moves one rung down.

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
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import sherpa_onnx
import sounddevice as sd
import soundfile as sf
from faster_whisper import WhisperModel
from piper import PiperVoice

from alarm_policy import DAYS, make_policy

SAMPLE_RATE = 16000
LAB_DIR = Path(__file__).resolve().parent.parent
DEFAULT_VAD = LAB_DIR / "models" / "silero_vad.onnx"
DEFAULT_VOICE = LAB_DIR / "voices" / "en_US-lessac-medium.onnx"
CLIPS_DIR = Path(__file__).resolve().parent / "promises"

# The ladder. Ten minutes is what I ask for, never what I get.
OPEN_WAIT = 20
MAX_FIRST_SNOOZE = 5  # minutes. Ask for less and you get what you asked for.
RUNGS = [
    dict(task="water", snooze=5 * 60, wait=15,
         offer="Five minutes. And you drink the water.", confirm="Recorded. Five minutes."),
    dict(task="day", snooze=2 * 60, wait=10,
         offer="Two minutes. Then you tell me what day it is.", confirm="Two minutes."),
    dict(task="hand", snooze=60, wait=5,
         offer="One minute. Then your hand on the device.", confirm="One minute."),
]
GRACE = 30


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
    return {1: "one", 2: "two", 3: "three", 4: "four", 5: "five"}.get(n, str(n))


# --- sensors ----------------------------------------------------------------

class Sensors:
    """Wraps the MPR121. If the board is missing, every check reports 'not done'
    and the alarm still runs, so the dialogue can be tested on its own."""

    def __init__(self, water_pad: int, hand_pads: list[int], water_delta: int) -> None:
        self.water_pad, self.hand_pads, self.water_delta = water_pad, hand_pads, water_delta
        self.cap = None
        try:
            import board, busio, adafruit_mpr121
            self.cap = adafruit_mpr121.MPR121(busio.I2C(board.SCL, board.SDA))
        except Exception as e:  # noqa: BLE001
            print(f"WARNING: no MPR121 ({e}); sensor checks will always be 'not done'")
        time.sleep(0.3)  # the chip's first reading after wake-up is 0
        self.water_baseline = self.water_reading()

    def water_reading(self) -> int:
        return self.cap.filtered_data(self.water_pad) if self.cap else 0

    def water_done(self) -> bool:
        return self.cap is not None and \
            abs(self.water_reading() - self.water_baseline) > self.water_delta

    def hand_done(self) -> bool:
        return self.cap is not None and any(self.cap[i].value for i in self.hand_pads)

    def test(self) -> None:
        print(f"water pad {self.water_pad} baseline {self.water_baseline}, "
              f"delta needed {self.water_delta}. Ctrl-C to stop.")
        while True:
            hand = [i for i in self.hand_pads if self.cap[i].value] if self.cap else []
            print(f"water {self.water_reading():4d}  done={self.water_done()!s:5}  "
                  f"hand touched {hand}", flush=True)
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
    ctx = {"today": today}

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

    say(f"It's {datetime.now().strftime('%-I:%M')}.")
    text, _ = hear(OPEN_WAIT)
    d = policy.decide("open", text, ctx)
    say(d["reply"])

    # The first offer is the smaller of five minutes and what they asked for.
    asked = d["minutes"]
    first = max(1, min(MAX_FIRST_SNOOZE, asked)) if asked else MAX_FIRST_SNOOZE
    unit = f"minute{'s' if first > 1 else ''}"
    RUNGS[0].update(snooze=first * 60,
                    offer=f"{spell(first).capitalize()} {unit}. And you drink the water.",
                    confirm=f"Recorded. {spell(first).capitalize()} {unit}.")

    for rung in RUNGS:
        ctx.update(task=rung["task"], offer=rung["offer"])
        say(rung["offer"])
        text, _ = hear(rung["wait"])
        d = policy.decide("offer", text, ctx)
        say(d["reply"])
        if d["action"] == "task_done":          # said the right day at the offer
            return say("You're awake. Good morning.")
        if d["action"] != "accept":
            continue                            # decline, silence, anything else

        if rung["task"] == "water":
            say("Say it.")
            text, samples = hear(rung["wait"])
            d = policy.decide("promise", text, ctx)
            say(d["reply"])
            if d["action"] != "accept":
                continue
            CLIPS_DIR.mkdir(exist_ok=True)
            sf.write(CLIPS_DIR / f"{datetime.now():%Y%m%d_%H%M%S}.wav", samples, SAMPLE_RATE)
            say(rung["confirm"])
            # The first snooze is a real snooze: silent for its full length,
            # whatever happens. Only afterwards does it say anything.
            if snooze(rung["snooze"], speed, until=sensors.water_done, early_exit=False):
                return say("You drank the water. Good morning.")
            say("Did you drink the water?")
            hear(rung["wait"], until=sensors.water_done)
            if sensors.water_done():
                return say("You drank the water. Good morning.")
            print("DEVICE: [plays back the promise]", flush=True)
            sd.play(samples, SAMPLE_RATE)
            sd.wait()
            hear(10, until=sensors.water_done)
            if sensors.water_done():
                return say("You drank the water. Good morning.")
            say("I didn't get that.")

        elif rung["task"] == "day":
            say(rung["confirm"])
            snooze(rung["snooze"], speed)
            say("What day is it?")
            text, _ = hear(rung["wait"])
            d = policy.decide("check_day", text, ctx)
            say(d["reply"])
            if d["action"] == "task_done":
                return say("You're awake. Good morning.")
            say(f"It's {today.capitalize()}.")

        elif rung["task"] == "hand":
            say(rung["confirm"])
            if snooze(rung["snooze"], speed, until=sensors.hand_done):
                return say("Good morning.")
            say("Hand on the device.")
            hear(rung["wait"], until=sensors.hand_done)
            if sensors.hand_done():
                return say("Good morning.")

    # Bottom of the ladder.
    say("Thirty seconds.")
    if snooze(GRACE, speed, until=sensors.hand_done):
        return say("Good morning.")
    print("DEVICE: [ALARM] hand on the device or Ctrl-C to stop", flush=True)
    while not sensors.hand_done():
        beep(alarm_volume)
        time.sleep(0.15)
    say("Good morning.")


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
    p.add_argument("--water-delta", type=int, default=30,
                   help="change in the water pad reading that counts as lifted")
    p.add_argument("--policy", choices=["rules", "claude"], default="rules",
                   help="dialogue policy: keyword rules, or Claude (needs ANTHROPIC_API_KEY)")
    p.add_argument("--alarm-volume", type=float, default=0.9,
                   help="beep amplitude 0 to 1 (use 0.1 in a room full of people)")
    p.add_argument("--sensor-test", action="store_true")
    p.add_argument("--vad-model", type=Path, default=DEFAULT_VAD)
    p.add_argument("--voice", type=Path, default=DEFAULT_VOICE)
    args = p.parse_args()

    sensors = Sensors(args.water_pad, args.hand_pads, args.water_delta)
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
    sensors.water_baseline = sensors.water_reading()  # baseline at the moment it fires
    run(speaker, listener, sensors, policy, args.speed, args.alarm_volume)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
