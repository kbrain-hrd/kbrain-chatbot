# 셀프스터디 문의 대응 서비스를 로그온 시 자동 실행하도록 등록한다.
#
#     powershell -ExecutionPolicy Bypass -File install-autostart.ps1
#
# 관리자 권한이 필요 없다 — 현재 사용자로 로그온할 때만 실행되는 작업이다.
# 해제하려면:  schtasks /delete /tn "kbrain-chatbot" /f

$ErrorActionPreference = "Stop"

$taskName = "kbrain-chatbot"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$runBat = Join-Path $scriptDir "run.bat"

if (-not (Test-Path $runBat)) {
    Write-Error "run.bat 을 찾지 못했습니다: $runBat"
}

# 이미 등록돼 있으면 지우고 다시 만든다 (경로가 바뀌었을 수 있다).
$existing = schtasks /query /tn $taskName 2>$null
if ($?) {
    schtasks /delete /tn $taskName /f | Out-Null
    Write-Host "기존 작업을 지웠습니다."
}

# /rl limited: 관리자 권한 없이 실행. 이 서비스는 관리자 권한이 필요 없다.
schtasks /create /tn $taskName /tr "`"$runBat`"" /sc onlogon /rl limited /f | Out-Null

Write-Host ""
Write-Host "등록 완료: $taskName"
Write-Host "  실행 파일 : $runBat"
Write-Host "  시점      : 로그온할 때마다"
Write-Host "  로그      : $(Join-Path $scriptDir 'logs\service.log')"
Write-Host ""
Write-Host "지금 바로 시작하려면:  schtasks /run /tn `"$taskName`""
Write-Host "중지하려면          :  schtasks /end /tn `"$taskName`""
Write-Host "등록을 해제하려면    :  schtasks /delete /tn `"$taskName`" /f"
