"""4단계 — 특정된 문항의 자료를 로드해 답변 초안을 만든다.

    uv run python -m backend.answer.draft "G-S01-M02" "질문 내용"

3단계가 어느 문항인지 정하고, 여기서 그 문항의 **문제지·해설·확정 답안지**를 로드해
초안을 쓴다. 로드 시점에 출처가 확정되므로 근거를 정확히 인용할 수 있다.

**매 질의마다 블라인드 풀이를 다시 하지 않는다.** 답안지 20개는 이미 실측으로 확정돼
있고(`verified: true`), 블라인드 풀이는 자료를 검증하는 배치 작업(1.5단계)이지
실시간 응답 경로가 아니다. 실시간에 다시 푸는 것은 느리고, 확정본보다 신뢰도가 낮다.

주력 질문이 "AI로 풀었는데 왜 틀렸나요"이므로, 초안의 핵심은 정답 숫자가 아니라
**갈린 지점**이다 — 해설의 "흔한 오답"과 문제지의 처리 규칙이 그 근거다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import anthropic
from pydantic import BaseModel, Field

from backend.answer.classify import PROJECT_ROOT, build_client

CONTENT_ROOT = PROJECT_ROOT / "content" / "selfstudy"
OPERATIONS_ROOT = PROJECT_ROOT / "content" / "operations"

# 2차 생성은 확신 있는 오답 0건이 걸린 지점이라 최상위 모델을 쓴다.
DRAFT_MODEL = "claude-opus-5"

ANCHOR_RE = re.compile(r"^([GB])-S(\d{2})-M(\d{2})(?:-Q(\d{2}))?$")
OPS_HEADING_RE = re.compile(r"^## \[(OPS-[^\]]+)\]\s*(.+)$")


class Draft(BaseModel):
    """답변 초안과 그 근거."""

    answer: str = Field(description="응시자에게 보낼 답변 초안. 존댓말, 군더더기 없이.")
    evidence: list[str] = Field(description="근거 인용. 어느 파일의 어느 대목인지 밝힌다.")
    flags: list[Literal["해설불일치", "근거부족", "공식정답오류", "판정보류"]] = Field(
        default_factory=list,
        description="검수자가 확인해야 할 사항. 없으면 빈 배열.",
    )
    confidence: Literal["high", "medium", "low"] = Field(
        description="자료에 답이 명확하면 high, 해석이 필요하면 medium, 근거가 부족하면 low.",
    )


@dataclass
class Materials:
    anchor: str
    problems: str
    solutions: str
    answers: str
    operations: str
    disputed: bool


def find_unit_dir(anchor: str) -> Path:
    """앵커의 등급·세트·과목으로 자료 디렉터리를 찾는다."""
    match = ANCHOR_RE.match(anchor)
    if not match:
        raise SystemExit(f"앵커 형식이 아닙니다: {anchor} (예: G-S01-M02 또는 G-S01-M02-Q03)")

    grade = {"G": "green", "B": "blue"}[match.group(1)]
    set_no, subject_no = int(match.group(2)), int(match.group(3))

    root = CONTENT_ROOT / grade
    for path in sorted(root.glob(f"s{set_no:02d}-*/m{subject_no:02d}")):
        if path.is_dir():
            return path
    raise SystemExit(f"자료를 찾지 못했습니다: {anchor} → {root}/s{set_no:02d}-*/m{subject_no:02d}")


def load_ops_section(anchor: str) -> str:
    """운영 자료에서 해당 섹션 본문만 잘라 온다.

    섹션 하나가 2만 자를 넘는 문서가 있어(셀프학습가이드) 파일을 통째로 싣지 않는다.
    """
    for path in sorted(OPERATIONS_ROOT.glob("*.md")):
        lines = path.read_text(encoding="utf-8").splitlines()
        starts = [(i, m) for i, line in enumerate(lines) if (m := OPS_HEADING_RE.match(line))]
        for order, (index, match) in enumerate(starts):
            if match.group(1) != anchor:
                continue
            end = starts[order + 1][0] if order + 1 < len(starts) else len(lines)
            return "\n".join(lines[index:end]).strip()
    raise SystemExit(f"운영 섹션을 찾지 못했습니다: {anchor}")


def load_materials(anchor: str) -> Materials:
    if anchor.startswith("OPS-"):
        return Materials(
            anchor=anchor,
            problems="",
            solutions="",
            answers="",
            operations=load_ops_section(anchor),
            disputed=False,
        )

    directory = find_unit_dir(anchor)

    def read(name: str) -> str:
        path = directory / f"{name}.md"
        return path.read_text(encoding="utf-8") if path.is_file() else ""

    answers = read("answers")
    return Materials(
        anchor=anchor,
        problems=read("problems"),
        solutions=read("solutions"),
        answers=answers,
        operations="",
        disputed="official_answer_disputed: true" in answers,
    )


SYSTEM_RULES = """\
너는 AI 챔피언 인증평가 문의에 대한 **답변 초안**을 쓴다. 초안은 사람이 검수한 뒤 나간다.

