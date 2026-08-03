"""7단계 — 승인 카드 구성.

카드에는 초안 전문·근거·플래그·[승인][수정][보류]·시트 링크를 싣는다.

**카드가 초안의 저장소다.** 분류·초안·근거·플래그는 응시자가 봐서는 안 되므로 시트에 두지
않는다 (2026-08-03 결정). 응시자가 편집 권한을 가진 시트라 열을 숨겨도 펼쳐 볼 수 있기
때문이다. 따라서 승인·수정 시 초안은 **카드 블록에서 되읽는다**.

그래서 초안을 잘라 싣지 않고 **3000자 제한에 맞춰 여러 블록으로 나눠** 담는다. 잘라 실으면
그 잘린 내용이 그대로 최종답변이 된다.

**버튼 value 에 행 번호와 질문 앞부분을 함께 담는다.** 승인 시 시트의 그 행이 카드가 가리키던
질문과 같은지 대조하기 위해서다. 시트에 행이 삽입·삭제되면 행 번호만으로는 엉뚱한 행에
승인 결과가 들어간다.
"""

from __future__ import annotations

import html
import json

# 슬랙 section 블록의 텍스트 상한은 3000자다. 여유를 두고 나눈다.
MAX_SECTION = 2800
KEY_LENGTH = 40

# 초안 블록을 알아보기 위한 표시. 승인 시 이 블록들을 순서대로 이어 붙인다.
DRAFT_PREFIX = "draft_"


def clip(text: str, limit: int = MAX_SECTION) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n_… 이하 생략 ({len(text):,}자). 전문은 시트에서 보세요._"


def draft_blocks(draft: str) -> list[dict]:
    """초안을 3000자 제한에 맞춰 나눠 담는다. 잘라내지 않는다 — 이 내용이 최종답변이 된다."""
    chunks = [draft[at : at + MAX_SECTION] for at in range(0, len(draft), MAX_SECTION)] or [""]
    return [
        {
            "type": "section",
            "block_id": f"{DRAFT_PREFIX}{index}",
            "text": {"type": "mrkdwn", "text": chunk},
        }
        for index, chunk in enumerate(chunks)
    ]


def extract_draft(blocks: list[dict]) -> str:
    """카드 블록에서 초안 전문을 되읽는다.

    슬랙은 mrkdwn 텍스트의 `&`·`<`·`>` 를 엔티티로 바꿔 보관하므로 되돌린다.
    """
    parts = [
        (int(block["block_id"][len(DRAFT_PREFIX) :]), block["text"]["text"])
        for block in blocks
        if str(block.get("block_id", "")).startswith(DRAFT_PREFIX)
    ]
    return html.unescape("".join(text for _, text in sorted(parts)))


def row_key(row_number: int, question: str) -> str:
    """버튼에 실을 식별자. 행 번호와 질문 앞부분을 함께 담는다."""
    return json.dumps({"row": row_number, "q": question[:KEY_LENGTH]}, ensure_ascii=False)


def parse_key(value: str) -> tuple[int, str]:
    data = json.loads(value)
    return int(data["row"]), data["q"]


def build(
    *,
    row_number: int,
    question: str,
    category: str,
    draft: str,
    evidence: str,
    flags: str,
    sheet_url: str,
) -> list[dict]:
    """초안 카드 블록. 초안이 없으면 승인할 것이 없으므로 버튼을 달지 않는다."""
    key = row_key(row_number, question)

    blocks: list[dict] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"[{category}] 검수 요청 · {row_number}행"},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*질문*\n{clip(question, 1000)}"},
        },
    ]

    if flags:
        blocks.append(
            {"type": "context", "elements": [{"type": "mrkdwn", "text": f"⚠️ {flags}"}]}
        )

    if draft:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "*초안*"}})
        blocks.extend(draft_blocks(draft))
    else:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*초안 없음* — 근거가 부족하거나 사람이 판단해야 하는 문의입니다.",
                },
            }
        )

    if evidence:
        blocks.append(
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*근거*\n{clip(evidence, 1500)}"}}
        )

    actions: list[dict] = [
        {
            "type": "button",
            "text": {"type": "plain_text", "text": "시트에서 보기"},
            "url": sheet_url,
            "action_id": "open_sheet",
        }
    ]

    if draft:
        # 승인·수정 모두 시트를 다시 읽어 반영한다 — 카드의 초안은 발송 시점 스냅샷이라
        # 시트에서 수정한 내용이 날아갈 수 있다 (app.py `approve` 참조).
        actions = [
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "승인"},
                "style": "primary",
                "action_id": "approve",
                "value": key,
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "수정"},
                "action_id": "revise",
                "value": key,
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "보류"},
                "style": "danger",
                "action_id": "hold",
                "value": key,
            },
            *actions,
        ]

    blocks.append({"type": "actions", "elements": actions})
    return blocks


def result_blocks(blocks: list[dict], note: str) -> list[dict]:
    """처리 후 카드 — 버튼을 떼고 결과 한 줄을 붙인다. 같은 카드를 두 번 누르지 못하게 한다."""
    kept = [block for block in blocks if block.get("type") != "actions"]
    return [*kept, {"type": "context", "elements": [{"type": "mrkdwn", "text": note}]}]


# 슬랙 모달 입력창의 초기값 상한은 3000자다. 넘으면 잘린 채 열리므로 그 사실을 알린다.
MAX_INITIAL = 2900


def revise_view(
    *, row_number: int, question: str, draft: str, channel: str, ts: str, sheet_url: str
) -> dict:
    """초안을 채워 넣은 편집 모달. 여기서 고친 내용이 최종답변이 된다."""
    trimmed = draft[:MAX_INITIAL]
    blocks: list[dict] = [
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*질문*\n{clip(question, 1000)}"}},
        {
            "type": "input",
            "block_id": "answer",
            "label": {"type": "plain_text", "text": "최종답변"},
            "element": {
                "type": "plain_text_input",
                "action_id": "value",
                "multiline": True,
                "initial_value": trimmed,
            },
        },
    ]
    if len(draft) > MAX_INITIAL:
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"⚠️ 초안이 {len(draft):,}자라 앞 {MAX_INITIAL:,}자만 실렸습니다. "
                        f"전문을 고치려면 <{sheet_url}|시트에서> 작업하세요.",
                    }
                ],
            }
        )

    return {
        "type": "modal",
        "callback_id": "revise_submit",
        "title": {"type": "plain_text", "text": f"{row_number}행 답변 수정"},
        "submit": {"type": "plain_text", "text": "저장하고 승인"},
        "close": {"type": "plain_text", "text": "취소"},
        # 모달 제출 시에는 원본 메시지 정보가 오지 않으므로 여기에 실어 보낸다.
        "private_metadata": json.dumps(
            {"row": row_number, "q": question[:KEY_LENGTH], "channel": channel, "ts": ts},
            ensure_ascii=False,
        ),
        "blocks": blocks,
    }


def revised_blocks(*, row_number: int, question: str, answer: str, who: str, sheet_url: str) -> list[dict]:
    """수정 승인 후 카드. 원본 블록을 받아올 수 없어 새로 구성한다 (초안·근거는 시트에 남는다)."""
    return [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"수정 승인 · {row_number}행"},
        },
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*질문*\n{clip(question, 1000)}"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*최종답변*\n{clip(answer)}"}},
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "시트에서 보기"},
                    "url": sheet_url,
                    "action_id": "open_sheet",
                }
            ],
        },
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"✏️ *{who}* 수정 후 승인 → 시트 {row_number}행"}],
        },
    ]
