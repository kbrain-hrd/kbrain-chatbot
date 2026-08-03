"""3단계 + 4단계를 실제 질문에 통과시켜 검수용 리포트를 만든다.

    uv run python -m backend.answer.pipeline [건수]

4단계 완료 조건은 "실제 질문 30건 이상으로 초안 품질 확인, **확신 있는 오답 0건**"이다.
오답 여부는 기계가 판정할 수 없으므로 초안을 리포트로 뽑아 사람이 검수한다.

`action` 이 `answer` 인 질문만 초안을 만든다. 되묻기·사람에게 넘김은 초안 대상이 아니다 —
그것이 설계다.
"""

from __future__ import annotations

import sys
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path

from backend.answer.classify import build_client, classify, load_catalog
from backend.search.index import build_hybrid_index
from backend.answer.draft import Draft, load_materials, make_draft
from backend.sheets.extract import Entry, read_entries
from backend.sheets.goldset import classify as rule_classify
from backend.sheets.goldset import sheet_grade_of

GRADE_WORD = {"green": "그린", "blue": "블루"}

# 규칙 기반으로 먼저 걸러 LLM 판정 대상을 좁힌다. 초안이 나올 수 있는 것은 문항·운영뿐인데,
# 앞선 실행에서 151건을 전부 판정하느라 판정 비용의 4/5를 초안 없이 태웠다.
DRAFTABLE_CATEGORIES = ("문항", "운영")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SHEETS_ROOT = PROJECT_ROOT / "raw" / "sheets"
OUT_PATH = PROJECT_ROOT / "eval" / "draft-review.md"

TARGET_DRAFTS = 30


@dataclass
class Row:
    question: str
    category: str
    anchor: str
    action: str
    reason: str
    draft: Draft | None
    error: str
    asked_grade: bool = False  # 되묻기 후 등급을 받아 재판정한 건인가


def collect_questions() -> list[Entry]:
    """초안이 나올 수 있는 질문만 추린다 — 규칙 기반 1차 스크리닝."""
    entries: list[Entry] = []
    for path in sorted(SHEETS_ROOT.rglob("*.xlsx")):
        for entry in read_entries(path):
            if rule_classify(entry).category in DRAFTABLE_CATEGORIES:
                entries.append(entry)
    return entries


def render(rows: list[Row], drafted: int) -> str:
    flagged = [r for r in rows if r.draft and r.draft.flags]
    low = [r for r in rows if r.draft and r.draft.confidence == "low"]
    after_ask = [r for r in rows if r.draft and r.asked_grade]

    out = [
        "# 초안 검수 리포트",
        "",
        "`uv run python -m backend.answer.pipeline` 산출물.",
        "실제 질문을 3단계(분류·문항 특정) → 4단계(초안 생성)로 통과시킨 결과다.",
        "",
        "**확인할 것: 확신 있는 오답이 있는가.** 근거 없이 단정한 곳, 자료에 없는 내용을 지어낸 곳,",
        "정답을 틀리게 제시한 곳을 찾으면 된다. 못 답한 것은 실패가 아니다.",
        "",
        "## 요약",
        "",
        f"- 처리한 질문: {len(rows)}건",
        f"- 초안 생성: **{drafted}건** (그중 등급 되묻기 후 답변 {len(after_ask)}건)",
        f"- 플래그 붙은 초안: {len(flagged)}건",
        f"- 신뢰도 low: {len(low)}건",
        "",
        "등급 되묻기 후 답변한 건은 실제 운영의 2턴 대화를 재현한 것이다 — 담당자가",
        "\"그린이신가요 블루이신가요\"를 묻고 답을 받은 뒤의 상태.",
        "",
        "---",
        "",
    ]

    index = 0
    for row in rows:
        if row.draft is None:
            continue
        index += 1
        draft = row.draft
        turn = " · 되묻기 후" if row.asked_grade else ""
        out += [
            f"## {index}. {row.category} · `{row.anchor or '-'}` · 신뢰도 {draft.confidence}{turn}",
            "",
            f"**질문**: {row.question}",
            "",
            f"**판정 근거**: {row.reason}",
            "",
        ]
        if draft.flags:
            out += [f"> ⚠️ 플래그: {' · '.join(draft.flags)}", ""]
        out += ["**초안**", "", draft.answer, "", "**근거**", ""]
        out += [f"- {item}" for item in draft.evidence]
        out += ["", "---", ""]

    skipped = [r for r in rows if r.draft is None]
    if skipped:
        out += [
            "## 초안을 만들지 않은 질문",
            "",
            "되묻기·사람에게 넘김으로 판정된 건이다. 초안이 없는 것이 정상 동작이다.",
            "",
            "| 분류 | 앵커 | 행동 | 질문 |",
            "|---|---|---|---|",
        ]
        for row in skipped:
            question = row.question.replace("|", "·")[:60]
            note = row.error or row.action
            out.append(f"| {row.category} | `{row.anchor or '-'}` | {note} | {question} |")

    return "\n".join(out) + "\n"


