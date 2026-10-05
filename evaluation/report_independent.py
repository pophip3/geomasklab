"""Readable application report and publication export figure from recorded scores."""
import argparse,csv,html,json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

def pct(x):return '—' if x is None else f'{100*x:.2f}%'
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);a=ap.parse_args();root=a.root
    summary=json.loads((root/'summary.json').read_text(encoding='utf-8'));protocol=json.loads((root/'run-protocol.json').read_text(encoding='utf-8'))
    manifest=list(csv.DictReader((root/'manifest.csv').open(encoding='utf-8')));out=root/'report';out.mkdir(exist_ok=True)
    audit=json.loads((root/'independent-score-audit.json').read_text(encoding='utf-8'))
    metric_rows=list(csv.DictReader((root/'per_request_metrics.csv').open(encoding='utf-8')))
    missed={target:sum(r['target']==target and r['method']=='whole' and r['stratum']=='positive' and r.get('success')=='True' and r.get('predicted_pixels')=='0' for r in metric_rows) for target in ['building','aircraft']}
    fig,axes=plt.subplots(1,2,figsize=(10,4.2),sharey=True)
    for ax,target in zip(axes,['building','aircraft']):
        s=next(s for s in summary['summaries'] if s['target']==target and s['method']=='fixed_direct')
        vals=[s['mean_positive_iou'],s['mean_positive_dice']];cis=[s['positive_iou_nominal_ci'],s['positive_dice_nominal_ci']]
        errs=np.array([[v-c['lower'] if c else 0 for v,c in zip(vals,cis)],[c['upper']-v if c else 0 for v,c in zip(vals,cis)]])*100
        ax.bar(['IoU','Dice'],[v*100 for v in vals],color=['#3574a5','#4b9f80'],yerr=errs,capsize=5,width=.55)
        ax.set_title(target.capitalize()+f' (positive n={s["positive_scoped_successes"]})');ax.set_ylim(0,100);ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
        for x,(v,c) in enumerate(zip(vals,cis)):ax.text(x,(c['upper'] if c else v)*100+3,f'{v*100:.1f}%',ha='center',fontsize=10)
    axes[0].set_ylabel('Positive-image mean score (%)')
    fig.suptitle('Frozen external-model segmentation: fixed referring prompts',fontsize=12)
    fig.text(.5,.015,'Warm fast mode; no test tuning. Error bars: nominal image-bootstrap 95% intervals; scene correlation is unverified.',ha='center',fontsize=8)
    fig.tight_layout(rect=[0,.05,1,.93]);fig.savefig(out/'fixed_model_accuracy.png',dpi=300);fig.savefig(out/'fixed_model_accuracy.svg');plt.close(fig)
    names={'fixed_direct':'Direct model: fixed referring prompt','whole':'Workbench: whole image','right':'Workbench: right half','roi':'Workbench: central ROI'}
    tr=[]
    for s in summary['summaries']:
        tr.append('<tr>'+''.join(f'<td>{html.escape(str(v))}</td>' for v in [s['target'],names[s['method']],f"{s['success']}/{s['requested']}",s['positive_scoped_successes'],pct(s['mean_positive_iou']),pct(s['mean_positive_dice']),
                  f"{s['empty_gt_false_positive_images']}/{s['empty_gt_successes']}",s['empty_gt_total_false_positive_pixels'],f"{s['median_wall_ms']:.0f}" if s['median_wall_ms'] is not None else '—'])+'</tr>')
    counts={target:{st:sum(r['target']==target and r['stratum']==st for r in manifest) for st in ['positive','negative']} for target in ['building','aircraft']}
    source='<a href="https://zenodo.org/records/5706578">LoveDA release</a>; <a href="https://captain-whu.github.io/iSAID/dataset.html">iSAID documentation</a>; <a href="https://captain-whu.github.io/DOTA/dataset.html">DOTA imagery documentation</a>'
    body=f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>GeoMaskLab — Independent application evaluation</title>
