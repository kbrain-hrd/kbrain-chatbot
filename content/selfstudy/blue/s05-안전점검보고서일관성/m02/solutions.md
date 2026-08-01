---
anchor_prefix: B-S05-M02
grade: blue
set_no: 5
set_title: 안전점검보고서일관성
subject_no: 2
subject_title: 데이터분석
kind: solutions
source: raw/blue/AI 챔피언 블루 인증평가 예제문제/5세트_안전점검보고서일관성/2과목_데이터분석/해설.pdf
extractor: pypdfium2
---

<!-- page 1 -->
[연습세트05·블루] 2과목 해설 — 데이터분석
# 2과목 데이터분석 — 정답 산출 코드 (pandas + sklearn)
import pandas as pd
from sklearn.model_selection import train_test_split
main = pd.read_csv("승강기_중대한고장_샘플.csv", encoding="utf-8-sig")
master = pd.read_csv("시도_고장지표.csv", encoding="utf-8-sig")
# 1단계: 주소 분리
main["시도"] = main["주소"].str.split().str[0]
main["시군구"] = main["주소"].str.split().str[1]
# 3단계: 시도 키로 inner join → 문항 1, 2
df = main.merge(master, on="시도", how="inner")
print("문항1 결합 키 =", "시도")
print("문항2 결합 행수 =", len(df)) # 3000
# 2단계: 라벨(최근_여부) 생성
df["연도"] = df["고장발생일"].str[:4].astype(int)
df["최근_여부"] = (df["연도"] >= 2020).astype(int)
# 문항3: 30건 이상 시도 중 최근 비율 최고
g = df.groupby("시도")["최근_여부"].agg(["mean", "size"])
g = g[g["size"] >= 30].sort_values("mean", ascending=False)
print("문항3 =", g.index[0]) # 세종특별자치시 (0.934)
# 문항4: 최근_여부=1 행의 건물명 글자 수 평균(반올림)
m = df.loc[df["최근_여부"] == 1, "건물명"].str.len().mean()
print("문항4 =", round(m)) # 9 (평균 ≈ 8.51)
# 문항5: 층화분할 후 테스트셋의 최근_여부=1 행 수
ytr, yte = train_test_split(df["최근_여부"], test_size=0.2,
 random_state=42, stratify=df["최근_여부"])
print("문항5 =", int((yte == 1).sum())) # 472 (테스트셋 600행 중)
문항별 풀이
문항 정답 근거
1 시도 메인의 주소 첫 단어(시도)와 마스터의 시도 컬럼이 매칭되는 결합 키
2 3000 메인 샘플 3,000건이 마스터의 시도와 모두 매칭 → inner join 후에도 3,000행
3 세종특별자치시 행 수 30건 이상 시도 중 최근 고장 비율 최고(약 0.934)
4 9 최근_여부=1 행의 건물명 글자 수 평균 ≈ 8.51 → 반올림 9

<!-- page 2 -->
문항 정답 근거
5 472 층화분할(test_size=0.2) 결과 테스트셋 600행 중 최근_여부=1 이 472행
제출물 참고 — 4모델 F1 비교
제출물용 4개 모델은 학습/예측 후 f1_score(average="macro") 로 비교합니다. 연습 세트는 신호가 약해 F1이
낮게 나오는 것이 정상입니다(학습용).
알고리즘 F1(macro) 예시
RandomForest 0.47
LogisticRegression 0.44
LinearSVC 0.44
GradientBoosting 0.44
자주 막히는 지점
· 약식·정식 시도명 혼재("전남" vs "전라남도") — 마스터에 둘 다 들어 있어 매칭은 됩니다.
· 문항 5는 단답이 모델 성능이 아니라 테스트셋의 라벨 1 행 수(472)임에 주의.
· 건물명 결측은 없으며, 문항 4는 전체 최근 고장 행의 건물명 길이로 계산합니다.
