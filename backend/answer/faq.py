"""문의 이력을 주제별 FAQ 초안으로 정리한다.

    uv run python -m backend.answer.faq [표본수]

문의 1,323건은 그대로 색인할 수 없다. 본문이 개인 상황 서술이라("저희 기관은 3월에
신청했는데 담당자가 바뀌어서…") 주제가 같아도 텍스트가 전부 다르다 — 3-gram 으로 묶었을 때
3건 이상 반복되는 주제가 덮는 것이 4% 뿐이었다. 기계적 중복 제거로는 줄지 않는다.

**산출물은 `eval/` 에 둔다. 자동으로 `content/` 에 넣지 않는다.**
과거 답변은 근거가 아니라 *검수 대상*이라는 것이 이 프로젝트의 첫 번째 원칙이다
(실제로 과거 답변에 오류가 있어 설계가 두 번 폐기됐다). 사람이 확인한 뒤에야 편입한다.

같은 이유로 **문항 정답·해설 문의는 제외**한다. 그쪽 근거는 문제 원문이지 과거 답변이 아니다.

**현재 `eval/faq-draft.md` 는 이 스크립트가 만든 것이 아니다.** 100건 표본으로 방식을
검증했을 때(주제 43개, 535원, 전량 환산 7,076원) 품질은 쓸 만했으나, 실제 정리는
세션에서 직접 읽어 만들었다 — 비용이 들지 않고, 배치 간 중복 주제를 병합할 수 있어서다.
이 스크립트는 **자료가 크게 늘어 사람이 감당하기 어려워질 때를 위한 대안**으로 남겨 둔다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import anthropic
from pydantic import BaseModel, Field

from backend.answer.classify import build_client
from backend.ingest.operations import CURRENT_YEAR
from backend.search.catalog import collect_operations
from backend.sheets.inquiries import Inquiry, dedupe, find_source, read_inquiries

OUT_PATH = Path("eval/faq-draft.md")

# 주제 추출은 요약·분류 작업이라 판정 모델과 같은 등급으로 충분하다. 답변 초안 생성
# (Opus)과 달리 여기 산출물은 사람 검수를 반드시 거친다.
MODEL = "claude-sonnet-5"

# 한 번에 너무 많이 주면 주제를 뭉뚱그리고, 출력이 길어져 응답 한도에 걸린다.
# 25건으로 시작했다가 답변이 8K 토큰을 넘겨 JSON 이 잘렸다 — 배치 하나가 통째로 날아간다.
BATCH_SIZE = 12


class FaqItem(BaseModel):
    question: str = Field(description="응시자가 실제로 쓸 법한 표현의 대표 질문 한 문장.")
    answer: str = Field(description="운영진 답변들을 종합한 표준 답변. 개인 사정은 빼고 일반화한다.")
    sources: int = Field(description="이 주제로 묶인 문의 건수.")
    caution: str = Field(
        default="",
        description="시점 의존 정보·확인 필요 사항. 없으면 빈 문자열.",
    )


class FaqBatch(BaseModel):
    items: list[FaqItem]


SYSTEM_RULES = f"""\
너는 운영 문의 이력을 **FAQ 초안**으로 정리하는 역할이다.

## 무엇을 만드는가

같은 주제의 문의를 묶어 `대표 질문 + 표준 답변` 한 쌍으로 만든다.
문의 본문에는 개인 사정이 섞여 있다("저희 기관은 3월에 신청했는데 담당자가 바뀌어서…").
**개인 사정을 빼고 누구에게나 통하는 형태로 일반화**하라.

## 제외할 것

- **특정 문항의 정답·해설·채점에 관한 문의.** 그쪽 근거는 문제 원문이지 과거 답변이 아니다.
  "3세트 2번 답이 왜 5인가요" 같은 것은 만들지 마라.
- **한 사람의 개별 처리 요청.** "제 수강 내역을 취소해 주세요" 는 FAQ 가 아니다.
  다만 "수강 내역은 어떻게 취소하나요" 로 일반화되면 만들어도 된다.
- **내부 처리 지침.** "확인 후 담당자에게 넘길 것" 같은 것은 응시자에게 나갈 답변이 아니다.
- 답변이 "확인해 보겠습니다" 로 끝나 **실제 내용이 없는 것**.

## 답변을 쓸 때

- 운영진이 실제로 답한 내용만 쓴다. **없는 내용을 채워 넣지 마라.**
- 여러 답변이 서로 다르면 합치지 말고 `caution` 에 갈린다고 적어라.
- 문서 경로·절차는 원문 그대로 살려라 (`나의 강의실 > 학습현황 > …`).

## caution 에 반드시 적을 것

- **연도·기수·날짜가 답변의 근거인 경우.** 지금은 {CURRENT_YEAR}년이다.
  "2024년 정원 기준" 같은 답변은 그대로 쓰면 오답이 되므로 반드시 표시하라.
