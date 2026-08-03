"""7단계 — 슬랙 승인 흐름.

    uv run python -m backend.slack.app      # 버튼을 받는 리스너 (Socket Mode)

`.env` 에 세 값이 필요하다.

    SLACK_BOT_TOKEN=xoxb-...
    SLACK_APP_TOKEN=xapp-...
    SLACK_CHANNEL=#셀프스터디-검수

**Socket Mode 를 쓴다.** 버튼 클릭을 받으려면 원래 백엔드가 공개 URL 로 떠 있어야 하는데,
Socket Mode 는 슬랙 쪽으로 연결을 걸어 그 부담을 없앤다. 6단계에서 Apps Script 트리거 대신
폴링을 택한 것과 같은 이유다.

**승인은 카드가 아니라 시트를 다시 읽어 반영한다.** 카드에 실린 초안은 발송 시점 스냅샷이다.
"고칠 게 있으면 시트에서 수정 후 승인"이 설계이므로(docs/04 2-1), 카드 내용을 그대로 쓰면
수정본이 날아간다.

버튼은 셋이고, **모두 답변으로 끝나거나 사람이 이어받을 지점을 남긴다.**

| 버튼 | 동작 | 시트 상태 |
|---|---|---|
| 승인 | 초안 그대로 최종답변 | `답변완료` |
| 수정 | 모달에서 초안을 고쳐 최종답변 | `답변완료` |
| 보류 | 지금 판단하기 어려움 | `사람확인` |

`반려`(상태만 바꾸고 끝)를 두지 않는다. 초안이 틀렸다는 판단 다음에 필요한 것은 반려
표시가 아니라 사람이 쓴 답이기 때문이다. 승인과 수정을 나누면 **초안 무수정 승인률**도
따로 집계할 수 있다 (docs/02-data.md 3장).
"""

from __future__ import annotations

import json
import os
from datetime import datetime

from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk import WebClient

from backend.sheets.client import (
    PROJECT_ROOT,
    STATUS_DONE,
    STATUS_HOLD,
    Sheet,
    open_sheet,
)
from backend.slack import card

# 시트에는 검수용 컬럼이 없다 — 초안·근거·플래그는 카드에서 되읽는다.
ROW_FIELDS = ("status", "question", "answer")


def settings() -> dict[str, str]:
    load_dotenv(PROJECT_ROOT / ".env")
    return {
        "bot": os.environ.get("SLACK_BOT_TOKEN", ""),
        "app": os.environ.get("SLACK_APP_TOKEN", ""),
        "channel": os.environ.get("SLACK_CHANNEL", ""),
    }


def post_card(sheet: Sheet, row_number: int, values: dict[str, str]) -> str:
    """검수 카드를 채널에 올린다. 슬랙이 설정돼 있지 않으면 빈 문자열을 돌려준다."""
    config = settings()
    if not (config["bot"] and config["channel"]):
        return ""

    blocks = card.build(
        row_number=row_number,
        question=values["question"],
        category=values["category"],
        draft=values["draft"],
        evidence=values["evidence"],
        flags=values["flags"],
        sheet_url=sheet.row_url(row_number),
    )
    response = WebClient(token=config["bot"]).chat_postMessage(
        channel=config["channel"],
        blocks=blocks,
        text=f"[{values['category']}] 검수 요청 · {row_number}행",
    )
    return response["ts"]


def find_row(sheet: Sheet, row_number: int) -> dict[str, str] | None:
    for row in sheet.read(ROW_FIELDS):
        if int(row["_row"]) == row_number:
            return row
    return None


