import sys
import time
import qwiic_proximity
import pi_servo_hat

# Pace Gate
# A VCNL4040 at the front of the plate sees the fork come in for a bite.
# Once the hand has pulled back out, the servo drops the cloche over the plate,
# holds it shut for a chewing pause, then lifts it again slowly.
# Reaching in while the lid is shut counts as a cheat.
#
#   python pace_gate.py            run the Pace Gate
#   python pace_gate.py --set 10   move the servo to one angle and hold it
#   python pace_gate.py --jog 10   start at 10, then type angles to move there slowly
#   python pace_gate.py --watch    print proximity readings only, for tuning

SERVO_CH = 0
# Angles, 0-120 for the kit micro servo. Higher angle closes the lid on this mount.
# Open stays well short of upright: once the lid tips past vertical the micro
# servo can't lift it back and stalls (it got hot doing exactly that).
LID_CLOSED = 100
LID_OPEN = 75   # 45 stood the lid fully upright (photos 2026-10-19), past where the servo can hold it

PAUSE_S = 10           # how long the lid stays shut after a bite (15 felt too long in testing)
GRACE_AFTER_OPEN_S = 2 # ignore the sensor right after the lid lifts, so grabbing the spoon back isn't a bite
BLOCKED_S = 3          # a reading that stays high this long is something sitting on the sensor, e.g. dropped food
CLEAR_DELAY_S = 0.5    # wait after the hand leaves before closing, so the lid never lands on it
OPEN_STEP = 1          # degrees per step when lifting; the slow lift is part of the joke
OPEN_STEP_DELAY = 0.03
CLOSE_STEP = 5
CLOSE_STEP_DELAY = 0.01

# Higher proximity = closer. Tune with --watch: note the reading with nothing
# over the sensor and with the fork right above it, and pick a value between.
# Measured with a spoon: 0-2 with nothing over the sensor, 65-100 at ~5 cm.
# A natural bite flat on the base only read 15-20, so the sensor was raised ~4-5 cm:
# then 3-8 idle (lid and bowl reflect a little), natural bites peak around 60.
BITE_THRESHOLD = 30
REARM_THRESHOLD = 15   # must drop below this before the next bite can count


def move(servo, start, end, step, delay):
    step = step if end >= start else -step
    for angle in range(start, end, step):
        servo.move_servo_position(SERVO_CH, angle)
        time.sleep(delay)
    servo.move_servo_position(SERVO_CH, end)


def setup_sensor():
    sensor = qwiic_proximity.QwiicProximity()
    if not sensor.connected:
        raise RuntimeError("VCNL4040 not found. Check the Qwiic connection.")
    sensor.begin()
    return sensor


def setup_servo():
    servo = pi_servo_hat.PiServoHat()
    servo.restart()
    return servo


def watch():
    sensor = setup_sensor()
    print("Printing proximity. Ctrl+C to stop.")
    try:
        while True:
            print(f"Proximity: {sensor.get_proximity():6d}", end="\r")
            time.sleep(0.05)
    except KeyboardInterrupt:
        print()


def safe(angle):
    # Never go below LID_OPEN: past it the lid tips back and the servo stalls.
    # Higher angles close the lid, so the top end is just the servo's 120 limit.
    lo, hi = LID_OPEN, 120
    if not lo <= angle <= hi:
        print(f"{angle} is outside the safe range {lo}-{hi}; using {max(lo, min(hi, angle))}.")
    return max(lo, min(hi, angle))


def set_angle(angle):
    angle = safe(angle)
    servo = setup_servo()
    servo.move_servo_position(SERVO_CH, angle)
    print(f"Servo on channel {SERVO_CH} at {angle} degrees. Ctrl+C to release.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print()


def jog(start):
    # Start at the angle the servo is already at, so it doesn't jump.
    servo = setup_servo()
    angle = safe(start)
    servo.move_servo_position(SERVO_CH, angle)
    print(f"At {angle}. Type an angle and Enter to move there slowly; blank Enter to quit.")
    while True:
        target = input("angle> ").strip()
        if not target:
            break
        target = safe(int(target))
        move(servo, angle, target, 1, 0.04)
        angle = target
        print(f"At {angle}.")


def run():
    sensor = setup_sensor()
    servo = setup_servo()
    servo.move_servo_position(SERVO_CH, LID_OPEN)

    bites = 0
    cheats = 0
    hand_in = False
    in_since = 0.0
    blocked = False
    ignore_until = 0.0
    print(f"Pace Gate ready. Bite threshold {BITE_THRESHOLD}, pause {PAUSE_S}s.")

    try:
        while True:
            proximity = sensor.get_proximity()
            print(f"Proximity: {proximity:6d}  bites: {bites}  cheats: {cheats}", end="\r")

            if time.time() < ignore_until:
                hand_in = False
            elif not hand_in and proximity > BITE_THRESHOLD:
                hand_in = True
                in_since = time.time()
            elif hand_in and not blocked and time.time() - in_since > BLOCKED_S:
                # A hand passes over in about a second; this has sat there too long.
                blocked = True
                print("\nSensor covered. Wipe it off; not counting this as a bite.")
            elif hand_in and proximity < REARM_THRESHOLD:
                hand_in = False
                if blocked:
                    blocked = False
                    print("Sensor clear again.")
                    continue
                # The spoon has come in and gone back out: that's a bite.
                bites += 1
                print(f"\nBite {bites}. Closing.")
                time.sleep(CLEAR_DELAY_S)
                move(servo, LID_OPEN, LID_CLOSED, CLOSE_STEP, CLOSE_STEP_DELAY)

                shut_until = time.time() + PAUSE_S
                reaching = False
                while time.time() < shut_until:
                    proximity = sensor.get_proximity()
                    if not reaching and proximity > BITE_THRESHOLD:
                        reaching = True
                        cheats += 1
                        print(f"Cheat {cheats}: reached in while shut.")
                    elif reaching and proximity < REARM_THRESHOLD:
                        reaching = False
                    time.sleep(0.05)

                print("Opening.")
                move(servo, LID_CLOSED, LID_OPEN, OPEN_STEP, OPEN_STEP_DELAY)
                ignore_until = time.time() + GRACE_AFTER_OPEN_S
            time.sleep(0.05)

    except KeyboardInterrupt:
        print(f"\nStopping. {bites} bites, {cheats} cheats.")
        servo.move_servo_position(SERVO_CH, LID_OPEN)


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--set":
        set_angle(int(sys.argv[2]))
    elif len(sys.argv) >= 3 and sys.argv[1] == "--jog":
        jog(int(sys.argv[2]))
    elif len(sys.argv) >= 2 and sys.argv[1] == "--watch":
        watch()
    else:
        run()
