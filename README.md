# 🎙️ WhatsApp Voice Note → Text (macOS)

**Transcribe any WhatsApp voice note on your Mac, on demand, 100% offline —
the built-in "voice message transcription" before WhatsApp shipped it.**

You keep using the **native WhatsApp Mac app** exactly as before. To transcribe
a voice note, you just **right-click it → "Save to Downloads"**. A floating
bubble instantly shows the text, and it's copied to your clipboard.

No cloud. No API key. No account. Nothing leaves your Mac — the transcription
runs locally with [whisper.cpp](https://github.com/ggerganov/whisper.cpp).

---

## Why this exists

WhatsApp's own voice-note transcription is still not available on many desktop
installs. If you live in the Mac app and drown in voice notes, this gives you
the feature today — without modifying, patching, or "hooking" WhatsApp in any
way (its app stays untouched and its signature intact).

The trick: WhatsApp already offers **"Save to Downloads"** in the right-click
menu of any voice note. We simply watch that folder. **The act of saving a note
is the act of choosing it** — so you pick exactly the note you want (even an old
one, deep in the conversation), with zero ambiguity.

## How it works

```
You right-click a voice note → "Save to Downloads"
        │
        ▼
Hammerspoon sees the new .opus file appear        (folder watcher)
        │
        ▼
whisper.cpp transcribes it locally                (offline engine)
        │
        ▼
Floating bubble shows the text + copied to clipboard
```

Three small pieces:

| Piece | Role |
|-------|------|
| **whisper.cpp** + a Whisper model | the offline speech-to-text engine |
| **`bin/transcribe.sh`** | decodes the `.opus` (via ffmpeg) and runs the engine |
| **Hammerspoon** config | watches Downloads, runs the script, shows the bubble |

## Requirements

- macOS (Apple Silicon recommended — transcription is ~3× real-time)
- [Homebrew](https://brew.sh)
- The installer pulls the rest: `ffmpeg`, `whisper-cpp`, `hammerspoon`, and the model.

## Install

```bash
git clone https://github.com/benjaminb10/whatsapp-voice-transcribe.git
cd whatsapp-voice-transcribe
./install.sh
```

Then:

1. Add this line to `~/.hammerspoon/init.lua`:
   ```lua
   dofile(os.getenv("HOME") .. "/whatsapp-voice-transcribe/hammerspoon/whatsapp-transcribe.lua")
   ```
   *(adjust the path to wherever you cloned it)*
2. Launch **Hammerspoon**, and grant it in **System Settings → Privacy & Security**:
   - **Accessibility** — for the ⌘⌥T shortcut
   - **Full Disk Access** — to read WhatsApp voice notes
   Then click the Hammerspoon menu-bar icon → **Reload Config**.

## Usage

- **Pick any note:** right-click it in WhatsApp → **Save to Downloads** → the
  text appears and is copied. The `.opus` file stays in Downloads (yours to keep
  or delete).
- **Quick shortcut:** press **⌘⌥T** to transcribe the *latest* received note
  without any click.

## Configuration

Edit the top of `hammerspoon/whatsapp-transcribe.lua`:

- `LANG` — `"auto"` (default), or force a language: `"en"`, `"fr"`, `"es"`, `"de"`, …
- `WATCH_DIRS` — folders to watch (default: Downloads + Desktop)
- `HOTKEY_MODS` / `HOTKEY_KEY` — change the shortcut

Prefer a different model (speed vs. accuracy)? Drop any ggml Whisper model in
`models/` and set `WHISPER_MODEL`, or edit `MODEL_NAME` in `bin/transcribe.sh`.

## Privacy

Everything is local. The audio never leaves your machine, there is no network
call, no telemetry, no key. You can read every line — it's ~200 lines of shell
and Lua.

## Limitations

- macOS + the native WhatsApp app only.
- You can't add a literal "Transcribe" item *inside* WhatsApp's menu (it's a
  closed app), so we ride its existing **"Save to Downloads"** action instead.
- Transcription quality is whatever the chosen Whisper model gives (the default
  `large-v3-turbo` is very good in many languages).

## Credits

- [whisper.cpp](https://github.com/ggerganov/whisper.cpp) by Georgi Gerganov
- [Hammerspoon](https://www.hammerspoon.org/) for the macOS glue
- OpenAI Whisper models

## License

[MIT](./LICENSE)
