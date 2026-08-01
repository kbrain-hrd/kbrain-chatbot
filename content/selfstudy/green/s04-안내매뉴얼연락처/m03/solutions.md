---
anchor_prefix: G-S04-M03
grade: green
set_no: 4
set_title: 안내매뉴얼연락처
subject_no: 3
subject_title: 자동화
kind: solutions
source: raw/green/0707_AI 챔피언 그린 인증평가 예제문제/4세트_안내매뉴얼연락처/3과목_자동화/해설.pdf
extractor: pypdfium2
---

<!-- page 1 -->
[연습04·그린·3과목] 해설 (연습 — 공개) — 웹 검색·필터 도구
풀이 흐름
ChatGPT/Claude/Replit에 첨부 JSON과 요구사항을 주고 단일 index.html 을 생성·정리.
프롬프트 예시
"첨부 안내서비스_목록.json (24건)을 fetch로 불러와 표로 보여주고, 서비스명 검색창 + 안내분야 드롭다운 + 표시 건수가 있는 단일 index.html을 순수 JS로
만들어줘."
핵심 골격
<input id="q" placeholder="서비스명 검색">
<select id="field"><option value="">전체</option></select>
<div id="count"></div><table id="list"></table>
<script>
let data=[];
fetch('안내서비스_목록.json').then(r=>r.json()).then(d=>{
 data=d; [...new Set(d.map(x=>x.안내분야))].forEach(f=>field.add(new Option(f,f))); render();
});
</script>
배포
Netlify Drop에 index.html + json 함께 업로드 → URL 제출.
흔한 오답
JSON 미동봉 배포로 목록 안 뜸 → 함께 배포
검색·분야필터 동시 적용 누락
function render(){
 const rows = data.filter(x => x.서비스명.includes(q.value) &&
 (!field.value || x.안내분야 === field.value));
 count.textContent = rows.length + '건';
 list.innerHTML = rows.map(x =>
 `<tr><td>${x.서비스명}</td><td>${x.안내분야}</td><td>${x.소관기관}</td><td>${x.온라인안내}</td><td>${x.콜센터}</td></tr>`
 ).join('');
}
q.oninput = field.onchange = render;
</script>
