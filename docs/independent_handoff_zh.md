# GeoMaskLab rc4 独立交接

这一版包含完整介绍首页、工作台、五项核心流程和论文插图导出。请在自己的电脑上测试，保留每次失败与作者帮助记录。

## 下载与启动

从 [v1.0.0rc6 发布页面](https://github.com/pophip3/geomasklab/releases/tag/v1.0.0rc6) 的 Assets 下载：

- `geomasklab-1.0.0rc6-py3-none-any.whl`：完整安装包。
- `GeoMaskLab-1.0.0rc6-source.zip`：相同版本的源码、真实影像示例和交接说明。
- `SHA256SUMS.txt`：核对下载文件。

安装 Python 3.10 或更新版本，把文件放在新的可写目录，解压源码 ZIP。在此目录打开 PowerShell：

```powershell
python -m venv ui-env
.\ui-env\Scripts\python.exe -m pip install .\geomasklab-1.0.0rc6-py3-none-any.whl
.\ui-env\Scripts\geomasklab.exe --version
.\ui-env\Scripts\geomasklab-ui.exe --port 4180
```

版本应为 `1.0.0rc6`。打开终端显示的 `http://127.0.0.1:4180`，先看到介绍首页。
点击 **Enter workbench** 进入工作台，**Overview** 返回首页。
保持终端运行；停止时按 Ctrl+C。端口被占用可改成 `--port 4182`。
安装包包含网页和图片，不需要另装前端工具。实验保存在运行目录下的 `experiments`，后续启动请使用同一目录。

## 完成并记录

1. 从首页点击 **Import image + mask**。在同一窗口的 **Source image** 选择 `examples/data/naip-denver/image.png`，在 **Target mask** 选择同目录的 `mask.png`。确认显示两个文件均为 **512 × 512 px**、状态为 **Dimensions match**。这一尺寸来自配套案例数据，软件保留用户影像的原始宽高。
2. **Semantic target** 选择 **Vegetation**；来源填写 `repository excess-green/Otsu baseline; not independently validated`，确认像素对齐后点击 **Import and view results**。应直接进入工作台的 V1，显示 **142,629 px / 262,144 px**、整图覆盖率 **54.41%**。若已处于工作台，入口为 **Import image / mask**；选择 **Upload an image with its mask** 可以一并导入，**Use current image** 用于向已选影像导入新掩膜。选错文件可在同一窗口更换，已填写内容保留。
3. 展开 **Measurement details**，点击 **Region & validity**，选择 **Right half**，保持已保存的有效范围，创建另一版本。
4. 点击 **Compare versions**，比较整图和半幅版本，选择 **Restrict to shared valid pixels**。记录共同分母和差异解释，导出 comparison ZIP。
5. 点击 **Inspect**，运行候选检查，点击一个候选定位，导出检查包。检查不应修改来源掩膜。
6. 点击 **Export evidence** 导出半幅证据包；**Export figure** 可导出同一保存版本的论文插图与 config。返回首页再进入、关闭页面再打开，检查选择的版本与结果是否保持。

该影像是真实 NAIP 数据，掩膜是未独立验证的颜色基线。覆盖率和内部校验都不是分割准确率。

影像、目标掩膜及有效像元掩膜须使用同一像素网格。提示中的尺寸取自当前选中的影像；不是只接受该尺寸的所有输入。尺寸不一致时请先核对所选影像与掩膜是否配套，不要将掩膜直接拉伸到另一张影像。

## 在第二个环境重放

停止网页。将下载的半幅证据包和比较包复制到源码目录之外的 `replay` 文件夹，分别重命名为 `selected-region-evidence.zip` 和 `comparison.zip`，记录原始文件名。在下载目录运行：

```powershell
python -m venv cli-env
.\cli-env\Scripts\python.exe -m pip install .\geomasklab-1.0.0rc6-py3-none-any.whl
.\cli-env\Scripts\python.exe -I -m geomasklab verify .\replay\selected-region-evidence.zip
.\cli-env\Scripts\python.exe -I -m geomasklab verify-comparison .\replay\comparison.zip
```

应成功退出，像素数和分母与保存结果一致。候选包用 `verify-components`，批量包用 `verify-batch`。

## 批量与反馈

按 [完整交接说明](independent_handoff.md) 的 **Exercise failure isolation and recovery** 生成批量样本，然后在 **More → Offline batch** 上传清单。点击 **Add files**，可逐个或分次添加输入文件；已添加文件会保留在清单中。确认五个 PNG 均在列表中，再开始批处理。**Remove** 移除单个文件，**Clear list** 清空输入列表。重选同名文件不会覆盖原文件；替换时先移除原文件。保留故意缺失的样本，观察失败隔离，尝试取消及 **Verify & resume**。如果任务过快无法取消，记录“未观察到取消”。

复制并填写 [handoff_record.csv](handoff_record.csv)。测试者可用 P01 代号，记录操作系统、Python 版本、命令或动作、实际输出、卡点和作者帮助。重试另加一行，不覆盖失败记录。
交回记录表、原始报错和导出 ZIP。未参与开发的同学实际完成后才能记录真人交接通过。

Linux/macOS 的安装和启动命令见英文交接说明。
