"""운영 섹션 의미 검색 — BM25 가 낱말 겹침으로 놓치는 것을 메운다.

    uv run python -m backend.search.dense "시험 떨어지면 다시 볼 수 있나요"

BM25 만으로도 표현이 겹치는 질문은 1위로 잡는다. 문제는 낱말이 어긋날 때다 —
"떨어지면 다시" ↔ "재응시", "몇 점" ↔ "75점" 처럼 같은 뜻을 다른 말로 물으면
순위가 밀린다(실측 3·6·6·9위). 그 간극을 메우는 것이 이 모듈의 유일한 목적이다.

**로컬 모델을 쓴다.** API 키가 늘지 않고, 반복 실험이 무료이며, 개인정보가 섞일 수 있는
문의 텍스트를 외부로 내보내지 않는다. `multilingual-e5-small` 은 471MB 로 CPU 에서도
빠르다 — 유선 응대는 응답 시간이 제약이라 큰 모델을 앞에 두지 않는다.

색인은 **런타임 파생물**이다. 289청크 임베딩이 기동 시 수 초면 끝나므로 파일로 떨구지
않는다. 원본은 `content/operations/*.md` 하나뿐이어야 한다.
"""

from __future__ import annotations

from backend.search.catalog import OpsSection
from backend.search.index import Hit, chunk_body

# e5 계열은 질의와 문서에 서로 다른 접두사를 요구한다. 빼먹으면 정확도가 눈에 띄게 떨어진다.
MODEL_NAME = "intfloat/multilingual-e5-small"
QUERY_PREFIX = "query: "
PASSAGE_PREFIX = "passage: "


class DenseIndex:
    """섹션을 청크로 나눠 임베딩한다. 점수는 섹션 단위로 집약한다."""

    def __init__(self, sections: list[OpsSection], model_name: str = MODEL_NAME) -> None:
        # torch 로딩이 무거우므로 이 시점에만 끌어온다. BM25 만 쓰는 경로는 영향받지 않는다.
        from sentence_transformers import SentenceTransformer

        self.sections = sections
        self.model = SentenceTransformer(model_name)

        self.owners: list[int] = []
        self.chunks: list[str] = []
        passages: list[str] = []
        for index, section in enumerate(sections):
            # 제목은 FAQ 에서 곧 질문이라 청크마다 붙여 문맥을 잃지 않게 한다.
            for chunk in chunk_body(section.body) or [section.title]:
                self.owners.append(index)
                self.chunks.append(chunk)
                passages.append(f"{PASSAGE_PREFIX}{section.title}\n{chunk}")

        self.vectors = self.model.encode(
            passages, normalize_embeddings=True, batch_size=32, show_progress_bar=False
        )

    def search(self, query: str, top_n: int = 5) -> list[Hit]:
        vector = self.model.encode(
            [f"{QUERY_PREFIX}{query}"], normalize_embeddings=True, show_progress_bar=False
        )[0]
        scores = self.vectors @ vector

        # 한 섹션이 여러 청크로 쪼개져 있다. 가장 잘 맞은 청크 점수를 그 섹션의 점수로 보고,
        # 그 청크를 스니펫으로 함께 돌려준다 — 판정 모델이 내용을 보고 고를 수 있어야 한다.
        best: dict[int, tuple[float, str]] = {}
        for position, (owner, score) in enumerate(zip(self.owners, scores)):
            value = float(score)
            if value > best.get(owner, (float("-inf"), ""))[0]:
                best[owner] = (value, self.chunks[position])

        ranked = sorted(best.items(), key=lambda kv: kv[1][0], reverse=True)
        return [Hit(self.sections[i], score, snippet) for i, (score, snippet) in ranked[:top_n]]


def build_dense_index() -> DenseIndex:
    from backend.search.catalog import collect_operations

    return DenseIndex(collect_operations())


def main() -> None:
    import sys

    if len(sys.argv) < 2:
        raise SystemExit('사용법: uv run python -m backend.search.dense "질문 내용"')

    index = build_dense_index()
    print(f"청크 {len(index.owners)}개 색인\n")
    for rank, hit in enumerate(index.search(" ".join(sys.argv[1:]), top_n=8), start=1):
        print(f"{rank}. {hit.score:6.3f}  {hit.section.anchor}")
        print(f"          {hit.section.title[:70]}")


if __name__ == "__main__":
    main()
