---
anchor_prefix: B-S01-M02
grade: blue
set_no: 1
set_title: 청렴윤리모니터링
subject_no: 2
subject_title: 데이터분석
kind: answers
source: raw/blue/AI 챔피언 블루 인증평가 예제문제/1세트_청렴윤리모니터링/2과목_데이터분석/답안지.pdf
extractor: both
extractors_agree: true
verified: false
---

> **미확정 정답지.** 두 추출기 결과는 일치하지만 아직 사람이 확인하지 않았습니다.
>
> 확정 후 프론트매터의 `verified` 를 `true` 로 바꾸고, 맞는 쪽만 남기세요.

## pypdfium2 추출

<!-- page 1 -->
[연습세트 01 · 블루] 2과목 답안지 (연습 — 공개)
이 파일은 연습세트 공개용 정답지입니다.
단답형 정답 (90점)
문항 배점 정답 근거 요약
1 5 기관코드 두 파일의 유일한 공통 컬럼
2 15 광역지자체 전처리 후 평균 청렴지수 최고 유형 (≈8.06)
3 20 141 inner merge → dropna → IQR(설문인원·평균처리일수) 후
4 20 7 라벨=1 기관의 청렴지수 평균 ≈ 7.21 → 반올림 7
5 30 13 test_size=0.2 테스트셋 29행 중 라벨=1 이 13행
제출파일 채점 기준 (10점)
항목 배점
.docx 또는 .hwpx 파일 정상 열림 2
차트 5종 이상 포함 5
모델 비교 결과(알고리즘명 + F1) 표시 3
참고: 4모델 F1(macro, test_size=0.2)은 LogisticRegression·RandomForest·KNN ≈ 0.86,
DecisionTree ≈ 0.82 수준 (제출물 평가용, 단답 아님).

## pdfplumber 추출

<!-- page 1 -->
[연습세트 01 · 블루] 2과목 답안지 (연습 — 공개)
이 파일은 연습세트 공개용 정답지입니다.
단답형 정답 (90점)
문항 배점 정답 근거 요약
1 5 기관코드 두 파일의 유일한 공통 컬럼
2 15 광역지자체 전처리 후 평균 청렴지수 최고 유형 (≈8.06)
3 20 141 inner merge → dropna → IQR(설문인원·평균처리일수) 후
4 20 7 라벨=1 기관의 청렴지수 평균 ≈ 7.21 → 반올림 7
5 30 13 test_size=0.2 테스트셋 29행 중 라벨=1 이 13행
제출파일 채점 기준 (10점)
항목 배점
.docx 또는 .hwpx 파일 정상 열림 2
차트 5종 이상 포함 5
모델 비교 결과(알고리즘명 + F1) 표시 3
참고: 4모델 F1(macro, test_size=0.2)은 LogisticRegression·RandomForest·KNN ≈ 0.86,
DecisionTree ≈ 0.82 수준 (제출물 평가용, 단답 아님).
