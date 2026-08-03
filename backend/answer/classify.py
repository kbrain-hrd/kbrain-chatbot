"""3단계 — 질문을 분류하고 문항을 특정한다.

카탈로그(문항 100개 + 운영 섹션 79개)를 프롬프트 **앞쪽에 고정**해 통째로 넣고,
LLM이 그 목록에서 고르게 한다. 벡터 검색을 쓰지 않는 이유는 docs/03-roadmap.md 참조.

카탈로그는 매 질의 동일하므로 프롬프트 캐싱 대상이다. 질문은 캐시 구간 뒤에 둔다 —
앞에 두면 매 요청 프리픽스가 달라져 캐시가 통째로 무효가 된다.

여기서는 **파일을 읽지 않는다.** 어느 문항인지 정하는 것까지가 이 단계의 일이고,
문서 로드와 초안 생성은 4단계다.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import anthropic
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from backend.search.catalog import OPS_SECTION_HEADING
from backend.search.index import OpsIndex, render_hits

# 검색이 정답을 1위로 올리지 못하는 경우가 있다("떨어지면 다시" ↔ "재응시" 처럼 낱말이
# 안 겹칠 때). 실측에서 정답은 3·6·6·9위였다. 재현율을 우선해 넉넉히 싣고 고르는 일은
# LLM 에 맡긴다 — 119개 중에서 고르는 것보다 12개 중에서 고르는 편이 쉽다.
OPS_TOP_N = 12

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = PROJECT_ROOT / "content" / "catalog.md"

# 1차 판정은 분류·특정·되묻기 판단까지다. 정확도 99% 기준이 걸려 있어 Sonnet 에서 시작하고,
# 골드셋 측정에서 더 가벼운 모델이 기준을 넘으면 그때 내린다.
DEFAULT_MODEL = "claude-sonnet-5"

CATEGORIES = ("문항", "운영", "자료요청", "기술지원", "교육내용", "무관", "분류불가")
ACTIONS = ("answer", "ask_grade", "escalate", "ignore")


class Judgment(BaseModel):
    """1차 판정 결과."""

    category: Literal["문항", "운영", "자료요청", "기술지원", "교육내용", "무관", "분류불가"]
    anchor: str | None = Field(
        default=None,
        description="특정된 앵커. 등급을 모르면 ?-S03-M02 처럼 등급 자리를 ? 로 둔다. 없으면 null.",
    )
    action: Literal["answer", "ask_grade", "escalate", "ignore"]
    reason: str = Field(description="판정 근거를 한 문장으로.")


SYSTEM_RULES = """\
너는 AI 챔피언 인증평가 문의를 분류하고 근거 문항·섹션을 특정하는 역할이다.
답변 초안을 쓰지 마라. 어느 근거를 봐야 하는지 정하는 것까지가 네 일이다.

## 분류 (category)

| 값 | 무엇인가 |
|---|---|
| 문항 | 예제문제의 문제·정답·해설·첨부에 대한 문의 |
| 운영 | 응시 환경·일정·신청·합격 기준·인증서 등. 운영 자료로 답할 수 있는 것 |
| 자료요청 | 파일을 보내달라는 요청. 다운로드 만료, 재발송, 자료 공유 |
| 기술지원 | 도구 설치·계정·로그인·실행 오류. 우리 근거 자료에 답이 없다 |
| 교육내용 | 개념 질문("RAG가 뭔가요"). 근거 없이 일반 지식으로 답하면 안 된다 |
| 무관 | 홍보·잡담·소속기관명만 적은 단편 |
| 분류불가 | 위 어디에도 넣기 어렵거나 내용이 너무 짧아 판단 불가 |

## 행동 (action)

- `answer` — 근거가 특정됐고 답변 가능
- `ask_grade` — 문항 문의인데 **등급(그린/블루)이 불명**하다. 되묻어야 한다
- `escalate` — 사람이 처리해야 한다 (자료요청·기술지원·교육내용·분류불가, 근거 특정 실패)
- `ignore` — 무관

