# 감시를 등록한다. 5분마다 guard.ps1 이 돌면서 서비스가 꺼져 있으면 다시 띄운다.
#
#     powershell -ExecutionPolicy Bypass -File install-guard.ps1
#
# 이걸 걸면 **시작 프로그램 폴더 방식은 필요 없어진다.** 감시가 5분마다 도니 로그온 후에도
# 알아서 뜨고, 시작 폴더 런처는 보이는 창을 띄워 오히려 사람이 만질 여지를 남긴다.
# 그래서 이 스크립트가 옛 런처를 지운다.
#
# 해제하려면:  schtasks /delete /tn "kbrain-chatbot-guard" /f

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$guard = Join-Path $root "guard.ps1"
$launcher = Join-Path $root "guard.vbs"
$taskName = "kbrain-chatbot-guard"

foreach ($f in @($guard, $launcher)) {
    if (-not (Test-Path $f)) { Write-Error "파일을 찾지 못했습니다: $f" }
}

# 작업 스케줄러에 등록. 현재 사용자로, 로그온해 있을 때만 돈다 —
# 서비스가 .env 와 구글 자격증명을 사용자 환경에서 읽기 때문이다.
#
# **powershell.exe 를 직접 걸지 않는다.** -WindowStyle Hidden 을 줘도 콘솔이 만들어졌다
# 잠시 뒤 숨겨져서, 5분마다 화면이 깜빡이며 작업을 가린다. wscript 는 콘솔이 없으므로
# 거기서 PowerShell 을 창 없이 띄우면 창이 아예 만들어지지 않는다.
$command = "wscript.exe //B //Nologo `"$launcher`""
schtasks /create /tn $taskName /tr $command /sc minute /mo 5 /f | Out-Null

# 옛 시작 프로그램 런처 제거 (있으면)
$startup = [Environment]::GetFolderPath("Startup")
$oldLauncher = Join-Path $startup "kbrain-chatbot.bat"
$removed = $false
if (Test-Path $oldLauncher) {
    Remove-Item $oldLauncher -Force
    $removed = $true
}

Write-Host ""
Write-Host "등록 완료"
Write-Host "  감시 작업   : $taskName  (5분마다)"
Write-Host "  하는 일     : 서비스가 꺼져 있으면 창 없이 다시 띄움"
Write-Host "  감시 기록   : $(Join-Path $root 'logs\guard.log')"
Write-Host "  서비스 기록 : $(Join-Path $root 'logs\service.log')"
if ($removed) {
    Write-Host "  옛 자동시작 : 제거함 ($oldLauncher)"
}
Write-Host ""
Write-Host "이제 서비스 창이 뜨지 않습니다. 돌고 있는지는 이렇게 확인합니다:"
Write-Host "  Get-NetTCPConnection -LocalPort 57321 -State Listen"
Write-Host ""
Write-Host "일부러 멈추려면  :  powershell -ExecutionPolicy Bypass -File stop.ps1"
Write-Host "감시를 해제하려면 :  schtasks /delete /tn `"$taskName`" /f"
Write-Host ""
