-- ============================================================
--  WhatsApp Voice Note → Text  (on-demand, 100% local)
--
--  Load it from your ~/.hammerspoon/init.lua with:
--      dofile(os.getenv("HOME") .. "/path/to/whatsapp-voice-transcribe/hammerspoon/whatsapp-transcribe.lua")
--
--  HOW IT WORKS: in WhatsApp, right-click a voice note → "Save to Downloads".
--  The moment the .opus lands in Downloads, it is transcribed automatically:
--  a floating bubble shows the text and it is copied to your clipboard.
--  The file is kept (you decide whether to delete it).
--
--  Only permission required: Full Disk Access (to read the saved note).
-- ============================================================

local HOME = os.getenv("HOME")

-- locate this repo relative to this very file, so it works wherever it's cloned
local selfPath = debug.getinfo(1, "S").source:sub(2)
local hereDir  = selfPath:match("(.*/)") or "./"
local BIN      = hereDir .. "../bin/"
local SH_TRANSCRIBE = BIN .. "transcribe.sh"

-- ---- config ----
local LANG       = "auto"                              -- "auto", "en", "fr", "es", ...
local WATCH_DIRS = { HOME .. "/Downloads", HOME .. "/Desktop" }
local AUDIO_EXT  = { opus=true, m4a=true, mp3=true, wav=true, ogg=true, caf=true, aac=true, amr=true }

-- ---- state ----
local bubble, runningTask
local handled = {}

local function trim(s) return (s or ""):gsub("^%s+", ""):gsub("%s+$", "") end
local function htmlEscape(s) return (s or ""):gsub("&","&amp;"):gsub("<","&lt;"):gsub(">","&gt;") end

-- ---- floating result bubble ----
local function showBubble(title, body, ok)
  if bubble then bubble:delete(); bubble = nil end
  local accent = ok and "#25D366" or "#e0a500"
  local footer = ok and "Copied to clipboard ✓ — Esc or ✕ to close"
                     or "Esc or ✕ to close"
  local html = ([[
    <html><head><meta charset="utf-8"><style>
      html,body{margin:0;background:transparent;font-family:-apple-system,'Helvetica Neue',sans-serif;}
      .card{margin:8px;padding:16px 18px;border-radius:16px;background:#fff;
            box-shadow:0 10px 34px rgba(0,0,0,.20);border:1px solid #eceff3;}
      .hd{display:flex;align-items:center;gap:8px;font-weight:700;font-size:14px;color:#111;margin-bottom:8px;}
      .dot{width:9px;height:9px;border-radius:50%%;background:%s;}
      .txt{font-size:15px;line-height:1.5;color:#1c2430;white-space:pre-wrap;word-wrap:break-word;}
      .ft{margin-top:12px;font-size:11px;color:#8a94a3;}
    </style></head><body><div class="card">
      <div class="hd"><span class="dot"></span>%s</div>
      <div class="txt">%s</div><div class="ft">%s</div>
    </div></body></html>
  ]]):format(accent, htmlEscape(title), htmlEscape(body), footer)

  local screen = hs.screen.mainScreen():frame()
  local w, h = 460, 320
  local frame = { x = screen.x + (screen.w - w)/2, y = screen.y + 70, w = w, h = h }
  bubble = hs.webview.new(frame)
    :windowStyle({ "titled", "closable", "nonactivating", "utility" })
    :windowTitle("🎙️ Transcription")
    :level(hs.drawing.windowLevels.floating)
    :closeOnEscape(true):allowTextEntry(false):shadow(true)
    :html(html):bringToFront(true):show()
end

-- ---- transcribe one file (cleanup: delete file on success if given) ----
local function transcribe(path, cleanup)
  if not path or path == "" then hs.alert.show("Nothing to transcribe 🤔", 1.5); return end
  if runningTask and runningTask:isRunning() then hs.alert.show("Already transcribing…", 1); return end
  hs.alert.show("🎙️ Transcribing…", 1.2)
  runningTask = hs.task.new("/bin/bash", function(code, stdout, stderr)
    local text = trim(stdout)
    if code ~= 0 or text == "" then
      showBubble("Transcription failed",
                 trim(stderr) ~= "" and trim(stderr) or "No text could be extracted.", false)
      return
    end
    hs.pasteboard.setContents(text)
    hs.alert.show("✅ Transcribed & copied", 1.2)
    showBubble("Voice note transcribed", text, true)
    if cleanup then os.remove(cleanup) end
  end, { SH_TRANSCRIBE, path })
  runningTask:setEnvironment({ PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
                               WHISPER_LANG = LANG, HOME = HOME })
  runningTask:start()
end

-- ---- optional confirmation prompt (used for non-opus audio) ----
local function promptTranscribe(path)
  local name = path:match("[^/]+$") or path
  hs.focus()
  local btn = hs.dialog.blockAlert("🎙️ Audio file detected",
    "\"" .. name .. "\"\n\nTranscribe it to text?", "Yes, transcribe", "No")
  if btn == "Yes, transcribe" then transcribe(path) end
end

-- ---- watch download folders ----
local function onDownloadChange(paths)
  for _, p in ipairs(paths) do
    local ext = p:match("%.([%w]+)$"); ext = ext and ext:lower()
    if ext and AUDIO_EXT[ext] then
      local a = hs.fs.attributes(p)
      if a and a.mode == "file" and not handled[p] then
        if (os.time() - (a.modification or 0)) <= 20 then   -- genuinely new file
          handled[p] = true
          if ext == "opus" then
            hs.timer.doAfter(0.5, function() transcribe(p) end)      -- WhatsApp note: instant
          else
            hs.timer.doAfter(0.5, function() promptTranscribe(p) end) -- other audio: ask first
          end
        end
      end
    end
  end
end

-- GLOBAL on purpose (no `local`): otherwise the pathwatcher gets garbage-collected
-- and stops firing after the first event. Keep a permanent reference alive.
WA_TRANSCRIBE_WATCHERS = {}
for _, dir in ipairs(WATCH_DIRS) do
  local w = hs.pathwatcher.new(dir, onDownloadChange)
  if w then w:start(); table.insert(WA_TRANSCRIBE_WATCHERS, w) end
end

hs.alert.show("WhatsApp → Text ready · right-click a note → Save to Downloads", 3)
