@echo off
chcp 65001 > nul
REM 셀프스터디 문의 대응 서비스 — 시트 폴링 + 슬랙 승인 리스너
REM
REM 작업 스케줄러에 등록해 로그온 시 자동 실행한다.
REM 화면이 보이지 않으므로 출력은 전부 logs\service.log 에 남긴다.
REM
REM 프로그램이 죽어도 30초 뒤 다시 띄운다. 네트워크가 끊기거나 슬랙 연결이
REM 끊어졌을 때 사람이 눈치채기 전까지 멈춰 있는 것이 가장 나쁘다.

cd /d "%~dp0"
if not exist logs mkdir logs

:loop
echo. >> logs\service.log
echo ==================== 시작 %date% %time% ==================== >> logs\service.log
uv run python -m backend.service >> logs\service.log 2>&1

REM 코드 3 = 서비스가 이미 실행 중. 다시 띄우면 같은 질문을 두 번 처리하므로 물러난다.
if %errorlevel%==3 (
    echo ---- 이미 실행 중이라 이 창은 종료합니다 ---- >> logs\service.log
    goto end
)

echo ---- 종료됨 (코드 %errorlevel%). 30초 뒤 다시 시작합니다 ---- >> logs\service.log
timeout /t 30 /nobreak > nul
goto loop

:end
