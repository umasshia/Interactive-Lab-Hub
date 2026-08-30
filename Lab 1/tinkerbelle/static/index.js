const control = document.getElementById('control');

// ============================================================================
// Optional shapes for the light page. Open the light as
//   http://<ip>:5001/?mode=glow    one soft patch of colour, dark edges
//   http://<ip>:5001/?mode=blobs   a field of flowers that breathe, on a <canvas>
// With no ?mode the page stays a plain flat colour (original behaviour).
//
// blobs options (all in the URL):
//   spread=<ms>   how long a colour change takes to travel across the field (default 900)
//   dir=<right|left|up|down|angle-in-degrees>   direction petals move on a swipe/poke (default right)
//   count=<n>     how many flowers (default 320)
//   seed=<n>      change the layout
//   tone=<hex>    starting colour before the wizard sends anything (e.g. tone=ff2fa0)
//
// Performance model: every flower is pre-rendered ONCE as a small greyscale sprite. Each frame
// the sprites are tinted (only when their colour changed) and drawn onto one canvas with
// additive blending. 300+ moving, blending flowers cost a few hundred small draw calls per
// frame, which the GPU-backed 2D canvas handles easily - unlike 300+ DOM elements.
// ============================================================================
const params = new URLSearchParams(window.location.search);
// ?debug=1 shows runtime errors on the page itself (useful on a phone with no console)
if (params.get('debug')) window.addEventListener('error', (e) => {
  const d = document.createElement('pre');
  d.style.cssText = 'position:fixed;top:40px;left:0;color:#f66;background:#000;z-index:9;font:14px monospace;white-space:pre-wrap;';
  d.textContent = `${e.message}\n${(e.filename || '').split('/').pop()}:${e.lineno}`;
  document.body.appendChild(d);
});
const lightMode = params.get('mode');
const spreadMs = Number(params.get('spread') || 900);
const blobCount = Number(params.get('count') || 320);

// deterministic pseudo-random so the layout is the same on every reload (change ?seed= to reshuffle)
let seed = Number(params.get('seed') || 7);
const rand = () => { seed = (seed * 1664525 + 1013904223) % 4294967296; return seed / 4294967296; };

// ---- layout: organic placement in three depth tiers. [x%, y%, radius% of the long screen edge, opacity]
const blobSpots = [];
{
  let tries = 0;
  while (blobSpots.length < blobCount && tries++ < blobCount * 40) {
    const u = rand();
    const tier = u < 0.08 ? 2 : u < 0.45 ? 1 : 0;
    const r = tier === 2 ? 8 + rand() * 6 : tier === 1 ? 3.2 + rand() * 2.2 : 1.7 + rand() * 1.3;
    const x = 2 + rand() * 96, y = 2 + rand() * 96;
    const minGap = tier === 0 ? 2.0 : tier === 1 ? 3.2 : 9;
    if (blobSpots.some(([bx, by, br]) => Math.hypot(bx - x, by - y) < minGap && (br > 6) === (r > 6))) continue;
    blobSpots.push([x, y, r, tier === 2 ? 0.32 : tier === 1 ? 0.85 : 0.95]);
  }
  blobSpots.sort((a, b) => b[2] - a[2]);   // big faint glows first, so they sit behind the flowers
}
const isGlow = blobSpots.map(([, , r]) => r > 6);

// ---- colour ripple: changes travel outward from the centre of the field
const origin = [50, 50];
const maxDist = Math.max(...blobSpots.map(([x, y]) => Math.hypot(x - origin[0], y - origin[1])));
const blobDelay = blobSpots.map(([x, y]) => Math.hypot(x - origin[0], y - origin[1]) / maxDist * spreadMs);

function dirVector(d) {
  const named = { right: 0, left: 180, up: 270, down: 90 };
  const deg = d in named ? named[d] : Number(d);
  return [Math.cos(deg * Math.PI / 180), Math.sin(deg * Math.PI / 180)];
}
const defaultDir = params.get('dir') || 'right';

