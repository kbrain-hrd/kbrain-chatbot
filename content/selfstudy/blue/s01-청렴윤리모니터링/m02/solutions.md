---
anchor_prefix: B-S01-M02
grade: blue
set_no: 1
set_title: 청렴윤리모니터링
subject_no: 2
subject_title: 데이터분석
kind: solutions
source: raw/blue/AI 챔피언 블루 인증평가 예제문제/1세트_청렴윤리모니터링/2과목_데이터분석/해설.pdf
extractor: pypdfium2
---

<!-- page 1 -->
[연습세트 01 · 블루] 2과목 해설 (연습 — 공개)
등급: 블루 — Python으로 직접 분석하는 것을 전제로 한 풀이입니다.
전체 분석 코드
# 2과목 데이터분석 — 정답 산출 코드
import pandas as pd, numpy as np
from sklearn.model_selection import train_test_split
df1 = pd.read_csv("첨부/청렴지수_현황.csv", encoding="utf-8-sig")
df2 = pd.read_csv("첨부/부패신고_현황.csv", encoding="utf-8-sig")
# 1) merge (문항1: 기관코드)
merged = pd.merge(df1, df2, on="기관코드", how="inner")
# 2~3) 결측 + IQR 이상치 (문항3: 141)
clean = merged.dropna()
def iqr_filter(df, col):
 q1, q3 = df[col].quantile([0.25, 0.75]); iqr = q3 - q1
 return df[(df[col] >= q1-1.5*iqr) & (df[col] <= q3+1.5*iqr)]
clean = iqr_filter(clean, "설문인원")
clean = iqr_filter(clean, "평균처리일수").copy()
print("문항3 행수 =", len(clean)) # 141
# 문항2: 기관유형별 평균 청렴지수 최고
print("문항2 =", clean.groupby("기관유형")["청렴지수"].mean().idxmax()) # 광역지자체
# 4) 라벨 생성 (시드 251)
rng = np.random.default_rng(251)
risk = (-0.45*clean["청렴지수"] + 0.08*clean["신고건수"]
 - 0.012*clean["처리율"] + 0.04*clean["평균처리일수"])
risk_n = (risk - risk.mean()) / risk.std()
clean["부패위험"] = ((risk_n + rng.normal(0, 0.5, len(clean))) > 0.1).astype(int)
# 문항4: 라벨1 기관의 청렴지수 평균(반올림)
print("문항4 =", round(clean.loc[clean["부패위험"]==1, "청렴지수"].mean())) # 7 (≈7.21)
# 문항5: 층화분할(test_size=0.2) 후 테스트셋 라벨1 수
ytr, yte = train_test_split(clean["부패위험"], test_size=0.2,
 random_state=42, stratify=clean["부패위험"])
print("문항5 =", int((yte == 1).sum())) # 13 (테스트셋 29행 중)

<!-- page 2 -->
문항별 풀이
문항 정답 핵심
1 기관코드 두 파일의 유일한 공통 컬럼 (set(df1.columns) & set(df2.columns))
2 광역지자체 dropna → IQR 후 groupby("기관유형")["청렴지수"].mean() 최고
3 141 merge → dropna → IQR(설문인원) → IQR(평균처리일수) 순서
4 7 라벨=1 기관 청렴지수 평균 ≈ 7.21 → 7
5 13 층화분할 후 테스트셋 29행 중 라벨=1 이 13행
주의
· 라벨 부패위험은 CSV에 없으며, 위 수식+시드(251)로 직접 생성해야 합니다. 정제 순서가 다르면 noise 정렬이
달라져 문항 4·5 값이 바뀝니다.
· 문항 5는 모델 성능이 아니라 테스트셋의 라벨 1 행 수(13)입니다. (test_size=0.2 — 0.25 아님)
· 흔한 오답: 문항3 175(정제 생략), 문항4 모델명·F1(옛 문제), 문항5 max_depth 값(옛 문제).
