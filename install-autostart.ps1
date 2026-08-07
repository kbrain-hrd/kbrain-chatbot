# 셀프스터디 문의 대응 서비스를 로그온 시 자동 실행하도록 등록한다.
#
#     powershell -ExecutionPolicy Bypass -File install-autostart.ps1
#
# **시작 프로그램 폴더**에 실행 파일을 넣는 방식이다. 작업 스케줄러(schtasks)를 먼저
# 시도했으나 환경에 따라 `Access is denied` 로 막힌다(2026-08-04 실측). 시작 폴더는
# 현재 사용자 소유라 권한 문제가 없고, run.bat 이 이미 죽으면 다시 뜨는 루프를 갖고
# 있어 스케줄러의 재시작 정책도 필요 없다.
#
# 해제하려면 아래 파일을 지우면 된다:
#   %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\kbrain-chatbot.bat

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$runBat = Join-Path $scriptDir "run.bat"

if (-not (Test-Path $runBat)) {
    Write-Error "run.bat 을 찾지 못했습니다: $runBat"
}

$startup = [Environment]::GetFolderPath("Startup")
$launcher = Join-Path $startup "kbrain-chatbot.bat"

# 창을 최소화해서 띄운다. 완전히 숨기지 않는 이유는 **돌고 있다는 것이 보이는 편이
# 안전하기 때문**이다 — 조용히 멈춰 있는 것을 알아채지 못하는 게 가장 나쁘다.
$body = @"
@echo off
start "kbrain-chatbot" /min "$runBat"
"@

# **OEM 코드페이지로 쓴다.** cmd 는 로그온 시 배치 파일을 시스템 기본 코드페이지(한글
# Windows 는 949)로 읽는다. UTF-8 로 저장하면 경로의 한글(`C:\Users\케이브레인\…`)이
# 깨져 run.bat 을 찾지 못하고, 창도 안 뜨고 로그도 안 남아 **조용히 실패한다**
# (2026-08-07 실측: 등록은 성공했는데 로그온해도 아무 일도 일어나지 않음).
# 경로가 전부 영문이면 두 인코딩의 바이트가 같아 드러나지 않는 종류의 버그다.
# run.bat 헤더의 "keep this file ASCII-only" 와 같은 함정 — 그쪽은 본문에서 한글을
# 걷어내 해결했지만, 여기는 경로에 한글이 박혀 있어 인코딩을 맞추는 수밖에 없다.
$oemCp = [int](Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Control\Nls\CodePage").OEMCP
[System.IO.File]::WriteAllText($launcher, $body, [System.Text.Encoding]::GetEncoding($oemCp))

Write-Host ""
Write-Host "등록 완료"
Write-Host "  실행 파일 : $runBat"
Write-Host "  등록 위치 : $launcher"
Write-Host "  시점      : 로그온할 때마다 (최소화된 창으로)"
Write-Host "  로그      : $(Join-Path $scriptDir 'logs\service.log')"
Write-Host ""
Write-Host "지금 바로 시작하려면 :  start `"`" /min `"$runBat`""
Write-Host "중지하려면           :  작업 관리자에서 python.exe 종료 또는 창 닫기"
Write-Host "등록을 해제하려면     :  del `"$launcher`""
