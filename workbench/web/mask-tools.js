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
 return `<p id="maskImageContext" class="mask-input-hint"><strong>Current image: ${escape(state.session.name)} · ${state.session.width} × ${state.session.height} px</strong><br>Uploaded images keep their dimensions. The mask must match this image's pixel grid.</p><label for="maskFile">${reference?'Reference':'Prediction'} mask · binary PNG</label><input id="maskFile" type="file" accept="image/png,.png" required aria-describedby="maskDimensionStatus"><p id="maskDimensionStatus" class="mask-input-hint" role="status" aria-live="polite">Choose a mask for the current image. White (1 or 255) denotes the target; black (0) denotes background.</p>${reference?'':'<button class="secondary" id="chooseMaskImage" type="button">Choose the matching source image</button>'}<label for="maskTarget">Semantic target</label><select id="maskTarget">${Object.entries(targetNames).map(([key,name])=>`<option value="${key}">${escape(name)}</option>`).join('')}</select><label for="maskSource">${reference?'Reference provenance':'Prediction source'}</label><textarea id="maskSource" maxlength="1000" required rows="3" placeholder="${reference?'Dataset and label version, annotation procedure, or reviewer identifier.':'Tool/model name and version, settings, and any postprocessing.'}"></textarea><label class="pin-control"><input id="maskAligned" type="checkbox" required> I confirm pixel alignment with the displayed image.</label>${reference?'<label class="pin-control"><input id="referenceIndependent" type="checkbox"> The reference was prepared independently of this prediction.</label>':''}`;
}

// Read the PNG dimensions before submission; the core still validates its pixels.
function configureMaskDimensions(submitId,getImage=()=>({width:state.session.width,height:state.session.height,name:state.session.name})){
 const input=$('maskFile'),status=$('maskDimensionStatus'),button=$(submitId);let revision=0;
 const check=async()=>{
  const attempt=++revision;button.disabled=true;const file=input.files[0];if(!file)return false;
  let message='',valid=false;
  try{
   const image=await getImage();
   const header=new Uint8Array(await file.slice(0,24).arrayBuffer());
   if(header.length<24||![137,80,78,71,13,10,26,10].every((v,i)=>header[i]===v)||String.fromCharCode(...header.slice(12,16))!=='IHDR'){
    message='Choose the black-and-white PNG mask, not the source photograph.';
   }else{
    const view=new DataView(header.buffer),w=view.getUint32(16),h=view.getUint32(20);
    valid=!!image&&w===image.width&&h===image.height;
    message=image?`Image: ${image.name} · ${image.width} × ${image.height} px\nMask: ${file.name} · ${w} × ${h} px\n${valid?'Dimensions match. Ready to import.':'Dimensions differ. Choose the matching source image or mask below; your selections are kept.'}`:`Mask: ${file.name} · ${w} × ${h} px\nChoose its source image in step 1. Image dimensions are preserved.`;
   }
  }catch(error){message=error.message;}
  if(attempt!==revision||$('maskFile')!==input||input.files[0]!==file)return false;
  status.textContent=message;input.setAttribute('aria-invalid',String(!valid));
  status.dataset.match=valid?'pass':'check';
  button.disabled=!valid||state.busy;return valid;
 };
 input.addEventListener('change',check);
 button.disabled=true;
 return check;
}

async function sourceImageDimensions(file){
 if(!file)return null;
 if(file.size>12*1024*1024)throw new Error('Source image exceeds 12 MB. Choose a smaller image chip.');
 const url=URL.createObjectURL(file);
 try{
  const image=await loadImage(url),width=image.naturalWidth,height=image.naturalHeight;
  if(width*height>16_000_000)throw new Error('Source image exceeds 16 million pixels. Choose a smaller image chip.');
  return {width,height,name:file.name};
 }catch(error){throw new Error(error.message==='Could not load the image.'?'Could not read the source image. Choose a PNG, JPEG or WebP image.':error.message);}
 finally{URL.revokeObjectURL(url);}
}

