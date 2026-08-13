# 서비스를 일부러 멈춘다.
#
#     powershell -ExecutionPolicy Bypass -File stop.ps1
#
# 창이 없어진 뒤로는 "창을 닫아서 멈추는" 방법을 쓸 수 없다. 그리고 그냥 프로세스만
# 죽이면 5분 안에 감시가 다시 띄운다. 그래서 **감시를 먼저 멈추고** 프로세스를 끝낸다.
#
# 다시 켜려면:  powershell -ExecutionPolicy Bypass -File guard.ps1

$ErrorActionPreference = "Continue"
$taskName = "kbrain-chatbot-guard"

Write-Host ""
Write-Host "1. 감시 중지"
schtasks /change /tn $taskName /disable 2>&1 | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host "   $taskName 비활성화됨"
} else {
    Write-Host "   감시 작업이 등록돼 있지 않습니다 (건너뜀)"
}

Write-Host "2. 서비스 종료"
# run.bat 을 먼저 끊는다. 남겨 두면 파이썬이 죽는 순간 30초 뒤 되살린다.
$batch = Get-CimInstance Win32_Process -Filter "Name='cmd.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*run.bat*" }
foreach ($p in $batch) {
    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    Write-Host "   run.bat 종료 (PID $($p.ProcessId))"
}
$children = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -in @('uv.exe', 'python.exe') }
foreach ($p in $children) {
    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    Write-Host "   $($p.Name) 종료 (PID $($p.ProcessId))"
}

Start-Sleep -Seconds 2
$still = Get-NetTCPConnection -LocalPort 57321 -State Listen -ErrorAction SilentlyContinue
Write-Host ""
if ($still) {
    Write-Host "아직 살아 있습니다 (PID $($still.OwningProcess)). 작업 관리자에서 확인하세요."
} else {
    Write-Host "멈췄습니다."
    Write-Host ""
    Write-Host "다시 켜려면 :  powershell -ExecutionPolicy Bypass -File guard.ps1"
    Write-Host "감시를 되살리려면 :  schtasks /change /tn `"$taskName`" /enable"
}
Write-Host ""
