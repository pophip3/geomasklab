/* Core-backed candidate review, explicit offline batching and saved-operation replay. */
function enhanceEnglishFileInputs(){
 $('modalBody').querySelectorAll('input[type="file"]:not([data-english-picker])').forEach(input=>{
  input.dataset.englishPicker='true';input.dataset.fileRequired=String(input.required);input.required=false;input.hidden=true;
  const label=input.labels?.[0]?.textContent.trim()||'input file',wrapper=document.createElement('div');wrapper.className='english-file-picker';
  const button=document.createElement('button');button.type='button';button.className='secondary';button.textContent=input.multiple?'Choose files':'Choose file';button.setAttribute('aria-label','Choose '+label);
  const status=document.createElement('span');status.textContent='No file selected';status.setAttribute('aria-live','polite');
  button.onclick=()=>input.click();input.addEventListener('change',()=>{status.textContent=input.files.length>1?input.files.length+' files selected':input.files[0]?.name||'No file selected';});
  input.after(wrapper);wrapper.append(button,status);input.dataset.chooseButton=label;
 });
}
new MutationObserver(enhanceEnglishFileInputs).observe($('modalBody'),{childList:true,subtree:true});
$('modalBody').addEventListener('submit',event=>{
 const missing=[...event.target.querySelectorAll('input[data-file-required="true"]')].find(input=>!input.files.length);
 if(missing){event.preventDefault();event.stopImmediatePropagation();toast('Choose '+missing.dataset.chooseButton+' before continuing.');missing.nextElementSibling?.querySelector('button')?.focus();}
},true);
const refreshBeforeOfflineTools=refreshWorkbench;
refreshWorkbench=function(...args){refreshBeforeOfflineTools(...args);$('inspectComponentsBtn').disabled=!state.selected?.mask_url||state.busy;};
refreshWorkbench();
$('batchBtn').textContent='Model/demo batch';