// ---- history of received colours, so delayed flowers can look into the past
const colorHistory = [];
if (params.get('tone')) colorHistory.push([0, '#' + params.get('tone').replace('#', '')]);
function colorAt(msAgo) {
  const t = performance.now() - msAgo;
  let best = colorHistory[0] && colorHistory[0][1];
  for (const [when, c] of colorHistory) {
    if (when <= t) best = c; else break;
  }
  return best;
}

// ---- hand gestures: the wizard mimics what the visitor's hand does at the wall.
// Every gesture is a "hand": a point that moves along a path for a while and pushes, pulls or
// carries the flowers near it. Flowers keep a displacement (offX/offY) that always decays back
// home, so after any gesture the field slowly returns to how it was.
//   tap    (Space)      a quick burst at the touch point: nearby flowers jump outward, then settle
//   swipe  (arrow keys) a hand sweeps through the point in that direction; flowers part in its wake
//   drag   (D)          a slow hand moves through; flowers near it are carried along, then released
//   hold   (H)          a hand rests on the wall; flowers gather in toward it, then drift back
// The touch point is the middle of the field unless the light URL says ?point=x,y (percent).
const handPoint = (params.get('point') || '50,50').split(',').map(Number);
const hands = [];   // {t0, kind, from:[x,y], to:[x,y], ms, radius, force, mode}
// Flowers have velocity: a hand accelerates them, they coast and slow (VEL_TAU), and their
// displacement then drifts home (RETURN_TAU). So nothing teleports - it starts, moves, settles.
//   force  = acceleration in %/s^2 at zero distance (swipe/drag/hold, applied while the hand is near)
//   kick   = one-off velocity in %/s given when the tap's ripple front passes a flower
const GESTURES = {
  tap:   { ms: 700,  radius: 22, kick: 34,   mode: 'ripple',  travel: 0 },
  swipe: { ms: 900,  radius: 14, force: 180, mode: 'repel',   travel: 70 },
  drag:  { ms: 2600, radius: 12, force: 110, mode: 'carry',   travel: 55 },
  hold:  { ms: 3000, radius: 22, rate: 1.6,  mode: 'bloom',   travel: 0 },   // rate = how fast the bloom builds, per second
};
const VEL_TAU = 0.28;   // seconds for a pushed flower to coast to a stop
function triggerHand(kind, opts) {
  const g = GESTURES[kind]; if (!g) return;
  const x = (opts && opts.x) ?? handPoint[0], y = (opts && opts.y) ?? handPoint[1];
  const vec = dirVector((opts && opts.dir) || defaultDir);
  const half = g.travel / 2;
  hands.push({ t0: performance.now(), kind, ...g, hit: new Set(),
    from: [x - vec[0] * half, y - vec[1] * half], to: [x + vec[0] * half, y + vec[1] * half], vec });
}
// where a hand is, 0..1 along its path, eased so it starts and stops gently
function handPos(h, now) {
  const u = Math.min(1, (now - h.t0) / h.ms);
  const e = h.travel ? d3.easeSinInOut(u) : 0;
  return [h.from[0] + (h.to[0] - h.from[0]) * e, h.from[1] + (h.to[1] - h.from[1]) * e, u];
}

