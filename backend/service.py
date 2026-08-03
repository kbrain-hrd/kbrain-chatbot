"""운영 실행 진입점 — 시트 폴링과 슬랙 리스너를 **한 프로세스**에서 함께 돌린다.

    uv run python -m backend.service

둘을 따로 띄우면 PC 를 켤 때마다 두 번 실행해야 하고, 한쪽만 죽어도 알아채기 어렵다.
자동 시작에 등록할 대상은 이 하나면 된다.

- **폴링**은 백그라운드 스레드에서 돈다. 시트에 올라온 질문을 감지해 초안을 만들고
  슬랙 카드를 보낸다.
- **슬랙 리스너**가 메인 스레드를 차지한다. [승인]/[수정]/[보류] 버튼을 받는다.

**폴링 스레드가 죽어도 프로세스는 살아 있다.** 리스너가 메인이라 그렇다. 그래서 스레드가
끝나면 그 사실을 로그에 남긴다 — 조용히 멈춰서 "카드가 안 오는데 왜인지 모르는" 상태가
가장 나쁘다.

시트와 슬랙 클라이언트는 각자 연다. gspread 연결을 스레드 간에 공유하지 않기 위해서다.
"""

from __future__ import annotations

import threading
import traceback
from datetime import datetime

from slack_bolt.adapter.socket_mode import SocketModeHandler

from backend.sheets import poll
from backend.slack.app import build_app, settings


def stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def poll_forever() -> None:
    """폴링 루프. 예기치 못한 예외로 스레드가 조용히 끝나지 않도록 감싼다."""
    try:
        poll.serve()
    except Exception:
        print(f"[{stamp()}] 폴링 스레드가 멈췄습니다 — 카드 발송이 중단됩니다.")
        traceback.print_exc()


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
