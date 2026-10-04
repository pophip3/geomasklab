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
    fig,axes=plt.subplots(1,2,figsize=(10,4.2),sharey=True)
    for ax,target in zip(axes,['building','aircraft']):
        s=next(s for s in summary['summaries'] if s['target']==target and s['method']=='fixed_direct')
        vals=[s['mean_positive_iou'],s['mean_positive_dice']];cis=[s['positive_iou_nominal_ci'],s['positive_dice_nominal_ci']]
        errs=np.array([[v-c['lower'] if c else 0 for v,c in zip(vals,cis)],[c['upper']-v if c else 0 for v,c in zip(vals,cis)]])*100
        ax.bar(['IoU','Dice'],[v*100 for v in vals],color=['#3574a5','#4b9f80'],yerr=errs,capsize=5,width=.55)
        ax.set_title(target.capitalize()+f' (positive n={s["positive_scoped_successes"]})');ax.set_ylim(0,100);ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
        for x,v in enumerate(vals):ax.text(x,v*100+4,f'{v*100:.1f}%',ha='center',fontsize=10)
    axes[0].set_ylabel('Positive-image mean score (%)')
    fig.suptitle('Frozen external-model segmentation: fixed referring prompts',fontsize=12)
    fig.text(.5,.015,'Warm fast mode; no test tuning. Error bars: nominal image-bootstrap 95% intervals; scene correlation is unverified.',ha='center',fontsize=8)
    fig.tight_layout(rect=[0,.05,1,.93]);fig.savefig(out/'fixed_model_accuracy.png',dpi=300);fig.savefig(out/'fixed_model_accuracy.svg');plt.close(fig)
    names={'fixed_direct':'直接模型：固定 referring 提示','whole':'工作台：全图','right':'工作台：右半幅','roi':'工作台：中心 ROI'}
    tr=[]
    for s in summary['summaries']:
        tr.append('<tr>'+''.join(f'<td>{html.escape(str(v))}</td>' for v in [s['target'],names[s['method']],f"{s['success']}/{s['requested']}",s['positive_scoped_successes'],pct(s['mean_positive_iou']),pct(s['mean_positive_dice']),
                  f"{s['empty_gt_false_positive_images']}/{s['empty_gt_successes']}",s['empty_gt_total_false_positive_pixels'],f"{s['median_wall_ms']:.0f}" if s['median_wall_ms'] is not None else '—'])+'</tr>')
    counts={target:{st:sum(r['target']==target and r['stratum']==st for r in manifest) for st in ['positive','negative']} for target in ['building','aircraft']}
    source='<a href="https://zenodo.org/records/5706578">LoveDA 原作者数据发布</a>；<a href="https://captain-whu.github.io/iSAID/dataset.html">iSAID 原作者说明</a>；<a href="https://captain-whu.github.io/DOTA/dataset.html">DOTA 原作者影像说明</a>'
    body=f'''<!doctype html><meta charset="utf-8"><title>GeoScope 独立评测结果</title>
<style>body{{font-family:Arial,"Microsoft YaHei",sans-serif;line-height:1.65;max-width:1100px;margin:32px auto;padding:0 20px;color:#253342}}table{{border-collapse:collapse;width:100%;font-size:14px}}td,th{{border:1px solid #d5dce4;padding:8px;text-align:left}}th{{background:#eaf0f5}}.note{{padding:16px;background:#fff3d9;border-left:4px solid #cb952a}}img{{width:100%}}code{{word-break:break-all}}</style>
<h1>GeoScope 独立评测结果</h1>
<p>本报告评估固定外部模型在新选应用影像上的实际分割质量，以及研究版工作台对模型输出、范围裁切和导出记录的保真性。所有测试样本和参数在预测前固定；结果来自真实模型请求。</p>
<h2>数据与人工标注</h2><p>建筑 30 张（20 正样本、10 无建筑图）；飞机 30 张（20 正样本、10 无飞机图）。建筑来自 LoveDA 验证集；飞机来自匹配的 iSAID/DOTA 验证集。标注由原数据作者提供，不是模型预测，也不是本次代理新做的人工标注。原始标签、二值真值和无效像素掩膜均保存，并可按哈希核查。{source}。</p>
<p>排除了本机既有冻结样本、已计分实验中的 43 个 iSAID 源图编号与已知文件哈希。LoveDA 每个域和 32 连续编号块最多选一张，以降低相邻切片重复；编号块不能证明不同拍摄场景。外部模型预训练是否见过这些公开数据、未定位场景是否重叠仍无法保证。</p>
<h2>实际精度</h2><p>下表的 IoU、Dice 是有目标且成功返回蒙版的图像均值。无目标图像单列误检，不把空真值自动计为满分。ROI 和半幅指标只在相应区域内的有效像素计分；界面覆盖率分母仍是整幅影像。完整逐请求结果包含失败项。</p>
<table><tr><th>类别</th><th>路径</th><th>成功/请求</th><th>区域内正样本</th><th>平均 IoU</th><th>平均 Dice</th><th>空真值误检图/成功空图</th><th>空真值误检像素总数</th><th>请求中位数 ms</th></tr>{''.join(tr)}</table>
<p class="note">固定直接路径用 <code>all buildings</code> / <code>all planes</code> 与 referring_seg；工作台由 Agent 选择 semantic_seg 或 referring_seg。因此两种路径的数值差异包含提示与工具选择差异，不能解释成工作台提高了同一模型算法的精度。严格保真对照另外重放工作台实际选择的相同服务参数。</p>
<img src="fixed_model_accuracy.png" alt="固定外部模型精度图"><p>误差条为 2000 次图像/源图编号 bootstrap 的名义 95% 区间。场景相关性未完全核实，区间仅作探索性描述，不作显著性或独立城市泛化结论。</p>
<h2>工作台执行与证据</h2><ul>
<li>支持请求完成：{summary['completed_supported_requests']}/180。</li>
<li>类别和范围正确：{summary['category_and_scope_correct']}/180。</li>
<li>导出包通过离线校验：{summary['exports_verified']}/180。</li>
<li>独立 NumPy 范围重建一致：{summary['independent_scope_reconstructions_equal']}/180。</li>
<li>同参数直接分割对照：完成 {summary['matched_direct_evaluated']} 次，全图蒙版逐像素相同 {summary['matched_full_equal']} 次。</li></ul>
<p>全部请求使用 fast 模式和新推理，未复用已有蒙版。软件提交：<code>{protocol['software_commit']}</code>；RemoteSAM 检查点 SHA-256：<code>{protocol['sam_model_info']['checkpoint_sha256']}</code>。顺序执行，服务已预热；RemoteAgent 在实验室 RTX 3090 上运行，RemoteSAM 在本机 RTX 4060 Laptop 上运行。共享设备负载可能影响耗时；当前结果不构成速度优势证明。</p>
<h2>材料与使用边界</h2><p><a href="../annotation-review/index.html">60 图人工标注复核包</a>、<a href="../annotation-review/human_review_sheet.csv">新增人工复核记录表</a>、<a href="../manifest.csv">冻结数据清单</a>、<a href="../run-protocol.json">预测前运行协议</a>、<a href="../per_request_metrics.csv">逐请求精度与失败记录</a>、<a href="../summary.json">完整汇总与分母</a>。</p>
<p>新增人工复核人员、签字和审核结论均未虚构。当前采用原作者公开人工标注；可进一步由研究成员进行盲法复核。LoveDA/iSAID/DOTA 数据仅在本地用于学术研究，原始影像和标注没有上传研究 GitHub。该小规模、分层应用集不是数据集完整官方测试榜，也不足以证明泛化、用户效率收益或新模型优越性。</p>'''
    (out/'index.html').write_text(body,encoding='utf-8');print('REPORT',str(out/'index.html'))
if __name__=='__main__':main()
