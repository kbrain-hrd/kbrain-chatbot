"""5단계 — 유선 대응 웹 UI.

    uv run uvicorn backend.web.app:app --reload

담당자가 **전화를 받는 중에** 쓰는 화면이다. 통화하면서 읽어야 하므로 근거를 접지 않고,
되묻기 문구가 즉시 보여야 한다.

판정과 초안을 **별도 엔드포인트로 나눈 이유**: 되묻기가 주력 동작이기 때문이다
(골드셋 21건 중 17건). 되묻기는 판정만으로 끝나므로 Sonnet 한 번이면 되고, 느린
Opus 초안 생성을 기다릴 필요가 없다. 한 번에 처리하면 모든 질문이 초안 대기 시간을
떠안는다.
"""

from __future__ import annotations

from pathlib import Path

import anthropic
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.answer.classify import build_client, classify, load_catalog
from backend.answer.draft import load_materials, make_draft
from backend.search.index import OpsIndex, build_index

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="셀프스터디 문의 대응")

_client: anthropic.Anthropic | None = None
_catalog: str = ""
_index: OpsIndex | None = None


def client() -> anthropic.Anthropic:
    global _client, _catalog, _index
    if _client is None:
        _client = build_client()
        _catalog = load_catalog()
        # 운영 섹션 색인. 파일로 떨구지 않고 기동 시 메모리에 세운다.
        _index = build_index()
    return _client


class AskRequest(BaseModel):
    question: str


class DraftRequest(BaseModel):
    question: str
    anchor: str


@app.post("/api/classify")
def api_classify(request: AskRequest) -> dict:
    """1차 판정 — 분류·앵커·행동. 되묻기는 여기서 끝난다."""
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="질문이 비어 있습니다.")

    judgment, response = classify(client(), question, _catalog, index=_index)
    return {
        "category": judgment.category,
        "anchor": judgment.anchor,
        "action": judgment.action,
        "reason": judgment.reason,
        "cached": bool(response.usage.cache_read_input_tokens),
    }


@app.post("/api/draft")
def api_draft(request: DraftRequest) -> dict:
    """2차 생성 — 자료를 로드해 초안을 만든다. 판정이 answer 일 때만 호출한다."""
    try:
        materials = load_materials(request.anchor)
    except SystemExit as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    draft, _ = make_draft(client(), request.question, materials)
    return {
        "answer": draft.answer,
        "evidence": draft.evidence,
        "flags": draft.flags,
        "confidence": draft.confidence,
        "disputed": materials.disputed,
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
