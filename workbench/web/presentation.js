/* Additive UI enhancements. Never infer measurements, accuracy or geographic metadata. */
(() => {
 'use strict';
 const workspace=document.querySelector('.workspace');
 const symbol=(id,body)=>document.querySelector('.svg-defs defs').insertAdjacentHTML('beforeend',`<symbol id="i-${id}" viewBox="0 0 24 24">${body}</symbol>`);
 symbol('split','<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M12 3v18M8 9l-3 3 3 3m8-6 3 3-3 3"/>');
 symbol('chevron','<path d="m15 5-7 7 7 7"/>');
 symbol('warning','<path d="m12 3 10 18H2Z"/><path d="M12 9v5m0 3v1"/>');
 symbol('home','<path d="m3 10 9-7 9 7v11h-6v-7H9v7H3Z"/>');
 symbol('trash','<path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7"/>');
 const addButton=(id,text,cls='secondary')=>{const b=document.createElement('button');b.id=id;b.type='button';b.className=cls;b.innerHTML=text;return b;};
 const setAttribute=(node,key,value)=>{if(node.getAttribute(key)!==String(value))node.setAttribute(key,value);};

 // Introduction is the default route. Saved sessions remain available behind it.
 const landing=document.createElement('section');landing.className='landing';landing.id='landing';
 landing.setAttribute('aria-label','GeoMaskLab project introduction');
 landing.innerHTML=`<div class="landing-top"><span>OPEN RESEARCH SOFTWARE / REMOTE SENSING</span><div class="landing-links"><a href="help.html" target="_blank" rel="noopener">Documentation ↗</a><a href="https://github.com/pophip3/geomasklab" target="_blank" rel="noopener">GitHub ↗</a><button id="citationBtn" type="button">Cite the software</button></div></div><div class="landing-hero"><div class="landing-copy"><div class="eyebrow">GEOMASKLAB · REPLAYABLE SEGMENTATION EVIDENCE</div><h1>See the mask.<br><span>Keep the evidence.</span></h1><p>A remote-sensing workbench for scoped mask measurements, fair comparisons and portable review records.</p><div class="landing-actions"><button id="enterWorkbench" class="primary" type="button">${icon('arrow')}Enter workbench</button><button id="loadSample" class="secondary" type="button">${icon('play')}Run an offline example</button></div><p class="landing-note">Start with a built-in procedural example. No model download, account or prepared ZIP required.</p><div class="landing-points"><span>${icon('check')}Explicit valid pixels</span><span>${icon('check')}Independent replay</span><span>${icon('check')}Portable evidence</span></div></div><div class="landing-visual"><div class="landing-visual-head"><span>OBSERVATION → MASK</span><span>DENVER / NAIP 2019</span></div><div class="landing-image"><img src="assets/naip-preview.png" alt="USDA NAIP aerial image of Denver, 2019"><canvas id="landingMask" width="512" height="512" aria-label="Animated actual excess-green color-baseline mask, not a model prediction"></canvas><div class="landing-scan"></div><div class="landing-chip">COLOR BASELINE · UNVALIDATED VEGETATION CANDIDATES</div></div><div class="landing-visual-foot"><span>USDA-FSA-APFO / USGS The National Map<br>Real imagery · Color-baseline overlay · No model inference</span><button id="pauseLanding" type="button" aria-pressed="false" aria-label="Pause preview animation">Pause</button></div></div></div><div class="landing-architecture"><div><span>01 / MEASURE</span><strong>One explicit analysis domain</strong><p>Bind the image, prediction, study region and valid pixels to the same recorded calculation.</p></div><div><span>02 / REVIEW</span><strong>Inspect before you conclude</strong><p>Compare masks under declared conditions. Review candidate boundaries and retain decisions.</p></div><div><span>03 / REPLAY</span><strong>Evidence that travels</strong><p>Export the recorded inputs and measurements. Recalculate offline with the same Python core.</p></div></div>`;
 document.querySelector('main').prepend(landing);
 const home=addButton('homeBtn',`${icon('home')}Overview`,'text-button home-button');home.title='Open the project introduction';home.setAttribute('aria-label','Open the project introduction');document.querySelector('.top-actions').prepend(home);
 // The legacy global history() shadows window.history. Fragment replacement uses Location.
 const navigateHome=()=>{if($('modal').open)closeModal();landing.hidden=false;document.body.classList.add('presentation-home');home.classList.add('active');$('workspaceBtn').classList.remove('active');document.querySelector('.landing-visual').classList.toggle('paused',$('pauseLanding').getAttribute('aria-pressed')==='true');if(location.hash!=='#home')location.replace('#home');window.scrollTo(0,0);};
 const navigateWorkbench=()=>{landing.hidden=true;document.body.classList.remove('presentation-home');home.classList.remove('active');$('workspaceBtn').classList.add('active');document.querySelector('.landing-visual').classList.add('paused');if(location.hash!=='#workbench')location.replace('#workbench');window.scrollTo(0,0);$('workspaceBtn').focus();};
 home.onclick=navigateHome;$('enterWorkbench').onclick=navigateWorkbench;
 $('workspaceBtn').addEventListener('click',navigateWorkbench);
 window.addEventListener('hashchange',()=>{if(location.hash==='#workbench')navigateWorkbench();else navigateHome();});
 if(location.hash==='#workbench')navigateWorkbench();else navigateHome();
 $('pauseLanding').onclick=()=>{const paused=$('pauseLanding').getAttribute('aria-pressed')!=='true';$('pauseLanding').setAttribute('aria-pressed',String(paused));$('pauseLanding').textContent=paused?'Resume':'Pause';$('pauseLanding').setAttribute('aria-label',paused?'Resume preview animation':'Pause preview animation');document.querySelector('.landing-visual').classList.toggle('paused',paused);};
 $('citationBtn').onclick=()=>modal('Cite the software',`<p>Use the exact software version and archived release you used in your work. A publication DOI is not recorded in this workbench.</p><pre>${escape(`Xing, Yun. GeoMaskLab, version ${state.status?.version||'not yet available'}.\nReplayable measurements and portable evidence for segmentation masks.\nRepository: https://github.com/pophip3/geomasklab`)}</pre><p>Yun Xing · Hohai University · ORCID 0009-0009-1746-5019. See CITATION.cff in the fixed release; an archival DOI remains pending.</p>`,'SOFTWARE CITATION');
 loadImage('assets/naip-preview-mask.png').then(image=>{const c=$('landingMask'),ctx=c.getContext('2d',{willReadFrequently:true});ctx.drawImage(image,0,0,512,512);const d=ctx.getImageData(0,0,512,512);for(let i=0;i<d.data.length;i+=4){const on=d.data[i]>127;d.data[i]=45;d.data[i+1]=212;d.data[i+2]=191;d.data[i+3]=on?135:0;}ctx.putImageData(d,0,0);}).catch(()=>{$('landingMask').hidden=true;document.querySelector('.landing-scan').hidden=true;document.querySelector('.landing-chip').textContent='NAIP OBSERVATION · PREVIEW MASK UNAVAILABLE';});
 let exampleLoading=false;
 $('loadSample').onclick=async()=>{
  if(exampleLoading||state.busy)return toast('Wait for the current task to finish.');
  exampleLoading=true;$('loadSample').disabled=true;$('loadSample').setAttribute('aria-busy','true');
  try{state.mode='demo';localStorage.setItem('geoscope-mode','demo');const before=state.session?.id;await newExperiment('urban');if(!state.session||state.session.id===before)return; navigateWorkbench();await run('Extract only buildings in the whole image.');}
  finally{exampleLoading=false;$('loadSample').disabled=false;$('loadSample').removeAttribute('aria-busy');}
 };

 // Layout controls do not replace task handlers or result renderers.
 const controls=document.createElement('div');controls.className='canvas-layout-controls';
 const collapse=addButton('collapseAssistant',`${icon('chevron')}Hide assistant`);collapse.setAttribute('aria-controls','assistantPanel');collapse.setAttribute('aria-expanded','true');
 document.querySelector('.conversation').id='assistantPanel';
 const hideResults=addButton('collapseResults',`${icon('layers')}Hide results`);hideResults.setAttribute('aria-controls','resultsPanel');hideResults.setAttribute('aria-expanded','true');document.querySelector('.results-panel').id='resultsPanel';
 const focus=addButton('canvasFocus',`${icon('fit')}Focus canvas`);focus.setAttribute('aria-pressed','false');
 controls.append(collapse,hideResults,focus);document.querySelector('.image-heading').append(controls);
 const rail=addButton('restoreAssistant',`${icon('chevron')}Show assistant`,'assistant-rail');rail.setAttribute('aria-controls','assistantPanel');workspace.prepend(rail);
 const updateLayout=()=>{const hidden=workspace.classList.contains('assistant-collapsed'),focused=workspace.classList.contains('canvas-focus'),resultsHidden=workspace.classList.contains('results-collapsed');for(const [button,name,glyph] of [[collapse,hidden?'Show assistant':'Hide assistant','chevron'],[hideResults,resultsHidden?'Show results':'Hide results','layers'],[focus,focused?'Exit focus':'Focus canvas','fit']]){button.innerHTML=icon(glyph);button.title=name;button.setAttribute('aria-label',name);}collapse.setAttribute('aria-expanded',String(!hidden));hideResults.setAttribute('aria-expanded',String(!resultsHidden));focus.setAttribute('aria-pressed',String(focused));collapse.hidden=hideResults.hidden=focused;};
 collapse.onclick=()=>{workspace.classList.toggle('assistant-collapsed');updateLayout();};rail.onclick=()=>{workspace.classList.remove('assistant-collapsed');updateLayout();collapse.focus();};
 hideResults.onclick=()=>{workspace.classList.toggle('results-collapsed');updateLayout();};
 focus.onclick=()=>{workspace.classList.toggle('canvas-focus');updateLayout();};
 document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!$('modal').open&&workspace.classList.contains('canvas-focus')){workspace.classList.remove('canvas-focus');updateLayout();focus.focus();}});
 document.querySelectorAll('[data-view]').forEach(button=>{button.prepend(new DOMParser().parseFromString(icon({original:'image',overlay:'layers',mask:'grid',compare:'split'}[button.dataset.view]),'text/html').body.firstChild);button.title=button.dataset.view==='compare'?'Slide between original image and saved mask overlay':button.textContent.trim();});
 const drawIcon=document.createElement('span');drawIcon.className='roi-icon';drawIcon.innerHTML=icon('target');$('drawRoiBtn').before(drawIcon);
 $('clearRoiBtn').insertAdjacentHTML('afterbegin',icon('trash'));$('clearRoiBtn').title='Clear the drawn study rectangle';
 const scale=document.createElement('div');scale.className='pixel-scale';scale.innerHTML='<span></span><i class="pixel-scale-line"></i>';scale.title='Pixel distance in the displayed image; physical distance and geographic north are not inferred.';$('imageStage').append(scale);
 const nicePixels=value=>{const p=10**Math.floor(Math.log10(Math.max(1,value)));return Math.max(1,[5,2,1].map(n=>n*p).find(n=>n<=value)||p/2);};
 const updateScale=()=>{if(!state.original)return;const rect=$('imageCanvas').getBoundingClientRect(),width=state.original.naturalWidth;if(!rect.width){scale.hidden=true;return;}scale.hidden=false;const pixels=nicePixels(80*width/rect.width);scale.querySelector('span').textContent=`${pixels} px`;scale.querySelector('i').style.width=(pixels*rect.width/width)+'px';};
 new ResizeObserver(updateScale).observe($('imageCanvas'));new MutationObserver(updateScale).observe($('imageCanvas'),{attributes:true,attributeFilter:['style','width','height']});
 $('legend').title='Foreground in the saved target mask. Uncolored pixels are background.';
 // Progressive disclosure: retain existing nodes and their handlers behind short labels.
 const resultsBody=document.querySelector('.results-body');
 const measurementDetails=document.createElement('details');measurementDetails.id='measurementDetails';measurementDetails.className='measurement-details';measurementDetails.innerHTML='<summary>Measurement details</summary><div class="measurement-details-body"></div>';
 const detailBody=measurementDetails.lastElementChild;
 const secondaryMetrics=document.createElement('dl');secondaryMetrics.className='metrics secondary-metrics';
 for(const id of ['scopeValue','qualityValue','totalValue','timeValue'])secondaryMetrics.append($(id).closest('div'));
 for(const node of [$('resultTitle'),$('resultSubtitle'),$('regionCoverage').parentElement,$('validitySummary')])detailBody.append(node);
 detailBody.append(secondaryMetrics,$('checksPanel'),$('reviewSummary'));
 const recordActions=document.createElement('div');recordActions.className='record-detail-actions';recordActions.append($('reportBtn'),$('detailBtn'));detailBody.append(recordActions);
 resultsBody.insertBefore(measurementDetails,$('artifactBox'));
 const compactTitle=document.createElement('h3');compactTitle.id='compactResultTitle';
 const compactContext=document.createElement('p');compactContext.id='compactResultContext';document.querySelector('.result-title').append(compactTitle,compactContext);
 const taskSettings=document.createElement('details');taskSettings.className='task-settings';taskSettings.innerHTML='<summary>Task settings & info</summary>';
 for(const node of [document.querySelector('.quality-control'),$('capabilityNote'),$('composerNote')])taskSettings.append(node);
 document.querySelector('.composer-wrap').append(taskSettings);
 const toolMenu=document.createElement('details');toolMenu.className='more-tools';toolMenu.innerHTML='<summary>More ▾</summary><div class="more-tools-menu"></div>';
 for(const id of ['evaluateReferenceBtn','offlineBatchBtn','batchBtn','verifyPacketBtn','guideBtn','libraryBtn'])toolMenu.lastElementChild.append($(id));
 document.querySelector('.investigation-bar>div:last-child').append(toolMenu);
 toolMenu.addEventListener('click',event=>{if(event.target.closest('button'))toolMenu.open=false;});
 document.addEventListener('click',event=>{if(!toolMenu.contains(event.target))toolMenu.open=false;});
 document.addEventListener('keydown',event=>{if(event.key==='Escape')toolMenu.open=false;});
 document.querySelector('.landing-copy>p').textContent='Measure segmentation masks and export replayable evidence.';
 const ledger=document.querySelector('.results-ledger'),ledgerDisclosure=document.createElement('details');ledgerDisclosure.className='ledger-disclosure';ledgerDisclosure.innerHTML='<summary>Result history</summary>';ledger.before(ledgerDisclosure);ledgerDisclosure.append(ledger);
 $('uploadBtn').before($('editExperimentBtn'));
 const labels={importMaskBtn:'Import mask',inspectComponentsBtn:'Inspect',evaluateReferenceBtn:'Reference evaluation',offlineBatchBtn:'Offline batch',batchBtn:'Model / demo batch',verifyPacketBtn:'Replay packet',guideBtn:'Workflow guide',editExperimentBtn:'Edit',recalculateBtn:'Region & validity',reviewBtn:'Review result',reportBtn:'Report',compareResultsBtn:'Compare versions',ledgerCompareBtn:'Compare',ledgerExportBtn:'Export CSV'};
 for(const [id,label] of Object.entries(labels))$(id).textContent=label;
 document.querySelector('.page-heading h1').textContent='Workbench';
 for(const [selector,label] of [['.conversation .panel-heading h2','Task'],['.image-heading h2','Image'],['.results-panel .panel-heading h2','Results'],['.artifact-box strong','Export'],['.version-heading .eyebrow','Versions'],['.ledger-heading h2','Saved results']])document.querySelector(selector).textContent=label;
 $('areaValue').closest('div').querySelector('dt').textContent='Mask pixels';
 const coverageCounts=document.querySelector('#coverageCard>small');coverageCounts.id='coverageCounts';coverageCounts.title='Foreground pixels / all image pixels: the denominator for whole-image coverage.';
 const coverageRing=$('ringValue');coverageRing.setAttribute('pathLength','100');document.querySelector('.coverage-ring').setAttribute('aria-hidden','true');
 $('candidateValue').closest('div').querySelector('dt').textContent='Candidates';
 $('candidateValue').closest('div').title='Connected components in the saved mask; candidates, not validated object counts.';
 $('query').placeholder='Ask a follow-up…';$('query').title='Enter to send; Shift+Enter for a new line.';
 const labelText=(id,value)=>{if($(id).textContent!==value)$(id).textContent=value;};
 const syncCompact=()=>{
  const r=state.selected;
  const metrics=r?.mask_url?r.metrics:null,ratio=metrics?.area_ratio;
  const coverage=typeof ratio==='number'&&Number.isFinite(ratio)?Math.max(0,Math.min(100,ratio*100)):0;
  coverageRing.style.strokeDasharray=`${coverage} ${100-coverage}`;
  labelText('coverageCounts',metrics&&Number.isFinite(metrics.pixel_area)&&Number.isFinite(metrics.total_pixels)?`${number(metrics.pixel_area)} / ${number(metrics.total_pixels)} px`:'');
  coverageCounts.hidden=!coverageCounts.textContent;
  setAttribute($('connectionBtn'),'data-mode',state.mode);
  const showingAnswer=!$('answerCard').hidden;
  const target=showingAnswer?'Scene response':r?.mask_url?targetLabel(r):'No result yet';
  labelText('compactResultTitle',target.charAt(0).toUpperCase()+target.slice(1));
  const validityNote=r?.metrics?.validity_measurements?.excluded_region_pixels>0?' · Validity applied':'';
  labelText('compactResultContext',showingAnswer?'Image description':r?.mask_url?`V${r.version} · ${r.task?.roi?'Rectangle':sideNames[r.task?.side]||'Recorded scope'}${validityNote}`:'Choose a target and run.');
  measurementDetails.hidden=showingAnswer||!r?.mask_url;
  if(state.session){labelText('imageMeta',`${state.session.width} × ${state.session.height} px`);labelText('imageName',state.session.name);}
  if(r?.mask_url){const ctx=$('contextChip').querySelector('span:last-child');ctx.title=`Continue from V${r.version} · ${targetLabel(r)}`;if(ctx.textContent!==`Using V${r.version}`)ctx.textContent=`Using V${r.version}`;}
  $('provenanceLabel').title=state.session?.source||'Data source';
  $('imageWatermark').title=r?.provenance?.perception||state.session?.source||'Image source';
  labelText('imageWatermark',state.view==='original'?(state.session?.sample?'Demo image':'Image'):r?.mode==='demo'?'Demo mask':r?.mode==='external'?'Imported mask':'Model mask');
  labelText('provenanceLabel',state.session?.imported_evidence?'Imported evidence':state.mode==='demo'?(state.session?.sample?'Demo · procedural mask':'Uploaded image'):'Model services');
  document.querySelectorAll('#versions button').forEach(button=>{const saved=state.session?.runs.find(run=>run.id===button.dataset.run);if(saved){button.title=`V${saved.version} · ${saved.task?.roi?'Rectangle':sideNames[saved.task?.side]} · ${targetLabel(saved)}`;const text=`V${saved.version}`;if(button.textContent!==text)button.textContent=text;}});
 };
 const compactMessage=(message,run)=>{
  if(!run?.mask_url)return;
  const bubble=message.querySelector('.bubble');if(!bubble)return;
  const explanation=document.createElement('details');explanation.className='message-details';explanation.innerHTML='<summary>Details</summary>';
  bubble.before(explanation);explanation.append(bubble);const meta=message.querySelector('.message-meta');if(meta)explanation.append(meta);
  const reply=document.createElement('p');reply.className='compact-reply';reply.textContent=`Mask saved · V${run.version}`;explanation.before(reply);
  message.querySelectorAll('[data-prompt]').forEach(button=>{button.title=button.dataset.prompt;const prompt=button.dataset.prompt;button.textContent=/^Export/.test(prompt)?'Export':prompt.includes('whole image')?'Whole image':prompt.includes('right half')?'Right half':'Left half';});
 };
 const addMessageBeforeCompact=addMessage;
 addMessage=function(role,text,kind='',run=null,...args){addMessageBeforeCompact(role,text,kind,run,...args);if(role==='assistant')compactMessage($('chat').lastElementChild,run);};
 updateLayout();
 const syncPresentation=()=>{
  const r=state.selected,review=r?.semantic_review?.state||'pending';setAttribute($('resultStatus'),'data-review',r?.mask_url?review:'none');setAttribute($('reviewPanel'),'data-review',review);
  setAttribute($('checksPanel'),'data-integrity',$('checkCount').textContent.replace(/\s/g,'')==='3/3'?'passed':'pending');
  $('figureExportBtn').disabled=!r?.mask_url||!state.mask||state.busy;
  document.querySelectorAll('[data-view]').forEach(b=>setAttribute(b,'aria-pressed',b.classList.contains('selected')));
  setAttribute($('sendBtn'),'aria-busy',state.busy);setAttribute($('quickRunBtn'),'aria-busy',state.busy);
  // Presentation of real error messages; no invented validation checklist.
  $('modal').classList.toggle('validation-dialog',/fail|invalid|not running|error/i.test($('modalTitle').textContent));
  syncCompact();
 };
 document.querySelector('.modal-header').insertAdjacentHTML('afterbegin',`<svg class="validation-symbol" aria-hidden="true"><use href="#i-warning"/></svg>`);
 const figureButton=addButton('figureExportBtn',`${icon('down')}Export figure`,'secondary figure-button');figureButton.title='Export a paper figure';figureButton.disabled=true;document.querySelector('.artifact-box').append(figureButton);
 const observed=new MutationObserver(syncPresentation);for(const id of ['resultStatus','checkCount','reviewState','modalTitle','versions','imageWatermark','connectionLabel'])observed.observe($(id),{childList:true,subtree:true,characterData:true});
 new MutationObserver(syncPresentation).observe($('sendBtn'),{attributes:true,attributeFilter:['disabled']});
 new MutationObserver(syncPresentation).observe(document.querySelector('.view-tabs'),{attributes:true,subtree:true,attributeFilter:['class']});syncPresentation();
 const refreshBeforePresentation=refreshWorkbench;
 refreshWorkbench=function(...args){const result=refreshBeforePresentation(...args);syncPresentation();return result;};

 // Publication figures render from the selected saved version, not transient ROI/zoom.
 const percent=v=>v==null?'undefined':(v*100).toFixed(2)+'%';
 function coloredMask(mask){const c=document.createElement('canvas');c.width=mask.naturalWidth;c.height=mask.naturalHeight;const x=c.getContext('2d',{willReadFrequently:true});x.drawImage(mask,0,0);const d=x.getImageData(0,0,c.width,c.height);for(let i=0;i<d.data.length;i+=4){const on=d.data[i]>127;d.data[i]=45;d.data[i+1]=212;d.data[i+2]=191;d.data[i+3]=on?140:0;}x.putImageData(d,0,0);return c;}
 function wrapText(ctx,text,x,y,maxWidth,lineHeight){let line='';for(const word of String(text).split(/\s+/)){const next=line?line+' '+word:word;if(line&&ctx.measureText(next).width>maxWidth){ctx.fillText(line,x,y);line=word;y+=lineHeight;}else line=next;}ctx.fillText(line,x,y);return y+lineHeight;}
 function renderFigure(snapshot,options){
  const {original,mask,run:r}=snapshot,w=original.naturalWidth,h=original.naturalHeight;
  const panels=options.layout==='single'?['overlay']:options.layout==='pair'?['original','overlay']:['original','overlay','mask'];
  const logicalWidth=1800,gap=24,margin=48,panelWidth=(logicalWidth-margin*2-gap*(panels.length-1))/panels.length;
  const panelHeight=Math.min(1000,Math.max(340,panelWidth*h/w)),top=options.labels?106:70;
  const figure=document.createElement('canvas');figure.width=Math.round(180/25.4*options.dpi);const factor=figure.width/logicalWidth;
  figure.height=Math.ceil((top+panelHeight+(options.legend?65:24)+(options.caption?300:90))*factor);
  const ctx=figure.getContext('2d');ctx.scale(factor,factor);ctx.fillStyle='#fff';ctx.fillRect(0,0,logicalWidth,figure.height/factor);
  ctx.fillStyle='#0f172a';ctx.font='bold 28px Arial';ctx.fillText('GeoMaskLab / '+targetLabel(r),margin,42);
  ctx.fillStyle='#475569';ctx.font='18px Arial';ctx.fillText(`V${r.version} · ${executionLabel(r)} · ${reviewNames[r.semantic_review?.state||'pending']}`,margin,68);
  const overlay=coloredMask(mask);
  panels.forEach((mode,index)=>{
   const px=margin+index*(panelWidth+gap),s=Math.min(panelWidth/w,panelHeight/h),iw=w*s,ih=h*s,x=px+(panelWidth-iw)/2,y=top+(panelHeight-ih)/2;
   if(options.labels){ctx.fillStyle='#0f172a';ctx.font='bold 21px Arial';ctx.fillText(`(${String.fromCharCode(97+index)}) ${mode==='original'?'Original image':mode==='overlay'?'Saved mask overlay':'Binary target mask'}`,px,top-14);}
   ctx.fillStyle='#f1f5f9';ctx.fillRect(px,top,panelWidth,panelHeight);ctx.imageSmoothingEnabled=mode!=='mask';ctx.drawImage(mode==='mask'?mask:original,x,y,iw,ih);if(mode==='overlay')ctx.drawImage(overlay,x,y,iw,ih);
   if(mode!=='original'&&r.task?.roi?.xyxy){const [ax,ay,bx,by]=r.task.roi.xyxy;ctx.save();ctx.strokeStyle='#f59e0b';ctx.lineWidth=2;ctx.setLineDash([8,5]);ctx.strokeRect(x+ax*s,y+ay*s,(bx-ax)*s,(by-ay)*s);ctx.restore();}
   if(options.scale){const length=nicePixels(w*.2),bar=length*s;ctx.fillStyle='#0f172ae8';ctx.fillRect(x+12,y+ih-53,Math.max(bar+24,148),42);ctx.strokeStyle='#fff';ctx.lineWidth=3;ctx.beginPath();ctx.moveTo(x+22,y+ih-27);ctx.lineTo(x+22+bar,y+ih-27);ctx.stroke();ctx.fillStyle='#fff';ctx.font='16px Consolas';ctx.fillText(`${length} px`,x+22,y+ih-38);}
  });
  let y=top+panelHeight+28;
  if(options.legend){ctx.fillStyle='#2dd4bf';ctx.fillRect(margin,y-16,17,17);ctx.fillStyle='#0f172a';ctx.font='19px Arial';ctx.fillText('Target foreground (overlay)',margin+27,y);ctx.fillStyle='#fff';ctx.strokeStyle='#64748b';ctx.fillRect(535,y-16,17,17);ctx.strokeRect(535,y-16,17,17);ctx.fillStyle='#0f172a';ctx.fillText('Foreground (binary mask)',562,y);ctx.fillRect(1020,y-16,17,17);ctx.fillText('Background (binary mask)',1047,y);y+=32;}
  if(options.caption){
   const m=r.metrics,valid=m.validity_measurements;
   ctx.fillStyle='#334155';ctx.font='19px Arial';
   y=wrapText(ctx,`Foreground ${number(m.pixel_area)} px | Whole-image coverage ${percent(m.area_ratio)} | Region coverage ${percent(m.scope_area_ratio)} | Valid-region coverage ${percent(valid?valid.coverage_of_valid_region:m.scope_area_ratio)}`,margin,y,logicalWidth-margin*2,27);
   y=wrapText(ctx,`Image ${w} × ${h} px | Scope: ${r.analysis_config?.region?.kind|| (r.task?.roi?'rectangle':sideNames[r.task?.side]||'recorded domain')} | ${valid?number(valid.excluded_region_pixels)+' region pixels excluded':'All image pixels declared valid'}. Image coordinates: origin top left, X right, Y down.`,margin,y,logicalWidth-margin*2,27);
   y=wrapText(ctx,'Masks and coverage are copied from the saved result. Integrity checks do not establish semantic accuracy. See the evidence bundle for analysis-domain and validity masks.',margin,y,logicalWidth-margin*2,27);
  }
  ctx.fillStyle='#64748b';ctx.font='16px Arial';const bottom=wrapText(ctx,`Run ${r.id} | ${snapshot.session.name} | Pixel units; geographic scale, CRS and north are not recorded in this browser session.`,margin,y+8,logicalWidth-margin*2,23);
  const cropped=document.createElement('canvas');cropped.width=figure.width;cropped.height=Math.ceil((bottom+margin)*factor);cropped.getContext('2d').drawImage(figure,0,0);return cropped;
 }
 function saveBlob(name,blob){const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),10000);}
 const canvasBlob=(canvas,type='image/png')=>new Promise((resolve,reject)=>canvas.toBlob(b=>b?resolve(b):reject(new Error('Image encoding failed.')),type,.98));
 function crc32(bytes){let c=0xffffffff;for(const b of bytes){c^=b;for(let k=0;k<8;k++)c=(c>>>1)^((c&1)?0xedb88320:0);}return (c^0xffffffff)>>>0;}
 async function pngWithDpi(canvas,dpi){
  const bytes=new Uint8Array(await (await canvasBlob(canvas)).arrayBuffer()),chunk=new Uint8Array(21),v=new DataView(chunk.buffer),ppm=Math.round(dpi/0.0254);
  v.setUint32(0,9);chunk.set([112,72,89,115],4);v.setUint32(8,ppm);v.setUint32(12,ppm);chunk[16]=1;v.setUint32(17,crc32(chunk.subarray(4,17)));
  // Browser PNG encoders may include a default pHYs; replace it rather than duplicate.
  const parts=[bytes.subarray(0,33),chunk];let offset=33;while(offset<bytes.length){const n=new DataView(bytes.buffer,bytes.byteOffset+offset,4).getUint32(0),end=offset+12+n;const type=String.fromCharCode(...bytes.subarray(offset+4,offset+8));if(type!=='pHYs')parts.push(bytes.subarray(offset,end));offset=end;}
  return new Blob(parts,{type:'image/png'});
 }
 async function rasterPdf(canvas,dpi){
  const jpeg=new Uint8Array(await (await canvasBlob(canvas,'image/jpeg')).arrayBuffer()),encoder=new TextEncoder(),parts=[],offsets=[0];let size=0;
  const put=data=>{const bytes=typeof data==='string'?encoder.encode(data):data;parts.push(bytes);size+=bytes.length;};
  const object=(id,body)=>{offsets[id]=size;put(`${id} 0 obj\n${body}\nendobj\n`);};const pw=(canvas.width/dpi*72).toFixed(3),ph=(canvas.height/dpi*72).toFixed(3);
  put('%PDF-1.4\n');object(1,'<< /Type /Catalog /Pages 2 0 R >>');object(2,'<< /Type /Pages /Kids [3 0 R] /Count 1 >>');
  object(3,`<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${pw} ${ph}] /Resources << /XObject << /Im0 4 0 R >> >> /Contents 5 0 R >>`);
  offsets[4]=size;put(`4 0 obj\n<< /Type /XObject /Subtype /Image /Width ${canvas.width} /Height ${canvas.height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${jpeg.length} >>\nstream\n`);put(jpeg);put('\nendstream\nendobj\n');
  const commands=`q\n${pw} 0 0 ${ph} 0 0 cm\n/Im0 Do\nQ\n`;object(5,`<< /Length ${encoder.encode(commands).length} >>\nstream\n${commands}endstream`);
  const xref=size;put('xref\n0 6\n0000000000 65535 f \n');for(let i=1;i<=5;i++)put(`${String(offsets[i]).padStart(10,'0')} 00000 n \n`);put(`trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF`);
  return new Blob(parts,{type:'application/pdf'});
 }
 async function hashFile(url){const response=await fetch(url);if(!response.ok)throw new Error('Could not read the saved input for hashing.');const bytes=await response.arrayBuffer();return [...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(b=>b.toString(16).padStart(2,'0')).join('');}
 async function figureConfig(snapshot,options){const r=snapshot.run;const [imageHash,maskHash]=await Promise.all([hashFile(snapshot.session.image_url),hashFile(r.mask_url)]);return {schema:'geomasklab-publication-figure/1.0',exported_at:new Date().toISOString(),software:{name:'GeoMaskLab',version:state.status?.version||null},input:{image_sha256:imageHash,hash_basis:'Saved normalized original.png bytes; not necessarily the initially uploaded file bytes',width:snapshot.original.naturalWidth,height:snapshot.original.naturalHeight,source:snapshot.session.source},mask:{sha256:maskHash,run_id:r.id,version:r.version},figure:options,task:r.task,analysis_config:r.analysis_config||null,measurements:r.metrics,provenance:r.provenance,execution_kind:r.execution_kind||null,execution_mode:r.mode,recorded_validation:r.validation||r.checks||null,trace:r.trace||[],semantic_review:r.semantic_review||null,perception_revision:r.provenance?.perception_revision||null,model_version:r.provenance?.model_version||null,weights_revision:r.provenance?.weights_revision||null,random_seed:r.task?.seed??null,missing_metadata_note:'Null means unavailable in the saved browser record. No model revision, weight version, random seed, geographic orientation or validation fact is inferred. Full replay requires the original evidence bundle.'};}
 figureButton.onclick=()=>{
  if(state.busy||!state.selected?.mask_url||!state.mask)return;
  const snapshot={session:JSON.parse(JSON.stringify(state.session)),run:JSON.parse(JSON.stringify(state.selected)),original:state.original,mask:state.mask};let preview;
  modal('Export a paper figure',`<p>Render the selected saved result at a fixed print width of 180 mm. Export settings change the figure, not the measurements.</p><div class="figure-options"><label for="figureLayout">Layout<select id="figureLayout"><option value="pair">Original / overlay</option><option value="triple">Original / overlay / binary mask</option><option value="single">Single overlay</option></select></label><label for="figureDpi">Resolution<select id="figureDpi"><option value="300">300 DPI</option><option value="600">600 DPI</option></select></label><label><span><input id="figureLegend" type="checkbox" checked> Mask legend</span></label><label><span><input id="figureScale" type="checkbox" checked> Pixel scale bar</span></label><label><span><input id="figureLabels" type="checkbox" checked> Subfigure labels</span></label><label><span><input id="figureCaption" type="checkbox" checked> Recorded measurements & caption</span></label></div><p class="composer-note">Geographic north, physical distance and CRS are unavailable in this browser session. PDF and SVG contain a raster figure; SVG does not convert mask edges to vectors.</p><div id="figurePreview"></div><p id="figureMeta" class="figure-meta"></p><div class="figure-downloads"><button id="figurePng" class="primary" type="button">Download PNG</button><button id="figurePdf" class="secondary" type="button">Download PDF</button><button id="figureSvg" class="secondary" type="button">Download SVG</button><button id="figureConfig" class="secondary" type="button">Download config.json</button></div><p class="composer-note">config.json records file hashes and available parameters. Export the evidence bundle as well for independent replay.</p>`,'PUBLICATION FIGURE');
  $('modal').classList.add('wide-dialog');
  const options=()=>({layout:$('figureLayout').value,dpi:Number($('figureDpi').value),legend:$('figureLegend').checked,scale:$('figureScale').checked,labels:$('figureLabels').checked,caption:$('figureCaption').checked,width_mm:180});
  const render=()=>{preview=renderFigure(snapshot,options());preview.className='figure-preview';preview.setAttribute('aria-label','Preview of selected saved result for publication');$('figurePreview').replaceChildren(preview);$('figureMeta').textContent=`${preview.width} × ${preview.height} px · ${options().dpi} DPI · 180 mm print width · V${snapshot.run.version}`;};
  document.querySelector('.figure-options').onchange=render;render();
  const filename=`geomasklab-${snapshot.run.id}-${snapshot.run.version}`;
  for(const format of ['Png','Pdf','Svg','Config'])$('figure'+format).onclick=async()=>{
   const button=$('figure'+format);button.disabled=true;button.setAttribute('aria-busy','true');const chosen=options(),canvas=renderFigure(snapshot,chosen);
   try{if(format==='Png')saveBlob(filename+'.png',await pngWithDpi(canvas,chosen.dpi));
    else if(format==='Pdf')saveBlob(filename+'.pdf',await rasterPdf(canvas,chosen.dpi));
    else if(format==='Svg'){const description=escape(`Raster publication figure, saved mask V${snapshot.run.version}, ${chosen.dpi} DPI; no vector boundary conversion.`);const svg=`<svg xmlns="http://www.w3.org/2000/svg" width="180mm" height="${(canvas.height/canvas.width*180).toFixed(3)}mm" viewBox="0 0 ${canvas.width} ${canvas.height}" role="img"><title>GeoMaskLab publication figure</title><desc>${description}</desc><image width="${canvas.width}" height="${canvas.height}" href="${canvas.toDataURL('image/png')}"/></svg>`;saveBlob(filename+'.svg',new Blob([svg],{type:'image/svg+xml'}));}
    else saveBlob(filename+'-config.json',new Blob([JSON.stringify(await figureConfig(snapshot,chosen),null,2)],{type:'application/json'}));
   }catch(error){toast(error.message);}finally{button.disabled=false;button.removeAttribute('aria-busy');}
  };
 };
})();
