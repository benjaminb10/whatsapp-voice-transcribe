#!/usr/bin/env python3
"""Pull voice notes (and images / videos) out of WhatsApp Web's on-disk cache, and transcribe them.

WhatsApp Web (Safari, a Safari "Add to Dock" web app, or Chrome) keeps every media it has
displayed in the browser's CacheStorage, already decrypted: plain Ogg/Opus, JPEG, PNG, WebP, MP4.
A voice note lands there as soon as its bubble is shown on screen (no need to play it).
This script scans that cache, de-duplicates, and transcribes the voice notes offline.
No browser automation, no clicks: you can keep working while it runs.

usage:
  wa-web-media.py --since "YYYY-MM-DD HH:MM" [--kinds voice,image,video] [--transcribe] [-o DIR]

--since filters on the CACHE time, which is the LAST time the media was displayed in
WhatsApp Web, not the time the message was sent. It moves forward every time the chat is
shown again, so avoid a tight --until.
"""
import argparse, glob, hashlib, json, os, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
TRANSCRIBE = os.path.join(HERE, "transcribe.sh")
CACHE = os.path.expanduser("~/Library/Caches/wa-export/transcripts.json")
H = os.path.expanduser("~")
SAFARI_ROOTS = (glob.glob(f"{H}/Library/Containers/com.apple.Safari.WebApp/Data/Library/Containers/"
                          "com.apple.Safari.WebApp.*/Library/WebKit/WebsiteData")
                + glob.glob(f"{H}/Library/Containers/com.apple.Safari/Data/Library/WebKit/WebsiteData"))
CHROME_PROFILES = glob.glob(f"{H}/Library/Application Support/Google/Chrome/*/")
# In Chrome, WhatsApp's media cache entries are keyed under this pseudo-host (stickers live elsewhere).
CHROME_MEDIA_KEY = b"_media_cache_v2_.whatsapp.com/lru-media-array-buffer-cache"


def parse_time(s):
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).timestamp()
        except ValueError:
            pass
    sys.exit(f"bad date: {s!r} (use YYYY-MM-DD or 'YYYY-MM-DD HH:MM')")


def sniff(data):
    """(kind, extension, offset) of the media stored in a cache record, or None."""
    # Safari stores the bare body; Chrome prefixes it with the cache key (~150 bytes).
    head = data[:1024]
    i = head.find(b"OggS")
    if i >= 0 and b"OpusHead" in data[i:i + 200]:
        return "voice", "opus", i
    for sig, ext in ((b"\xff\xd8\xff", "jpg"), (b"\x89PNG\r\n", "png")):
        i = head.find(sig)
        if i >= 0:
            return "image", ext, i
    i = head.find(b"WEBP")
    if i >= 8 and head[i - 8:i - 4] == b"RIFF":
        return "image", "webp", i - 8
    i = head.find(b"ftyp")
    if i >= 4:
        return "video", "mp4", i - 4
    return None


