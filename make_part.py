#!/usr/bin/env python3
"""책 홍보 시네마틱 쇼츠 한 편 만들기 — Windows / macOS 공용.

    python make_part.py books/대충영어/part1.json [--no-render] [--regen-img 3,5] [--no-qa]

단계: ① Gemini 배경 이미지(캐시 books/<책>/img/) ② Typecast 문장별 음성(캐시 tts-cache/) → 줄마다 −14 LUFS
      ③ HyperFrames 조립·렌더(books/<책>/work-<id>/) ④ 음량·무음·형식 QA + 눈 검사용 프레임 시트
산출: books/<책>/out/<id>.mp4 · <id>.qa.json · <id>.frames.jpg
키: 키트 폴더의 .env (GEMINI_API_KEY, TYPECAST_API_KEY) — 화면·로그에 출력하지 않는다.
종료코드 0 = 통과 · 3 = QA 실패(파일은 남김) · 그 밖 = 오류
"""
import argparse, hashlib, io, json, os, re, shutil, subprocess, sys, time, wave
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
from pathlib import Path
import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8"); sys.stderr.reconfigure(encoding="utf-8")   # Windows 콘솔(cp949)에서 한글·이모지 깨짐 방지
except Exception:
    pass

KIT = Path(__file__).resolve().parent
W, H, FPS, SR = 1080, 1920, 30, 48000
HF_VER = "0.8.143"                       # 올릴 때는 한 편 시험 렌더 후
TARGET = -14.0
VOICES = {"Jiseon": "tc_6a4f2130d153a5cac8e19996", "Hyunjun": "tc_6a6194d59eea84806aea652c"}   # 여성 / 남성
TEMPO = 1.05
LEAD, GAP, TAIL = 0.25, 0.32, 1.1        # 첫 소리 전 · 문장 사이 · 끝 뒤 (초)
XF = 0.45                                # 배경 교차 전환
IS_WIN = os.name == "nt"

IMG_STYLE = ("Single full-bleed photograph filling the whole frame edge to edge — no borders, no inset frames, no collage, "
             "no split panels. Photorealistic cinematic film still, shot on 35mm, shallow depth of field, dramatic but warm "
             "lighting, subtle film grain, rich slightly muted colors. Vertical 9:16 composition; keep the top 20% and the "
             "middle band visually calm so large white captions stay readable.")
IMG_NEG = ("Absolutely no text of any kind: no letters, no words, no captions, no signs, no logos, no watermarks, no readable "
           "book titles or pages, no shop signs or billboards. No celebrities or recognizable real people.")


# ───────────────────────── 공통 ─────────────────────────
def env(name):
    v = os.environ.get(name)
    if not v and (KIT / ".env").exists():
        for ln in (KIT / ".env").read_text(encoding="utf-8").splitlines():
            if ln.strip().startswith(name + "="):
                v = ln.split("=", 1)[1].strip().strip('"').strip("'")
    if not v:
        sys.exit(f"✖ {name} 가 없다 — 키트 폴더의 .env 에 넣을 것 (.env.example 참고)")
    return v


def need(tool):
    p = shutil.which(tool)
    if not p:
        sys.exit(f"✖ {tool} 를 찾을 수 없다 — README 의 설치 단계를 먼저 (설치 후 새 터미널을 열 것)")
    return p


def sh(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, encoding="utf-8", errors="replace", **kw)


