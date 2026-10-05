const $ = id => document.getElementById(id);
const state = { session:null, selected:null, last:null, original:null, mask:null, mode:'demo', view:'original', zoom:1, busy:false, status:null, loadToken:0,
 roi:null,roiDraft:null,roiStart:null,roiDrawing:false,roiClear:false,batch:null };
const sideNames = {all:'Whole image',left:'Left half',right:'Right half',top:'Top half',bottom:'Bottom half'};
const qualityNames = {auto:'Automatic',fast:'Fast',accurate:'Tiled refinement'};
const targetNames = {building:'Buildings',aircraft:'Aircraft',road:'Roads',water:'Water',tree:'Vegetation',ship:'Ships'};
const targetLabel = run => (run?.task?.invert?'Non-':'')+(targetNames[run?.task?.target]||'Target').toLowerCase();
const statusNames = {completed:'Pending semantic review',answered:'Answered',needs_clarification:'Clarification needed',failed:'Failed',needs_review:'Review required',export_ready:'Ready to export'};
const reviewNames = {pending:'Pending review',accepted:'Accepted by reviewer',rejected:'Rejected by reviewer'};
const runStateLabel = r => r.mask_url?(reviewNames[r.semantic_review?.state]||statusNames[r.status]):statusNames[r.status];
const number = n => Number(n).toLocaleString('en-US');
const escape = s => String(s ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const icon = name => `<svg><use href="#i-${name}"/></svg>`;
const intro = $('chat').innerHTML;
let toastTimer;
function toast(text){$('toast').textContent=text;$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,3800);}
async function api(path,payload){const response=await fetch(path,payload?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}:{});const data=await response.json();if(!response.ok)throw new Error(data.error||'Request failed.');return data;}
function loadImage(url){return new Promise((resolve,reject)=>{const image=new Image();image.onload=()=>resolve(image);image.onerror=()=>reject(new Error('Could not load the image.'));image.src=url;});}
function modal(title,html,eyebrow='GEOMASKLAB'){$('modalTitle').textContent=title;$('modalEyebrow').textContent=eyebrow;$('modalBody').innerHTML=html;if(!$('modal').open)$('modal').showModal();}
function closeModal(){$('modal').close();}
$('closeModal').onclick=closeModal;
$('modal').addEventListener('click',e=>{if(e.target===$('modal')){const r=$('modal').getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)closeModal();}});

async function newExperiment(sample='urban',image=null,name=null){
 if(state.busy)return toast('Wait for the current task to finish.');
 state.busy=true;$('sendBtn').disabled=true;$('newBtn').disabled=true;
 try{
  const session=await api('/api/session',{sample,image,name});
  await showSession(session);
 }catch(e){toast(e.message);}finally{state.busy=false;$('sendBtn').disabled=false;$('newBtn').disabled=false;}
}

async function showSession(session){
  const original=await loadImage(session.image_url);
  state.loadToken++;Object.assign(state,{session,original,selected:null,last:null,mask:null,view:'original',zoom:1,roi:null,roiDraft:null,roiStart:null,roiDrawing:false,roiClear:false});
  // Restore the mode that actually produced this experiment when the user has
  // not explicitly saved a different preference.
  if(!session.imported_evidence&&session.runs.length&&!localStorage.getItem('geoscope-mode'))state.mode=session.runs.at(-1).mode;
  clearTimeout(toastTimer);$('toast').hidden=true;
  $('chat').innerHTML=intro;
  if(session.sample==='airport'){
   const btn=$('starterList').querySelectorAll('button')[1];btn.dataset.prompt='Extract aircraft in the right half and calculate coverage.';btn.querySelector('span').innerHTML='Extract right-half aircraft<small>Segmentation and pixel coverage</small>';
  }
  $('imageName').textContent=session.name;$('imageMeta').textContent=`RGB · ${session.width} × ${session.height} px · Pixel coordinates`;
  $('fileThumb').src=session.image_url;$('coordinateLabel').textContent=`${session.width} × ${session.height} px`;
  $('stageLabel').textContent=session.sample?'Example image / '+(session.sample==='urban'?'01':'02'):'Uploaded image';
  $('imageWatermark').textContent=session.sample?'SAMPLE IMAGE':'USER IMAGE';
  $('contextChip').hidden=true;$('versions').innerHTML='<span class="small-muted">Result versions appear here after segmentation.</span>';
  $('qualityMode').value='auto';updateRoiUI();
  $('trace').innerHTML='<div class="trace-placeholder">'+icon('target')+'<span>Each operation has a saved execution record.</span><small>Planning → Segmentation → Measurements → Verification</small></div>';
  $('runLabel').textContent='Awaiting a task';$('query').value='';updateMode();resetMetrics();draw();syncView();closeModal();
  localStorage.setItem('geoscope-session',session.id);
  if(session.runs.length){
   $('chat').innerHTML='';
   for(const r of session.runs){addMessage('user',r.query,'',null,r.created_at||null);addMessage('assistant',r.message,r.status==='failed'?'warning':'',r);}
   state.last=session.runs.at(-1);
   const remembered=localStorage.getItem('geoscope-selected-'+session.id);
   const selected=session.runs.find(r=>r.id===remembered&&r.mask_url)||[...session.runs].reverse().find(r=>r.mask_url);
   renderVersions();if(selected)await selectRun(selected);else{if(state.last.status==='answered')renderAnswer(state.last);renderTrace(state.last);}
  }
}
async function openExperiment(id){
 if(state.busy)return toast('Wait for the current task to finish.');
 state.busy=true;$('sendBtn').disabled=true;$('newBtn').disabled=true;
 try{await showSession(await api('/api/session/'+encodeURIComponent(id)));}
 catch(e){toast(e.message);}finally{state.busy=false;$('sendBtn').disabled=false;$('newBtn').disabled=false;}
}

