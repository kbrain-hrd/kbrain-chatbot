---
anchor_prefix: B-S04-M02
grade: blue
set_no: 4
set_title: 안내매뉴얼연락처
subject_no: 2
subject_title: 데이터분석
kind: answers
source: raw/blue/AI 챔피언 블루 인증평가 예제문제/4세트_안내매뉴얼연락처/2과목_데이터분석/답안지.pdf
extractor: both
extractors_agree: true
verified: false
---

> **미확정 정답지.** 두 추출기 결과는 일치하지만 아직 사람이 확인하지 않았습니다.
>
> 확정 후 프론트매터의 `verified` 를 `true` 로 바꾸고, 맞는 쪽만 남기세요.

## pypdfium2 추출

<!-- page 1 -->
[연습세트04·블루·2과목] 답안지 (연습 — 공개)
정답 산출: pandas로 공공시설_예약현황.csv + 시설유형_통계.csv를 시설유형 키로 merge, 라벨 =
노쇼여부=="노쇼" → 1, 이상치(예약대기일 < 0 또는 결측) 제거, train_test_split(test_size=0.2,
random_state=42, stratify=라벨).
단답형 정답 (90점)
문항 배점 정답 근거 요약
1 15 시설유형 두 CSV의 유일한 공통 컬럼
2 20 회의실 merge 후 시설유형별 노쇼율 1위 (약 68.77%)
3 15 1496 예약대기일 < 0 또는 결측 4행 제거 → 1500-4=1496
4 20 18 라벨1 예약의 예약대기일 평균 18.16일 → 반올림 18
5 20 158 테스트셋 300행, stratify=라벨로 노쇼율 약 52.6% 유지 → 라벨1 158행
제출파일 (10점) — 분석 노트북 1부 (.ipynb)
채점 항목 배점
2파일 merge (시설유형 키) 2
결측·이상치 처리 (예약대기일 < 0 또는 결측 제거) 2
차트 포함 (노쇼 분포·시설유형별 노쇼율 등) 3
4모델 비교 + F1 (LogisticRegression·DecisionTree·RandomForest·SVM 등) 3

## pdfplumber 추출

<!-- page 1 -->
[연습세트04·블루·2과목] 답안지 (연습 — 공개)
정답 산출: pandas로 공공시설_예약현황.csv + 시설유형_통계.csv를 시설유형 키로 merge, 라벨 =
노쇼여부=="노쇼" → 1, 이상치(예약대기일 < 0 또는 결측) 제거, train_test_split(test_size=0.2,
random_state=42, stratify=라벨).
단답형 정답 (90점)
문항 배점 정답 근거 요약
1 15 시설유형 두 CSV의 유일한 공통 컬럼
2 20 회의실 merge 후 시설유형별 노쇼율 1위 (약 68.77%)
3 15 1496 예약대기일 < 0 또는 결측 4행 제거 → 1500-4=1496
4 20 18 라벨1 예약의 예약대기일 평균 18.16일 → 반올림 18
5 20 158 테스트셋 300행, stratify=라벨로 노쇼율 약 52.6% 유지 → 라벨1 158행
제출파일 (10점) — 분석 노트북 1부 (.ipynb)
채점 항목 배점
2파일 merge (시설유형 키) 2
결측·이상치 처리 (예약대기일 < 0 또는 결측 제거) 2
차트 포함 (노쇼 분포·시설유형별 노쇼율 등) 3
4모델 비교 + F1 (LogisticRegression·DecisionTree·RandomForest·SVM 등) 3
