import time
from time import strftime
import digitalio
import board
from PIL import Image, ImageDraw, ImageFont
import adafruit_rgb_display.st7789 as st7789

# Configuration for CS and DC pins (these are FeatherWing defaults on M0/M4):
cs_pin = digitalio.DigitalInOut(board.D5)
dc_pin = digitalio.DigitalInOut(board.D25)
reset_pin = None

# Config for display baudrate (default max is 24mhz):
BAUDRATE = 64000000

# Setup SPI bus using hardware SPI:
spi = board.SPI()

# Create the ST7789 display:
disp = st7789.ST7789(
    spi,
    cs=cs_pin,
    dc=dc_pin,
    rst=reset_pin,
    baudrate=BAUDRATE,
    width=135,
    height=240,
    x_offset=53,
    y_offset=40,
)

# Create blank image for drawing.
height = disp.width  # we swap height/width to rotate it to landscape!
width = disp.height
image = Image.new("RGB", (width, height))
rotation = 90

draw = ImageDraw.Draw(image)

font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)

# Turn on the backlight
backlight = digitalio.DigitalInOut(board.D22)
backlight.switch_to_output()
backlight.value = True

# One small modification on top of the barebones clock: 12 candles, drawn
# as plain rectangles, one per 2-hour block of the day. Each one shrinks
# as its block burns down, so the row doubles as a coarse hour marker.
NUM_CANDLES = 12
CANDLE_WIDTH = 14
CANDLE_GAP = 5
CANDLE_MAX_HEIGHT = 60
CANDLE_BASE_Y = height - 10

while True:
    draw.rectangle((0, 0, width, height), outline=0, fill=(0, 0, 0))

    now = strftime("%m/%d/%Y %H:%M:%S")
    draw.text((0, -2), now, font=font, fill=(255, 255, 255))

    localtime = time.localtime()
    current_block = localtime.tm_hour // 2
    burn_fraction = ((localtime.tm_hour % 2) * 60 + localtime.tm_min) / 120

    for i in range(NUM_CANDLES):
        x = 4 + i * (CANDLE_WIDTH + CANDLE_GAP)
        if i < current_block:
            candle_height = 6  # already burned out
        elif i == current_block:
            candle_height = max(6, int(CANDLE_MAX_HEIGHT * (1 - burn_fraction)))
        else:
            candle_height = CANDLE_MAX_HEIGHT  # not lit yet
        draw.rectangle(
            (x, CANDLE_BASE_Y - candle_height, x + CANDLE_WIDTH, CANDLE_BASE_Y),
            fill=(255, 210, 130),
        )

    # Display image.
    disp.image(image, rotation)
    time.sleep(1)