function updateMode(){
 $('connectionLabel').textContent=state.mode==='demo'?'Demo mode':'Live mode';
 $('provenanceLabel').textContent=state.mode==='demo'?(state.session?.sample?'Synthetic example · Procedural mask':'Uploaded image · Model services required'):'Live mode · External model services';
 $('composerNote').textContent=state.mode==='demo'?'Offline demonstration · No model calls':'Live mode sends images to your configured model services.';
 if(state.session?.imported_evidence)$('provenanceLabel').textContent='Imported evidence · No inference during import';
 if(state.session?.imported_evidence&&state.mode==='demo')$('composerNote').textContent='Imported evidence supports offline review and region recalculation. New segmentation requests require model services.';
}

$('importBtn').onclick=()=>{if(state.busy)return toast('Wait for the current task to finish.');$('bundleInput').click();};
$('bundleInput').onchange=async e=>{
 const file=e.target.files[0];e.target.value='';if(!file)return;
 if(state.busy)return toast('Wait for the current task to finish.');
 if(file.size>12*1024*1024)return toast('Evidence bundles must be 12 MB or smaller.');
 state.busy=true;$('importBtn').disabled=true;$('sendBtn').disabled=true;$('newBtn').disabled=true;
 try{
  const bundle=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(new Error('Could not read the evidence bundle.'));reader.readAsDataURL(file);});
  await showSession(await api('/api/import',{bundle,name:file.name}));
  toast('Evidence verified and restored without inference. You can now review or recalculate a region.');
 }catch(error){modal('Evidence verification failed',`<p>${escape(error.message)}</p><p>The current experiment is preserved. Check the source bundle before importing it again.</p>`,'EVIDENCE HANDOFF');}
 finally{state.busy=false;$('importBtn').disabled=false;$('sendBtn').disabled=false;$('newBtn').disabled=false;}
};
function resetMetrics(){
 $('recalculateBtn').disabled=true;$('regionCoverage').textContent='—';
 $('reviewPanel').hidden=true;
 $('answerCard').hidden=true;$('coverageCard').hidden=false;$('metricsPanel').hidden=false;$('checksPanel').hidden=false;
 $('resultEyebrow').textContent='COVERAGE ANALYSIS';$('artifactText').textContent='Image · Mask · Overlay · Measurements · Logs';
 $('ratioValue').textContent='—';$('areaValue').innerHTML='— <small>px</small>';$('scopeValue').textContent='—';$('timeValue').textContent='—';$('candidateValue').textContent='—';$('qualityValue').textContent='—';
 $('totalValue').textContent=number(state.session?.width*state.session?.height||0);$('resultTitle').textContent='Awaiting segmentation';$('resultSubtitle').textContent='Run a task to see its results here.';
 $('resultStatus').textContent='Ready';$('resultStatus').className='result-badge';$('coverageBar').style.width='0%';$('ringValue').setAttribute('stroke-dasharray','0 164');
 $('checksList').innerHTML=['Mask matches the image dimensions','Spatial constraints checked','Measurements and artifacts saved'].map(s=>`<p class="pending"><span>○</span>${s}</p>`).join('');$('checkCount').textContent='0 / 3';$('exportBtn').disabled=true;$('reportBtn').disabled=true;
}
function renderAnswer(run){
 $('recalculateBtn').disabled=true;$('regionCoverage').textContent='—';
 $('reviewPanel').hidden=true;
 $('answerCard').hidden=false;$('coverageCard').hidden=true;$('metricsPanel').hidden=true;$('checksPanel').hidden=true;
 $('resultEyebrow').textContent='IMAGE UNDERSTANDING';$('resultTitle').textContent='Scene response received';
 $('resultSubtitle').textContent='Image response from RemoteAgent';$('answerText').textContent=run.message;
 $('resultStatus').textContent='Answered';$('resultStatus').className='result-badge success';
 $('artifactText').textContent='Image · Model response · Decision record · Logs';$('exportBtn').disabled=true;$('reportBtn').disabled=true;
}

