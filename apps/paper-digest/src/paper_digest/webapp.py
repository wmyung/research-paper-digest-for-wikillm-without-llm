from __future__ import annotations


def app_html(version: str) -> str:
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light">
  <title>WikiLLM Paper Digest</title>
  <style>
    :root {{ --ink:#112521; --muted:#5c6d68; --line:#d8e2de; --paper:#fbfcf8; --accent:#0a6b52; --accent2:#dff1e9; --warn:#8b4a08; --bad:#a32929; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; color:var(--ink); background:linear-gradient(135deg,#edf5f0 0,#fbfcf8 45%,#f5efe6 100%); font:15px/1.55 ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; min-height:100vh; }}
    main {{ max-width:920px; margin:0 auto; padding:52px 24px 72px; }}
    header {{ display:grid; grid-template-columns:1fr auto; gap:24px; align-items:start; margin-bottom:30px; }}
    .eyebrow {{ color:var(--accent); font-weight:750; letter-spacing:.12em; text-transform:uppercase; font-size:12px; }}
    h1 {{ font:700 clamp(34px,6vw,58px)/1.03 ui-serif,Georgia,serif; letter-spacing:-.035em; margin:10px 0 12px; max-width:720px; }}
    .lede {{ color:var(--muted); max-width:690px; font-size:17px; margin:0; }}
    .version {{ border:1px solid var(--line); border-radius:999px; padding:6px 11px; background:#fff9; color:var(--muted); white-space:nowrap; font-size:12px; }}
    .card {{ background:#fffffff0; border:1px solid var(--line); border-radius:20px; padding:24px; box-shadow:0 16px 50px #18342b12; }}
    .drop {{ border:1.5px dashed #9bb8ae; border-radius:15px; padding:35px 20px; text-align:center; cursor:pointer; background:var(--paper); transition:.15s; }}
    .drop.drag {{ border-color:var(--accent); background:var(--accent2); transform:translateY(-1px); }}
    .drop strong {{ display:block; font-size:18px; margin-bottom:5px; }}
    .drop small {{ color:var(--muted); }}
    input[type=file] {{ position:absolute; width:1px; height:1px; opacity:0; }}
    .files {{ margin:14px 0 0; padding:0; list-style:none; }}
    .files li {{ display:flex; gap:10px; justify-content:space-between; border-top:1px solid #edf1ef; padding:9px 2px; color:var(--muted); }}
    .files b {{ color:var(--ink); font-weight:650; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
    .options {{ display:grid; grid-template-columns:1fr 1fr; gap:12px 20px; margin:20px 0; }}
    label.opt {{ display:flex; align-items:flex-start; gap:9px; color:var(--muted); }}
    label.opt span {{ display:block; }} label.opt b {{ color:var(--ink); display:block; }}
    button {{ width:100%; border:0; border-radius:12px; padding:14px 18px; font:700 15px/1 inherit; cursor:pointer; background:var(--accent); color:white; }}
    button:hover {{ filter:brightness(.95); }} button:disabled {{ opacity:.5; cursor:wait; }}
    .privacy {{ margin:13px 2px 0; color:var(--muted); font-size:13px; }}
    .result {{ display:none; margin-top:18px; }}
    .result.show {{ display:block; }}
    .result-head {{ display:flex; align-items:center; justify-content:space-between; gap:14px; }}
    .badge {{ display:inline-flex; border-radius:999px; padding:6px 10px; font-weight:750; font-size:12px; background:var(--accent2); color:var(--accent); }}
    .badge.fail {{ background:#fff0e2; color:var(--warn); }}
    .score {{ font:700 27px/1 ui-serif,Georgia,serif; }}
    .errors {{ color:var(--bad); padding-left:20px; }}
    .downloads {{ display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-top:16px; }}
    .downloads button {{ background:#eef4f1; color:var(--ink); border:1px solid var(--line); }}
    footer {{ color:var(--muted); font-size:12px; margin-top:18px; }}
    @media (max-width:640px) {{ main{{padding:28px 14px 48px}} header{{grid-template-columns:1fr}} .version{{justify-self:start}} .card{{padding:16px}} .options,.downloads{{grid-template-columns:1fr}} }}
  </style>
</head>
<body>
<main>
  <header>
    <div>
      <div class="eyebrow">wikillm-digest-noLLM</div>
      <h1>WikiLLM Paper Digest</h1>
      <p class="lede">연구논문 PDF와 보충자료를 LLM 호출 없이 근거 추적 가능한 WikiLLM 소스 Markdown으로 변환합니다.</p>
    </div>
    <span class="version">v{version} · no LLM</span>
  </header>

  <section class="card" aria-labelledby="convert-heading">
    <h2 id="convert-heading" style="margin-top:0">로컬에서 변환</h2>
    <div id="drop" class="drop" role="button" tabindex="0" aria-controls="files">
      <strong>PDF를 놓거나 파일을 선택하세요</strong>
      <small>첫 PDF가 본문입니다. PDF, XLSX, DOCX, CSV, JSON, MD 등 보충자료를 함께 넣을 수 있습니다.</small>
    </div>
    <input id="files" type="file" multiple accept=".pdf,.xlsx,.xlsm,.docx,.csv,.tsv,.json,.md,.txt,.rst,.zip">
    <ul id="file-list" class="files" aria-live="polite"></ul>

    <div class="options">
      <label class="opt"><input id="doi-metadata" type="checkbox" checked><span><b>DOI 메타데이터 보완</b>공개 DOI만 Crossref에 조회</span></label>
      <label class="opt"><input type="checkbox" checked disabled><span><b>95점 품질 게이트</b>미달 결과를 성공으로 표시하지 않음</span></label>
    </div>
    <button id="convert" type="button">Markdown 만들기</button>
    <p class="privacy">파일과 논문 본문은 이 브라우저와 로컬 프로세스 사이에서만 처리됩니다. 결과는 서버에 보관되지 않습니다.</p>
  </section>

  <section id="result" class="card result" aria-live="polite">
    <div class="result-head">
      <div><span id="status" class="badge">처리 중</span><h2 id="message" style="margin:10px 0 0">품질 검증 중…</h2></div>
      <div id="score" class="score">—</div>
    </div>
    <ul id="errors" class="errors"></ul>
    <div id="downloads" class="downloads" hidden>
      <button id="download-md" type="button">Markdown 다운로드</button>
      <button id="download-qa" type="button">QA 보고서 다운로드</button>
    </div>
  </section>
  <footer>Deterministic extraction · grounded repair passes · OCR fallback · no generative model runtime</footer>
</main>
<script>
  const picker=document.querySelector('#files'), drop=document.querySelector('#drop'), list=document.querySelector('#file-list');
  const convert=document.querySelector('#convert'), result=document.querySelector('#result'), statusEl=document.querySelector('#status');
  const message=document.querySelector('#message'), score=document.querySelector('#score'), errors=document.querySelector('#errors');
  const downloads=document.querySelector('#downloads'); let payload=null;
  const human=n=>n<1024?n+' B':n<1048576?(n/1024).toFixed(1)+' KB':(n/1048576).toFixed(1)+' MB';
  function renderFiles(){{ list.innerHTML=''; [...picker.files].forEach((f,i)=>{{const li=document.createElement('li'),name=document.createElement('b'),size=document.createElement('span');name.textContent=String(i+1)+'. '+f.name;size.textContent=human(f.size);li.append(name,size);list.append(li);}}); }}
  function choose(){{picker.click()}} drop.addEventListener('click',choose); drop.addEventListener('keydown',e=>{{if(e.key==='Enter'||e.key===' ') choose()}}); picker.addEventListener('change',renderFiles);
  ['dragenter','dragover'].forEach(x=>drop.addEventListener(x,e=>{{e.preventDefault();drop.classList.add('drag')}}));
  ['dragleave','drop'].forEach(x=>drop.addEventListener(x,e=>{{e.preventDefault();drop.classList.remove('drag')}}));
  drop.addEventListener('drop',e=>{{picker.files=e.dataTransfer.files;renderFiles()}});
  function blobDownload(content,type,name){{const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([content],{{type}}));a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)}}
  document.querySelector('#download-md').onclick=()=>blobDownload(payload.markdown,'text/markdown;charset=utf-8',payload.filename);
  document.querySelector('#download-qa').onclick=()=>blobDownload(JSON.stringify(payload.qa,null,2),'application/json;charset=utf-8',payload.filename.replace(/\\.md$/,'.qa.json'));
  convert.addEventListener('click',async()=>{{
    if(!picker.files.length){{alert('먼저 본문 PDF를 선택하세요.');return}}
    convert.disabled=true; result.classList.add('show'); downloads.hidden=true; errors.innerHTML=''; statusEl.className='badge'; statusEl.textContent='처리 중'; message.textContent='추출·보완·품질 검증 중…'; score.textContent='—';
    const form=new FormData(); [...picker.files].forEach(f=>form.append('files',f,f.name)); form.append('options',JSON.stringify({{strict:true,profile:'auto',enable_doi_metadata:document.querySelector('#doi-metadata').checked}}));
    try {{
      const response=await fetch('/v1/digest',{{method:'POST',body:form}}); payload=await response.json();
      const ready=payload.status==='SOURCE_READY'; statusEl.textContent=payload.status||'ERROR'; statusEl.className='badge'+(ready?'':' fail');
      message.textContent=ready?'WikiLLM 소스 Markdown이 완성되었습니다.':'Markdown 후보는 완성되었지만 품질 게이트를 통과하지 못했습니다.';
      score.textContent=Math.round((payload.qa?.quality_score||0)*100)+'점';
      (payload.qa?.errors||[payload.detail].filter(Boolean)).forEach(x=>{{const li=document.createElement('li');li.textContent=x;errors.append(li)}});
      downloads.hidden=!payload.markdown;
    }} catch(err) {{statusEl.textContent='ERROR';statusEl.className='badge fail';message.textContent='로컬 변환 요청을 완료하지 못했습니다.';const li=document.createElement('li');li.textContent=String(err);errors.replaceChildren(li)}}
    finally {{convert.disabled=false}}
  }});
</script>
</body>
</html>"""
