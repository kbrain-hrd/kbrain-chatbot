---
anchor_prefix: B-S03-M02
grade: blue
set_no: 3
set_title: 가상기본법조항
subject_no: 2
subject_title: 데이터분석
kind: solutions
source: raw/blue/AI 챔피언 블루 인증평가 예제문제/3세트_가상기본법조항/2과목_데이터분석/해설.pdf
extractor: pypdfium2
---

<!-- page 1 -->
[연습세트03·블루] 2과목 해설 (연습 — 공개)
전체 분석 코드
# 2과목 데이터분석 — 정답 산출 코드
import pandas as pd
from sklearn.model_selection import train_test_split
prog = pd.read_csv("자원봉사프로그램.csv")
master = pd.read_csv("모집분야_지표.csv")
# 1) 모집분야 키로 inner merge (문항1)
df = prog.merge(master, on="모집분야", how="inner")
# 2) 위도·경도 결측 행 제거 (문항2)
df = df.dropna(subset=["위도", "경도"])
print("문항2 정제 후 행수 =", len(df)) # 3213
# 3) 라벨: 모집대상에 "청소년" 포함 → 1
df["라벨"] = df["모집대상"].astype(str).str.contains("청소년").astype(int)
# 문항3: 사업수 30건 이상 분야 중 청소년 포함비율(=라벨 평균) 최고
g = df.groupby("모집분야")["라벨"].agg(["mean", "size"])
g = g[g["size"] >= 30].sort_values("mean", ascending=False)
print("문항3 =", g.index[0]) # 환경ㆍ생태계보호
# 문항4: 라벨=1 프로그램의 등록기관수 평균(반올림)
print("문항4 =", round(df.loc[df["라벨"]==1, "등록기관수"].mean())) # 486
# 문항5: 층화분할(test_size=0.2) 후 테스트셋 라벨1 수
ytr, yte = train_test_split(df["라벨"], test_size=0.2,
 random_state=42, stratify=df["라벨"])
print("문항5 =", int((yte == 1).sum())) # 245 (테스트셋 643행 중)
문항별 풀이
문
항
정답 핵심
1 모집분야 두 CSV의 공통 키
2 3213 inner merge 후 위도·경도 결측 행 제거
3 환경ㆍ생태계보
호
사업수 30건 이상 분야 중 청소년 포함 비율 최고(약 0.72; 마스터 청소년포함비율 기
준으로도 최고)

<!-- page 2 -->
문
항
정답 핵심
4 486 라벨=1 프로그램의 등록기관수 평균 ≈ 486.1
5 245 층화분할 후 테스트셋 643행 중 라벨=1 이 245행
주의 — 라벨은 모집대상 문자열에 "청소년"이 포함되는지로 정의합니다("성인 청소년"·"청소년"=1, "성인"=0).
정제 순서(merge → 위도·경도 결측 제거)를 지켜야 행수(3213)와 이후 값이 재현됩니다.