- 운영진 확인이 필요해 보이는 대목.
- 답변끼리 내용이 갈리는 경우.

## 이미 있는 FAQ

아래 제목과 **같은 주제면 만들지 마라.** 이미 자료에 들어가 있다.
"""


def existing_faq_titles() -> str:
    titles = [s.title for s in collect_operations() if s.doc == "문의FAQ"]
    return "\n".join(f"- {t}" for t in titles)


def render_batch(items: list[Inquiry]) -> str:
    lines = []
    for index, item in enumerate(items, start=1):
        lines += [f"### 문의 {index}", f"Q. {item.question}", f"A. {item.answer}", ""]
    return "\n".join(lines)


def extract(client: anthropic.Anthropic, items: list[Inquiry], seeds: str) -> tuple[FaqBatch, object]:
    response = client.messages.parse(
        model=MODEL,
        max_tokens=8000,
        system=[
            {"type": "text", "text": SYSTEM_RULES + seeds, "cache_control": {"type": "ephemeral"}},
        ],
        messages=[
            {
                "role": "user",
                "content": "다음 문의 이력을 FAQ 초안으로 정리하세요.\n\n" + render_batch(items),
            }
        ],
        output_format=FaqBatch,
    )
    return response.parsed_output, response.usage


def sample(items: list[Inquiry], size: int) -> list[Inquiry]:
    """균등 간격으로 고른다. 앞에서 자르면 시트 순서(시간순) 편향이 그대로 들어온다."""
    if size >= len(items):
        return items
    step = len(items) / size
    return [items[int(i * step)] for i in range(size)]


def render(results: list[FaqItem], total: int, cost: int) -> str:
    out = [
        "# 문의 이력 FAQ 초안 (검수 대기)",
        "",
        "`backend/answer/faq.py` 산출물. **이대로 쓰면 안 된다.**",
        "과거 답변은 근거가 아니라 검수 대상이다 — 실제로 오류가 확인되어 설계가 두 번 폐기됐다.",
        "",
        f"문의 {total}건에서 주제 {len(results)}개 추출. 약 {cost:,}원.",
        "",
        "**검수 방법**: `caution` 이 붙은 것부터 본다. 특히 연도가 근거인 답변은",
        "운영진 확인 없이 편입하면 오답이 된다. 확인이 끝난 항목만",
        "`content/operations/` 로 옮긴다.",
        "",
        "| # | 문의 수 | 대표 질문 | 확인 필요 |",
        "|---|---|---|---|",
    ]
    for index, item in enumerate(sorted(results, key=lambda i: -i.sources), start=1):
        flag = item.caution.replace("|", "·")[:60] if item.caution else "-"
        out.append(f"| {index} | {item.sources} | {item.question.replace('|', '·')} | {flag} |")

    out += ["", "---", ""]
    for index, item in enumerate(sorted(results, key=lambda i: -i.sources), start=1):
        out += [f"## {index}. {item.question}", "", f"문의 {item.sources}건", ""]
        if item.caution:
            out += [f"> **확인 필요** {item.caution}", ""]
        out += [item.answer, ""]
    return "\n".join(out)


def main() -> None:
    size = int(sys.argv[1]) if len(sys.argv) > 1 else 100

    source = find_source()
    if source is None:
        raise SystemExit("raw/ 에 문의내용 정리 xlsx 가 없습니다.")

    everything = dedupe(read_inquiries(source))
    items = sample(everything, size)
    seeds = existing_faq_titles()
    batches = [items[i : i + BATCH_SIZE] for i in range(0, len(items), BATCH_SIZE)]

    print(f"문의 {len(everything)}건 중 {len(items)}건 표본, {len(batches)}배치\n")

    client = build_client()
    results: list[FaqItem] = []
    cost = 0.0

    for index, batch in enumerate(batches, start=1):
        parsed, usage = extract(client, batch, seeds)
        results.extend(parsed.items)
        # Sonnet 5 인트로 기준 (입력 $2 / 출력 $10 per 1M), 환율 1,400원
        cost += (usage.input_tokens * 2 + usage.output_tokens * 10) / 1_000_000 * 1400
        print(f"  배치 {index}/{len(batches)}  주제 {len(parsed.items)}개  누적 {len(results)}개")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(render(results, len(items), round(cost)), encoding="utf-8")

    flagged = sum(1 for item in results if item.caution)
    print(f"\n주제 {len(results)}개 → {OUT_PATH}")
    print(f"확인 필요 표시 {flagged}개")
    print(f"비용 약 {cost:,.0f}원  (전량 {len(everything)}건 환산 약 "
          f"{cost / len(items) * len(everything):,.0f}원)")


if __name__ == "__main__":
    main()
