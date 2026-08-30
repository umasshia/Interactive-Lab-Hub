// Solo mode for one-person wizarding.
// Press P on the Wizard page to run the scripted take below; Escape cancels.
// Plug earbuds into the laptop: one short beep = "hand flat and still now",
// two beeps = "touch the wall now". The light change follows the beep by 1 second,
// so the light appears to react to what you just did.
//
// Each line is [milliseconds from start, key-to-press or 'beep1'/'beep2'].
const SOLO_SCRIPT = [
  // the field on its own: dim, cool, breathing
  [0,     'L'],          // dim violet-blue
  [6000,  '1'],          // drifts to emerald
  [13000, 'L'],          // and back
  // someone walks up
  [19000, 'beep1'],      // -> walk into frame, stop in front of the flowers
  [20000, 'A'],          // warmer and a little brighter over 4 s
  // they tap
  [27000, 'beep2'],      // -> tap the wall
  [28000, 'tap'],
  // they flick a flower
  [34000, 'beep2'],      // -> flick a flower to the right
  [35000, 'poke'],
  // they walk away
  [43000, 'beep1'],      // -> step back out of frame
  [44000, 'L'],          // cooler and dimmer over 5 s
  [52000, '1'],          // the field goes on without them
  [60000, '0'],
];

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
  for (const [ms, action] of SOLO_SCRIPT) {
    soloTimers.push(setTimeout(() => {
      if (action === 'beep1') beep(1);
      else if (action === 'beep2') beep(2);
      else if (action.startsWith('poke')) {             // 'poke' or 'poke:left' etc.
        const dir = action.split(':')[1];
        socket.emit('poke', dir ? { dir } : {}); triggerPoke(dir ? { dir } : {});
      }
      else if (/^(tap|swipe|drag|hold)/.test(action)) {  // 'tap', 'swipe:left', 'drag', 'hold'
        const [kind, dir] = action.split(':');
        const g = dir ? { kind, dir } : { kind };
        socket.emit('hand', g); triggerHand(kind, g);
      }
      else if (keys[action]) runKey(keys[action]);
    }, ms));
  }
}

function cancelSoloScript() {
  soloTimers.forEach(clearTimeout);
  soloTimers = [];
}

document.addEventListener('keydown', (e) => {
  if (e.target.tagName === 'TINKER-BUTTON' || e.target.tagName === 'INPUT') return;
  if (e.key === 'p' || e.key === 'P') runSoloScript();
  if (e.key === 'Escape') { cancelSoloScript(); console.log('solo script cancelled'); }
});
