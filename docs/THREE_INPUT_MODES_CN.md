# CUMCM Harness v0.5.0-rc1：三种正式输入

基于 `mythrise/math_harness @ 8d9c59619edeb0928e7e24688e074fe1cff91250`。

当前完整仓库已接入三模式。上游包的安装、设计与原始验收记录保存在 [three-input-upgrade/](three-input-upgrade/README.md)，本轮实测见 [本机报告](../reports/THREE_INPUT_V050_LOCAL_CN.md)。原 MOSAIC、OurWork、凭证加载与旧工作区保持原状。

## 三种输入

| input-mode | 输入 | 运行含义 |
|---|---|---|
| `idea` | 原题、官方数据、一个或多个初版idea文件 | 完整建模链。初版是建议，不是已经批准的模型；重点适配此模式。 |
| `scratch` | 原题、官方数据 | 同一完整建模链，不要求预先准备idea。无官方数据时可省略`--data`。 |
| `revise` | 已完成论文；可另附原题作对照 | 先诊断，再做含义保持的文字修订。实质科学修改进入待研究清单，不伪造重新实验。 |

`--input-mode`与`--mode practice|contest`是不同维度，不要混用。

## 已接入仓库的入口

使用 Python 3.11+ 的 editable 环境；本机请进入 `.runtime/three-inputs-v050-worktree`。包安装器仅适用于其声明的原始基线，不要对已经升级的检出重复覆盖。

更新后使用模块入口最直接：

```bash
cd /path/to/math_harness
.venv/bin/python -m cumcm_harness init --help
```

使用已安装`cumcm`命令前，重新执行一次editable install，让console入口指向新的分派器：

```bash
.venv/bin/python -m pip install --no-build-isolation -e '.[dev,excel]'
```

执行及TeX继续使用原有Docker隔离。源码变了，即使标签不变也须重建：

```bash
docker build -t cumcm-egoharness:0.4.0-rc1 .
docker build -f Dockerfile.tex -t cumcm-egoharness-tex:0.3.1 .
```

镜像标签沿用当前仓库配置，不代表运行旧代码。不要改旧工作区的指纹强行恢复；旧成果保留，按新版本重新`init`。

## 模式一：你和网页Pro先讨论，再交给完整Harness

优先保存成UTF-8 Markdown。可以直接使用整理后的自然语言，不要求手写严格JSON。原题、官方数据与初版思路必须分别存放。

```bash
.venv/bin/python -m cumcm_harness init workspaces/idea-new \
  --input-mode idea \
  --problem /absolute/path/official_problem.md \
  --data /absolute/path/official_data \
  --prior-idea /absolute/path/web_first_model.md \
  --config configs/input-idea.json \
  --exa-policy configs/exa-policy-r2.json

.venv/bin/python -m cumcm_harness run workspaces/idea-new
```

多个来源可重复`--prior-idea`，例如网页AI方案和你自己整理的反方笔记。每个来源保留独立摘要与出处。最多6份、合计240000字符；超限会阻断，不静默删掉聊天内容。

有真实网页使用记录时，增加：

```bash
--external-ai-records /absolute/path/external_ai_records.json
```

格式见`examples/three-inputs/external_ai_records.example.json`，每个idea文件对应一条、顺序一致。模板的UNREPORTED等字段需要根据实际情况填写，未显示的模型不猜。纯人工笔记标记`source_type=human_notes`，不会被伪造为AI调用。practice可不填；contest必须提供实际网页工具和主要提示记录，最后仍需真实人工签核。

### 它会如何处理初版？

1. 原题、数据独立解析；先给出没有看过外部idea的题意、数据方案和基准组合。
2. 外部思路整理员按原文位置提取方法、假设、目标、约束、偏好、风险及待核验引用。网页声称的成绩不进入实验结果。
3. 独立反方将它们映射到实际小问，记录候选、拒绝、暂缓、冲突。
4. 建模手利用这些建议重新推导；逐条记录ADOPT/MODIFY/REJECT/DEFER。采纳的假设绑定到正式假设表，继续受Exa文献与程序检验约束。
5. 进入原有全部阶段：文献反方、模型审查、独立评测器、代码、每候选自测、基准/消融/敏感性、冻结确认、正文、摘要、语义/视觉审查、人工签核与打包。

初版方案不会直接写入已冻结的`plan`，不导入网页声称的PASS，不把聊天引用变成已核验文献。未采纳建议保留理由；暂缓不是已经验证。人类希望保留的观点会被显式记录，但不能压过原题、数据与科学否决。

关键产物：