## 문항과 운영을 가르는 기준

**질문이 특정 세트·과목·문항을 지목하면 `문항`이다.** 제출 파일 형식, 채점 기준, 첨부 데이터,
정답 근거 무엇을 묻든 마찬가지다 — "3세트 2과목의 제출파일" 은 그 문항의 요구사항이므로
`문항` 이지 `운영` 이 아니다.

`운영` 은 **특정 문항과 무관한 일반 규정**이다: 응시 환경, 일정, 신청 방법, 합격 기준,
인증서 발급, CBT 접속, 재응시. 세트·과목 언급이 없다.

헷갈리면 이렇게 판단하라 — 답을 찾으러 **어느 문서를 열어야 하는가**.
특정 세트의 문제지·해설·답안지를 열어야 하면 `문항`, 준비안내·CBT가이드·FAQ 를 열어야 하면 `운영`.

## 등급은 절대 추측하지 마라

그린과 블루는 **세트명·주제가 같고 정답만 다르다.** 등급을 잘못 고르면 엉뚱한 정답을
근거로 답하게 되고, 이것이 이 시스템에서 가장 위험한 실패다.

**질문 텍스트에 "그린" 또는 "블루"라는 낱말이 문자 그대로 있을 때만** 등급을 확정한다.
`[연습세트01·블루]` 처럼 인용된 문서 제목 안에 있어도 인정한다.

그 외에는 **전부 `?`** 다. 다음은 등급 근거가 **아니다** — 절대 등급을 유추하지 마라:

- 폴더 경로나 파일명 (`5세트_안전점검보고서일관성\\1과목_생성형AI(콘텐츠)\\첨부`)
- 과목 이름 표기 차이 (`생성형AI(콘텐츠)` 든 `콘텐츠` 든 등급 근거가 아니다)
- 문제 내용, 사용 도구, 난이도, 데이터 크기
- 카탈로그에 한쪽 등급만 비슷해 보이는 것

등급이 `?` 이면 `action` 은 `ask_grade` 다. 단, 아래 "되묻기보다 먼저인 것"에 해당하면
그쪽이 우선한다.

## 되묻기보다 먼저인 것

다음은 등급을 되물어도 답할 수 없으므로 **바로 `escalate`** 다. 앵커는 아는 데까지 적는다.

1. **3과목** — 단답 정답이 없는 산출물 평가라 카탈로그에 문항이 없다. 채점 루브릭 경로가
   아직 없으므로 사람이 처리한다. 앵커는 `?-S02-M03` 처럼 세트·과목까지 적어라
2. **공식 정답 오류** — 카탈로그에 ⚠️ 로 표시된 문항. 정답을 단정하면 안 된다
3. **오류 제기** — 응시자가 "답안지가 잘못됐다", "해설이 틀렸다"고 지적하는 문의.
   판정하지 말고 대조 결과만 사람에게 넘긴다

## 앵커 형식

- 문항: `G-S01-M02-Q03` (등급-세트-과목-문항). 문항 번호를 모르면 `G-S01-M02` 까지만
- 등급 불명: `?-S01-M02`
- 운영: 카탈로그의 `OPS-...` 앵커를 그대로
- 특정 실패: null

## 그 밖에

- 세트나 과목이 특정되지 않으면 `escalate`
- 자료를 보내달라는 요청은 세트·과목을 언급해도 `자료요청`이다
- 운영 문의는 카탈로그의 운영 섹션에 근거가 있으면 `answer` 다. 근거가 없을 때만 `escalate`

