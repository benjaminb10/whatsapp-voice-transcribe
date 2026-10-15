#!/usr/bin/env node
/*
wa-web-chat: pull the voice notes, photos and videos of ONE WhatsApp Web chat,
each tied to its sender and send time, and transcribe the voice notes offline.

wa-web-media.py reads WhatsApp Web's media cache blindly: it cannot tell which
chat or which person a voice note came from, and its timestamps are "last
displayed" times. This tool asks the open WhatsApp Web page instead. The page
keeps every loaded message in memory with its sender, send time, caption,
duration and the SHA-256 of its file, and that hash is also the key of the
decrypted file in the browser's media cache. So every file comes out labelled,
and media from your other chats are never touched.

It talks to Chrome over the DevTools protocol (no Playwright, no dependency),
read-only: it never clicks, types or sends anything.

  # 1. start a Chrome with a debug port and a profile of its own, log in to WhatsApp Web
  open -na "Google Chrome" --args --user-data-dir="$HOME/wa-chrome" --remote-debugging-port=9222 https://web.whatsapp.com
  # 2. open the chat and scroll back over the period you want (media are cached once shown)
  # 3. pull it
  bin/wa-web-chat.mjs --chat "Family" --since "2026-10-14 08:00" --transcribe --lang fr

Needs Node 22+ (built-in WebSocket). Transcription uses bin/transcribe.sh.
*/
import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import path from 'node:path';

const HERE = path.dirname(new URL(import.meta.url).pathname);
const TRANSCRIBE = path.join(HERE, 'transcribe.sh');
const CACHE = path.join(homedir(), 'Library/Caches/wa-export/transcripts.json');

const argv = process.argv.slice(2);
const opt = (name, def) => { const i = argv.indexOf(`--${name}`); return i >= 0 && argv[i + 1] ? argv[i + 1] : def; };
const flag = (name) => argv.includes(`--${name}`);
if (flag('help') || !opt('chat')) {
  console.error(`usage: wa-web-chat.mjs --chat "<chat name>" [--since "YYYY-MM-DD HH:MM"] [--kinds voice,image,video]
                       [--transcribe] [--lang fr] [--port 9222] [-o DIR] [--json]

  --chat        part of the chat (or group) name, as shown in WhatsApp Web
  --since       keep messages SENT after this local time (default: everything loaded)
  --kinds       voice,image,video (default: voice,image)
  --transcribe  transcribe voice notes offline (writes <file>.txt), --lang to force a language
  --port        Chrome remote debugging port (default 9222)
  -o            output folder (default ~/Downloads/whatsapp-web-chat)
  --json        print a JSON array instead of tab-separated lines

Only messages loaded in the page are seen: open the chat and scroll back first.
A file is only there if its bubble was displayed (videos are usually not cached).`);
  process.exit(flag('help') ? 0 : 1);
}
const CHAT = opt('chat');
const SINCE = opt('since') ? Math.floor(new Date(opt('since').replace(' ', 'T')).getTime() / 1000) : 0;
if (Number.isNaN(SINCE)) { console.error(`bad --since: ${opt('since')}`); process.exit(1); }
const KINDS = new Set(opt('kinds', 'voice,image').split(','));
const PORT = Number(opt('port', '9222'));
const oi = argv.indexOf('-o');
const OUT = oi >= 0 ? argv[oi + 1] : path.join(homedir(), 'Downloads/whatsapp-web-chat');

// --- DevTools protocol: evaluate an async function in the WhatsApp Web tab ---
async function evaluate(expression) {
  let tabs;
  try { tabs = await (await fetch(`http://127.0.0.1:${PORT}/json`)).json(); } catch {
    throw new Error(`no Chrome on debug port ${PORT} (start it with --remote-debugging-port=${PORT})`);
  }
  const tab = tabs.find((t) => t.type === 'page' && t.url.startsWith('https://web.whatsapp.com'));
  if (!tab) throw new Error('no WhatsApp Web tab open in that Chrome');
  const ws = new WebSocket(tab.webSocketDebuggerUrl);
  await new Promise((ok, ko) => { ws.onopen = ok; ws.onerror = () => ko(new Error('cannot connect to the tab')); });
  const res = await new Promise((ok) => {
    ws.onmessage = (e) => { const m = JSON.parse(e.data); if (m.id === 1) ok(m); };
    ws.send(JSON.stringify({ id: 1, method: 'Runtime.evaluate', params: { expression, awaitPromise: true, returnByValue: true } }));
  });
  ws.close();
  if (res.result?.exceptionDetails) throw new Error(res.result.exceptionDetails.exception?.description || 'page error');
  return res.result?.result?.value;
}

