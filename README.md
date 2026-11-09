# Subtitle Automation Pipeline

Turn a video (local file or link) into Korean subtitles (`.srt` / `.vtt`) with a local Whisper model, then review and correct them with Claude Code.

Everything up to the draft runs **locally and free**: yt-dlp, ffmpeg and faster-whisper. No API key is needed. Claude only joins for the review step.

## Pipeline

| # | Step | Tool |
|---|------|------|
| 0 | Input: file path, `입력/` folder, or URL (video + separate audio saved) | yt-dlp |
| 1 | Extract audio (16 kHz mono) | ffmpeg |
| 2 | Drop silent parts | Silero VAD (built into faster-whisper) |
| 3 | Korean speech recognition with sentence timestamps and confidence | Whisper via faster-whisper (`small` by default, `medium` / `large-v3` optional) |
| 4 | Hints: glossary terms and the head of the script as `initial_prompt` | Whisper |
| 5 | Optional script alignment: replace each recognized sentence with the closest script line (timing stays audio-based) | `difflib` |
| 6 | Glossary fixes (`wrong => right`) | Python |
| 7 | Write `.srt` / `.vtt` and a `.검토.txt` review list (low confidence, script mismatches) | Python |
| 8 | Review and correction: awkward sentences, inconsistent names, web lookup of proper nouns | Claude Code (`/자막` skill + `사전전문가` and `자막조정` agents) |

The script is optional. Without one, steps 4-5 are skipped.

## Setup

```bash
pip install faster-whisper yt-dlp numpy
# ffmpeg must be on PATH
cp 용어목록.example.txt 용어목록.txt   # your own glossary
```

Tested on WSL2 (CPU, int8). A weak GPU is not needed.

## Usage

```bash
python3 make_subs.py video.mp4                      # one file
python3 make_subs.py https://www.youtube.com/...    # download, then transcribe
python3 make_subs.py                                # everything in 입력/
python3 make_subs.py video.mp4 --script 대본/video.txt --model medium
python3 make_subs.py URL --audio-only               # smaller download
python3 srt2vtt.py 출력/video.srt                   # re-sync .vtt after hand edits
```

Options: `--model tiny|base|small|medium|large-v3`, `--device auto|cpu|cuda`, `--no-vtt`, `--out DIR`.

A script is one line per sentence in `대본/<video name>.txt` (picked up automatically) or passed with `--script`.

## With Claude Code

Open Claude Code in this folder and run:

```
/자막 https://www.youtube.com/watch?v=...
```

The skill runs the pipeline, then reviews the result. Two agents help:

- `사전전문가` checks proper nouns and known words on the web and only marks a spelling as confirmed when two sources agree.
- `자막조정` fixes awkward or inconsistent lines using existing usage in the subtitles or published sources.

Agents only propose changes. Timecodes and cue numbers are never changed.

## Layout

```
make_subs.py        main pipeline
srt2vtt.py          .srt -> .vtt
용어목록.example.txt  glossary template
CLAUDE.md           working rules for Claude Code
.claude/            skill and agents
입력/ 음성/ 출력/ 대본/   input, saved audio, output, scripts (git-ignored)
```

## Notes

- Accuracy depends mostly on the model size, a script, and a glossary. Larger models are slower on CPU.
- Only subtitle text is sent out when Claude reviews or searches. Audio and video never leave the machine.
- Download only content you have the right to use. Respect each platform's terms.