## 근거 원칙

- **문제 원문이 유일한 고정점이다.** 해설과 답안지는 검수 대상이기도 하다
- 주어진 자료에 없는 내용은 쓰지 마라. 일반 지식으로 메우지 마라
- 근거가 부족하면 억지로 답하지 말고 `근거부족` 플래그와 `confidence: low` 로 넘겨라
- **못 답하는 것은 괜찮지만, 틀린 답을 확신 있게 제시하는 것은 안 된다**

## 응시자가 실제로 묻는 것

응시자는 AI로 문제를 풀고 온다(문제지에 "AI 챗봇 자유 활용"이 명시돼 있다).
그래서 "정답이 뭐예요"보다 **"내 답이 왜 틀렸나요"** 가 많다.

정답 숫자만 알려주지 말고 **어디서 갈렸는지**를 짚어라. 해설의 "흔한 오답" 표와
문제지의 처리 규칙(결측치 처리·반올림·경계 조건 `>` vs `>=`)이 그 근거다.

## 답안지에 적힌 채점 정책이 문제지보다 우선한다

문제지가 "정확히 일치"라고 해도 답안지에 "±3 허용" 같은 채점 기준이 있으면 답안지를 따른다.
그런 경우 그 사실을 답변에 밝혀라.

## 플래그

| 플래그 | 언제 |
|---|---|
| `해설불일치` | 해설과 답안지가 서로 다른 값을 가리킨다 |
| `근거부족` | 자료에 답이 없다 |
| `공식정답오류` | 자료에 출제기관이 오류를 인정했다고 표시돼 있다 |
| `판정보류` | 응시자가 자료 오류를 제기했고 판단이 갈린다 |

`공식정답오류` 가 표시된 문항이면 **정답을 단정하지 마라.** 경위를 안내하고
수정본이 나오기 전임을 밝힌 뒤 검수자에게 넘겨라.

## 문체

- 존댓말. 군더더기 없이 요점부터
- 근거는 `evidence` 에 따로 담는다. 답변 본문에 파일 경로를 늘어놓지 마라
- 응시자가 틀린 이유를 짚을 때는 비난조가 되지 않게 한다
"""


def make_draft(
    client: anthropic.Anthropic,
    question: str,
    materials: Materials,
    model: str = DRAFT_MODEL,
) -> tuple[Draft, anthropic.types.Message]:
    context = "\n\n".join(
        part
        for part in (
            f"# 문제지\n\n{materials.problems}" if materials.problems else "",
            f"# 해설\n\n{materials.solutions}" if materials.solutions else "",
            f"# 답안지 (확정본)\n\n{materials.answers}" if materials.answers else "",
            f"# 운영 자료\n\n{materials.operations}" if materials.operations else "",
        )
        if part
    )

    response = client.messages.parse(
        model=model,
        max_tokens=8000,
        system=[{"type": "text", "text": SYSTEM_RULES}],
        messages=[
            {
                "role": "user",
                "content": (
                    f"## 근거 자료 ({materials.anchor})\n\n{context}\n\n"
                    f"---\n\n## 응시자 문의\n\n{question}\n\n"
                    "위 자료만을 근거로 답변 초안을 작성하세요."
                ),
            }
        ],
        output_format=Draft,
    )
    return response.parsed_output, response


def main() -> None:
    import sys

    if len(sys.argv) < 3:
        raise SystemExit('사용법: uv run python -m backend.answer.draft "G-S01-M02" "질문 내용"')

    anchor, question = sys.argv[1], " ".join(sys.argv[2:])
    materials = load_materials(anchor)

    if materials.disputed:
        print("⚠️  이 문항은 공식 정답에 오류가 확인된 상태입니다.\n")

    client = build_client()
    draft, response = make_draft(client, question, materials)

    print(f"신뢰도 : {draft.confidence}")
    print(f"플래그 : {', '.join(draft.flags) if draft.flags else '없음'}")
    print(f"\n--- 초안 ---\n{draft.answer}")
    print("\n--- 근거 ---")
    for item in draft.evidence:
        print(f"  · {item}")

    usage = response.usage
    print(f"\n사용량 : 입력 {usage.input_tokens} / 출력 {usage.output_tokens}")


if __name__ == "__main__":
    main()
