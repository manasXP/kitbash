#!/usr/bin/env python3
"""Fetch a video's transcript as plain text with minute markers, using yt-dlp captions.

    yt_transcript.py URL [--lang en] [--out FILE]

Downloads only the subtitle track (manual first, else auto-generated), strips the WebVTT
timing tags and the rolling duplicate lines YouTube auto-captions contain, and prints one
line per caption cue prefixed with [mm:ss]. Exit 2 when no caption track exists (say so;
do not guess the content) and 3 when yt-dlp fails (video unavailable, no network).
Standard library only; needs yt-dlp on PATH.
"""
import argparse
import glob
import os
import re
import subprocess
import sys
import tempfile

TAG = re.compile(r"<[^>]+>")
TIME = re.compile(r"^(\d\d):(\d\d):(\d\d)\.\d+ --> ")


def vtt_to_lines(text):
    lines, last = [], None
    stamp = None
    for raw in text.splitlines():
        m = TIME.match(raw)
        if m:
            h, mnt, s = (int(x) for x in m.groups())
            stamp = f"{h * 60 + mnt:02d}:{s:02d}"
            continue
        if not raw.strip() or raw.startswith(("WEBVTT", "Kind:", "Language:")):
            continue
        line = TAG.sub("", raw).replace("&nbsp;", " ").strip()
        if not line or line in ("[Music]", "[Applause]") or line == last:
            continue
        lines.append(f"[{stamp}] {line}" if stamp else line)
        last = line
    return lines


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("url")
    ap.add_argument("--lang", default="en", help="caption language prefix (default en)")
    ap.add_argument("--out", help="write the transcript here instead of stdout")
    a = ap.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        cmd = ["yt-dlp", "--no-update", "--skip-download", "--write-subs", "--write-auto-subs",
               "--sub-langs", f"{a.lang}.*", "--sub-format", "vtt", "--no-warnings",
               "-o", os.path.join(tmp, "video"), a.url]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            sys.stderr.write(proc.stderr.strip() + "\n")
            sys.stderr.write("yt_transcript: yt-dlp failed; no transcript fetched\n")
            return 3
        tracks = sorted(glob.glob(os.path.join(tmp, "video.*.vtt")))
        if not tracks:
            sys.stderr.write(f"yt_transcript: no '{a.lang}' caption track on this video; nothing to transcribe\n")
            return 2
        manual = [t for t in tracks if "-orig" not in t]
        with open((manual or tracks)[0], encoding="utf-8") as fh:
            lines = vtt_to_lines(fh.read())
    title = subprocess.run(["yt-dlp", "--no-update", "--no-warnings", "--print", "%(title)s | %(uploader)s | %(duration)ss",
                            a.url], capture_output=True, text=True).stdout.strip()
    body = (f"# {title}\n# {a.url}\n" if title else "") + "\n".join(lines) + "\n"
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            fh.write(body)
        print(f"wrote {len(lines)} caption lines to {a.out}")
    else:
        sys.stdout.write(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
