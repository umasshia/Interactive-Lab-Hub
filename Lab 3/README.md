# Chatterboxes

**Collaborators:** none, I did this lab alone.

A speech-enabled bedside alarm that never grants a snooze outright. It counters with less time plus one small task, records my promise, and plays it back to me if I do not follow through. Storyboard and script are in Part D.

---

# Part 1

## A. Text to Speech

I tried all three engines on the same greeting. My greeting script uses Piper: [`speech-scripts/greet_samu.sh`](speech-scripts/greet_samu.sh). It says "Hello Samu" rather than "Hello Giorgi" because Piper pronounces Giorgi as "Jorgee".

- **espeak-ng:** very robotic and close to hard to understand. I could follow it, but I had to concentrate the whole time it was talking.
- **festival:** also robotic and sounds similar to espeak, though not the same. The voice is deeper and a little easier to understand.
- **Piper:** sounds the most like a real person and is by far the easiest to understand. The cadence is a little off, so you can tell it is not human, but it sounds good.

**Is the same greeting, in these different voices, the same greeting?**

No, it was not the same greeting. The words did not change, but who was saying them did. With espeak and festival it felt like a computer reading a sentence out loud, so "welcome back" was just information. Piper still sounded synthetic, but it was close enough to a person saying it to me that the same words felt like an actual greeting instead of a message.

## B. Speech to Text

Class recording, `lookdave.wav` (3.72s). All three sizes transcribed it correctly.

| model | transcription | real-time factor |
|---|---|---|
| tiny.en | 1.09s | 0.29x |
| base.en | 2.03s | 0.55x |
| small.en | 6.07s | 1.63x |

My own recording, 10 seconds, saying "Hi I am Samu, my favourite numbers are 1 2 3 5 8 13 21 34".

| model | transcription | real-time factor | transcript |
|---|---|---|---|
| tiny.en | 1.47s | 0.15x | Hi, I am some my favorite numbers are 1, 2, 3, 5, 8, 13, 21, 34. |
| base.en | 2.55s | 0.26x | Hi, I am Samu. My favorite numbers are 1, 2, 3, 5, 8, 13, 21, 34. |
| small.en | 7.93s | 0.79x | Hi, I am Samu. My favorite numbers are 1, 2, 3, 5, 8, 13, 21, 34. |

**At what point does the accuracy improvement stop being worth the delay, for a system that has to answer you?**

For me the line is at base.en. Going from tiny to base cost about one extra second on a ten second clip and fixed the only mistake, which was my name. Going from base to small cost another five seconds and fixed nothing. For a device that has to answer me, a one second wait feels like it is thinking, but a wait longer than what I said feels broken, and small.en was already close to that on the class recording, where it ran slower than real time.

**Script that verbally asks for a numerical input and records the answer:** [`speech-scripts/ask_number.py`](speech-scripts/ask_number.py). Piper asks the question, Silero VAD decides when the answer has ended, faster-whisper (base.en) transcribes it, and the device reads the digits back. The raw audio and transcript are saved so the digit errors can be inspected. The endpointing silence is set to 1.0s instead of the class default of 0.4s, because people say numbers in groups with longer pauses between the groups.

Three runs:

| question | heard | digits extracted |
|---|---|---|
| zip code | `One, one, two, three, four.` | none |
| zip code | `1, 2, 3, 4, 5.` | 12345 |
| phone number, said in groups | `917 550 753 3` | 9175507533, all correct |

Two characteristic errors showed up. In the first run whisper wrote the numbers as words, so the digit filter found nothing, while in the second run it wrote them as digits. In the phone number run every digit was right but the grouping was not, so a device reading it back would sound wrong while being right.

## C. Turn-taking

**At 0.2s, what kinds of normal speech get cut off? At 1.5s, what does the delay make the system seem like?**

At 0.2 seconds it felt like I had to get everything out fast. Any normal pause to think was treated as the end of my turn, so I was being cut off mid idea. "I want to order... the dumplings" came back as two separate turns:

```
[1.3s speech, 0.95s to transcribe]  I want to order...
[0.8s speech, 0.85s to transcribe]  the dumplings.
```

At 1.5 seconds it worked, but it felt a little dragged out. I pause a lot when I talk, so it never cut me off, but the wait after I finished was long enough to notice.

The default 0.4 seconds felt smooth. It never cut me off and it did not leave me waiting either, so this is the one that felt most like talking to something that was listening.

Echo bot at the default 0.4s:

```
  heard: I need to get bread.
  reply: You said: I need to get bread.
  [asr 0.89s | tts first audio 0.28s | total gap 1.17s]
```

## D. Storyboard

### The Negotiating Alarm

![Storyboard](images/storyboard.png)

The storyboard covers scenes 1 and 2 of the script below. Scenes 3 and 4 are the rest of the ladder, and scene 5 is design only.

**Process**