function candidateFlags(component){
 return [['touches_image_boundary','Image edge'],['touches_roi_boundary','Region edge'],['touches_invalid_boundary','Invalid edge']].filter(([key])=>component[key]).map(([,name])=>name).join(' · ')||'Interior';
}
async function inspectCandidates(){
 if(state.busy||!state.selected?.mask_url)return;
 const sid=state.session.id,rid=state.selected.id,original=state.original;
 modal('Candidate regions & clipping boundaries',`<p>Inspect 8-connected foreground after region and validity clipping. Filters create a review layer; source evidence remains unchanged.</p><form id="componentForm" class="comparison-form"><label for="componentMin">Minimum area (px)<input id="componentMin" type="number" min="1" max="64000000" value="1" required></label><label for="componentBoundary">Boundary filter<select id="componentBoundary"><option value="all">All candidates</option><option value="touching">Any boundary contact</option><option value="interior">Interior candidates</option></select></label><button class="primary" id="inspectRun" type="submit">Inspect candidates</button></form><div id="componentOutput" aria-live="polite"></div>`,'CANDIDATE REVIEW');
 $('modal').classList.add('wide-dialog');
 $('componentForm').onsubmit=async event=>{
  event.preventDefault();const form=event.currentTarget;$('inspectRun').disabled=true;
  $('componentOutput').innerHTML='<p class="comparison-empty" role="status">Verifying evidence and inspecting connected regions…</p>';
  try{
   const result=await api('/api/inspect-components',{session_id:sid,run_id:rid,min_area_pixels:Number($('componentMin').value),boundary_filter:$('componentBoundary').value});
   if($('componentForm')!==form)return;
   $('componentOutput').innerHTML=`<div class="comparison-summary"><div><small>ALL COMPONENTS</small><strong>${number(result.component_count)}</strong></div><div><small>SELECTED CANDIDATES</small><strong>${number(result.selected_component_count)}</strong></div><div><small>SELECTED FOREGROUND</small><strong>${number(result.selected_foreground_pixels)} <span>px</span></strong></div></div><div class="candidate-preview"><canvas id="candidateCanvas" aria-label="Selected candidate layer and highlighted bounding box"></canvas><div id="candidateDetail"><strong>Choose a candidate</strong><p>Locate its bounding box and inspect boundary flags.</p></div></div><div class="candidate-pagination"><button id="componentPrevious" class="secondary">← Previous</button><span id="componentPage"></span><button id="componentNext" class="secondary">Next →</button></div><div class="table-scroll" id="componentTable"></div><p class="mask-input-hint">Rows include unselected components. IDs remain stable under filtering. Image, region and invalid boundary flags use 8-neighbor contact and may overlap.</p><div class="modal-notice">${escape(result.interpretation)}</div><button class="primary" id="exportComponents">Export replayable inspection ↓</button><p class="mask-input-hint">Offline replay: <code>geomasklab verify-components inspection.zip</code></p>`;
   const layer=await loadImage('data:image/png;base64,'+result.selection_png_base64);
   if($('componentForm')!==form)return;
   let page=0,active=null;const pageSize=25;
   const paint=()=>{
    const canvas=$('candidateCanvas'),scale=Math.min(1,960/original.naturalWidth,640/original.naturalHeight);
    canvas.width=Math.max(1,Math.round(original.naturalWidth*scale));canvas.height=Math.max(1,Math.round(original.naturalHeight*scale));const ctx=canvas.getContext('2d');ctx.drawImage(original,0,0,canvas.width,canvas.height);
    const overlay=document.createElement('canvas');overlay.width=canvas.width;overlay.height=canvas.height;const m=overlay.getContext('2d',{willReadFrequently:true});m.imageSmoothingEnabled=false;m.drawImage(layer,0,0,canvas.width,canvas.height);const pixels=m.getImageData(0,0,canvas.width,canvas.height);
    for(let i=0;i<pixels.data.length;i+=4){const positive=pixels.data[i]>127;pixels.data[i]=69;pixels.data[i+1]=197;pixels.data[i+2]=161;pixels.data[i+3]=positive?145:0;}m.putImageData(pixels,0,0);ctx.drawImage(overlay,0,0);
    if(active){const [x1,y1,x2,y2]=active.bbox;ctx.strokeStyle='#ffc04c';ctx.lineWidth=3;ctx.strokeRect(x1*scale,y1*scale,(x2-x1)*scale,(y2-y1)*scale);}
   };
   const render=()=>{
    const rows=result.components.slice(page*pageSize,(page+1)*pageSize);
    $('componentPage').textContent=result.component_count?`${page*pageSize+1}–${page*pageSize+rows.length} of ${number(result.component_count)}`:'No foreground components';
    $('componentPrevious').disabled=page===0;$('componentNext').disabled=(page+1)*pageSize>=result.component_count;
    $('componentTable').innerHTML=`<table class="analysis-table"><thead><tr><th>Candidate</th><th>Area</th><th>Boundary contact</th><th>Selection</th></tr></thead><tbody>${rows.map(c=>`<tr class="${active?.component_id===c.component_id?'selected-row':''}"><td><button class="text-button" data-component="${c.component_id}">C${c.component_id} · Locate ↗</button></td><td>${number(c.area_pixels)} px</td><td>${escape(candidateFlags(c))}</td><td>${c.selected?'Selected':escape(c.exclusion_reasons.join(', '))}</td></tr>`).join('')||'<tr><td colspan="4">No foreground within the selected valid domain.</td></tr>'}</tbody></table>`;
    $('componentTable').querySelectorAll('[data-component]').forEach(button=>button.onclick=()=>{
     active=result.components.find(c=>c.component_id===Number(button.dataset.component));
     $('candidateDetail').innerHTML=`<strong>C${active.component_id} · ${number(active.area_pixels)} px</strong><p>Bounding box: [${active.bbox.join(', ')}], exclusive upper bounds.</p><p>Centroid: (${active.centroid.x}, ${active.centroid.y}) px.</p><p class="boundary-hint">${escape(candidateFlags(active))}</p>${active.touches_roi_boundary?'<small>Region-boundary contact may indicate clipping. Review the source prediction before interpreting this candidate.</small>':''}`;paint();render();
    });
   };
   $('componentPrevious').onclick=()=>{page--;render();};$('componentNext').onclick=()=>{page++;render();};
   $('exportComponents').onclick=()=>download(result.packet_url);paint();render();
  }catch(error){if($('componentForm')===form)$('componentOutput').innerHTML='<p class="comparison-empty" role="alert">'+escape(error.message)+'</p>';}
  finally{if($('componentForm')===form)$('inspectRun').disabled=false;}
 };
 $('componentForm').requestSubmit();
}
$('inspectComponentsBtn').onclick=inspectCandidates;

