#!/usr/bin/env python3
"""(선택) 책 PDF 가 있으면 본문 글을 뽑아 근거로 쓴다 — 웹 자료보다 훨씬 많다.

    python tools/pdf_text.py books/대충영어/book.pdf
→ 같은 폴더 book.txt (쪽마다 「=====P12」 표시). check_evidence.py 가 sources.md 와 함께 대조한다.
PDF 는 저작권이 있으니 권리자에게 받은 것만 쓰고, 다른 사람에게 다시 나눠 주지 않는다.
"""
import sys
from pathlib import Path
import fitz  # PyMuPDF

p = Path(sys.argv[1])
doc = fitz.open(p)
txt = "\n".join(f"=====P{i + 1}\n{pg.get_text()}" for i, pg in enumerate(doc))
out = p.with_name("book.txt")
out.write_text(txt, encoding="utf-8")
print(f"{doc.page_count}쪽 → {out} ({len(txt):,}자)")
