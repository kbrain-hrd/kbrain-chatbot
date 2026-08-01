---
anchor_prefix: G-S02-M02
grade: green
set_no: 2
set_title: 자치행정협력사업
subject_no: 2
subject_title: 데이터분석
kind: solutions
source: raw/green/0707_AI 챔피언 그린 인증평가 예제문제/2세트_자치행정협력사업/2과목_데이터분석/해설.pdf
extractor: pypdfium2
---

<!-- page 1 -->
[연습세트02·그린] 2과목 해설 (연습 — 공개)
풀이 개요
가상 시·군·구 인구·세대 현황 CSV(100행)에서 데이터 행 수·1위 시군구·1위 시도·서울특별시 시군구 수·30만 이
상 시군구 수를 산출합니다.
전체 분석 코드
import csv
from collections import Counter
with open("첨부/가상_시군구_인구현황.csv", encoding="utf-8-sig") as f:
 rows = list(csv.DictReader(f))
# 1) 데이터 행 수 (문항 1: 100)
slot1 = len(rows)
# 2) 인구 1위 시군구 (문항 2: 노원구)
top = max(rows, key=lambda r: int(r["인구"]))
slot2 = top["시군구"]
# 3) 시군구 수가 가장 많은 시도 (문항 3: 경기도)
cnt = Counter(r["시도"] for r in rows)
slot3 = cnt.most_common(1)[0][0]
# 4) 서울특별시 시군구 수 (문항 4: 18)
slot4 = cnt.get("서울특별시", 0)
# 5) 인구 300,000 이상 시군구 수 (문항 5: 37)
slot5 = sum(1 for r in rows if int(r["인구"]) >= 300000)
문항별 정답·풀이
문항 정답 풀이 요약
1 100 헤더 제외 데이터 행 수. DictReader 길이
2 노원구 인구 최댓값 행의 시군구명
3 경기도 시도 빈도 1위 — Counter.most_common(1)
4 18 시도 == "서울특별시" 행 수
5 37 인구 >= 300000 조건 만족 행 수

<!-- page 2 -->
흔한 오답
문항 오답 원인
1 헤더 포함 101행으로 답함
2 시도 1위 (서울·경기)로 답함 — Q는 시군구 단위
4 "서울" 부분 일치 검색 → 다른 값
5 30만 정확 vs 30만 이상 경계 혼동 ( > vs >= )
제출파일 (10점) — 시도별_시군구수.csv
import csv
from collections import Counter
cnt = Counter(r["시도"] for r in rows)
items = sorted(cnt.items(), key=lambda x: -x[1])
with open("시도별_시군구수.csv", "w", encoding="utf-8-sig", newline="") as f:
 w = csv.writer(f); w.writerow(["시도","시군구수"]); w.writerows(items)
헤더: 시도, 시군구수 / 시도별 1행 / 시군구수 내림차순 / UTF-8-sig(BOM 포함)
