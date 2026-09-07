# 文献到可检验设计：2026-09-05

检索以 Exa 为主，三条检索线累计返回/请求21个候选条目（存在重复，不等于21篇完整阅读）；对下面的一手页面另外联网核对。近期窗口为2025-09-05至2026-09-05，同时保留一篇2025年ICLR的方法论来源。会议论文和技术预印本分开，不将摘要的实验成绩当作本算法证据。

|论文/来源|已核对状态与日期|本轮迁移|没有复现或不能外推|
|---|---|---|---|
|Agentic Context Engineering: Evolving Contexts for Self-Improving Language Models (ACE)|ICLR 2026正式会议页面|生成、反思、整理分权；有版本的局部更新|没有运行原Generator/Reflector/Curator LLM；模型预测器不是语言Agent|
|LongHorizon-Harness: Advancing Long-Horizon Agents for Real-World Tasks|2026-08-03 arXiv预印本|Manage–Execute–Audit；任务状态只能写入经环境验证的事实；有界局部任务|未找到会议录用证据；其Agent成绩不等于搜索优化收益|
|Agentic Harness Engineering: Observability-Driven Automatic Evolution of Coding-Agent Harnesses|2026-04-28初稿，2026-05-18 v4；预印本|每次干预有明确对象、事先预测、事后证据；修改可撤销且可归因|未运行其自动LLM改代码系统；搜索已支付FE不能撤回|
|Offline Model-Based Optimization by Learning to Rank|ICLR 2025 Poster|预测误差小不自动意味着候选排序好；加入排序质量审计和原候选回退|未训练作者Ranking loss；本文用Ridge/ExtraTrees，且是在线而非离线MBO|
|Meta-Black-Box Optimization with Bi-Space Landscape Analysis and Dual-Control Mechanism for SAEA (DB-SAEA)|AAAI 2026，正式页2026-03-14|将生成候选与购买真实评价分开|未训练原文RL/TabPFN，不能声称击败作者算法|
|openJiuwen: Beyond Static Harnesses for Long-Horizon Coding Agents|2026-08-28 arXiv预印本|固定核心策略外的运行时适配；组件可组合|未运行原框架，不借用其SWE/Terminal分数|

## 一手链接

- ACE: https://iclr.cc/virtual/2026/poster/10008343
- LongHorizon-Harness: https://arxiv.org/abs/2608.01964
- AHE: https://arxiv.org/abs/2604.25850
- Offline-RaM: https://iclr.cc/virtual/2025/poster/28117
- DB-SAEA: https://ojs.aaai.org/index.php/AAAI/article/view/41016
- openJiuwen: https://arxiv.org/abs/2608.27969

## 最近邻边界

“候选池+代理模型+真实评价”是已有SAEA思想，本轮不宣称发明。新研究假设是将其限制为冻结优化器的可审计残差调用：保存原候选、模型权限与真实档案隔离、历史时序验证、先预测后观测、错误触发回退、严格预算。实验需要分别检验预测器、结构特征、模型门、采集准则和搜索后端；不能因为加入Harness名字就宣称新颖或SOTA。

框架中的管理者/执行者/审计者都是Python组件，不调用外部LLM，不存在隐含Token预算；其建模、训练、候选生成、编码缓存和预测开销都计入串行搜索时间。当前不做会自动改写目标、约束、门槛或源代码的在线Agent。
