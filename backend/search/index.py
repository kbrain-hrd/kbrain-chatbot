"""운영 섹션 검색 — 카탈로그에 전량 싣는 대신 질문에 맞는 것만 고른다.

    uv run python -m backend.search.index "수료증 언제 나오나요"

**문항에는 쓰지 않는다.** 그린·블루는 세트명·주제·문제 유형이 같고 숫자만 달라
검색으로 가르면 엉뚱한 등급을 근거로 답하게 되고, 주력 동작인 되묻기("양쪽 다 있으니
등급을 물어야 한다")는 상위 N개 목록으로 표현할 수 없다. 문항 카탈로그는 계속 통째로 싣는다.

운영은 사정이 다르다 — 등급 개념이 없고, 되묻기가 없고, 질문↔질문 매칭이라 검색이 듣는다.
자료가 쌓여도 프롬프트가 커지지 않는 것이 도입 이유다.

여기는 낱말 검색(BM25)이고, 의미 검색은 `dense.py` 에 있다. 둘을 `HybridIndex` 가
순위로 융합한다 — 서로 못 하는 일이 달라서 한쪽만으로는 부족하다.
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


# 섹션 길이 편차가 크다 — 문의FAQ 는 중앙값 94자인데 셀프학습가이드 "실전처럼 연습하기"는
# 20,040자다. 긴 섹션을 통째로 한 단위로 다루면 임베딩에서 의미가 뭉개지고 BM25 에서도
# 길이 정규화에 눌린다. **색인에서만 잘게 나누고 앵커는 섹션 그대로 돌려준다** —
# 마크다운을 쪼개면 앵커가 바뀌어 골드셋 레이블과 문서 참조가 깨진다.
CHUNK_SIZE = 600
CHUNK_OVERLAP = 120

SENTENCE_END_RE = re.compile(r"(?<=[.!?다요])\s+")


def chunk_body(body: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """문단 → 문장 순으로 경계를 찾아 자른다. 경계가 없으면 그때만 강제로 끊는다."""
    if len(body) <= size:
        return [body] if body.strip() else []

    pieces: list[str] = []
    for paragraph in body.split("\n\n"):
        if len(paragraph) <= size:
            pieces.append(paragraph)
            continue
        sentence = ""
        for part in SENTENCE_END_RE.split(paragraph):
            if len(sentence) + len(part) > size and sentence:
                pieces.append(sentence)
                sentence = part
            else:
                sentence = f"{sentence} {part}".strip()
        if sentence:
            pieces.append(sentence)

    chunks: list[str] = []
    current = ""
    for piece in pieces:
        if len(current) + len(piece) > size and current:
            chunks.append(current)
            current = current[-overlap:] + "\n" + piece if overlap else piece
        else:
            current = f"{current}\n{piece}".strip()
    if current.strip():
        chunks.append(current)

    # 경계가 전혀 없는 덩어리(표가 한 줄로 눌린 경우 등)는 여기서 잘린다
    final: list[str] = []
    for chunk in chunks:
        while len(chunk) > size * 2:
            final.append(chunk[: size * 2])
            chunk = chunk[size * 2 - overlap :]
        final.append(chunk)
    return [c for c in final if c.strip()]


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


# RRF 표준값. 점수를 직접 더하지 않고 **순위**로 융합하는 이유는 두 점수의 스케일이
# 다르기 때문이다 — BM25 는 상한이 없고 코사인은 -1~1 이라, 정규화 없이 더하면 한쪽이 먹는다.
RRF_K = 60

# 융합 전에 각 검색기에서 뽑아 둘 후보 수. 최종 top-N 보다 넉넉해야 한쪽에서만
# 상위인 문서가 살아남는다.
FUSION_POOL = 30


class HybridIndex:
    """BM25(낱말 일치) + 의미 검색을 순위로 융합한다.

    한쪽만 쓰지 않는 이유는 서로 못 하는 일이 다르기 때문이다. 의미 검색은
    "떨어지면 다시" ↔ "재응시" 를 잇지만 `cdsa.site` 같은 고유 문자열에는 약하다.
    BM25 는 그 반대다.
    """

    def __init__(self, lexical: OpsIndex, dense: object, k: int = RRF_K) -> None:
        self.lexical = lexical
        self.dense = dense
        self.k = k
        self.sections = lexical.sections

    def search(self, query: str, top_n: int = 5) -> list[Hit]:
        fused: dict[str, float] = {}
        found: dict[str, OpsSection] = {}
        for engine in (self.lexical, self.dense):
            for rank, hit in enumerate(engine.search(query, top_n=FUSION_POOL), start=1):
                anchor = hit.section.anchor
                fused[anchor] = fused.get(anchor, 0.0) + 1 / (self.k + rank)
                found[anchor] = hit.section

        ranked = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)
        return [Hit(found[anchor], score) for anchor, score in ranked[:top_n]]


def build_hybrid_index() -> HybridIndex:
    """기본 검색기. 의미 검색 모델을 함께 올린다."""
    from backend.search.dense import DenseIndex

    sections = collect_operations()
    return HybridIndex(OpsIndex(sections), DenseIndex(sections))


def render_hits(hits: list[Hit]) -> str:
    """판정 프롬프트에 실을 표. 카탈로그의 운영 표와 같은 열을 쓴다."""
    out = [
        "## 운영 자료 (질문으로 검색한 결과)",
        "",
        "**검색 결과일 뿐이라 질문과 무관한 항목이 섞여 있다.** 검색은 관련이 없어도 언제나",
        "무언가를 돌려주므로, 제목이 그럴듯하다는 이유로 고르지 마라.",
        "",
        "- 질문이 **특정 세트·과목·문항을 지목하면**, 이 목록에 무엇이 있든 `문항` 이다",
        "- 이 목록에 질문의 근거가 **실제로** 있을 때만 `운영` 으로 판정한다",
        "- 근거가 없으면 다른 운영 섹션에도 없다고 보고 `escalate` 하라",
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