def build_app() -> App:
    config = settings()
    if not config["bot"]:
        raise SystemExit("SLACK_BOT_TOKEN 이 없습니다. .env 를 확인하세요.")
    if not config["app"]:
        raise SystemExit("SLACK_APP_TOKEN 이 없습니다. Socket Mode 토큰(xapp-...)이 필요합니다.")

    app = App(token=config["bot"])
    sheet = open_sheet()

    def resolve(body: str) -> tuple[int, dict[str, str] | None, str]:
        """버튼 value 로 시트 행을 찾고, 카드가 가리키던 질문과 같은지 대조한다."""
        row_number, expected = card.parse_key(body)
        row = find_row(sheet, row_number)
        if row is None:
            return row_number, None, f"{row_number}행을 찾지 못했습니다. 시트가 변경된 것 같습니다."
        if not row["question"].startswith(expected[: card.KEY_LENGTH]):
            return row_number, None, (
                f"{row_number}행의 질문이 카드와 다릅니다. 행이 삽입·삭제된 것 같으니 "
                "시트에서 직접 확인하세요."
            )
        return row_number, row, ""

    def close_card(client: WebClient, body: dict, note: str) -> None:
        client.chat_update(
            channel=body["channel"]["id"],
            ts=body["message"]["ts"],
            blocks=card.result_blocks(body["message"]["blocks"], note),
            text=note,
        )

    @app.action("approve")
    def approve(ack, body, client, say) -> None:
        ack()
        row_number, row, error = resolve(body["actions"][0]["value"])
        if row is None:
            say(text=f"⚠️ {error}")
            return

        # 초안은 카드에 담겨 있다. 시트에는 검수용 컬럼을 두지 않기 때문이다.
        final = card.extract_draft(body["message"]["blocks"]).strip()
        if not final:
            say(text=f"⚠️ {row_number}행 카드에서 초안을 읽지 못했습니다.")
            return

        who = body["user"].get("name") or body["user"]["id"]
        sheet.write(
            row_number,
            {
                "answer": final,
                "answered_at": datetime.now().strftime("%Y-%m-%d"),
                "status": STATUS_DONE,
            },
        )
        close_card(client, body, f"✅ *{who}* 승인 → 시트 {row_number}행 `{STATUS_DONE}`")

    @app.action("revise")
    def revise(ack, body, client, say) -> None:
        """초안이 틀렸을 때 — 슬랙에서 바로 고쳐 쓴다.

        `반려` 로 상태만 바꾸면 그 질문은 답변 없이 남는 막다른 길이 된다. 초안이 틀렸다는
        판단 다음에 필요한 것은 반려 표시가 아니라 **사람이 쓴 답**이다.
        """
        ack()
        row_number, row, error = resolve(body["actions"][0]["value"])
        if row is None:
            say(text=f"⚠️ {error}")
            return

        client.views_open(
            trigger_id=body["trigger_id"],
            view=card.revise_view(
                row_number=row_number,
                question=row["question"],
                draft=card.extract_draft(body["message"]["blocks"]),
                channel=body["channel"]["id"],
                ts=body["message"]["ts"],
                sheet_url=sheet.row_url(row_number),
            ),
        )

    @app.view("revise_submit")
    def revise_submit(ack, body, view, client) -> None:
        ack()
        meta = json.loads(view["private_metadata"])
        row_number = int(meta["row"])
        final = view["state"]["values"]["answer"]["value"]["value"].strip()

        row = find_row(sheet, row_number)
        if row is None or not row["question"].startswith(meta["q"][: card.KEY_LENGTH]):
            client.chat_postMessage(
                channel=meta["channel"],
                text=f"⚠️ {row_number}행이 카드와 달라 저장하지 못했습니다. 시트에서 확인하세요.",
            )
            return

        who = body["user"].get("name") or body["user"]["id"]
        sheet.write(
            row_number,
            {
                "answer": final,
                "answered_at": datetime.now().strftime("%Y-%m-%d"),
                "status": STATUS_DONE,
            },
        )
        client.chat_update(
            channel=meta["channel"],
            ts=meta["ts"],
            blocks=card.revised_blocks(
                row_number=row_number,
                question=row["question"],
                answer=final,
                who=who,
                sheet_url=sheet.row_url(row_number),
            ),
            text=f"수정 승인 · {row_number}행",
        )

    @app.action("hold")
    def hold(ack, body, client, say) -> None:
        """지금 판단하기 어려운 건 — 시트에서 사람이 이어받는다."""
        ack()
        row_number, row, error = resolve(body["actions"][0]["value"])
        if row is None:
            say(text=f"⚠️ {error}")
            return

        who = body["user"].get("name") or body["user"]["id"]
        sheet.write(row_number, {"status": STATUS_HOLD})
        close_card(client, body, f"⏸️ *{who}* 보류 → 시트 {row_number}행 `{STATUS_HOLD}`")

    @app.action("open_sheet")
    def open_sheet_link(ack) -> None:
        ack()  # 링크 버튼은 확인만 하면 된다

    return app


def main() -> None:
    config = settings()
    app = build_app()
    print(f"슬랙 리스너 시작 — 채널 {config['channel']}. 중지는 Ctrl+C.")
    SocketModeHandler(app, config["app"]).start()


if __name__ == "__main__":
    main()
