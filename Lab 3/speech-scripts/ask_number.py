#!/usr/bin/env python3
"""Lab 3 Part B: ask for a number out loud, record the answer, transcribe it.

    python ask_number.py
    python ask_number.py --question "How many pets do you have?"
    python ask_number.py --model tiny.en --min-silence 0.6

The device speaks the question with Piper, then waits. Silero VAD decides when
the answer has ended, faster-whisper transcribes it, and the device reads back
what it heard. The raw audio and the transcript are saved under answers/ so the
characteristic digit errors can be inspected afterwards.

Why --min-silence defaults to 1.0 here rather than the 0.4 in echo_bot.py:
people say numbers in groups ("nine one seven ... five five five ...") with
pauses between the groups that are longer than the pauses between words. At 0.4
the device would take the first group as the whole answer.
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

SAMPLE_RATE = 16000
LAB_DIR = Path(__file__).resolve().parent.parent
DEFAULT_VAD = LAB_DIR / "models" / "silero_vad.onnx"
DEFAULT_VOICE = LAB_DIR / "voices" / "en_US-lessac-medium.onnx"
ANSWERS_DIR = Path(__file__).resolve().parent / "answers"


def say(voice: PiperVoice, text: str) -> None:
    for chunk in voice.synthesize(text):
        audio = np.frombuffer(chunk.audio_int16_bytes, dtype=np.int16)
        sd.play(audio, samplerate=chunk.sample_rate)
        sd.wait()


def record_one_utterance(vad_model: Path, min_silence: float) -> np.ndarray:
    """Blocks until the VAD has heard one complete utterance, returns its samples."""
    config = sherpa_onnx.VadModelConfig()
    config.silero_vad.model = str(vad_model)
    config.silero_vad.min_silence_duration = min_silence
    config.sample_rate = SAMPLE_RATE
    vad = sherpa_onnx.VoiceActivityDetector(config, buffer_size_in_seconds=30)
    window = config.silero_vad.window_size

    buffer = np.empty(0, dtype=np.float32)
    samples_per_read = int(0.1 * SAMPLE_RATE)
    with sd.InputStream(channels=1, dtype="float32", samplerate=SAMPLE_RATE) as stream:
        while True:
            chunk, _ = stream.read(samples_per_read)
            buffer = np.concatenate([buffer, chunk.reshape(-1)])
            while len(buffer) > window:
                vad.accept_waveform(buffer[:window])
                buffer = buffer[window:]
            if not vad.empty():
                utterance = np.array(vad.front.samples, dtype=np.float32)
                vad.pop()
                return utterance


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--question", default="What is your zip code?")
    parser.add_argument("--model", default="base.en",
                        help="whisper model size (default: base.en, the smallest "
                             "that got my own digits right in testing)")
    parser.add_argument("--min-silence", type=float, default=1.0,
                        help="seconds of silence that end the answer (default: 1.0)")
    parser.add_argument("--vad-model", type=Path, default=DEFAULT_VAD)
    parser.add_argument("--voice", type=Path, default=DEFAULT_VOICE)
    args = parser.parse_args()

    for path, what in [(args.vad_model, "VAD model"), (args.voice, "Piper voice")]:
        if not path.is_file():
            sys.exit(f"{what} not found at {path}. Run ./setup.sh first.")

    print("Loading models...", flush=True)
    recognizer = WhisperModel(args.model, device="cpu", compute_type="int8")
    voice = PiperVoice.load(str(args.voice))

    say(voice, args.question)
    print(f"asked:  {args.question}")
    print(f"listening (endpointing after {args.min_silence}s of silence)...", flush=True)

    answer = record_one_utterance(args.vad_model, args.min_silence)
    turn_ended = time.perf_counter()

    segments, _ = recognizer.transcribe(answer, beam_size=1)
    heard = " ".join(s.text.strip() for s in segments)
    asr_time = time.perf_counter() - turn_ended
    digits = re.sub(r"\D", "", heard)

    print(f"heard:  {heard!r}")
    print(f"digits: {digits or '(none)'}")
    print(f"[answer {len(answer) / SAMPLE_RATE:.1f}s | asr {asr_time:.2f}s]")

    ANSWERS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    sf.write(ANSWERS_DIR / f"{stamp}.wav", answer, SAMPLE_RATE)
    (ANSWERS_DIR / f"{stamp}.txt").write_text(
        f"question: {args.question}\nheard: {heard}\ndigits: {digits}\n")
    print(f"saved:  answers/{stamp}.wav and .txt")

    if digits:
        say(voice, "I heard " + " ".join(digits) + ".")
    else:
        say(voice, "Sorry, I did not catch a number.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