def lufs_of(p):
    r = subprocess.run([need("ffmpeg"), "-nostats", "-i", str(p), "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    m = re.findall(r"I:\s*(-?[\d.]+) LUFS", r.stderr)
    return float(m[-1]) if m else None


def read_wav(p):
    with wave.open(str(p)) as w:
        a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float64)
        return a.reshape(-1, w.getnchannels())


def write_wav(p, a):
    a = np.clip(a, -32767, 32767).astype(np.int16)
    with wave.open(str(p), "wb") as w:
        w.setnchannels(a.shape[1]); w.setsampwidth(2); w.setframerate(SR); w.writeframes(a.tobytes())


def log_usage(name, row):
    with open(KIT / name, "a", encoding="utf-8") as f:
        f.write(json.dumps({"t": time.strftime("%F %T"), **row}, ensure_ascii=False) + "\n")


# ───────────────────────── ① 배경 이미지 (Gemini) ─────────────────────────
def pick_image_model(key):
    import requests
    r = requests.get("https://generativelanguage.googleapis.com/v1beta/models?pageSize=200",
                     headers={"x-goog-api-key": key}, timeout=30)
    if r.status_code != 200:
        sys.exit(f"✖ Gemini 키 확인 실패 {r.status_code} — 키가 맞는지, 결제가 켜져 있는지 확인")
    names = [m["name"].split("/", 1)[-1] for m in r.json().get("models", [])
             if "generateContent" in m.get("supportedGenerationMethods", []) and "image" in m["name"] and "veo" not in m["name"]]
    if not names:
        sys.exit("✖ 이 키로 쓸 수 있는 이미지 생성 모델이 없다")
    def rank(n):
        m = re.search(r"(\d+(?:\.\d+)?)", n)
        return ("preview" in n or "exp" in n, -(float(m.group(1)) if m else 0), len(n))
    return sorted(names, key=rank)[0]


def gen_image(client, model, prompt):
    from google.genai import types
    def call():
        try:
            cfg = types.GenerateContentConfig(image_config=types.ImageConfig(aspect_ratio="9:16"))
            return client.models.generate_content(model=model, contents=prompt, config=cfg)
        except (TypeError, AttributeError, ValueError):
            return client.models.generate_content(model=model, contents=prompt)
    with ThreadPoolExecutor(1) as ex:                     # SDK 가 응답 없이 매달리는 일이 있다 — 120초 제한(Windows 에는 SIGALRM 이 없다)
        resp = ex.submit(call).result(timeout=120)
    for cand in (resp.candidates or []):
        for part in (cand.content.parts or []):
            d = getattr(part, "inline_data", None)
            if d and d.data:
                return d.data
    raise RuntimeError(f"이미지가 안 왔다: {(getattr(resp, 'text', '') or '')[:150]}")


def to_1080x1920(raw):
    from PIL import Image
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    s = max(W / img.width, H / img.height)
    img = img.resize((round(img.width * s), round(img.height * s)), Image.LANCZOS)
    x, y = (img.width - W) // 2, (img.height - H) // 2
    return img.crop((x, y, x + W, y + H))


def make_images(spec, bdir, regen):
    d = bdir / "img"; d.mkdir(exist_ok=True)
    need_ = [(i, ln["img"]) for i, ln in enumerate(spec["lines"])
             if ln.get("img") and ((i + 1) in regen or not (d / f"{spec['id']}-{i+1:02d}.png").exists())]
    if not need_:
        return
    from google import genai
    key = env("GEMINI_API_KEY")
    model = pick_image_model(key); client = genai.Client(api_key=key)
    print(f"   이미지 모델: {model}", flush=True)
    for i, p in need_:
        dst = d / f"{spec['id']}-{i+1:02d}.png"
        for attempt in range(2):
            try:
                to_1080x1920(gen_image(client, model, f"{p}\n\n{IMG_STYLE}\n{IMG_NEG}")).save(dst)
                print(f"   img {i+1:02d} ✓", flush=True); break
            except (Exception, FutTimeout) as e:
                print(f"   img {i+1:02d} 실패({str(e)[:100]})", flush=True)
                if attempt: raise
                time.sleep(4)
        log_usage("image-usage.jsonl", {"model": model, "id": spec["id"], "n": i + 1})


# ───────────────────────── ② 소리 (Typecast) ─────────────────────────
_last = [0.0]


def typecast(text, voice_id, path):
    """Typecast v1 → WAV. 영구 캐시(같은 목소리·글이면 다시 부르지 않는다), 호출 사이 3초."""
    import requests
    k = hashlib.sha256(json.dumps([voice_id, "ssfm-v30", TEMPO, "normal", 1, text], ensure_ascii=False).encode()).hexdigest()[:24]
    cdir = KIT / "tts-cache"; cdir.mkdir(exist_ok=True)
    cf = cdir / f"{k}.wav"
    if cf.exists() and cf.stat().st_size > 1000:
        shutil.copy(cf, path); return
    wait = 3.0 - (time.time() - _last[0])
    if wait > 0: time.sleep(wait)
    r = requests.post("https://api.typecast.ai/v1/text-to-speech",
                      headers={"X-API-KEY": env("TYPECAST_API_KEY"), "Content-Type": "application/json"},
                      json={"voice_id": voice_id, "text": text, "model": "ssfm-v30", "language": "kor",
                            "prompt": {"emotion_preset": "normal", "emotion_intensity": 1},
                            "output": {"volume": 100, "audio_pitch": 0, "audio_tempo": TEMPO, "audio_format": "wav"}},
                      timeout=120)
    _last[0] = time.time()
    log_usage("typecast-usage.jsonl", {"status": r.status_code, "chars": len(text)})
    if r.status_code != 200:
        sys.exit(f"✖ Typecast {r.status_code}: {r.text[:200]}")
    cf.write_bytes(r.content)
    shutil.copy(cf, path)


def make_audio(spec, work):
    ff = need("ffmpeg")
    vid = VOICES[spec.get("voice", "Jiseon")]
    tdir = work / "tts"; tdir.mkdir(parents=True, exist_ok=True)
    clips = []
    for i, ln in enumerate(spec["lines"]):
        say = ln["say"]
        if re.search(r"[0-9A-Za-z]", say):
            print(f"⚠ 소리 글에 숫자/영문이 있다(한글로 풀어 쓸 것): {say}")
        raw = tdir / f"{i:02d}-raw.wav"
        typecast(say, vid, raw)
        trim = tdir / f"{i:02d}.wav"
        sh([ff, "-y", "-v", "error", "-i", str(raw), "-af",
            "silenceremove=start_periods=1:start_silence=0.05:start_threshold=-45dB,areverse,"
            "silenceremove=start_periods=1:start_silence=0.08:start_threshold=-45dB,areverse,"
            "aformat=sample_rates=48000:channel_layouts=stereo", "-c:a", "pcm_s16le", str(trim)])
        clips.append(read_wav(trim) * 10 ** ((TARGET - lufs_of(trim)) / 20))      # 줄마다 먼저 −14
    t, plan = LEAD, []
    for a in clips:
        plan.append({"t0": round(t, 3), "d": round(len(a) / SR, 3)})
        t += len(a) / SR + GAP
    dur = round(plan[-1]["t0"] + plan[-1]["d"] + TAIL, 2)
    mix = np.zeros((int(dur * SR) + SR, 2))
    for a, p in zip(clips, plan):
        s = int(p["t0"] * SR); mix[s:s + len(a)] += a
    pre = work / "mix_pre.wav"; write_wav(pre, mix[:int(dur * SR)])
    final = work / "audio.wav"
    for _ in range(3):
        sh([ff, "-y", "-v", "error", "-i", str(pre), "-af", "alimiter=limit=0.84:attack=3:release=60:level=disabled",
            "-c:a", "pcm_s16le", str(final)])
        lf = lufs_of(final)
        if abs(lf - TARGET) < 0.25: break
        write_wav(pre, read_wav(pre) * 10 ** ((TARGET - lf) / 20))
    return plan, dur


# ───────────────────────── ③ 화면 (HyperFrames) ─────────────────────────
def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def hl(s):
    """숫자+단위와 《책 이름》을 노랑으로."""
    s = esc(s)
    s = re.sub(r"(\d[\d,.]*\s*(?:년|만 시간|시간|쪽|배속|개|명|%|억|만)?)", r"<em>\1</em>", s)
    s = re.sub(r"(《[^》]+》)", r"<em>\1</em>", s)
    return s


STYLE = r'''
@font-face{font-family:"GM";src:url("fonts/GmarketSansBold.otf");font-weight:700}
@font-face{font-family:"GM";src:url("fonts/GmarketSansMedium.otf");font-weight:500}
@font-face{font-family:"PB";src:url("fonts/Pretendard-Bold.otf");font-weight:700}
@font-face{font-family:"PB";src:url("fonts/Pretendard-Regular.otf");font-weight:400}
html,body{margin:0;background:#000}
#root{position:relative;width:1080px;height:1920px;overflow:hidden;font-family:"PB",sans-serif;color:#fff}
.bg{position:absolute;inset:-40px;opacity:0;will-change:transform,opacity}
.bg img{width:100%;height:100%;object-fit:cover;display:block}
.scrim{position:absolute;inset:0;background:linear-gradient(180deg,rgba(0,0,0,.55) 0%,rgba(0,0,0,0) 26%,rgba(0,0,0,0) 48%,rgba(0,0,0,.45) 70%,rgba(0,0,0,.75) 100%)}
.band{position:absolute;left:60px;right:60px;top:150px;text-align:center}
.band .t{display:inline-block;background:#000;color:#fff;font-family:"GM";font-weight:700;font-size:66px;line-height:1.18;padding:14px 30px 10px;letter-spacing:-1px}
.band .t em{font-style:normal;color:#FFD43B}
.band .s{margin-top:14px;font-family:"PB";font-weight:700;font-size:32px;color:#fff;text-shadow:0 2px 8px rgba(0,0,0,.9)}
.cap{position:absolute;left:70px;right:70px;top:1040px;height:300px;display:flex;align-items:center;justify-content:center;text-align:center;
 font-family:"GM";font-weight:700;font-size:74px;line-height:1.22;letter-spacing:-1.5px;word-break:keep-all;opacity:0;
 text-shadow:0 0 6px #000,0 0 14px rgba(0,0,0,.85),3px 3px 0 #000,-3px 3px 0 #000,3px -3px 0 #000,-3px -3px 0 #000}
.cap em{font-style:normal;color:#FFD43B}
#endc{position:absolute;inset:0;opacity:0}
#endbg{position:absolute;inset:0;background:radial-gradient(110% 70% at 50% 38%,#2b2416 0%,#0d0b08 70%)}
#rays{position:absolute;left:50%;top:700px;width:1600px;height:1600px;margin:-800px 0 0 -800px;border-radius:50%;
 background:conic-gradient(from 0deg,rgba(255,212,59,.0),rgba(255,212,59,.14),rgba(255,212,59,0) 12%,rgba(255,212,59,.12) 25%,rgba(255,212,59,0) 37%,rgba(255,212,59,.12) 50%,rgba(255,212,59,0) 62%,rgba(255,212,59,.12) 75%,rgba(255,212,59,0) 87%,rgba(255,212,59,.14));filter:blur(6px)}
#cov{position:absolute;left:300px;top:430px;width:480px;filter:drop-shadow(0 50px 40px rgba(0,0,0,.7))}
#cov img{width:100%;display:block;border-radius:6px}
.et{position:absolute;left:0;right:0;text-align:center}
#e1{top:960px;font-family:"GM";font-weight:700;font-size:62px;color:#fff;letter-spacing:-1px;line-height:1.25;padding:0 60px}
#e1 em{font-style:normal;color:#FFD43B}
#e2{top:1125px;font-family:"PB";font-weight:700;font-size:36px;color:rgba(255,255,255,.85)}
#e3{top:1210px;left:50%;right:auto;width:660px;margin-left:-330px;height:104px;border-radius:52px;background:linear-gradient(95deg,#FFB020,#FF8A14);
 color:#2a1a00;font-family:"GM";font-weight:700;font-size:44px;display:flex;align-items:center;justify-content:center;box-shadow:0 26px 40px -16px rgba(255,138,20,.65)}
#e4{top:1350px;font-family:"PB";font-weight:400;font-size:28px;color:rgba(255,255,255,.6)}
'''


def cover_of(bdir):
    for n in ("cover.png", "cover.jpg", "cover.jpeg", "cover.webp"):
        if (bdir / n).exists():
            return bdir / n
    sys.exit(f"✖ 표지가 없다: {bdir}/cover.jpg (tools/book_research.py 가 받아 온다)")


def make_html(spec, plan, dur, work, bdir):
    B, J = [], []
    add = J.append
    lines = spec["lines"]; n = len(lines)
    img_idx = [i for i, ln in enumerate(lines) if ln.get("img")]
    for k, i in enumerate(img_idx):                       # 배경: 자기 줄 시작에 들어와 다음 그림까지, 확대/축소 번갈아
        B.append(f'<div class="bg" id="bg{i}"><img src="img/{spec["id"]}-{i+1:02d}.png"></div>')
        t_in = max(0, plan[i]["t0"] - XF / 2) if k else 0
        nxt = img_idx[k + 1] if k + 1 < len(img_idx) else n - 1
        span = plan[nxt]["t0"] + XF - t_in
        dx, s0, s1 = (-30, 1.0, 1.12) if k % 2 == 0 else (30, 1.12, 1.02)
        add(f'tl.set("#bg{i}",{{opacity:{1 if k == 0 else 0}}},0);')
        if k:
            add(f'tl.to("#bg{i}",{{opacity:1,duration:{XF},ease:"none"}},{t_in:.3f});')
        add(f'tl.fromTo("#bg{i}",{{scale:{s0},x:{-dx}}},{{scale:{s1},x:{dx},duration:{span:.3f},ease:"none"}},{t_in:.3f});')
    B.append('<div class="scrim"></div>')
    tt = "<br>".join(hl(x) for x in spec["title_top"])
    B.append(f'<div class="band" id="band"><div class="t">{tt}</div><div class="s">{esc(spec.get("title_sub", ""))}</div></div>')
    add('tl.from("#band .t",{y:-60,opacity:0,duration:.45,ease:"back.out(1.8)"},0.02);')
    add('tl.from("#band .s",{opacity:0,duration:.4},0.35);')
    cid = 0
    for i, ln in enumerate(lines[:-1]):                   # 자막: '|' 조각을 글자 수 비율로 (마지막 줄은 끝 카드가 대신)
        parts = ln["cap"].split("|"); tot = sum(len(p) for p in parts)
        t = plan[i]["t0"]; d = plan[i]["d"]
        for j, p in enumerate(parts):
            pd = d * len(p) / tot
            t_out = t + pd + (GAP if j == len(parts) - 1 else 0) - 0.04
            # ⚠ .cap 은 flex — 안에 <em> 을 바로 두면 앞뒤 띄어쓰기가 사라진다 → <span> 으로 감싼다
            B.append(f'<div class="cap" id="c{cid}"><span>{hl(p)}</span></div>')
            add(f'tl.fromTo("#c{cid}",{{opacity:0,scale:.82,y:24}},{{opacity:1,scale:1,y:0,duration:.22,ease:"back.out(2.2)"}},{t:.3f});')
            add(f'tl.set("#c{cid}",{{opacity:0}},{t_out:.3f});')
            t += pd; cid += 1
    e = spec["end"]; tl0 = plan[-1]["t0"] - 0.15
    cov = cover_of(bdir)
    B.append('<div id="endc"><div id="endbg"></div><div id="rays"></div>'
             f'<div id="cov"><img src="assets/{cov.name}"></div>'
             f'<div class="et" id="e1">{esc(e["slogan"])}<br><em>{esc(e["book"])}</em></div>'
             f'<div class="et" id="e2">{esc(e["by"])}</div>'
             f'<div class="et" id="e3">{esc(e["cta"])}</div>'
             f'<div class="et" id="e4">{esc(e.get("note", ""))}</div></div>')
    add(f'tl.to("#endc",{{opacity:1,duration:.4,ease:"none"}},{tl0:.3f});')
    add(f'tl.to("#band",{{opacity:0,y:-40,duration:.35}},{tl0:.3f});')
    add(f'tl.fromTo("#rays",{{rotation:0}},{{rotation:40,duration:{dur - tl0:.2f},ease:"none"}},{tl0:.3f});')
    add(f'tl.fromTo("#cov",{{y:260,opacity:0,rotation:7,scale:.8}},{{y:-190,opacity:1,rotation:-3,scale:1,duration:.75,ease:"back.out(1.6)"}},{tl0 + .1:.3f});')
    add(f'tl.to("#cov",{{y:-208,duration:1.2,yoyo:true,repeat:3,ease:"sine.inOut"}},{tl0 + .9:.3f});')
    add(f'tl.from("#e1",{{y:40,opacity:0,duration:.4,ease:"power3.out"}},{tl0 + .35:.3f});')
    add(f'tl.from("#e2",{{opacity:0,duration:.4}},{tl0 + .7:.3f});')
    t_cta = plan[-1]["t0"] + plan[-1]["d"] * 0.55
    add(f'tl.fromTo("#e3",{{scale:.4,opacity:0}},{{scale:1,opacity:1,duration:.4,ease:"back.out(2.4)"}},{t_cta:.3f});')
    add(f'tl.to("#e3",{{scale:1.06,duration:.35,yoyo:true,repeat:3,ease:"sine.inOut"}},{t_cta + .5:.3f});')
    add(f'tl.from("#e4",{{opacity:0,duration:.4}},{t_cta + .2:.3f});')
    html = f'''<!doctype html>
<html lang="ko"><head><meta charset="UTF-8"><meta name="viewport" content="width=1080, height=1920"><title>book-youtube-{spec["id"]}</title>
<script src="gsap.min.js"></script><style>{STYLE}</style></head><body>
<div id="root" data-composition-id="scene" data-start="0" data-width="{W}" data-height="{H}" data-duration="{dur}">
{chr(10).join(B)}
<audio id="narr" src="audio.wav" data-start="0" data-duration="{dur}" data-track-index="0" data-volume="1"></audio>
</div>
<script>
const tl=gsap.timeline({{paused:true}});
{chr(10).join(J)}
window.__timelines=window.__timelines||{{}};window.__timelines["scene"]=tl;
</script></body></html>'''
    (work / "index.html").write_text(html, encoding="utf-8")
    if (work / "fonts").exists(): shutil.rmtree(work / "fonts")
    shutil.copytree(KIT / "assets/fonts", work / "fonts")
    (work / "assets").mkdir(exist_ok=True)
    shutil.copy(cov, work / "assets" / cov.name)
    shutil.copy(KIT / "assets/gsap.min.js", work / "gsap.min.js")
    shutil.copy(KIT / "assets/hyperframes.json", work / "hyperframes.json")
    (work / "img").mkdir(exist_ok=True)
    for i in img_idx:
        f = f"{spec['id']}-{i+1:02d}.png"
        shutil.copy(bdir / "img" / f, work / "img" / f)


def render(work, out):
    ff = need("ffmpeg"); npx = need("npx")
    envv = {**os.environ, "HYPERFRAMES_SKIP_SKILLS": "1"}
    if not IS_WIN and Path("/opt/homebrew/bin").exists():
        envv["PATH"] = "/opt/homebrew/bin:" + envv.get("PATH", "")
    raw = work / "raw.mp4"
    cmd = [npx, "--yes", f"hyperframes@{HF_VER}", "render", "--fps", str(FPS), "--quality", "delivery", "--workers", "4", "--output", str(raw)]
    if IS_WIN:
        cmd = ["cmd", "/c", *cmd]                         # npx 는 Windows 에서 .cmd 배치 파일이다
    for attempt in range(2):                              # 브라우저 워커 일시 장애가 잦다 — 1회 재시도
        r = subprocess.run(cmd, cwd=str(work), env=envv, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=2400)
        if r.returncode == 0 and raw.exists(): break
        print("render 실패:", (r.stderr or r.stdout)[-800:])
        if attempt: sys.exit(1)
    g = 0.0; tmp = work / "final.mp4"
    for _ in range(3):
        sh([ff, "-nostdin", "-y", "-v", "error", "-i", str(raw), "-i", str(work / "audio.wav"), "-map", "0:v", "-map", "1:a",
            "-c:v", "copy", "-af", f"volume={g}dB,alimiter=limit=0.84:level=disabled", "-c:a", "aac", "-b:a", "192k",
            "-shortest", "-movflags", "+faststart", str(tmp)])
        l = lufs_of(tmp)
        if abs(l - TARGET) < 0.2: break
        g += TARGET - l
    out.parent.mkdir(exist_ok=True)
    shutil.move(str(tmp), str(out))


# ───────────────────────── ④ QA ─────────────────────────
def qa(spec, plan, dur, out, work):
    ff = need("ffmpeg")
    res = {"file": str(out), "checks": {}, "ok": True}
    def chk(k, ok, det):
        res["checks"][k] = {"ok": bool(ok), "detail": det}; res["ok"] &= bool(ok)
    I = lufs_of(out)
    chk("lufs_total", I is not None and abs(I - TARGET) <= 0.5, f"{I} LUFS (목표 −14 ±0.5)")
    per = []
    for i, p in enumerate(plan):
        seg = work / f"_q{i}.wav"
        sh([ff, "-y", "-v", "error", "-ss", f"{p['t0']:.3f}", "-t", f"{p['d']:.3f}", "-i", str(out), "-vn", str(seg)])
        per.append(lufs_of(seg))
    med = float(np.median(per)); dev = [round(x - med, 2) for x in per]
    chk("lufs_per_line", all(abs(x) <= 1.0 for x in dev), {"median": round(med, 2), "dev": dev})
    r = subprocess.run([ff, "-nostats", "-i", str(out), "-af", "silencedetect=noise=-45dB:d=1.5", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
    sil = re.findall(r"silence_duration: ([\d.]+)", r)
    chk("silence", not sil, f"1.5초 넘는 무음 {len(sil)}곳")
    pr = json.loads(sh([need("ffprobe"), "-v", "error", "-show_entries", "format=duration:stream=width,height", "-of", "json", str(out)]).stdout)
    vd = float(pr["format"]["duration"]); vs = next(s for s in pr["streams"] if s.get("width"))
    chk("format", vs["width"] == 1080 and vs["height"] == 1920 and abs(vd - dur) < 0.3, f"{vs['width']}x{vs['height']} {vd:.2f}s")
    end_hold = dur - (plan[-1]["t0"] - 0.15)
    chk("end_card_3s", end_hold >= 3.0, f"{end_hold:.2f}s")
    bad = [ln["cap"] for ln in spec["lines"] if re.search(r"(하나|둘|셋|넷|열|스물|서른|마흔|쉰|백|천|이만|삼만|십)\s*(년|시간|개|쪽|명|가지)", ln["cap"])]
    chk("caption_numbers", not bad, bad or "자막 숫자는 아라비아 숫자")
    # 눈 검사용 프레임 시트 — 자막 조각 중간 몇 장 + 끝 화면 (글자 판독은 사람이 본다)
    times = [plan[0]["t0"] + 1.0, plan[1]["t0"] + 1.0, plan[len(plan) // 2]["t0"] + 1.0, plan[-2]["t0"] + 1.0, dur - 0.4]
    shots = []
    for k, t in enumerate(times):
        f = work / f"_f{k}.png"
        sh([ff, "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", str(out), "-frames:v", "1", "-vf", "scale=360:640", str(f)])
        shots.append(f)
    sheet = out.with_name(f"{spec['id']}.frames.jpg")
    args = [ff, "-y", "-v", "error"]
    for f in shots: args += ["-i", str(f)]
    sh(args + ["-filter_complex", f"hstack={len(shots)}", str(sheet)])
    res["frames"] = str(sheet)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec"); ap.add_argument("--no-render", action="store_true"); ap.add_argument("--no-qa", action="store_true")
    ap.add_argument("--regen-img", default="")
    a = ap.parse_args()
    sp = Path(a.spec).resolve()
    spec = json.loads(sp.read_text(encoding="utf-8")); bdir = sp.parent
    regen = {int(x) for x in a.regen_img.split(",") if x}
    work = bdir / f"work-{spec['id']}"; work.mkdir(exist_ok=True)
    need("ffmpeg"); need("ffprobe")
    print("① 이미지", flush=True); make_images(spec, bdir, regen)
    print("② 소리", flush=True); plan, dur = make_audio(spec, work)
    print(f"   길이 {dur}초", flush=True)
    make_html(spec, plan, dur, work, bdir)
    (work / "plan.json").write_text(json.dumps({"plan": plan, "dur": dur}), encoding="utf-8")
    if a.no_render:
        print("HTML:", work / "index.html"); return
    out = bdir / "out" / f"{spec['id']}.mp4"
    print("③ 렌더 (1~3분)", flush=True); render(work, out)
    if a.no_qa:
        print("완료:", out); return
    res = qa(spec, plan, dur, out, work)
    (bdir / "out" / f"{spec['id']}.qa.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    for k, v in res["checks"].items():
        print(("✓" if v["ok"] else "✗"), k, v["detail"])
    print("프레임 시트(눈으로 확인):", res["frames"])
    print("QA", "통과" if res["ok"] else "실패", "→", out)
    sys.exit(0 if res["ok"] else 3)


if __name__ == "__main__":
    main()
