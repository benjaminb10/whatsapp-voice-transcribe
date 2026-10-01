#!/usr/bin/env python3
"""
wa-export: export a whole WhatsApp conversation from the macOS app to text,
with every voice note transcribed offline (whisper.cpp).

Reads WhatsApp's local database (read-only snapshot), never touches the app.

  wa-export.py --list                         # show your chats
  wa-export.py "Alice" --from "2026-09-01 08:00" --to "2026-09-15 20:00"
  wa-export.py "Team" --from 2026-09-01 --format json -o team.json
"""
import argparse, json, locale, os, re, shutil, signal, sqlite3, subprocess, sys, tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
WA = os.path.expanduser("~/Library/Group Containers/group.net.whatsapp.WhatsApp.shared")
TRANSCRIBE = os.path.join(HERE, "transcribe.sh")
CACHE = os.path.expanduser("~/Library/Caches/wa-export/transcripts.json")
EPOCH = 978307200  # Core Data dates count seconds from 2001-01-01

KINDS = {1: "📷 Photo", 2: "🎬 Video", 4: "👤 Contact", 5: "📍 Location",
         8: "📎 Document", 11: "GIF", 14: "(deleted message)", 15: "Sticker"}


def die(msg):
    sys.exit(f"wa-export: {msg}")


def open_db():
    """Copy the DB (+ WAL) to a temp dir: consistent read, WhatsApp stays untouched."""
    src = os.path.join(WA, "ChatStorage.sqlite")
    if not os.path.exists(src):
        die("WhatsApp database not found. Is the WhatsApp Mac app installed and signed in?")
    tmp = tempfile.mkdtemp(prefix="wa-export-")
    try:
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(src + suffix):
                shutil.copy2(src + suffix, os.path.join(tmp, "ChatStorage.sqlite" + suffix))
    except PermissionError:
        die("permission denied. Give your terminal Full Disk Access "
            "(System Settings → Privacy & Security → Full Disk Access).")
    return sqlite3.connect(os.path.join(tmp, "ChatStorage.sqlite"))


def parse_date(s, end=False):
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            d = datetime.strptime(s, fmt)
        except ValueError:
            continue
        # an end bound without seconds includes the whole minute / day
        pad = {"%Y-%m-%d %H:%M": 59, "%Y-%m-%d": 86399}.get(fmt, 0) if end else 0
        return d.timestamp() - EPOCH + pad
    die(f"bad date '{s}' (use YYYY-MM-DD or 'YYYY-MM-DD HH:MM')")


def list_chats(con):
    rows = con.execute("""
        select s.ZPARTNERNAME, s.ZSESSIONTYPE, count(m.Z_PK), sum(m.ZMESSAGETYPE = 3), max(m.ZMESSAGEDATE)
        from ZWACHATSESSION s join ZWAMESSAGE m on m.ZCHATSESSION = s.Z_PK
        where s.ZSESSIONTYPE in (0, 1) group by s.Z_PK order by max(m.ZMESSAGEDATE) desc""").fetchall()
    print(f"{'last message':<17} {'msgs':>6} {'voice':>6}  chat")
    for name, kind, n, voice, last in rows:
        tag = " (group)" if kind == 1 else ""
        print(f"{datetime.fromtimestamp(last + EPOCH):%Y-%m-%d %H:%M} {n:>6} {voice or 0:>6}  {name}{tag}")


def name_map(con):
    """JID → display name, from chat names first, then WhatsApp push names."""
    names = {}
    for jid, name in con.execute("select ZJID, ZPUSHNAME from ZWAPROFILEPUSHNAME"):
        if jid and name:
            names[jid] = name
    for jid, name in con.execute("select ZCONTACTJID, ZPARTNERNAME from ZWACHATSESSION where ZSESSIONTYPE in (0, 3)"):
        if jid and name:
            names[jid.removesuffix(".status")] = name
    return names


def transcribe_all(paths, jobs, lang):
    cache = {}
    if os.path.exists(CACHE):
        cache = json.load(open(CACHE))
    todo = sorted(p for p in paths if p not in cache and os.path.exists(os.path.join(WA, "Message", p)))
    if todo:
        print(f"Transcribing {len(todo)} voice notes (cached ones are skipped)…", file=sys.stderr)
    env = dict(os.environ, **({"WHISPER_LANG": lang} if lang else {}))

    def work(p):
        r = subprocess.run([TRANSCRIBE, os.path.join(WA, "Message", p)], capture_output=True, text=True, env=env)
        if r.returncode != 0:
            die(r.stderr.strip() or "transcription failed")
        return p, " ".join(r.stdout.split()) or "(inaudible)"

    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with ThreadPoolExecutor(jobs) as ex:
        for i, (p, text) in enumerate(ex.map(work, todo), 1):
            cache[p] = text
            if i % 5 == 0 or i == len(todo):
                json.dump(cache, open(CACHE, "w"), ensure_ascii=False)
                print(f"  {i}/{len(todo)}", file=sys.stderr)
    return cache


