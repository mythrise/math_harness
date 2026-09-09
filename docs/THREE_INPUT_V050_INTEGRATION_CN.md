# 三模式输入 0.5.0-rc1 本机接入

来源为用户提供的 `CUMCM_Harness_v0.5.0-rc1_三模式输入升级包.zip`，基线提交 `8d9c59619edeb0928e7e24688e074fe1cff91250`。ZIP SHA-256 为 `4acb9e7d2248faa2f8a7c6e5563ce080478f07488d93c0e856a5c1e9c199dad4`。上游 97 项清单校验、安装器 check-only / apply / test 均实际运行，原始报告保存在 [上游记录](three-input-upgrade/TEST_REPORT_CN.md)，本机验证另见 [本轮报告](../reports/THREE_INPUT_V050_LOCAL_CN.md)。

## 输入、处理、输出与接入点

| 模式 | 输入 | 处理 | 输出与接入位置 |
|---|---|---|---|
| idea | 原题、官方数据、初版文件与可选来源记录 | 先盲题意/数据/基准；逐字提取初版；独立反审；映射到实际问题、任务、假设 | `entry/` 私有原件、`ideas/accepted.json`、`ideas/plan_alignment.json`；接回原 Controller 文献、评测、实验、确认、论文全链 |
| scratch | 原题与可选官方数据 | 同一完整研究链，无初版整理阶段；缺必要数据时阻断 | 原研究产物；空数据只表示无附件，不授权伪造观测 |
| revise | 已有 DOCX/MD/TXT/TEX/PDF，可附原题 | 先诊断，安全段落文字补丁，原段哈希和词法保护，独立审查 | 原格式工作副本（PDF 转 Markdown）、修订报告、研究交接；科学修改须另建 idea 工作区 |

`input-mode` 与 `practice|contest` 独立。模式、来源、配置和角色技能均绑定冻结身份。旧工作区不改指纹；新代码用于新工作区。`init` 自动推断模式并默认启用资料合同层；保留显式三模式选项与旧 CLI 的其他命令。

外部引用、性能数字和绕过审查的指令无法成为题面事实或实验结果。未知来源保持 UNREPORTED；纯人工记录不伪装为 AI 调用。原始聊天正文不进入公开摘要。科学修改交接不代表旧实验已被重新运行。

## 本轮集成修复

- 生产、验证镜像和新默认配置同步到 0.5.0-rc1；原 0.4 镜像与工作区保留。
- 空官方数据的发布 JSON Schema 与运行时一致。
- 数学保护先在全文定位，再标记相交块；长公式跨越 1600 字分块仍不允许改运算符。
- DOCX 批注、修订跟踪可跨段，因此保护整个正文；所有 XML / 关系部件均拒绝 DTD。表格、图片、数学和非正文部件保留，并显式警告未读内容。
- `audit revise` 读取已完成发布步骤的 CAS 输出清单，联动篡改导出文件与可见摘要也无法通过。
- 题面向模型提供精确原文锚点供复制；原文、Unicode 偏移和覆盖门禁仍严格执行。
- 全量测试的 Docker 只读快照加入 `scripts/`，支持新增测试的既有夹具引用。
- DOCX 独立渲染镜像包含 Writer 与 Math；无 Math 时确实发现公式空白，修复后再渲染全部页面。

## 可运行验收

```bash
./scripts/cumcm verify-vendor
.venv/bin/python -m pytest -q tests/test_three_inputs_*.py
.venv/bin/python -m scripts.validate_algorithm_upgrade --out reports/NEW-full --seeds 2
.venv/bin/python -m scripts.validate_three_inputs --out workspaces/NEW-idea --input-mode idea --r2
.venv/bin/python -m scripts.validate_three_inputs --out workspaces/NEW-idea --input-mode idea --r2 --replay
.venv/bin/python -m scripts.validate_three_inputs --out workspaces/NEW-scratch --input-mode scratch --r2
.venv/bin/python -m scripts.validate_three_inputs --out workspaces/NEW-scratch --input-mode scratch --r2 --replay
.venv/bin/python -m scripts.validate_three_inputs --out workspaces/NEW-revise --input-mode revise
.venv/bin/python -m scripts.validate_three_inputs --out workspaces/NEW-revise --input-mode revise --replay
./scripts/cumcm audit workspaces/NEW-revise
.venv/bin/python -m scripts.validate_document_revision --out reports/NEW-docx
.venv/bin/python -m scripts.validate_tex_revision --out reports/NEW-tex
```

数值和 TeX 均经 Docker 隔离。文档验证使用固定编辑/审查回复，实际运行 DOCX、XML 保留检查、LibreOffice 与 XeLaTeX；它不证明原科研结论。TeX 编辑器只处理传入源文件，不展开 include；命令密集且无安全正文的整篇源会阻断。图表等内容须单独编译核验。

真实服务脚本 `validate_three_inputs_live.py` 固定最多 6 次 CLI 调用；`validate_exa_r2_live.py` 做有界公开 HTTP 烟测；`validate_materials_live.py` 默认使用公开合成题，也接受明确提供的 `--problem --data --prior-idea --external-ai-records` 来新建有界真实任务。已有授权的 Exa 私有文件和共享租约可通过原安全加载器显式选择，不复制密钥。旧 RUNNING 状态必须先检查；这些脚本不覆盖旧目录、不自动清理失败证据。

GitHub 的两个工作流分别验证完整内核和三模式联跑；均不配置模型或 Exa 凭证。新增工作流包含 DOCX/TeX 实际渲染、修订审计、idea 支撑包独立复现与封存重放。版本保持 RC；真实网页初稿、历史题完成度和人工审查须看各自回执，不能由 CI PASS 代替。
