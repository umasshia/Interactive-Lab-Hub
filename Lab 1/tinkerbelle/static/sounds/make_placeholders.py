"""Placeholder sounds for the Borderless remix, synthesised so the prototype runs offline today.
Replace the files in static/sounds/ with real recordings when you have them; same names.
  ambient.wav  24 s seamless loop: two soft drones that swell and ebb like breathing, plus a low wash
  tap.wav      soft bell, half a second
  swipe.wav    short whoosh of filtered noise
"""
import numpy as np, wave, sys, os
SR = 44100
out = sys.argv[1]
os.makedirs(out, exist_ok=True)

def save(name, x):
    x = np.clip(x, -1, 1)
    with wave.open(os.path.join(out, name), 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((x * 32767).astype('<i2').tobytes())

def onepole(x, cutoff):
    """simple lowpass; cutoff may be an array (Hz per sample) for sweeps"""
    cutoff = np.broadcast_to(cutoff, x.shape)
    a = np.exp(-2 * np.pi * cutoff / SR)
    y = np.zeros_like(x); s = 0.0
    for i in range(len(x)):
        s = a[i] * s + (1 - a[i]) * x[i]; y[i] = s
    return y

# ---- ambient: 24 s loop. Drone frequencies chosen so an integer number of cycles fits in 24 s,
# and the breathing LFO period divides 24, so the loop point is seamless.
DUR = 24
t = np.arange(int(SR * DUR)) / SR
breath = 0.5 - 0.5 * np.cos(2 * np.pi * t / 6)            # 6 s in-out, 0..1
drone = (0.35 * np.sin(2 * np.pi * 110 * t) + 0.25 * np.sin(2 * np.pi * 165 * t)
         + 0.15 * np.sin(2 * np.pi * 220 * t) + 0.10 * np.sin(2 * np.pi * 137.5 * t))
drone *= 0.35 + 0.65 * breath
rng = np.random.default_rng(3)
wash = rng.standard_normal(len(t))
wash = onepole(wash, 260) * 3.0 * (0.2 + 0.8 * breath)     # low, breathy
amb = 0.45 * drone + 0.25 * wash
# crossfade the noise seam so the loop is click-free
n = SR // 2
ramp = np.linspace(0, 1, n)
amb[:n] = amb[:n] * ramp + amb[-n:] * (1 - ramp)
amb[-n:] = amb[:n]
save('ambient.wav', amb * 0.6)

# ---- tap: soft bell
DUR = 0.55
t = np.arange(int(SR * DUR)) / SR
env = np.minimum(t / 0.004, 1) * np.exp(-t / 0.16)
bell = (np.sin(2 * np.pi * 660 * t) * np.exp(-t / 0.20) + 0.5 * np.sin(2 * np.pi * 1320 * t) * np.exp(-t / 0.09)
        + 0.25 * np.sin(2 * np.pi * 1980 * t) * np.exp(-t / 0.05))
save('tap.wav', bell * env * 0.5)

# ---- swipe: whoosh, noise through a lowpass that sweeps up then down
DUR = 0.6
t = np.arange(int(SR * DUR)) / SR
sweep = 300 + 2500 * np.sin(np.pi * t / DUR) ** 2
noise = rng.standard_normal(len(t))
wh = onepole(noise, sweep)
env = np.sin(np.pi * t / DUR) ** 1.5
save('swipe.wav', wh * env * 1.8)
print('wrote', os.listdir(out))
