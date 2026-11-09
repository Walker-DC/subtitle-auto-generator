#!/usr/bin/env python3
"""교정한 .srt에서 .vtt를 다시 만든다.  python3 srt2vtt.py 출력/영상.srt"""
import re, sys
from pathlib import Path
for f in map(Path, sys.argv[1:]):
    t = re.sub(r"(\d\d:\d\d:\d\d),(\d{3})", r"\1.\2", f.read_text(encoding="utf-8"))
    t = re.sub(r"(?m)^\d+\n(?=\d\d:)", "", t)
    f.with_suffix(".vtt").write_text("WEBVTT\n\n" + t, encoding="utf-8")
    print("->", f.with_suffix(".vtt"))
