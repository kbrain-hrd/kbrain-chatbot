---
anchor_prefix: B-S03-M01
grade: blue
set_no: 3
set_title: 가상기본법조항
subject_no: 1
subject_title: 생성형AI(콘텐츠)
kind: solutions
source: raw/blue/AI 챔피언 블루 인증평가 예제문제/3세트_가상기본법조항/1과목_생성형AI(콘텐츠)/해설.pdf
extractor: pypdfium2
---

<!-- page 1 -->
[연습세트03·블루] 해설 (연습 — 공개)
풀이
# 1과목 콘텐츠 — 정답 산출 코드
import re
from collections import Counter
from pathlib import Path
body = re.sub(r"^<!--.*?-->\n*", "", text, count=1, flags=re.DOTALL)
# 문항1~3: 외부 법령 「...법/법률」 인용
refs = re.findall(r"「([^」]+?(?:법|법률))」", body)
c = Counter(refs)
slot1 = len(c) # 6 (법령 종류 수)
slot2, slot3 = c.most_common(1)[0] # 개인정보 보호법, 3
# 조 (번호, 제목)
arts = [(int(n), t) for n, t in re.findall(r"제(\d+)조\(([^)]+)\)", body)]
bonchik = [(n, t) for n, t in arts if n <= 14] # 본칙 제1~14조
# 문항4: 조 제목에 "기본계획" 또는 "시행계획"
slot4 = sum(1 for n, t in bonchik if ("기본계획" in t or "시행계획" in t)) # 2
# 문항5: 과태료를 정한 본칙 조
slot5 = "제" + str(next(n for n, t in bonchik if "과태료" in t)) + "조" # 제14조
print(slot1, slot2, slot3, slot4, slot5)
문항별 풀이
문
항
정답 근거
1 6 「」 안 외부 법령 종류: 개인정보 보호법·공공기록물 관리에 관한 법률·전자정부법·정보통
신망 이용촉진 및 정보보호 등에 관한 법률·공공데이터의 제공 및 이용 활성화에 관한 법률·지
능정보화 기본법
2 개인정
보 보호
법
제3·9·10조에서 3회 인용 — 최빈
3 3 "개인정보 보호법" 등장 횟수
4 2 제5조(기본계획의 수립)·제6조(시행계획의 수립) — 본칙 조 제목 기준
text = Path("첨부/본문/가상_행정정보통합관리법.md").read_text(encoding="utf-8")

<!-- page 2 -->
문
항
정답 근거
5 제14조 제14조(과태료) — 1천만원 이하 과태료 규정
주의 — 문항 5는 과태료를 정한 조 번호(제14조)를 묻습니다. 조 번호의 합(1+…+14=105) 같은 값과 혼동하지 마
세요.
