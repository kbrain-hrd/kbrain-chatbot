---
anchor_prefix: B-S05-M01
grade: blue
set_no: 5
set_title: 안전점검보고서일관성
subject_no: 1
subject_title: 생성형AI(콘텐츠)
kind: solutions
source: raw/blue/AI 챔피언 블루 인증평가 예제문제/5세트_안전점검보고서일관성/1과목_생성형AI(콘텐츠)/해설.pdf
extractor: pypdfium2
---

<!-- page 1 -->
[연습세트05·블루] 해설 (연습 — 공개)
# 1과목 콘텐츠 — 정답 산출 코드
import re
from pathlib import Path
# [본문] 5가지 사실 불일치 점검 → 문항 1, 2
body = Path("첨부/본문/2026_안전점검_보고서.md").read_text(encoding="utf-8")
facts = {
 "총점검건수": re.findall(r"(450|440)\s*건", body),
 "지적사항수": re.findall(r"(120|115)\s*건", body),
 "시정완료율": re.findall(r"(85|82)\s*%", body),
 "예산집행률": re.findall(r"(92|90)\s*%", body),
 "총괄책임자": re.findall(r"(권혁[수주])", body),
}
q1 = sum(1 for v in facts.values() if len(set(v)) >= 2) # 두 값 모두 등장한 사실 수
print("문항1 불일치 사실 수 =", q1) # 5
print("문항2 총점검건수 차이 =", abs(450 - 440)) # 10
# [참고1] 2025 백서 요약 → 문항 3, 4
ref1 = Path("첨부/참고/참고1_2025_안전점검_백서_요약.md").read_text(encoding="utf-8")
print("문항3 2025년 점검 시설 수 =", 412) # 412곳 (성과지표 표)
print("문항4 안전등급 단계 수 =", len("SABCDE")) # 6 (S·A·B·C·D·E)
# [참고4] 평가위 회의록 → 문항 5
ref4 = Path("첨부/참고/참고4_안전점검_평가위원회_회의록.md").read_text(encoding="utf-8")
print("문항5 노후시설 정밀점검 대상 =", 84) # 84곳 (안건 3)
문항별 풀이
문
항
정
답
근거
1 5 총점검건수·지적사항수·시정완료율·예산집행률·총괄책임자 5가지 모두 본문에 서로 다른 두 값
이 등장 → 불일치 5건
2 10 총점검건수가 450건과 440건 두 값으로 기록 → 차이 450 − 440 = 10
3 412 참고1 「II. 주요 성과 지표」 표의 2025년 점검 시설 수 412곳
4 6 참고1 「I. 개관」의 안전등급 S·A·B·C·D·E → 6단계
5 84 참고4 「안건 3. 노후 시설 정밀 점검 우선순위」의 정밀 점검 대상 84곳

<!-- page 2 -->
출제 의도 — 문항 1·2는 같은 문서 내부의 사실 불일치를 직접 세는 능력, 문항 3·4·5는 참고자료에서 정확한 수치
를 찾아 읽는 능력을 확인합니다. 본문 값(450·120·85·92·권혁수)과 참고자료 통계는 별개이므로 혼동하지 않도
록 주의합니다.
