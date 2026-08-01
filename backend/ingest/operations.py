"""운영 자료를 마크다운으로 변환하고 섹션 앵커를 부여한다.

    uv run python -m backend.ingest.operations

문제 자료와 달리 형식이 제각각이라(hwpx · HTML · PDF) 추출기를 따로 둔다.
문항 구조가 없으므로 앵커는 `OPS-준비안내-응시환경` 처럼 문서-섹션 단위다.

멱등하다. 자료가 갱신되면 다시 돌리면 된다.
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

from backend.ingest.extract import extract_pdfium

RAW = Path("raw")
OUT_DIR = Path("content/operations")

# hwpx 본문에서 `1. 개요` 처럼 번호가 붙은 문단이 섹션 경계다.
HWPX_HEADING_RE = re.compile(r"^(\d+)\.\s*(.+)$")


@dataclass
class Section:
    title: str
    body: str


@dataclass
class Document:
    slug: str  # 앵커에 쓰는 문서 이름 (예: 준비안내)
    source: Path
    sections: list[Section]


def slugify(text: str) -> str:
    """앵커에 쓸 수 있게 다듬는다. 한글은 그대로 두고 공백·기호만 정리."""
    cleaned = re.sub(r"[^\w가-힣]+", "", text)
    return cleaned or "본문"


# ---------------------------------------------------------------- hwpx


def extract_hwpx(path: Path) -> list[Section]:
    """hwpx 는 zip 안의 Contents/section0.xml 이 본문이다.

    텍스트가 서식 단위로 잘게 쪼개져 있어 문단(`<hp:p>`) 단위로 다시 붙인다.
    """
    with zipfile.ZipFile(path) as zf:
        xml = zf.read("Contents/section0.xml").decode("utf-8")

    paragraphs = []
    for chunk in re.findall(r"<hp:p\b.*?</hp:p>", xml, re.DOTALL):
        pieces = re.findall(r"<hp:t>(.*?)</hp:t>", chunk, re.DOTALL)
        text = "".join(re.sub(r"<[^>]+>", "", piece) for piece in pieces)
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            paragraphs.append(text)

    return group_by_heading(paragraphs, HWPX_HEADING_RE)


def group_by_heading(paragraphs: list[str], heading_re: re.Pattern[str]) -> list[Section]:
    sections: list[Section] = []
    title = "머리말"
    buffer: list[str] = []

    for text in paragraphs:
        match = heading_re.match(text)
        if match:
            if buffer:
                sections.append(Section(title, "\n\n".join(buffer)))
                buffer = []
            title = match.group(2).strip()
        else:
            buffer.append(text)

    if buffer:
        sections.append(Section(title, "\n\n".join(buffer)))
    return sections


# ---------------------------------------------------------------- HTML


class GuideParser(HTMLParser):
    """h1/h2 를 섹션 경계로 삼아 본문 텍스트를 모은다.

    이 가이드는 페이지마다 같은 h1/h2 쌍을 반복 출력하므로, 제목이 바뀔 때만
    새 섹션을 연다. 같은 제목이 다시 나오면 이어 붙인다.
    """

    SKIP = {"script", "style", "head"}

    def __init__(self) -> None:
        super().__init__()
        self.sections: list[Section] = []
        self._heading_level: int | None = None
        self._heading_text: list[str] = []
        self._skip_depth = 0
        self._current: Section | None = None
        self._h1 = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.SKIP:
            self._skip_depth += 1
        elif tag in ("h1", "h2"):
            self._heading_level = int(tag[1])
            self._heading_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in ("h1", "h2") and self._heading_level is not None:
            title = re.sub(r"\s+", " ", "".join(self._heading_text)).strip()
            if self._heading_level == 1:
                self._h1 = title
            elif title:
                full = f"{self._h1} — {title}" if self._h1 else title
                if self._current is None or self._current.title != full:
                    self._current = Section(full, "")
                    self.sections.append(self._current)
            self._heading_level = None

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._heading_level is not None:
            self._heading_text.append(data)
            return
        text = re.sub(r"\s+", " ", data).strip()
        if text and self._current is not None:
            self._current.body += text + "\n"


def extract_html(path: Path) -> list[Section]:
    parser = GuideParser()
    parser.feed(path.read_text(encoding="utf-8", errors="replace"))
    # 반복 출력 탓에 같은 문장이 여러 번 담긴다. 순서를 지키며 중복 줄을 걷어낸다.
    for section in parser.sections:
        seen: set[str] = set()
        kept = []
        for line in section.body.splitlines():
            if line and line not in seen:
                seen.add(line)
                kept.append(line)
        section.body = "\n".join(kept)
    return [s for s in parser.sections if s.body.strip()]


# ---------------------------------------------------------------- PDF

def extract_pdf(path: Path) -> list[Section]:
    """슬라이드형 PDF는 **페이지 상단 첫 줄이 제목** 역할을 한다.

    번호가 붙은 절 제목이 없으므로 페이지 제목으로 섹션을 나누고, 같은 제목이
    연달아 나오면(여러 장에 걸친 설명) 하나로 합친다.
    """
    sections: list[Section] = []

    for page_no, page in enumerate(extract_pdfium(path), start=1):
        lines = [re.sub(r"\s+", " ", line).strip() for line in page.splitlines()]
        lines = [line for line in lines if line]
        if not lines:
            continue

        title, rest = lines[0], lines[1:]
        body = "\n".join([f"<!-- page {page_no} -->", *rest])

        if sections and sections[-1].title == title:
            sections[-1].body += "\n" + body
        else:
            sections.append(Section(title, body))

    return sections


# ---------------------------------------------------------------- 출력


def render(doc: Document) -> str:
    out = [
        "---",
        f"doc: {doc.slug}",
        f"source: {doc.source.as_posix()}",
        f"sections: {len(doc.sections)}",
        "---",
        "",
        f"# {doc.slug}",
        "",
    ]
    # 간지처럼 같은 제목이 떨어져 다시 나오는 경우가 있다. 앵커가 겹치면 조회가
    # 모호해지므로 뒤에 순번을 붙여 유일하게 만든다.
    used: dict[str, int] = {}
    for section in doc.sections:
        anchor = f"OPS-{doc.slug}-{slugify(section.title)}"
        used[anchor] = used.get(anchor, 0) + 1
        if used[anchor] > 1:
            anchor = f"{anchor}-{used[anchor]}"
        out += [f"## [{anchor}] {section.title}", "", section.body.strip(), ""]
    return "\n".join(out).rstrip() + "\n"


def build() -> list[Document]:
    guide_html = next(RAW.glob("pkg/*/*.html"))

    docs = [
        Document("준비안내", RAW / "2026년_AI챔피언_자기주도형_수행평가_준비안내.hwpx", []),
        Document("셀프학습가이드", guide_html, []),
        Document("CBT가이드", RAW / "CBT_가이드.pdf", []),
    ]

    for doc in docs:
        suffix = doc.source.suffix.lower()
        if suffix == ".hwpx":
            doc.sections = extract_hwpx(doc.source)
        elif suffix == ".html":
            doc.sections = extract_html(doc.source)
        else:
            doc.sections = extract_pdf(doc.source)

    return docs


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    docs = build()

    for doc in docs:
        path = OUT_DIR / f"{doc.slug}.md"
        path.write_text(render(doc), encoding="utf-8")
        size = path.stat().st_size
        print(f"{doc.slug:<12} 섹션 {len(doc.sections):>3}개  {size:>7,} bytes  → {path}")

    print(
        "\n종합안내서(60p)는 디자인 브로슈어라 읽기 순서가 뒤엉켜 후순위입니다 "
        "— docs/05-data-survey.md 5장."
    )


if __name__ == "__main__":
    main()
