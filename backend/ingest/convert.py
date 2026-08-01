"""1단계 — PDF를 마크다운으로 변환하고, 두 추출기 결과를 대조해 리포트를 낸다.

    uv run python -m backend.ingest.convert

멱등하다. 같은 raw/ 로 몇 번을 돌려도 산출물이 같아야 한다 (자료가 계속 추가되므로
매번 전체를 다시 돌리게 된다). 그래서 리포트에도 실행 시각을 넣지 않는다.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from backend.ingest.extract import (
    extract_pdfium,
    extract_plumber,
    number_tokens,
    parse_header,
)
from backend.ingest.sources import Unit, discover

REPORT_PATH = Path("eval/ingest-diff.md")


@dataclass
class Finding:
    """한 PDF의 대조 결과."""

    source: str
    out_path: str
    kind: str
    header_mismatch: str | None  # 폴더 경로와 문서 헤더가 어긋난 경우
    missing_numbers: list[str]  # pypdfium2 에는 있는데 pdfplumber 에 없는 숫자
    extra_numbers: list[str]  # 반대 방향 — pypdfium2 가 숫자를 병합했을 신호
    line_delta: int  # 정규화 후 라인 수 차이

    @property
    def is_clean(self) -> bool:
        return (
            self.header_mismatch is None
            and not self.missing_numbers
            and not self.extra_numbers
            and self.line_delta == 0
        )


def normalize_lines(pages: list[str]) -> list[str]:
    """추출기 간 공백 처리 차이를 걷어내고 내용 라인만 남긴다."""
    lines = []
    for page in pages:
        for line in page.splitlines():
            collapsed = re.sub(r"\s+", " ", line).strip()
            if collapsed:
                lines.append(collapsed)
    return lines


def render_pages(pages: list[str]) -> list[str]:
    """페이지 마커를 붙여 본문을 만든다. 마커는 원본과 대조할 때의 좌표가 된다."""
    body = []
    for index, page in enumerate(pages, start=1):
        body.append(f"<!-- page {index} -->")
        body.append(page.strip())
        body.append("")
    return body


def to_markdown(
    unit: Unit,
    kind: str,
    source: Path,
    pdfium_pages: list[str],
    plumber_pages: list[str],
    agree: bool,
) -> str:
    """프론트매터 + 본문. 문항 분리와 앵커 부여는 2단계 작업이므로 전문을 그대로 싣는다.

    답안지는 두 추출기가 서로 다른 방식으로 실패한다 — pdfplumber 는 숫자를 누락하고
    pypdfium2 는 인접 셀 숫자를 병합한다. 어느 쪽도 단일 기준이 될 수 없으므로
    **두 결과를 모두 싣고 사람이 원본과 대조해 확정**한다. 정답은 이 시스템의 근거이므로
    추측으로 하나를 고르지 않는다.
    """
    is_answers = kind == "answers"

    front_matter = [
        "---",
        f"anchor_prefix: {unit.anchor_prefix}",
        f"grade: {unit.grade}",
        f"set_no: {unit.set_no}",
        f"set_title: {unit.set_title}",
        f"subject_no: {unit.subject_no}",
        f"subject_title: {unit.subject_title}",
        f"kind: {kind}",
        f"source: {source.as_posix()}",
    ]

    if is_answers:
        front_matter += [
            "extractor: both",
            f"extractors_agree: {str(agree).lower()}",
            "verified: false",  # 사람이 원본과 대조해 확정하면 true 로 바꾼다
        ]
    else:
        front_matter += ["extractor: pypdfium2"]

    front_matter += ["---", ""]

    if not is_answers:
        return "\n".join(front_matter + render_pages(pdfium_pages)).rstrip() + "\n"

    notice = (
        "> **미확정 정답지.** 두 추출기 결과가 **갈립니다** — 원본 PDF와 대조해 확정하세요."
        if not agree
        else "> **미확정 정답지.** 두 추출기 결과는 일치하지만 아직 사람이 확인하지 않았습니다."
    )

    body = [
        notice,
        ">",
        "> 확정 후 프론트매터의 `verified` 를 `true` 로 바꾸고, 맞는 쪽만 남기세요.",
        "",
        "## pypdfium2 추출",
        "",
        *render_pages(pdfium_pages),
        "## pdfplumber 추출",
        "",
        *render_pages(plumber_pages),
    ]

    return "\n".join(front_matter + body).rstrip() + "\n"


def check_header(unit: Unit, pages: list[str]) -> str | None:
    """문서가 밝힌 등급·세트·과목이 폴더 경로와 맞는지 본다.

    과목 번호를 적지 않은 문서가 있어, 그런 경우 등급·세트만 대조한다.
    """
    if not pages:
        return "본문 없음 — 헤더 확인 불가"

    parsed = parse_header(pages[0])
    if parsed is None:
        return "문서 헤더를 찾지 못함"

    grade, set_no, subject_no = parsed

    if (grade, set_no) != (unit.grade, unit.set_no):
        return f"문서는 {grade}/{set_no}세트 라고 밝힘 — 경로는 {unit.grade}/{unit.set_no}세트"

    if subject_no is not None and subject_no != unit.subject_no:
        return f"문서는 {subject_no}과목 이라고 밝힘 — 경로는 {unit.subject_no}과목"

    return None


def convert_one(unit: Unit, kind: str, source: Path) -> Finding:
    pdfium_pages = extract_pdfium(source)
    plumber_pages = extract_plumber(source)

    pdfium_numbers = Counter(number_tokens("\n".join(pdfium_pages)))
    plumber_numbers = Counter(number_tokens("\n".join(plumber_pages)))
    missing = sorted((pdfium_numbers - plumber_numbers).elements())
    extra = sorted((plumber_numbers - pdfium_numbers).elements())

    out_path = unit.out_dir / f"{kind}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        to_markdown(unit, kind, source, pdfium_pages, plumber_pages, agree=not (missing or extra)),
        encoding="utf-8",
    )

    return Finding(
        source=source.as_posix(),
        out_path=out_path.as_posix(),
        kind=kind,
        header_mismatch=check_header(unit, pdfium_pages),
        missing_numbers=missing,
        extra_numbers=extra,
        line_delta=len(normalize_lines(pdfium_pages)) - len(normalize_lines(plumber_pages)),
    )


def render_report(findings: list[Finding], unit_count: int) -> str:
    header_issues = [f for f in findings if f.header_mismatch]
    pdfium_suspect = [f for f in findings if f.extra_numbers]
    plumber_missing = [f for f in findings if f.missing_numbers and not f.extra_numbers]
    line_issues = [f for f in findings if f.line_delta != 0 and not (f.missing_numbers or f.extra_numbers)]
    answer_sheets = [f for f in findings if f.kind == "answers"]

    out = [
        "# 인제스트 대조 리포트",
        "",
        "`uv run python -m backend.ingest.convert` 산출물. pypdfium2 와 pdfplumber 로 각각 추출해 대조한다.",
        "두 추출기가 갈리는 지점이 곧 변환 위험 지점이므로, 사람이 원본과 확인할 곳을 좁혀준다.",
        "",
        "**두 추출기는 서로 다른 방식으로 실패한다.** pdfplumber 는 답안지에서 숫자를 통째로 누락하고,",
        "pypdfium2 는 좁은 표 열에서 인접 셀 숫자를 병합한다(`15 4` → `154`). 단일 기준이 성립하지 않아",
        "답안지는 두 결과를 모두 실어두고 사람이 확정한다.",
        "",
        "## 요약",
        "",
        f"- 과목 단위: {unit_count}개",
        f"- 변환한 PDF: {len(findings)}개",
        f"- 헤더 교차검증 불일치: **{len(header_issues)}건**",
        f"- **기준 추출기(pypdfium2) 손상 의심: {len(pdfium_suspect)}건** ← 가장 먼저 볼 것",
        f"- pdfplumber 숫자 누락: {len(plumber_missing)}건",
        f"- 숫자는 같으나 라인 수가 다름: {len(line_issues)}건",
        f"- 미확정 답안지: {len(answer_sheets)}개 (전부 `verified: false`)",
        "",
    ]

    out += ["## 1. 헤더 교차검증", ""]
    if header_issues:
        out += ["문서가 밝힌 등급·세트·과목이 폴더 경로와 어긋납니다. **파일 배치 사고일 수 있습니다.**", ""]
        out += [f"- `{f.source}` — {f.header_mismatch}" for f in header_issues]
    else:
        out += ["불일치 없음. 모든 문서의 등급·세트·과목이 폴더 경로와 일치합니다."]
    out += [""]

    out += [
        "## 2. 기준 추출기(pypdfium2) 손상 의심",
        "",
        "pdfplumber 에만 있는 숫자가 존재합니다. pypdfium2 가 인접 셀 숫자를 **병합**했을 신호이며,",
        "이 경우 pdfplumber 쪽이 맞을 가능성이 높습니다. **정답이 틀리게 변환되는 유형입니다.**",
        "",
    ]
    if pdfium_suspect:
        for finding in pdfium_suspect:
            out += [
                f"### `{finding.source}`",
                "",
                f"- pdfplumber 에만 존재: `{' '.join(finding.extra_numbers)}`",
            ]
            if finding.missing_numbers:
                out += [f"- pypdfium2 에만 존재: `{' '.join(finding.missing_numbers)}`"]
            out += [f"- 변환 결과: `{finding.out_path}`", ""]
    else:
        out += ["없음.", ""]

    out += [
        "## 3. pdfplumber 숫자 누락",
        "",
        "pypdfium2 에는 있으나 pdfplumber 에 없는 숫자입니다. 이미 확인된 pdfplumber 결함이므로",
        "pypdfium2 쪽이 맞을 가능성이 높지만, 답안지는 확정 시 원본으로 확인하세요.",
        "",
    ]
    if plumber_missing:
        out += [
            f"- `{f.source}` — 누락 {len(f.missing_numbers)}개: `{' '.join(f.missing_numbers)}`"
            for f in plumber_missing
        ]
    else:
        out += ["없음."]
    out += [""]

    out += ["## 4. 라인 수 차이 (숫자는 일치)", ""]
    if line_issues:
        out += ["표 열 병합·줄바꿈 처리 차이일 가능성이 높으나, 표 손상일 수도 있습니다.", ""]
        out += [f"- `{f.source}` — 라인 차이 {f.line_delta:+d}" for f in line_issues]
    else:
        out += ["차이 없음."]
    out += [""]

    return "\n".join(out)


def main() -> None:
    units = discover()
    if not units:
        raise SystemExit("raw/green, raw/blue 아래에서 과목 단위를 찾지 못했습니다.")

    findings = []
    for unit in units:
        for kind, source in sorted(unit.pdfs().items()):
            findings.append(convert_one(unit, kind, source))

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(render_report(findings, len(units)), encoding="utf-8")

    clean = sum(1 for f in findings if f.is_clean)
    print(f"단위 {len(units)}개 / PDF {len(findings)}개 변환")
    print(f"이상 없음 {clean}개, 확인 필요 {len(findings) - clean}개 → {REPORT_PATH}")


if __name__ == "__main__":
    main()
