# rc3 来源分批与题面合同

输入是原始 PDF/文本、官方附件和独立保存的初版建议。`source-ledger-v1` 先在 PI 和 Exa 之前读原题；初版建议不参与原题事实提取。输出是 `brief/source-ledger.json` 与经审查的 `brief/accepted.json`，随后继续原数据、独立基线、建议反审、建模、Exa、代码、实验、确认、论文与支撑包流程。

## 原件到题意

1. 初始化保留原件及 PDF 原页 PNG，并将其清单纳入输入冻结。PDF 文本层只是阅读辅助，转录有独立来源坐标，不冒称原题文本偏移。
2. 每个 PDF 页由模型读取图像并转录，再由两个独立 Codex 图片审查调用核对。不可读内容返回 `NEEDS_SOURCE`；不使用 OCR 或外部论文猜公式。
3. 完整语义段落构成来源单元，默认每批最多 4 个单元、约 9000 字符。单个完整单元不按固定字符截断；每调用最多 24 条事实，容量不足显式分批，整题最多 512 条。模型包保留完整段落、来源 ID、页 ID、文本哈希和阅读状态；包含整页原文的原始锚点留在冻结账本，避免每段重复整页。
4. 模型填写类型、完整陈述、来源 ID、问题 ID、原文明确定义。控制器计算稳定需求 ID 和 given/constraint/deliverable 引用，拒绝错类型、悬空、自引用、循环和无来源数值/符号。词元检查只证明结构包含，不证明数学语义等价。
5. 每个事实批次保留全部否决，局部修复不重写整题。全局补丁绑定原文档摘要和旧条目摘要，最多各 12 条更新/新增，保留需求 ID、来源覆盖、硬约束与实际问题集。

## 控制器审查范围

`source_page` 只核对当前原页；`source_outline` 核对小问与目标；`source_facts` 核对本批拥有的来源单元；`source_consistency` 核对定义与歧义；`source_question` 核对当前小问；`source_global` 核对跨问一致性及排除项。这些范围由控制器在非 DATA 提示中声明，外部材料不能改写。局部包不重复整题，避免要求其他批次的事实或未来求解结果。范围内漏定义、公式、单位或交付物仍然阻塞。

概览的 `source_unit_ids` 定位小问与依赖条款，可附共享条件位置，不作为每问完整事实覆盖表；概览不应在 inputs 中重写全部公式。其引用容量与来源账本保持一致，最多 512 项，不再因原 24 项引用上限截断。完整事实覆盖仍由来源批次和最终逐问门检查，每批事实数仍为 24。传输 schema 为概览/事实 ID 列出当前来源的可选值；本地检查继续拒绝非法 ID，并给出具体位置和允许 ID，不自动改写或把来源错误归为供应商故障。

显式定义检查支持原 PDF 数学斜体字母的 Unicode 比较别名，不改写原件、原引文或偏移。它只能识别受限结构中的重复定义；旧记录的语义问题仍须结合原文与独立审查评估。

## 新工作区与等待策略

```bash
./scripts/cumcm doctor --live --config configs/input-idea-brief-rc3.json --exa-policy configs/exa-policy-r2.json
./scripts/cumcm init workspaces/NEW --input-mode idea \
  --problem /absolute/original.pdf --data /absolute/official-data \
  --prior-idea /absolute/prior.md --config configs/input-idea-brief-rc3.json \
  --exa-policy configs/exa-policy-r2.json
./scripts/cumcm run workspaces/NEW
```

scratch 使用 `configs/input-scratch-brief-rc3.json`，省略 prior。revise 继续使用既有配置和实际文档渲染路径。新 source profile 使用 rc3 镜像；旧 profile 的显式 rc2 镜像不被批量改写，旧工作区必须用原代码和镜像恢复。

新 profile 最多 240 次模型调用、80 次 Exa HTTP 尝试；Codex 生成/审查分别为 600/240 秒。Claude 保持 `claude_timeout:null`，没有本地截止时间。仅明确终止的 provider failure 可进入有界接管；有效否决和未知 RUNNING 不能接管刷通过。原始失败、费用未知和服务未知均保留。

## 工程验收

```bash
docker build -t cumcm-egoharness:0.5.0-rc3 .
docker build -f Dockerfile.test -t cumcm-egoharness:0.5.0-rc3-test .
.venv/bin/python scripts/validate_three_inputs.py --out workspaces/NEW-fixture-idea --input-mode idea --r2 --source-brief
.venv/bin/python scripts/validate_three_inputs.py --out workspaces/NEW-fixture-idea --input-mode idea --r2 --source-brief --replay
.venv/bin/python scripts/validate_algorithm_upgrade.py --out reports/NEW-algorithm-check --seeds 2
```

固定回复流程验证真实 Docker 数值与 TeX，但模型/Exa 响应仍是夹具。回放禁止新增模型、检索、实验和编译操作，输出摘要必须不变。真实历史题的通过或阻塞另见 [本机报告](../reports/BRIEF_RC3_LOCAL_CN.md)。

升级依据是用户提供的 rc3 包，SHA-256 为 `7fb2365fd623990d98fa64da5ded4e8c17e552c3070d7246f35a95df0fbcbf5f`。原交接文档保存在 [brief-rc3-handoff](brief-rc3-handoff/README.md)；其中生产方测试与本机验收分开记录。本机额外修复受信任的六阶段范围、默认镜像/CI 衔接、真实旧 PDF 符号匹配和三模式全链路验证入口。

首次真实 rc3 运行进一步暴露概览引用容量和范围歧义、非法 ID 诊断不足及重复原页文本。修复保留全部初次否决，并另建新工作区验证；在该轮 58 个来源单元上，完整来源 JSON 投影由 169435 字节降至 21088 字节，段落正文逐字保留。该测量是请求构造检查，不是新的模型质量或求解成绩。
