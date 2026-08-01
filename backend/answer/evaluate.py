"""3단계 정확도 측정 — 확정 골드셋으로 분류·문항 특정을 채점한다.

    uv run python -m backend.answer.evaluate [모델ID]

완료 조건은 **문항 특정 정확도 ≥ 99%, 등급 판별 ≥ 99%** (docs/03-roadmap.md 3단계).

측정을 두 축으로 나눈다. 정답의 다수가 `ask_grade` 라서, 되묻기만 잘해도 총점은 높게 나오는데
그게 "문항을 잘 특정한다"는 뜻은 아니기 때문이다.

  세트·과목 특정  등급을 뺀 S..-M.. 부분이 맞는가
  등급 판별       등급이 명시된 건은 맞히고, 불명확한 건은 되묻는가

`검수전` 플래그가 붙은 건은 제외한다 — 질문 시점 자료가 현재와 달라 정확도를 왜곡한다.
"""

from __future__ import annotations

import hashlib
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from backend.answer.classify import DEFAULT_MODEL, build_client, classify, load_catalog
from backend.sheets.extract import read_entries
from backend.sheets.goldset import classify as rule_classify

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LABELS_PATH = PROJECT_ROOT / "eval" / "goldset-labels.md"
SHEETS_ROOT = PROJECT_ROOT / "raw" / "sheets"

LABEL_ROW_RE = re.compile(r"^\|\s*`([0-9a-f]{8})`\s*\|")


@dataclass
class GoldItem:
    qid: str
    question: str
    category: str
    anchor: str
    action: str
    flag: str
    note: str


def load_labels() -> dict[str, dict[str, str]]:
    """확정 레이블을 qid 로 색인해 읽는다."""
    labels: dict[str, dict[str, str]] = {}
    for line in LABELS_PATH.read_text(encoding="utf-8").splitlines():
        if not LABEL_ROW_RE.match(line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 7:
            continue
        labels[cells[0].strip("`")] = {
            "sheet_grade": cells[1],
            "category": cells[2],
            "anchor": cells[3].strip("`").strip(),
            "action": cells[4],
            "flag": cells[5],
            "note": cells[6],
        }
    return labels


def load_gold_items() -> list[GoldItem]:
    """레이블에 대응하는 질문 원문을 raw/sheets 에서 붙인다."""
    labels = load_labels()

    items: list[GoldItem] = []
    for path in sorted(SHEETS_ROOT.rglob("*.xlsx")):
        for entry in read_entries(path):
            if rule_classify(entry).category != "문항":
                continue
            qid = hashlib.sha256(entry.question.encode("utf-8")).hexdigest()[:8]
            label = labels.get(qid)
            if label is None:
                continue
            items.append(
                GoldItem(
                    qid=qid,
                    question=entry.question,
                    category=label["category"],
                    anchor="" if label["anchor"] == "-" else label["anchor"],
                    action=label["action"],
                    flag="" if label["flag"] == "-" else label["flag"],
                    note=label["note"],
                )
            )
    return items


def set_subject_of(anchor: str) -> str:
    """앵커에서 등급을 뺀 세트·과목 부분. 없으면 빈 문자열."""
    match = re.search(r"S(\d{2})-M(\d{2})", anchor or "")
    return f"S{match.group(1)}-M{match.group(2)}" if match else ""


def grade_of(anchor: str) -> str:
    """앵커의 등급 자리. G / B / ? / 빈 문자열."""
    match = re.match(r"([GB?])-S", anchor or "")
    return match.group(1) if match else ""


def main() -> None:
    model = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MODEL

    items = load_gold_items()
    scored = [i for i in items if "검수전" not in i.flag]
    print(f"골드셋 {len(items)}건 중 측정 대상 {len(scored)}건 (검수전 {len(items) - len(scored)}건 제외)")
    print(f"모델: {model}\n")

    client = build_client()
    catalog = load_catalog()

    category_hit = subject_hit = grade_hit = action_hit = 0
    subject_total = grade_total = 0
    cache_read = cache_write = output_tokens = 0
    misses: list[str] = []

    for index, item in enumerate(scored, start=1):
        judgment, response = classify(client, item.question, catalog, model=model)

        usage = response.usage
        cache_read += usage.cache_read_input_tokens or 0
        cache_write += usage.cache_creation_input_tokens or 0
        output_tokens += usage.output_tokens

        problems = []

        if judgment.category == item.category:
            category_hit += 1
        else:
            problems.append(f"분류 {judgment.category}≠{item.category}")

        # 세트·과목: 정답에 앵커가 있는 건만 채점
        expected_subject = set_subject_of(item.anchor)
        if expected_subject:
            subject_total += 1
            if set_subject_of(judgment.anchor or "") == expected_subject:
                subject_hit += 1
            else:
                problems.append(f"세트과목 {judgment.anchor or '-'}≠{item.anchor}")

        # 등급: 정답 앵커에 등급 자리가 있는 건만
        expected_grade = grade_of(item.anchor)
        if expected_grade:
            grade_total += 1
            if grade_of(judgment.anchor or "") == expected_grade:
                grade_hit += 1
            else:
                problems.append(f"등급 {grade_of(judgment.anchor or '') or '-'}≠{expected_grade}")

        if judgment.action == item.action:
            action_hit += 1
        else:
            problems.append(f"행동 {judgment.action}≠{item.action}")

        mark = "OK  " if not problems else "MISS"
        print(f"{mark} {index:>2}/{len(scored)} {item.qid}  {item.note[:34]}")
        if problems:
            misses.append(f"  {item.qid} {item.note[:40]}\n    " + " / ".join(problems))

    def pct(hit: int, total: int) -> str:
        return f"{hit}/{total} ({hit / total * 100:.1f}%)" if total else "해당 없음"

    print("\n" + "=" * 60)
    print(f"분류        {pct(category_hit, len(scored))}")
    print(f"세트·과목   {pct(subject_hit, subject_total)}   ← 완료 조건 99%")
    print(f"등급 판별   {pct(grade_hit, grade_total)}   ← 완료 조건 99%")
    print(f"행동        {pct(action_hit, len(scored))}")
    print(
        f"\n토큰  캐시읽기 {cache_read:,} / 캐시쓰기 {cache_write:,} / 출력 {output_tokens:,}"
    )

    if misses:
        print(f"\n틀린 건 {len(misses)}개:")
        for miss in misses:
            print(miss)


if __name__ == "__main__":
    main()
