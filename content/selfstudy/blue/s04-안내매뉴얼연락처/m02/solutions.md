---
anchor_prefix: B-S04-M02
grade: blue
set_no: 4
set_title: 안내매뉴얼연락처
subject_no: 2
subject_title: 데이터분석
kind: solutions
source: raw/blue/AI 챔피언 블루 인증평가 예제문제/4세트_안내매뉴얼연락처/2과목_데이터분석/해설.pdf
extractor: pypdfium2
---

<!-- page 1 -->
[연습세트04·블루·2과목] 해설 (연습 — 공개)
본 해설은 문제지에 명시된 데이터 처리 규칙(시설유형 키 merge → 라벨 정의 → 예약대기일 이상치 제거 →
train_test_split)을 그대로 적용한 결과입니다.
1. 머지 & 라벨 정의
공공시설_예약현황.csv(1500행)와 시설유형_통계.csv(6개 시설유형)을 시설유형 키로 inner merge →
1500행 유지. 노쇼여부=='노쇼'를 라벨 1로, 그 외(이용완료·취소 등)를 0으로 정의.
2. 문항별 정답 풀이
문항 정답 풀이
1 시설유형 두 파일의 공통 컬럼은 시설유형 1개.
2 회의실 merge 후 시설유형별 노쇼율은 회의실 68.77% / 야외운동장 68.65% / 캠핑장
62.98% / 체육관 48.95% / 공연장 38.08% / 강당 27.63%. 1위는 회의실.
3 1496 예약대기일 < 0인 행 또는 결측 행 4개 제거 → 1500-4=1496행.
4 18 정제된 1496행 중 라벨1(노쇼) 예약의 예약대기일 평균 18.1614일 → 반올림 18(일).
5 158 test_size=0.2 → 테스트셋 300행. stratify=라벨로 라벨1 비율 약 52.6% 유지 →
158행.
3. 정답 산출 코드
import pandas as pd
from sklearn.model_selection import train_test_split
rsv = pd.read_csv("첨부/공공시설_예약현황.csv") # 1,500행
fac = pd.read_csv("첨부/시설유형_통계.csv") # 6개 유형
m = pd.merge(rsv, fac, on="시설유형", how="inner") # 시설유형 키 merge
m["라벨"] = (m["노쇼여부"] == "노쇼").astype(int)
# 문2: 시설유형별 노쇼율 1위
top = m.groupby("시설유형")["라벨"].mean().idxmax() # 회의실
# 이상치 처리: 예약대기일 < 0 또는 결측 제거
m = m[(m["예약대기일"] >= 0) & m["예약대기일"].notna()] # 1496행
# 문4: 라벨1 예약대기일 평균
mean_wait = m.loc[m["라벨"]==1, "예약대기일"].mean() # 18.16 → 18
# 문5: 테스트셋 라벨1 행수
X, y = m.drop(columns=["라벨"]), m["라벨"]
_, _, _, y_te = train_test_split(X, y, test_size=0.2,
 random_state=42, stratify=y)
print((y_te==1).sum()) # 158

<!-- page 2 -->
4. 제출 노트북(.ipynb) 작성 요령
한 노트북 파일에 ① 2파일 merge, ② 결측·이상치 처리, ③ 노쇼 분포·시설유형별 노쇼율 차트, ④ 4개
분류 모델(LogisticRegression·DecisionTree·RandomForest·SVM 등) F1 비교 + 결론을 모두 포함.
stratify=라벨 + random_state=42 + test_size=0.2 고정.
