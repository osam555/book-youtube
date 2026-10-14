#!/usr/bin/env python3
"""원고의 근거가 진짜 책 글에 있는지 대조한다 — 렌더 전에 반드시 돌린다.

    python tools/check_evidence.py books/대충영어/part1.json

각 줄의 "evidence" 안 「 」 로 감싼 인용을 모두 꺼내, 같은 책 폴더의 sources.md(+ 있으면 book.txt)에
그대로 있는지 본다(띄어쓰기·따옴표·문장부호 무시). 인용 안의 「…」 는 중간 생략으로 보고 조각마다 찾는다.
한 줄이라도 인용이 없거나 못 찾으면 종료코드 1.
"""
import json, re, sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

norm = lambda s: re.sub(r"[^0-9A-Za-z가-힣]", "", s)


def main():
    spec_p = Path(sys.argv[1])
    spec = json.loads(spec_p.read_text(encoding="utf-8"))
    d = spec_p.parent
    corpus = ""
    for name in ("sources.md", "book.txt"):
        if (d / name).exists():
            corpus += (d / name).read_text(encoding="utf-8")
    if not corpus:
        sys.exit("✖ sources.md / book.txt 가 없다 — tools/book_research.py 먼저")
    C = norm(corpus)
    bad = 0
    for i, ln in enumerate(spec["lines"], 1):
        quotes = re.findall(r"「(.+?)」", ln.get("evidence", ""))
        if not quotes:
            print(f"✗ {i}줄: 인용(「…」)이 없다 — {ln.get('say', '')}"); bad += 1; continue
        for q in quotes:
            miss = [p for p in re.split(r"…|\.\.\.", q) if len(norm(p)) >= 4 and norm(p) not in C]
            if miss:
                print(f"✗ {i}줄: 책 글에서 못 찾음 → {miss}"); bad += 1
            else:
                print(f"✓ {i}줄: 「{q[:40]}…」")
    print("근거 대조", "통과" if not bad else f"실패 {bad}건")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
