"""raw/ 를 스캔해 등급 × 세트 × 과목 단위를 찾는다.

폴더명이 등급마다 다르다:
    green  0707_AI 챔피언 그린 인증평가 예제문제/1세트_청렴윤리모니터링/1과목_콘텐츠/
    blue   AI 챔피언 블루 인증평가 예제문제/1세트_청렴윤리모니터링/1과목_생성형AI(콘텐츠)/

세트 주제명은 등급 공통이지만 과목명은 다르므로, 출력 경로에는 과목 번호만 쓰고
원래 이름은 마크다운 프론트매터에 보존한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

GRADE_CODES = {"green": "G", "blue": "B"}

# 문제지·해설·답안지 → 출력 파일명
KINDS = {"문제지": "problems", "해설": "solutions", "답안지": "answers"}

SET_RE = re.compile(r"^(\d+)세트_(.+)$")
SUBJECT_RE = re.compile(r"^(\d+)과목_(.+)$")

CONTENT_ROOT = Path("content/selfstudy")


@dataclass(frozen=True)
class Unit:
    """등급 × 세트 × 과목 하나. 문제지·해설·답안지 세 PDF를 가진다."""

    grade: str  # green | blue
    set_no: int
    set_title: str
    subject_no: int
    subject_title: str
    directory: Path

    @property
    def anchor_prefix(self) -> str:
        """G-S01-M02 — 문항 번호를 붙이면 완전한 앵커가 된다."""
        return f"{GRADE_CODES[self.grade]}-S{self.set_no:02d}-M{self.subject_no:02d}"

    @property
    def out_dir(self) -> Path:
        return CONTENT_ROOT / self.grade / f"s{self.set_no:02d}-{self.set_title}" / f"m{self.subject_no:02d}"

    def pdfs(self) -> dict[str, Path]:
        """{'problems': Path, ...} — 존재하는 것만."""
        found = {}
        for korean, english in KINDS.items():
            path = self.directory / f"{korean}.pdf"
            if path.is_file():
                found[english] = path
        return found


def discover(raw: Path = Path("raw")) -> list[Unit]:
    """raw/{green,blue}/ 아래의 모든 과목 단위를 찾는다.

    정렬된 순서로 반환한다 — 재실행 시 산출물이 같아야 하므로.
    """
    units: list[Unit] = []

    for grade in sorted(GRADE_CODES):
        grade_root = raw / grade
        if not grade_root.is_dir():
            continue

        for subject_dir in sorted(p for p in grade_root.rglob("*") if p.is_dir()):
            subject_match = SUBJECT_RE.match(subject_dir.name)
            if not subject_match:
                continue

            set_match = SET_RE.match(subject_dir.parent.name)
            if not set_match:
                continue

            units.append(
                Unit(
                    grade=grade,
                    set_no=int(set_match.group(1)),
                    set_title=set_match.group(2),
                    subject_no=int(subject_match.group(1)),
                    subject_title=subject_match.group(2),
                    directory=subject_dir,
                )
            )

    return units