function openMaskImport(paired=false){
 if(state.busy||!state.session)return;
 const initial=state.session,parent=state.selected?.id||null;
 modal('Import image and mask',`<form id="maskImportForm" class="review-form"><label for="maskImageMode">1 · Source image</label><select id="maskImageMode"><option value="new">Upload an image with its mask</option><option value="current">Use current image: ${escape(initial.name)} · ${initial.width} × ${initial.height} px</option></select><div id="pairedImageUpload"><label for="pairedImageFile">Source image · PNG, JPEG or WebP</label><input id="pairedImageFile" type="file" accept="image/png,image/jpeg,image/webp" required><p id="pairedImageInfo" class="mask-input-hint" role="status">Choose the original color image. Its dimensions will be preserved.</p></div>${maskFormFields()}<button class="primary" id="submitMaskImport" type="submit">Import and view results</button><p id="maskImportStatus" role="status" aria-live="polite"></p></form>`,'IMAGE + PREDICTION');
 $('maskFile').labels[0].textContent='2 · Target mask · black-and-white PNG';
 $('chooseMaskImage').remove();
 $('maskDimensionStatus').classList.add('mask-dimension-status');
 $('maskImageContext').remove();
 $('maskImageMode').value=paired?'new':'current';
 $('maskTarget').value=state.selected?.task?.target||$('quickTarget').value;
 const fields=document.createElement('details');fields.className='import-validity-details';fields.innerHTML='<summary>Optional valid-pixel exclusions</summary><label for="importValidityFile">Validity PNG · white includes, black excludes</label><input id="importValidityFile" type="file" accept="image/png,.png"><label for="importValiditySource">Validity source and exclusion rationale</label><textarea id="importValiditySource" maxlength="1000" rows="2"></textarea>';
 $('submitMaskImport').before(fields);
 const imageInput=$('pairedImageFile');let cachedFile=null,cachedDimensions=null,pendingSession=null,pendingFile=null;
 const getImage=async()=>{
  if($('maskImageMode').value==='current')return {width:initial.width,height:initial.height,name:initial.name};
  const file=imageInput.files[0];if(!file)return null;
  if(file!==cachedFile){cachedFile=null;cachedDimensions=await sourceImageDimensions(file);cachedFile=file;}
  return cachedDimensions;
 };
 const checkDimensions=configureMaskDimensions('submitMaskImport',getImage);
 const updateImageMode=()=>{const upload=$('maskImageMode').value==='new';$('pairedImageUpload').hidden=!upload;imageInput.dataset.fileRequired=String(upload);imageInput.required=upload&&!imageInput.dataset.englishPicker;checkDimensions();};
 $('maskImageMode').onchange=updateImageMode;updateImageMode();
 imageInput.addEventListener('change',async()=>{
  const file=imageInput.files[0],info=$('pairedImageInfo');
  try{const d=await sourceImageDimensions(file);if($('pairedImageFile')!==imageInput||imageInput.files[0]!==file)return;cachedFile=file;cachedDimensions=d;info.textContent=d?`${d.name} · ${d.width} × ${d.height} px. Original dimensions preserved.`:'Choose the original color image.';}
  catch(error){if($('pairedImageFile')!==imageInput)return;info.textContent=error.message;cachedFile=null;cachedDimensions=null;}
  await checkDimensions();
 });
 $('importValidityFile').onchange=()=>{$('importValiditySource').required=!!$('importValidityFile').files.length;};
 $('maskImportForm').onsubmit=async e=>{
  e.preventDefault();if(state.busy)return;const form=e.currentTarget,file=$('maskFile').files[0];
  if(!file||file.size>12*1024*1024)return toast('Choose a binary PNG mask no larger than 12 MB.');
  if(!await checkDimensions())return;
  if(state.busy)return;
  const target=$('maskTarget').value,source=$('maskSource').value;
  const validFile=$('importValidityFile').files[0],validSource=$('importValiditySource').value;
  if(validFile&&validFile.size>12*1024*1024)return toast('Choose a validity PNG no larger than 12 MB.');
  if(!validFile&&validSource.trim())return toast('Choose a validity mask for the supplied validity source.');
  const imageFile=imageInput.files[0],newImage=$('maskImageMode').value==='new';
  if(newImage&&!imageFile)return;
  state.busy=true;$('submitMaskImport').disabled=true;$('maskImportStatus').textContent='Validating mask pixels and saving a separate version…';refreshWorkbench();
  try{
   let session=initial;
   if(newImage){
    if(!pendingSession||pendingFile!==imageFile){pendingSession=await api('/api/session',{image:await maskFileData(imageFile),name:imageFile.name});pendingFile=imageFile;}
    session=pendingSession;
   }
   const sid=session.id;
   const request={session_id:sid,parent_run_id:newImage?null:parent,target,source,aligned:true,mask:await maskFileData(file)};
   if(validFile){request.valid_mask=await maskFileData(validFile);request.valid_source=validSource;}
   const result=await api('/api/import-mask',request);
   localStorage.setItem('geoscope-selected-'+sid,result.id);await showSession(await api('/api/session/'+sid));
   if(location.hash!=='#workbench')location.replace('#workbench');
   if($('maskImportForm')===form)closeModal();toast('Image and mask imported. Results saved as V'+result.version+'.');
  }catch(error){if($('maskImportForm')===form){$('maskImportStatus').textContent=error.message;$('submitMaskImport').disabled=false;}toast(error.message);}
  finally{state.busy=false;refreshWorkbench();}
 };
}
$('importMaskBtn').onclick=()=>openMaskImport(!!state.session?.sample);

