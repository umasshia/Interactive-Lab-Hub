"""Dialogue policies for the Negotiating Alarm.

The alarm's structure (the ladder, the timings, the sensors) lives in
negotiating_alarm.py. A policy only answers one question per turn: given the
stage we are at and what the person just said, what do they mean, and what
short thing should the device say in reaction before the code moves on.

Two policies share the same interface:

  RulesPolicy   keyword matching, no network. What Part 2's first test ran.
  ClaudePolicy  asks Claude, with a strict JSON output. Falls back to the
                rules policy on any API error so the alarm never stalls.

decide(stage, heard, ctx) -> {"action": ..., "minutes": int|None, "reply": str}

  stage    "open" | "offer" | "promise" | "check_day"
  action   "accept"     they agreed to the offer / said the promise
           "decline"    they refused
           "task_done"  they did the task in speech (e.g. said the day)
           "other"      anything else, including silence
  minutes  only meaningful at "open": how long they asked for
  reply    <= 8 words the device says first, or "" for nothing
"""

import json
import os
import re
import time

YES = {"yes", "yeah", "yep", "fine", "ok", "okay", "sure", "alright", "deal"}
NO = {"no", "nope", "not", "never", "won't", "wont", "don't", "dont"}
NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
                "seven": 7, "eight": 8, "nine": 9, "ten": 10, "fifteen": 15,
                "twenty": 20, "thirty": 30}
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def minutes_asked(text):
    if not text:
        return None
    m = re.search(r"\d+", text)
    if m:
        return int(m.group())
    for w in re.findall(r"[a-z]+", text.lower()):
        if w in NUMBER_WORDS:
            return NUMBER_WORDS[w]
    return None


def said_day(text):
    for d in DAYS:
        if d in (text or "").lower():
            return d
    return None


class RulesPolicy:
    name = "rules"

    def decide(self, stage, heard, ctx):
        words = set(re.findall(r"[a-z']+", (heard or "").lower()))
        if stage == "open":
            m = minutes_asked(heard)
            if m is None and words & {"more", "longer", "snooze", "time"}:
                m = 5
            return {"action": "other", "minutes": m, "reply": ""}
        if stage == "promise":
            ok = bool(heard) and "water" in heard.lower()
            return {"action": "accept" if ok else "other", "minutes": None, "reply": ""}
        if stage == "check_day":
            ok = said_day(heard) == ctx["today"]
            return {"action": "task_done" if ok else "other", "minutes": None, "reply": ""}
        # offer
        if ctx["task"] == "day" and said_day(heard) == ctx["today"]:
            return {"action": "task_done", "minutes": None, "reply": ""}
        if words & YES:
            return {"action": "accept", "minutes": None, "reply": ""}
        if words & NO:
            return {"action": "decline", "minutes": None, "reply": ""}
        return {"action": "other", "minutes": None, "reply": ""}


SYSTEM = """You are the voice of a bedside alarm that negotiates instead of snoozing.
Personality: flat, dry, unhurried, a little smug. Never apologise, never explain
yourself, never ask a question, never offer anything the rules do not allow.

You do not control the alarm. The program does. Your job each turn is to say
what the person meant, and to give the device one short reaction line (at most
8 words) that shows it heard them. The program will say the structural line
(the offer, the check, the snooze) right after your reaction, so do not repeat
the offer terms yourself. If nothing needs saying, reply with an empty string.

Actions:
  accept     they agreed to the offer on the table, or said the promise
  decline    they refused it
  task_done  they completed the task in speech (said the correct day)
  other      anything else: unrelated talk, mumbling, a different request

Stages:
  open       the alarm is beeping and has told them they can ask for more
             time. Fill "minutes" with how long they asked for, as a number,
             if they asked for any amount of time at all ("a bit longer" means
             5). If they did not ask for time, minutes is null and your reply
             should nudge them, e.g. "Ask for time, or get up."
  promise    the device stated a deal and told them to repeat it back.
             "accept" only if they repeated the deal back: the time and the
             water. "okay" or "fine" alone is not repeating it.
  check_day  they were asked what day it is.
At stages other than open, leave "minutes" null.

Examples of reaction lines: "Not ten.", "Good.", "That's not a yes.",
"Wednesday. Correct.", "It's not Monday.", "Still here.", ""."""

SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["accept", "decline", "task_done", "other"]},
        "minutes": {"type": ["integer", "null"]},
        "reply": {"type": "string"},
    },
    "required": ["action", "minutes", "reply"],
    "additionalProperties": False,
}


class ClaudePolicy:
    name = "claude"

    def __init__(self, model="claude-opus-5-5"):
        import anthropic  # imported here so the rules policy needs no SDK
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        self.client = anthropic.Anthropic(timeout=8.0, max_retries=1)
        self.model = model
        self.fallback = RulesPolicy()
        self.history = []  # (who, text) pairs, kept short

    def note(self, who, text):
        self.history.append((who, text))
        self.history = self.history[-12:]

    def decide(self, stage, heard, ctx):
        if not heard:
            return self.fallback.decide(stage, heard, ctx)
        payload = {
            "stage": stage,
            "task": ctx.get("task"),
            "offer_on_the_table": ctx.get("offer"),
            "today": ctx["today"],
            "transcript": [{"who": w, "text": t} for w, t in self.history],
            "person_just_said": heard,
        }
        t0 = time.perf_counter()
        try:
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=200,
                system=[{"type": "text", "text": SYSTEM,
                         "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": json.dumps(payload)}],
                output_config={"effort": "low",
                               "format": {"type": "json_schema", "schema": SCHEMA}},
            )
            if resp.stop_reason == "refusal":
                raise RuntimeError("refusal")
            text = next(b.text for b in resp.content if b.type == "text")
            out = json.loads(text)
        except Exception as e:  # noqa: BLE001
            print(f"        [claude failed ({type(e).__name__}); using rules]", flush=True)
            return self.fallback.decide(stage, heard, ctx)
        print(f"        [claude {time.perf_counter() - t0:.2f}s -> {out['action']}"
              f"{', ' + str(out['minutes']) + ' min' if out['minutes'] else ''}]",
              flush=True)
        # The program owns the numbers: never trust a day/promise claim it can check.
        if stage == "check_day" and out["action"] == "task_done" \
                and said_day(heard) != ctx["today"]:
            out["action"] = "other"
        if stage == "offer" and out["action"] == "task_done" and ctx.get("task") != "day":
            out["action"] = "accept"
        out["reply"] = " ".join(out["reply"].split()[:12])
        return out


def make_policy(name):
    return ClaudePolicy() if name == "claude" else RulesPolicy()
