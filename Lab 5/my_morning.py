"""
Part I, my version (Out the door): how long after my alarm did I leave my room?

The answer is worked out in code from the night log; Qwen only gets the computed facts
and turns them into one sentence, which Piper from Lab 3 reads out loud.

    python my_morning.py                 # answer from night_log.jsonl now
    python my_morning.py --watch         # run next to overnight.py, answer when I walk back in
    python my_morning.py --no-speak      # print only
    python my_morning.py --alarm 08:00

The rule: I'm up at the first time the camera sees me at the door after the alarm that is
not followed by another sighting within 10 minutes. A sighting followed by another one
within 10 minutes is a short trip (bathroom, phone), not getting up. Out and back look the
same in the log, so sightings after the alarm are paired in order.
"""
import argparse
import datetime
import json
import pathlib
import subprocess
import time

import requests

RETURN_WINDOW = datetime.timedelta(minutes=10)
LAB3 = pathlib.Path(__file__).resolve().parent.parent / "Lab 3"


def sightings(entries):
    """Start time of every stretch with someone in view (nobody, then a person)."""
    out, before = [], "nobody"
    for e in entries:
        if "reading" not in e:
            continue
        if e["reading"] != "nobody" and before == "nobody":
            out.append(datetime.datetime.fromisoformat(e["t"]))
        before = e["reading"]
    return out


def next_alarm(start, hhmm):
    h, m = map(int, hhmm.split(":"))
    alarm = start.replace(hour=h, minute=m, second=0)
    return alarm if alarm > start else alarm + datetime.timedelta(days=1)


def out_the_door(seen, alarm):
    """Short trips, the real exit and the return after the alarm, by the 10-minute rule."""
    after = [s for s in seen if s >= alarm]
    trips, i = [], 0
    while i < len(after):
        back = after[i + 1] if i + 1 < len(after) else None
        if back and back - after[i] <= RETURN_WINDOW:
            trips.append((after[i], back))
            i += 2
        else:
            return trips, after[i], back
    return trips, None, None


def clock(t):
    return f"{t.hour}:{t.minute:02d}"


def ask(facts, llm):
    prompt = ("Facts about this morning:\n" + "\n".join(facts) + "\n\n"
              "Write one short sentence, spoken to me as \"you\", saying when I left my room "
              "and how many minutes after my alarm that was. Use the exact times and numbers "
              "from the facts and nothing else.")
    r = requests.post("http://localhost:11434/api/generate", json={
        "model": llm,
        "prompt": prompt,
        "think": False,
        "stream": False,
        "options": {"num_predict": 60, "temperature": 0.2},
    }, timeout=120)
    r.raise_for_status()
    return r.json()["response"].strip()


def speak(text):
    # List form, no shell: nothing Qwen writes can run as a command. "--" keeps a sentence
    # that starts with "-" from being read as a piper flag.
    piper = subprocess.Popen(
        [str(LAB3 / ".venv" / "bin" / "python"), "-m", "piper", "--model", "en_US-lessac-medium",
         "--data-dir", str(LAB3 / "voices"), "--output-raw", "--", text],
        stdout=subprocess.PIPE)
    subprocess.run(["aplay", "-q", "-r", "22050", "-f", "S16_LE", "-t", "raw", "-"], stdin=piper.stdout)
    piper.stdout.close()
    piper.wait()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", default="night_log.jsonl")
    parser.add_argument("--alarm", default="07:30")
    parser.add_argument("--model", default="qwen3.5:0.8b")
    parser.add_argument("--watch", action="store_true", help="wait until I come back into the room")
    parser.add_argument("--no-speak", action="store_true")
    args = parser.parse_args()

    log = pathlib.Path(args.log)
    while True:
        entries = [json.loads(line) for line in log.open() if line.strip()] if log.exists() else []
        if entries:
            alarm = next_alarm(datetime.datetime.fromisoformat(entries[0]["t"]), args.alarm)
            seen = sightings(entries)
            trips, left, back = out_the_door(seen, alarm)
            if not args.watch or back:
                break
        elif not args.watch:
            raise SystemExit(f"{args.log} is empty or missing")
        time.sleep(5)

    early = [s for s in seen if s.date() == alarm.date() and s < alarm]
    if left is None:                         # nothing to work out: say so, do not ask the model
        text = f"The camera did not see you leave your room after {clock(alarm)} this morning."
    else:
        minutes = int((left - alarm).total_seconds() // 60)
        facts = [
            f"Alarm: {clock(alarm)}",
            f"Got up and left the room: {clock(left)}, {minutes} minutes after the alarm",
            f"Came back into the room: {clock(back)}" if back else "Has not come back into the room yet",
            "Short trips out and back after the alarm, before that: "
            + (", ".join(f"{clock(a)} to {clock(b)}" for a, b in trips) or "none"),
            "Seen at the door before the alarm: " + (", ".join(clock(s) for s in early) or "never"),
        ]
        print("\n".join(facts))
        t0 = time.time()
        text = ask(facts, args.model)
        print(f"[{args.model}, {time.time() - t0:.1f} s] {text}")
        if clock(left) not in text or str(minutes) not in text:
            text = f"This morning you left your room at {clock(left)}, {minutes} minutes after your alarm."
            print("Qwen's sentence is missing the time or the minutes, so the plain sentence is used.")

    print("\n" + text)
    if not args.no_speak:
        speak(text)
