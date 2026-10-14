#!/usr/bin/env python3
"""책 이름 → 책 정보·근거 글·표지를 모은다 (예스24 상품 페이지 + 교보문고 검색).

    python tools/book_research.py "대충영어" [--author 오승종] [--yes24 165030814]

결과: books/<책이름>/
  book.json   제목·저자·출판사·표지·구매 링크(예스24·교보)
  sources.md  책소개·목차·책 속으로·출판사 리뷰·저자 소개 원문 — 원고의 「근거」는 반드시 이 파일(또는 book.txt)에 있는 문장만
  cover.jpg   표지

검색 결과가 엉뚱한 책이면 --author 로 좁히거나 --yes24 <상품번호> 로 직접 지정한다.
교보문고 상품 페이지는 자동 수집을 막아서, 교보 링크는 검색 결과의 첫 상품을 적어 둔다 — 사람이 한 번 열어 확인할 것.
"""
import argparse, html, json, re, sys, urllib.parse
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
UA = {"User-Agent": "Mozilla/5.0",            # ⚠ 크롬 전체 UA 를 쓰면 예스24 가 검색 결과 없는 다른 페이지를 준다(2026-10-14 실측)
      "Accept-Language": "ko-KR,ko;q=0.9"}
SECTIONS = [("infoset_introduce", "책소개"), ("infoset_toc", "목차"), ("infoset_inBook", "책 속으로"),
            ("infoset_pubReivew", "출판사 리뷰"), ("infoset_authorGrp", "저자 소개")]

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def get(url):
    r = requests.get(url, headers=UA, timeout=30)
    r.raise_for_status()
    r.encoding = "utf-8"
    return r.text


def clean(fragment):
    t = re.sub(r"<script.*?</script>|<style.*?</style>", "", fragment, flags=re.S)
    t = html.unescape(t)                                   # textarea 안은 한 번 더 이스케이프돼 있다
    t = re.sub(r"<br\s*/?>", "\n", t)
    t = re.sub(r"</p>|</div>|</li>", "\n", t)
    t = html.unescape(re.sub(r"<[^>]+>", "", t))
    t = re.sub(r"[ \t ]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n\n", t)
    return t.strip()


def yes24_search(title, author=None):
    q = urllib.parse.quote(f"{title} {author or ''}".strip())
    s = get(f"https://www.yes24.com/Product/Search?domain=BOOK&query={q}")
    i = s.find('id="yesSchList"')                         # 실제 검색 결과 목록만 (위쪽 광고·추천 상품 제외)
    ids = list(dict.fromkeys(re.findall(r"/product/goods/(\d+)", s[i:] if i > 0 else s, flags=re.I)))
    if not ids:
        sys.exit("✖ 예스24 검색 결과가 없다 — 제목을 바꾸거나 --yes24 로 상품번호를 직접 넣을 것")
    return ids


def yes24_page(gid):
    s = get(f"https://www.yes24.com/product/goods/{gid}")
    meta = lambda k: (re.search(r'property="%s" content="([^"]+)"' % k, s) or [None, ""])[1]
    title = html.unescape(meta("og:title")).replace(" - 예스24", "")
    parts = [p.strip() for p in title.split("|")]
    out = {"title": parts[0], "author": parts[1] if len(parts) > 1 else "", "publisher": parts[2] if len(parts) > 2 else "",
           "cover_url": meta("og:image"), "yes24_url": f"https://www.yes24.com/product/goods/{gid}", "sections": {}}
    for sid, name in SECTIONS:
        i = s.find(f'id="{sid}"')
        if i < 0:
            continue
        j = s.find('<div id="infoset_', i + 10)
        body = s[s.find('>', i) + 1:j if j > 0 else i + 60000]     # 여는 태그의 속성 글자는 버린다
        body = re.sub(r'<h4 class="tit_txt">.*?</h4>', "", body, flags=re.S)
        txt = clean(body)
        txt = re.sub(r"(펼쳐보기|접기|더보기)\s*$", "", txt).strip()
        if len(txt) > 30:
            out["sections"][name] = txt
    return out


def kyobo_first(title, author=None):
    """교보 검색 결과에서 「[국내도서] <제목>」이 정확히 맞는 첫 상품. 맨 앞 상품이 다른 판(ebook·세트)인 경우가 있다(2026-10-14 실측)."""
    q = urllib.parse.quote(f"{title} {author or ''}".strip())
    try:
        s = get(f"https://search.kyobobook.co.kr/search?keyword={q}")
    except Exception:
        return ""
    want = title.replace(" ", "")
    for pid in dict.fromkeys(re.findall(r"상품 제목&#39;, &quot;(S\d+)", s)):
        i = s.find(f"상품 제목&#39;, &quot;{pid}")
        txt = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s[i:i + 1500])))
        m = re.search(r"\[국내도서\]\s*(.+?)\s*(?:더보기|$)", txt)
        if m and m.group(1).replace(" ", "") == want:
            return f"https://product.kyobobook.co.kr/detail/{pid}"
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("title"); ap.add_argument("--author"); ap.add_argument("--yes24")
    a = ap.parse_args()
    if a.yes24:
        info = yes24_page(a.yes24)
    else:
        info = None
        for gid in yes24_search(a.title, a.author)[:6]:          # 제목이 맞는 첫 「책」(음반·굿즈 제외)
            cand = yes24_page(gid)
            if a.title.replace(" ", "") in cand["title"].replace(" ", "") and cand["sections"]:
                info = cand; break
        if not info:
            sys.exit("✖ 제목이 맞는 책을 못 찾았다 — --author 나 --yes24 <상품번호> 를 쓸 것")
    info["kyobo_url"] = kyobo_first(info["title"], info["author"].split(" ")[0] if info["author"] else None)
    slug = re.sub(r'[\\/:*?"<>|]', "", info["title"]).strip().replace(" ", "_")
    d = ROOT / "books" / slug
    d.mkdir(parents=True, exist_ok=True)
    if info["cover_url"]:
        r = requests.get(info["cover_url"], headers=UA, timeout=30)
        if r.ok and len(r.content) > 5000:
            (d / "cover.jpg").write_bytes(r.content)
    md = [f"# {info['title']} — 근거 원문", f"출처: {info['yes24_url']}", ""]
    for name, txt in info["sections"].items():
        md += [f"## {name}", "", txt, ""]
    (d / "sources.md").write_text("\n".join(md), encoding="utf-8")
    sec = info.pop("sections")
    info["sections_found"] = list(sec)
    info["buy_url"] = info["kyobo_url"] or info["yes24_url"]
    (d / "book.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(info, ensure_ascii=False, indent=2))
    print(f"\n→ {d}  (sources.md {sum(len(x) for x in sec.values()):,}자, 표지 {'있음' if (d / 'cover.jpg').exists() else '없음'})")
    if info["kyobo_url"]:
        print("⚠ 교보 링크는 검색 첫 결과다 — 브라우저로 열어 같은 책인지 확인할 것")


if __name__ == "__main__":
    main()
