# 0.5.0-rc1 三模式输入本机验收

本轮已在基线 `8d9c59619edeb0928e7e24688e074fe1cff91250` 上完成代码升级和工程验收。可运行检出位于 `.runtime/three-inputs-v050-worktree`；原主目录未提交工作及旧运行均保留。上游清单、原报告与本机新证据分开存放。

## 工程结果

| 项目 | 本机结果 | 证据范围 |
|---|---|---|
| 上游 ZIP | 97 项 SHA-256 校验；安装器 check/apply/test 通过；工具测试 20 项 | 36 路径安装，随后另行本地修复 |
| 完整 pytest | Docker 739 项通过，无跳过 | 包含数值测试与 161 项三模式测试 |
| 宿主基础设施 | 648 项通过 | 数值算法测试留在 Docker；不执行模型代码 |
| 数值重复 | 两次各 98 行、9 类诊断，原始结果与诊断相同 | 2 个种子，CPU 有界诊断；外部候选执行和全局晋级均为 0 |
| idea + R2 | `DEMO_COMPLETE_NOT_LIVE_VALIDATED`，22 个 Docker 实验任务，完整 PDF/支撑包 | 模型/HTTP 是固定回复；实验与 XeLaTeX 实际执行 |
| scratch + R2 | `DEMO_COMPLETE_NOT_LIVE_VALIDATED`，22 个 Docker 实验任务，完整 PDF/支撑包 | 同上 |
| revise | `REVISION_FIXTURE_COMPLETE_NOT_LIVE_VALIDATED`，0 个研究实验任务，导出与 CAS 审计通过 | 固定编辑与独立审查回复；未重跑原实验 |
| 三路 replay | 产物摘要不变，新增模型/HTTP/实验/TeX 调用均为 0 | 重放时将新增调用入口设为失败哨兵 |
| 真实新角色 CLI | Codex / Claude 各 3 次，6/6 有效结构化回复 | 包含虚假成绩、绕过审查指令和数字保护；不是整题完成 |
| 真实 Exa | 4 次公开 HTTP；同工作区重放新增 HTTP 为 0 | 支持/反例检索、正文读取和结构化输出能力烟测；不发送题面附件 |
| DOCX | 两份实物 DOCX 各修订 1 处，4 页实际渲染并查看 | 数学、表格、图片、编号、脚注、引用保留；其他 ZIP 成员字节相同 |
| DOCX 批注/跟踪 | 2 个反例在模型调用前停止 | 整篇正文保护，避免跨段范围漏改 |
| TeX | 既有正文片段修订，前后各 1 页编译并查看 | 公式、表格、引用编号、脚注保留；命令密集整篇输入在调用前停止 |
| 支撑包独立复现 | 基准/候选各 1 个确认种子在新 Docker 容器复现 | 答案和独立评价 JSON 相同，源码附录字节匹配 |
| PaperKit | 86 项原版测试、两份完整参考样例、原生布局/长标题/分支与负例通过 | 真实隔离 TeX；不是正式论文签核 |
| 生产镜像一致性 | 本机 61 个核心 Python 文件与镜像一致 | 镜像 ID / 每文件哈希见 JSON |
| 旧入口兼容 | materials legacy 全链与零调用重放、原 R2 故障注入全链通过 | 固定模型/HTTP，实际 Docker 实验与 TeX |
| vendor | 原 408 项清单通过 | MOSAIC / OurWork 未修改 |

idea 夹具的 4 条初版建议分别为 2 条 MODIFY、2 条 REJECT，保留基准和实际假设映射。公开摘要无原始聊天正文，无执行证据的 99% 成绩和越权指令没有进入结果。更多假引用、漏问、无效问题/任务编号、混淆来源、过长公式和摘要篡改反例包含在自动测试中；这仍不是“真正网页初稿”的完整验收。

## 发现并保留的失败

