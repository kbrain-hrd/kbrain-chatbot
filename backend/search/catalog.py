"""2단계 — 확정된 답안지에서 문항을 분리해 앵커 카탈로그를 만든다.

    uv run python -m backend.search.catalog

앵커는 `G-S01-M02-Q03` (등급-세트-과목-문항) 형식이다. 등급이 빠지면 그린·블루가
세트명·주제가 같고 정답만 달라 엉뚱한 근거로 답하게 되므로 필수다.

정답의 출처는 **확정된(verified: true) 답안지뿐**이다. 미확정 답안지는 카탈로그에
넣지 않는다 — 확정 전 값을 근거로 쓰면 1단계에서 잡은 추출 사고가 그대로 흘러든다.

문항 표의 헤더가 파일마다 조금씩 다르므로(`| 문항 | 배점 | 정답 | 근거 |` /
`| 문항 | 정답 | 검증 |` 등) 헤더에서 컬럼 위치를 찾아 흡수한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

CONTENT_ROOT = Path("content/selfstudy")
OPERATIONS_ROOT = Path("content/operations")
CATALOG_PATH = Path("content/catalog.md")
OVERRIDES_PATH = Path("content/question-overrides.md")

OPS_HEADING_RE = re.compile(r"^## \[(OPS-[^\]]+)\]\s*(.+)$")

# 카탈로그를 문항/운영으로 가르는 경계. 판정 때 운영만 검색 결과로 갈아끼우므로
# 여기서만 정의하고 backend.answer.classify 가 같은 값을 쓴다.
OPS_SECTION_HEADING = "## 운영 자료"

# 3과목은 단답 정답이 없는 산출물 평가라 문항 앵커가 성립하지 않는다.
SHORT_ANSWER_SUBJECTS = (1, 2)


@dataclass(frozen=True)
class Question:
    anchor: str
    grade: str
    set_no: int
    set_title: str
    subject_no: int
    question_no: int
    points: str
    answer: str
    note: str  # 근거·검증 요약 (있는 경우)
    question: str  # 문제지에서 뽑은 질문 요약 (추출 실패 시 빈 문자열)
    disputed: bool  # 공식 정답에 오류가 확인된 문항인가


def parse_front_matter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    fields = {}
    for line in text[3:end].splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()
    return fields


def split_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def find_question_table(text: str) -> tuple[list[str], list[list[str]]] | None:
    """문항 번호를 첫 칸에 담은 마크다운 표를 찾는다."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not line.strip().startswith("|"):
            continue
        header = split_row(line)
        if "문항" not in header:
            continue
        # 헤더 다음 줄은 구분선, 그 뒤가 데이터
        rows = []
        for row_line in lines[index + 2 :]:
            if not row_line.strip().startswith("|"):
                break
            cells = split_row(row_line)
            if cells and re.fullmatch(r"\d+", cells[0]):
                rows.append(cells)
        if rows:
            return header, rows
    return None


def column_index(header: list[str], *names: str) -> int | None:
    """헤더에 `근거 (첨부 보도자료 원문)` 처럼 수식어가 붙는 경우가 있어 부분 일치로 찾는다."""
    for name in names:
        for index, cell in enumerate(header):
            if cell.startswith(name):
                return index
    return None


# 문제지 표는 `1 15 질문 내용... 정수 (정확히 일치)` 형태로 평탄화된다.
# 답 형식이 질문 뒤에 붙어 오므로 꼬리에서 잘라낸다. 질문 본문에도 "정수" 같은 말이
# 나올 수 있어 뒤쪽에서만 찾는다.
ANSWER_FORMAT_TAIL_RE = re.compile(
    r"\s+(정수|한글\s*단답|한글|단답|제N조|L26-NNN)\b.{0,30}$"
)
PROBLEM_ROW_RE = re.compile(r"^(\d{1,2})\s+(\d{1,2})\s+(.+)$")