- `entry.json`与`entry/`：冻结输入、私有原始材料。
- `ideas/accepted.json`：片段、来源、反方判断，仍是候选级证据。
- `ideas/plan_alignment.json`：逐项采纳/修改/拒绝/暂缓，以及对应问题、任务和假设索引。
- `ideas/public_summary.json`：可公开的摘要与状态，不含原始聊天正文。
- `input_provenance.json`：网页使用的用户报告记录，不伪装成CLI执行回执。

生产`idea`模式缺文献通道时会明确阻断，而不是悄悄省略研究。源文件内的“忽略审查”等文字只是数据，没有控制权限。

## 模式二：从原题和官方数据开始

```bash
.venv/bin/python -m cumcm_harness init workspaces/scratch-new \
  --input-mode scratch \
  --problem /absolute/path/official_problem.md \
  --data /absolute/path/official_data \
  --config configs/input-scratch.json \
  --exa-policy configs/exa-policy-r2.json

.venv/bin/python -m cumcm_harness run workspaces/scratch-new
```

“0输入”指没有初版思路，不是没有题目。真的不需要外部数据时允许省略`--data`；数据方案不得因此编造观测。原有`--confirmation`、`--private-dev`、`--private-confirm`、`--sources`仍保留在研究模式。

## 模式三：已有论文修订

```bash
.venv/bin/python -m cumcm_harness init workspaces/revise-new \
  --input-mode revise \
  --paper /absolute/path/completed_paper.docx \
  --config configs/input-revise.json

.venv/bin/python -m cumcm_harness run workspaces/revise-new
```

可另加`--problem`供核对；不会因为仅有论文就声称覆盖了原题全部要求。

- **DOCX**：修改普通正文，保留包内其他文件及原有公式、表格、图片、字段。混合数学段落不改；检测到批注或修订跟踪时保护整篇正文，覆盖跨段范围，并明确报告。输出`revised.docx`。
- **MD/TXT/TEX**：输出同类副本，代码块、公式及TeX控制段受保护，不执行原TeX。
- **仅有PDF**：读取可提取文本，输出修订Markdown；不声称保留了原PDF版式或完整公式。扫描件需要已核验的文本源。

所有修改绑定原段落哈希，保护数字、公式、引用、代码、技术标识、比较关系及部分语义强度词；随后独立审查含义是否保持。词法保护不是数学证明，模型审查也不是原实验重跑。

产物：`deliverables/revised.*`、`revision-report.json`、`research_handoff.md`、实际新增编辑调用记录。发现需要换模型、重算数值或补证据的问题，只生成研究请求。把`research_handoff.md`与原题、数据交给新的`idea`工作区，才能进入完整实验。

原始论文不覆盖。原论文已有AI历史不会被编辑器猜测重建；正式提交前须合并真实原始披露。practice生成使用详情Markdown工作副本；contest沿用隔离TeX生成AI详情PDF和真实人工门禁。编辑完成不等于原论文科学结论或国赛全部规则已重新验收。

## 原题与初版格式

原题继续使用MD/TXT或可提取文本PDF。初版支持MD/TXT/JSON/TEX、普通DOCX和可提取文本PDF。含公式/表格的idea DOCX会要求核验后的Markdown转录，避免隐藏遗漏。复杂PDF的公式、表格和图示仍需人工核对；不静默OCR。

## 验证

```bash
.venv/bin/python -m pytest -q tests/test_three_inputs_*.py
.venv/bin/python -m pytest -q
.venv/bin/python scripts/validate_three_inputs.py --out workspaces/check-idea --input-mode idea --r2
.venv/bin/python scripts/validate_three_inputs.py --out workspaces/check-idea --input-mode idea --r2 --replay
.venv/bin/python scripts/validate_three_inputs.py --out workspaces/check-scratch --input-mode scratch --r2
.venv/bin/python scripts/validate_three_inputs.py --out workspaces/check-revise --input-mode revise
```

这些脚本使用明确固定的模型/检索回复，不是真实AI研究能力评测。默认数值与TeX走Docker。`--local-fixture-components`只用于脚本自带的固定工程夹具，不是任意真实代码的本地执行后门。

上游测试与本机测试分别记录。本轮新增真实 CLI、公开 Exa HTTP、Docker 数值与文档渲染验收；具体成功与阻断状态以 [本机报告](../reports/THREE_INPUT_V050_LOCAL_CN.md) 为准。没有自动签核或提交论文。

## 导出完整源码

对已提交版本使用 `git archive --format=zip HEAD -o /outside/repository/math_harness_v0.5.0-rc1_full.zip`。该命令只导出跟踪源码与筛选后的报告，不包含私有凭证、工作区和原始赛题。上游 `build_full_source.py` 是原始基线加 overlay 的安装辅助工具，不应把它的首次输出当成本轮修复后的最终源码。