$('evaluateReferenceBtn').onclick=()=>{
 if(state.busy||!state.selected?.mask_url)return;
 const sid=state.session.id,run=state.selected;
 modal('Evaluate against a reference',`<p>V${run.version} · ${escape(targetLabel(run))} · ${escape(run.task.roi?'Rectangle ROI':sideNames[run.task.side])}. Scores use this result's saved region only. Reference foreground must denote the positive target${run.task.invert?'; it will be complemented to match this result':''}.</p><details id="referenceInputs" open><summary>Reference inputs · change mask or provenance</summary><form id="referenceForm" class="review-form">${maskFormFields(true)}<button class="primary" id="submitReference" type="submit">Evaluate saved result</button></form></details><div id="referenceOutput"></div>`,'REFERENCE LABEL ASSESSMENT');
 $('modal').classList.add('wide-dialog');$('maskTarget').value=run.task.target;
 const checkDimensions=configureMaskDimensions('submitReference');
 const clear=()=>{if(!state.busy)$('referenceOutput').innerHTML='';};
 $('referenceForm').addEventListener('input',clear);$('referenceForm').addEventListener('change',clear);
 $('referenceForm').onsubmit=async e=>{
  e.preventDefault();if(state.busy)return;const form=e.currentTarget,file=$('maskFile').files[0];
  if(!file||file.size>12*1024*1024)return toast('Choose a binary PNG reference no larger than 12 MB.');
  if(!await checkDimensions())return;
  if(state.busy)return;
  const source=$('maskSource').value,target=$('maskTarget').value,independent=$('referenceIndependent').checked,aligned=$('maskAligned').checked;
  state.busy=true;refreshWorkbench();$('submitReference').disabled=true;
  $('referenceOutput').innerHTML='<div class="comparison-empty" role="status">Verifying prediction evidence and evaluating the reference…</div>';
  try{
   const result=await api('/api/evaluate-reference',{session_id:sid,run_id:run.id,reference:await maskFileData(file),source,target,independent,aligned});
   if($('referenceForm')!==form)return;
   const pct=v=>v==null?'Undefined':(v*100).toFixed(2)+'%';
   $('referenceOutput').innerHTML=`<div class="reference-heading"><strong>V${run.version} / Reference assessment</strong><span>${number(result.evaluated_pixels)} evaluated pixels</span></div><div class="reference-metrics">${Object.entries(result.metrics).map(([key,value])=>`<div><small>${escape({iou:'IoU',dice:'Dice',precision:'Precision',recall:'Recall',specificity:'Specificity',pixel_accuracy:'Pixel accuracy'}[key])}</small><strong>${pct(value)}</strong></div>`).join('')}</div><div class="comparison-visual"><img src="data:image/png;base64,${result.difference_png_base64}" alt="Reference comparison: mint true positives, amber false positives, magenta false negatives inside the saved region"></div><div class="comparison-legend"><span><i style="background:#45c5a1"></i>True positive · ${number(result.counts.tp)} px</span><span><i style="background:#f0ad4e"></i>False positive · ${number(result.counts.fp)} px</span><span><i style="background:#d47bde"></i>False negative · ${number(result.counts.fn)} px</span><span>True negative · ${number(result.counts.tn)} px</span></div><p><strong>Reference source:</strong> ${escape(result.reference.source)}</p><div class="modal-notice">${run.mode==='demo'?'This prediction is a procedural fixture. Its scores are software checks, not real-image model accuracy. ':''}${result.reference.independent_user_assertion?'Reference independence was asserted by the user; it has not been authenticated.':'Reference independence was not asserted. These scores must not be presented as independent validation.'} Scores depend on reference quality and pixel alignment; one image does not establish general model accuracy. Empty denominators are undefined.</div><div class="comparison-downloads"><button class="primary" id="downloadReferencePacket">Download evaluation packet ZIP ↓</button><button class="secondary" id="downloadReferenceJSON">Metrics JSON ↓</button></div><p class="mask-input-hint">The packet contains the reference, prediction evidence, metrics, error image and hash manifest. Recompute it offline with geomasklab verify-assessment.</p>`;
   $('downloadReferencePacket').onclick=()=>download(result.packet_url);
   $('referenceInputs').open=false;
   $('downloadReferenceJSON').onclick=()=>{const {difference_png_base64,packet_url,...metadata}=result;saveTextFile('geomasklab-reference-'+run.id+'.json',JSON.stringify(metadata,null,2));};
  }catch(error){if($('referenceForm')===form)$('referenceOutput').innerHTML='<div class="comparison-empty" role="alert">'+escape(error.message)+'</div>';toast(error.message);}
  finally{state.busy=false;refreshWorkbench();if($('referenceForm')===form)$('submitReference').disabled=false;}
 };
};