def extract_question_texts(path: Path) -> dict[int, str]:
    """문제지에서 문항별 질문 텍스트를 뽑는다.

    PDF 추출 시 표가 평탄화되며 질문이 표 밖으로 밀려나는 파일이 있다. 그런 경우
    질문 칸이 답 형식만 담긴 채로 나오므로, 건져지지 않은 문항은 비워 두고
    카탈로그 생성 단계에서 목록으로 보고한다.
    """
    if not path.is_file():
        return {}

    texts: dict[int, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = PROBLEM_ROW_RE.match(line.strip())
        if not match:
            continue
        question_no, _, rest = int(match.group(1)), match.group(2), match.group(3).strip()
        if not (1 <= question_no <= 5) or question_no in texts:
            continue

        rest = ANSWER_FORMAT_TAIL_RE.sub("", rest).strip()

        # 질문이 밀려나 답 형식만 남은 줄은 버린다
        if len(rest) < 8 or "?" not in rest and "니까" not in rest:
            continue
        texts[question_no] = re.sub(r"\s+", " ", rest)

    return texts


def extract_questions(path: Path) -> list[Question]:
    text = path.read_text(encoding="utf-8")
    meta = parse_front_matter(text)

    if meta.get("verified") != "true":
        return []

    subject_no = int(meta["subject_no"])
    if subject_no not in SHORT_ANSWER_SUBJECTS:
        return []

    found = find_question_table(text)
    if found is None:
        raise SystemExit(f"{path}: 문항 표를 찾지 못했습니다.")

    header, rows = found
    no_at = header.index("문항")
    answer_at = column_index(header, "정답")
    points_at = column_index(header, "배점")
    note_at = column_index(header, "검증", "근거 요약", "근거", "채점 기준")

    if answer_at is None:
        raise SystemExit(f"{path}: 표에 '정답' 컬럼이 없습니다 — 헤더 {header}")

    prefix = meta["anchor_prefix"]
    question_texts = extract_question_texts(path.with_name("problems.md"))

    # 출제기관이 오류를 인정한 문항 — 정답을 그대로 내보내면 안 된다.
    disputed = set()
    if meta.get("official_answer_disputed") == "true":
        disputed = {int(n) for n in re.findall(r"\d+", meta.get("disputed_questions", ""))}

    questions = []
    for cells in rows:
        if len(cells) <= answer_at:
            continue
        question_no = int(cells[no_at])
        questions.append(
            Question(
                anchor=f"{prefix}-Q{question_no:02d}",
                grade=meta["grade"],
                set_no=int(meta["set_no"]),
                set_title=meta["set_title"],
                subject_no=subject_no,
                question_no=question_no,
                points=cells[points_at] if points_at is not None and len(cells) > points_at else "",
                answer=cells[answer_at],
                note=cells[note_at] if note_at is not None and len(cells) > note_at else "",
                question=question_texts.get(question_no, ""),
                disputed=question_no in disputed,
            )
        )
    return questions


def load_overrides() -> dict[str, str]:
    """문제지에서 자동 추출이 안 되는 문항의 질문 텍스트를 읽는다."""
    if not OVERRIDES_PATH.is_file():
        return {}

    overrides = {}
    for line in OVERRIDES_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = split_row(line)
        if len(cells) < 2:
            continue
        anchor = cells[0].strip("`")
        if re.fullmatch(r"[GB]-S\d{2}-M\d{2}-Q\d{2}", anchor):
            overrides[anchor] = cells[1]
    return overrides


def collect() -> list[Question]:
    questions: list[Question] = []
    for path in sorted(CONTENT_ROOT.rglob("answers.md")):
        questions.extend(extract_questions(path))

    # 보완 파일이 있으면 그쪽을 우선한다 — 자동 추출이 질문을 중간에서 자른 경우가 있다.
    overrides = load_overrides()
    questions = [
        Question(**{**q.__dict__, "question": overrides[q.anchor]}) if q.anchor in overrides else q
        for q in questions
    ]
    return sorted(questions, key=lambda q: (q.grade, q.set_no, q.subject_no, q.question_no))


def check(questions: list[Question]) -> list[str]:
    """완료 조건 검사 — 누락·중복 0건."""
    problems = []

    anchors = [q.anchor for q in questions]
    duplicates = {a for a in anchors if anchors.count(a) > 1}
    if duplicates:
        problems.append(f"앵커 중복: {sorted(duplicates)}")

    for grade in ("green", "blue"):
        for set_no in range(1, 6):
            for subject_no in SHORT_ANSWER_SUBJECTS:
                got = [q for q in questions if (q.grade, q.set_no, q.subject_no) == (grade, set_no, subject_no)]
                numbers = sorted(q.question_no for q in got)
                if numbers != [1, 2, 3, 4, 5]:
                    problems.append(f"{grade} {set_no}세트 {subject_no}과목 문항 번호 이상: {numbers}")

    empty = [q.anchor for q in questions if not q.answer]
    if empty:
        problems.append(f"정답이 빈 문항: {empty}")

    return problems


def missing_questions(questions: list[Question]) -> list[str]:
    """질문 텍스트를 문제지에서 건지지 못한 문항. 누락·중복과 달리 즉시 실패 사유는 아니다."""
    return [q.anchor for q in questions if not q.question]


def suspect_questions(questions: list[Question]) -> list[tuple[str, str]]:
    """질문이 중간에서 잘린 것으로 의심되는 문항.

    PDF 표에서 질문이 두 줄로 나뉘면 첫 줄만 잡히고 뒤가 날아간다. 답 형식 단어로
    끝나거나 물음표 없이 끝나는 질문이 그 신호다. 보완 파일로 고칠 대상을 알려준다.
    """
    suspects = []
    for q in questions:
        if not q.question:
            continue
        text = q.question.rstrip()
        if text.endswith(("?", ".", ")")):
            continue
        suspects.append((q.anchor, text))
    return suspects


# 운영 질문에 자주 등장하는 말. 섹션 제목만으로는 안에 무엇이 있는지 알기 어려운 문서가
# 있어(종합안내서의 "III AI 챔피언" 등) 본문에서 이 낱말들을 찾아 카탈로그에 함께 싣는다.
OPS_KEYWORDS = (
    "수료", "선발", "합격", "75점", "재응시", "인증서", "일정", "신청", "응시",
    "CBT", "웹캠", "신분증", "이러닝", "그린", "블루", "배점", "채점", "제출",
    "준비물", "환경", "자격", "가점", "결시",
)


@dataclass(frozen=True)
class OpsSection:
    anchor: str
    doc: str
    title: str
    length: int  # 본문 길이 — 조회 비용 가늠용
    keywords: str  # 본문에 나타난 운영 핵심어
    body: str  # 검색 색인용. 카탈로그 표에는 싣지 않는다


def collect_operations() -> list[OpsSection]:
    """운영 자료의 섹션 앵커를 모은다.

    운영 질문은 문항 구조가 없어 섹션 단위로 특정한다. 제목만으로 고를 수 있도록
    카탈로그에 목록을 싣는다.
    """
    sections: list[OpsSection] = []
    for path in sorted(OPERATIONS_ROOT.glob("*.md")):
        doc = path.stem
        lines = path.read_text(encoding="utf-8").splitlines()
        starts = [(i, m) for i, line in enumerate(lines) if (m := OPS_HEADING_RE.match(line))]
        for order, (index, match) in enumerate(starts):
            end = starts[order + 1][0] if order + 1 < len(starts) else len(lines)
            body = "\n".join(lines[index + 1 : end]).strip()
            found = [word for word in OPS_KEYWORDS if word in body]
            sections.append(
                OpsSection(match.group(1), doc, match.group(2).strip(), len(body), " · ".join(found), body)
            )
    return sections


def render(questions: list[Question], ops: list[OpsSection]) -> str:
    out = [
        "# 앵커 카탈로그",
        "",
        "`uv run python -m backend.search.catalog` 산출물. **확정된(`verified: true`) 답안지에서만** 생성한다.",
        "",
        "질문 특정은 이 표를 통째로 컨텍스트에 넣고 고르는 방식이다 — 벡터 검색을 쓰지 않는 이유는",
        "`docs/03-roadmap.md` 참조. 앵커에 **등급(G/B)이 반드시 포함**된다. 그린과 블루는 세트명·주제가",
        "같고 정답만 다르므로, 등급을 빠뜨리면 엉뚱한 정답을 근거로 답하게 된다.",
        "",
        f"총 {len(questions)}문항 (1·2과목 × 5세트 × 2등급 × 5문항). 3과목은 단답 정답이 없어 제외.",
        f"운영 자료 섹션 {len(ops)}개는 문서 끝에 별도로 싣는다.",
        "",
    ]

    disputed = [q for q in questions if q.disputed]
    if disputed:
        out += [
            f"## ⚠️ 공식 정답에 오류가 확인된 문항 ({len(disputed)}건)",
            "",
            "출제기관이 오류를 인정하고 **수정 예정**인 문항이다. 아래 표의 정답은 **수정 전 값**이므로",
            "**정답이라고 단정해 답변하지 말 것.** 판정 대신 경위를 안내하고 사람에게 넘긴다.",
            "",
            "| 앵커 | 수정 전 공식 정답 | 내용 |",
            "|---|---|---|",
        ]
        for q in disputed:
            out.append(f"| `{q.anchor}` | {q.answer} | {q.note.replace('|', '·')} |")
        out += [
            "",
            "경위는 해당 답안지 파일(`content/selfstudy/.../answers.md`) 상단에 전문이 있다.",
            "",
        ]

    subject_names = {1: "콘텐츠", 2: "데이터분석"}

    for grade in ("green", "blue"):
        label = "그린" if grade == "green" else "블루"
        out += [f"## {label} ({grade})", ""]
        for set_no in range(1, 6):
            in_set = [q for q in questions if q.grade == grade and q.set_no == set_no]
            if not in_set:
                continue
            out += [f"### {set_no}세트 — {in_set[0].set_title}", ""]
            for subject_no in SHORT_ANSWER_SUBJECTS:
                items = [q for q in in_set if q.subject_no == subject_no]
                if not items:
                    continue
                out += [
                    f"**{subject_no}과목 {subject_names[subject_no]}**",
                    "",
                    "| 앵커 | 배점 | 질문 | 정답 | 근거 |",
                    "|---|---|---|---|---|",
                ]
                for q in items:
                    note = q.note.replace("|", "·")
                    question = q.question.replace("|", "·") or "*(문제지 추출 실패 — 원문 확인 필요)*"
                    answer = f"⚠️ {q.answer}" if q.disputed else q.answer
                    out.append(f"| `{q.anchor}` | {q.points} | {question} | {answer} | {note} |")
                out.append("")

    out += [
        OPS_SECTION_HEADING,
        "",
        "운영 질문(신청 방법·응시 환경·합격 기준·일정 등)의 근거다. 문항 구조가 없어 **섹션 단위**로 특정한다.",
        "본문 길이는 조회 비용 가늠용이며, 긴 섹션은 통째로 싣기 전에 필요한 부분을 확인하세요.",
        "",
        "아래 표는 **사람이 전체를 훑기 위한 목록**이다. 판정할 때는 이 표를 통째로 싣지 않고",
        "질문으로 검색한 상위 5개만 싣는다 (`backend/search/index.py`). 문항 표는 전량 싣는다.",
        "",
        "**어디를 먼저 볼지**:",
        "",
        "- **FAQ** `OPS-셀프학습가이드-부록2인증평가FAQ수행평가관련자주묻는질문` — 인증 방식·합격 기준(75점)·",
        "  CBT 진행·평가 일정·재응시·인증서 발급·문의처가 한곳에. 가장 밀도가 높다.",
        "- **종합안내서 `III AI 챔피언`** — 선발·수료 기준, 그린/블루 과정 구성. 사실상 운영 답지다.",
        "  제목이 로마숫자라 내용을 짐작하기 어려우니 아래 핵심어를 보고 고를 것.",
        "- **준비안내 · CBT가이드** — 응시 환경·준비물·접속 절차. 제목이 명확해 바로 찾을 수 있다.",
        "",
        "섹션 제목이 불친절한 문서가 있어 본문의 핵심어를 함께 싣는다. 제목이 아니라 **핵심어로 고르면 된다.**",
        "",
        "| 앵커 | 문서 | 섹션 | 길이 | 핵심어 |",
        "|---|---|---|---|---|",
    ]
    for section in ops:
        out.append(
            f"| `{section.anchor}` | {section.doc} | {section.title} | "
            f"{section.length:,} | {section.keywords or '-'} |"
        )

    return "\n".join(out).rstrip() + "\n"


def main() -> None:
    questions = collect()
    ops = collect_operations()
    problems = check(questions)

    ops_anchors = [s.anchor for s in ops]
    duplicated = {a for a in ops_anchors if ops_anchors.count(a) > 1}
    if duplicated:
        problems.append(f"운영 섹션 앵커 중복: {sorted(duplicated)}")

    CATALOG_PATH.write_text(render(questions, ops), encoding="utf-8")

    size = CATALOG_PATH.stat().st_size
    print(f"문항 {len(questions)}개 + 운영 섹션 {len(ops)}개 → {CATALOG_PATH} "
          f"({size:,} bytes, 대략 {size // 3:,} 토큰)")

    absent = missing_questions(questions)
    if absent:
        print(f"\n질문 텍스트 추출 실패 {len(absent)}건 (문제지 표가 평탄화되며 질문이 밀려난 경우):")
        for anchor in absent:
            print(f"  - {anchor}")

    suspects = suspect_questions(questions)
    if suspects:
        print(f"\n질문이 잘린 것으로 의심되는 문항 {len(suspects)}건 — content/question-overrides.md 로 보완하세요:")
        for anchor, text in suspects:
            print(f"  - {anchor}: ...{text[-40:]}")

    if problems:
        print("\n확인 필요:")
        for problem in problems:
            print(f"  - {problem}")
        raise SystemExit(1)
    print("누락·중복 없음.")


if __name__ == "__main__":
    main()