let offlineBatchPoll=null,offlineBatchGeneration=0;
function stopOfflinePoll(){offlineBatchGeneration++;if(offlineBatchPoll){clearTimeout(offlineBatchPoll);offlineBatchPoll=null;}}
function batchSummaryMarkup(job){
 const summary=job.summary||job.progress,rows=summary?.samples||[],aggregate=summary?.aggregate||{};
 const pct=value=>value==null?'Undefined':(value*100).toFixed(2)+'%';
 return `<div class="analysis-explanation"><span class="eyebrow">${escape(job.status.replaceAll('_',' '))}</span><p>${escape(job.error||job.notice||'Explicitly paired inputs; no model inference.')}</p></div>${summary?`<div class="comparison-summary"><div><small>COMPLETED / FAILED</small><strong>${summary.completed_count} / ${summary.failed_count}</strong></div><div><small>MACRO MEAN COVERAGE</small><strong>${pct(aggregate.macro_mean_coverage)}</strong></div><div><small>PIXEL-WEIGHTED COVERAGE</small><strong>${pct(aggregate.micro_weighted_coverage)}</strong></div></div><p class="mask-input-hint">Valid-region coverage. Successful zero coverage is retained; empty valid domains are undefined and omitted. Failed samples never enter coverage means.</p><div class="table-scroll"><table class="analysis-table"><thead><tr><th>Sample</th><th>State</th><th>Foreground / valid pixels</th><th>Coverage</th><th>Issue</th><th>Inspect</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${escape(r.id)}</td><td>${escape(r.status)}</td><td>${r.foreground_pixels==null?'Unavailable':number(r.foreground_pixels)+' / '+number(r.valid_region_pixels)}</td><td>${pct(r.coverage_of_valid_region)}</td><td>${escape(r.error?.message||r.error?.code||'—')}</td><td>${r.status==='completed'&&!['running','cancelling'].includes(job.status)?`<button class="text-button" data-batch-sample="${escape(r.id)}">Open evidence ↗</button>`:'—'}</td></tr>`).join('')}</tbody></table></div>`:''}<div class="comparison-downloads"><button id="cancelOfflineBatch" class="secondary" ${!['running','cancelling'].includes(job.status)?'disabled':''}>Cancel after current sample</button><button id="resumeOfflineBatch" class="secondary" ${['running','cancelling','completed'].includes(job.status)?'disabled':''}>Verify & resume</button><button id="exportOfflineBatch" class="primary" ${!job.packet_url?'disabled':''}>Export replayable batch ↓</button></div>`;
}
async function showOfflineJob(id){
 const output=$('offlineBatchOutput'),generation=++offlineBatchGeneration;if(!output)return;
 try{
  const job=await api('/api/offline-batch/'+id);if($('offlineBatchOutput')!==output||generation!==offlineBatchGeneration)return;
  $('offlineBatchOutput').innerHTML=batchSummaryMarkup(job);
  $('cancelOfflineBatch').onclick=async()=>{try{await api('/api/offline-batch/cancel',{id});await showOfflineJob(id);}catch(e){toast(e.message);}};
  $('resumeOfflineBatch').onclick=async()=>{try{await api('/api/offline-batch/resume',{id});await showOfflineJob(id);}catch(e){toast(e.message);}};
  $('exportOfflineBatch').onclick=()=>download(job.packet_url);
  $('offlineBatchOutput').querySelectorAll('[data-batch-sample]').forEach(button=>button.onclick=async()=>{
   button.disabled=true;
   try{const session=await api('/api/offline-batch/open-result',{id,sample_id:button.dataset.batchSample});await showSession(session);toast('Verified batch evidence opened without inference.');}
   catch(error){toast(error.message);button.disabled=false;}
  });
  if(['running','cancelling'].includes(job.status)){stopOfflinePoll();offlineBatchPoll=setTimeout(()=>showOfflineJob(id),650);}
 }catch(error){if($('offlineBatchOutput')===output&&generation===offlineBatchGeneration)output.innerHTML='<p role="alert">'+escape(error.message)+'</p>';}
}
const batchManifestExample={schema:'geomasklab-batch-manifest/1.0',samples:[{id:'example-01',image:'image.png',mask:'mask.png',target:'tree',source:'External mask tool, version and settings',aligned:true,valid_mask:'valid.png',valid_source:'Explicit inclusion/exclusion rationale',scope:'all'}]};
$('offlineBatchBtn').onclick=()=>{
 if(state.busy)return toast('Wait for the current task to finish.');
 stopOfflinePoll();const saved=localStorage.getItem('geomasklab-offline-batch');
 modal('Explicit offline mask batch',`<p>Upload a JSON manifest and the files it names. Each sample has explicit image, mask, target and source pairing. The CLI supports relative subdirectories; this browser uses flat filenames.</p><form id="offlineBatchForm" class="review-form"><label for="offlineManifest">Manifest · JSON</label><input type="file" id="offlineManifest" accept="application/json,.json" required><label for="offlineInputs">Explicit input files · select all named images, masks and references</label><input type="file" id="offlineInputs" multiple required><p class="mask-input-hint">Up to 128 files, 32 MB total. Missing or invalid sample inputs are reported individually. A running sample finishes before cooperative cancellation takes effect.</p><button id="startOfflineBatch" class="primary" type="submit">Start offline batch</button></form><details class="manifest-example"><summary>See a manifest example</summary><pre>${escape(JSON.stringify(batchManifestExample,null,2))}</pre></details>${saved?'<button id="restoreOfflineBatch" class="secondary">Restore most recent batch</button>':''}<div id="offlineBatchOutput" aria-live="polite"></div>`,'RELIABLE BATCH PROCESSING');
 $('modal').classList.add('wide-dialog');
 if(saved)$('restoreOfflineBatch').onclick=()=>showOfflineJob(saved);
 $('offlineBatchForm').onsubmit=async event=>{
  event.preventDefault();stopOfflinePoll();const form=event.currentTarget;$('startOfflineBatch').disabled=true;
  try{
   const manifestFile=$('offlineManifest').files[0];if(!manifestFile)throw new Error('Choose a JSON manifest first.');if(manifestFile.size>1024*1024)throw new Error('The manifest must be 1 MB or smaller.');
   const manifest=JSON.parse(await manifestFile.text()),inputs=[...$('offlineInputs').files];
   if(inputs.length>128||inputs.reduce((n,f)=>n+f.size,0)>32*1024*1024)throw new Error('Select up to 128 input files totaling no more than 32 MB.');
   if(new Set(inputs.map(f=>f.name.toLowerCase())).size!==inputs.length)throw new Error('Input basenames must be unique; explicit pairing cannot resolve duplicate filenames.');
   const files=[];for(const file of inputs)files.push({name:file.name,data:await maskFileData(file)});
   const job=await api('/api/offline-batch/start',{manifest,files});localStorage.setItem('geomasklab-offline-batch',job.id);
   if($('offlineBatchForm')===form)await showOfflineJob(job.id);toast('Offline batch started; the current experiment is preserved.');
  }catch(error){if($('offlineBatchForm')===form)$('offlineBatchOutput').innerHTML='<p class="comparison-empty" role="alert">'+escape(error.message)+'</p>';}
  finally{if($('offlineBatchForm')===form)$('startOfflineBatch').disabled=false;}
 };
};
$('modal').addEventListener('close',stopOfflinePoll);
$('verifyPacketBtn').onclick=()=>{if(state.busy)return toast('Wait for the current task to finish.');$('reviewPacketInput').click();};
$('reviewPacketInput').onchange=async event=>{
 const file=event.target.files[0];event.target.value='';if(!file)return;
 if(file.size>12*1024*1024)return toast('Browser review packets must be 12 MB or smaller; use the CLI for larger packets.');
 try{
  const facts=await api('/api/verify-review-packet',{packet:await maskFileData(file)});
  const comparison=facts.comparison;
  modal('Saved operation replayed',`<div class="replay-success"><span>✓</span><div><strong>${escape(facts.kind)} packet verified</strong><p>Operation conditions and exported measurements were recomputed from saved source inputs by the core.</p></div></div>${comparison?`<p>${escape(comparison.explanation)}</p><p>Common valid pixels: ${number(comparison.common_scope_pixels)}. Change accounting: ${number(comparison.foreground_change_accounting.saved_total_delta_pixels)} px.</p>`:''}<details><summary>Verification record</summary><pre class="verification-record">${escape(JSON.stringify(facts,null,2))}</pre></details><div class="modal-notice">Internal replay establishes consistency. Origin authenticity and human review identity require separate trusted evidence.</div>`,'OFFLINE REPLAY');
 }catch(error){modal('Review packet verification failed','<p role="alert">'+escape(error.message)+'</p>','OFFLINE REPLAY');}
};
