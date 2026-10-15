# 🎙️ WhatsApp Voice Note → Text (macOS)

**Transcribe any WhatsApp voice note on your Mac, on demand, 100% offline —
the built-in "voice message transcription" before WhatsApp shipped it.**

You keep using the **native WhatsApp Mac app** exactly as before. To transcribe
a voice note, you just **right-click it → "Save to Downloads"**. A floating
bubble instantly shows the text, and it's copied to your clipboard.

No cloud. No API key. No account. Nothing leaves your Mac — the transcription
runs locally with [whisper.cpp](https://github.com/ggerganov/whisper.cpp).

**New: WhatsApp Web too.** Using WhatsApp in Safari, a Safari web app, or Chrome?
Grab its voice notes, photos and videos straight from the browser cache, transcribed,
without clicking anything. See [WhatsApp Web](#whatsapp-web-voice-notes-photos-videos).

**New: one chat, every media labelled.** `wa-web-chat` asks the open WhatsApp
Web page which voice note or photo belongs to which chat, who sent it and when.
No guessing, and your other chats are never touched. See
[One chat from WhatsApp Web](#one-chat-from-whatsapp-web-sender-and-time-included).

**Export a whole conversation.** Pick a chat and a date range, get one
text file with every message in order, and every voice note already
transcribed. No clicking through notes one by one. See
[Export a whole chat](#export-a-whole-chat-with-voice-notes-transcribed).

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
2. Launch **Hammerspoon**, and grant it **Full Disk Access** in
   **System Settings → Privacy & Security** (needed to read the saved note).
   Then click the Hammerspoon menu-bar icon → **Reload Config**.

## Usage

**Pick any note:** right-click it in WhatsApp → **Save to Downloads** → the text
appears in a floating bubble and is copied to your clipboard. The `.opus` file
stays in Downloads (yours to keep or delete).

## Export a whole chat (with voice notes transcribed)

`bin/wa-export.py` reads WhatsApp's local database directly (a read-only
snapshot, WhatsApp itself is never touched) and writes the conversation to a
single file, voice notes transcribed inline:

```markdown
## Wednesday 30 September 2026

**[09:01] Alice:** https://example.com  new SaaS, worth a look
**[09:23] Alice:** 🎤 Quick voice note: check their landing page, the CRM columns are smart…
**[11:46] Me:** Yes, I'll show it to our lawyer
```

```bash
bin/wa-export.py --list                                   # your chats, with message / voice-note counts
bin/wa-export.py "Alice"                                  # whole chat → ~/Desktop/WhatsApp Alice <date>.md
bin/wa-export.py "Alice" --from "2026-09-30 09:00" --to "2026-10-01 10:31"
bin/wa-export.py "Team" --from 2026-09-01 --format json -o team.json
```

| Option | |
|---|---|
| `--from`, `--to` | `YYYY-MM-DD` or `"YYYY-MM-DD HH:MM"`, local time, both inclusive (default: whole chat) |
| `--format` | `md` (default), `txt` or `json` |
| `--me` | label for your own messages (default `Me`) |
| `--lang` | force the transcription language (`en`, `fr`, …), default auto-detect |
| `-j` | parallel transcriptions (default 2) |
| `-o` | output path |

- Group chats show each sender's name, and `@mentions` are resolved to names.
- Transcripts are cached in `~/Library/Caches/wa-export/`, so re-exporting an
  overlapping range is instant. On an Apple Silicon Mac, expect roughly
  2 minutes for 65 voice notes the first time.
- Your **terminal** needs **Full Disk Access** (System Settings → Privacy &
  Security) to read WhatsApp's data folder.
- Only voice notes **downloaded on this Mac** can be transcribed. Older ones
  that never were show up as `(voice note not downloaded on this Mac)`.
- WhatsApp's database format is undocumented and may change with an app update.

## WhatsApp Web (voice notes, photos, videos)

WhatsApp Web has no "Save to Downloads" for voice notes, and its chat export
leaves them out (`<voice message omitted>`). But to play them, it keeps every
media it has **displayed** in the browser's Cache Storage, already decrypted.
`bin/wa-web-media.py` reads that cache directly: no browser automation, no clicks,
the window can stay in the background.

```bash
# 1. note the time, open the chat in WhatsApp Web and scroll through it
#    (a voice note is cached as soon as its bubble is on screen; no need to play it)
# 2. pull everything displayed since then, and transcribe the voice notes
bin/wa-web-media.py --since "2026-10-15 21:30" --kinds voice,image --transcribe --lang fr
# a Chrome profile driven by Playwright/Puppeteer? point to it:
bin/wa-web-media.py --since 2026-10-15 --chrome-profile ~/my-wa-profile
```

Each media is written to `~/Downloads/whatsapp-web-media/` (`.opus`, `.jpg`…),
with a `.txt` next to each transcribed voice note, and listed on stdout:
`cache time · kind · duration/size · file · transcript`.

| Option | |
|---|---|
| `--since` | cache time lower bound, local time (required) |
| `--kinds` | `voice` (default), `image`, `video`, comma-separated |
| `--transcribe`, `--lang`, `-j` | transcribe voice notes, like `wa-export` (shared cache) |
| `--chrome-profile` | extra Chrome profile dir to scan, repeatable (the default Chrome profiles are always scanned) |
| `--min-image-kb` | skip smaller images: blurred previews, avatars (default 25) |
| `--until`, `-o` | upper bound, output dir |

Good to know:

- **Cache time is the last time the media was displayed**, not when it was
  sent, and it moves forward each time the chat is shown again. Note the time
  right before opening the chat and use it as `--since`; avoid a tight `--until`.
- The cache also holds media from **other chats** displayed after `--since`:
  keep only those of the chat you want (the transcript makes it obvious).
- To get the text, use WhatsApp Web's own **⋮ › Export chat**, then put each
  voice note back in place (durations shown in quoted replies help).
- Media never displayed in WhatsApp Web aren't there, and the cache is LRU:
  extract soon after opening the chat.
- Supports Safari, Safari "Add to Dock" web apps, and Chrome (only WhatsApp's
  media cache is read, stickers and other sites are ignored).

## One chat from WhatsApp Web (sender and time included)

`wa-web-media.py` reads the browser cache blindly: a file there has no chat, no
sender, and only the time it was last *displayed*. `bin/wa-web-chat.mjs` asks the
WhatsApp Web page instead. The page keeps every loaded message in memory with its
sender, send time, caption, duration and the SHA-256 of its file, and that hash
is also the key of the decrypted file in the media cache. So each file comes out
labelled, and only the chat you name is read.

It talks to Chrome over the DevTools protocol, read-only (it never clicks, types
or sends), with no dependency beyond Node 22+.

```bash
# 1. a Chrome with a debug port and a profile of its own (log in to WhatsApp Web once)
open -na "Google Chrome" --args --user-data-dir="$HOME/wa-chrome" \
  --remote-debugging-port=9222 https://web.whatsapp.com
# 2. open the chat and scroll back over the period you want
# 3. pull its media, voice notes transcribed
bin/wa-web-chat.mjs --chat "Family" --since "2026-10-14 08:00" --transcribe --lang fr
```

One line per media on stdout (or `--json`):
`send time · sender · kind · duration · file · transcript or caption`.
Files are named `YYYYMMDD-HHMMSS-<sender>-<id>.<ext>`, with a `.txt` next to each
transcribed voice note.

| Option | |
|---|---|
| `--chat` | part of the chat or group name (it must match a single chat) |
| `--since` | keep messages **sent** after this local time |
| `--kinds` | `voice,image` (default), add `video` |
| `--transcribe`, `--lang` | transcribe voice notes, same cache as `wa-export` |
| `--port`, `-o`, `--json` | debug port (9222), output folder, JSON output |

Good to know:

- Only messages **loaded** in the page are seen: scroll back in the chat first.
  The tool tells you when `--since` is older than what the page holds.
- A file is there only if its bubble was **displayed**. Photos and voice notes
  are cached as soon as you scroll past them; videos often are not.
- Opening a chat in WhatsApp Web marks it as read, as usual. The tool itself
  opens nothing.
- It relies on WhatsApp Web's internal modules, which can change without notice.

## Configuration

Edit the top of `hammerspoon/whatsapp-transcribe.lua`:

- `LANG` — `"auto"` (default), or force a language: `"en"`, `"fr"`, `"es"`, `"de"`, …
- `WATCH_DIRS` — folders to watch (default: Downloads + Desktop)

Prefer a different model (speed vs. accuracy)? Drop any ggml Whisper model in
`models/` and set `WHISPER_MODEL`, or edit `MODEL_NAME` in `bin/transcribe.sh`.

## Privacy

Everything is local. The audio never leaves your machine, there is no network
call, no telemetry, no key. You can read every line — it's a few hundred lines of shell,
Lua, Python and JavaScript. `wa-web-chat` only talks to your own Chrome, on localhost.

## Limitations

- macOS. The native WhatsApp app for transcribe-on-save and `wa-export`; WhatsApp Web (Safari / Chrome) for `wa-web-media`; Chrome with a debug port for `wa-web-chat`.
- `wa-export` relies on WhatsApp's internal database layout, which can change
  without notice.
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
