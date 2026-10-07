/* Verify all five workflows in the installed wheel and replay downloads in a second environment. */
const {chromium}=require(process.env.PLAYWRIGHT_PATH||'playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
const {execFileSync}=require('node:child_process');
(async()=>{
 const output=path.resolve(process.env.GEOMASKLAB_HANDOFF_AUDIT||'handoff-audit');await fs.mkdir(output,{recursive:true});
 const cli=process.env.GEOMASKLAB_REPLAY_PYTHON;if(!cli)throw new Error('Set GEOMASKLAB_REPLAY_PYTHON to the second installed environment.');
 const inputs=path.join(output,'inputs');await fs.mkdir(inputs,{recursive:true});
 execFileSync(cli,['-I','-c',`from PIL import Image
import json
from pathlib import Path
p=Path('inputs');Image.new('RGB',(8,6),'#356259').save(p/'image.png')
m=Image.new('L',(8,6));m.paste(255,(2,1,6,4));m.save(p/'mask.png')
v=Image.new('L',(8,6));v.paste(255,(0,0,4,6));v.save(p/'valid.png')
Image.new('L',(8,6)).save(p/'empty.png')
Image.new('L',(512,512)).save(p/'empty-naip.png')
s={'id':'whole','image':'image.png','mask':'mask.png','target':'tree','source':'Hand-counted software fixture','aligned':True}
a={**s,'id':'valid','valid_mask':'valid.png','valid_source':'Explicit left half'}
e={**s,'id':'empty','valid_mask':'empty.png','valid_source':'Empty domain fixture'}
b={**s,'id':'missing','image':'deliberately-missing.png'}
(p/'manifest.json').write_text(json.dumps({'schema':'geomasklab-batch-manifest/1.0','samples':[s,a,e,b]}))`],{cwd:output,encoding:'utf8'});
 const replay=(command,name)=>JSON.parse(execFileSync(cli,['-I','-X','utf8','-m','geomasklab',command,path.join(output,name)],{cwd:output,encoding:'utf8'}));
 const browser=await chromium.launch({headless:true,channel:'msedge'}),context=await browser.newContext({viewport:{width:1600,height:1100},acceptDownloads:true}),page=await context.newPage();
 const errors=[],checks=[];page.on('pageerror',e=>errors.push(e.message));
 const download=async(selector,name)=>{const [d]=await Promise.all([page.waitForEvent('download'),page.click(selector)]);await d.saveAs(path.join(output,name));};
 const close=()=>page.click('#closeModal');
 try{
  await page.goto(process.env.GEOMASKLAB_UI_URL||'http://127.0.0.1:4197');await page.waitForFunction(()=>state.original&&!state.busy);
  assert.equal(await page.evaluate(()=>state.status.version),'1.0.0');await page.click('#enterWorkbench');
  const dataRoot=path.resolve(__dirname,'../examples/data/naip-denver');
  await page.locator('#fileInput').setInputFiles(path.join(dataRoot,'image.png'));await page.waitForFunction(()=>state.original?.naturalWidth===512&&!state.busy);
  await page.locator('.more-tools>summary').click();await page.click('#importMaskBtn');await page.locator('#maskFile').setInputFiles(path.join(dataRoot,'mask.png'));
  await page.selectOption('#maskTarget','tree');await page.fill('#maskSource','NAIP Denver excess-green/Otsu color baseline; unvalidated vegetation candidates.');await page.check('#maskAligned');await page.click('#submitMaskImport');await page.waitForFunction(()=>state.selected?.mode==='external'&&!state.busy);
  const baseline=await page.evaluate(()=>({id:state.selected.id,metrics:state.selected.metrics}));assert.equal(baseline.metrics.pixel_area,142629);
  await download('#exportBtn','baseline.zip');const baseReplay=replay('verify','baseline.zip');assert.equal(baseReplay.pixel_area,142629);
  checks.push('Real NAIP external mask import and independently installed CLI replay');
  await page.click('#measurementDetails>summary');await page.click('#recalculateBtn');await page.selectOption('#regionScope','right');await page.locator('#regionForm button[type=submit]').click();await page.waitForFunction(id=>state.selected?.id!==id&&!state.busy,baseline.id);
  const right=await page.evaluate(()=>({id:state.selected.id,metrics:state.selected.metrics}));await download('#exportBtn','right.zip');assert.equal(replay('verify','right.zip').pixel_area,right.metrics.pixel_area);
  checks.push('Saved-mask region operation preserves source and agrees with the installed CLI');
  await page.click('#compareResultsBtn');await page.selectOption('#comparisonA',baseline.id);await page.selectOption('#comparisonB',right.id);await page.click('#runComparison');await page.locator('#downloadComparisonPacket').waitFor();await download('#downloadComparisonPacket','comparison.zip');
  const comparison=replay('verify-comparison','comparison.zip').comparison;assert.equal(comparison.change_kind,'Analysis_Conditions_Only');assert.equal(comparison.changed_pixels,0);assert.equal(comparison.common_scope_pixels,131072);await close();
  checks.push('Fair comparison reports changed analysis conditions and unchanged common-domain prediction');
  await page.click('#inspectComponentsBtn');await page.click('#inspectRun');await page.locator('#exportComponents').waitFor();await page.locator('[data-component]').first().click();assert.match(await page.locator('#candidateDetail').innerText(),/C\d/);await download('#exportComponents','components.zip');assert(replay('verify-components','components.zip').verified);await close();
  checks.push('Candidate boundary inspection, clickable location and independent packet replay');
  await page.click('#recalculateBtn');await page.selectOption('#validityAction','replace');await page.locator('#validityFile').setInputFiles(path.join(inputs,'empty-naip.png'));await page.fill('#validitySource','Explicit empty domain for null-ratio acceptance');await page.locator('#regionForm button[type=submit]').click();await page.waitForFunction(id=>state.selected?.id!==id&&!state.busy,right.id);
  assert.equal(await page.evaluate(()=>state.selected.metrics.validity_measurements.coverage_of_valid_region),null);await download('#exportBtn','empty-domain.zip');assert.equal(replay('verify','empty-domain.zip').validity_measurements.coverage_of_valid_region,null);
  checks.push('Empty validity remains null in saved browser metrics and CLI replay');
  await page.click('.more-tools>summary');await page.click('#offlineBatchBtn');await page.locator('#offlineManifest').setInputFiles(path.join(inputs,'manifest.json'));await page.locator('#offlineInputs').setInputFiles(['image.png','mask.png','valid.png','empty.png'].map(n=>path.join(inputs,n)));await page.click('#startOfflineBatch');
  await page.locator('#exportOfflineBatch:not([disabled])').waitFor({timeout:60000});await download('#exportOfflineBatch','batch.zip');const batch=replay('verify-batch','batch.zip');assert(batch.verified);
  assert.equal(batch.samples.filter(s=>s.status==='completed').length,3);assert.equal(batch.samples.filter(s=>s.status==='failed').length,1);
  await page.click('#resumeOfflineBatch');await page.locator('#exportOfflineBatch:not([disabled])').waitFor({timeout:60000});await download('#exportOfflineBatch','resumed-batch.zip');assert(replay('verify-batch','resumed-batch.zip').verified);await close();
  checks.push('Explicit batch isolates missing input, retains empty domain and supports verified resume');
  await page.locator('#reviewPacketInput').setInputFiles(path.join(output,'comparison.zip'));await page.locator('.replay-success').waitFor();await close();
  checks.push('Browser packet replay uses the same core as the independently installed CLI');
  assert.deepEqual(errors,[]);await fs.writeFile(path.join(output,'handoff-browser.json'),JSON.stringify({passed:true,version:'1.0.0',checks,browser_errors:errors,human_participants:0,scope:'Automated installed-wheel browser workflow and second-environment CLI replay; not a human handoff.'},null,2));
  console.log('Installed-wheel five-stage browser handoff and CLI replay passed.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