function updateRoiUI(){
 const roi=state.roi?.xyxy;
 $('roiLabel').textContent=roi?`ROI: (${roi[0]}, ${roi[1]}) – (${roi[2]}, ${roi[3]}) px`:'No rectangle selected';
 $('drawRoiBtn').classList.toggle('selected',state.roiDrawing);
 $('drawRoiBtn').textContent=state.roiDrawing?'Drag on the image to draw an ROI':'Draw ROI';
 $('clearRoiBtn').disabled=!roi;
 $('imageCanvas').classList.toggle('roi-drawing',state.roiDrawing);
}
function imagePoint(event){
 const canvas=$('imageCanvas'),rect=canvas.getBoundingClientRect();
 return [Math.min(canvas.width,Math.max(0,Math.floor((event.clientX-rect.left)/rect.width*canvas.width))),
         Math.min(canvas.height,Math.max(0,Math.floor((event.clientY-rect.top)/rect.height*canvas.height)))];
}
function finishRoi(event){
 if(!state.roiStart)return;
 const point=imagePoint(event),start=state.roiStart;
 const box=[Math.min(start[0],point[0]),Math.min(start[1],point[1]),Math.max(start[0],point[0]),Math.max(start[1],point[1])];
 state.roiStart=null;state.roiDraft=null;state.roiDrawing=false;
 if(box[2]-box[0]>=3&&box[3]-box[1]>=3){
  state.roi={xyxy:box,source:'drawn',image_size:[state.session.width,state.session.height]};state.roiClear=false;
 }else toast('The ROI is too small. Draw a larger rectangle.');
 updateRoiUI();draw();
}
$('drawRoiBtn').onclick=()=>{if(state.busy||!state.session)return;state.roiDrawing=!state.roiDrawing;state.roiDraft=null;state.roiStart=null;updateRoiUI();draw();};
$('clearRoiBtn').onclick=()=>{state.roi=null;state.roiDraft=null;state.roiDrawing=false;state.roiClear=true;updateRoiUI();draw();};
$('imageCanvas').addEventListener('pointerdown',event=>{
 if(!state.roiDrawing||state.busy||!state.session)return;
 event.preventDefault();state.roiStart=imagePoint(event);state.roiDraft=[...state.roiStart,...state.roiStart];
 $('imageCanvas').setPointerCapture(event.pointerId);draw();
});
$('imageCanvas').addEventListener('pointermove',event=>{
 if(!state.roiStart)return;
 event.preventDefault();state.roiDraft=[...state.roiStart,...imagePoint(event)];draw();
});
$('imageCanvas').addEventListener('pointerup',finishRoi);
$('imageCanvas').addEventListener('pointercancel',()=>{state.roiStart=null;state.roiDraft=null;state.roiDrawing=false;updateRoiUI();draw();});

function draw(){
 if(!state.original)return;
 const canvas=$('imageCanvas'),ctx=canvas.getContext('2d'),w=state.original.naturalWidth,h=state.original.naturalHeight;
 canvas.width=w;canvas.height=h;
 ctx.drawImage(state.original,0,0);
 if(state.mask){
  const maskCanvas=document.createElement('canvas');maskCanvas.width=w;maskCanvas.height=h;const m=maskCanvas.getContext('2d',{willReadFrequently:true});m.drawImage(state.mask,0,0,w,h);
  if(state.view==='mask'){ctx.drawImage(state.mask,0,0,w,h);}
  else if(state.view==='overlay'||state.view==='compare'){
   const data=m.getImageData(0,0,w,h),opacity=Number($('opacity').value)/100;
   for(let i=0;i<data.data.length;i+=4){const yes=data.data[i]>127;data.data[i]=76;data.data[i+1]=224;data.data[i+2]=153;data.data[i+3]=yes?Math.round(opacity*255):0;}
   m.putImageData(data,0,0);ctx.save();
   const split=w*Number($('compareSlider').value)/100;
   if(state.view==='compare'){ctx.beginPath();ctx.rect(split,0,w-split,h);ctx.clip();}
   ctx.drawImage(maskCanvas,0,0);ctx.restore();
   if(state.view==='compare'){ctx.strokeStyle='#f4faef';ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(split,0);ctx.lineTo(split,h);ctx.stroke();}
  }
  if(state.view!=='original'&&state.view!=='mask'){
   const side=state.selected?.task?.side;
   if(side&&side!=='all'){ctx.save();ctx.setLineDash([7,7]);ctx.strokeStyle='#effbd8bb';ctx.lineWidth=1.5;ctx.beginPath();if(side==='left'||side==='right'){ctx.moveTo(w/2,0);ctx.lineTo(w/2,h);}else{ctx.moveTo(0,h/2);ctx.lineTo(w,h/2);}ctx.stroke();ctx.restore();}
  }
 }
 const rectangle=state.roiDraft||state.roi?.xyxy;
 if(rectangle){
  const [ax,ay,bx,by]=rectangle,x=Math.min(ax,bx),y=Math.min(ay,by),rw=Math.abs(bx-ax),rh=Math.abs(by-ay);
  ctx.save();ctx.fillStyle='#e9b75722';ctx.strokeStyle='#f2bd53';ctx.lineWidth=Math.max(2,w/500);
  ctx.setLineDash([Math.max(6,w/100),Math.max(4,w/160)]);ctx.fillRect(x,y,rw,rh);ctx.strokeRect(x,y,rw,rh);ctx.restore();
 }
 canvas.style.transform=`scale(${state.zoom})`; $('zoomLabel').textContent=Math.round(state.zoom*100)+'%';
 $('legendScope').textContent=state.selected?.metrics?(state.selected.task.roi?'Rectangle ROI':sideNames[state.selected.task.side]):'No mask result';
 $('imageWatermark').textContent=state.selected?.mode==='demo'&&state.view!=='original'?'DEMO ANNOTATION · NOT MODEL OUTPUT':state.session?.sample?'SAMPLE IMAGE':'USER IMAGE';
}
function syncView(){document.querySelectorAll('[data-view]').forEach(b=>b.classList.toggle('selected',b.dataset.view===state.view));$('compareControl').hidden=state.view!=='compare';}
function view(mode){if(mode!=='original'&&!state.mask)return toast('Run segmentation before viewing a mask or comparison.');state.view=mode;draw();syncView();}
document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>view(b.dataset.view));
$('opacity').oninput=()=>{$('opacityValue').textContent=$('opacity').value+'%';draw();};$('compareSlider').oninput=draw;
$('zoomIn').onclick=()=>{state.zoom=Math.min(3,state.zoom+.25);draw();};$('zoomOut').onclick=()=>{state.zoom=Math.max(.5,state.zoom-.25);draw();};$('fitBtn').onclick=()=>{state.zoom=1;draw();};
$('imageCanvas').addEventListener('mousemove',e=>{const r=e.target.getBoundingClientRect();const x=Math.floor((e.clientX-r.left)/r.width*e.target.width),y=Math.floor((e.clientY-r.top)/r.height*e.target.height);$('coordinateLabel').textContent=`X ${x} · Y ${y} px`;});
$('imageCanvas').addEventListener('mouseleave',()=>{$('coordinateLabel').textContent=`${state.session.width} × ${state.session.height} px`;});

