# 源码调研、2026规则与设计取舍

核验日期：2026-09-05。使用官方仓库及官方文档，不以star数、README愿景或代理评分当作能力测量。以下是读取公开源码得到的设计判断，不是运行四个基线后的性能排名。

## 上游组合

| 项目及核验版本 | 已有长处 | 需要针对本需求补足的部分 | 本系统吸收方式 |
|---|---|---|---|
| XiaoMaColtAI/math-modeling-skill，6ea5f3bcb95f6677e446fa1e26a7cceaf36db53f | 建模/代码/论文三阶段、渐进加载、M1/P1/P2/W1/W2独立只读质检、数值/来源/编译验收 | 不能笼统说“它没有门禁”；本任务仍需可强制执行的阶段状态、双CLI、外部固定评测与多种子确认 | 保留三角色语义，门禁写进Python而非只靠执行者遵守文字 |
| jihe520/MathModelAgent，83d8783187a2d29dda1b046cb667009cc50c8203 | Skills优先、现有桌面/多角色流程、17套Typst模板与9步论文验收 | README明确转向Skills而非继续自研Harness；旧栈列出的部分HIL/RAG/回退功能又标为未完成。不能把功能愿景当代码验收 | 复用“基于Codex/Claude现成工具+阶段skills”思路；按用户要求改为LaTeX |
| qiancheng0/ModelingAgent，读取main的README及src/ModelAgent/mathmodel.py | 选模、假设、因素提取/批评、数据/仿真、ModelingBench与多专家ModelingJudge | 该入口以factor_critics标记判断提前结束，后续数据/仿真/写作未逐项核实；这是静态阅读发现的恢复风险，不称为本次实测事故 | 改为每阶段摘要绑定收据和输出完整性；吸收按问题配置评价职责 |
| usail-hkust/LLM-MM-Agent，c593c794131a7343c6d9ed379220969322b91e64 | HMML分层98种高层方案、actor-critic建模、按依赖求解、MLE-Solver；另有新Web Demo | MMAgent/main.py中论文阶段被注释为optional，不能据此说整个项目无论文能力；原论文/美赛流程不自动满足2026国赛格式 | 吸收问题→子任务→方法→公式→求解路径，但不冒称本包复制了全部98种实现 |
| mythrise/ego_agent_infra，读取main README及docs/agent-native-data-plane.md | Deterministic Core + LLM Residual、实验编译、资源否决、阶段回执、每Agent独立SQLite/FOCUS、可信经验升级 | 生产Nexa/Agent Memory/AgentTeams和完整RXP服务是更大部署。本任务没有连接这些服务 | 小型本地确定性内核及可选stage-commit桥；明确NOT_CONFIGURED，不伪称在线 |

## 直接阅读入口

- https://github.com/XiaoMaColtAI/math-modeling-skill/blob/6ea5f3bcb95f6677e446fa1e26a7cceaf36db53f/README.md
- https://github.com/XiaoMaColtAI/math-modeling-skill/blob/6ea5f3bcb95f6677e446fa1e26a7cceaf36db53f/references/Subagent%E8%B0%83%E5%BA%A6.md
- https://github.com/jihe520/MathModelAgent/blob/83d8783187a2d29dda1b046cb667009cc50c8203/README.md
- https://github.com/qiancheng0/ModelingAgent/blob/main/src/ModelAgent/mathmodel.py
- https://github.com/qiancheng0/ModelingAgent/blob/main/README.md
- https://github.com/usail-hkust/LLM-MM-Agent/blob/c593c794131a7343c6d9ed379220969322b91e64/MMAgent/main.py
- https://github.com/usail-hkust/LLM-MM-Agent/blob/c593c794131a7343c6d9ed379220969322b91e64/README_zh.md
- https://github.com/mythrise/ego_agent_infra/blob/main/README.md
- https://github.com/mythrise/ego_agent_infra/blob/main/docs/agent-native-data-plane.md

没有伪造不可得的main commit SHA。对未锁定的main，以上分析只对应本次检索到的内容；复做对比实验前必须记录实际checkout commit。新内核没有直接复制这五个仓库源码；附件算法与矢量代码由用户提供并单独保留来源。

## 近期autoresearch带来的设计取舍

| 一手资料 | 对本设计的启发 | 不作的推断 |
|---|---|---|
| AutoResearch: Insight In, Hallucination Out, arXiv:2608.17906, 2026年8月 | 可检验机制、执行与证据接受分开、fresh-context独立审查、允许继续/修改/终止 | 原论文的跨模态/系统实验得分不迁移成国赛胜率 |
| Sibyl-AutoResearch, arXiv:2605.22343, 2026年5月 | 保存失败，让经验转为具体后续行为和受测试的harness修复；写作者消费成熟度标记的主张 | 该工作自己说明追溯材料不构成受控比较优势，不能仅靠引用叫“最先进且最强” |
| Anthropic, Effective harnesses for long-running agents | 长会话依靠持久化进度、可恢复状态和实际验证，而非无限长对话 | 进度文件不是正确性证明 |
| OpenAI, Harness engineering | 将约束、可观测性和反馈变成可执行环境 | 工程约束数量不等于数学建模能力提升 |

文献：
https://arxiv.org/abs/2608.17906
https://arxiv.org/abs/2605.22343
https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents
https://openai.com/index/harness-engineering/

这不是对所有2026系统的穷尽排行榜。本包把能够实现和测试的确定性部分写成代码；研究创新、跨题泛化和真正双模型表现留给独立基准验证。

## CLI合同与认证

Codex非交互官方文档： https://developers.openai.com/codex/noninteractive/
Codex配置： https://developers.openai.com/codex/config-reference/
Claude非交互： https://code.claude.com/docs/en/headless
Claude参数： https://code.claude.com/docs/en/cli-reference

适配器记录实际CLI版本，输出经Schema校验。Claude的JSON Schema结果来自structured_output而非把自然语言result当合格JSON。Bare模式跳过自动发现上下文，并且不读取订阅OAuth/钥匙串；本版本支持显式API凭证。功能参数探测失败应阻塞，不能删掉安全参数硬跑。

## 2026规则来源

格式规范，发布2026-03-03：
https://www.mcm.edu.cn/html_cn/node/4cd596519c9eb9fbd866398f6df0caa3.html

AI工具使用规定，发布2026-08-03，自2026-09-01试行：
https://www.mcm.edu.cn/html_cn/node/fef94648f2836ab6cc81586f4c38512b.html

电子稿第一页摘要、不含承诺与编号页；正文不要目录且≤30页；附录不限页但要有完整可运行代码及支撑列表；A4页边距≥25mm；电子论文和ZIP/RAR支撑包各≤20MB。字体/字号/行距/颜色全国未统一规定，赛区可另有要求。

AI允许使用但核心建模由团队主导，AI内容逐项人工核验；参考文献前列AI工具使用声明，支撑材料含AI工具使用详情.pdf，说明具体用途/提示方式/采纳修改核验。不是“只有不披露才违规”，直接提交未经必要人工核验的核心AI成果也不合规。

本包LaTeX是根据这些要求自行实现的profile；未发现和本次交付相同的官方LaTeX类，因此不使用“官方2026 LaTeX模板”作为名称。
