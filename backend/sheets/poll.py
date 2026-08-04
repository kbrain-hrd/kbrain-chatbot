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

import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

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
from backend.slack.app import post_alert, post_card

DEFAULT_INTERVAL = 60

GRADE_WORD = {"green": "그린", "blue": "블루"}

# 한 사이클에서 처리할 행 상한. 시트에 질문이 한꺼번에 쌓여 있어도 비용이 예고 없이
# 튀지 않게 한다. 남은 행은 다음 사이클에서 이어 처리된다.
MAX_PER_CYCLE = 20

# `escalate` 가 나왔을 때 다시 판정해 볼 횟수. 판정 1회가 약 12원이라 부담이 크지 않고,
# 되묻기·사람확인으로 새는 건을 줄이는 값이 그보다 크다.
ESCALATE_RETRIES = 2

# 이만큼 연속으로 실패하면 슬랙에 알린다. 한두 번은 흔한 일이라 알릴 값이 없고,
# 이 정도면 일시적 오류로 보기 어렵다. 기본 간격(60초)에서 약 5분에 해당한다.
ALERT_AFTER = 5

ACTION_FLAG = {
    "ask_grade": "등급되묻기필요",
    "escalate": "사람확인필요",
    "ignore": "무관",
}

# 근거가 없어 못 답한 것(정상)과 입력이 온전하지 않아 막힌 것(버그)을 가르는 표시.
MISROUTED_FLAG = "판정실패"

# 판정 결과 이력. 질문 원문은 담지 않는다(해시로 식별). git 제외 경로에 둔다.
SNAPSHOT_PATH = Path(__file__).resolve().parents[2] / "logs" / "judgments.json"


@dataclass
class Result:
    """시트 한 행에 쓸 값."""

    category: str
    draft: str
    evidence: str
    flags: str
    trail: str = ""  # 판정 이력 — 첫 판정과 재판정이 어떻게 갈렸는지
    misrouted: bool = False  # 입력이 온전하지 않아 막힌 건인가 (근거 부족과 구분)


@dataclass
class Ask:
    """시트 한 행에서 만든 판정 입력.

    **질문과 등급을 따로 들고 다니지 않는다.** 예전에는 `question` 과 `grade` 가 따로
    흘러서 호출부마다 등급을 얹는 것을 기억해야 했고, 실제로 한 곳에서 빠뜨려
    초안이 통째로 누락됐다 (2026-08-04). 행에서 입력을 만드는 지점을 여기 하나로 묶는다.
    """

    question: str  # 마스킹된 원문 — 기록·표시용
    prompt: str  # 판정에 실제로 넣는 문자열
    grade: str  # 시트에서 확정된 등급 (없으면 빈 문자열)

    @property
    def graded(self) -> bool:
        return bool(self.grade)


def with_grade(question: str, grade: str) -> str:
    """시트 등급을 질문에 얹는다.

    시트가 `AI 챔피언 그린 4회차` 처럼 등급별로 나뉘어 있으면 **그 시트에 올라온 질문의
    등급은 이미 확정**이다. 그런데도 원문으로 먼저 묻고 되묻기가 나오면 그때 등급을
    붙이는 방식이었는데, 그러면 세 가지가 나빠진다.

    1. 답을 아는 것을 모르는 척 물어보므로 API 호출이 두 배가 된다
    2. 첫 판정이 되묻기가 아닌 다른 이유로 흔들리면 등급을 얹을 기회를 놓친다
    3. 되묻기가 최종 결과로 남을 수 있다 — 시트가 등급을 아는데 응시자에게 되묻는 셈이다

    → **처음부터 얹는다.** 단, 질문이 스스로 등급을 밝혔으면 그것을 따른다.

    이것은 "등급을 추측하지 않는다"는 제약을 어기는 것이 아니다. 추측 금지는 질문 **본문**에서
    등급을 유추하지 말라는 것이고, 시트 출처는 유추가 아니라 확정된 사실이다.
    시트 이름에 등급이 없으면 `grade` 가 비고, 그때는 원문 그대로 물어 되묻게 한다.
    """
    if not grade or "그린" in question or "블루" in question:
        return question
    return f"[{grade} 등급] {question}"


def build_ask(row: dict[str, str], grade: str) -> Ask:
    """시트 행 → 판정 입력. **판정에 넣을 문자열은 반드시 이 함수를 거친다.**"""
    question = question_of(row)
    return Ask(question=question, prompt=with_grade(question, grade), grade=grade)


