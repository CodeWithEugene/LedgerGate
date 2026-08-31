#!/usr/bin/env python3
"""Render the LedgerGate demo from stills + VOICEOVER.txt (macOS say + ffmpeg)."""

from __future__ import annotations

import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FRAMES = ROOT / "frames"
BUILD = ROOT / "build"
OUT = ROOT / "ledgergate-demo.mp4"

VOICE = "Samantha (Premium)"
RATE = 170
FPS = 30
WIDTH, HEIGHT = 1920, 1080
TAIL_PAD = 0.65
LAST_PAD = 1.4

# Primary timeline: almost full-frame, ~3% Ken Burns so chrome stays visible.
SCENES = [
    # id, image, z0, z1, x0, x1, y0, y1
    ("01", "01-inbox-guarded.png", 1.00, 1.03, 0.50, 0.50, 0.00, 0.10),
    ("02", "03-evaluation-curve-guarded.png", 1.00, 1.03, 0.50, 0.55, 0.00, 0.12),
    ("03", "04-policy-menu.png", 1.00, 1.03, 0.50, 0.58, 0.00, 0.04),
    ("04", "07-inbox-reckless.png", 1.00, 1.03, 0.50, 0.50, 0.00, 0.08),
    ("05", "07b-inbox-reckless-gate.png", 1.00, 1.03, 0.50, 0.50, 0.00, 0.08),
    ("06", "08-inbox-guarded-return.png", 1.00, 1.03, 0.50, 0.50, 0.00, 0.06),
    ("07", "09-needs-review.png", 1.00, 1.03, 0.50, 0.50, 0.00, 0.18),
    ("08", "10-receipt-everline-gate.png", 1.00, 1.03, 0.50, 0.50, 0.00, 0.10),
    ("09", "12-procedure-clause.png", 1.00, 1.03, 0.50, 0.50, 0.00, 0.10),
    ("10", "13-approvals.png", 1.00, 1.03, 0.50, 0.50, 0.00, 0.08),
    ("11", "14-approve-dialog.png", 1.00, 1.03, 0.50, 0.50, 0.00, 0.08),
    ("12", "16-evaluation-scorecard.png", 1.00, 1.03, 0.50, 0.50, 0.00, 0.08),
    ("13", "18-inbox-close.png", 1.03, 1.00, 0.50, 0.50, 0.06, 0.00),
]


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    print("+", " ".join(cmd[:8]), ("..." if len(cmd) > 8 else ""))
    return subprocess.run(cmd, check=True, **kw)


def probe_duration(path: Path) -> float:
    out = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        text=True,
    )
    return float(out.strip())


def parse_voiceover(text: str) -> dict[str, str]:
    parts = re.split(r"\[Scene (\d+)[^\]]*\]", text)
    by_id: dict[str, str] = {}
    # split keeps markers: '', '01', body, '02', body, ...
    i = 1
    while i + 1 < len(parts):
        sid = parts[i].zfill(2)
        body = parts[i + 1].strip()
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
        spoken = " [[slnc 380]] ".join(paragraphs)
        by_id[sid] = spoken
        i += 2
    return by_id


def ken_burns_filter(duration: float, z0, z1, x0, x1, y0, y1) -> str:
    t = f"{duration:.4f}"
    z = f"({z0:.4f}+({z1:.4f}-{z0:.4f})*min(t/{t}\\,1))"
    xf = f"({x0:.4f}+({x1:.4f}-{x0:.4f})*min(t/{t}\\,1))"
    yf = f"({y0:.4f}+({y1:.4f}-{y0:.4f})*min(t/{t}\\,1))"
    return (
        f"crop=w='max(2\\,floor(iw/{z}/2)*2)':h='max(2\\,floor(ih/{z}/2)*2)'"
        f":x='(iw-ow)*{xf}':y='(ih-oh)*{yf}',"
        f"scale={WIDTH}:{HEIGHT}:flags=lanczos,setsar=1,fps={FPS},format=yuv420p"
    )


def synth_scene(sid: str, spoken: str) -> Path:
    aiff = BUILD / f"{sid}.aiff"
    wav = BUILD / f"{sid}.wav"
    txt = BUILD / f"{sid}.txt"
    txt.write_text(spoken, encoding="utf-8")
    run(["say", "-v", VOICE, "-r", str(RATE), "-f", str(txt), "-o", str(aiff)])
    pad = LAST_PAD if sid == "13" else TAIL_PAD
    fade = ["-af", f"apad=pad_dur={pad:.2f}"]
    if sid == "01":
        fade = ["-af", f"afade=t=in:st=0:d=0.12,apad=pad_dur={pad:.2f}"]
    if sid == "13":
        dur = probe_duration(aiff) + pad
        fade = [
            "-af",
            f"apad=pad_dur={pad:.2f},afade=t=out:st={dur - 0.9:.2f}:d=0.85",
        ]
    run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(aiff),
            *fade,
            "-ar",
            "48000",
            "-ac",
            "2",
            "-c:a",
            "pcm_s16le",
            str(wav),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return wav


def render_clip(scene: tuple, wav: Path) -> Path:
    sid, image, z0, z1, x0, x1, y0, y1 = scene
    png = FRAMES / image
    if not png.exists():
        raise FileNotFoundError(png)
    duration = probe_duration(wav)
    vf = ken_burns_filter(duration, z0, z1, x0, x1, y0, y1)
    mp4 = BUILD / f"{sid}.mp4"
    run(
        [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-framerate",
            str(FPS),
            "-i",
            str(png),
            "-i",
            str(wav),
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            "-t",
            f"{duration:.3f}",
            "-movflags",
            "+faststart",
            str(mp4),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return mp4


def concat(clips: list[Path]) -> None:
    listing = BUILD / "concat.txt"
    listing.write_text(
        "".join(f"file '{p.resolve()}'\n" for p in clips), encoding="utf-8"
    )
    run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(listing),
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(OUT),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main() -> int:
    BUILD.mkdir(exist_ok=True)
    vo = parse_voiceover((ROOT / "VOICEOVER.txt").read_text(encoding="utf-8"))
    missing = [s[0] for s in SCENES if s[0] not in vo]
    if missing:
        print("missing VO for", missing, file=sys.stderr)
        return 1

    print(f"Synthesizing {len(SCENES)} scenes with {VOICE} @ {RATE} wpm-ish")
    wavs: dict[str, Path] = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = {
            pool.submit(synth_scene, sid, vo[sid]): sid for sid, *_ in SCENES
        }
        for fut in as_completed(futs):
            sid = futs[fut]
            wavs[sid] = fut.result()
            print(f"  audio {sid}: {probe_duration(wavs[sid]):.1f}s")

    clips: list[Path] = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futs = {
            pool.submit(render_clip, scene, wavs[scene[0]]): scene[0]
            for scene in SCENES
        }
        done: dict[str, Path] = {}
        for fut in as_completed(futs):
            sid = futs[fut]
            done[sid] = fut.result()
            print(f"  clip {sid}: {probe_duration(done[sid]):.1f}s")
    clips = [done[s[0]] for s in SCENES]

    print("Concatenating")
    concat(clips)
    total = probe_duration(OUT)
    print(f"Wrote {OUT} ({total:.1f}s, {OUT.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