// ---- flick (Enter): the flower nearest the touch point is sent flying in the swipe direction.
// It's the same flower - nothing appears or disappears. It coasts a long way (FLICK_TAU),
// shoves whatever it passes, then drifts back home slowly with everything else.
// per-flower motion state, in % of the screen: displacement from home, velocity, and excitement
const offX = blobSpots.map(() => 0), offY = blobSpots.map(() => 0);
const velX = blobSpots.map(() => 0), velY = blobSpots.map(() => 0);
const bloom = blobSpots.map(() => 0);    // 0..1: how excited a flower is (hold gesture); fades on its own
const BLOOM_TAU = 1.8;                   // seconds for the excitement to fade after the hand leaves
const FLICK_SPEED = 70;         // initial speed, % of screen per second
const FLICK_TAU = 0.9;          // seconds it keeps coasting (longer than a normal push)
const FLICK_RADIUS = 14;        // how close a flower must be to get shoved by the flier
const FLICK_SHOVE = 420;        // shove acceleration at zero distance
const RETURN_TAU = 4500;        // ms time-constant for displaced flowers drifting back
const flying = new Set();       // flowers currently flying (use the longer coast)
function triggerPoke(opts) {
  const x = (opts && opts.x) ?? handPoint[0], y = (opts && opts.y) ?? handPoint[1];
  const vec = dirVector((opts && opts.dir) || defaultDir);
  let hero = -1, best = Infinity;
  blobSpots.forEach(([bx, by], i) => {
    if (isGlow[i]) return;
    const d = Math.hypot(bx + offX[i] - x, by + offY[i] - y); if (d < best) { best = d; hero = i; }
  });
  if (hero < 0) return;
  velX[hero] += vec[0] * FLICK_SPEED; velY[hero] += vec[1] * FLICK_SPEED;
  flying.add(hero);
}

// ---- per-flower personality
const phase = blobSpots.map((_, i) => i * 1.7);
const rotation = blobSpots.map(() => rand() * 360);
const wander = blobSpots.map(() => [9000 + rand() * 12000, 11000 + rand() * 14000, 1.5 + rand() * 2.5]); // [period x, period y, amplitude %]
const heartYellow = blobSpots.map(() => rand() < 0.7);
// Hue spread around the tone: most flowers near it, a good share well away, some opposite.
// A warm tone gives reds/oranges/magentas with blue accents; a cold tone gives blues/purples/teals.
const hueJitter = blobSpots.map(() => {
  const u = rand(), sign = rand() < 0.5 ? -1 : 1;
  if (u < 0.5) return sign * rand() * 35;
  if (u < 0.85) return sign * (35 + rand() * 55);
  return 150 + rand() * 60;
});
const lightJitter = blobSpots.map(() => (rand() - 0.5) * 24);
function tint(color, i) {
  const c = d3.hcl(color);
  if (isNaN(c.h)) return color;                       // black / grey: leave alone
  c.h += hueJitter[i]; c.l = Math.max(0, c.l + lightJitter[i]); c.c = c.c * 1.15 + 12;
  return c.formatRgb();
}