`reason` 은 **한 문장, 40자 이내**로 쓴다. 판단의 핵심만 적고 설명하지 마라.
"""


GRADE_REMINDER = """다시 확인한다 — 질문 텍스트에 "그린" 또는 "블루"라는 낱말이 그대로 있지 않으면
등급은 예외 없이 `?` 다. 카탈로그에 한쪽 등급만 있어 보이거나 내용이 비슷하다는 것은
등급 근거가 아니다. 등급이 `?` 인 문항 문의는 `ask_grade` 다."""


def load_catalog() -> str:
    if not CATALOG_PATH.is_file():
        raise SystemExit(f"카탈로그가 없습니다: {CATALOG_PATH}\nbackend.search.catalog 를 먼저 실행하세요.")
    return CATALOG_PATH.read_text(encoding="utf-8")


def build_client() -> anthropic.Anthropic:
    load_dotenv(PROJECT_ROOT / ".env")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY 가 없습니다. 프로젝트 루트의 .env 를 확인하세요.")
    return anthropic.Anthropic()


def split_catalog(catalog: str) -> tuple[str, str]:
    """카탈로그를 (문항, 운영) 으로 가른다."""
    at = catalog.find(OPS_SECTION_HEADING)
    if at == -1:
        return catalog, ""
    return catalog[:at].rstrip() + "\n", catalog[at:]


def classify(
    client: anthropic.Anthropic,
    question: str,
    catalog: str,
    model: str = DEFAULT_MODEL,
    index: OpsIndex | None = None,
) -> tuple[Judgment, anthropic.types.Message]:
    """질문 하나를 판정한다. (판정, 원응답) 을 돌려준다 — 사용량 확인용.

    `index` 를 주면 운영 섹션을 통째로 싣지 않고 **질문에 관련된 상위 N개만** 싣는다.
    문항 카탈로그는 그대로 둔다 — 검색으로 가르면 안 되는 이유는 backend/search/index.py 참조.
    """
    if index is not None:
        items, _ = split_catalog(catalog)
        catalog = items
        operations = render_hits(index.search(question, top_n=OPS_TOP_N))
    else:
        operations = ""

    response = client.messages.parse(
        model=model,
        max_tokens=2000,
        system=[
            {"type": "text", "text": SYSTEM_RULES},
            # 문항 카탈로그까지가 캐시 구간이다. 질문마다 달라지는 운영 검색 결과와
            # 질문 자체는 이 뒤에 온다 — 앞에 두면 매 요청 프리픽스가 달라져 캐시가 통째로 깨진다.
            {"type": "text", "text": catalog, "cache_control": {"type": "ephemeral"}},
            *([{"type": "text", "text": operations}] if operations else []),
            # 카탈로그가 길어질수록 맨 앞의 등급 규칙이 묻힌다. 운영 FAQ 34건을 넣었더니
            # 등급을 유추하는 사례가 다시 나타났다(9회 중 3회 → 편입 전 7회 중 0회).
            # 가장 위험한 규칙 하나만 카탈로그 뒤에 다시 붙인다. 캐시 구간 밖이라 비용은 무시할 수준.
            {"type": "text", "text": GRADE_REMINDER},
        ],
        messages=[{"role": "user", "content": f"다음 문의를 판정하세요.\n\n{question}"}],
        output_format=Judgment,
    )
    return response.parsed_output, response


def main() -> None:
    import sys

    if len(sys.argv) < 2:
        raise SystemExit('사용법: uv run python -m backend.answer.classify "질문 내용"')

    client = build_client()
    catalog = load_catalog()
    judgment, response = classify(client, " ".join(sys.argv[1:]), catalog)

    print(f"분류   : {judgment.category}")
    print(f"앵커   : {judgment.anchor or '-'}")
    print(f"행동   : {judgment.action}")
    print(f"근거   : {judgment.reason}")
    usage = response.usage
    print(
        f"\n사용량 : 입력 {usage.input_tokens} / 캐시쓰기 {usage.cache_creation_input_tokens} / "
        f"캐시읽기 {usage.cache_read_input_tokens} / 출력 {usage.output_tokens}"
    )


if __name__ == "__main__":
    main()
