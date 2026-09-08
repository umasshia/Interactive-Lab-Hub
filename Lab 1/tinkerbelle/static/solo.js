// Solo mode for one-person wizarding.
// Press P on the Wizard page to run the scripted take below; Escape cancels.
// Plug earbuds into the laptop: one short beep = "hand flat and still now",
// two beeps = "touch the wall now". The light change follows the beep by 1 second,
// so the light appears to react to what you just did.
//
// Captions for the recording: [seconds from the start of the take, text]. Drawn onto the light
// canvas while the take runs (P starts it, Esc stops it), so they end up in the recording. Each
// shows for 5 s unless the next one comes sooner. &captions=off on the light URL disables them.
const CAPTIONS = [
  [0,   'Flower field, no one interacting'],
  [20,  'Person approaches. Nearby flowers gather and twinkle'],
  [28,  'Tap. Flowers break into petals'],
  [34,  'Swipe. More petals scatter'],
  [40,  'Person leaves'],
  [50,  'Petals return to their flowers'],
  [65,  'Flowers reassembled'],
  [75,  'Two people approach'],
  [83,  'Two touches. Petals collide in the middle'],
  [95,  'Both leave'],
  [105, 'Petals return'],
  [125, 'Season change'],
  [150, ''],
];
// The take. Each line is [milliseconds from start, action]. Actions:
//   {key:'4'}                          a colour key        {sound:'ambient', on:true}   the pad
//   {hand:'tap'|'swipe'|'drag'|'hold', x, y, dir}   a gesture at a wall point (percent)
//   {poke:true, x, y, dir}             a flick             {approach:0|1, x, y}         approach at point 0 or 1
//   {leave:true}                       release both        {field:{...}}                a field op (reset, season ...)
//   {end:true}                         the end (stops a recording)
// Wall coordinates are percent across and down. Timing matches CAPTIONS above.
const SOLO_SCRIPT = [
  [0,      { field: { op: 'reset' } }],                       // cherry season, full bloom, the field alone
  [0,      { sound: 'ambient', on: true }],
  [20000,  { approach: 0, x: 30, y: 50 }],
  [28000,  { hand: 'tap', x: 30, y: 50 }],
  [34000,  { hand: 'swipe', x: 30, y: 50, dir: 'right' }],
  [40000,  { leave: true }],
                                                              // 1:05 petals are back (gather 12 s: the last leaves by ~53 s and lands by ~60 s)
  [75000,  { approach: 0, x: 25, y: 50 }],
  [75000,  { approach: 1, x: 75, y: 50 }],
  [83000,  { hand: 'tap', x: 25, y: 50 }],
  [83500,  { poke: true, x: 75, y: 50, dir: 'left' }],
  [95000,  { leave: true }],
  [125000, { season: 1 }],                                     // summer
  [150000, { end: true }],
];

// run one action here and on every other page
function soloAct(a) {
  if (a.key) { const k = keys && keys[a.key.toLowerCase()]; if (k) runKey(k); }
  else if (a.hand) { const g = { kind: a.hand, x: a.x, y: a.y, dir: a.dir }; socket.emit('hand', g); triggerHand(a.hand, g); }
  else if (a.poke) { const g = { x: a.x, y: a.y, dir: a.dir }; socket.emit('poke', g); triggerPoke(g); }
  else if (a.approach !== undefined) { const ap = { slot: a.approach, x: a.x, y: a.y }; socket.emit('approach', ap); triggerApproach(ap); }
  else if (a.leave) { socket.emit('leave', {}); releaseApproaches(); }
  else if (a.sound) { const op = { op: a.sound, on: a.on }; socket.emit('sound', op); soundOp(op); }
  else if (a.field) { socket.emit('field', a.field); fieldOp(a.field); }
  else if (a.season !== undefined) {
    seasonOp(a.season);
    const op = { op: 'season', k: season, base: SEASONS[season].base, ms: seasonFadeMs };
    socket.emit('field', op); fieldOp(op);
  }
  else if (a.end) cancelSoloScript();
}

let soloTimers = [];
let audioCtx;

function beep(times) {
  audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
  for (let i = 0; i < times; i++) {
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.frequency.value = 880;
    gain.gain.value = 0.15;
    osc.connect(gain).connect(audioCtx.destination);
    const t = audioCtx.currentTime + i * 0.18;
    osc.start(t);
    osc.stop(t + 0.09);
  }
}

function runSoloScript() {
  cancelSoloScript();
  console.log('solo script started');
  socket.emit('field', { op: 'record', on: true }); fieldOp({ op: 'record', on: true });   // the caption clock on every light
  for (const [ms, action] of SOLO_SCRIPT) {
    soloTimers.push(setTimeout(() => {
      if (action === 'beep1') beep(1);
      else if (action === 'beep2') beep(2);
      else soloAct(action);
    }, ms));
  }
}

function cancelSoloScript() {
  if (!soloTimers.length) return;
  soloTimers.forEach(clearTimeout);
  soloTimers = [];                                  // cleared first: the record-off below may call back in here
  socket.emit('field', { op: 'record', on: false }); fieldOp({ op: 'record', on: false });
}

document.addEventListener('keydown', (e) => {
  if (e.target.tagName === 'TINKER-BUTTON' || e.target.tagName === 'INPUT') return;
  if (e.code === 'KeyP' || e.key === 'p' || e.key === 'P') runSoloScript();
  if (e.code === 'Escape' || e.key === 'Escape') { cancelSoloScript(); console.log('solo script cancelled'); }
});
