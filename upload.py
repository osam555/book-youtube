#!/usr/bin/env python3
"""(선택) 유튜브 자동 업로드 — 즉시 공개 + AI 공시 + 구매 링크 댓글.
가장 쉬운 방법은 이 스크립트 대신 YouTube Studio 에서 손으로 올리는 것이다(README 「6. 올리기」).

준비(한 번): Google Cloud 에서 OAuth 클라이언트(데스크톱 앱)를 만들고 JSON 을 secrets/client_secret.json 으로 저장.
    python upload.py books/대충영어/part1.upload.json
처음 실행하면 브라우저가 열려 채널 계정으로 로그인·허용 → secrets/token.json 저장. 올리기 전에 채널 이름을 묻는다.
댓글 「고정」은 API 로 안 된다 — Studio 에서 댓글 ⋮ → 고정.
"""
import json, sys, datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

KIT = Path(__file__).resolve().parent
SEC = KIT / "secrets"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.force-ssl"]


def service():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    tok = SEC / "token.json"
    c = Credentials.from_authorized_user_file(str(tok), SCOPES) if tok.exists() else None
    if c and not c.valid and c.refresh_token:
        c.refresh(Request())
    if not c or not c.valid:
        if not (SEC / "client_secret.json").exists():
            sys.exit("✖ secrets/client_secret.json 이 없다 — README 「6. 올리기」의 준비를 먼저")
        c = InstalledAppFlow.from_client_secrets_file(str(SEC / "client_secret.json"), SCOPES).run_local_server(port=0)
    SEC.mkdir(exist_ok=True); tok.write_text(c.to_json(), encoding="utf-8")
    return build("youtube", "v3", credentials=c)


def main():
    mp = Path(sys.argv[1]).resolve()
    meta = json.loads(mp.read_text(encoding="utf-8"))
    pid = mp.name.split(".")[0]                                   # part1.upload.json → part1
    mp4 = mp.parent / "out" / f"{pid}.mp4"
    ledger = mp.parent / "uploaded.json"
    rows = json.loads(ledger.read_text(encoding="utf-8")) if ledger.exists() else []
    if any(r["id"] == pid for r in rows):
        sys.exit(f"이미 올렸다: {[r for r in rows if r['id'] == pid]}")
    y = service()
    ch = y.channels().list(part="snippet", mine=True).execute()["items"][0]["snippet"]["title"]
    if input(f"채널 「{ch}」 에 {mp4.name} 를 공개로 올린다. 계속? (y/n) ").strip().lower() != "y":
        sys.exit("취소")
    from googleapiclient.http import MediaFileUpload
    body = {"snippet": {"title": meta["title"][:100], "description": meta["description"], "categoryId": "27",
                        "tags": meta.get("tags", []), "defaultLanguage": "ko", "defaultAudioLanguage": "ko"},
            "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False, "embeddable": True,
                       "containsSyntheticMedia": True}}     # AI 이미지·합성 음성 — 반드시 켠다(API 로 다시 읽어 확인은 안 됨 → Studio 에서 확인)
    vid = y.videos().insert(part="snippet,status", body=body,
                            media_body=MediaFileUpload(str(mp4), chunksize=-1, resumable=True, mimetype="video/mp4")).execute()["id"]
    rows.append({"id": pid, "video_id": vid, "channel": ch, "at": datetime.datetime.now().isoformat(timespec="seconds")})
    ledger.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print("업로드:", f"https://youtube.com/shorts/{vid}")
    if meta.get("comment"):
        try:
            y.commentThreads().insert(part="snippet", body={"snippet": {"videoId": vid, "topLevelComment": {
                "snippet": {"textOriginal": meta["comment"]}}}}).execute()
            print("댓글 달림 — Studio 에서 고정할 것")
        except Exception as e:
            print("⚠ 댓글 실패(Studio 에서 손으로):", str(e)[:150])
    print(f"⚠ AI 공시 확인: https://studio.youtube.com/video/{vid}/edit → 모두 표시 → 변경되거나 합성된 콘텐츠 = 예")


if __name__ == "__main__":
    main()
