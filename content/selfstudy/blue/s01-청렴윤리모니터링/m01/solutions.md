---
anchor_prefix: B-S01-M01
grade: blue
set_no: 1
set_title: 청렴윤리모니터링
subject_no: 1
subject_title: 생성형AI(콘텐츠)
kind: solutions
source: raw/blue/AI 챔피언 블루 인증평가 예제문제/1세트_청렴윤리모니터링/1과목_생성형AI(콘텐츠)/해설.pdf
extractor: pypdfium2
---

<!-- page 1 -->
[연습세트 01 · 블루] 1과목 해설 (연습 — 공개)
등급: 블루 — Python 스크립트를 직접 작성하는 것을 전제로 한 풀이 전략입니다.
추천 풀이 코드
# 1과목 콘텐츠 — 정답 산출 코드
import re, glob
from pathlib import Path
def parse(p):
 t = Path(p).read_text(encoding="utf-8")
 dept = re.search(r"부서:\s*([^|]+?)\s*\|", t).group(1).strip()
 date = re.search(r"발표일:\s*([\d-]+)", t).group(1).strip()
 body = re.sub(r"^<!--.*?-->\n*", "", t, count=1, flags=re.DOTALL)
 return {"dept": dept, "date": date, "body": body}
items = [parse(p) for p in files]
slot1 = len(set(it["dept"] for it in items)) # 2 담당 부서 종류 수
slot2 = max(items, key=lambda x: len(x["body"]))["dept"] # 공무원행동강령과
slot3 = sum(int(m) for it in items
 for m in re.findall(r"(\d+)억\s*원", it["body"])) # 76
slot4 = min(items, key=lambda x: x["date"])["dept"] # 공무원행동강령과 (발표일 최초)
slot5 = max(int(m) for it in items
 for m in re.findall(r"(\d+)개", it["body"])) # 243
print(slot1, slot2, slot3, slot4, slot5)
문항별 풀이
문
항
정답 풀이
1 2 5건의 담당 부서는 공무원행동강령과(3건)·공직자윤리과(2건) → 부서 종류는 2개
2 공무원행동강령
과
본문 글자 수 최다는 260510a(851자) → 그 파일의 부서
3 76 r"(\d+)억\s*원" 으로 추출. 260515에 "38억 원"이 2회 → 38+38=76 (findall 필
수)
4 공무원행동강령
과
발표일이 가장 빠른 파일은 260510a(2026-05-10) → 그 파일의 부서
5 243 260520b "243개 지방자치단체"가 (숫자)개 최댓값
files = sorted(glob.glob("첨부/자료묶음/보도자료/**/*.md", recursive=True))

<!-- page 2 -->
흔한 오답
문항 오답 원인
1 44 / 5 "청렴" 등장 횟수 합(44) 또는 파일 수(5)와 혼동 — 묻는 것은 부서 종류 수
3 38 findall 대신 search로 1회만 추출
4 260515 줄 수 최다 파일 코드와 혼동 — 현재는 발표일 최초 파일의 부서명
5 40 "40개 문항"을 최댓값으로 오판
