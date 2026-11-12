# Final Project

Concept, CS 5424 Fall 2026.

## Name

Akvar (means I'm here in Georgian)

## Team

Solo

## Big idea

Two small boxes that let two people say something to each other quickly, but only go live when both are there.

I can never catch my sister. She is in Armenia, nine hours ahead, and a call is too much for something real quick. I want what you get living with someone: you're both in the kitchen or at your desks and you just say something.

Each box notices when someone is near it and has a ring of light. The box only shows the other person while you're at yours, so it works like a window: if I can see her, she can see me, and nobody can check on the other from across the room. If she's there, the ring glows, I hold the button, talk, let go, and it plays on her box. She answers the same way. If she just left, the glow is fading and I know I just missed her. If she's not there, it waits as a voice message and plays when she walks up, but not in her night. Each day we catch each other, one of seven lights stays on, so the box shows our week.

Friendship lamps and the Good Night Lamp only send a signal one way. Alexa Drop In lets one person go live whether or not the other is there. This only goes live when both are, and it works the same in both directions.

## Timeline

Core loop: hold the button on box A, talk, let go, it plays on box B within about two seconds. Live talk and voice messages are the same clip, played now or later, so I build that first.

- Nov 11 to 15: two Pis on MQTT, button on A lights B, then a clip from A plays on B.
- Nov 16 and 18: push-to-talk both ways, presence sensors, glow only when both are at their boxes.
- Nov 19 to 25: hold clips when nobody's there, quiet hours (each box has its own time zone setting), fading glow, week lights, cardboard boxes, first test with two or three people.
- Week of Dec 1: check-off.
- Dec 1 to 5: test with classmates in two rooms and with my sister, then change things.
- Dec 7: show, boxes at opposite ends of the room.
- Dec 14: write-up and video.

## Parts needed

Two Pis (I have one), two USB mics and speakers (I have one set from Lab 3), two presence sensors (VL53L1X distance sensor or a PIR motion sensor), two NeoPixel rings, 14 small LEDs for the week lights, two Qwiic buttons. Python, MQTT, and the Lab 3 audio setup. My own broker for the test with my sister, since the class broker is shared.

## Fall-back plan

If audio between two boxes doesn't work by Dec 1, the far end becomes a phone web page. If presence sensing is unreliable, presence becomes a button. If the light ring is a problem, one LED at three brightness levels covers live, just missed and away, and the week lights get cut. For testing, a classmate can play clips by hand from a laptop.

## AI use

The idea is mine. Claude helped look up what exists and write this up.
