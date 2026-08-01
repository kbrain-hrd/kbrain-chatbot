---
anchor_prefix: G-S05-M01
grade: green
set_no: 5
set_title: 안전점검보고서일관성
subject_no: 1
subject_title: 콘텐츠
kind: solutions
source: raw/green/0707_AI 챔피언 그린 인증평가 예제문제/5세트_안전점검보고서일관성/1과목_콘텐츠/해설.pdf
extractor: pypdfium2
---

<!-- page 1 -->
[연습세트05·그린] 해설 (연습 — 공개)
보고서를 AI에 업로드 + 프롬프트:
"5가지 사실(총점검건수·지적사항수·시정완료율·예산집행률·총괄책임자)의 본문 보고값을 모두 추출해 표
로 정리. 각 사실의 unique 값 가짓수도 답해줘."
5사실 모두 unique=2 → 모순 5
본문 ## 1~5 = 5 (장 수)
5사실 모두 모순 → 문항 3 = 5
문항 4(총점검건수 unique) = 2, 문항 5(책임자 unique) = 2
