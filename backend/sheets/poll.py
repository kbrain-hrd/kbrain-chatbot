"""6단계 — 시트 폴링 → 판정·초안 기록.

    uv run python -m backend.sheets.poll --once   # 1회 처리 후 종료
    uv run python -m backend.sheets.poll          # 주기 폴링 (기본 60초)

**상태가 비어 있는 행**만 처리하고, 처리한 행은 `검수대기` 로 바꾼다. 질문 등록 시 상태를
적는 관례가 없어 빈칸이 곧 미처리다 (backend/sheets/client.py `is_pending`).

**멱등하다** — 처리한 행은 상태가 채워져 다시 걸리지 않는다. 이 한 가지가 중복 처리와
비용 중복을 동시에 막는다.

`ask_grade` · `escalate` 는 **초안 없이 판정만 기록한다.** 초안이 없는 것이 정상 동작이고
(docs/01-design.md), 담당자가 시트에서 보고 처리한다. 특히 시트 경로는 비동기라
되묻기를 사람이 대신 해야 하므로 플래그로 명확히 표시한다.

일시적 실패(API·네트워크)는 **상태를 바꾸지 않는다** — 다음 폴링에서 자동 재시도된다.
자료 로드 실패처럼 재시도해도 같은 결과인 것은 사유를 적고 검수대기로 넘긴다.
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime

import anthropic

from backend.answer.classify import build_client, classify, load_catalog
from backend.answer.draft import load_materials, make_draft
from backend.search.index import HybridIndex, build_hybrid_index
from backend.sheets.client import (
    STATUS_REVIEW,
    Sheet,
    is_pending,
    open_sheet,
    question_of,
)
from backend.sheets.goldset import sheet_grade_of
from backend.slack.app import post_card

DEFAULT_INTERVAL = 60

GRADE_WORD = {"green": "그린", "blue": "블루"}

# 한 사이클에서 처리할 행 상한. 시트에 질문이 한꺼번에 쌓여 있어도 비용이 예고 없이
# 튀지 않게 한다. 남은 행은 다음 사이클에서 이어 처리된다.
MAX_PER_CYCLE = 20

# `escalate` 가 나왔을 때 다시 판정해 볼 횟수. 판정 1회가 약 12원이라 부담이 크지 않고,
# 되묻기·사람확인으로 새는 건을 줄이는 값이 그보다 크다.
ESCALATE_RETRIES = 2

ACTION_FLAG = {
    "ask_grade": "등급되묻기필요",
    "escalate": "사람확인필요",
    "ignore": "무관",
}


@dataclass
class Result:
    """시트 한 행에 쓸 값."""

    category: str
    draft: str
    evidence: str
    flags: str


def process(
    client: anthropic.Anthropic,
    catalog: str,
    question: str,
    grade: str,
    index: HybridIndex,
) -> Result:
    """질문 하나를 판정하고, 답변 가능한 경우에만 초안까지 만든다.

    `grade` 는 시트 이름에서 뽑은 등급이다. 시트가 `AI 챔피언 그린 4회차` 처럼 등급별로
    나뉘어 있으면 **그 시트에 올라온 질문의 등급은 이미 확정**이므로 되물을 이유가 없다.
    질문 텍스트만 보고 되묻는 것은 시트 경로에서 불필요한 왕복을 만든다
    (pipeline.py 도 같은 방식으로 되묻기 후 재판정을 재현한다).

    이것은 "등급을 추측하지 않는다"는 제약을 어기는 것이 아니다. 추측 금지는 질문 **본문**에서
    등급을 유추하지 말라는 것이고, 시트 출처는 유추가 아니라 확정된 사실이다.
    시트 이름에 등급이 없으면 `grade` 가 비고, 그때는 그대로 되묻는다.

    `index` 는 운영 섹션 검색기다. 카탈로그에 운영 섹션이 더 이상 들어 있지 않으므로
    (docs/04 2-7·2-8) 이것을 넘기지 않으면 운영 문의가 근거를 찾지 못한다.
    """
    judgment, _ = classify(client, question, catalog, index=index)

    # 등급만 몰라서 막힌 경우에 한해 시트 등급을 얹어 다시 판정한다.
    if judgment.action == "ask_grade" and grade:
        judgment, _ = classify(client, f"[{grade} 등급] {question}", catalog, index=index)

    # 근거가 있는데도 `escalate` 로 흔들리는 경우가 있어 다시 판정한다.
    # 같은 질문·같은 코드로 3회 돌려 1회가 escalate 로 나오는 것을 실측했다 (2026-08-03).
    # 운영 섹션이 카탈로그 전량 적재에서 검색 top-5 로 바뀌면서(docs/04 2-7) 근거가 경계에
    # 걸리는 질문이 생겼고, 그런 질문에서 판정이 흔들린다.
    #
    # **answer 가 나올 때만 바꿔 잡는다.** escalate 를 뒤집는 방향으로만 재시도하므로
    # "확신 있는 오답 0건" 기준을 낮추지 않는다. 끝까지 escalate 면 그대로 사람에게 간다.
    for _ in range(ESCALATE_RETRIES):
        if judgment.action != "escalate" or judgment.category not in ("운영", "문항"):
            break
        retry, _ = classify(client, question, catalog, index=index)
        if retry.action == "answer" and retry.anchor:
            judgment = retry
            break

    anchor = judgment.anchor or "-"
    flags = [ACTION_FLAG[judgment.action]] if judgment.action in ACTION_FLAG else []

    if judgment.action != "answer" or not judgment.anchor:
        return Result(
            category=judgment.category,
            draft="",
            evidence=f"{anchor} — {judgment.reason}",
            flags=" · ".join(flags),
        )

    try:
        materials = load_materials(judgment.anchor)
    except SystemExit as exc:
        # 재시도해도 같은 결과다. 사유를 남기고 사람에게 넘긴다.
        return Result(
            category=judgment.category,
            draft="",
            evidence=f"{anchor} — {judgment.reason}",
            flags=f"자료없음 · 사람확인필요 ({exc})",
        )

    draft, _ = make_draft(client, question, materials)

    evidence = [f"{anchor} — {judgment.reason}", *draft.evidence]
    if materials.disputed and "공식정답오류" not in draft.flags:
        draft.flags.append("공식정답오류")

    return Result(
        category=judgment.category,
        draft=draft.answer,
        evidence="\n".join(evidence),
        flags=" · ".join([*draft.flags, f"신뢰도 {draft.confidence}"]),
    )


def run_once(
    sheet: Sheet,
    client: anthropic.Anthropic,
    catalog: str,
    grade: str,
    index: HybridIndex,
) -> int:
    """미처리 행을 처리한다. 처리한 행 수를 돌려준다."""
    rows = sheet.read(("status", "question"))
    pending = [row for row in rows if is_pending(row)]

    if not pending:
        return 0

    targets = pending[:MAX_PER_CYCLE]
    if len(pending) > len(targets):
        print(f"  대기 {len(pending)}행 중 {len(targets)}행만 처리합니다 (사이클 상한)")

    done = 0
    for row in targets:
        row_number = int(row["_row"])
        question = question_of(row)

        try:
            result = process(client, catalog, question, grade, index)
        except Exception as exc:
            # 일시적 실패로 본다. 상태를 그대로 두면 다음 폴링에서 재시도된다.
            print(f"  {row_number}행 실패 ({type(exc).__name__}: {exc}) — 상태 유지, 다음 폴링에서 재시도")
            continue

        # 카드를 먼저 보내고, 성공한 뒤에 상태를 바꾼다. 초안은 시트가 아니라 카드에만
        # 남으므로(응시자에게 보이면 안 된다), 발송 전에 상태를 바꾸면 슬랙이 실패했을 때
        # 초안이 어디에도 남지 않고 재시도 대상에서도 빠진다.
        try:
            posted = post_card(
                sheet,
                row_number,
                {
                    "question": question,
                    "category": result.category,
                    "draft": result.draft,
                    "evidence": result.evidence,
                    "flags": result.flags,
                },
            )
        except Exception as exc:
            print(f"  {row_number}행 슬랙 발송 실패 ({type(exc).__name__}: {exc}) — 다음 폴링에서 재시도")
            continue

        sheet.write(row_number, {"status": STATUS_REVIEW})
        done += 1
        mark = "초안" if result.draft else "판정만"
        sent = "카드 발송" if posted else "슬랙 미설정"
        print(f"  {row_number}행 → {result.category} · {mark} · {result.flags or '플래그 없음'} · {sent}")

    return done


def serve(once: bool = False) -> None:
    """시트를 감시한다. `backend.service` 에서는 이 함수를 스레드로 돌린다."""
    interval = int(os.environ.get("POLL_INTERVAL", DEFAULT_INTERVAL))

    sheet = open_sheet()
    client = build_client()
    catalog = load_catalog()

    # 운영 섹션은 카탈로그가 아니라 검색으로 싣는다 (docs/04 2-7·2-8).
    # 색인 구축에 30초쯤 걸리므로 폴링 루프 밖에서 한 번만 만든다.
    print("운영 검색 색인 구축 중…")
    index = build_hybrid_index()

    title = sheet.worksheet.spreadsheet.title
    grade = GRADE_WORD.get(sheet_grade_of(title), "")

    print(f"시트: {title} [{sheet.worksheet.title}]")
    print(f"상태가 비어 있는 행을 처리해 '{STATUS_REVIEW}' 로 바꿉니다.")
    print(f"시트 등급: {grade or '불명 — 등급이 필요한 문항 문의는 되묻습니다'}")
    print("판정 약 12원 / 초안 약 99원 — 사이클당 최대 "
          f"{MAX_PER_CYCLE}행 (2026-08-01 실측)\n")

    if once:
        done = run_once(sheet, client, catalog, grade, index)
        print(f"\n처리 {done}행")
        return

    print(f"{interval}초 간격 폴링. 중지는 Ctrl+C.\n")
    try:
        while True:
            stamp = datetime.now().strftime("%H:%M:%S")
            done = run_once(sheet, client, catalog, grade, index)
            if done:
                print(f"[{stamp}] 처리 {done}행\n")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n중지했습니다.")


def main() -> None:
    serve(once="--once" in sys.argv)


if __name__ == "__main__":
    main()