def trim(ext, blob):
    """Cut the media exactly where it ends (Chrome appends cache metadata after the body)."""
    if ext == "opus":  # walk the Ogg pages
        pos = 0
        while blob[pos:pos + 4] == b"OggS" and pos + 27 <= len(blob):
            nseg = blob[pos + 26]
            pos += 27 + nseg + sum(blob[pos + 27:pos + 27 + nseg])
        return blob[:pos]
    if ext == "jpg":
        end = blob.rfind(b"\xff\xd9")
        return blob[:end + 2] if end > 0 else blob
    if ext == "png":
        end = blob.find(b"IEND")
        return blob[:end + 8] if end > 0 else blob
    if ext == "webp":
        return blob[:8 + int.from_bytes(blob[4:8], "little")]
    return blob


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", path], capture_output=True, text=True).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--since", required=True, help="cache time lower bound, local time")
    ap.add_argument("--until", help="cache time upper bound (usually leave empty)")
    ap.add_argument("--kinds", default="voice", help="comma-separated: voice,image,video (default: voice)")
    ap.add_argument("--min-image-kb", type=int, default=25, help="skip smaller images: blurred previews, avatars")
    ap.add_argument("--transcribe", action="store_true", help="transcribe voice notes (writes <file>.txt)")
    ap.add_argument("--lang", help="transcription language, e.g. en, fr (default: auto-detect)")
    ap.add_argument("-j", "--jobs", type=int, default=2, help="parallel transcriptions")
    ap.add_argument("-o", "--out", default=os.path.expanduser("~/Downloads/whatsapp-web-media"))
    ap.add_argument("--chrome-profile", action="append", default=[],
                    help="extra Chrome profile dir to scan (e.g. one driven by Playwright); repeatable")
    a = ap.parse_args()

    kinds = set(a.kinds.split(","))
    lo, hi = parse_time(a.since), (parse_time(a.until) + 59 if a.until else float("inf"))
    chrome = [os.path.join(os.path.expanduser(p), "") for p in a.chrome_profile] + CHROME_PROFILES
    roots = SAFARI_ROOTS + [r for p in chrome for r in glob.glob(os.path.join(p, "**", "Service Worker", "CacheStorage"), recursive=True)]
    if not roots:
        sys.exit("No Safari / Chrome WhatsApp Web data found.")
    os.makedirs(a.out, exist_ok=True)

    seen, found = set(), []
    for root in roots:
        is_chrome = "Service Worker" in root
        for d, _, files in os.walk(root):
            if "CacheStorage" not in d:
                continue
            for f in files:
                p = os.path.join(d, f)
                try:
                    mt = os.path.getmtime(p)
                    if not lo <= mt <= hi:
                        continue
                    data = open(p, "rb").read()
                except OSError:
                    continue
                if is_chrome and CHROME_MEDIA_KEY not in data[:600]:
                    continue  # another site, or a WhatsApp sticker
                hit = sniff(data)
                if not hit or hit[0] not in kinds:
                    continue
                kind, ext, i = hit
                blob = trim(ext, data[i:])
                if kind == "image" and len(blob) < a.min_image_kb * 1024:
                    continue
                h = hashlib.md5(blob).hexdigest()[:10]
                if h in seen:
                    continue
                seen.add(h)
                dst = os.path.join(a.out, f"{datetime.fromtimestamp(mt):%Y%m%d-%H%M%S}-{h}.{ext}")
                with open(dst, "wb") as fh:
                    fh.write(blob)
                found.append((mt, kind, dst))
    found.sort()
    print(f"{len(found)} media extracted to {a.out}", file=sys.stderr)

    texts = {}
    voices = [dst for _, kind, dst in found if kind == "voice"]
    if a.transcribe and voices:
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
        env = dict(os.environ, **({"WHISPER_LANG": a.lang} if a.lang else {}))
        key = lambda p: "web:" + p.rsplit("-", 1)[-1]  # content hash, stable across runs
        todo = [p for p in voices if key(p) not in cache]

        def work(p):
            out = subprocess.run([TRANSCRIBE, p], capture_output=True, text=True, env=env)
            return p, " ".join(out.stdout.split()) or "(inaudible)"
        with ThreadPoolExecutor(a.jobs) as ex:
            for n, (p, t) in enumerate(ex.map(work, todo), 1):
                cache[key(p)] = t
                json.dump(cache, open(CACHE, "w"), ensure_ascii=False)
                print(f"  transcribed {n}/{len(todo)}", file=sys.stderr)
        for p in voices:
            texts[p] = cache[key(p)]
            with open(p + ".txt", "w") as fh:
                fh.write(texts[p] + "\n")

    for mt, kind, dst in found:
        info = f"{duration(dst):.1f}s" if kind != "image" else f"{os.path.getsize(dst) // 1024} KB"
        line = f"{datetime.fromtimestamp(mt):%Y-%m-%d %H:%M:%S}\t{kind}\t{info}\t{os.path.basename(dst)}"
        print(line + (f"\t{texts[dst]}" if dst in texts else ""))


if __name__ == "__main__":
    main()