def process(
    client: anthropic.Anthropic,
    catalog: str,
    ask: Ask,
    index: HybridIndex,
) -> Result:
    """질문 하나를 판정하고, 답변 가능한 경우에만 초안까지 만든다.

    `index` 는 운영 섹션 검색기다. 카탈로그에 운영 섹션이 더 이상 들어 있지 않으므로
    (docs/04 2-7·2-8) 이것을 넘기지 않으면 운영 문의가 근거를 찾지 못한다.
    """
    asked = ask.prompt
    judgment, _ = classify(client, asked, catalog, index=index)
    trail = [f"1차 {judgment.action}"]

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
        retry, _ = classify(client, asked, catalog, index=index)
        trail.append(f"재판정 {retry.action}")
        if retry.action == "answer" and retry.anchor:
            judgment = retry
            break

    anchor = judgment.anchor or "-"

    # **`되묻기` 와 `판정실패` 를 가른다.** 시트가 등급을 아는데도 되묻기가 나왔다면
    # 응시자에게 물을 일이 아니라 **입력이 제대로 전달되지 않았다는 신호**다.
    # 예전에는 이것이 `사람확인필요` 에 섞여 들어가, 근거가 없어 못 답한 정상 건과
    # 화면상 구분되지 않았다 (2026-08-04). 섞이면 버그가 조용히 지나간다.
    misrouted = judgment.action == "ask_grade" and ask.graded
    if misrouted:
        flags = [MISROUTED_FLAG]
    else:
        flags = [ACTION_FLAG[judgment.action]] if judgment.action in ACTION_FLAG else []

    if judgment.action != "answer" or not judgment.anchor:
        return Result(
            category=judgment.category,
            draft="",
            evidence=f"{anchor} — {judgment.reason}",
            flags=" · ".join(flags),
            trail=" → ".join(trail),
            misrouted=misrouted,
        )

    try:
        materials = load_materials(judgment.anchor)
    except SystemExit as exc:
        # 앵커까지 잡고 자료를 못 찾은 것은 판정이 아니라 자료 쪽 문제다.
        return Result(
            category=judgment.category,
            draft="",
            evidence=f"{anchor} — {judgment.reason}",
            flags=f"{MISROUTED_FLAG} · 자료없음 ({exc})",
            trail=" → ".join(trail),
            misrouted=True,
        )

    draft, _ = make_draft(client, ask.question, materials)

    evidence = [f"{anchor} — {judgment.reason}", *draft.evidence]
    if materials.disputed and "공식정답오류" not in draft.flags:
        draft.flags.append("공식정답오류")

    return Result(
        category=judgment.category,
        draft=draft.answer,
        evidence="\n".join(evidence),
        flags=" · ".join([*draft.flags, f"신뢰도 {draft.confidence}"]),
        trail=" → ".join(trail),
    )


def snapshot_key(question: str) -> str:
    """질문을 식별하는 열쇠. **원문을 남기지 않는다** — 본문에 이름·소속이 적힌 사례가 있다."""
    return hashlib.sha256(question.encode("utf-8")).hexdigest()[:12]


def load_snapshots() -> dict[str, dict]:
    if not SNAPSHOT_PATH.is_file():
        return {}
    try:
        return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}  # 깨졌으면 버리고 새로 쌓는다. 회귀 감지는 보조 장치다


def check_regression(question: str, result: Result) -> str:
    """같은 질문이 예전보다 나쁘게 판정됐으면 그 사실을 돌려준다.

    초안이 나오던 질문이 어느 날 조용히 초안 없이 넘어가는 일이 실제로 있었다
    (2026-08-04). 그때는 로그를 파야만 알 수 있었다. 결과를 남겨두고 견주면
    같은 일이 반복될 때 바로 드러난다.
    """
    snapshots = load_snapshots()
    key = snapshot_key(question)
    before = snapshots.get(key)

    note = ""
    if before and before.get("drafted") and not result.draft:
        note = f"초안이 있던 질문인데 이번엔 초안 없음 (이전 앵커 {before.get('anchor', '-')})"

    snapshots[key] = {
        "drafted": bool(result.draft),
        "anchor": result.evidence.split(" —")[0] if result.evidence else "-",
        "flags": result.flags,
    }
    try:
        SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT_PATH.write_text(
            json.dumps(snapshots, ensure_ascii=False, indent=1), encoding="utf-8"
        )
    except OSError as exc:
        print(f"      판정 이력 저장 실패 ({exc}) — 회귀 감지만 건너뜁니다")
    return note


