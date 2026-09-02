#!/bin/bash
# install.sh — one-shot setup for whatsapp-voice-transcribe (macOS)
# Installs ffmpeg + whisper.cpp (via Homebrew), downloads the model,
# and installs Hammerspoon if missing.
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
MODEL_NAME="ggml-large-v3-turbo-q5_0.bin"
MODEL_URL="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/${MODEL_NAME}"
MODEL_PATH="$REPO/models/$MODEL_NAME"

say() { printf "\033[1;32m==>\033[0m %s\n" "$1"; }

command -v brew >/dev/null || { echo "Homebrew required: https://brew.sh"; exit 1; }

say "Installing ffmpeg + whisper.cpp"
brew list ffmpeg      >/dev/null 2>&1 || brew install ffmpeg
brew list whisper-cpp >/dev/null 2>&1 || brew install whisper-cpp

say "Installing Hammerspoon (if missing)"
brew list --cask hammerspoon >/dev/null 2>&1 || brew install --cask hammerspoon

if [ ! -f "$MODEL_PATH" ]; then
  say "Downloading Whisper model (~574 MB)…"
  curl -L --fail --progress-bar -o "$MODEL_PATH" "$MODEL_URL"
else
  say "Model already present, skipping download"
fi

chmod +x "$REPO"/bin/*.sh

say "Done. Final steps:"
cat <<EOF

1) Add this line to ~/.hammerspoon/init.lua :

     dofile("$REPO/hammerspoon/whatsapp-transcribe.lua")

2) Launch Hammerspoon, then grant it Full Disk Access
   (System Settings → Privacy & Security → Full Disk Access → add Hammerspoon).
   Then: Hammerspoon menu-bar icon → Reload Config.

3) In WhatsApp, right-click a voice note → "Save to Downloads".
   The transcription pops up and is copied to your clipboard.

EOF
