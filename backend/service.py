"""운영 실행 진입점 — 시트 폴링과 슬랙 리스너를 **한 프로세스**에서 함께 돌린다.

    uv run python -m backend.service

둘을 따로 띄우면 PC 를 켤 때마다 두 번 실행해야 하고, 한쪽만 죽어도 알아채기 어렵다.
자동 시작에 등록할 대상은 이 하나면 된다.

- **폴링**은 백그라운드 스레드에서 돈다. 시트에 올라온 질문을 감지해 초안을 만들고
  슬랙 카드를 보낸다.
- **슬랙 리스너**가 메인 스레드를 차지한다. [승인]/[수정]/[보류] 버튼을 받는다.

**폴링이 멈추면 프로세스를 끝낸다.** 리스너가 메인이라 스레드만 죽으면 프로세스는 살아
있는데, 그러면 `run.bat` 의 자동 재시작도 걸리지 않는다. 슬랙 버튼은 여전히 동작하니
겉보기엔 멀쩡하고 카드만 안 온다 — 조용히 멈춰서 "왜인지 모르는" 상태가 가장 나쁘다.
그래서 일부러 프로세스를 종료해 재시작을 유도한다.

(일시적인 네트워크 오류로는 멈추지 않는다. 사이클 단위 재시도는 `poll.serve` 안에 있다.)

시트와 슬랙 클라이언트는 각자 연다. gspread 연결을 스레드 간에 공유하지 않기 위해서다.
"""

from __future__ import annotations

import os
import socket
import threading
import traceback
from datetime import datetime

from slack_bolt.adapter.socket_mode import SocketModeHandler

from backend.sheets import poll
from backend.slack.app import build_app, settings

# 중복 실행을 막는 자물쇠. 이 포트를 잡은 프로세스가 유일한 서비스다.
# 포트를 쓰는 이유는 **프로세스가 어떻게 죽든 OS 가 반드시 회수해 주기 때문**이다.
# 잠금 파일은 강제 종료·정전 뒤 남아서 다음 실행을 막아 버린다.
LOCK_PORT = 57321

_lock: socket.socket | None = None


def stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def acquire_lock() -> bool:
    """이 프로세스가 유일한 서비스인지 확보한다. 이미 떠 있으면 False.

    두 개가 동시에 돌면 같은 질문을 두 번 처리해 카드가 중복 발송되고, 옛 코드와 새 코드가
    같은 시트를 건드려 로그와 시트가 어긋난다 (2026-08-04 실제로 겪음).
    """
    global _lock
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        server.bind(("127.0.0.1", LOCK_PORT))
        server.listen(1)
    except OSError:
        server.close()
        return False
    _lock = server  # 프로세스가 사는 동안 잡아 둔다
    return True


def poll_forever() -> None:
    """폴링 루프. 어떤 이유로든 끝나면 프로세스를 종료해 재시작을 유도한다."""
    try:
        poll.serve()
    except Exception:
        traceback.print_exc()

    # 여기 닿았다는 것은 사이클 단위 재시도로도 회복하지 못했다는 뜻이다.
    # 프로세스를 살려 두면 run.bat 이 다시 띄우지 못해 카드 발송이 영구히 멈춘다.
    # 데몬 스레드에서 sys.exit 는 스레드만 끝내므로 os._exit 로 프로세스를 끝낸다.
    print(f"[{stamp()}] 폴링이 멈췄습니다 — 프로세스를 종료해 재시작을 유도합니다.")
    os._exit(1)


def main() -> None:
    config = settings()

    if not acquire_lock():
        print(
            f"[{stamp()}] 서비스가 이미 실행 중입니다 (포트 {LOCK_PORT} 사용 중) — 종료합니다.\n"
            "  중복 실행하면 같은 질문이 두 번 처리됩니다.\n"
            "  기존 것을 멈추려면 그 서비스 창을 닫으세요 (창 자체가 서비스입니다)."
        )
        # run.bat 은 이 코드를 보고 재시작 루프를 멈춘다. 30초마다 같은 메시지를
        # 로그에 쌓지 않기 위해서다.
        raise SystemExit(3)

    print(f"[{stamp()}] 셀프스터디 문의 대응 서비스 시작")
    print(f"  슬랙 채널: {config['channel']}")

    app = build_app()

    thread = threading.Thread(target=poll_forever, name="poll", daemon=True)
    thread.start()

    print(f"[{stamp()}] 슬랙 리스너 시작 — 중지는 Ctrl+C")
    try:
        SocketModeHandler(app, config["app"]).start()
    except KeyboardInterrupt:
        print(f"\n[{stamp()}] 중지했습니다.")


if __name__ == "__main__":
    main()