// ---- sprites: greyscale flower shapes with the shading baked in, built once
const S = 128;                                   // sprite size in px
function makeCanvas() { const c = document.createElement('canvas'); c.width = S; c.height = S; return c; }
const flowerVariants = [                         // [petals, rx, ry, inner ring?]
  [5, 15, 21, false], [6, 13, 21, false], [5, 17, 19, false], [5, 14, 20, true], [6, 12, 20, true],
];
function petalPath(ctx, cx, cy, rx, ry, angle) {
  ctx.save(); ctx.translate(cx, cy); ctx.rotate(angle);
  ctx.beginPath(); ctx.ellipse(0, 0, rx, ry, 0, 0, Math.PI * 2); ctx.restore();
}
function buildFlowerSprite(variant) {
  const [petals, rx, ry, inner] = variant;
  const cv = makeCanvas(), ctx = cv.getContext('2d');
  const k = 1.15, C = S / 2;                     // viewBox 100 -> sprite px
  ctx.filter = 'blur(2px)';
  const drawRing = (n, prx, pry, dist, offset, lum) => {
    for (let i = 0; i < n; i++) {
      const a = (i + offset) * 2 * Math.PI / n;
      const cx = C + Math.sin(a) * dist, cy = C - Math.cos(a) * dist;
      const g = ctx.createLinearGradient(C, C, cx + Math.sin(a) * pry, cy - Math.cos(a) * pry);
      const base = Math.round(255 * lum * (i % 2 ? 0.9 : 1)), tipv = Math.round(150 * lum);
      g.addColorStop(0, `rgb(${base},${base},${base})`);
      g.addColorStop(1, `rgb(${tipv},${tipv},${tipv})`);
      ctx.fillStyle = g;
      petalPath(ctx, cx, cy, prx, pry, a); ctx.fill();
    }
  };
  drawRing(petals, rx * k, ry * k, (ry + 2) * k, 0, 1);
  if (inner) drawRing(petals, rx * 0.8 * k, ry * 0.6 * k, ry * 0.55 * k, 0.5, 0.95);
  ctx.fillStyle = '#ffffff'; ctx.beginPath(); ctx.arc(C, C, 11 * k, 0, Math.PI * 2); ctx.fill();
  ctx.filter = 'none';
  return cv;
}
function buildGlowSprite() {
  const cv = makeCanvas(), ctx = cv.getContext('2d');
  const g = ctx.createRadialGradient(S / 2, S / 2, 0, S / 2, S / 2, S / 2);
  g.addColorStop(0, 'rgba(255,255,255,1)'); g.addColorStop(0.35, 'rgba(255,255,255,0.55)'); g.addColorStop(1, 'rgba(255,255,255,0)');
  ctx.fillStyle = g; ctx.fillRect(0, 0, S, S);
  return cv;
}
function buildHeartSprite(yellow) {
  const cv = makeCanvas(), ctx = cv.getContext('2d');
  const g = ctx.createRadialGradient(S / 2, S / 2, 0, S / 2, S / 2, 15);
  if (yellow) { g.addColorStop(0, '#fff3b0'); g.addColorStop(0.5, 'rgba(255,209,102,0.9)'); g.addColorStop(1, 'rgba(255,209,102,0)'); }
  else { g.addColorStop(0, 'rgba(255,255,255,0.95)'); g.addColorStop(0.5, 'rgba(255,255,255,0.5)'); g.addColorStop(1, 'rgba(255,255,255,0)'); }
  ctx.fillStyle = g; ctx.fillRect(0, 0, S, S);
  return cv;
}

let canvas, ctx, W = 0, H = 0, dpr = 1;
let shapeSprites = [], heartSprites = [], tinted = [], tintedColor = [];
if (lightMode) {
  document.documentElement.style.height = '100%';
  document.body.style.margin = '0';
  document.body.style.minHeight = '100vh';
  document.body.style.overflow = 'hidden';
  document.body.style.background = '#000';
}
if (lightMode === 'blobs') {
  canvas = document.createElement('canvas');
  canvas.style.cssText = 'position:fixed;inset:0;width:100%;height:100%;z-index:-1;';
  document.body.appendChild(canvas);
  ctx = canvas.getContext('2d');
  const resize = () => {
    dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    W = window.innerWidth; H = window.innerHeight;
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
  };
  resize(); window.addEventListener('resize', resize);
  const variantSprites = flowerVariants.map(buildFlowerSprite);
  const glowSprite = buildGlowSprite();
  const heartY = buildHeartSprite(true), heartW = buildHeartSprite(false);
  shapeSprites = blobSpots.map((_, i) => isGlow[i] ? glowSprite : variantSprites[Math.floor(rand() * variantSprites.length)]);
  heartSprites = blobSpots.map((_, i) => isGlow[i] ? null : (heartYellow[i] ? heartY : heartW));
  tinted = blobSpots.map(makeCanvas);
  tintedColor = blobSpots.map(() => null);
}

