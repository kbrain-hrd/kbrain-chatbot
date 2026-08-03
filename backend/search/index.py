"""운영 섹션 검색 — 카탈로그에 전량 싣는 대신 질문에 맞는 것만 고른다.

    uv run python -m backend.search.index "수료증 언제 나오나요"

**문항에는 쓰지 않는다.** 그린·블루는 세트명·주제·문제 유형이 같고 숫자만 달라
검색으로 가르면 엉뚱한 등급을 근거로 답하게 되고, 주력 동작인 되묻기("양쪽 다 있으니
등급을 물어야 한다")는 상위 N개 목록으로 표현할 수 없다. 문항 카탈로그는 계속 통째로 싣는다.

운영은 사정이 다르다 — 등급 개념이 없고, 되묻기가 없고, 질문↔질문 매칭이라 검색이 듣는다.
자료가 쌓여도 프롬프트가 커지지 않는 것이 도입 이유다.

임베딩을 쓰지 않는 것은 같은 이유의 연장이다. 색인 대상이 수백 개이고 질문↔질문
매칭이라 낱말이 겹친다. BM25 가 실제로 놓치는 것이 확인되면 그때 붙여도 늦지 않다.
색인은 **런타임 파생물**이다 — 원본은 `content/operations/*.md` 이고 파일로 떨구지 않는다.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from backend.search.catalog import OpsSection, collect_operations

# BM25 표준 계수. 문서 길이 편차가 큰 편이라(FAQ 한 줄 ~ 종합안내서 수천 자) b 는 기본값을 쓴다.
K1 = 1.2
B = 0.75

# 제목이 곧 질문인 FAQ 가 많다. 제목 낱말은 본문보다 무겁게 친다.
TITLE_WEIGHT = 3

HANGUL_RE = re.compile(r"[가-힣]+")
ALNUM_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    """한글은 2-gram, 영숫자는 낱말 단위.

    형태소 분석기를 두지 않는다. "수료증은"·"수료증을" 처럼 조사가 붙는 한국어에서
    2-gram 은 어간을 자동으로 나눠 주고, 의존성이 늘지 않는다.
    """
    lowered = text.lower()
    tokens = ALNUM_RE.findall(lowered)
    for chunk in HANGUL_RE.findall(lowered):
        if len(chunk) == 1:
            tokens.append(chunk)
        else:
            tokens += [chunk[i : i + 2] for i in range(len(chunk) - 1)]
    return tokens


@dataclass
class Hit:
    section: OpsSection
    score: float


class OpsIndex:
    """운영 섹션 BM25 색인."""

    def __init__(self, sections: list[OpsSection]) -> None:
        self.sections = sections
        self.docs = [Counter(tokenize(s.title) * TITLE_WEIGHT + tokenize(s.body)) for s in sections]
        self.lengths = [sum(d.values()) for d in self.docs]
        self.avg_length = sum(self.lengths) / len(self.lengths) if self.lengths else 0.0

        df: Counter[str] = Counter()
        for doc in self.docs:
            df.update(doc.keys())
        total = len(self.docs)
        self.idf = {
            term: math.log(1 + (total - count + 0.5) / (count + 0.5)) for term, count in df.items()
        }

    def search(self, query: str, top_n: int = 5) -> list[Hit]:
        terms = tokenize(query)
        hits = []
        for index, doc in enumerate(self.docs):
            score = 0.0
            for term in terms:
                freq = doc.get(term)
                if not freq:
                    continue
                norm = 1 - B + B * self.lengths[index] / self.avg_length
                score += self.idf[term] * freq * (K1 + 1) / (freq + K1 * norm)
            if score > 0:
                hits.append(Hit(self.sections[index], score))
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:top_n]


def build_index() -> OpsIndex:
    return OpsIndex(collect_operations())


def render_hits(hits: list[Hit]) -> str:
    """판정 프롬프트에 실을 표. 카탈로그의 운영 표와 같은 열을 쓴다."""
    out = [
        "## 운영 자료 (질문과 관련된 섹션만)",
        "",
        "운영 섹션 전체가 아니라 **이 질문에 관련된 것만** 골라 실었다.",
        "여기에 근거가 없으면 다른 운영 섹션에도 없다고 보고 `escalate` 하라.",
        "",
        "| 앵커 | 문서 | 섹션 | 핵심어 |",
        "|---|---|---|---|",
    ]
    for hit in hits:
        section = hit.section
        out.append(f"| `{section.anchor}` | {section.doc} | {section.title} | {section.keywords or '-'} |")
    return "\n".join(out)


def main() -> None:
    import sys

    if len(sys.argv) < 2:
        raise SystemExit('사용법: uv run python -m backend.search.index "질문 내용"')

    index = build_index()
    query = " ".join(sys.argv[1:])
    print(f"섹션 {len(index.sections)}개 색인\n")
    for rank, hit in enumerate(index.search(query, top_n=8), start=1):
        print(f"{rank}. {hit.score:6.2f}  {hit.section.anchor}")
        print(f"          {hit.section.title[:70]}")


if __name__ == "__main__":
    main()
