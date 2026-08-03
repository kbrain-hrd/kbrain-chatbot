"""6단계 — 구글시트 접근.

    uv run python -m backend.sheets.client      # 연결·헤더 확인 + 긴 글 열 줄바꿈 서식

서비스 계정으로 시트를 연다. `.env` 에 두 값이 필요하다.

    SHEET_URL=https://docs.google.com/spreadsheets/d/<ID>/edit
    GOOGLE_CREDENTIALS=raw/<서비스계정>.json

컬럼은 **위치가 아니라 헤더 이름으로 찾는다.** docs/02-data.md 3장 스키마는 "제안"이고
실제 시트가 그대로라는 보장이 없다. 헤더가 다르면 HEADERS 의 별칭만 고치면 된다.

**개인정보 컬럼은 읽는 범위에서 아예 빠진다.** 시트 전체를 받아오면 이름·소속기관이
프로세스 안에 들어오므로, 헤더 행만 먼저 읽어 필요한 컬럼의 범위를 만들고 그것만 가져온다.
질문 본문에 남은 연락처는 `extract.mask` 로 마스킹한다 — 컬럼을 빼는 것만으로는 걸러지지
않는 사례가 확인됐다 (CLAUDE.md 개인정보).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

import gspread
from dotenv import load_dotenv

from backend.sheets.extract import mask

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 헤더가 1행이라는 보장이 없다 — 실제 시트는 1행이 제목 줄이었다(2026-08-03).
# extract.py 도 같은 이유로 상위 몇 행을 훑어 헤더를 찾는다.
HEADER_SEARCH_ROWS = 12

# 우리가 읽거나 쓰는 컬럼. 값은 허용 헤더 이름들이다.
# 시트에는 **응시자가 봐도 되는 것만** 둔다. 분류·초안·근거·플래그는 검수용이라
# 슬랙 카드에만 싣는다 (2026-08-03 결정) — 응시자가 편집 권한을 가진 시트라
# 열을 숨겨도 펼쳐 볼 수 있기 때문이다.
HEADERS: dict[str, tuple[str, ...]] = {
    "question": ("질문", "질문 내용", "문의내용"),
    "status": ("상태",),
    # 승인된 최종답변이 들어가는 칸. 기존 운영 관례를 그대로 쓴다 — docs/04 2-7.
    "answer": ("답변",),
    "answered_at": ("답변일", "검수일시"),
}

# 매핑하지 않는 컬럼 — 개인정보. 목록에 두는 것은 시트에 있는지 확인해 보고하기 위해서다.
PII_HEADERS = {
    "질문자", "이름", "교육생 이름", "소속기관", "소속기관구분", "연락처", "이메일", "전화번호",
}

STATUS_REVIEW = "검수대기"
# 승인·수정 결과. `답변완료` 는 과거 회차 시트에서 쓰이던 값을 그대로 이었다.
STATUS_DONE = "답변완료"
# 지금 판단하기 어려워 넘긴 건. `반려` 로 두면 답변 없이 끝나는 막다른 길이 된다.
STATUS_HOLD = "답변대기"

SHEET_ID_RE = re.compile(r"/spreadsheets/d/([a-zA-Z0-9-_]+)")


def spreadsheet_id(value: str) -> str:
    """URL 이면 ID 를 뽑고, ID 를 그대로 넣었으면 그대로 쓴다."""
    match = SHEET_ID_RE.search(value)
    return match.group(1) if match else value.strip()


@dataclass
class Sheet:
    """열린 워크시트 + 헤더 이름으로 찾은 컬럼 위치 (1-based)."""

    worksheet: gspread.Worksheet
    columns: dict[str, int]
    header_row: int
    header: list[str]

    @property
    def first_data_row(self) -> int:
        return self.header_row + 1

    def letter(self, key: str) -> str:
        return gspread.utils.rowcol_to_a1(1, self.columns[key]).rstrip("1")

    def row_url(self, row_number: int) -> str:
        """해당 행으로 바로 열리는 링크. 슬랙 카드에서 시트로 넘어갈 때 쓴다."""
        spreadsheet = self.worksheet.spreadsheet
        return f"{spreadsheet.url}#gid={self.worksheet.id}&range=A{row_number}"

    def read(self, keys: tuple[str, ...]) -> list[dict[str, str]]:
        """지정한 컬럼만 읽어 행 순서대로 돌려준다. 행 번호는 `_row` 에 담는다.

        컬럼별로 범위를 나눠 요청하므로 개인정보 컬럼은 응답에 포함되지 않는다.
        열 단위 범위는 뒤쪽 빈 행이 잘려 오므로 길이를 맞춰 정렬을 유지한다.
        """
        start = self.first_data_row
        ranges = [f"{self.letter(key)}{start}:{self.letter(key)}" for key in keys]
        fetched = self.worksheet.batch_get(ranges)

        columns: dict[str, list[str]] = {}
        for key, values in zip(keys, fetched):
            columns[key] = [cells[0].strip() if cells else "" for cells in values]

        height = max((len(values) for values in columns.values()), default=0)
        rows = []
        for index in range(height):
            row = {"_row": str(start + index)}
            for key in keys:
                values = columns[key]
                row[key] = values[index] if index < len(values) else ""
            rows.append(row)
        return rows

    def write(self, row_number: int, values: dict[str, str]) -> None:
        """한 행의 여러 셀을 한 번의 요청으로 쓴다."""
        payload = [
            {"range": f"{self.letter(key)}{row_number}", "values": [[value]]}
            for key, value in values.items()
        ]
        self.worksheet.batch_update(payload)


# 긴 글이 들어가는 열. 줄바꿈을 걸지 않으면 한 줄로 잘려 보인다.
WRAP_COLUMNS = ("question", "answer")


def apply_wrap(sheet: Sheet) -> None:
    """긴 답변·근거가 잘려 보이지 않도록 줄바꿈 + 행 높이 자동 조정을 건다.

    **줄바꿈만으로는 부족하다.** `WRAP` 은 셀 안에서 줄을 나누지만, 행 높이가 고정값으로
    지정돼 있으면 늘어나지 않아 여전히 잘려 보인다. xlsx 에서 변환된 시트는 행 높이가
    고정으로 박혀 있어 `autoResizeDimensions` 로 그 고정을 풀어야 한다 (2026-08-03 확인).
    한 번 풀어두면 이후 내용이 길어져도 자동으로 늘어난다.
    """
    worksheet = sheet.worksheet
    worksheet.batch_format(
        [
            {
                "range": f"{sheet.letter(key)}{sheet.first_data_row}:{sheet.letter(key)}",
                "format": {"wrapStrategy": "WRAP", "verticalAlignment": "TOP"},
            }
            for key in WRAP_COLUMNS
        ]
    )
    worksheet.spreadsheet.batch_update(
        {
            "requests": [
                {
                    "autoResizeDimensions": {
                        "dimensions": {
                            "sheetId": worksheet.id,
                            "dimension": "ROWS",
                            "startIndex": sheet.header_row,  # 0-based — 헤더 바로 다음 행
                            "endIndex": worksheet.row_count,
                        }
                    }
                }
            ]
        }
    )


def find_header(worksheet: gspread.Worksheet) -> tuple[int, list[str]]:
    """`질문` 컬럼이 있는 첫 행을 헤더로 본다 — extract.py 와 같은 기준.

    한 행씩 읽어 찾는 즉시 멈춘다. 상위 몇 행을 한 번에 가져오면 데이터 행의
    개인정보까지 딸려 오므로 그렇게 하지 않는다.
    """
    for row in range(1, HEADER_SEARCH_ROWS + 1):
        header = [cell.strip() for cell in worksheet.row_values(row)]
        if set(HEADERS["question"]) & set(header):
            return row, header
    raise SystemExit(
        f"상위 {HEADER_SEARCH_ROWS}행에서 헤더를 찾지 못했습니다.\n"
        f"질문 컬럼 이름이 {' / '.join(HEADERS['question'])} 중 하나여야 합니다."
    )


def open_sheet() -> Sheet:
    load_dotenv(PROJECT_ROOT / ".env")

    url = os.environ.get("SHEET_URL", "")
    credentials = os.environ.get("GOOGLE_CREDENTIALS", "")
    if not url:
        raise SystemExit("SHEET_URL 이 없습니다. 프로젝트 루트의 .env 를 확인하세요.")
    if not credentials:
        raise SystemExit("GOOGLE_CREDENTIALS 가 없습니다. 서비스 계정 JSON 경로를 .env 에 적으세요.")

    key_path = Path(credentials)
    if not key_path.is_absolute():
        key_path = PROJECT_ROOT / key_path
    if not key_path.is_file():
        raise SystemExit(f"서비스 계정 키 파일이 없습니다: {key_path}")

    client = gspread.service_account(filename=str(key_path))
    try:
        spreadsheet = client.open_by_key(spreadsheet_id(url))
    except gspread.exceptions.APIError as exc:
        raise SystemExit(
            f"시트를 열지 못했습니다: {exc}\n"
            f"서비스 계정({key_path.name})이 해당 시트에 편집자로 공유돼 있는지 확인하세요."
        ) from exc

    tab = os.environ.get("SHEET_TAB", "")
    worksheet = spreadsheet.worksheet(tab) if tab else spreadsheet.sheet1

    header_row, header = find_header(worksheet)
    columns: dict[str, int] = {}
    missing: list[str] = []
    for key, names in HEADERS.items():
        found = next((name for name in names if name in header), None)
        if found is None:
            missing.append(f"{key} ({' / '.join(names)})")
        else:
            columns[key] = header.index(found) + 1

    if missing:
        raise SystemExit(
            "시트에서 찾지 못한 컬럼이 있습니다:\n  - "
            + "\n  - ".join(missing)
            + f"\n\n헤더 행({header_row}행)의 실제 컬럼: {header}\n"
            "시트에 컬럼을 추가하거나 backend/sheets/client.py 의 HEADERS 별칭을 고치세요."
        )

    return Sheet(worksheet=worksheet, columns=columns, header_row=header_row, header=header)


def is_pending(row: dict[str, str]) -> bool:
    """아직 처리하지 않은 행인가 — 질문이 있고 상태가 비어 있으면 미처리다.

    과거 회차 시트의 상태값은 `답변완료` 뿐이었고 `대기` 는 쓰인 적이 없다. 질문 등록 시
    상태를 적는 관례가 없으므로 빈칸을 미처리로 본다 (2026-08-03 결정). 처리한 행은
    `검수대기` 가 되므로 이 조건에 다시 걸리지 않는다.
    """
    return bool(row["question"]) and not row["status"]


def question_of(row: dict[str, str]) -> str:
    """질문 본문을 마스킹해 돌려준다. 시트에서 읽은 질문은 항상 이 함수를 거친다."""
    return mask(row["question"])


def main() -> None:
    sheet = open_sheet()
    header = sheet.header

    print(f"시트   : {sheet.worksheet.spreadsheet.title} [{sheet.worksheet.title}]")
    print(f"헤더   : {sheet.header_row}행 {header}\n")

    for key in HEADERS:
        print(f"  {key:<9} → {sheet.letter(key)}열")

    pii = [name for name in header if name in PII_HEADERS]
    print(f"\n읽지 않는 개인정보 컬럼: {pii or '없음'}")

    rows = sheet.read(("status", "question"))
    pending = [row for row in rows if is_pending(row)]
    print(f"\n헤더 {sheet.header_row}행 / 데이터 {len(rows)}행 / 미처리(상태 빈칸) {len(pending)}행")

    apply_wrap(sheet)
    print(f"줄바꿈 서식 적용: {', '.join(sheet.letter(key) for key in WRAP_COLUMNS)}열")


if __name__ == "__main__":
    main()
