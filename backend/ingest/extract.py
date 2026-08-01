"""PDF 텍스트 추출기 두 종.

pypdfium2 가 기준이고 pdfplumber 는 대조군이다. pdfplumber 는 일부 답안지에서
문항·배점 숫자를 통째로 누락하는 것이 확인됐으므로 단독으로 쓰지 않는다.
두 결과가 갈리는 지점이 곧 변환 위험 지점이라 대조군으로 남긴다.
(docs/05-data-survey.md 3장)
"""

from __future__ import annotations

import re
from pathlib import Path

import pdfplumber
import pypdfium2 as pdfium

# 문서 첫머리의 대괄호 표기. 형식이 문서마다 제각각이라 조각으로 나눠 찾는다.
#   [연습세트01·그린] 1과목 — 콘텐츠      과목이 대괄호 밖
#   [연습세트02·블루] 답안지               과목 표기 없음
#   [연습세트04·블루·2과목] 답안지         과목이 대괄호 안
#   [연습04·그린·1과목] 해설               "세트" 글자 없음
#   [연습세트 05·그린] 답안지              공백 있음
BRACKET_RE = re.compile(r"\[([^\]]{0,60})\]")
SET_RE = re.compile(r"연습\s*(?:세트)?\s*(\d+)")
GRADE_RE = re.compile(r"(그린|블루)")
SUBJECT_RE = re.compile(r"(\d+)\s*과목")

GRADE_BY_LABEL = {"그린": "green", "블루": "blue"}


def extract_pdfium(path: Path) -> list[str]:
    """페이지별 텍스트. 기준 추출기."""
    pdf = pdfium.PdfDocument(path)
    try:
        return [page.get_textpage().get_text_bounded() for page in pdf]
    finally:
        pdf.close()


def extract_plumber(path: Path) -> list[str]:
    """페이지별 텍스트. 대조군."""
    with pdfplumber.open(path) as pdf:
        return [page.extract_text() or "" for page in pdf.pages]


def parse_header(text: str) -> tuple[str, int, int | None] | None:
    """문서 첫머리에 적힌 (등급, 세트번호, 과목번호)를 읽는다.

    문서가 스스로 등급·세트·과목을 밝히고 있으므로 폴더 경로와 대조할 수 있다.
    그린과 블루는 세트명·주제가 같고 정답만 다르므로, 파일이 엉뚱한 곳에 놓이면
    이후 처리가 전부 무의미해진다. 그 사고를 변환 시점에 잡기 위한 것이다.

    과목 번호는 아예 적지 않은 문서가 있어 None 일 수 있다. 등급·세트는 모든 문서가 밝힌다.
    """
    head = text[:400]

    bracket = BRACKET_RE.search(head)
    if not bracket:
        return None

    inside = bracket.group(1)
    grade_match = GRADE_RE.search(inside)
    set_match = SET_RE.search(inside)
    if not (grade_match and set_match):
        return None

    # 과목은 대괄호 안에 있기도 하고 바로 뒤에 있기도 하다. 너무 멀리서 찾으면 본문을 오인한다.
    subject_match = SUBJECT_RE.search(inside) or SUBJECT_RE.search(head[bracket.end() : bracket.end() + 60])

    return (
        GRADE_BY_LABEL[grade_match.group(1)],
        int(set_match.group(1)),
        int(subject_match.group(1)) if subject_match else None,
    )


def number_tokens(text: str) -> list[str]:
    """텍스트에 등장하는 숫자 토큰 전부.

    정답지에서 숫자가 사라지는 것이 가장 위험한 변환 사고이므로,
    두 추출기의 숫자 집합을 직접 비교하기 위해 뽑는다.
    """
    return re.findall(r"\d+", text)
