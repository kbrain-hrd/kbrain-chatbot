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
[System.IO.File]::WriteAllText($launcher, $body, (New-Object System.Text.UTF8Encoding $false))

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
