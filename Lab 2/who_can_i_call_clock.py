import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import board
import digitalio
import lgpio
from PIL import Image, ImageDraw, ImageFont
import adafruit_rgb_display.st7789 as st7789
from twilio.rest import Client

from who_can_i_call_config import (
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_FROM_NUMBER,
    MY_PHONE_NUMBER,
    PEOPLE,
)

# --- Display setup (same pinout as screen_clock.py) ---
cs_pin = digitalio.DigitalInOut(board.D5)
dc_pin = digitalio.DigitalInOut(board.D25)
spi = board.SPI()
disp = st7789.ST7789(
    spi, cs=cs_pin, dc=dc_pin, rst=None, baudrate=64000000,
    width=135, height=240, x_offset=53, y_offset=40,
)
width, height = disp.height, disp.width  # landscape
rotation = 90

image = Image.new("RGB", (width, height))
draw = ImageDraw.Draw(image)

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
name_font = ImageFont.truetype(FONT_BOLD, 15)
time_font = ImageFont.truetype(FONT_BOLD, 42)
calling_font = ImageFont.truetype(FONT_BOLD, 28)
status_font = ImageFont.truetype(FONT, 13)
hint_font = ImageFont.truetype(FONT, 11)

# Backlight is dimmed via software PWM (a plain on/off digitalio pin can't
# dim) -- lower BACKLIGHT_PERCENT for less brightness/reflection on camera.
BACKLIGHT_PERCENT = 15
_backlight_handle = lgpio.gpiochip_open(0)
lgpio.gpio_claim_output(_backlight_handle, 22)
lgpio.tx_pwm(_backlight_handle, 22, 1000, BACKLIGHT_PERCENT)

buttonA = digitalio.DigitalInOut(board.D23)
buttonB = digitalio.DigitalInOut(board.D24)
buttonA.switch_to_input(pull=digitalio.Pull.UP)
buttonB.switch_to_input(pull=digitalio.Pull.UP)

# --- Awake-hours model ---
AWAKE_START = 8   # 08:00 local: fully callable from here
AWAKE_END = 22     # 22:00 local: fully callable until here
EDGE_HOURS = 1     # hours on either side of the awake window shown as amber

BG = (22, 22, 26)
TEXT = (240, 238, 235)
MUTED = (140, 138, 135)
GREEN = (110, 200, 140)
AMBER = (230, 170, 90)
ROSE = (210, 110, 110)


def status_for(hour_float):
    if AWAKE_START <= hour_float < AWAKE_END:
        return GREEN, "Good time to call"
    if AWAKE_START - EDGE_HOURS <= hour_float < AWAKE_START or AWAKE_END <= hour_float < AWAKE_END + EDGE_HOURS:
        return AMBER, "Might be waking / winding down"
    return ROSE, "Probably asleep"


def is_callable(hour_float):
    color, _ = status_for(hour_float)
    return color == GREEN


def center_text(cx, y, text, font, fill):
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    draw.text((cx - w / 2, y), text, font=font, fill=fill)


def draw_page_dots(current_index, count):
    dot_r = 2
    gap = 10
    total_w = (count - 1) * gap
    start_x = width / 2 - total_w / 2
    y = height - 10
    for i in range(count):
        x = start_x + i * gap
        color = TEXT if i == current_index else (60, 60, 65)
        draw.ellipse((x - dot_r, y - dot_r, x + dot_r, y + dot_r), fill=color)


def place_call(person, result_box):
    result_box["status"] = "calling"
    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        # Ring the contact; once they answer, bridge in MY_PHONE_NUMBER so
        # it's a real two-way call, not just a one-way announcement.
        twiml = (
            f'<Response><Dial callerId="{TWILIO_FROM_NUMBER}">'
            f'{MY_PHONE_NUMBER}</Dial></Response>'
        )
        client.calls.create(
            to=person["phone"],
            from_=TWILIO_FROM_NUMBER,
            twiml=twiml,
        )
        result_box["status"] = "calling"
    except Exception as e:  # surfaced on screen, never logged with secrets
        result_box["status"] = f"failed: {type(e).__name__}"
    result_box["until"] = time.monotonic() + 3


current_index = 0
confirming = False
call_result = {"status": None, "until": 0}
a_prev = True  # DigitalInOut reads True when NOT pressed (pull-up)
b_prev = True

while True:
    draw.rectangle((0, 0, width, height), fill=BG)

    a_now = buttonA.value
    b_now = buttonB.value
    a_pressed = a_prev and not a_now  # falling edge
    b_pressed = b_prev and not b_now
    a_prev, b_prev = a_now, b_now

    person = PEOPLE[current_index]
    now_local = datetime.now(ZoneInfo(person["timezone"]))
    hour_float = now_local.hour + now_local.minute / 60
    color, label = status_for(hour_float)

    calling_active = call_result["status"] and time.monotonic() < call_result["until"]

    if b_pressed:
        if confirming:
            confirming = False
        elif not calling_active:
            current_index = (current_index + 1) % len(PEOPLE)

    if a_pressed and not confirming and not calling_active:
        if is_callable(hour_float):
            threading.Thread(target=place_call, args=(person, call_result), daemon=True).start()
        else:
            confirming = True
    elif a_pressed and confirming:
        confirming = False
        threading.Thread(target=place_call, args=(person, call_result), daemon=True).start()

    # Name + status dot, always shown at the top
    draw.ellipse((10, 12, 18, 20), fill=color)
    draw.text((24, 8), person["name"], font=name_font, fill=TEXT)

    if calling_active:
        status_text = call_result["status"]
        if status_text.startswith("failed"):
            center_text(width / 2, 40, "Call failed", calling_font, ROSE)
            center_text(width / 2, 84, status_text, status_font, MUTED)
        else:
            center_text(width / 2, 46, "Calling…", calling_font, TEXT)
            center_text(width / 2, 84, person["name"], status_font, MUTED)
    elif confirming:
        center_text(width / 2, 26, now_local.strftime("%H:%M"), time_font, TEXT)
        center_text(width / 2, 76, label, status_font, color)
        draw.line((30, 96, width - 30, 96), fill=(50, 50, 55), width=1)
        draw.text((10, 104), "A  call anyway", font=hint_font, fill=TEXT)
        draw.text((width - 78, 104), "B  cancel", font=hint_font, fill=MUTED)
    else:
        center_text(width / 2, 34, now_local.strftime("%H:%M"), time_font, TEXT)
        center_text(width / 2, 84, label, status_font, color)
        draw.text((10, height - 22), "B  next", font=hint_font, fill=MUTED)
        draw.text((width - 60, height - 22), "A  call", font=hint_font, fill=MUTED)
        draw_page_dots(current_index, len(PEOPLE))

    disp.image(image, rotation)
    time.sleep(0.1)
