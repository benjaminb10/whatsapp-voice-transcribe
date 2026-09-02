#!/bin/bash
# transcribe.sh <audio-file>
# Transcribes a single audio file (e.g. a WhatsApp .opus voice note) to text,
# in the language of your choice, fully offline using whisper.cpp.
# Prints the transcription to stdout.
#
# Env overrides:
#   WHISPER_MODEL  path to a ggml model .bin       (default: ../models/<MODEL_NAME>)
#   WHISPER_LANG   language code, e.g. en/fr/es/de (default: auto)
set -euo pipefail

# Make sure Homebrew tools are found even when launched outside an interactive shell.
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

DIR="$(cd "$(dirname "$0")" && pwd)"
MODEL_NAME="ggml-large-v3-turbo-q5_0.bin"
MODEL="${WHISPER_MODEL:-$DIR/../models/$MODEL_NAME}"
LANG="${WHISPER_LANG:-auto}"

FFMPEG="$(command -v ffmpeg || true)"
WHISPER="$(command -v whisper-cli || true)"

[ -z "$FFMPEG" ]  && { echo "ERROR: ffmpeg not found (brew install ffmpeg)" >&2; exit 1; }
[ -z "$WHISPER" ] && { echo "ERROR: whisper-cli not found (brew install whisper-cpp)" >&2; exit 1; }
[ -f "$MODEL" ]   || { echo "ERROR: model not found at $MODEL (run install.sh)" >&2; exit 1; }

AUDIO="${1:-}"
if [ -z "$AUDIO" ] || [ ! -f "$AUDIO" ]; then
  echo "usage: transcribe.sh <audio-file>" >&2
  exit 1
fi

WAV="$(mktemp -t wa_transcribe).wav"
trap 'rm -f "$WAV"' EXIT

# 1) decode to 16 kHz mono WAV (what whisper expects)
"$FFMPEG" -y -loglevel error -i "$AUDIO" -ar 16000 -ac 1 "$WAV"

# 2) transcribe, plain text, no timestamps
"$WHISPER" -m "$MODEL" -f "$WAV" -l "$LANG" -nt -t 8 2>/dev/null \
  | sed 's/^[[:space:]]*//' \
  | sed '/^$/d'
