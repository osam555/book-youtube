# book-youtube-kit

책 이름 하나로 그 책의 홍보 쇼츠(시네마틱 3부작)를 만드는 키트. **작업 절차는 스킬 `.claude/skills/book-youtube/SKILL.md` 를 먼저 읽고 그대로 따른다.**

- 파이썬은 가상환경: Windows `.venv\Scripts\python.exe`, macOS `.venv/bin/python`
- `.env` 의 키는 출력·복사·커밋 금지. `secrets/` 도 마찬가지
- 원고 근거는 `books/<책>/sources.md`(·`book.txt`)의 원문만. 렌더 전 `tools/check_evidence.py` 통과 필수
- 유튜브 업로드·공개는 사용자 승인 후에만