I commute to school and need to be there by 8:30, and I struggle with it every morning, so I wanted an alarm that fights back. I started by listing devices that would be funny to argue with and picked this one. My first version either allowed the snooze or refused it, which ends after one exchange. Having it counter-offer instead, less time plus one small task, gave it a reason to come back with a second question, and that second question is really the alarm. The ladder came from asking what happens if I just fall asleep again: each round halves the snooze and shortens the wait, and silence counts as a no. I also thought about having it text a family member to judge my excuse, and a mode where it narrates me not moving, but both need another person or voice, so they stayed as notes. Drawing the storyboard moved one thing. I had the device replaying my recorded promise late in the ladder, but in the panels it was clearly the moment that makes the idea work, so it became the first thing the device does when I go quiet.

**Dialogue script**

```
THE NEGOTIATING ALARM
Dialogue script, CS 5424 Lab 3 Part 1

Legend
[wait Ns]    device listens for up to N seconds, timed from the moment it stops speaking.
[sleep N]    device is silent and not listening for N.
[sensor]     the sensor decides whether a task was done. The question the device asks is what it says about it, not how it finds out. Water: glass lifted off a copper tape pad. Hand: palm on the capacitive pad on top of the device.
[off button] a physical red button. Stops everything at any point.

Rules
Answers the device understands: yes (yes, fine, ok, sure), no, a number of minutes, a day of the week.
Silence, mumbling, or anything it cannot map moves one rung down. It never stands still, whether it was a check or an offer.
Ladder: opening wait 20s. Then 5 min / 15s wait, 2 min / 10s, 1 min / 5s, then 30s grace with no question, then the alarm at full volume. Ten minutes is what I ask for, never what I get.
Times are rounded to the minute. Storyboard covers scenes 1 and 2. Scene 5 is design only, not in the Part 2 build.

SCENE 1, 6:45 AM, dark room

DEVICE:  It's 6:45.
         [wait 20s]
G:       Ten more minutes.
DEVICE:  Five. And you drink the water.
         [wait 15s]
G:       Fine.
DEVICE:  Say it.
         [wait 15s]
G:       I'll drink the water.
DEVICE:  Recorded. Five minutes.
         [sleep 5 min]

SCENE 2, 6:50 AM

DEVICE:  [sensor: glass still on the pad]
         Did you drink the water?
         [wait 15s]
G:       (nothing)
DEVICE:  [plays G's own voice] "I'll drink the water."
         [wait 10s]
G:       (mumbles)
DEVICE:  I didn't get that. Two minutes. Then you tell me what day it is.
         [wait 10s]
G:       Ok.
DEVICE:  Two minutes.
         [sleep 2 min]

SCENE 2 ALT, the happy path

DEVICE:  [sensor: glass lifted during the sleep]
         You drank the water. Good morning.
         [off]

SCENE 3, 6:53 AM

DEVICE:  What day is it?
         [wait 10s]
G:       Monday.
DEVICE:  It's Sunday. One minute. Then your hand on the device.
         [wait 5s]
G:       Ok.
DEVICE:  One minute.
         [sleep 1 min]

SCENE 3 ALT, the happy path

G:       Sunday.
DEVICE:  You're awake. Good morning.
         [off]

SCENE 4, 6:54 AM

DEVICE:  Hand on the device.
         [wait 5s, sensor: nothing]
         Thirty seconds.
         [sleep 30s]
         [alarm at full volume. No question. Stops only on sensor: hand on the device, or the off button.]

SCENE 5, 11:20 PM, same day (design only)

G:       Alarm for 6:45.
DEVICE:  6:45. You still owe me the water. That's first tomorrow.
         [off]
```

## E. Acting out the dialogue

I played the device, crouched behind the chair that stood in for the nightstand, and a friend played the sleeper on the couch without having seen the script. Before recording I revised the Part D script for acting: the alarm beeps first, the sleeper asks for more time instead of the device opening the negotiation, they have to repeat the deal back or the beeping continues, and after 20 seconds of silence the device hints that they can ask for more time.

**Recording:**

https://github.com/user-attachments/assets/9298a63a-34f8-49ea-b9be-eb7b9c311e3d

**Describe if the dialogue seemed different than what you imagined when it was acted out, and how.**

After the beeping, right away the participant stood up and drank the water. Then I replied, "You drank the water. Thank you. Good morning." And he went back on the couch. This tells me there's no actual way right now that the device communicates that it can interact with you, or invites it. Also, the user can just go back to sleep after drinking the water or turning off the alarm.

---

The idea, the storyboard panels, the dialogue script, and the substance of all written answers are mine. The storyboard drawing was generated with AI from my panel descriptions. I used Claude to write the greeting and number-asking scripts, to turn my spoken notes for Parts A to C into written answers that I approved, to proofread my writing, and to help revise the script for acting out in Part E. The Part E reflection is my own writing, with only typos fixed.

---

# Lab 3 Part 2

## Prep for Part 2

**1. What could be improved in the design?**

After acting it out, the biggest problem was that there was no way to confirm the person actually did anything. It also was not clear that you could talk to the device at all. The pauses were too long, and in my first prototype the line "Ask me for more time" was worded badly and sounded unnatural.

