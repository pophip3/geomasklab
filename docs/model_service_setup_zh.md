# 模型服务配置与真实推理验收

2026-10-04 已接入研究版工作台。原比赛仓库保持不变。

## 当前部署

| 服务 | 研究版使用的地址 | 已验证的运行环境 |
|---|---|---|
| RemoteAgent | `http://127.0.0.1:18000/v1`，模型 ID `RemoteAgent` | SSH 隧道连接已有实验室 RTX 3090 GPU0 服务；OpenAI 兼容多模态接口 |
| RemoteSAM | `http://127.0.0.1:6657/predict` | 本机 RTX 4060 Laptop；PyTorch 2.6.0+cu124、torchvision 0.21.0+cu124、Transformers 4.30.2；FP16，EPOC 关闭 |
| GeoScope 研究版 | `http://127.0.0.1:4180` | Python 3.13.9；独立 `.env` 自动加载 |

RemoteSAM 服务版本为 1.2.0，运行源码从比赛提交
`df802ab54b8f4ee496ca83c104bfaee44f7ee888` 的外部服务目录复制到独立
`runtime/remotesam`。第三方源码、权重、SSH 地址和密钥不纳入研究仓库。
研究版工作台是已修改的软件；外部预训练模型保留其既有来源。

检查点 `RemoteSAMv1.pth` 实际 SHA-256 已重新计算，结果为
`f85dfa044a527f096b9e41eacfe298040d52e77fca642f46dfe1226745e137e7`。
模型成功加载 1107 个张量，无 unexpected keys；缺少的
`text_encoder.embeddings.position_ids` 是生成缓冲区。

## 本机恢复使用

本地独立 `runtime/start-all.ps1` 可恢复 SSH 隧道、RemoteSAM 与研究版工作台。
它只绑定回环地址，先检查端口以避免重复启动，并检查两个服务的就绪响应。
SSH 私有主机设置仅保存在本机脚本中。

```powershell
& .\runtime\start-all.ps1
python .\runtime\verify-live-services.py
```

上述命令从研究项目根目录执行。完整冷启动就绪检查最长 90 秒；网络中断时
先查看 `runtime/remoteagent-tunnel.stderr.log`，模型加载问题查看
`runtime/remotesam.stderr.log`。仅有端口监听不等于模型可推理。

`.env` 已被 Git 忽略。外部部署者按 `.env.example` 填写自己的实际地址、
模型 ID 与检查点版本；端点的 `/v1` 和 `/predict` 后缀必须保留。
修改 `.env` 后需要重启工作台。

## 本次真实推理验收

使用已有 800 × 600 开发影像重新请求模型，没有回放历史模型输出。
原始文件 SHA-256 为
`f067e773544d44d3601fdade477f672d7bdaae456cf228fed393292070f75dc3`。
上传时工作台转为 RGB PNG，因此实验记录中的输入哈希对应规范化后的文件。

| 用例 | 真实执行路径 | 前景像素 | 整幅影像覆盖率 | 结果 |
|---|---|---:|---:|---|
| 全图建筑 | Agent 规划 → SAM `semantic_seg` / `building` / `fast` → 统计 → Agent 反馈 | 134003 | 27.9173% | 完成 |
| 右半幅建筑 | 新请求完整目标蒙版 → 工作台像素裁切 → 统计 → Agent 反馈 | 74673 | 15.5569% | 完成 |

两次请求均启用 `force_perception=True`，禁止复用已有蒙版。
每次导出包均通过离线验证：8 个文件的校验和、输入和蒙版身份、尺寸、
二值范围、空间裁切重放、像素面积与覆盖率分母一致。
模型结果的叠加图也已查看，用于检查影像对齐及明显异常。

完整原始响应、模型元数据、规划与反馈、蒙版、导出包和验证结果留在本机
`runtime/acceptance` 与被忽略的 `experiments` 目录。当前仅完成服务配置验收；
这些开发影像没有独立人工标注，**不能据此报告 IoU、Dice、泛化能力或对照优势**。
随后已按 `application_protocol_v2.md` 完成 60 张新选影像的冻结应用评测，
参见 `application_results_zh.md`。配置验收的开发影像仍不计入该评测。
