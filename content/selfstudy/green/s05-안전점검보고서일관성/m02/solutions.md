---
anchor_prefix: G-S05-M02
grade: green
set_no: 5
set_title: 안전점검보고서일관성
subject_no: 2
subject_title: 데이터분석
kind: solutions
source: raw/green/0707_AI 챔피언 그린 인증평가 예제문제/5세트_안전점검보고서일관성/2과목_데이터분석/해설.pdf
extractor: pypdfium2
---

<!-- page 1 -->
[연습세트05·그린] 2과목 해설 — 데이터분석
풀이 흐름 (Excel·노코드 가능)
import csv
from collections import Counter
with open("승강기_중대한고장_샘플.csv", encoding="utf-8-sig") as f:
 rows = list(csv.reader(f))
body = rows[1:]
clean = [r for r in body if r[0].strip() and r[2].strip()]
print(len(clean)) # 문항 1 = 3000
sido = lambda r: r[2].split()[0] if r[2].strip() else ""
print(len({sido(r) for r in clean if sido(r)})) # 문항 2 = 31
print(len({r[0][:4] for r in clean if r[0][:4].isdigit()})) # 문항 3 = 18
cnt = Counter(sido(r) for r in clean if sido(r))
print(cnt.most_common(1)[0][0]) # 문항 4 = "경기도"
print(sum(1 for r in clean if r[0][:4].isdigit() and int(r[0][:4]) >= 2020))
# 문항 5 = 2358
문항별 풀이 한 줄
문항 1 = 3000: 샘플 자체가 정제됨.
문항 2 = 31: 약식·정식 혼재. 정규화 시 17.
문항 3 = 18: 연도 unique.
문항 4 = 경기도: 최다.
문항 5 = 2358: 2020~2025 합.
자주 막히는 지점
샘플링 — 158k 원본 대신 시드 고정 3000 샘플 사용.
주소 파싱 — split[0]이 시도. 약식·정식 혼재.
연도 추출 — r[0][:4].isdigit() 검증.