// Tint a greyscale sprite with a colour, keeping its shading: multiply, then restore the alpha.
function retint(i, color) {
  const t = tinted[i].getContext('2d');
  t.globalCompositeOperation = 'source-over';
  t.clearRect(0, 0, S, S);
  t.drawImage(shapeSprites[i], 0, 0);
  t.globalCompositeOperation = 'multiply';
  t.fillStyle = color; t.fillRect(0, 0, S, S);
  t.globalCompositeOperation = 'destination-in';
  t.drawImage(shapeSprites[i], 0, 0);
  t.globalCompositeOperation = 'source-over';
  if (heartSprites[i]) {
    // the heart keeps its own colour but dims with the tone, so a fade to black takes it too
    t.globalAlpha = Math.max(0, Math.min(1, d3.hcl(color).l / 55));
    t.drawImage(heartSprites[i], 0, 0);
    t.globalAlpha = 1;
  }
  tintedColor[i] = color;
}

let lastFrame = performance.now();
function renderBlobs() {
  const now = performance.now();
  const dt = Math.min((now - lastFrame) / 1000, 0.05); lastFrame = now;

  // flying flowers shove whatever they pass; once slow, they're ordinary again
  for (const hero of [...flying]) {
    const speed = Math.hypot(velX[hero], velY[hero]);
    if (speed < 4) { flying.delete(hero); continue; }
    const hx = blobSpots[hero][0] + offX[hero], hy = blobSpots[hero][1] + offY[hero];
    blobSpots.forEach(([bx, by], j) => {
      if (j === hero || isGlow[j]) return;
      const ddx = bx + offX[j] - hx, ddy = by + offY[j] - hy, dist = Math.hypot(ddx, ddy);
      if (dist < FLICK_RADIUS && dist > 0.01) {
        const a = (1 - dist / FLICK_RADIUS) * FLICK_SHOVE * Math.min(1, speed / 40) * dt;
        velX[j] += ddx / dist * a; velY[j] += ddy / dist * a;
      }
    });
  }
  // hands accelerate the flowers near them
  for (const h of hands) {
    const [hx, hy, u] = handPos(h, performance.now());
    if (h.mode === 'ripple') {
      // an expanding ring: each flower gets one outward kick when the front reaches it
      const front = h.radius * d3.easeSinOut(Math.min(1, u * 1.4));
      blobSpots.forEach(([bx, by], j) => {
        if (isGlow[j] || h.hit.has(j)) return;
        const ddx = bx - hx, ddy = by - hy, dist = Math.hypot(ddx, ddy);
        if (dist > front || dist < 0.01) return;
        h.hit.add(j);
        const k = h.kick * (1 - 0.6 * dist / h.radius);     // weaker further out
        velX[j] += ddx / dist * k; velY[j] += ddy / dist * k;
      });
      continue;
    }
    blobSpots.forEach(([bx, by], j) => {
      if (isGlow[j]) return;
      const ddx = bx + offX[j] - hx, ddy = by + offY[j] - hy, dist = Math.hypot(ddx, ddy);
      if (dist >= h.radius || dist < 0.01) return;
      if (h.mode === 'bloom') { bloom[j] = Math.min(1, bloom[j] + (1 - dist / h.radius) * h.rate * dt); return; }
      const a = (1 - dist / h.radius) * h.force * dt;
      if (h.mode === 'repel')        { velX[j] += ddx / dist * a;        velY[j] += ddy / dist * a; }
      else if (h.mode === 'carry')   { velX[j] += h.vec[0] * a;          velY[j] += h.vec[1] * a; }
    });
  }
  // integrate: velocity moves the flower and coasts to a stop; displacement drifts home
  const coast = Math.exp(-dt / VEL_TAU), coastHero = Math.exp(-dt / FLICK_TAU), bloomFade = Math.exp(-dt / BLOOM_TAU);
  for (let j = 0; j < offX.length; j++) {
    offX[j] += velX[j] * dt; offY[j] += velY[j] * dt;
    const c = flying.has(j) ? coastHero : coast;
    velX[j] *= c; velY[j] *= c;
    bloom[j] *= bloomFade;
  }
  const decay = Math.exp(-dt * 1000 / RETURN_TAU);
  for (let j = 0; j < offX.length; j++) {
    offX[j] *= decay; offY[j] *= decay;
    const m = Math.hypot(offX[j], offY[j]);
    const cap = flying.has(j) ? 60 : 30;
    if (m > cap) { offX[j] *= cap / m; offY[j] *= cap / m; }
  }

  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.globalCompositeOperation = 'source-over';
  ctx.globalAlpha = 1;
  ctx.fillStyle = '#000'; ctx.fillRect(0, 0, W, H);
  ctx.globalCompositeOperation = 'lighter';       // additive: overlapping flowers brighten, like light on a wall
  const long = Math.max(W, H);

  blobSpots.forEach(([bx, by, br, op], i) => {
    // breathing + slow wander
    const breathe = Math.sin(now / (2600 + 900 * (i % 5)) + phase[i]);
    const [px, py, amp] = wander[i];
    let dx = amp * Math.sin(now / px * 2 * Math.PI + phase[i]);
    let dy = amp * Math.cos(now / py * 2 * Math.PI + phase[i]);
    let scale = 1 + 0.10 * breathe;
    let push = 0;
    // poke
    const visibility = 1;
    dx += offX[i]; dy += offY[i];
    const speed = Math.hypot(velX[i], velY[i]);
    push += Math.min(speed / 25, 1) * 0.8;                    // moving flowers glow
    push += bloom[i] * 1.2;                                   // held flowers glow more
    push = Math.min(push, 1.6);
    scale *= 1 + 0.18 * Math.min(speed / 25, 1) + 0.45 * bloom[i];   // and open up

    // colour: this flower's own shade of the (delayed) tone; re-tint only when it changed
    const tone = colorAt(blobDelay[i]) || '#000';
    const c = isGlow[i] ? tone : tint(tone, i);
    if (c !== tintedColor[i]) retint(i, c);

    const x = (bx + dx) / 100 * W, y = (by + dy) / 100 * H;
    const size = br * 2 / 100 * long * scale;
    const sway = (rotation[i] + 6 * Math.sin(now / 5200 + phase[i])) * Math.PI / 180;
    ctx.save();
    ctx.translate(x, y); ctx.rotate(sway);
    ctx.globalAlpha = op * visibility;
    ctx.drawImage(tinted[i], -size / 2, -size / 2, size, size);
    if (push > 0.02) {                            // brighten while moving: draw again, additively
      ctx.globalAlpha = op * visibility * 0.6 * Math.min(push, 1);
      ctx.drawImage(tinted[i], -size / 2, -size / 2, size, size);
    }
    ctx.restore();
  });

  const cutoff = now - spreadMs - 2000;
  while (colorHistory.length > 1 && colorHistory[1][0] < cutoff) colorHistory.shift();
  while (hands.length && now - hands[0].t0 > hands[0].ms) hands.shift();
  requestAnimationFrame(renderBlobs);
}
if (lightMode === 'blobs') requestAnimationFrame(renderBlobs);

