# book-youtube — 책 홍보 쇼츠 자동 제작 키트 (Windows · macOS)

책 이름만 말하면 Claude Code 가 그 책을 찾아 **30초짜리 세로 홍보 쇼츠**를 만들어 준다.

> 상단 고정 제목 · 가운데 큰 자막 · AI 실사 배경 · 한국어 음성 · 끝 표지 카드 — 1·2·3부 시리즈

예시 결과: `books/대충영어/` (근거 `sources.md`, 원고 `part1.json`, 업로드 문구 `part1.upload.json`)

---

## 1. 받기

```bash
git clone https://github.com/osam555/book-youtube.git
cd book-youtube
```
(비공개 저장소라 저장소 주인이 초대해야 받을 수 있다. Git 이 없으면 Windows 는 `winget install Git.Git`, macOS 는 `xcode-select --install`.)

## 2. 설치 (한 번만)

**Windows** — 폴더에서 오른쪽 클릭 → 터미널에서 열기:
```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```
**macOS** — 터미널에서:
```bash
bash setup.sh
```
설치하는 것: Node.js, ffmpeg, Python 3.12, 파이썬 패키지(`.venv`), HyperFrames(렌더용 크롬), Claude Code 전역 스킬 `book-youtube`.
끝나면 **터미널을 새로 연다.**

Claude Code 가 없다면: https://claude.com/claude-code 에서 설치(데스크톱 앱 또는 `npm i -g @anthropic-ai/claude-code`).

## 3. 키 넣기

설치가 만든 `.env` 를 열어 두 줄을 채운다 (Windows `notepad .env`, macOS `open -e .env`).

| 키 | 어디서 | 쓰임 |
|---|---|---|
| `GEMINI_API_KEY` | https://aistudio.google.com/apikey — **결제 켜기** 필요 | 배경 이미지 7장/편 |
| `TYPECAST_API_KEY` | https://typecast.ai → API | 한국어 음성 8줄/편 |

`.env` 는 절대 남에게 보내거나 올리지 않는다(.gitignore 에 들어 있음).

## 4. 만들기

키트 폴더에서 Claude Code 를 열고 말한다:

```
대충영어 책 홍보 쇼츠 1부 만들어
```
Claude 가 스킬대로 진행한다: 책 찾기 → 근거 모으기 → 1·2·3부 기획(확인 받음) → 원고 → 근거 대조 → 이미지·음성 → 렌더 → 검수 → 보여 주기.
결과: `books/<책>/out/part1.mp4`

손으로 돌리고 싶다면 (Windows 는 `.venv\Scripts\python.exe`):
```bash
.venv/bin/python tools/book_research.py "책 이름"
.venv/bin/python tools/check_evidence.py books/책이름/part1.json
.venv/bin/python make_part.py books/책이름/part1.json
```

## 5. 비용

한 편에 Gemini 이미지 7장 + Typecast 음성 약 160음절. 같은 문장·같은 그림은 캐시되어 다시 만들 때 돈이 들지 않는다.

## 6. 올리기

**쉬운 길 (권장)** — YouTube Studio → 만들기 → 동영상 업로드 → `out/part1.mp4`
1. 제목·설명은 `part1.upload.json` 에서 복사
2. **「변경되거나 합성된 콘텐츠」 = 예** (AI 이미지·합성 음성 — 꼭 켠다)
3. 공개 → 게시 후 댓글에 구매 링크를 달고 ⋮ → **고정**

**자동 업로드 (선택)** — Google Cloud Console 에서 YouTube Data API v3 를 켜고 OAuth 클라이언트(데스크톱 앱)를 만들어 JSON 을 `secrets/client_secret.json` 으로 저장한 뒤:
```bash
.venv/bin/python upload.py books/책이름/part1.upload.json
```

## 7. 업데이트

```bash
git pull
```
(설치 스크립트를 다시 돌릴 필요는 보통 없다. requirements.txt 가 바뀌었으면 `.venv/bin/python -m pip install -r requirements.txt`.)

## 문제 해결

| 증상 | 해결 |
|---|---|
| `ffmpeg 를 찾을 수 없다` | 설치 후 터미널을 새로 열었는지 |
| `Gemini 키 확인 실패 401/403` | 키 오타, 또는 AI Studio 에서 결제 미설정 |
| 이미지에 글자·액자·콜라주 | `make_part.py … --regen-img 번호` 로 그 장만 다시 |
| 렌더가 바로 실패 | `npx --yes hyperframes@0.8.143 --version` 으로 크롬 다운로드 확인 |
| Windows 한글 깨짐 | `chcp 65001` 후 다시 |

## 저작권·주의
- `sources.md` 는 온라인 서점의 책 소개 글이다. 원고 근거용으로만 쓰고 그대로 퍼뜨리지 않는다.
- 글꼴: Pretendard(SIL OFL), Gmarket Sans(G마켓 무료 글꼴 — 글꼴 자체 판매 금지).
- 영상에 「효과에는 개인차가 있습니다」를 남기고, 효능·기간 약속은 쓰지 않는다.
