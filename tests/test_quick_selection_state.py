"""Exercise the shipped quick-task handlers, including stale-result protection."""
from pathlib import Path
import shutil
import subprocess
import unittest


@unittest.skipUnless(shutil.which('node'), 'Node.js is required for browser handler checks')
class QuickSelectionStateTests(unittest.TestCase):
    def test_selection_scope_history_and_busy_controls(self):
        source = Path(__file__).resolve().parents[1] / 'workbench/web/workbench.js'
        script = r'''
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const elements=new Map();
function $(id){if(!elements.has(id))elements.set(id,{value:'',disabled:false,hidden:false,textContent:'',innerHTML:'',style:{},options:[]});return elements.get(id);}
const state={session:{name:'test',runs:[]},status:{sam_configured:true},mode:'live',busy:false,selected:null,mask:null,loadToken:0};
let resets=0,draws=0;
const context={$,state,document:{querySelector:()=>({textContent:''})},targetNames:{building:'Buildings',tree:'Trees'},sideNames:{all:'Whole image',right:'Right half'},
escape:String,number:String,targetLabel:r=>r.task.target,runStateLabel:()=>'',executionLabel:()=>'',
updateMode:()=>{},selectRun:async r=>{state.selected=r;state.mask={pixels:true};},showSession:async()=>{},renderTrace:()=>{},renderReview:()=>{},
resetMetrics:()=>{resets++;$('exportBtn').disabled=true;$('ratioValue').textContent='—';},renderVersions:()=>{},draw:()=>draws++,syncView:()=>{}};
$('demoTargetHint'); // Existing real hint, so the test does not need element creation.
const shipped=fs.readFileSync(process.argv[1],'utf8').split("$('ledgerExportBtn').onclick")[0];
vm.createContext(context);vm.runInContext(shipped,context);
(async()=>{
 const building={id:'b',mask_url:'/b.png',task:{target:'building',side:'right'}};
 state.session.runs.push(building);
 await context.selectRun(building);
 assert.equal($('quickTarget').value,'building');assert.equal($('quickScope').value,'right');
 $('quickTarget').value='tree';$('quickTarget').onchange();
 assert.equal(state.selected,null);assert.equal(state.mask,null);assert.equal(state.view,'original');
 assert.equal(resets,1);assert.equal($('exportBtn').disabled,true);assert.equal($('ratioValue').textContent,'—');
 assert.equal(state.session.runs[0],building);assert.equal(state.loadToken,1);
 await context.selectRun(building); // Saved version still opens and restores its exact task.
 $('quickScope').value='all';$('quickScope').onchange();assert.equal(state.selected,null);assert.equal(resets,2);
 await context.selectRun({...building,task:{target:'building',side:'all',roi:{xyxy:[1,2,3,4]}}});
 assert.equal($('quickScope').value,'roi');
 state.busy=true;context.refreshWorkbench();
 for(const id of ['quickTarget','quickScope','qualityMode','quickRunBtn'])assert.equal($(id).disabled,true);
 $('quickTarget').value='tree';$('quickTarget').onchange();assert.notEqual(state.selected,null);assert.equal(resets,2);
 state.busy=false;context.refreshWorkbench();
 for(const id of ['quickTarget','quickScope','qualityMode','quickRunBtn'])assert.equal($(id).disabled,false);
 assert.equal(draws,2);console.log('Quick selection state checks passed');
})().catch(e=>{console.error(e);process.exitCode=1});
'''
        result = subprocess.run([shutil.which('node'), '-e', script, str(source)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