function paint(color) {
  if (lightMode === 'glow') {
    document.body.style.background =
      `radial-gradient(circle at 50% 50%, ${color} 0%, ${color} 25%, #000 75%) no-repeat`;
  } else if (lightMode === 'blobs') {
    colorHistory.push([performance.now(), color]);   // the render loop paints it, per-flower delayed
  } else {
    document.body.style.backgroundColor = color;
  }
}

const light = document.getElementById('light');

const socket = io();
const interpolate = d3.interpolateHcl;  // hue-based: fades travel through the colour wheel instead of through grey
const eases = Object.fromEntries(Object.entries(d3).filter((a) => a.toString().startsWith('ease')).map(([a, b]) => [a.substring(4), b]))
const audio = new Audio();

audio.loop = true;
let current;
let animateID;
let audioID;
let keys;
window.onload  = () => {
  keys = [...document.querySelectorAll('tinker-button')].reduce((obj, btn) => {
    obj[btn.letter.toLowerCase()] = btn
    return obj;
  }, {})
}

function playSound(soundLink, duration) {
  if (soundLink) {
    if (!audio.paused) {
      audio.pause();
    }
    audio.src = soundLink;
    audio.play();
    setTimeout(() =>  audio.pause() , duration);
  }
  return;
}

const runKey = (key) => {
  const { color: { hex }, duration, easing, sound_only, soundLink } = key
  const ease = eases[easing]
  if (sound_only) {
    playSound(soundLink, duration);
    socket.emit('audio', {soundLink, duration})
    return
  }
  if(soundLink){
    playSound(soundLink, duration);
    socket.emit('audio', {soundLink, duration})
  }

  if (animateID) {
    cancelAnimationFrame(animateID)
  }
  const startTime = performance.now();
  // Capture the starting colour ONCE. The original code re-read the current colour every
  // frame and interpolated from there, so progress compounded and every fade finished in
  // a fraction of its duration. Interpolating from a fixed start makes the fade take the
  // full duration.
  // Start from the colour we last painted (tracked in `current`), not from what the browser
  // reports for the body style: reading it back can yield a value d3 parses as black, which
  // made every fade dip to black before rising to its target.
  const startColor = current || getComputedStyle(document.body).getPropertyValue('--background-body').trim();
  const toColor = interpolate(startColor, hex);

  function animate(now) {
    const timeSinceStart = (now - startTime);

    // l goes from 0 to 1;
    const l = ease(Math.min(timeSinceStart / duration, 1));
    current = toColor(l)
    paint(current)
    socket.emit('hex', current)
    if (l < 1) {
      animateID = requestAnimationFrame(animate);
    }
  }
  animateID = requestAnimationFrame(animate);
}



