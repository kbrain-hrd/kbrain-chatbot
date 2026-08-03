"""문항 문의 25건의 확정 레이블 — 3단계 정확도 측정의 정답.

    uv run python -m backend.sheets.labels

자동 판정(`goldset.py`)의 후보를 사람이 검토해 확정한 것이다.
질문 원문은 저장하지 않는다 — 본문에 이름·소속기관이 적힌 사례가 있어 원격에 올릴 수 없다.
대신 질문 텍스트의 SHA-256 앞 8자(`qid`)로 식별하고, 원문은 raw/sheets/ 에서 붙인다.

LABELS 는 `goldset.classify` 가 category='문항' 으로 판정한 질문들의 **순서**에 대응한다.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from backend.sheets.extract import read_entries
from backend.sheets.goldset import classify

SHEETS_ROOT = Path("raw/sheets")
OUT_PATH = Path("eval/goldset-labels.md")

# (category, anchor, action, flags, 요지)
#
# 2026-08-01 정정 — 첫 측정에서 레이블 자체의 오류가 드러나 10건을 고쳤다.
#   3과목 6건   ask_grade → escalate. 3과목은 단답 정답이 없어 카탈로그에 문항이 없다.
#               등급을 되물어도 답할 근거가 없으므로(루브릭 경로 미결정) 사람에게 넘기는 것이 맞다.
#               세트·과목 앵커는 유지한다 — 사람이 어느 문항인지 알아야 한다.
#   오류 2건    ask_grade → escalate. 공식정답오류·오류제기는 판정하지 않고 넘긴다
#               ([01](../../docs/01-design.md) 6장). 되묻기보다 이쪽이 우선한다.
#   운영 2건    escalate → answer. 둘 다 CBT가이드·FAQ 에 근거가 있어 답변 가능하다.
#
# 2026-08-03 정정 — 1건. "첨부 파일이 누락된 것 같으니 확인 부탁드립니다" 를 `문항` 으로
#   달아 뒀는데, 판정 규칙은 "자료를 보내달라는 요청은 세트·과목을 언급해도 `자료요청`"
#   이라고 명시한다. 규칙이 먼저 있었고 레이블이 그것을 어긴 것이라 레이블을 고쳤다.
#   실무적으로도 담당자가 파일을 확인해 올려 줄 건이지 문항 근거를 찾아 답할 건이 아니다.
#   (모델은 6/6 으로 규칙대로 판정하고 있었고 앵커 `?-S05-M01` 도 맞혔다.)
LABELS: list[tuple[str, str, str, str, str]] = [
    ("문항", "?-S02-M03", "escalate", "3과목", "2세트 3과목 json 제출 범위"),
    ("문항", "?-S03-M03", "escalate", "3과목·오류제기", "본문 필터링인데 정답은 본문/제목"),
    ("문항", "?-S03-M02", "ask_grade", "", "제출파일 1개인지 2개인지"),
    ("문항", "?-S01-M02", "ask_grade", "검수전", "총인구수 정렬 오류 (현재 자료는 수정됨)"),
    ("문항", "?-S05-M01-Q02", "escalate", "공식정답오류", "불일치 사실 수 5 vs 10"),
    ("문항", "G-S03-M02", "answer", "검수전", "컬럼명 불일치 (등급 명시됨)"),
    ("문항", "?-S02-M03", "escalate", "3과목", "UI/UX가 채점 대상인지"),
    ("문항", "?-S03-M03", "escalate", "3과목", "json 파일 포함 여부"),
    ("문항", "?-S03-M02", "ask_grade", "검수전", "컬럼·빈 셀 확인 요청"),
    ("문항", "?-S03-M03", "escalate", "3과목·오류제기", "해설 결과 수 10 vs 8"),
    ("문항", "?-S05-M02", "ask_grade", "", "빈 셀이 없어 보임"),
    ("운영", "", "escalate", "재분류", "배포 플랫폼(cdsa.site) 허용 여부 — 제출 규정"),
    ("문항", "?-S01-M02", "ask_grade", "검수전", "총인구수 정렬 오류 (재질문)"),
    ("문항", "?-S03-M02", "escalate", "오류제기", "답안지·해설지 표기 오류"),
    ("자료요청", "?-S05-M01", "escalate", "", "첨부 파일 누락 여부"),
    ("문항", "", "escalate", "3과목·세트불명", "구현 메모 의미 + rss 링크 감점"),
    ("운영", "", "answer", "재분류", "보안서약서 AI 사용 규정 해석"),
    ("운영", "", "answer", "재분류", "시험 구성·웹캠 요건"),
    ("문항", "?-S01-M01", "ask_grade", "", "본문 길이 라운드 처리 기준"),
    ("문항", "?-S01-M03", "escalate", "3과목", "외부 리소스 구성 방식"),
    ("문항", "?-S01-M02", "ask_grade", "", "부패위험 컬럼이 CSV에 없음"),
    ("문항", "", "escalate", "3과목·세트불명", "제출물.md 배점·제출 여부"),
    ("문항", "", "escalate", "3과목·세트불명", "구현 메모에 무엇을 쓰는지"),
    ("문항", "B-S01-M02", "answer", "", "4개 알고리즘 임의 선택 가능 여부"),
    ("문항", "?-S04-M02-Q03", "ask_grade", "자동판정오류", "1496행 vs 결측 20행"),
]


def qid_of(question: str) -> str:
    return hashlib.sha256(question.encode("utf-8")).hexdigest()[:8]


def collect_item_questions() -> list[tuple[str, str]]:
    """(qid, 시트 등급) — classify 가 '문항'으로 본 질문들, 판정 순서 그대로."""
    found = []
    for path in sorted(SHEETS_ROOT.rglob("*.xlsx")):
        for entry in read_entries(path):
            candidate = classify(entry)
            if candidate.category == "문항":
                found.append((qid_of(entry.question), candidate.sheet_grade))
    return found


def render(rows: list[tuple[str, str, tuple[str, str, str, str, str]]]) -> str:
    from collections import Counter

    categories = Counter(label[0] for _, _, label in rows)
    actions = Counter(label[2] for _, _, label in rows)
    excluded = sum(1 for _, _, label in rows if "검수전" in label[3])

    out = [
        "# 골드셋 확정 레이블 — 문항 문의 25건",
        "",
        "3단계(질문 분류 + 문항 특정) 정확도 측정의 정답이다.",
        "자동 판정(`backend/sheets/goldset.py`)의 후보를 사람이 검토해 확정했다.",
        "",
        "**질문 원문은 여기 넣지 않는다.** 본문에 이름·소속기관이 적힌 사례가 있어 원격에",
        "올릴 수 없기 때문이다. 질문 텍스트의 SHA-256 앞 8자(`qid`)로 식별하며, 원문은",
        "`raw/sheets/` 에 있고 `backend/sheets/labels.py` 가 다시 붙인다.",
        "",
        "## 레이블 뜻",
        "",
        "| 필드 | 값 |",
        "|---|---|",
        "| `category` | 문항 / 운영 / 자료요청 / 기술지원 / 교육내용 / 무관 / 분류불가 |",
        "| `anchor` | 특정된 앵커. 등급 불명이면 `?-S..-M..` 로 두고 되묻는다 |",
        "| `action` | `answer` 답변 가능 · `ask_grade` 등급 되묻기 · `escalate` 사람에게 |",
        "| `flag` | 측정·처리 시 주의할 점 |",
        "",
        "## 플래그",
        "",
        "- `3과목` — 단답 정답이 없는 산출물 평가. 앵커 카탈로그에 없고 루브릭 경로가 필요하다.",
        "- `오류제기` — 자료 오류를 지적하는 질문. **판정하지 말고** 대조 결과만 제시한다.",
        "- `검수전` — 질문 시점 자료가 현재와 다르다. **정확도 측정에서 제외**한다.",
        "- `공식정답오류` — 출제기관이 오류를 인정한 문항. 정답을 단정하면 안 된다.",
        "- `세트불명` — 3과목을 언급하나 세트를 밝히지 않아 특정 불가.",
        "- `재분류` / `자동판정오류` — 자동 판정을 사람이 바로잡은 건.",
        "",
        "## 레이블",
        "",
        "| qid | 시트 등급 | category | anchor | action | flag | 요지 |",
        "|---|---|---|---|---|---|---|",
    ]
    for qid, sheet_grade, (category, anchor, action, flag, note) in rows:
        out.append(
            f"| `{qid}` | {sheet_grade or '-'} | {category} | "
            f"{f'`{anchor}`' if anchor else '-'} | {action} | {flag or '-'} | {note} |"
        )

    out += [
        "",
        "## 집계",
        "",
        "| 항목 | 값 |",
        "|---|---|",
        f"| 총 | {len(rows)} |",
    ]
    for name, count in categories.most_common():
        out.append(f"| {name} | {count} |")
    for name, count in actions.most_common():
        out.append(f"| `{name}` | {count} |")
    out += [
        "",
        f"**측정에서 제외할 건:** `검수전` {excluded}건 — 질문 시점 자료가 현재와 달라 정확도를 왜곡한다.",
        f"→ 유효 측정 대상 **{len(rows) - excluded}건**.",
        "",
        "## 이 레이블이 말해주는 것",
        "",
        "1. **등급 되묻기가 압도적이다.** 등급을 밝힌 질문은 2건뿐이었다. 되묻기를 예외가 아니라",
        "   문항 경로의 기본 동작으로 설계해야 하는 근거다.",
        "2. **3과목 문의가 적지 않다.** 단답 정답이 없어 앵커 카탈로그에 없으므로, 루브릭 경로를",
        "   만들기 전까지는 전부 사람에게 넘어간다.",
        "3. **세트를 안 밝히는 3과목 질문이 있다.** 3과목은 세트가 달라도 요구사항 형식이 비슷해",
        "   학생이 세트를 생략하는 경향이 있다. 이 경우 세트도 되물어야 한다.",
    ]
    return "\n".join(out) + "\n"


def main() -> None:
    found = collect_item_questions()

    if len(found) != len(LABELS):
        raise SystemExit(
            f"문항 질문 {len(found)}건인데 확정 레이블은 {len(LABELS)}건입니다.\n"
            "자동 판정이 바뀌면 순서가 어긋납니다 — LABELS 를 다시 검토하세요."
        )

    rows = [(qid, grade, label) for (qid, grade), label in zip(found, LABELS)]
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(render(rows), encoding="utf-8")
    print(f"레이블 {len(rows)}건 → {OUT_PATH}")


if __name__ == "__main__":
    main()
