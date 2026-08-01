---
anchor_prefix: B-S02-M02
grade: blue
set_no: 2
set_title: 자치행정협력사업
subject_no: 2
subject_title: 데이터분석
kind: solutions
source: raw/blue/AI 챔피언 블루 인증평가 예제문제/2세트_자치행정협력사업/2과목_데이터분석/해설.pdf
extractor: pypdfium2
---

<!-- page 1 -->
[연습세트02·블루·2과목] 해설 (연습 — 공개)
본 해설은 문제지에 명시된 데이터 처리 규칙(시도코드 zfill(2) → inner merge → 결측치 처리 → 이상치 제거
→ 라벨 생성 → train_test_split)을 그대로 적용한 결과입니다.
1. 데이터 적재 & 머지
자치행정사업.csv(250행)와 자치단체_마스터.csv(17행)를 시도코드 키로 inner merge. 시도코드는 한쪽이
정수, 한쪽이 문자열일 수 있어 .astype(str).str.zfill(2)로 2자리 통일 후 머지하면 250행 유지.
2. 문항별 정답 풀이
문항 정답 풀이
1 시도코드 두 파일의 공통 컬럼은 시도코드 1개. 답형식 한글 단답.
2 서울특별시 merge 직후(전처리 전) 시도명별 총사업비_억원 평균을 groupby+mean으로
산출. 서울특별시 약 166.8억원으로 17개 시도 중 1위.
3 240
두 핵심 컬럼(총사업비_억원·시민참여수)이 모두 결측인 행은 없고, 한쪽 결측은
각 컬럼 평균으로 대체 → 250행 유지. 총사업비_억원 > 200인 행 10건 제거 →
최종 240행.
4 99 전처리 후 시민참여수 중앙값 1133.5 기준 라벨 부여 시 라벨1=120건. 이들의
총사업비_억원 평균 99.1534 → 반올림 99.
5 24 test_size=0.2 → 테스트셋 48행. stratify=라벨이라 라벨1 비율 50% 그대로 유지
→ 라벨1 24행.
3. 정답 산출 코드

<!-- page 2 -->
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
biz = pd.read_csv("첨부/자치행정사업.csv")
mst = pd.read_csv("첨부/자치단체_마스터.csv")
# 시도코드 2자리 문자열 통일
biz["시도코드"] = biz["시도코드"].astype(str).str.zfill(2)
mst["시도코드"] = mst["시도코드"].astype(str).str.zfill(2)
# inner merge
m = pd.merge(biz, mst, on="시도코드", how="inner") # 250행
# 문2: 시도명별 총사업비 평균 1위
top = m.groupby("시도명")["총사업비_억원"].mean().idxmax() # 서울특별시
# 결측치 처리: 둘 다 결측 제거, 한쪽 결측은 평균 대체
both = m[["총사업비_억원","시민참여수"]].isna().all(axis=1)
m = m[~both].copy()
for c in ["총사업비_억원","시민참여수"]:
 m[c] = m[c].fillna(m[c].mean())
# 이상치: 총사업비_억원 > 200 제거
m = m[m["총사업비_억원"] <= 200] # 문3: 240
# 라벨 = 시민참여수 >= 중앙값
m["라벨"] = (m["시민참여수"] >= m["시민참여수"].median()).astype(int)
mean_label1 = m.loc[m["라벨"]==1, "총사업비_억원"].mean() # 문4: 99.15 → 99
# 학습/테스트 분할
X, y = m.drop(columns=["라벨"]), m["라벨"]
_, _, _, y_te = train_test_split(X, y, test_size=0.2,
 random_state=42, stratify=y)
print((y_te==1).sum()) # 문5: 24
4. 제출파일(지표.csv) 작성 요령
전처리 후 데이터에서 시도명별로 사업수·라벨1수를 집계하고, 사업수=0이면 라벨1수·비율을 0으로 채워
17개 시도 모두 포함. 라벨1비율 내림차순 정렬 후 UTF-8(BOM 권장)로 저장.
