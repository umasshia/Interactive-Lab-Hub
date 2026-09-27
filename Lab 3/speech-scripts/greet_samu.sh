#!/usr/bin/env bash
# Lab 3 Part A: have the Pi greet me by name using Piper (neural TTS).
#
# Run from inside the Lab 3 venv:
#   source ../.venv/bin/activate
#   ./greet_giorgi.sh
#
# Uses --output-raw so playback starts while the sentence is still being
# synthesized, instead of waiting for a whole .wav to be written first.

set -euo pipefail
VOICES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/voices"

python3 -m piper \
  --model en_US-lessac-medium \
  --data-dir "$VOICES_DIR" \
  --output-raw \
  -- "Hello Samu. Welcome back. It is good to hear from you again." \
  | aplay -r 22050 -f S16_LE -t raw -