def alert(text: str) -> bool:
    """슬랙에 운영 경고를 올린다. **알림이 실패해도 폴링을 멈추지 않는다.**

    네트워크가 끊긴 상황이면 슬랙 호출도 함께 실패할 수 있는데, 그것 때문에 폴링까지
    죽으면 알리려던 문제를 더 키운다.
    """
    try:
        return post_alert(text)
    except Exception as exc:
        print(f"      슬랙 알림 실패 ({type(exc).__name__}: {exc})")
        return False


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
        ask = build_ask(row, grade)
        question = ask.question

        try:
            result = process(client, catalog, ask, index)
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
                    "trail": result.trail,
                },
            )
        except Exception as exc:
            print(f"  {row_number}행 슬랙 발송 실패 ({type(exc).__name__}: {exc}) — 다음 폴링에서 재시도")
            continue

        # **상태는 언제나 `검수대기` 다.** 초안이 없다고 시스템이 `답변대기` 로 단정하지
        # 않는다 — 처리 결과를 정하는 것은 사람이고, 사람이 누르지 않았는데 상태가 바뀌면
        # 검수한 적 없는 건이 처리된 것처럼 보인다. 초안이 없는 건도 카드에 [직접 작성]과
        # [보류] 가 달리므로 슬랙에서 그대로 처리할 수 있다.
        sheet.write(row_number, {"status": STATUS_REVIEW})
        done += 1
        mark = "초안" if result.draft else "초안없음"
        sent = "카드 발송" if posted else "슬랙 미설정"
        print(
            f"  {row_number}행 → {result.category} · {mark} · "
            f"{result.flags or '플래그 없음'} · {STATUS_REVIEW} · {sent}"
            + (f"  [{result.trail}]" if result.trail else "")
        )

        # 입력이 온전하지 않아 막힌 건은 **버그 신호**다. 근거가 없어 못 답한 정상 건과
        # 달리 사람이 코드를 봐야 하므로, 로그에만 남기지 않고 바로 알린다.
        if result.misrouted:
            print(f"      ⚠️ 판정실패 — 입력이 제대로 전달되지 않았을 수 있습니다")
            alert(
                f"⚠️ *{row_number}행 판정실패* — 근거를 찾기 전 단계에서 막혔습니다.\n"
                f"```{result.flags}\n판정 이력: {result.trail or '-'}```\n"
                f"시트 등급: {grade or '(불명)'} · 근거가 없어 못 답한 것과는 다른 상황입니다."
            )

        # 같은 질문이 예전보다 나쁘게 판정됐는지 견준다.
        regression = check_regression(question, result)
        if regression:
            print(f"      ⚠️ 회귀: {regression}")
            alert(f"⚠️ *{row_number}행 판정 강등* — {regression}")

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
    failures = 0
    alerted = False
    try:
        while True:
            stamp = datetime.now().strftime("%H:%M:%S")

            # **한 사이클이 실패해도 루프를 끝내지 않는다.** 구글 시트 연결이 끊기는 일은
            # 실제로 일어나고(ConnectionResetError 실측, 2026-08-03), 그걸로 폴링이
            # 영구히 멈추면 프로세스는 살아 있어서 재시작도 걸리지 않는다.
            # 카드가 안 오는데 이유를 모르는 상태가 가장 나쁘다.
            try:
                done = run_once(sheet, client, catalog, grade, index)
            except Exception as exc:
                failures += 1
                print(
                    f"[{stamp}] 폴링 실패 {failures}회째 "
                    f"({type(exc).__name__}: {exc}) — {interval}초 뒤 다시 시도합니다"
                )
                # 로그는 사람이 열어봐야 보인다. 계속 실패하면 담당자가 보고 있는
                # 검수 채널로 알린다. 복구될 때까지 한 번만 보낸다 — 30초마다
                # 같은 경고가 쌓이면 채널이 묻힌다.
                if failures >= ALERT_AFTER and not alerted:
                    alerted = alert(
                        f"⚠️ *시트 폴링이 {failures}회 연속 실패했습니다* — 질문 감지가 멈춰 있습니다.\n"
                        f"```{type(exc).__name__}: {exc}```\n"
                        "인터넷 연결 · 시트 공유 권한 · 서비스 계정 키를 확인하세요."
                    )
                time.sleep(interval)
                continue

            if failures:
                print(f"[{stamp}] 폴링 복구됨 (연속 실패 {failures}회 뒤)")
                if alerted:
                    alert(f"✅ 시트 폴링이 복구됐습니다 (연속 실패 {failures}회 뒤).")
                failures = 0
                alerted = False
            if done:
                print(f"[{stamp}] 처리 {done}행\n")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n중지했습니다.")


def main() -> None:
    serve(once="--once" in sys.argv)


if __name__ == "__main__":
    main()