function addMessage(role,text,kind='',run=null,recordedAt=run?.created_at){
 const d=document.createElement('div');d.className=`message ${role} ${kind}`;
 const date=recordedAt?new Date(recordedAt):!run&&recordedAt===undefined?new Date():null;
 const clock=date&&Number.isFinite(date.getTime())?date.toLocaleString('en-US',{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}):'Time unavailable';
 d.innerHTML=`<div class="message-label"><span>${role==='user'?'YOU':'GEOMASKLAB'}</span><span>${escape(clock)}</span></div><div class="bubble"></div>`;
 d.querySelector('.bubble').textContent=text;
 if(run?.mask_url){
  const target=targetLabel(run),next=run.task.side==='left'?'right':'left';
  const chips=document.createElement('div');chips.className='followup-chips';
  const prompts=(run.imported_evidence||state.session?.imported_evidence)?['Export the selected result.']:[`Extract ${target} in the ${next} half.`,`Extract ${target} in the whole image.`,'Export the selected result.'];
  for(const q of prompts){const btn=document.createElement('button');btn.textContent=q;btn.dataset.prompt=q;chips.append(btn);}d.append(chips);
  const meta=document.createElement('div');meta.className='message-meta';meta.textContent=`V${run.version} · ${run.execution_kind==='saved_mask_region_analysis'?'Offline region analysis':run.mode==='demo'?'Procedural demonstration':'Model-service response'} · ${run.duration_ms} ms`;d.append(meta);
 }
 if(run?.status==='needs_clarification'){
  const chips=document.createElement('div');chips.className='followup-chips';const target=state.selected?.task?.target||state.status.samples[state.session.sample]?.target||'building';
  for(const side of ['left','right']){const b=document.createElement('button');b.textContent=`${sideNames[side]} ${targetNames[target].toLowerCase()}`;b.dataset.prompt=`Extract ${targetNames[target].toLowerCase()} in the ${side} half.`;chips.append(b);}d.append(chips);
 }
 $('chat').append(d);$('chat').scrollTop=$('chat').scrollHeight;
}
function renderTrace(run){
 $('runLabel').textContent=`RUN ${run.id.slice(0,6).toUpperCase()} · ${run.duration_ms} ms`;
 $('trace').innerHTML=run.trace.map(t=>`<div class="trace-step ${escape(t.state)}" title="${escape(t.detail)}"><strong><b>${String(t.step).padStart(2,'0')}</b>${escape(t.name)}</strong><p>${escape(t.detail)}</p></div>`).join('');
 $('executionDot').style.background=run.status==='failed'?'#c89969':'#6d967b';
}
function renderVersions(){
 const versions=state.session.runs.filter(r=>r.mask_url);
 $('versions').innerHTML=versions.map(r=>`<button class="version-pill ${r.id===state.selected?.id?'selected':''}" data-run="${r.id}"><span>V${r.version}</span>${escape(r.task.roi?'Rectangle ROI':sideNames[r.task.side])} · ${escape(targetLabel(r))}</button>`).join('')||'<span class="small-muted">Result versions appear here after segmentation.</span>';
}
async function selectRun(run){
 const token=++state.loadToken;
 try{const mask=await loadImage(run.mask_url);if(token!==state.loadToken)return;
  $('answerCard').hidden=true;$('coverageCard').hidden=false;$('metricsPanel').hidden=false;$('checksPanel').hidden=false;
  $('resultEyebrow').textContent='COVERAGE ANALYSIS';$('artifactText').textContent='Image · Mask · Overlay · Measurements · Logs';
  state.selected=run;state.mask=mask;state.view='overlay';const m=run.metrics,ratio=m.area_ratio*100;
  state.roi=run.task?.roi||null;state.roiClear=false;state.roiDrawing=false;state.roiDraft=null;
  $('qualityMode').value=run.task?.quality_mode||'auto';updateRoiUI();
  localStorage.setItem('geoscope-selected-'+state.session.id,run.id);
  $('ratioValue').textContent=ratio.toFixed(2);$('areaValue').innerHTML=number(m.pixel_area)+' <small>px</small>';$('scopeValue').textContent=run.task.roi?'Rectangle ROI':sideNames[run.task.side];$('timeValue').textContent=run.duration_ms+' ms';
  $('candidateValue').textContent=m.candidate_stats?number(m.candidate_stats.candidate_count):'Not recorded in this older result';
  $('regionCoverage').textContent=m.scope_area_ratio==null?'Not recorded or empty scope':`${(m.scope_area_ratio*100).toFixed(2)}% (${number(m.scope_area_pixels)} px)`;
  $('recalculateBtn').disabled=false;
  $('qualityValue').textContent=run.mode==='demo'?'Procedural demo':qualityNames[run.task?.effective_quality_mode]||'Unconfirmed by service';
  $('resultTitle').textContent=(run.task.roi?'Rectangle ROI':sideNames[run.task.side])+' · '+targetLabel(run);$('resultSubtitle').textContent=`V${run.version} · ${run.mode==='demo'?'Procedural mask · Not model output':'Model output · Review required'}`;
  if(run.imported_evidence)$('resultSubtitle').textContent+=` · Imported from V${run.imported_evidence.source_version} · No new inference`;
  if(run.imported_evidence)$('timeValue').textContent=run.duration_ms+' ms (source run)';
  if(run.execution_kind==='saved_mask_region_analysis'){
   $('resultSubtitle').textContent=`V${run.version} · Offline region analysis · No model inference · Source ${run.source_prediction.mode}`;
   $('qualityValue').textContent='Saved mask';
  }
  $('resultStatus').textContent=runStateLabel(run);
  const category=run.capability||state.status?.capabilities?.targets?.[run.task.target];
  if(category?.level==='experimental')$('resultSubtitle').textContent+=' · Experimental category · Accuracy not validated';
  renderReview(run);
  $('coverageBar').style.width=ratio+'%';$('ringValue').setAttribute('stroke-dasharray',`${ratio*1.634} 164`);
  $('checksList').innerHTML=['Mask and image dimensions match',`Scope matches ${run.task.roi?'the rectangle ROI':sideNames[run.task.side].toLowerCase()}`,'Measurements and result files saved'].map(s=>`<p><span>✓</span>${escape(s)}</p>`).join('');$('checkCount').textContent='3 / 3';
  $('contextChip').hidden=false;$('contextChip').lastElementChild.textContent=`Parent V${run.version} · ${targetLabel(run)} · ${sideNames[run.task.side]}`;
  $('exportBtn').disabled=false;$('reportBtn').disabled=!run.report_url;renderVersions();renderTrace(run);draw();syncView();
 }catch(e){toast(e.message);}
}
function renderReview(run){
 const review=run.semantic_review||{state:'pending',events:[]},last=review.events.at(-1);
 $('reviewPanel').hidden=false;$('reviewState').textContent=reviewNames[review.state]||reviewNames.pending;
 $('reviewSummary').textContent=last?`${last.reviewer} · ${new Date(last.at).toLocaleString('en-US')} · ${last.note}`:'Inspect target identity, omissions, false positives and boundaries before recording a decision.';
 $('resultStatus').textContent=reviewNames[review.state]||reviewNames.pending;
 $('resultStatus').className='result-badge '+(review.state==='accepted'?'success':review.state==='rejected'?'warning':'');
}
$('reviewBtn').onclick=()=>{
 if(state.busy||!state.selected)return toast('Wait for the task to finish before reviewing.');
 const selected=state.selected,sessionId=state.session.id;
 modal('Record review',`<p>Inspect the original image and overlay for target identity, omissions, false positives and boundary errors. This decision applies only to V${selected.version}; each new result starts pending review.</p><div class="modal-notice">Review does not edit masks or measurements. Decisions are self-reported; they are not independent accuracy estimates or authenticated identities.</div><form id="reviewForm" class="review-form"><label for="reviewDecision">Review decision</label><select id="reviewDecision" required><option value="">Choose a decision</option><option value="accepted">Accept this result</option><option value="rejected">Reject this result</option><option value="pending">Return to pending review</option></select><label for="reviewerName">Reviewer label</label><input id="reviewerName" required maxlength="100" autocomplete="off"><label for="reviewNote">Review rationale</label><textarea id="reviewNote" required maxlength="2000" rows="4" placeholder="Describe the regions inspected, any problems found, and suitability for the intended use."></textarea><button type="submit" class="primary" id="saveReview">Save review</button></form><h3>Review history</h3><div class="review-history">${(selected.semantic_review?.events||[]).map(e=>`<p><strong>${escape(reviewNames[e.decision])}</strong> · ${escape(e.reviewer)} · ${escape(new Date(e.at).toLocaleString('en-US'))}<br>${escape(e.note)}</p>`).join('')||'<p>No review records yet.</p>'}</div>`,'SEMANTIC REVIEW');
 $('reviewForm').onsubmit=async e=>{
  e.preventDefault();const button=$('saveReview');button.disabled=true;
  try{const updated=await api('/api/review',{session_id:sessionId,run_id:selected.id,decision:$('reviewDecision').value,reviewer:$('reviewerName').value,note:$('reviewNote').value});
   if(state.session.id===sessionId){const existing=state.session.runs.find(r=>r.id===updated.id);if(existing)Object.assign(existing,updated);if(state.selected?.id===updated.id){Object.assign(state.selected,updated);renderReview(state.selected);}}
   closeModal();toast('Review saved. It will be included in the report and evidence export.');
  }catch(error){toast(error.message);button.disabled=false;}
 };
};
async function run(query,simulateFailure=false){
 if(state.busy||!state.session)return;
 query=query.trim();if(!query)return;
 state.busy=true;$('sendBtn').disabled=true;$('newBtn').disabled=true;$('busyOverlay').hidden=false;$('query').value='';
 if($('starterList'))$('starterList').remove();
 const welcome=$('chat').querySelector('.assistant-intro');if(welcome)welcome.remove();
 addMessage('user',query);const parent=state.selected?.id||null;
 try{
  const payload={session_id:state.session.id,query,mode:state.mode,parent_run_id:parent,simulate_failure:simulateFailure,
                 quality_mode:$('qualityMode').value};
  if(state.roi)payload.roi=state.roi;
  else if(state.roiClear)payload.roi={};
  if(state.roi)payload.scope='all';
  const result=await api('/api/run',payload);
  state.session.runs.push(result);state.last=result;
  addMessage('assistant',result.message,['failed','needs_clarification','needs_review'].includes(result.status)?'warning':'',result);
  if(result.mask_url)await selectRun(result);else{if(result.status==='answered')renderAnswer(result);renderTrace(result);}
  if(result.status==='export_ready')download(result.export_url);
  if(result.status==='failed'&&state.selected)toast('The task failed. The previous valid result remains on the canvas.');
 }catch(e){addMessage('assistant',e.message,'warning');toast('Request failed. No result was generated.');}
 finally{state.busy=false;$('sendBtn').disabled=false;$('newBtn').disabled=false;$('busyOverlay').hidden=true;}
}
$('taskForm').onsubmit=e=>{e.preventDefault();run($('query').value);};
$('query').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();run($('query').value);}};
document.addEventListener('click',e=>{const experiment=e.target.closest('[data-session]');if(experiment)openExperiment(experiment.dataset.session);const prompt=e.target.closest('[data-prompt]');if(prompt)run(prompt.dataset.prompt);const v=e.target.closest('[data-run]');if(v&&!state.busy){const r=state.session.runs.find(x=>x.id===v.dataset.run);if(r?.mask_url){selectRun(r);closeModal();}}});
function download(url){const a=document.createElement('a');a.href=url;a.download='';document.body.append(a);a.click();a.remove();}
$('exportBtn').onclick=()=>{if(state.selected){download(state.selected.export_url);toast('Evidence download started: image, masks, measurements, logs and report.');}};
$('recalculateBtn').onclick=()=>{
 if(state.busy||!state.selected?.mask_url)return;
 const sessionId=state.session.id,sourceId=state.selected.id;
 const roi=state.roi?JSON.parse(JSON.stringify(state.roi)):null;
 modal('Recalculate a region from the saved mask',
  `<p>This operation changes the spatial scope only. It uses the original full-image mask and does not call model services.</p>
   <form id="regionForm"><label for="regionScope">Analysis scope</label>
   <select id="regionScope"><option value="all">Whole image</option><option value="left">Left half</option><option value="right">Right half</option><option value="top">Top half</option><option value="bottom">Bottom half</option>${roi?'<option value="roi">Current rectangle ROI</option>':''}</select>
   <p>${roi?`Current rectangle: ${escape(JSON.stringify(roi.xyxy))}.`:'To analyze a rectangle, close this dialog and draw an ROI on the image first.'}</p>
   <p>The semantic target and complement setting are retained. The new result will have a separate review record.</p>
   <button id="saveRegion" class="primary" type="submit">Create result version</button></form>`,'OFFLINE REGION ANALYSIS');
 $('regionScope').value=roi?'roi':state.selected.task.side;
 $('regionForm').onsubmit=async e=>{
  e.preventDefault();if(state.busy)return;
  const choice=$('regionScope').value;state.busy=true;
  $('saveRegion').disabled=true;$('sendBtn').disabled=true;$('newBtn').disabled=true;
  try{
   const result=await api('/api/recalculate-region',{session_id:sessionId,run_id:sourceId,scope:choice==='roi'?'all':choice,roi:choice==='roi'?roi:null});
   if(state.session.id===sessionId){state.session.runs.push(result);state.last=result;addMessage('user',result.query);addMessage('assistant',result.message,'',result);await selectRun(result);}
   closeModal();toast('Created a separate result version without model inference.');
  }catch(error){toast(error.message);if($('saveRegion'))$('saveRegion').disabled=false;}
  finally{state.busy=false;$('sendBtn').disabled=false;$('newBtn').disabled=false;}
 };
};
$('reportBtn').onclick=()=>{if(state.selected?.report_url)download(state.selected.report_url);};
function gallery(){
 if(state.busy)return toast('Wait for the current task to finish.');
 modal('Choose an image',`<p>Try a procedural example, or upload an image for analysis with configured model services.</p><div class="sample-grid">${Object.entries(state.status?.samples||{}).map(([key,s])=>`<button class="sample-card" data-sample="${key}"><img src="assets/${escape(s.file)}" alt="${escape(s.name)}"><strong>${escape(s.name)}</strong><small>${s.size.join(' × ')} px · Procedural ${targetNames[s.target].toLowerCase()} mask</small></button>`).join('')}</div><p style="margin-top:16px">Example masks demonstrate interactions and pixel operations. They are not RemoteSAM predictions or ground truth for EO accuracy evaluation.</p><button class="secondary" id="modalUpload">${icon('image')}Upload an image</button>`,'IMAGE LIBRARY');
 $('modalBody').querySelectorAll('[data-sample]').forEach(b=>b.onclick=()=>newExperiment(b.dataset.sample));$('modalUpload').onclick=()=>{closeModal();$('fileInput').click();};
}
$('galleryBtn').onclick=gallery;$('newBtn').onclick=gallery;$('uploadBtn').onclick=gallery;$('workspaceBtn').onclick=()=>window.scrollTo({top:0,behavior:'smooth'});
$('fileInput').onchange=async e=>{const file=e.target.files[0];if(!file)return;if(file.size>12*1024*1024){toast('Upload an image no larger than 12 MB.');e.target.value='';return;}const reader=new FileReader();reader.onload=()=>newExperiment(null,reader.result,file.name);reader.onerror=()=>toast('Could not read the image.');reader.readAsDataURL(file);e.target.value='';};