// Runs inside the page. WAWebCollections is WhatsApp Web's own message store.
const inPage = (chat, since, kinds) => `(async () => {
  let C;
  try { C = window.require('WAWebCollections'); } catch { return { error: 'WhatsApp Web not ready (log in and wait for your chats)' }; }
  const want = ${JSON.stringify(chat)}.toLowerCase();
  const chats = C.Chat.getModelsArray().filter(c => (c.formattedTitle || c.name || '').toLowerCase().includes(want));
  if (!chats.length) return { error: 'no chat matching ' + ${JSON.stringify(chat)} };
  if (chats.length > 1) return { error: 'several chats match: ' + chats.map(c => c.formattedTitle || c.name).join(', ') };
  const cache = await caches.open('lru-media-array-buffer-cache');
  const b64 = (buf) => { const u = new Uint8Array(buf); let s = ''; for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode.apply(null, u.subarray(i, i + 0x8000)); return btoa(s); };
  const KIND = { ptt: 'voice', audio: 'voice', image: 'image', video: 'video' };
  const out = [];
  for (const m of chats[0].msgs.getModelsArray()) {
    const kind = KIND[m.type];
    if (!kind || !${JSON.stringify([...KINDS])}.includes(kind) || m.t < ${since}) continue;
    const who = m.id?.fromMe ? 'me' : (m.senderObj?.name || m.senderObj?.formattedName || m.senderObj?.pushname || m.notifyName || '');
    const r = { id: m.id?.id, kind, time: m.t, sender: who, caption: (m.caption || '').trim(), duration: Number(m.duration) || 0, mimetype: m.mimetype || '', sha256: m.filehash || '' };
    if (m.filehash) {
      const hit = await cache.match('https://_media_cache_v2_.whatsapp.com/lru-media-array-buffer-cache_' + encodeURIComponent(m.filehash)).catch(() => null);
      if (hit) r.data = b64(await hit.arrayBuffer());
    }
    out.push(r);
  }
  return { chat: chats[0].formattedTitle || chats[0].name, loadedFrom: chats[0].msgs.getModelsArray()[0]?.t || 0, media: out };
})()`;

const pad = (n) => String(n).padStart(2, '0');
const stamp = (t) => { const d = new Date(t * 1000); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`; };
const slug = (s) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^a-zA-Z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 30) || 'unknown';
const ext = (r) => (r.kind === 'voice' ? 'opus' : r.kind === 'video' ? 'mp4' : /png/.test(r.mimetype) ? 'png' : /webp/.test(r.mimetype) ? 'webp' : 'jpg');

const res = await evaluate(inPage(CHAT, SINCE, KINDS)).catch((e) => ({ error: e.message }));
if (res?.error) { console.error(`wa-web-chat: ${res.error}`); process.exit(1); }
if (SINCE && res.loadedFrom > SINCE) console.error(`note: the page only has messages from ${stamp(res.loadedFrom)}, scroll further back in the chat to reach --since`);

mkdirSync(OUT, { recursive: true });
const cache = existsSync(CACHE) ? JSON.parse(readFileSync(CACHE, 'utf8')) : {};
const env = { ...process.env, ...(opt('lang') ? { WHISPER_LANG: opt('lang') } : {}) };
const rows = [];
for (const r of res.media) {
  const d = new Date(r.time * 1000);
  const file = r.data ? path.join(OUT, `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}-${slug(r.sender)}-${r.id}.${ext(r)}`) : null;
  if (file) writeFileSync(file, Buffer.from(r.data, 'base64'));
  let transcript = null;
  if (file && r.kind === 'voice' && flag('transcribe')) {
    const key = `sha:${r.sha256}`;
    if (!(key in cache)) {
      try { cache[key] = execFileSync(TRANSCRIBE, [file], { env, encoding: 'utf8' }).split(/\s+/).join(' ').trim() || '(inaudible)'; } catch (e) { cache[key] = null; console.error(`transcription failed: ${path.basename(file)}`); }
      mkdirSync(path.dirname(CACHE), { recursive: true });
      writeFileSync(CACHE, JSON.stringify(cache));
    }
    transcript = cache[key];
    if (transcript) writeFileSync(`${file}.txt`, `${transcript}\n`);
  }
  rows.push({ time: stamp(r.time), sender: r.sender, kind: r.kind, duration: r.duration, caption: r.caption, file, transcript });
}
console.error(`${res.chat}: ${rows.length} media, ${rows.filter((x) => x.file).length} files written to ${OUT}`);
if (flag('json')) console.log(JSON.stringify(rows, null, 2));
else for (const x of rows) console.log([x.time, x.sender, x.kind, x.duration ? `${x.duration}s` : '', x.file ? path.basename(x.file) : '(not cached)', x.transcript || x.caption].join('\t'));
