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
import threading
import traceback
from datetime import datetime

from slack_bolt.adapter.socket_mode import SocketModeHandler

from backend.sheets import poll
from backend.slack.app import build_app, settings


def stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


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
