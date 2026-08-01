---
anchor_prefix: B-S04-M03
grade: blue
set_no: 4
set_title: 안내매뉴얼연락처
subject_no: 3
subject_title: 서비스구현(자동화)
kind: solutions
source: raw/blue/AI 챔피언 블루 인증평가 예제문제/4세트_안내매뉴얼연락처/3과목_서비스구현(자동화)/해설.pdf
extractor: pypdfium2
---

<!-- page 1 -->
[연습세트04·블루·3과목] 해설 (연습 — 공개)
본 과목은 두 가지 산출물(정적 페이지 + Python 자동화) 평가 과목입니다. 정답 단답값이 없고 산출물
동작·완성도로 채점되므로 본 해설은 작성 가이드를 제공합니다.
1. 산출물 ① 정적 페이지 작성 가이드
안내서비스.csv를 자바스크립트(또는 HTML 빌드 시점)로 카테고리별로 그룹화해 카드로 렌더링. 키워드
검색 input → 카테고리·문의기관 텍스트 매칭 후 결과 카드 표시 + "결과 N건" 텍스트. 첨부
이미지/카드뉴스1~4.png는 상대경로(예: ./이미지/카드뉴스1.png)로 <img> 태그 삽입(최소 3장).
Netlify·Vercel·v0 중 무료 호스팅을 골라 배포하고 URL을 배포_URL.txt에 한 줄로 기재.
2. 산출물 ② solution.py 구현 가이드
표준 라이브러리(csv·pathlib·collections)만으로 충분히 작성 가능. 안내서비스.csv를 한 번에 읽어
카테고리 컬럼 기준으로 dict 그룹핑 → 각 카테고리별 출력_카테고리별/<카테고리명>.csv (헤더 동일)
저장 → 카테고리별 건수와 대표 문의기관(Counter.most_common(1))을 결과_카테고리집계.csv로 저장.
콘솔에 분리 결과와 집계 완료를 [OK] 형식으로 출력.
3. 참고 구현 (solution.py 예시)

<!-- page 2 -->
from pathlib import Path
import csv
from collections import Counter, defaultdict
SRC = Path("안내서비스.csv")
OUT_DIR = Path("출력_카테고리별")
OUT_DIR.mkdir(exist_ok=True)
# 1) CSV 적재
with SRC.open(encoding="utf-8-sig", newline="") as f:
 rows = list(csv.DictReader(f))
# 2) 카테고리별로 행 분리
by_cat = defaultdict(list)
for r in rows:
 by_cat[r["카테고리"]].append(r)
# 3) 카테고리별 CSV 저장
for cat, items in by_cat.items():
 out = OUT_DIR / f"{cat}.csv"
 with out.open("w", encoding="utf-8-sig", newline="") as f:
 w = csv.DictWriter(f, fieldnames=items[0].keys())
 w.writeheader()
 w.writerows(items)
 print(f" · {cat} {len(items)}건")
# 4) 집계표 (카테고리별 건수 + 대표 문의기관)
with Path("결과_카테고리집계.csv").open("w", encoding="utf-8-sig", newline="") as f:
 w = csv.writer(f)
 w.writerow(["카테고리", "건수", "대표_문의기관"])
 for cat, items in sorted(by_cat.items(), key=lambda x: -len(x[1])):
 rep = Counter(r["문의기관"] for r in items).most_common(1)[0][0]
 w.writerow([cat, len(items), rep])
print(f"[OK] 안내서비스 {len(rows)}건 카테고리별 분리 → {OUT_DIR}/")
print(f"[OK] 집계표 → 결과_카테고리집계.csv")
4. 제출 체크리스트
□ 배포_URL.txt 한 줄 — 정적 페이지 공개 URL
□ solution.py — 표준 라이브러리만 사용, 실행 오류 없음
□ 결과_카테고리집계.csv — UTF-8(엑셀 호환), 헤더 + 카테고리별 1행
□ 제출물.md — 사용 AI 도구 + 구현 메모 3~5줄
