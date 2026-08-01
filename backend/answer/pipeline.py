"""3단계 + 4단계를 실제 질문에 통과시켜 검수용 리포트를 만든다.

    uv run python -m backend.answer.pipeline [건수]

4단계 완료 조건은 "실제 질문 30건 이상으로 초안 품질 확인, **확신 있는 오답 0건**"이다.
오답 여부는 기계가 판정할 수 없으므로 초안을 리포트로 뽑아 사람이 검수한다.

`action` 이 `answer` 인 질문만 초안을 만든다. 되묻기·사람에게 넘김은 초안 대상이 아니다 —
그것이 설계다.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from backend.answer.classify import build_client, classify, load_catalog
from backend.answer.draft import Draft, load_materials, make_draft
from backend.sheets.extract import Entry, read_entries

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


def collect_questions() -> list[Entry]:
    entries: list[Entry] = []
    for path in sorted(SHEETS_ROOT.rglob("*.xlsx")):
        entries.extend(read_entries(path))
    return entries


def render(rows: list[Row], drafted: int) -> str:
    flagged = [r for r in rows if r.draft and r.draft.flags]
    low = [r for r in rows if r.draft and r.draft.confidence == "low"]

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
        f"- 초안 생성: **{drafted}건**",
        f"- 플래그 붙은 초안: {len(flagged)}건",
        f"- 신뢰도 low: {len(low)}건",
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
        out += [
            f"## {index}. {row.category} · `{row.anchor or '-'}` · 신뢰도 {draft.confidence}",
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
    entries = collect_questions()

    rows: list[Row] = []
    drafted = 0

    for entry in entries:
        if drafted >= target:
            break

        try:
            judgment, _ = classify(client, entry.question, catalog)
        except Exception as exc:
            rows.append(Row(entry.question, "-", "", "-", "", None, f"판정 실패: {exc}"))
            continue

        row = Row(
            question=entry.question,
            category=judgment.category,
            anchor=judgment.anchor or "",
            action=judgment.action,
            reason=judgment.reason,
            draft=None,
            error="",
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

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(render(rows, drafted), encoding="utf-8")
    print(f"\n질문 {len(rows)}건 처리 / 초안 {drafted}건 → {OUT_PATH}")


if __name__ == "__main__":
    main()
