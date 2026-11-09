#!/usr/bin/env python3
"""영상 -> 음성 추출(ffmpeg) -> Whisper 한국어 인식 -> .srt/.vtt 생성.

사용:  python3 make_subs.py 영상.mp4 [--script 대본.txt] [--model small] [--no-vtt]
       python3 make_subs.py https://유튜브등/링크   (링크의 영상을 내려받아 처리)
       python3 make_subs.py                          (입력/ 폴더의 모든 영상 처리)

대본: 대본/영상이름.txt (한 줄 = 한 대사)가 있으면 자동으로 사용한다.
      대본을 인식 힌트로 쓰고, 인식된 문장을 대본의 가장 비슷한 줄로 교체한다(시간은 음성 기준).
"""
import argparse, difflib, re, shutil, subprocess, sys, tempfile, wave
import numpy as np
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOW_CONF = -0.8  # avg_logprob가 이보다 낮으면 검토 대상
VIDEO_EXT = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv", ".wmv", ".m4v", ".mp3", ".wav", ".m4a"}


def load_terms():
    terms, fixes, mode = [], [], None
    f = ROOT / "용어목록.txt"
    if not f.exists():
        return terms, fixes
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("["):
            mode = line.strip("[]")
        elif mode == "용어":
            terms.append(line)
        elif mode == "교정" and "=>" in line:
            a, b = (s.strip() for s in line.split("=>", 1))
            if a:
                fixes.append((a, b))
    return terms, fixes


def norm(s: str) -> str:
    return re.sub(r"[\W_]+", "", s)


def load_script(path: Path):
    if not path or not path.exists():
        return []
    return [l.strip() for l in path.read_text(encoding="utf-8-sig").splitlines() if l.strip() and not l.startswith("#")]


def find_script(video_stem: str, explicit):
    if explicit:
        return explicit
    for d in (ROOT / "대본",):
        f = d / f"{video_stem}.txt"
        if f.exists():
            return f
    return None


def align_to_script(segs, lines, threshold=0.55, window=8):
    """인식 문장을 대본의 순서상 가장 비슷한 줄로 교체. 검토 필요 항목을 반환."""
    ptr, review = 0, []
    nlines = [norm(l) for l in lines]
    for s in segs:
        sn = norm(s["text"])
        best = (0.0, None, 0)  # score, text, consumed
        for i in range(ptr, min(ptr + window, len(lines))):
            for n in (1, 2):
                if i + n > len(lines):
                    continue
                cand = "".join(nlines[i:i + n])
                sc = difflib.SequenceMatcher(None, sn, cand).ratio()
                if sc > best[0]:
                    best = (sc, " ".join(lines[i:i + n]), n)
                    best_i = i
        if best[1] and best[0] >= threshold:
            if best[1] != s["text"]:
                review.append((s, f"대본으로 교체({best[0]:.2f})", s["text"], best[1]))
            s["text"] = best[1]
            ptr = best_i + best[2]
        else:
            part = best[1] and len(sn) >= 4 and sn in norm(best[1])
            review.append((s, "대본 일부(긴 줄 분할?)" if part else "대본에 없음/불일치", s["text"], best[1] or ""))
    return review


def download(url: str, audio_only: bool) -> Path:
    (ROOT / "입력").mkdir(exist_ok=True)
    cmd = ["yt-dlp", "--no-playlist", "--windows-filenames", *(["--js-runtimes", "node"] if shutil.which("node") else []), "-o", str(ROOT / "입력" / "%(title)s.%(ext)s"),
           "--print", "after_move:filepath"]
    cmd += ["-x", "--audio-format", "m4a"] if audio_only else ["-f", "bv*[height<=720]+ba/b", "--merge-output-format", "mp4"]
    r = subprocess.run(cmd + [url], check=True, capture_output=True, text=True)
    f = Path(r.stdout.strip().splitlines()[-1])
    if f.suffix.lower() not in {".m4a", ".mp3", ".wav"}:  # 영상을 받았으면 음성도 따로 보관
        (ROOT / "음성").mkdir(exist_ok=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(f), "-vn", "-c:a", "aac", "-b:a", "128k",
                        str(ROOT / "음성" / f"{f.stem}.m4a")], check=True)
    return f


def extract_audio(video: Path, wav: Path):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-vn",
                    "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)], check=True)


