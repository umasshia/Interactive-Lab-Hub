# Final Project

Concept, CS 5424 Fall 2026.

## Big idea

Two small boxes that let two people say something to each other quickly, but only go live when both are there.

I can never catch my sister. She is in Berlin, six hours ahead, and a call is too much for something real quick. I want what you get living with someone: you're both in the kitchen or at your desks and you just say something.

Each box has a proximity sensor and a light that shows if the other person is near their box. If she's there, I hold the button, talk, let go, and it plays on her box. She answers the same way. If she's not there, it waits as a voice message and plays when she walks up, but not in her night.

Friendship lamps and the Good Night Lamp only send a signal. Alexa Drop In goes live whether or not the other person is there. This only goes live when both are.

## Timeline

Core loop: hold the button on box A, talk, let go, it plays on box B within about two seconds. Live talk and voice messages are the same clip, played now or later, so I build that first.

- Nov 11 to 15: two Pis on MQTT, button on A lights B, then a clip from A plays on B.
- Nov 16 and 18: push-to-talk both ways, proximity sensors, presence light.
- Nov 19 to 25: hold clips when nobody's there, quiet hours (each box has its own time zone setting), cardboard boxes, first test with two or three people.
- Week of Dec 1: check-off.
- Dec 1 to 5: test with classmates in two rooms and with my sister, then change things.
- Dec 7: show, boxes at opposite ends of the room.
- Dec 14: write-up and video.

## Parts needed

Two Pis (I have one), two USB mics and speakers (I have one set from Lab 3), proximity sensors (VCNL4040 or APDS-9960), Qwiic buttons, LEDs or the PiTFT. Python, MQTT, and the Lab 3 audio setup. My own broker for the test with my sister, since the class broker is shared.

## Fall-back plan

If audio between two boxes doesn't work by Dec 1, the far end becomes a phone web page. If proximity is unreliable, presence becomes a button. For testing, a teammate can play clips by hand from a laptop.

## AI use

The idea is mine. Claude helped look up what exists and write this up.
