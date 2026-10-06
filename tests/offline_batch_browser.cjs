/* File-picker regression: repeated selections must retain every explicitly paired input. */
const {chromium}=require(process.env.PLAYWRIGHT_PATH||'playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises'),path=require('node:path');
const {execFileSync}=require('node:child_process');
(async()=>{
 const output=path.resolve(process.env.GEOMASKLAB_PICKER_AUDIT||'batch-picker-audit');await fs.mkdir(output,{recursive:true});
 const python=process.env.GEOMASKLAB_REPLAY_PYTHON;if(!python)throw new Error('Set GEOMASKLAB_REPLAY_PYTHON to the independently installed CLI.');
 let inputRoot;
 if(process.env.GEOMASKLAB_BATCH_INPUTS)inputRoot=path.resolve(process.env.GEOMASKLAB_BATCH_INPUTS);
 else{
  const fixtureRoot=path.join(output,'public-example');
  execFileSync(python,[path.resolve(__dirname,'../examples/five_step_workflow.py'),'--output',fixtureRoot],{cwd:output,encoding:'utf8'});
  inputRoot=path.join(fixtureRoot,'inputs');
  await fs.copyFile(path.join(fixtureRoot,'batch-manifest.json'),path.join(inputRoot,'batch-manifest.json'));
 }
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const page=await browser.newPage({viewport:{width:1280,height:1000},acceptDownloads:true,reducedMotion:'reduce'});
 const errors=[],checks=[];page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.goto(process.env.GEOMASKLAB_UI_URL||'http://127.0.0.1:4198');await page.waitForFunction(()=>state.original&&!state.busy);
  await page.click('#enterWorkbench');await page.locator('.more-tools>summary').click();await page.click('#offlineBatchBtn');
  const input=page.locator('#offlineInputs');
  const names=()=>input.evaluate(e=>[...e.files].map(f=>f.name));
  await page.locator('#offlineManifest').setInputFiles(path.join(inputRoot,'batch-manifest.json'));
  const five=['image.png','baseline.png','perturbed.png','valid.png','empty-valid.png'];
  for(let i=0;i<five.length;i++){
   await input.setInputFiles(path.join(inputRoot,five[i]));assert.deepEqual(await names(),five.slice(0,i+1));
   assert.equal(await page.locator('#offlineFileList li').count(),i+1);
  }
  checks.push('Five separate file selections accumulate all named inputs');
  const initial=await input.evaluate(async e=>[...new Uint8Array(await e.files[1].arrayBuffer())].slice(0,24));
  await input.setInputFiles({name:'BASELINE.PNG',mimeType:'image/png',buffer:Buffer.from('different content')});
  assert.deepEqual(await names(),five);assert.deepEqual(await input.evaluate(async e=>[...new Uint8Array(await e.files[1].arrayBuffer())].slice(0,24)),initial);
  assert.match(await page.locator('#offlineFileNotice').innerText(),/existing files were kept/);
  checks.push('Case-insensitive duplicate names never overwrite selected file bytes');
  await page.locator('[data-remove-input="valid.png"]').click();assert.deepEqual(await names(),five.filter(n=>n!=='valid.png'));
  await input.setInputFiles(path.join(inputRoot,'valid.png'));assert.equal((await names()).length,5);
  checks.push('Individual removal and re-addition update the submitted file list');
  await input.setInputFiles([]);assert.equal((await names()).length,5);
  checks.push('An empty picker selection preserves existing files');
  const tooMany=Array.from({length:129},(_,i)=>({name:`limit-${i}.png`,mimeType:'image/png',buffer:Buffer.from('x')}));
  await input.setInputFiles(tooMany);assert.equal((await names()).length,5);assert.match(await page.locator('#offlineFileNotice').innerText(),/limit/);
  await input.setInputFiles({name:'oversized.png',mimeType:'image/png',buffer:Buffer.alloc(33*1024*1024)});assert.equal((await names()).length,5);
  checks.push('Count and byte limits reject additions without discarding the previous list');
  await page.click('#clearOfflineInputs');assert.deepEqual(await names(),[]);assert.equal(await page.locator('#offlineFileList li').count(),0);
  await page.click('#startOfflineBatch');assert.equal(await page.locator('#exportOfflineBatch').count(),0);
  assert.equal(await page.locator('#offlineManifest').evaluate(e=>e.files[0].name),'batch-manifest.json');
  await input.setInputFiles([path.join(inputRoot,five[0]),path.join(inputRoot,five[1])]);
  for(const name of five.slice(2))await input.setInputFiles(path.join(inputRoot,name));
  assert.deepEqual(await names(),five);checks.push('Clear list retains the manifest and supports mixed single/multiple additions');
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  assert.equal(await page.locator('#offlineFileList').evaluate(e=>e.scrollWidth>e.clientWidth),false);
  await page.screenshot({path:path.join(output,'batch-files-mobile.png')});
  await page.setViewportSize({width:1280,height:1000});await page.screenshot({path:path.join(output,'batch-files-desktop.png')});
  let sent;
  page.on('request',request=>{if(request.url().endsWith('/api/offline-batch/start'))sent=request.postDataJSON();});
  await page.click('#startOfflineBatch');
  await page.locator('#exportOfflineBatch:not([disabled])').waitFor({timeout:60000});
  assert.deepEqual(sent.files.map(f=>f.name),five);
  const [download]=await Promise.all([page.waitForEvent('download'),page.click('#exportOfflineBatch')]);
  const packet=path.join(output,'sequential-batch.zip');await download.saveAs(packet);
  const result=JSON.parse(execFileSync(python,['-I','-X','utf8','-m','geomasklab','verify-batch',packet],{cwd:output,encoding:'utf8'}));
  assert.equal(result.verified,true);assert.equal(result.completed_count,3);assert.equal(result.failed_count,1);
  assert.equal(result.samples.find(s=>s.id==='baseline-valid').foreground_pixels,105232);
  checks.push('All five accumulated files reach the server; real batch and independent replay retain expected results');
  assert.deepEqual(errors,[]);
  const receipt={passed:true,version:await page.evaluate(()=>state.status.version),checks,browser_errors:errors,independent_batch_replay:result};
  await fs.writeFile(path.join(output,'batch-picker-verification.json'),JSON.stringify(receipt,null,2));
  console.log(JSON.stringify({passed:true,checks:checks.length,completed:result.completed_count,expectedMissingInputFailures:result.failed_count}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