def ts(sec: float, sep: str) -> str:
    ms = round(sec * 1000)
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02}{sep}{ms:03}"


def write_subs(segs, out: Path, vtt: bool):
    srt = [f"{i}\n{ts(s['start'], ',')} --> {ts(s['end'], ',')}\n{s['text']}\n" for i, s in enumerate(segs, 1)]
    out.with_name(out.name + ".srt").write_text("\n".join(srt), encoding="utf-8")
    if vtt:
        v = [f"{ts(s['start'], '.')} --> {ts(s['end'], '.')}\n{s['text']}\n" for s in segs]
        out.with_name(out.name + ".vtt").write_text("WEBVTT\n\n" + "\n".join(v), encoding="utf-8")


def transcribe(model, wav: Path, terms, fixes, script_lines=()):
    prompt = "게임 영상입니다."
    if terms:
        prompt += " 용어: " + ", ".join(terms) + "."
    if script_lines:
        prompt += " " + " ".join(script_lines)[:200]
    # av 버전 충돌을 피하려고 wav를 직접 읽어 배열로 넘긴다
    with wave.open(str(wav)) as w:
        audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    it, info = model.transcribe(audio, language="ko", vad_filter=True, beam_size=5,
                                initial_prompt=prompt, condition_on_previous_text=False)
    segs = []
    for s in it:
        text = s.text.strip()
        for a, b in fixes:
            text = text.replace(a, b)
        if text:
            segs.append({"start": s.start, "end": s.end, "text": text, "conf": s.avg_logprob})
        print(f"  [{ts(s.start, '.')}] {text}", flush=True)
    return segs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*", help="영상 파일 경로 또는 http 링크")
    ap.add_argument("--script", type=Path, help="대본 txt (생략 시 대본/영상이름.txt 자동 탐색)")
    ap.add_argument("--audio-only", action="store_true", help="링크는 음성만 내려받기(빠름)")
    ap.add_argument("--model", default="small", help="tiny/base/small/medium/large-v3 (클수록 정확, 느림)")
    ap.add_argument("--device", default="auto", help="auto/cpu/cuda")
    ap.add_argument("--no-vtt", action="store_true")
    ap.add_argument("--out", type=Path, default=ROOT / "출력")
    a = ap.parse_args()

    files = []
    for f in a.files:
        if re.match(r"https?://", f):
            print(f"내려받는 중: {f}")
            files.append(download(f, a.audio_only))
        else:
            files.append(Path(f))
    files = files or sorted(p for p in (ROOT / "입력").iterdir() if p.suffix.lower() in VIDEO_EXT)
    if not files:
        sys.exit("처리할 영상이 없습니다. 입력/ 폴더에 영상을 넣거나 경로를 지정하세요.")
    a.out.mkdir(exist_ok=True)

    from faster_whisper import WhisperModel
    compute = "int8" if a.device == "cpu" else "default"
    print(f"모델 로딩: {a.model}")
    model = WhisperModel(a.model, device=a.device, compute_type=compute)
    terms, fixes = load_terms()

    for v in files:
        print(f"\n== {v.name}")
        with tempfile.TemporaryDirectory() as td:
            wav = Path(td) / "audio.wav"
            extract_audio(v, wav)
            sf = find_script(v.stem, a.script)
            lines = load_script(sf)
            if lines:
                print(f"대본 사용: {sf.name} ({len(lines)}줄)")
            segs = transcribe(model, wav, terms, fixes, lines)
        review = align_to_script(segs, lines) if lines else []
        review += [(s, f"인식 신뢰도 낮음({s['conf']:.2f})", s["text"], "") for s in segs if s.get("conf", 0) < LOW_CONF]
        review.sort(key=lambda r: r[0]["start"])
        write_subs(segs, a.out / v.stem, not a.no_vtt)
        if review:
            rp = a.out / f"{v.stem}.검토.txt"
            rp.write_text("\n\n".join(f"[{ts(s['start'], '.')}] {why}\n  인식: {old}" + (f"\n  대본: {new}" if new else "") for s, why, old, new in review), encoding="utf-8")
            print(f"-> 검토 필요 {len(review)}건: {rp}")
        print(f"-> {a.out / v.stem}.srt ({len(segs)}문장)")


if __name__ == "__main__":
    main()