def main():
    ap = argparse.ArgumentParser(description="Export a WhatsApp chat to text, voice notes transcribed offline.")
    ap.add_argument("chat", nargs="?", help="chat name (or part of it)")
    ap.add_argument("--list", action="store_true", help="list chats and exit")
    ap.add_argument("--from", dest="start", help="start date, 'YYYY-MM-DD[ HH:MM]' (default: beginning)")
    ap.add_argument("--to", dest="end", help="end date, inclusive (default: now)")
    ap.add_argument("--format", choices=("md", "txt", "json"), default="md")
    ap.add_argument("-o", "--out", help="output file (default: ~/Desktop/WhatsApp <chat> <date>.<format>)")
    ap.add_argument("--me", default="Me", help="label for your own messages (default: Me)")
    ap.add_argument("--lang", help="transcription language, e.g. en, fr (default: auto-detect)")
    ap.add_argument("-j", "--jobs", type=int, default=2, help="parallel transcriptions (default: 2)")
    a = ap.parse_args()

    con = open_db()
    if a.list:
        return list_chats(con)
    if not a.chat:
        ap.error("give a chat name, or use --list")

    chats = con.execute("select Z_PK, ZPARTNERNAME, ZSESSIONTYPE from ZWACHATSESSION "
                        "where ZPARTNERNAME like ? and ZSESSIONTYPE in (0, 1)", (f"%{a.chat}%",)).fetchall()
    exact = [c for c in chats if c[1].lower() == a.chat.lower()]
    chats = exact or chats
    if not chats:
        die(f"no chat matches '{a.chat}' (try --list)")
    if len(chats) > 1:
        die("several chats match, be more specific:\n  " + "\n  ".join(c[1] for c in chats))
    chat_id, chat_name, kind = chats[0]

    start = parse_date(a.start) if a.start else -10**12
    end = parse_date(a.end, end=True) if a.end else 10**12
    rows = con.execute("""
        select m.ZMESSAGEDATE, m.ZISFROMME, m.ZMESSAGETYPE, m.ZTEXT, i.ZMEDIALOCALPATH, i.ZTITLE, g.ZMEMBERJID
        from ZWAMESSAGE m
        left join ZWAMEDIAITEM i on i.ZMESSAGE = m.Z_PK
        left join ZWAGROUPMEMBER g on g.Z_PK = m.ZGROUPMEMBER
        where m.ZCHATSESSION = ? and m.ZMESSAGEDATE between ? and ?
        order by m.ZMESSAGEDATE""", (chat_id, start, end)).fetchall()
    if not rows:
        die("no messages in that date range")

    names = name_map(con)
    voice = [r[4] for r in rows if r[2] == 3 and r[4]]
    transcripts = transcribe_all(voice, a.jobs, a.lang)

    def mention(num):
        return next((names[j] for j in (f"{num}@lid", f"{num}@s.whatsapp.net") if j in names), num)

    messages = []
    for date, me, typ, text, path, title, member in rows:
        if me:
            who = a.me
        elif kind == 1:
            who = names.get(member, (member or "?").split("@")[0])
        else:
            who = chat_name
        if typ == 3:
            body, is_voice = transcripts.get(path, "(voice note not downloaded on this Mac)"), True
        elif typ in (0, 7):
            body, is_voice = (text or "").strip(), False
        else:
            extra = "" if typ == 14 else " ".join(x.strip() for x in (title, text) if x and x.strip())
            body, is_voice = KINDS.get(typ, f"[message type {typ}]") + (f": {extra}" if extra else ""), False
        body = re.sub(r"@(\d{6,})", lambda mt: "@" + mention(mt.group(1)), body)
        if body:
            messages.append({"time": datetime.fromtimestamp(date + EPOCH), "from": who,
                             "voice": is_voice, "text": body})

    out = a.out or os.path.expanduser(
        f"~/Desktop/WhatsApp {chat_name} {messages[0]['time']:%Y-%m-%d}.{a.format}")
    with open(out, "w") as f:
        if a.format == "json":
            json.dump([dict(m, time=m["time"].isoformat()) for m in messages], f, ensure_ascii=False, indent=1)
        else:
            md = a.format == "md"
            f.write(f"# WhatsApp: {chat_name}\n\n" if md else f"WhatsApp: {chat_name}\n\n")
            day = None
            for m in messages:
                if m["time"].date() != day:
                    day = m["time"].date()
                    f.write(f"\n## {m['time']:%A %d %B %Y}\n\n" if md else f"\n--- {m['time']:%A %d %B %Y} ---\n")
                mic = "🎤 " if m["voice"] else ""
                f.write(f"**[{m['time']:%H:%M}] {m['from']}:** {mic}{m['text']}  \n" if md
                        else f"[{m['time']:%H:%M}] {m['from']}: {mic}{m['text']}\n")
    n_voice = sum(m["voice"] for m in messages)
    print(f"{len(messages)} messages ({n_voice} voice notes) → {out}", file=sys.stderr)
    print(out)


if __name__ == "__main__":
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)  # quiet when piped into head
    try:
        locale.setlocale(locale.LC_TIME, "")
    except locale.Error:
        pass
    main()