document.onkeydown = (event) => {
  if (event.isComposing || event.target.tagName === 'TINKER-BUTTON') {
    return;
  }
  // gestures: what the visitor's hand is doing at the wall
  const arrows = { ArrowRight: 'right', ArrowLeft: 'left', ArrowUp: 'up', ArrowDown: 'down' };
  let gesture = null;
  if (event.key === ' ') gesture = { kind: 'tap' };
  else if (arrows[event.key]) gesture = { kind: 'swipe', dir: arrows[event.key] };
  else if (event.key === 'd' || event.key === 'D') gesture = { kind: 'drag' };
  else if (event.key === 'h' || event.key === 'H') gesture = { kind: 'hold' };
  if (gesture) { event.preventDefault(); socket.emit('hand', gesture); triggerHand(gesture.kind, gesture); return; }
  if (event.key === 'Enter') { event.preventDefault(); socket.emit('poke', {}); triggerPoke({}); return; }
  keys[event.key] ? runKey(keys[event.key]) : undefined;
}



socket.on('connect', () => {
  socket.on('hex', (val) => { current = val; paint(val) })
  socket.on('hand', (v) => { triggerHand(v.kind, v) })
  socket.on('poke', (v) => { triggerPoke(v || {}) })
  socket.on('audio', (val) => {playSound(val.soundLink, val.duration);})
  socket.on('pauseAudio', (val) => {audio.pause();})
  socket.onAny((event, ...args) => {
    console.log(event, args);
  });
});

// enter controller mode
control.onclick = () => {
  console.log('control')
  // make sure you're not in fullscreen
  if (document.fullscreenElement) {
    document.exitFullscreen()
      .then(() => console.log('exited full screen mode'))
      .catch((err) => console.error(err));
  }
  // make buttons and controls visible
  document.getElementById('user').classList.remove('fadeOut');
  document.getElementById('controlPanel').style.opacity = 0.6;
};

light.onclick = () => {
  // safari requires playing on input before allowing audio
  audio.muted = true;
  audio.play().then(audio.muted = false)

  // in light mode make it full screen and fade buttons
  document.documentElement.requestFullscreen();
  document.getElementById('user').classList.add('fadeOut');
  document.getElementById('controlPanel').style.opacity = 0;
};