def main() -> None:
    target = int(sys.argv[1]) if len(sys.argv) > 1 else TARGET_DRAFTS

    client = build_client()
    catalog = load_catalog()
    ops_index = build_hybrid_index()
    entries = collect_questions()

    # 크레딧을 예고 없이 태우지 않도록 상한을 먼저 밝힌다.
    # 판정 12원 + 되묻기 재판정 12원 + 초안 99원 (2026-08-01 실측)
    max_cost = len(entries) * 24 + target * 99
    print(f"대상 {len(entries)}건 (규칙 스크리닝 후) / 초안 목표 {target}건")
    print(f"최대 예상 비용 약 {max_cost:,}원 — 초안 목표에 도달하면 조기 종료\n")

    rows: list[Row] = []
    drafted = 0

    for entry in entries:
        if drafted >= target:
            break

        try:
            judgment, _ = classify(client, entry.question, catalog, index=ops_index)
        except Exception as exc:
            rows.append(Row(entry.question, "-", "", "-", "", None, f"판정 실패: {exc}"))
            continue

        # 되묻기 이후를 재현한다. 실제 운영에서는 담당자가 "그린이신가요 블루이신가요"를
        # 물어 답을 받는데, 시트가 등급별로 나뉘어 있으므로 그 등급이 곧 응시자의 답이다.
        # 1턴에서 끊으면 되묻기가 전부 미답변으로 집계돼 기여도가 실제보다 낮게 나온다.
        asked_grade = False
        if judgment.action == "ask_grade":
            grade = GRADE_WORD.get(sheet_grade_of(entry.source), "")
            if grade:
                asked_grade = True
                try:
                    judgment, _ = classify(client, f"[{grade} 등급] {entry.question}", catalog, index=ops_index)
                except Exception as exc:
                    rows.append(
                        Row(entry.question, "-", "", "-", "", None, f"재판정 실패: {exc}", True)
                    )
                    continue

        row = Row(
            question=entry.question,
            category=judgment.category,
            anchor=judgment.anchor or "",
            action=judgment.action,
            reason=judgment.reason,
            draft=None,
            error="",
            asked_grade=asked_grade,
        )

        if judgment.action == "answer" and judgment.anchor:
            try:
                materials = load_materials(judgment.anchor)
                row.draft, _ = make_draft(client, entry.question, materials)
                drafted += 1
                print(f"  초안 {drafted}/{target}  {judgment.category} {judgment.anchor}")
            except SystemExit as exc:
                row.error = f"자료 로드 실패: {exc}"
            except Exception as exc:
                row.error = f"초안 실패: {type(exc).__name__}"

        rows.append(row)

    # 실행마다 새 파일로 남긴다. 앞선 실행에서 재실행이 이전 리포트를 덮어써 결과를 잃었다.
    stamp = datetime.now().strftime("%m%d-%H%M")
    out_path = OUT_PATH.with_name(f"draft-review-{stamp}.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render(rows, drafted), encoding="utf-8")
    print(f"\n질문 {len(rows)}건 처리 / 초안 {drafted}건 → {out_path}")


if __name__ == "__main__":
    main()