<style>body{{font-family:Arial,Helvetica,sans-serif;line-height:1.65;max-width:1100px;margin:32px auto;padding:0 20px;color:#253342;background:#fbfcfd}}h1,h2{{color:#18372f}}.table-wrap{{overflow:auto}}table{{border-collapse:collapse;width:100%;font-size:14px;background:white}}td,th{{border:1px solid #d5dce4;padding:8px;text-align:left}}th{{background:#eaf0f5}}.note{{padding:16px;background:#fff3d9;border-left:4px solid #cb952a}}img{{width:100%;height:auto}}code{{word-break:break-all}}a{{color:#206c51}}</style>
<h1>Independent application evaluation</h1>
<p>This report measures the frozen external model on newly selected application images and checks whether the workbench preserves its masks, spatial operations and exported evidence. Samples and parameters were fixed before prediction. Results come from actual model requests; this English presentation does not rerun or change the recorded experiment.</p>
<h2>Images and source human annotations</h2><p>The sample contains 30 building images and 30 aircraft images: 20 positive and 10 target-absent images per category. Buildings come from LoveDA validation data; aircraft come from matched iSAID/DOTA validation data. Pixel labels were supplied by the original dataset annotators. They are neither predictions nor newly created human annotations. Source labels, binary ground truth and valid-pixel masks are retained locally with hashes. {source}.</p>
<p>Selection excluded previously frozen local samples, known file hashes and 43 iSAID source IDs used in earlier scored experiments. At most one LoveDA image was selected from each domain and block of 32 consecutive IDs. ID blocks reduce adjacent-chip duplication but do not establish distinct scenes. Unknown model pretraining exposure and unidentified scene overlap remain limitations.</p>
<h2>Observed segmentation quality</h2><p>IoU and Dice below are image means over successfully returned, positive scoped cases, including empty predictions scored as zero. Target-absent cases report false positives separately; empty ground truth is not automatically scored as perfect. Half-image and ROI scores use valid pixels inside that scope. Whole-image coverage and within-region coverage have different denominators; neither is an accuracy metric. The complete request table retains failures.</p>
<div class="table-wrap"><table><tr><th>Category</th><th>Execution path</th><th>Completed / requested</th><th>Positive scoped cases</th><th>Mean IoU</th><th>Mean Dice</th><th>False-positive / completed empty images</th><th>Total false-positive pixels in empty images</th><th>Median request ms</th></tr>{''.join(tr)}</table></div>
<p class="note">The direct path uses <code>all buildings</code> / <code>all planes</code> and referring_seg. The agent-driven workbench chooses semantic_seg or referring_seg. Their numerical difference includes prompting and tool selection; it does not show that the workbench improves the same model algorithm. A separate fidelity control replays the exact service parameters chosen by the workbench.</p>
<p>Whole-image workbench predictions are empty for {missed['building']} of 20 positive building images and {missed['aircraft']} of 20 positive aircraft images. These misses remain in the scores as zero IoU/Dice. Successful execution does not mean correct recognition. An empty mask requires review and does not prove that a target is absent.</p>
<img src="fixed_model_accuracy.png" alt="Fixed external-model mean IoU and Dice on positive images"><p>Error bars are nominal 95% intervals from 2,000 image/source-ID bootstrap samples. Scene correlation is incompletely verified; these are exploratory intervals, not significance tests or evidence of independent-city generalization.</p>
<h2>Execution and evidence checks</h2><ul>
<li>Supported workbench requests completed: {summary['completed_supported_requests']}/180.</li>
<li>Recorded category and scope correct: {summary['category_and_scope_correct']}/180.</li>
<li>Export bundles verified offline: {summary['exports_verified']}/180.</li>
<li>Independent NumPy scope reconstruction identical: {summary['independent_scope_reconstructions_equal']}/180.</li>
<li>Matched service-parameter controls: {summary['matched_direct_evaluated']} completed; {summary['matched_full_equal']} full masks pixel-identical.</li></ul>
<p>An independent Pillow audit checked {audit['frozen_input_file_hashes_checked']} input hashes, {audit['human_label_conversions_checked']} source-label conversions and {audit['confusion_tables_and_scores_checked']} confusion tables/IoU/Dice calculations, all consistently. It verifies conversion and arithmetic, not the semantic correctness of the original human annotations.</p>
<p>Requests used fast mode and fresh inference, without reusing existing masks. Experiment source commit: <code>{protocol['software_commit']}</code>. RemoteSAM checkpoint SHA-256: <code>{protocol['sam_model_info']['checkpoint_sha256']}</code>. Requests ran sequentially with warmed services: RemoteAgent on a laboratory RTX 3090 and RemoteSAM on a local RTX 4060 Laptop GPU. Shared-device load may affect timings. These measurements do not establish a speed advantage or describe new release-candidate model accuracy.</p>
<h2>Records and interpretation limits</h2><p><a href="../annotation-review/index.html">Source annotation review packet</a> · <a href="../annotation-review/human_review_sheet.csv">Additional human-review sheet</a> · <a href="../manifest.csv">Frozen data manifest</a> · <a href="../run-protocol.json">Pre-prediction protocol</a> · <a href="../per_request_metrics.csv">Per-request scores and failures</a> · <a href="../summary.json">Full summary and denominators</a> · <a href="../independent-score-audit.json">Independent arithmetic and conversion audit</a>.</p>
<p>No new human reviewer, signature or approval is claimed. The study uses the original authors' published human labels; additional blind review remains possible. LoveDA/iSAID/DOTA images and labels are retained locally for research and are not redistributed in the software repository. This small stratified application set is not an official complete benchmark and does not establish generalization, user labor savings or a superior new model.</p></html>'''
    (out/'index.html').write_text(body,encoding='utf-8');print('REPORT',str(out/'index.html'))
if __name__=='__main__':main()
