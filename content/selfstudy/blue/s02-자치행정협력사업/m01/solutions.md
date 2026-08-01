---
anchor_prefix: B-S02-M01
grade: blue
set_no: 2
set_title: 자치행정협력사업
subject_no: 1
subject_title: 생성형AI(콘텐츠)
kind: solutions
source: raw/blue/AI 챔피언 블루 인증평가 예제문제/2세트_자치행정협력사업/1과목_생성형AI(콘텐츠)/해설.pdf
extractor: pypdfium2
---

<!-- page 1 -->
[연습세트02·블루] 해설 (연습 — 공개)
풀이
import csv
 rows = list(csv.DictReader(f))
for r in rows:
 r["예산_억원"] = int(r["예산_억원"])
 r["협력지자체수"] = int(r["협력지자체수"])
top = max(rows, key=lambda r: r["예산_억원"])
slot1 = top["사업번호"] # L26-018
slot2 = top["분야"] # 협력거버넌스
slot3 = sum(1 for r in rows if r["협력지자체수"] >= 10) # 7
slot4 = len({r["담당부서"] for r in rows}) # 7
slot5 = sum(r["예산_억원"] for r in rows) # 2285
문항별 풀이
문항 풀이
1 CSV 예산 max → L26-018 (359억)
2 L26-018 분야 컬럼 → 협력거버넌스
3 협력지자체수 ≥ 10 필터 → 7건 (L26-004·006·008·009·011·012·019)
4 담당부서 set() → 7종
5 전체 예산 sum() → 2285억 (정수 합산, 오차 없음)
흔한 오답
오류 원인 예방
문항 1 오답 → 문항 2 연쇄 오답 문항 2 채점은 문항 1 정답 기준 문항 1 먼저 검증
문항 3·4 같은 계산으로 착각 답이 우연히 둘 다 7 각각 독립 계산 확인
문항 3을 6으로 답함 > 10 (초과) 적용 "이상" = >=
문항 4를 잘못 셈 중복 포함 set() 사용 필수
문항 5에 단위 포함 "2285억원" 입력 숫자만
with open("첨부/데이터/2026_자치행정사업.csv", encoding="utf-8-sig", newline="") as f:
