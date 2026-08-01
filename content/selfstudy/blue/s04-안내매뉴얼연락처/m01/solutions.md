---
anchor_prefix: B-S04-M01
grade: blue
set_no: 4
set_title: 안내매뉴얼연락처
subject_no: 1
subject_title: 생성형AI(콘텐츠)
kind: solutions
source: raw/blue/AI 챔피언 블루 인증평가 예제문제/4세트_안내매뉴얼연락처/1과목_생성형AI(콘텐츠)/해설.pdf
extractor: pypdfium2
---

<!-- page 1 -->
[연습04·블루·1과목] 해설 (연습 — 공개)
0. 무엇을 하는 문제인가
우수사례집(12건)을 사례 단위로 구조화하여 교차 집계하고, 정책 브리핑 1부를 제작한다.
1. 단계별 코드 (Python)
import re
from collections import Counter
# 사례 블록 단위로 분리해 필드 추출
blocks = re.split(r"### 사례 \d+\.", body)[1:]
recs = [{
 "분야": re.search(r"캠페인분야: (\S+)", b).group(1),
 "인원": int(re.search(r"참여인원: (\d+)", b).group(1)),
 "표창": re.search(r"표창등급: (\S+)", b).group(1),
 "온라인": re.search(r"온라인진행: (\S)", b).group(1),
} for b in blocks]
문항 1 — 총 참여인원
sum(r["인원"] for r in recs) # 94300
문항 2 — 최다 표창등급
Counter(r["표창"] for r in recs).most_common(1)[0][0] # 시장표창
문항 3 — 생활안전 분야 평균 참여인원
safe = [r["인원"] for r in recs if r["분야"]=="생활안전"]
round(sum(safe)/len(safe)) # 11125
문항 4 — 온라인(O) 사례 참여인원 합
sum(r["인원"] for r in recs if r["온라인"]=="O") # 64500
body = open("첨부/사례집/생활안전_캠페인_사례집.md", encoding="utf-8").read()

<!-- page 2 -->
문항 5 — 분야별 참여인원 합 최대
fs = Counter()
for r in recs: fs[r["분야"]] += r["인원"]
fs.most_common(1)[0][0] # 생활안전
정답
94300 / 시장표창 / 11125 / 64500 / 생활안전
흔한 실수
사례 블록 단위로 파싱하지 않으면 분야-인원 매칭이 어긋남
문항 3 평균을 전체 사례로 계산 → '생활안전' 분야만 대상
