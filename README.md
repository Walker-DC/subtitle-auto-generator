# Subtitle Automation Pipeline (자막 자동화 파이프라인)

영상(파일 또는 링크)에서 한국어 자막(`.srt` / `.vtt`)을 자동으로 만들고, Claude Code로 검수·교정까지 이어서 하는 파이프라인입니다.

초안 생성까지는 전부 **내 PC에서 무료로** 돌아갑니다(yt-dlp, ffmpeg, faster-whisper). API 키가 필요 없고, Claude는 검수 단계에서만 사용합니다.

## 파이프라인

| 단계 | 하는 일 | 도구 |
|---|---|---|
| 0 | 입력: 파일 경로, `입력/` 폴더, 링크 (링크는 영상과 음성을 따로 저장) | yt-dlp |
| 1 | 음성 추출 (16kHz 모노) | ffmpeg |
| 2 | 무음 구간 제거 | Silero VAD (faster-whisper 내장) |
| 3 | 한국어 음성 인식, 문장별 시작·끝 시간과 신뢰도 | Whisper (faster-whisper). 기본 `small`, 옵션 `medium` / `large-v3` |
| 4 | 인식 힌트: 용어목록과 대본 앞부분을 `initial_prompt`로 전달 | Whisper |
| 5 | (선택) 대본 정렬: 인식 문장을 대본에서 가장 비슷한 줄로 교체, 시간은 음성 기준 | `difflib` |
| 6 | 용어 교정 (`틀린말 => 맞는말` 자동 치환) | Python |
| 7 | `.srt` / `.vtt` 저장, 검토 목록(`.검토.txt`) 작성 (신뢰도 낮은 문장, 대본 불일치) | Python |
| 8 | 검수·교정: 어색한 문장, 이름 표기 불일치, 고유명사 웹 검색 확인 | Claude Code (`/자막` 스킬, `사전전문가`, `자막조정` 에이전트) |

대본은 선택 사항입니다. 없으면 4~5단계는 건너뜁니다.

## 설치

```bash
pip install faster-whisper yt-dlp numpy
# ffmpeg가 PATH에 있어야 합니다
cp 용어목록.example.txt 용어목록.txt   # 나만의 용어목록
```

WSL2(CPU, int8)에서 테스트했습니다. 고성능 GPU가 없어도 됩니다.

## 사용법

```bash
python3 make_subs.py video.mp4                      # 파일 하나
python3 make_subs.py https://www.youtube.com/...    # 링크: 내려받은 뒤 인식
python3 make_subs.py                                # 입력/ 폴더 전체
python3 make_subs.py video.mp4 --script 대본/video.txt --model medium
python3 make_subs.py URL --audio-only               # 음성만 받기(가벼움)
python3 srt2vtt.py 출력/video.srt                   # 손으로 고친 뒤 .vtt 다시 만들기
```

옵션: `--model tiny|base|small|medium|large-v3`, `--device auto|cpu|cuda`, `--no-vtt`, `--out 폴더`

대본은 한 줄에 한 대사로 적은 txt입니다. `대본/영상이름.txt`로 두면 자동으로 쓰이고, `--script`로 직접 지정할 수도 있습니다.

## Claude Code와 함께 쓰기

이 폴더에서 Claude Code를 열고 다음처럼 실행합니다.

```
/자막 https://www.youtube.com/watch?v=...
```

스킬이 파이프라인을 돌린 뒤 결과를 검수합니다. 두 에이전트가 돕습니다.

| 역할 | 하는 일 | 모델 |
|---|---|---|
| `/자막` 스킬 (메인) | 파이프라인 실행, 검수 지휘, 확정된 수정 적용 | 세션에서 쓰는 Claude 모델 |
| `사전전문가` | 고유명사와 알려진 단어를 웹에서 확인합니다. 서로 다른 출처 2곳이 같은 표기일 때만 확정으로 표시합니다. | Sonnet |
| `자막조정` | 어색하거나 표기가 엇갈리는 문장을 자막 안의 기존 용례나 공개된 자료를 근거로 조정안을 냅니다. | Opus |

에이전트의 모델은 `.claude/agents/*.md` 맨 위 `model:` 줄에서 바꿀 수 있습니다.

`/자막` 없이 "이 영상 자막 만들어줘"처럼 요청해도 `CLAUDE.md` 지침에 따라 같은 절차로 진행됩니다.

에이전트는 제안만 하고 파일은 직접 수정하지 않습니다. 타임코드와 문장 번호는 바꾸지 않습니다.

## 폴더 구성

```
make_subs.py          메인 파이프라인
srt2vtt.py            .srt -> .vtt 변환
용어목록.example.txt   용어목록 템플릿
CLAUDE.md             Claude Code 작업 규칙
.claude/              스킬과 에이전트
입력/ 음성/ 출력/ 대본/  입력, 보관한 음성, 결과, 대본 (git 제외)
```

## 참고

- 정확도는 모델 크기, 대본, 용어목록에 가장 크게 좌우됩니다. 큰 모델은 CPU에서 느립니다.
- Claude가 검수하거나 검색할 때 나가는 건 자막 텍스트뿐입니다. 음성과 영상은 PC 밖으로 나가지 않습니다.
- 권리가 있는 콘텐츠만 내려받으세요. 각 플랫폼의 약관을 지켜야 합니다.
