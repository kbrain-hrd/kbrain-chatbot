"""3단계 골드셋 후보를 만든다 — 질문마다 기대 분류·앵커·행동을 레이블링한다.

    uv run python -m backend.sheets.goldset

여기서 만드는 것은 **후보**다. 자동 판정한 뒤 사람이 검토해 확정한다.
확정본은 `eval/goldset.md` 에 두고, 이 스크립트는 재실행해도 확정본을 덮지 않는다.

레이블 세 가지:
  category  문제 / 운영 / 분류불가
  anchor    특정 가능한 경우의 앵커. 등급이 불명이면 세트·과목까지만 적는다.
  action    answer(답변 가능) / ask_grade(등급 되묻기) / escalate(사람에게)

**등급 되묻기가 핵심이다.** 질문은 "3세트 2과목"까지만 밝히는 경우가 많은데,
그린과 블루는 세트명이 같고 정답이 다르다. 시트가 등급별로 나뉘어 있어 맥락으로는
알 수 있지만 질문 텍스트만으로는 모르므로, 추측하지 않고 되묻는 것이 정답이다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from backend.sheets.extract import Entry, read_entries

SHEETS_ROOT = Path("raw/sheets")
OUT_PATH = Path("eval/goldset-candidates.md")
FINAL_PATH = Path("eval/goldset.md")

GRADE_IN_TEXT = {"그린": "G", "블루": "B"}
SUBJECT_WORDS = {
    1: ("1과목", "콘텐츠", "생성형"),
    2: ("2과목", "데이터분석", "데이터 분석"),
    3: ("3과목", "자동화", "서비스구현", "서비스 구현"),
}

# 분류마다 취해야 할 행동이 다르다 — 그래서 3분류로는 부족하다.
#   문항·운영   근거가 있어 답변 가능
#   자료요청    사람이 파일을 보내야 함. 챗봇이 답할 성질이 아니다
#   기술지원    도구 설치·계정 문제. 우리 근거 자료에 답이 없다
#   교육내용    개념 질문. 근거 없이 일반 지식으로 답하면 설계 원칙 위반
#   무관        홍보·잡담

MATERIAL_REQUEST_WORDS = (
    "다시 받", "재발송", "다운로드", "만료", "보내주", "공유해", "받을 수 있", "못 받",
    "재전송", "링크가", "자료 요청", "주세요",
)
SUPPORT_WORDS = (
    "안티그래비티", "노트북LM", "제미나이", "설치", "계정", "패치", "로그인", "접속이",
    "실행이", "오류가", "버전", "구독", "결제",
)
OPS_WORDS = (
    "응시", "접속", "CBT", "일정", "인증서", "재응시", "합격", "신청", "웹캠", "신분증",
    "화면 공유", "제출", "수료", "이러닝", "평가", "시험", "배점", "채점", "인증",
    "이수", "기간", "동영상", "영상", "강의", "수강", "과정", "언제", "가능할까요",
)
CONCEPT_WORDS = ("차이", "무엇인가요", "뭐예요", "뭔가요", "개념", "원리", "장단점", "이점")
IRRELEVANT_WORDS = ("홍보", "단톡방", "open.kakao")

EXAM_WORDS = ("세트", "과목", "문항", "정답", "답안", "문제지", "해설", "첨부")

SET_RE = re.compile(r"(?:연습\s*)?세트\s*0?(\d)|0?(\d)\s*세트")
QUESTION_NO_RE = re.compile(r"(\d)\s*번(?:\s*문항|\s*문제)?|문항\s*(\d)")


@dataclass
class Candidate:
    question: str
    answer: str
    sheet_grade: str  # 시트 파일명에서 온 등급 (맥락 정보 — 질문 텍스트에는 없을 수 있다)
    category: str
    anchor: str
    action: str
    reason: str


def sheet_grade_of(source: str) -> str:
    if "그린" in source:
        return "green"
    if "블루" in source:
        return "blue"
    return ""


def detect_subject(text: str) -> int | None:
    for number, words in SUBJECT_WORDS.items():
        if any(word in text for word in words):
            return number
    return None


def classify(entry: Entry) -> Candidate:
    text = entry.question
    sheet_grade = sheet_grade_of(entry.source)

    set_match = SET_RE.search(text)
    set_no = next((int(g) for g in (set_match.groups() if set_match else []) if g), None)
    subject_no = detect_subject(text)
    grade_in_text = next((code for word, code in GRADE_IN_TEXT.items() if word in text), None)

    def has(words: tuple[str, ...]) -> bool:
        return any(word in text for word in words)

    # 우선순위가 있다. 자료 요청은 세트·과목을 언급해도 파일을 달라는 뜻이므로
    # 문항 문의보다 먼저 걸러야 한다.
    if has(IRRELEVANT_WORDS):
        category = "무관"
    elif has(MATERIAL_REQUEST_WORDS):
        category = "자료요청"
    elif has(SUPPORT_WORDS):
        category = "기술지원"
    elif set_no or subject_no:
        category = "문항"
    elif has(OPS_WORDS):
        category = "운영"
    elif has(CONCEPT_WORDS):
        category = "교육내용"
    elif has(EXAM_WORDS):
        category = "문항"
    else:
        category = "분류불가"

    anchor, action, reason = "", "escalate", ""

    if category == "자료요청":
        return Candidate(text, entry.answer, sheet_grade, category, "", "escalate",
                         "파일 발송이 필요 — 사람이 처리")
    if category == "기술지원":
        return Candidate(text, entry.answer, sheet_grade, category, "", "escalate",
                         "도구·환경 문제로 근거 자료 없음")
    if category == "교육내용":
        return Candidate(text, entry.answer, sheet_grade, category, "", "escalate",
                         "개념 질문 — 근거 없이 일반 지식으로 답하지 않는다")
    if category == "무관":
        return Candidate(text, entry.answer, sheet_grade, category, "", "ignore", "홍보·잡담")

    if category == "문항":
        if set_no and subject_no:
            question_match = QUESTION_NO_RE.search(text)
            question_no = next((int(g) for g in question_match.groups() if g), None) if question_match else None

            if grade_in_text:
                anchor = f"{grade_in_text}-S{set_no:02d}-M{subject_no:02d}"
                action = "answer"
                reason = "등급·세트·과목이 질문에 모두 있음"
            else:
                anchor = f"?-S{set_no:02d}-M{subject_no:02d}"
                action = "ask_grade"
                reason = "세트·과목은 있으나 등급 표기 없음 — 되묻기"

            if question_no and 1 <= question_no <= 5:
                anchor += f"-Q{question_no:02d}"
            else:
                reason += " / 문항 번호 불명"
        else:
            action = "escalate"
            reason = "세트 또는 과목이 특정되지 않음"
    elif category == "운영":
        action = "answer"
        reason = "운영 자료로 답변 가능"
    else:
        reason = "분류 신호 없음"

    return Candidate(
        question=text,
        answer=entry.answer,
        sheet_grade=sheet_grade,
        category=category,
        anchor=anchor,
        action=action,
        reason=reason,
    )


def render(candidates: list[Candidate]) -> str:
    from collections import Counter

    categories = Counter(c.category for c in candidates)
    actions = Counter(c.action for c in candidates)

    out = [
        "# 골드셋 후보 (검토 전)",
        "",
        "`uv run python -m backend.sheets.goldset` 산출물. **자동 판정이라 그대로 쓰면 안 된다.**",
        "사람이 검토해 확정한 뒤 `eval/goldset.md` 로 옮긴다.",
        "",
        "## 분포",
        "",
        f"- 총 {len(candidates)}건",
        f"- 분류: {dict(categories)}",
        f"- 행동: {dict(actions)}",
        "",
        "`ask_grade` 는 세트·과목은 밝혔으나 **등급(그린/블루)을 밝히지 않은** 질문이다.",
        "그린과 블루는 세트명이 같고 정답이 다르므로 추측하지 않고 되묻는 것이 정답이다.",
        "",
        "## 항목",
        "",
        "| # | 분류 | 앵커 | 행동 | 시트 등급 | 질문 | 판정 근거 |",
        "|---|---|---|---|---|---|---|",
    ]
    for index, c in enumerate(candidates, start=1):
        question = c.question.replace("|", "·")[:90]
        out.append(
            f"| {index} | {c.category} | `{c.anchor or '-'}` | {c.action} | "
            f"{c.sheet_grade or '-'} | {question} | {c.reason} |"
        )
    return "\n".join(out) + "\n"


def main() -> None:
    entries: list[Entry] = []
    for path in sorted(SHEETS_ROOT.rglob("*.xlsx")):
        entries.extend(read_entries(path))

    candidates = [classify(entry) for entry in entries]

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(render(candidates), encoding="utf-8")

    from collections import Counter

    print(f"후보 {len(candidates)}건 → {OUT_PATH}")
    print(f"  분류: {dict(Counter(c.category for c in candidates))}")
    print(f"  행동: {dict(Counter(c.action for c in candidates))}")

    if FINAL_PATH.exists():
        print(f"\n확정본이 이미 있습니다: {FINAL_PATH} (덮어쓰지 않음)")


if __name__ == "__main__":
    main()
