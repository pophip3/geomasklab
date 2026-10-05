/* Experiment management, verified version comparison and measurement ledger. */
function saveTextFile(name, value, type='application/json') {
 const url=URL.createObjectURL(new Blob([value],{type}));
 const a=document.createElement('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();
 setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function refreshWorkbench() {
 if(!state.session)return;
 const runs=state.session.runs||[],masks=runs.filter(r=>r.mask_url);
 $('experimentHeading').textContent=state.session.name;
 $('experimentNote').textContent=state.session.notes||'An image. A reproducible record.';
 $('overviewVersions').textContent=masks.length;
 $('overviewPending').textContent=masks.filter(r=>(r.semantic_review?.state||'pending')==='pending').length;
 $('compareResultsBtn').disabled=$('ledgerCompareBtn').disabled=masks.length<2;
 $('ledgerExportBtn').disabled=!runs.length;
 document.querySelector('.version-tag').textContent=state.status?.version||'Development build';
 if(!runs.length){$('ledgerTable').innerHTML='<p class="ledger-empty">Your results will appear here. Failed requests remain visible alongside completed versions.</p>';return;}
 const pct=value=>value==null?'—':(value*100).toFixed(2)+'%';
 $('ledgerTable').innerHTML=`<table><thead><tr><th>Version / target</th><th>Spatial scope</th><th>Foreground</th><th>Whole-image coverage</th><th>Within-region coverage</th><th>Valid-region coverage</th><th>Review / execution</th><th></th></tr></thead><tbody>${[...runs].reverse().map(r=>{
 const m=r.metrics||{},task=r.task||{};
 return `<tr class="${r.id===state.selected?.id?'selected-row':''}"><td><strong>V${r.version}</strong><span>${escape(task.target?targetLabel(r):r.status==='answered'?'Scene response':'Request')}</span></td><td>${escape(task.roi?'Rectangle ROI':sideNames[task.side]||'—')}</td><td>${m.pixel_area==null?'—':number(m.pixel_area)+' px'}</td><td>${pct(m.area_ratio)}<small>${m.total_pixels?number(m.total_pixels)+' px denominator':''}</small></td><td>${pct(m.scope_area_ratio)}<small>${m.scope_area_pixels!=null?number(m.scope_area_pixels)+' px denominator':''}</small></td><td>${pct(m.validity_measurements?.coverage_of_valid_region??(m.validity_measurements?null:m.scope_area_ratio))}<small>${m.validity_measurements?number(m.validity_measurements.valid_region_pixels)+' valid px · '+number(m.validity_measurements.excluded_region_pixels)+' excluded':m.pixel_area!=null?'All pixels declared valid':''}</small></td><td><span class="ledger-status ${r.status==='failed'?'is-failed':''}">${escape(runStateLabel(r)||r.status)}</span><small>${executionLabel(r)}</small></td><td>${r.mask_url?`<button class="text-button" data-run="${r.id}">Open ↗</button>`:'—'}</td></tr>`;
 }).join('')}</tbody></table>`;
}
const previousSelectRun=selectRun;
selectRun=async function(...args){await previousSelectRun(...args);refreshWorkbench();};
const previousShowSession=showSession;
showSession=async function(...args){await previousShowSession(...args);$('quickTarget').value=state.session.sample==='airport'?'aircraft':'building';refreshWorkbench();};
const previousRenderTrace=renderTrace;
renderTrace=function(...args){previousRenderTrace(...args);refreshWorkbench();};
const previousRenderReview=renderReview;
renderReview=function(...args){previousRenderReview(...args);refreshWorkbench();};
refreshWorkbench();

$('quickTaskForm').onsubmit=async e=>{
 e.preventDefault();if(state.busy)return;
 const scope=$('quickScope').value,target=$('quickTarget').value;
 if(scope==='roi'&&!state.roi)return toast('Draw a rectangle on the image first.');
 if(scope!=='roi'){state.roi=null;state.roiDraft=null;state.roiClear=true;updateRoiUI();draw();}
 const location=scope==='roi'?'the selected region':scope==='all'?'the whole image':`the ${scope} half`;
 $('quickRunBtn').disabled=true;
 try{await run(`Extract only ${targetNames[target].toLowerCase()} in ${location}.`);}
 finally{$('quickRunBtn').disabled=false;refreshWorkbench();}
};
$('ledgerExportBtn').onclick=()=>{if(state.session)download('/api/ledger/'+state.session.id);};
$('editExperimentBtn').onclick=()=>{
 if(state.busy||!state.session)return;
 const s=state.session;
 modal('Experiment details',`<p>Name this investigation and save research notes. Image pixels, result versions and evidence remain unchanged.</p><form id="experimentForm" class="review-form"><label for="experimentName">Experiment name</label><input id="experimentName" maxlength="120" required value="${escape(s.name)}"><label for="experimentNotes">Research notes</label><textarea id="experimentNotes" maxlength="4000" rows="4" placeholder="Describe the research question, settings to compare or observations.">${escape(s.notes||'')}</textarea><label class="pin-control"><input id="experimentPinned" type="checkbox" ${s.pinned?'checked':''}> Pin in the experiment library</label><button class="primary" type="submit" id="saveExperiment">Save details</button></form>`,'EXPERIMENT DETAILS');
 $('experimentForm').onsubmit=async e=>{
  e.preventDefault();$('saveExperiment').disabled=true;
  try{const updated=await api('/api/session/update',{session_id:s.id,name:$('experimentName').value,notes:$('experimentNotes').value,pinned:$('experimentPinned').checked});
   if(state.session.id===s.id){Object.assign(state.session,updated);$('imageName').textContent=updated.name;refreshWorkbench();}
   closeModal();toast('Experiment details saved.');
  }catch(error){toast(error.message);if($('saveExperiment'))$('saveExperiment').disabled=false;}
 };
};

async function experimentLibrary(){
 if(state.busy)return toast('Wait for the current task to finish.');
 try{
  const data=await api('/api/sessions');
  modal('Experiment library',`<p>Return to a saved investigation. Names and notes are searchable; pinned experiments appear first.</p><div class="library-tools"><label class="sr-only" for="librarySearch">Search experiments</label><input id="librarySearch" type="search" placeholder="Search names and research notes…"><select id="libraryFilter" aria-label="Filter experiments"><option value="all">All experiments</option><option value="pinned">Pinned</option><option value="pending">Awaiting review</option></select></div><div id="experimentCards" class="experiment-cards"></div>`,'SAVED INVESTIGATIONS');
  const render=()=>{
   const term=$('librarySearch').value.trim().toLowerCase(),filter=$('libraryFilter').value;
   const list=data.sessions.filter(s=>(s.name+' '+(s.notes||'')).toLowerCase().includes(term)&&(filter==='all'||filter==='pinned'&&s.pinned||filter==='pending'&&s.pending_count>0)).sort((a,b)=>Number(b.pinned)-Number(a.pinned));
   $('experimentCards').innerHTML=list.map(s=>`<button class="experiment-card" data-session="${escape(s.id)}"><img src="/experiments/${s.id}/original.png" alt="${escape(s.name)}"><div><small>${s.pinned?'PINNED · ':''}${s.width} × ${s.height} px</small><strong>${escape(s.name)}</strong><p>${escape(s.notes||'No research notes yet.')}</p><span>${s.mask_count} mask versions · ${s.pending_count} pending review</span></div><b>↗</b></button>`).join('')||'<p class="ledger-empty">No matching experiments. Try another search or filter.</p>';
  };
  $('librarySearch').oninput=render;$('libraryFilter').onchange=render;render();
 }catch(error){toast(error.message);}
}
$('historyBtn').textContent='Experiments';$('historyBtn').onclick=experimentLibrary;
$('libraryBtn').onclick=experimentLibrary;
$('guideBtn').onclick=()=>modal('From image to evidence',`<p>A short illustrated guide to the workbench. This schematic is not a model prediction or a measurement.</p><div class="guide-visual"><svg viewBox="0 0 600 230" role="img" aria-label="Animated workflow schematic: image structures, a green overlay, and an exported evidence record"><rect x="8" y="8" width="365" height="212" rx="7" fill="#344d57"/><path d="M8 126H373M187 8V220" stroke="#213843" stroke-width="28"/><g fill="#84949c"><rect x="40" y="37" width="70" height="54" rx="3"/><rect x="239" y="34" width="88" height="55" rx="3"/><rect x="56" y="156" width="72" height="36" rx="3"/><rect x="243" y="155" width="57" height="38" rx="3"/></g><g class="guide-masks" fill="#73d5ac" fill-opacity=".65" stroke="#95efc3" stroke-width="2"><rect x="40" y="37" width="70" height="54" rx="3"/><rect x="239" y="34" width="88" height="55" rx="3"/><rect x="56" y="156" width="72" height="36" rx="3"/><rect x="243" y="155" width="57" height="38" rx="3"/></g><rect class="guide-scan" x="10" y="15" width="3" height="198" fill="#90eed1"/><path d="M398 112H433m-9-7 9 7-9 7" stroke="#8fbbb5" stroke-width="2" fill="none"/><g class="guide-export"><rect x="455" y="37" width="124" height="155" rx="7" fill="#e5f2ef"/><path d="M475 62H540M475 105H553M475 125H553M475 145H529" stroke="#86b5a6" stroke-width="5"/><path d="m532 166 9 9 18-20" stroke="#287b5d" stroke-width="3" fill="none"/></g></svg><span>ILLUSTRATIVE WORKFLOW · NO MODEL INFERENCE</span></div><div class="guide-steps"><div><strong>01 / Segment</strong><p>Choose an image, a target and a spatial scope. Procedural examples are available offline.</p></div><div><strong>02 / Inspect</strong><p>Switch image layers, review boundaries and compare saved versions in their common region.</p></div><div><strong>03 / Preserve</strong><p>Record a review decision, export verified evidence and save measurements to a CSV table.</p></div></div><div class="modal-notice">Mask agreement and integrity checks do not establish semantic accuracy. Review the output against independent reference labels when measuring model performance.</div>`,'WORKFLOW GUIDE');

async function compareResultsDialog(){
 if(state.busy||!state.session)return;
 const runs=state.session.runs.filter(r=>r.mask_url),sessionId=state.session.id;
 if(runs.length<2)return toast('Create two mask versions before comparing.');
 const options=runs.map(r=>`<option value="${r.id}">V${r.version} · ${escape(targetLabel(r))} · ${escape(r.task.roi?'Rectangle ROI':sideNames[r.task.side])}</option>`).join('');
 modal('Compare result versions',`<p>Compare two verified masks of the same image and semantic target. Agreement is measured inside the intersection of their selected valid domains.</p><form id="comparisonForm" class="comparison-form"><label>Version A<select id="comparisonA">${options}</select></label><label>Version B<select id="comparisonB">${options}</select></label><button id="runComparison" class="primary" type="submit">Compare masks</button></form><div id="comparisonOutput"><div class="comparison-empty">Choose two versions to inspect where foreground is shared or changes.</div></div>`,'RESULT INVESTIGATION');
 $('modal').classList.add('wide-dialog');
 $('comparisonA').value=runs[0].id;$('comparisonB').value=state.selected?.id===runs[0].id?runs.at(-1).id:state.selected?.id||runs.at(-1).id;
 $('comparisonForm').onsubmit=async e=>{
  e.preventDefault();const form=e.currentTarget;$('runComparison').disabled=true;
  $('comparisonOutput').innerHTML='<div class="comparison-empty" role="status">Verifying saved masks…</div>';
  try{
   const result=await api('/api/compare-results',{session_id:sessionId,run_a:$('comparisonA').value,run_b:$('comparisonB').value});
   if($('comparisonForm')!==form)return;
   const ratio=result.mask_agreement_iou==null?'Undefined':(result.mask_agreement_iou*100).toFixed(2)+'%';
   $('comparisonOutput').innerHTML=`<div class="comparison-summary"><div><small>COMMON VALID DOMAIN</small><strong>${number(result.common_scope_pixels)} <span>px</span></strong></div><div><small>CHANGED FOREGROUND</small><strong>${number(result.changed_pixels)} <span>px</span></strong></div><div><small>MASK AGREEMENT IoU</small><strong>${ratio}</strong></div></div>${result.pixel_diff_available?`<div class="comparison-visual"><img src="data:image/png;base64,${result.difference_png_base64}" alt="Version comparison in the common valid domain: blue removed, amber added, green shared foreground"></div>`:'<div class="comparison-empty" role="status">No common valid domain. Pixel comparison is unavailable.</div>'}<div class="comparison-legend"><span><i style="background:#4c83ff"></i>Removed (A only) · ${number(result.a_only_pixels)} px</span><span><i style="background:#f0ad4e"></i>Added (B only) · ${number(result.b_only_pixels)} px</span><span><i style="background:#45c5a1"></i>Common foreground · ${number(result.shared_foreground_pixels)} px</span></div><p class="comparison-explanation">${result.full_prediction_pixels_equal?'The full-image prediction pixels are identical. Different totals reflect scope or validity changes.':'The full-image prediction pixels differ. Inspect the selected masks and provenance.'} ${result.common_scope_pixels===0?'No common valid domain. Pixel differences and agreement are unavailable.':result.mask_agreement_iou==null?'Both masks contain no foreground in the shared region; agreement is undefined.':''}</p><div class="modal-notice">Mask agreement is not accuracy against ground truth. This comparison uses saved evidence and performs no inference.</div><div class="comparison-downloads"><button id="downloadComparison" class="secondary">Download comparison JSON ↓</button><button id="downloadDifference" class="secondary">Download difference image ↓</button></div>`;
   $('downloadComparison').onclick=()=>{const {difference_png_base64,...metadata}=result;saveTextFile('geomasklab-comparison.json',JSON.stringify(metadata,null,2));};
   $('downloadDifference').disabled=!result.pixel_diff_available;
   $('downloadDifference').onclick=()=>{const a=document.createElement('a');a.href='data:image/png;base64,'+result.difference_png_base64;a.download='geomasklab-version-difference.png';a.click();};
  }catch(error){if($('comparisonForm')===form){$('comparisonOutput').innerHTML='<div class="comparison-empty" role="alert">'+escape(error.message)+'</div>';toast(error.message);}}
  finally{if($('comparisonForm')===form)$('runComparison').disabled=false;}
 };
}
$('compareResultsBtn').onclick=$('ledgerCompareBtn').onclick=compareResultsDialog;
$('modal').addEventListener('close',()=>$('modal').classList.remove('wide-dialog'));
$('guideBtn').addEventListener('click',()=>{
 $('modalBody').insertAdjacentHTML('beforeend','<div class="guide-controls"><button class="secondary" id="pauseGuide" aria-pressed="false">Pause animation</button><a href="/help.html">Read the offline user guide ↗</a></div>');
 $('pauseGuide').onclick=()=>{const paused=$('modalBody').querySelector('.guide-visual').classList.toggle('is-paused');$('pauseGuide').textContent=paused?'Resume animation':'Pause animation';$('pauseGuide').setAttribute('aria-pressed',String(paused));};
});
