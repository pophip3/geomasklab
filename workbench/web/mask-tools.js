/* Interoperable binary masks and explicit reference-label assessment. */
function maskFileData(file) {
 return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(new Error('Could not read the PNG mask.'));reader.readAsDataURL(file);});
}
function maskDownload(name,data,type) {
 const bytes=Uint8Array.from(atob(data),c=>c.charCodeAt(0));
 const url=URL.createObjectURL(new Blob([bytes],{type}));
 const a=document.createElement('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();
 setTimeout(()=>URL.revokeObjectURL(url),1000);
}
const refreshBeforeMaskTools=refreshWorkbench;
refreshWorkbench=function(...args){refreshBeforeMaskTools(...args);$('importMaskBtn').disabled=!state.session||state.busy;$('evaluateReferenceBtn').disabled=!state.selected?.mask_url||state.busy;};
refreshWorkbench();

function maskFormFields(reference=false){
 return `<label for="maskFile">${reference?'Reference':'Prediction'} mask · binary PNG</label><input id="maskFile" type="file" accept="image/png,.png" required><p class="mask-input-hint">Exact image size: ${state.session.width} × ${state.session.height} px. Use 0/1 or 0/255; white means the positive target. No resizing or thresholding.</p><label for="maskTarget">Semantic target</label><select id="maskTarget">${Object.entries(targetNames).map(([key,name])=>`<option value="${key}">${escape(name)}</option>`).join('')}</select><label for="maskSource">${reference?'Reference provenance':'Prediction source'}</label><textarea id="maskSource" maxlength="1000" required rows="3" placeholder="${reference?'Dataset and label version, annotation procedure, or reviewer identifier.':'Tool/model name and version, settings, and any postprocessing.'}"></textarea><label class="pin-control"><input id="maskAligned" type="checkbox" required> I confirm pixel alignment with the displayed image.</label>${reference?'<label class="pin-control"><input id="referenceIndependent" type="checkbox"> The reference was prepared independently of this prediction.</label>':''}`;
}

$('importMaskBtn').onclick=()=>{
 if(state.busy||!state.session)return;
 const sid=state.session.id,parent=state.selected?.id||null;
 modal('Import a prediction mask',`<p>Use a binary mask from another segmentation tool without configuring model services. A new whole-image version will start pending review.</p><form id="maskImportForm" class="review-form">${maskFormFields()}<div class="modal-notice">Use the same orientation and pixel grid as the displayed image. Source information is self-reported. Color-coded, multiclass and probability masks require explicit conversion before import.</div><button class="primary" id="submitMaskImport" type="submit">Import as a new version</button><p id="maskImportStatus" role="status"></p></form>`,'EXTERNAL PREDICTION');
 $('maskTarget').value=state.selected?.task?.target||$('quickTarget').value;
 const fields=document.createElement('div');fields.innerHTML='<label for="importValidityFile">Optional validity PNG · white includes, black excludes</label><input id="importValidityFile" type="file" accept="image/png,.png"><label for="importValiditySource">Validity source and exclusion rationale</label><textarea id="importValiditySource" maxlength="1000" rows="2"></textarea><p class="mask-input-hint">Without a validity mask, all pixels are declared valid. Prediction and validity masks have separate roles.</p>';
 $('submitMaskImport').before(fields);
 $('importValidityFile').onchange=()=>{$('importValiditySource').required=!!$('importValidityFile').files.length;};
 $('maskImportForm').onsubmit=async e=>{
  e.preventDefault();if(state.busy)return;const form=e.currentTarget,file=$('maskFile').files[0];
  if(!file||file.size>12*1024*1024)return toast('Choose a binary PNG mask no larger than 12 MB.');
  const target=$('maskTarget').value,source=$('maskSource').value;
  const validFile=$('importValidityFile').files[0],validSource=$('importValiditySource').value;
  if(validFile&&validFile.size>12*1024*1024)return toast('Choose a validity PNG no larger than 12 MB.');
  if(!validFile&&validSource.trim())return toast('Choose a validity mask for the supplied validity source.');
  state.busy=true;$('submitMaskImport').disabled=true;$('maskImportStatus').textContent='Validating mask pixels and saving a separate version…';refreshWorkbench();
  try{
   const request={session_id:sid,parent_run_id:parent,target,source,aligned:true,mask:await maskFileData(file)};
   if(validFile){request.valid_mask=await maskFileData(validFile);request.valid_source=validSource;}
   const result=await api('/api/import-mask',request);
   if(state.session?.id===sid){localStorage.setItem('geoscope-selected-'+sid,result.id);await showSession(await api('/api/session/'+sid));}
   if($('maskImportForm')===form)closeModal();toast('External mask imported. Review is pending; no inference was performed.');
  }catch(error){if($('maskImportForm')===form){$('maskImportStatus').textContent=error.message;$('submitMaskImport').disabled=false;}toast(error.message);}
  finally{state.busy=false;refreshWorkbench();}
 };
};

$('evaluateReferenceBtn').onclick=()=>{
 if(state.busy||!state.selected?.mask_url)return;
 const sid=state.session.id,run=state.selected;
 modal('Evaluate against a reference',`<p>V${run.version} · ${escape(targetLabel(run))} · ${escape(run.task.roi?'Rectangle ROI':sideNames[run.task.side])}. Scores use this result's saved region only. Reference foreground must denote the positive target${run.task.invert?'; it will be complemented to match this result':''}.</p><details id="referenceInputs" open><summary>Reference inputs · change mask or provenance</summary><form id="referenceForm" class="review-form">${maskFormFields(true)}<button class="primary" id="submitReference" type="submit">Evaluate saved result</button></form></details><div id="referenceOutput"></div>`,'REFERENCE LABEL ASSESSMENT');
 $('modal').classList.add('wide-dialog');$('maskTarget').value=run.task.target;
 const clear=()=>{if(!state.busy)$('referenceOutput').innerHTML='';};
 $('referenceForm').addEventListener('input',clear);$('referenceForm').addEventListener('change',clear);
 $('referenceForm').onsubmit=async e=>{
  e.preventDefault();if(state.busy)return;const form=e.currentTarget,file=$('maskFile').files[0];
  if(!file||file.size>12*1024*1024)return toast('Choose a binary PNG reference no larger than 12 MB.');
  const source=$('maskSource').value,target=$('maskTarget').value,independent=$('referenceIndependent').checked,aligned=$('maskAligned').checked;
  state.busy=true;refreshWorkbench();$('submitReference').disabled=true;
  $('referenceOutput').innerHTML='<div class="comparison-empty" role="status">Verifying prediction evidence and evaluating the reference…</div>';
  try{
   const result=await api('/api/evaluate-reference',{session_id:sid,run_id:run.id,reference:await maskFileData(file),source,target,independent,aligned});
   if($('referenceForm')!==form)return;
   const pct=v=>v==null?'Undefined':(v*100).toFixed(2)+'%';
   $('referenceOutput').innerHTML=`<div class="reference-heading"><strong>V${run.version} / Reference assessment</strong><span>${number(result.evaluated_pixels)} evaluated pixels</span></div><div class="reference-metrics">${Object.entries(result.metrics).map(([key,value])=>`<div><small>${escape({iou:'IoU',dice:'Dice',precision:'Precision',recall:'Recall',specificity:'Specificity',pixel_accuracy:'Pixel accuracy'}[key])}</small><strong>${pct(value)}</strong></div>`).join('')}</div><div class="comparison-visual"><img src="data:image/png;base64,${result.difference_png_base64}" alt="Reference comparison: mint true positives, amber false positives, magenta false negatives inside the saved region"></div><div class="comparison-legend"><span><i style="background:#45c5a1"></i>True positive · ${number(result.counts.tp)} px</span><span><i style="background:#f0ad4e"></i>False positive · ${number(result.counts.fp)} px</span><span><i style="background:#d47bde"></i>False negative · ${number(result.counts.fn)} px</span><span>True negative · ${number(result.counts.tn)} px</span></div><p><strong>Reference source:</strong> ${escape(result.reference.source)}</p><div class="modal-notice">${run.mode==='demo'?'This prediction is a procedural fixture. Its scores are software checks, not real-image model accuracy. ':''}${result.reference.independent_user_assertion?'Reference independence was asserted by the user; it has not been authenticated.':'Reference independence was not asserted. These scores must not be presented as independent validation.'} Scores depend on reference quality and pixel alignment; one image does not establish general model accuracy. Empty denominators are undefined.</div><div class="comparison-downloads"><button class="primary" id="downloadReferencePacket">Download evaluation packet ZIP ↓</button><button class="secondary" id="downloadReferenceJSON">Metrics JSON ↓</button></div><p class="mask-input-hint">The packet contains the reference, prediction evidence, metrics, error image and hash manifest. Recompute it offline with reference_evaluation.py.</p>`;
   $('downloadReferencePacket').onclick=()=>download(result.packet_url);
   $('referenceInputs').open=false;
   $('downloadReferenceJSON').onclick=()=>{const {difference_png_base64,packet_url,...metadata}=result;saveTextFile('geomasklab-reference-'+run.id+'.json',JSON.stringify(metadata,null,2));};
  }catch(error){if($('referenceForm')===form)$('referenceOutput').innerHTML='<div class="comparison-empty" role="alert">'+escape(error.message)+'</div>';toast(error.message);}
  finally{state.busy=false;refreshWorkbench();if($('referenceForm')===form)$('submitReference').disabled=false;}
 };
};