1. 首次宿主回归 630 项通过、1 项失败，发现镜像默认仍留在 0.4；更新默认后完整新回归通过。
2. 首次全量 Docker 测试收集失败：未复制新测试依赖的 `scripts/validate_materials_pipeline.py`；修复验证快照后 739 项通过。
3. 长公式跨块时原有保护漏掉首块运算符；改为全文定位后标记所有相交块，新增负例通过。
4. DOCX 批注/修订跨段及部分 XML DTD 识别不足；现在整体保护审阅正文并检查全部 XML / 关系部件。
5. 初次 DOCX 渲染 XML 保留检查通过，但可视核验发现公式空白；补齐 LibreOffice Math 后重新渲染，公式可见。保留初次 summary 及专门失败说明，不把初次进程 PASS 当版式 PASS。
6. revise 原先套用普通研究审计；现在读取修订发布 CAS 清单，修改导出和可见摘要无法掩盖篡改。

## 真实历史题与尚未完成的范围

已使用此前指定的公开 2023 A 题原始 PDF、官方附件/模板和无损坐标 CSV 启动新的 idea 实调。既有建模要求单独作为 prior 输入，来源标为未报告的本机历史材料，不能冒充网页会话或题面权威。原 workspace 没有修改。预算上限为 100 次模型调用、32 次 Exa HTTP；所有模型生成代码仍须经 Docker。

**最终为 `BLOCKED / ScientificRejection`**，已结束且没有 RUNNING 步骤：共 7 次真实 CLI 回执（Codex 6、Claude 1），另有 1 条导入材料来源记录，后者不计模型调用；4 次 Exa HTTP 均为 DONE。题意首轮因 `Invalid constraint mapping` 返工，第二轮进入真实审查；审查提出目标/可行域定义、光学模型、布局和算法适用性仍需明确。有效否定意见被保留，耗尽该阶段的有界返工后停止，没有换提供方绕过，也没有进入实验。冻结输入、事件链和 Exa 尝试经只读审计通过。

完整历史题解答、raw 初稿到最终计划/代码/结果的逐条比较未完成。因此本次完成的是三模式工程升级与分层验证，不能宣称已通过真实赛题整题验收。详见 [历史题回执](three-inputs-v050/historical-2023A-summary.json)。

未提供可核验来源的真实网页初稿，因此相关专项为 `NOT_RUN`；已完成的是固定对抗样例和有界真实新角色调用。没有人工签核、正式提交、获奖保证或稳定版认证。版本保持 `0.5.0-rc1`。

## 文件与远程核验

机器可读汇总：[THREE_INPUT_V050_LOCAL.json](THREE_INPUT_V050_LOCAL.json)。筛选后的测试 XML、模型摘要、HTTP 摘要、数值/渲染/重放回执与六张修订前后页面见 [three-inputs-v050/](three-inputs-v050/)。公开测试 XML 中的伪密钥参数已脱敏，测试数与判定保留，原始摘要另存。原始模型提示、日志、历史题输入、私有凭证和冻结工作区均未纳入 Git。

代码提交 `2c8f0d0137b51b3e6d8f17e1f8f99e6e76b61b62` 已推送 `main`，远程 SHA 实际核对一致。两条 GitHub 工作流均成功：

- [deterministic-contract-tests](https://github.com/mythrise/math_harness/actions/runs/34362332290)：下载并检查 648 项宿主 / 739 项 Docker / 86 项 PaperKit 测试，无失败或跳过；两次 98 行数值重复、旧入口/R2 重放、支撑包、隔离与论文返工回执通过。
- [three-input-modes](https://github.com/mythrise/math_harness/actions/runs/34362332271)：161 项新测试，idea/scratch 各 22 个完成任务、三路零调用重放、支撑包与 DOCX/TeX 渲染通过。下载的 4 页 DOCX/TeX 前后图已逐页查看，公式、表格、脚注与引用显示正常。

机器摘要为 [GitHub 内核验收](three-inputs-v050/github-deterministic.json) 和 [GitHub 三模式验收](three-inputs-v050/github-three-inputs.json)。本次后续补记仅改 `reports/`，运行代码、测试、配置和工作流与上述受测提交一致；不重新消耗模型调用或实验预算。
