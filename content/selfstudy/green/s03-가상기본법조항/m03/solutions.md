---
anchor_prefix: G-S03-M03
grade: green
set_no: 3
set_title: 가상기본법조항
subject_no: 3
subject_title: 자동화
kind: solutions
source: raw/green/0707_AI 챔피언 그린 인증평가 예제문제/3세트_가상기본법조항/3과목_자동화/해설.pdf
extractor: pypdfium2
---

<!-- page 1 -->
[연습세트03·그린] 3과목 해설 — 자동화
가장 빠른 풀이 (생성AI 활용)
ChatGPT/Claude/v0/Lovable에 다음을 그대로 붙여넣고 시키면 30분 안에 완성:
첨부 조항데이터.json은 가상 행정정보 통합관리 기본법 15개 조항이 들어있는 배열이다.
각 항목은 {조, 제목, 본문}.
스타일은 시스템 폰트, 카드형, 헤더는 sticky.
→ 결과를 받아 첨부 조항데이터.json 을 같은 폴더에 두고 index.html 더블클릭 → 동작 확인 → Netlify 드
래그&드롭 배포 → URL 복사.
핵심 동작 점검 (응시자 셀프 체크)
# 확인할 것 OK 기준
1 로컬에서 index.html 열기 카드 15개 표시
2 "행정안전부장관" 검색 카드 7개
3 "공동활용" 검색
4 "기본계획" 검색 카드
5 빈 검색 (모두 지우기) 15 카드 복원
6 결과 수 표시 "결과 N건" 갱신
위 6개 동작하면 채점 (1)~(4) 만점 가능.
배포 (Netlify 무료)
1. https://app.netlify.com 가입
2. "Add new site" → "Deploy manually" → 소스 폴더 드래그&드롭
3. 발급된 URL을 제출물.md 에 붙여넣기
자주 막히는 지점
조항데이터.json 경로 — fetch('조항데이터.json') 사용 시 같은 폴더 필수
한글 인코딩 — <meta charset="utf-8"> 필수
요구사항:
1. 페이지 로드 시 모든 조항을 카드 형태로 렌더링
2. 상단 검색창에 키워드 입력 시, 본문에 키워드가 포함된 카드만 표시
3. 화면 어딘가에 "결과 N건"이 보이도록
4. HTML/CSS/JS 한 파일씩, 외부 라이브러리 없이 카드 8개
1개

<!-- page 2 -->
이벤트 바인딩 — q.addEventListener('input', ...)
JSON 파싱 — .then().json() 체인
제출 가이드
## 1. 배포 URL
https://my-virtual-law-search.netlify.app
## 2. 사용 AI 도구
ChatGPT-4o
## 3. 구현 메모
- AI에게 위 프롬프트 그대로 줘서 한 번에 받은 코드 사용
- 한글 검색 안되는 문제는 charset utf-8 추가로 해결
- Netlify 드래그앤드롭으로 배포