function renderBatch(batch){
 state.batch=batch;
 if(!$('modal').open||$('modalTitle').textContent!=='Batch analysis')return;
 const items=batch.items||[],total=batch.total_count||items.length;
 const done=batch.status==='completed',failed=batch.status==='failed';
 $('modalBody').innerHTML=`<div class="batch-progress"><strong>${failed?'Batch failed to start':done?'Batch complete':'Running images sequentially'} · ${batch.completed_items||items.length} / ${total}</strong><p>${failed?escape(batch.error):'Each image has its own results. A failed item does not overwrite completed results.'}</p></div>
  <div class="batch-items">${items.map((item,i)=>`<div class="batch-item"><span>${i+1}. ${escape(item.session_id)}</span><b>${escape(statusNames[item.status]||item.status)}</b><small>${item.metrics?`${number(item.metrics.pixel_area)} px · ${(item.metrics.area_ratio*100).toFixed(2)}% · Components ${item.metrics.candidate_stats?.candidate_count??'—'}`:escape(item.failure_reason||'Awaiting result')}</small><button data-session="${escape(item.session_id)}">Open image</button></div>`).join('')}</div>
  ${done?`<button class="primary" id="batchExportBtn">Export batch CSV</button>`:''}`;
 if(done)$('batchExportBtn').onclick=()=>download(`/api/batch-export/${batch.batch_id}`);
}
async function watchBatch(batchId){
 for(;;){
  try{
   const batch=await api(`/api/batch/${batchId}`);renderBatch(batch);
   if(batch.status!=='running')return;
  }catch(e){toast(e.message);return;}
  await new Promise(resolve=>setTimeout(resolve,700));
 }
}
async function batchDialog(){
 if(state.busy)return toast('Wait for the current task to finish.');
 if(state.batch?.status==='running'){
  modal('Batch analysis','<p>Restoring batch progress…</p>','BATCH EXPERIMENT');
  renderBatch(state.batch);return;
 }
 try{
  const data=await api('/api/sessions');
  modal('Batch analysis',`<p>Select 2–5 saved images to run one task sequentially. Use Choose image to add images first.</p>
   <div class="batch-selector">${data.sessions.map(s=>`<label><input type="checkbox" class="batch-check" value="${escape(s.id)}" ${s.id===state.session?.id?'checked':''}><span>${escape(s.name)}<small>${s.width} × ${s.height} px · ${s.run_count} runs</small></span></label>`).join('')}</div>
   <div class="batch-add"><button class="secondary" data-add-sample="airport">Add aircraft example</button><button class="secondary" data-add-sample="urban">Add urban example</button></div>
   <label class="batch-label" for="batchQuery">Shared task</label><textarea id="batchQuery" rows="2" maxlength="1800" placeholder="For example: Extract aircraft in these images and calculate coverage."></textarea>
   <label class="batch-inline"><input id="batchUseRoi" type="checkbox" ${state.roi?'':'disabled'}> Use the current ROI for images with matching dimensions</label>
   <p>Leave unchecked to use whole images. Batch items run sequentially; failures are recorded separately.</p>
   <button class="primary" id="startBatchBtn">Start batch</button>`,'BATCH EXPERIMENT');
  $('modalBody').querySelectorAll('[data-add-sample]').forEach(b=>b.onclick=async()=>{
   try{await api('/api/session',{sample:b.dataset.addSample});await batchDialog();toast('Example added to the image list.');}
   catch(e){toast(e.message);}
  });
  $('startBatchBtn').onclick=async()=>{
   const selected=[...$('modalBody').querySelectorAll('.batch-check:checked')].map(el=>el.value);
   const query=$('batchQuery').value.trim();
   if(selected.length<2||selected.length>5)return toast('Select 2–5 images.');
   if(!query)return toast('Enter one shared task with a single semantic target.');
   const useRoi=$('batchUseRoi').checked;
   if(useRoi){
    const chosen=data.sessions.filter(s=>selected.includes(s.id));
    if(chosen.some(s=>s.width!==state.roi.image_size[0]||s.height!==state.roi.image_size[1]))return toast('These images have different dimensions and cannot share this ROI.');
   }
   $('startBatchBtn').disabled=true;
   try{
    const batch=await api('/api/batch/start',{session_ids:selected,query,mode:state.mode,
      quality_mode:$('qualityMode').value,roi:useRoi?state.roi:{},scope:'all'});
    renderBatch(batch);watchBatch(batch.batch_id);
   }catch(e){$('startBatchBtn').disabled=false;toast(e.message);}
  };
 }catch(e){toast(e.message);}
}
$('batchBtn').onclick=batchDialog;
async function history(){
 const runs=state.session?.runs||[];
 modal('Experiment history',runs.length?`<p>Results are saved separately. Open a valid version to inspect it or use it as the parent of a new task.</p>${[...runs].reverse().map(r=>`<button class="history-row" ${r.mask_url?`data-run="${r.id}"`:''} ${!r.mask_url?'disabled':''}><span>V${r.version}</span><div><strong>${escape(r.query)}</strong><small>${escape(runStateLabel(r))} · ${r.mode==='demo'?'Demo':'Live'}</small></div><time>${r.duration_ms} ms</time></button>`).join('')}`:'<p>No tasks have run yet. Try extracting buildings in the right half.</p>','EXPERIMENT HISTORY');
 try{
  const data=await api('/api/sessions');if(!$('modal').open||$('modalTitle').textContent!=='Experiment history')return;
  $('modalBody').insertAdjacentHTML('beforeend','<h3>Saved image experiments</h3>'+data.sessions.map(s=>`<button class="history-row" data-session="${escape(s.id)}"><span>↗</span><div><strong>${escape(s.name)}</strong><small>${s.width} × ${s.height} px · ${s.run_count} runs</small></div></button>`).join(''));
 }catch(e){toast('Could not load saved experiments.');}
}
$('historyBtn').onclick=history;
function details(log=false){
 const r=log?state.last||state.selected:state.selected||state.last;
 if(!r)return modal('Run details','<p>No task has run yet. Execution events, provenance and parameters will appear here.</p>');
 modal(log?'Full execution log':'Result and execution details',`<p><strong>RUN ${r.id}</strong> · ${r.mode==='demo'?'Procedural demonstration':'Live model services'} · ${escape(runStateLabel(r))}</p><div class="modal-notice">${escape(r.provenance.perception)}</div>${r.mask_url?`<div class="download-list"><a href="${r.mask_url}" download="mask.png">mask.png ↓</a><a href="${r.overlay_url}" download="overlay.png">overlay.png ↓</a><a href="${r.export_url}" download>Complete evidence bundle ↓</a></div>`:''}<h3>Data source and method</h3><p>${escape(r.provenance.source)}</p><p>Planner: ${escape(r.provenance.planner)}. Coverage is measured from the binary mask; no geographic area is inferred.</p><pre>${escape(JSON.stringify(log?r.trace:r,null,2))}</pre>`,'RUN PROVENANCE');
}
$('detailBtn').onclick=()=>details(false);$('logBtn').onclick=()=>details(true);
$('sourceBtn').onclick=()=>modal('Image provenance',`<p>${escape(state.session?.source||'No image selected')}</p><p>Built-in masks are generated from geometric rules. They test interactions, context and pixel operations; they do not measure model accuracy.</p><p>Coordinates start at the top-left: X increases rightward and Y downward. Directions are image-relative. Whole-image coverage uses all image pixels as its denominator.</p>`,'DATA NOTES');
async function connections(){
 try{state.status=await api('/api/status');}catch(e){return toast('The local server is unavailable.');}
 const canLive=state.status.agent_configured&&state.status.sam_configured;
 modal('Runtime settings',`<div class="mode-options"><button id="demoMode" class="${state.mode==='demo'?'selected':''}">Offline demo<small>Procedural masks · Deterministic measurements</small></button><button id="liveMode" class="${state.mode==='live'?'selected':''}" ${!canLive?'disabled':''}>Model services<small>${canLive?'Configured; verified on execution':'Planner and segmentation services required'}</small></button></div><div class="connection-list"><div><span>Planner service</span><b>${state.status.agent_configured?'Configured; inference not checked':'Not configured'}</b></div><div><span>RemoteSAM</span><b>${state.status.sam_configured?'Configured; inference not checked':'Not configured'}</b></div><div><span>Measurements and local storage</span><b style="color:#5d8850">Local server available</b></div></div><p>Live mode sends images to the services configured on the Python server. API keys stay on the server.</p><h3>Connection setup</h3><p>Set GEO_AGENT_BASE_URL, GEO_AGENT_MODEL and GEO_REMOTESAM_URL as described in the README, then restart. Configuration does not establish successful inference.</p><button class="secondary" id="failureDemo">Try a controlled failure</button>`,'RUNTIME SETTINGS');
 $('demoMode').onclick=()=>{state.mode='demo';localStorage.setItem('geoscope-mode','demo');updateMode();closeModal();toast('Switched to offline demo.');};$('liveMode').onclick=()=>{state.mode='live';localStorage.setItem('geoscope-mode','live');updateMode();closeModal();toast('Switched to live model services.');};
 $('failureDemo').onclick=()=>{closeModal();run('Test preservation of earlier results after a controlled tool failure.',true);};
 $('modalBody').insertAdjacentHTML('beforeend','<h3>Service connection checks</h3><p>The workbench validates RemoteAgent plans before calling RemoteSAM and returns tool feedback to the planner. These checks inspect service availability and readiness declarations without sending images; they do not evaluate inference quality.</p><button class="secondary" id="checkServices">Check connections</button><pre id="serviceReport" hidden></pre><p>Configure .env in the project root, then restart. Your machine must be able to reach the configured services.</p>');
 $('checkServices').onclick=async()=>{
  const button=$('checkServices'),box=$('serviceReport');button.disabled=true;box.hidden=false;box.textContent='Checking service availability…';
  try{const report=await api('/api/check-services',{});box.textContent=`Planner service：${report.agent.message}\nRemoteSAM：${report.sam.message}\n\n${report.note}`;}
  catch(e){box.textContent=e.message;}finally{button.disabled=false;}
 };
}
$('connectionBtn').onclick=connections;
$('aboutBtn').onclick=()=>modal('Turn a question into a traceable experiment',`<p>GeoMaskLab helps researchers segment images, inspect masks and preserve evidence for review.</p><h3>Suggested workflow</h3><p>Choose an image → select a scope → segment one target → inspect components and coverage → record a review → export the evidence. Use offline region analysis to investigate saved masks without inference.</p><h3>Categories and quality</h3><p>Buildings and aircraft are the primary use cases. Roads, water, vegetation and ships remain experimental. Tiled refinement can change omissions and false positives; it does not guarantee greater accuracy. Review all model outputs.</p><h3>Supported operations</h3><p>RGB uploads, bounded task planning, validated segmentation, deterministic measurements, versioned results, review, evidence handoff, offline region analysis and small sequential batches.</p><h3>Scope and limitations</h3><p>Offline examples test software behavior rather than model accuracy. Live mode requires compatible services. Components are candidates, not verified object counts. Pixel measurements are not geographic area, and integrity checks do not establish semantic correctness.</p><p>Experiments are stored in the local experiments directory and can be restored after a page reload or server restart.</p>`,'ABOUT THE PROTOTYPE');

async function init(){
 try{
  state.status=await api('/api/status');const saved=localStorage.getItem('geoscope-session');
  if(saved){try{await showSession(await api('/api/session/'+encodeURIComponent(saved)));return;}catch(e){localStorage.removeItem('geoscope-session');}}
  await newExperiment('urban');
 }
 catch(e){modal('Local server not running','<p>Start the local server as described in the README, then open http://127.0.0.1:4180.</p>');}
}
init();
