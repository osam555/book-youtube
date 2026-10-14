# book-youtube 설치 — Windows 10/11 (PowerShell)
# 실행: 이 폴더에서  powershell -ExecutionPolicy Bypass -File .\setup.ps1
# 끝나면 터미널을 닫고 새로 열어야 PATH 가 반영된다.
$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot

Write-Host "1/5 Node.js, ffmpeg, Python, Git (이미 있으면 건너뜀)" -ForegroundColor Cyan
foreach ($id in "OpenJS.NodeJS.LTS","Gyan.FFmpeg","Python.Python.3.12","Git.Git") {
  winget install -e --id $id --accept-source-agreements --accept-package-agreements | Out-Null
}
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

Write-Host "2/5 파이썬 가상환경(.venv) + 패키지" -ForegroundColor Cyan
if (-not (Test-Path .venv)) { py -3.12 -m venv .venv; if (-not $?) { python -m venv .venv } }
.\.venv\Scripts\python.exe -m pip install --upgrade pip | Out-Null
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

Write-Host "3/5 HyperFrames 미리 받기 (렌더용 크롬 포함, 몇 분)" -ForegroundColor Cyan
npx --yes hyperframes@0.8.143 --version

Write-Host "4/5 키 파일" -ForegroundColor Cyan
if (-not (Test-Path .env)) { Copy-Item .env.example .env; Write-Host "  .env 를 만들었다 → notepad .env 로 열어 키 두 개를 넣을 것" -ForegroundColor Yellow }

Write-Host "5/5 Claude Code 전역 스킬 등록 (어느 폴더에서든 「책 홍보 쇼츠」라고 하면 이 키트를 찾게)" -ForegroundColor Cyan
$dst = Join-Path $HOME ".claude\skills\book-youtube"
New-Item -ItemType Directory -Force -Path $dst | Out-Null
(Get-Content ".claude\skills\book-youtube\SKILL.md" -Raw -Encoding UTF8).Replace("{{KIT_DIR}}", $PSScriptRoot) | Set-Content (Join-Path $dst "SKILL.md") -Encoding UTF8

Write-Host "`n확인:" -ForegroundColor Cyan
node --version; (ffmpeg -version | Select-Object -First 1); .\.venv\Scripts\python.exe --version
Write-Host "`n설치 끝. 새 터미널에서 이 폴더로 와서 claude 를 열고 「대충영어 책 홍보 쇼츠 1부 만들어」라고 말하면 된다." -ForegroundColor Green
