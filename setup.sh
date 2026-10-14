#!/usr/bin/env bash
# book-youtube 설치 — macOS (Apple Silicon / Intel)
# 실행: 이 폴더에서  bash setup.sh
set -e
cd "$(dirname "$0")"
KIT="$(pwd)"

echo "1/5 Homebrew 로 Node.js, ffmpeg, Python 설치 (이미 있으면 건너뜀)"
if ! command -v brew >/dev/null; then
  echo "  Homebrew 가 없다 → https://brew.sh 의 한 줄 명령으로 먼저 설치한 뒤 다시 실행"; exit 1
fi
for p in node ffmpeg python@3.12; do brew list "$p" >/dev/null 2>&1 || brew install "$p"; done
PY="$(brew --prefix python@3.12)/bin/python3.12"

echo "2/5 파이썬 가상환경(.venv) + 패키지"
[ -d .venv ] || "$PY" -m venv .venv
.venv/bin/python -m pip install --upgrade pip >/dev/null
.venv/bin/python -m pip install -r requirements.txt

echo "3/5 HyperFrames 미리 받기 (렌더용 크롬 포함, 몇 분)"
npx --yes hyperframes@0.8.143 --version

echo "4/5 키 파일"
if [ ! -f .env ]; then cp .env.example .env; echo "  .env 를 만들었다 → open -e .env 로 열어 키 두 개를 넣을 것"; fi

echo "5/5 Claude Code 전역 스킬 등록"
DST="$HOME/.claude/skills/book-youtube"
if [ -f "$DST/SKILL.md" ] && ! grep -q "book-youtube-kit 설치본" "$DST/SKILL.md"; then
  echo "  ⚠ 이미 다른 book-youtube 스킬이 있어 덮어쓰지 않았다: $DST (이 폴더 안에서 claude 를 열면 키트 스킬이 쓰인다)"
else
  mkdir -p "$DST"
  sed "s|{{KIT_DIR}}|$KIT|g" .claude/skills/book-youtube/SKILL.md > "$DST/SKILL.md"
fi

echo; node --version; ffmpeg -version | head -1; .venv/bin/python --version
echo; echo "설치 끝. 이 폴더에서 claude 를 열고 「대충영어 책 홍보 쇼츠 1부 만들어」라고 말하면 된다."