**2. Beyond speech: how does someone know when the device is listening, and when it is thinking?**

If the device says something inviting and then stops, especially if it ends on a question, you can assume it is listening. I don't think a light or a screen would help much with showing that it is thinking, because the person is half asleep and won't be processing things quickly either, so a few seconds of delay won't stand out. The beeping already does the most important job, which is telling you it is time to wake up.

**3. New storyboard, diagram or script**

The new script is the step-by-step flow under "Prototype: how the system works" below, with the device's actual lines. The main changes from the Part D script: the device now opens the conversation and asks "Do you need more time?" instead of waiting to be asked, the person has to say the deal back before the snooze starts, the snooze is silent, and the water task is checked with a sensor instead of being taken on trust.

## Prototype: how the system works

The device sits on my desk across the room from my bed, next to a glass of water. It is a Raspberry Pi 5 with a USB microphone, a USB speaker, and an MPR121 capacitive touch board connected over Qwiic. Everything is in [`speech-scripts/negotiating_alarm.py`](speech-scripts/negotiating_alarm.py).

**What it does, in order**

1. **Alarm.** It beeps, says "Good morning. It's 6:45.", and waits. If I say nothing, it beeps again and asks "Do you need more time?" In Part E nobody knew the device could be spoken to, so the device now asks the question itself instead of waiting to be asked.
2. **The deal.** If I ask for time, or just say "yeah", it offers at most five minutes, in exchange for drinking the water: "Ten is a lot. I'll give you five minutes, and then you drink that water. Say that back to me." If I talk without asking for time, it asks whether I want more time or am getting up.
3. **Say it back.** A plain "okay" is not enough ("I need to hear you say it."). I have to say the time and the water back to it. That sentence is recorded as my promise: "Okay. I'm holding you to that."
4. **Snooze.** Silent for the full time, whatever happens.
5. **Bugging.** If the glass has not been drunk from, the snooze is over for good: "Time's up, and that glass hasn't moved. Remember this?", and it plays my own recorded promise back to me. Then it asks what day it is, then "Last chance. Put your hand on me and I'll stop.", and goes back to beeping if all of those fail. Drinking the water at any point ends the alarm.

**Sensors**

- **Glass of water.** The glass sits on a pad of copper tape wired to pad 0 of the capacitive board. I measured it with a guided calibration mode (`--calibrate`): lifting the glass raises the reading by about 20, while a hand on the glass lowers it by about 40, so a touch cannot be mistaken for a lift. Drinking means the glass is off the pad for at least three seconds. A shorter lift is called out ("That was a lift, not a sip.").
- **Hand on the device.** Pads 6 to 11 on the board, touched directly.
- The pads are read 20 times a second on a background thread, so a drink taken while the device is talking is not missed.

**Speech**

- **Listening:** Silero voice activity detection decides when I have stopped talking, and faster-whisper (base.en) transcribes on the Pi. Base was the smallest model that got my own speech right in Part 1.
- **Understanding:** each transcript goes to a dialogue policy, which decides what I meant (asked for time, repeated the deal, refused, said the right day) and gives the device a short reaction line. There are two policies: simple keyword rules, and Claude (`claude-opus-5-5`) with a persona file, [`alarm_persona.md`](speech-scripts/alarm_persona.md), that describes the alarm's character. The program, not the model, owns the timings, the snooze length and the sensors, so the model can react but cannot give me more time.
- **Speaking:** OpenAI text-to-speech (`gpt-4o-mini-tts`, voice "marin", with the delivery instruction "Speak like a dry, unhurried hotel concierge. Deadpan, quietly amused."). I compared five voices with and without that instruction and picked this one by ear. Piper, which runs on the Pi, sounded too robotic for the character. Every fixed line is generated once in the background at startup and cached on the Pi, so only Claude's live reactions need a network request. If OpenAI can't be reached, the device falls back to Piper rather than going silent.

**Running it**

```
python negotiating_alarm.py --policy claude --tts openai             # real timings
python negotiating_alarm.py --policy claude --tts openai --speed 10  # snoozes 10x shorter, for demos
python negotiating_alarm.py --calibrate                              # measure the water pad
```

**Video of the system:**

https://github.com/user-attachments/assets/410e1d62-6f01-4a76-bca2-40778d98db66



## Test the system

### What worked well about the system and what didn't?
To do.

### What worked well about the controller and what didn't?
To do.

### What lessons can you take away from the WoZ interactions for designing a more autonomous version of the system?
To do.

### How could you use your system to create a dataset of interaction? What other sensing modalities would make sense to capture?
To do.

---

**Part 2 AI use.** The device design and the findings are mine. I used Claude (Claude Code) to write the device's code: the alarm flow, the sensor handling and calibration, and the dialogue policy. Claude also wrote up "how the system works" from the code, and wrote my prep answers 1 and 2 from what I told it, which I reviewed and approved. Inside the device, Claude (`claude-opus-5-5`) interprets what the person says, and OpenAI's `gpt-4o-mini-tts` speaks the device's lines.
