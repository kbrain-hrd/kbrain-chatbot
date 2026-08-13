# 서비스가 꺼져 있으면 창 없이 다시 띄운다. 작업 스케줄러가 5분마다 부른다.
#
# **왜 필요한가.** run.bat 의 재시작 루프는 파이썬이 죽었을 때만 작동한다. 창이 닫히면
# 그 루프까지 같이 사라져 되살릴 주체가 없다. 2026-08-07 에 실제로 그렇게 멈췄고
# 6일 동안 아무도 몰랐다 — 폴링 실패는 슬랙으로 알리지만 죽은 뒤에는 알릴 주체가 없다.
#
# **왜 창을 숨기나.** 콘솔 창은 사람이 만지면 멈춘다. Ctrl+C 는 (글자가 선택돼 있지 않으면)
# 복사가 아니라 중단이고, 창을 클릭만 해도 선택 모드로 들어가 출력이 막혀 프로그램이 선다.
# 서비스를 사람이 만질 수 있는 창에 얹어 두는 것 자체가 함정이다.
#
# 살아 있는지는 **자물쇠 포트**로 판단한다. backend/service.py 가 57321 을 잡고 있으므로
# 이 포트가 비어 있으면 서비스가 없는 것이다.

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$runBat = Join-Path $root "run.bat"
$logDir = Join-Path $root "logs"
$logPath = Join-Path $logDir "guard.log"

function Write-Log([string]$message) {
    if (-not (Test-Path $logDir)) {
        New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    }
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $message"
    [System.IO.File]::AppendAllText($logPath, "$line`r`n", [System.Text.UTF8Encoding]::new($true))
}

# 1. 자물쇠 포트가 잡혀 있으면 정상이다. 조용히 끝낸다.
$listening = Get-NetTCPConnection -LocalPort 57321 -State Listen -ErrorAction SilentlyContinue
if ($listening) { exit 0 }

# 2. 기동 중일 수 있다. 포트를 잡기 전 몇 초 동안은 run.bat 만 떠 있다.
#    이때 또 띄우면 두 인스턴스가 같은 로그 파일을 열려다 실패해 빈 루프를 돈다
#    (2026-08-07 실측). 프로세스를 한 번 더 확인한다.
$running = Get-CimInstance Win32_Process -Filter "Name='cmd.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*run.bat*" }
if ($running) { exit 0 }

# 3. 없다. 창 없이 띄운다.
Write-Log "서비스가 꺼져 있어 다시 띄웁니다."
Start-Process -FilePath $runBat -WorkingDirectory $root -WindowStyle Hidden

Start-Sleep -Seconds 20
$ok = Get-NetTCPConnection -LocalPort 57321 -State Listen -ErrorAction SilentlyContinue
if ($ok) {
    Write-Log "기동 확인 (PID $($ok.OwningProcess))"
} else {
    Write-Log "20초 안에 기동하지 못했습니다. logs\service.log 를 확인하세요."
}
