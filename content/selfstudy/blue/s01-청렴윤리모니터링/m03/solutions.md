---
anchor_prefix: B-S01-M03
grade: blue
set_no: 1
set_title: 청렴윤리모니터링
subject_no: 3
subject_title: 서비스구현(자동화)
kind: solutions
source: raw/blue/AI 챔피언 블루 인증평가 예제문제/1세트_청렴윤리모니터링/3과목_서비스구현(자동화)/해설.pdf
extractor: pypdfium2
---

<!-- page 1 -->
[연습세트 01 · 블루] 3과목 해설 (연습 — 공개)
채점자·제작자 전용. 자동화 과목은 단답 없음. 산출물 ① 정적 페이지 + 산출물 ② Python 도구를 직접 확인하여
채점.
산출물 ② Python 예시 코드
# solution.py — 산출물 ② 예시
import csv
from pathlib import Path
from collections import Counter
B = Path("첨부")
sin = list(csv.DictReader(open(B/"청렴신고_사건데이터.csv", encoding="utf-8-sig")))
edu = list(csv.DictReader(open(B/"청렴교육_현황.csv", encoding="utf-8-sig")))
총건수 = len(sin) # 500
유형별 = Counter(r["신고유형"] for r in sin)
이수율 = {}
for r in edu:
이수율평균 = {k: round(sum(v)/len(v), 1) for k, v in 이수율.items()}
with open("결과_요약.csv", "w", newline="", encoding="utf-8-sig") as f:
 w = csv.writer(f)
 w.writerow(["항목", "값"])
 w.writerow(["총사건", 총건수]); w.writerow(["처리완료", 처리완료]); w.writerow(["평균처리일", 평
균처리])
print(f"[OK] 신고 {총건수}건 분석 → 결과_요약.csv")
print(f" 총 사건: {총건수}건 / 처리 완료: {처리완료}건 / 평균 처리: {평균처리}일")
예상 출력 (첨부 데이터 기준)
항목 값
총 사건 500건
처리 완료 229건
평균 처리기간 52일
신고유형별 금품수수 145 · 직권남용 108 · 예산횡령 89 · 이해충돌 81 · 공금유용 60 · 기타 17
유효처리 = [int(r["처리기간_일"]) for r in sin if r["처리기간_일"]]
평균처리 = round(sum(유효처리) / len(유효처리)) # 결측 20 제외 → 52
    if r["교육이수율"]: 이수율.setdefault(r["기관유형"], []).append(float(r["교육이수율"]))
처리완료 = sum(1 for r in sin if r["처리상태"] == "처리완료") # 229

<!-- page 2 -->
항목 값
기관유형별 평균 이수율 중앙행정기관 79.8 · 공공기관 77.9 · 교육기관 77.1 · 지방자치단체 72.5
산출물 ① 정적 페이지 가이드
첨부 CSV를 JSON으로 변환 → 카드 렌더링 + 신고유형/처리상태 필터 + "결과 N건" 표시
정적 캡처로 대체 가능
Netlify·Vercel·v0 중 배포 후 URL을 배포_URL.txt 에 한 줄로 기록
채점 팁
· "처리 완료"는 처리상태 == "처리완료"만 카운트(229). 조사중·이첩·접수완료·기각 제외.
· 평균 처리기간은 전체 사건 처리기간_일 평균(≈51.7 → 52). AI가 처리완료 건만 평균 내면 값이 달라질 수 있으
니 정의 확인.
• 
•
• 
외부 리소스: 빌드 시 RSS 최신 5건을 정적 데이터로 저장하고, 페이지에는 RSS 출처 링크와 목록을 표시.
