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
    open_sheets,
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


# 올린 카드의 위치. 나중에 **시트에서 처리된 건의 카드를 닫기 위해** 필요하다.
# 슬랙 봇 권한이 chat:write 뿐이라 채널을 되읽을 수 없으므로, 올릴 때 남겨 두지 않으면
# 그 카드를 다시 찾아갈 방법이 없다. 블록도 함께 둔다 — 닫을 때 원문을 그대로 살려
# 초안·근거가 카드에 남게 하기 위해서다.
CARD_PATH = PROJECT_ROOT / "logs" / "cards.json"


def load_cards() -> dict[str, dict]:
    try:
        return json.loads(CARD_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_cards(cards: dict[str, dict]) -> None:
    try:
        CARD_PATH.parent.mkdir(parents=True, exist_ok=True)
        CARD_PATH.write_text(json.dumps(cards, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        print(f"      카드 위치 기록 실패 ({exc})")


def card_key(sheet_id: str, row_number: int) -> str:
    return f"{sheet_id}:{row_number}"


def forget_card(sheet_id: str, row_number: int) -> None:
    """슬랙에서 처리된 카드는 목록에서 뺀다.

    빼지 않으면 폴링이 그 카드를 다시 닫으면서 `✅ 승인` 같은 처리 기록을 덮어쓴다.
    목록에 남아 있는 것은 **슬랙에서 손대지 않은 카드**뿐이어야 한다.
    """
    cards = load_cards()
    if cards.pop(card_key(sheet_id, row_number), None) is not None:
        save_cards(cards)


def close_sheet_handled(sheet: Sheet, row_number: int, status: str) -> bool:
    """시트에서 처리된 건의 카드를 닫는다. 카드는 지우지 않고 버튼만 뗀다."""
    config = settings()
    if not (config["bot"] and config["channel"]):
        return False
    cards = load_cards()
    key = card_key(sheet.worksheet.spreadsheet.id, row_number)
    entry = cards.get(key)
    if not entry:
        return False

    note = f"📄 시트에서 처리됨 → `{status}`"
    try:
        WebClient(token=config["bot"]).chat_update(
            channel=entry["channel"],
            ts=entry["ts"],
            blocks=card.result_blocks(entry["blocks"], note),
            text=note,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"      {row_number}행 카드 갱신 실패 ({type(exc).__name__}: {exc})")
        return False

    cards.pop(key, None)
    save_cards(cards)
    return True


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
        trail=values.get("trail", ""),
        sheet_id=sheet.worksheet.spreadsheet.id,
        sheet_title=sheet.worksheet.spreadsheet.title,
    )
    response = WebClient(token=config["bot"]).chat_postMessage(
        channel=config["channel"],
        blocks=blocks,
        # 알림 미리보기(목록·모바일 배너)에 뜨는 줄. 여기에도 회차를 넣어야
        # 카드를 열기 전에 어느 시트 건인지 알 수 있다.
        text=f"[{card.short_title(sheet.worksheet.spreadsheet.title)}] "
        f"[{values['category']}] 검수 요청 · {row_number}행",
    )

    cards = load_cards()
    cards[card_key(sheet.worksheet.spreadsheet.id, row_number)] = {
        "channel": response["channel"],
        "ts": response["ts"],
        "blocks": blocks,
    }
    save_cards(cards)
    return response["ts"]


def post_alert(text: str) -> bool:
    """운영 경고를 검수 채널에 올린다. 슬랙이 설정돼 있지 않으면 아무것도 하지 않는다.

    카드와 같은 채널로 보낸다. 담당자가 이미 보고 있는 곳이라 따로 확인할 데를
    늘리지 않는다.
    """
    config = settings()
    if not (config["bot"] and config["channel"]):
        return False
    WebClient(token=config["bot"]).chat_postMessage(channel=config["channel"], text=text)
    return True


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
    sheets = open_sheets()
    by_id = {s.worksheet.spreadsheet.id: s for s in sheets}

    def pick(sheet_id: str) -> tuple[Sheet | None, str]:
        """카드가 가리키는 시트를 고른다.

        **모르면 추측하지 않는다.** 시트가 여럿일 때 엉뚱한 회차에 답변을 적는 것이
        답변을 못 다는 것보다 나쁘다. 옛 카드에는 시트 정보가 없어서, 시트가 하나뿐일
        때만 그것으로 보고 여럿이면 사람에게 넘긴다.
        """
        if sheet_id:
            found = by_id.get(sheet_id)
            if found is None:
                return None, "카드가 가리키는 시트가 지금 감시 목록에 없습니다. .env 의 SHEET_URL 을 확인하세요."
            return found, ""
        if len(sheets) == 1:
            return sheets[0], ""
        return None, (
            "이 카드에는 시트 정보가 없습니다(감시 시트가 하나였을 때 만들어진 카드). "
            "감시 중인 시트가 여러 개라 어느 회차인지 확정할 수 없으니 시트에서 직접 처리하세요."
        )

    def resolve(body: str) -> tuple[int, dict[str, str] | None, str, Sheet | None]:
        """버튼 value 로 시트 행을 찾고, 카드가 가리키던 질문과 같은지 대조한다."""
        row_number, expected, sheet_id = card.parse_key(body)
        sheet, why = pick(sheet_id)
        if sheet is None:
            return row_number, None, why, None
        row = find_row(sheet, row_number)
        if row is None:
            return row_number, None, f"{row_number}행을 찾지 못했습니다. 시트가 변경된 것 같습니다.", None
        if not row["question"].startswith(expected[: card.KEY_LENGTH]):
            return row_number, None, (
                f"{row_number}행의 질문이 카드와 다릅니다. 행이 삽입·삭제된 것 같으니 "
                "시트에서 직접 확인하세요."
            ), None
        return row_number, row, "", sheet

    def close_card(
        client: WebClient,
        body: dict,
        note: str,
        sheet: Sheet | None = None,
        row_number: int | None = None,
    ) -> None:
        # 슬랙에서 처리한 카드는 추적 목록에서 뺀다. 남겨 두면 폴링이 그 카드를 다시
        # 닫으면서 "승인" 같은 처리 기록을 덮어쓴다.
        if sheet is not None and row_number is not None:
            forget_card(sheet.worksheet.spreadsheet.id, row_number)
        client.chat_update(
            channel=body["channel"]["id"],
            ts=body["message"]["ts"],
            blocks=card.result_blocks(body["message"]["blocks"], note),
            text=note,
        )

    @app.action("approve")
    def approve(ack, body, client, say) -> None:
        ack()
        row_number, row, error, sheet = resolve(body["actions"][0]["value"])
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
        close_card(client, body, f"✅ *{who}* 승인 → 시트 {row_number}행 `{STATUS_DONE}`",
                   sheet, row_number)

    @app.action("revise")
    def revise(ack, body, client, say) -> None:
        """초안이 틀렸을 때 — 슬랙에서 바로 고쳐 쓴다.

        `반려` 로 상태만 바꾸면 그 질문은 답변 없이 남는 막다른 길이 된다. 초안이 틀렸다는
        판단 다음에 필요한 것은 반려 표시가 아니라 **사람이 쓴 답**이다.
        """
        ack()
        row_number, row, error, sheet = resolve(body["actions"][0]["value"])
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
                sheet_id=sheet.worksheet.spreadsheet.id,
            ),
        )

    @app.view("revise_submit")
    def revise_submit(ack, body, view, client) -> None:
        ack()
        meta = json.loads(view["private_metadata"])
        row_number = int(meta["row"])
        final = view["state"]["values"]["answer"]["value"]["value"].strip()

        # 모달은 카드와 별개로 열리므로 시트를 다시 골라야 한다.
        sheet, why = pick(meta.get("s", ""))
        if sheet is None:
            client.chat_postMessage(channel=meta["channel"], text=f"⚠️ {why}")
            return

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
        forget_card(sheet.worksheet.spreadsheet.id, row_number)
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

    @app.action("rejudge")
    def rejudge(ack, body, client, say) -> None:
        """다시 판정한다 — 상태를 비워 다음 폴링이 그 행을 미처리로 보게 한다.

        리스너는 판정기·색인을 들고 있지 않으므로 여기서 직접 다시 돌리지 않는다.
        상태를 되돌리는 것으로 충분하고, **사람이 눌러서 일어난 일**이라 자동 상태
        변경 금지 원칙에도 어긋나지 않는다.
        """
        ack()
        row_number, row, error, sheet = resolve(body["actions"][0]["value"])
        if row is None:
            say(text=f"⚠️ {error}")
            return

        who = body["user"].get("name") or body["user"]["id"]
        sheet.write(row_number, {"status": ""})
        close_card(client, body, f"🔄 *{who}* 재판정 요청 → 다음 폴링에서 다시 처리됩니다",
                   sheet, row_number)

    @app.action("hold")
    def hold(ack, body, client, say) -> None:
        """지금 판단하기 어려운 건 — 시트에서 사람이 이어받는다."""
        ack()
        row_number, row, error, sheet = resolve(body["actions"][0]["value"])
        if row is None:
            say(text=f"⚠️ {error}")
            return

        who = body["user"].get("name") or body["user"]["id"]
        sheet.write(row_number, {"status": STATUS_HOLD})
        close_card(client, body, f"⏸️ *{who}* 보류 → 시트 {row_number}행 `{STATUS_HOLD}`",
                   sheet, row_number)

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
