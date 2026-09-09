---
name: problem-intake
description: Ground complete problem requirements in immutable text and visually reviewed source pages
---

# 题意分析与来源追踪
输入是控制器冻结的原题、原页图像、来源单元、数据审计和当前子任务合同。输出严格以本次 JSON schema 为准：可能是原页转录、题目概览、小批量事实、歧义检查或局部补丁；不要把所有子任务都写成一份完整 problem_brief。

## 来源，不是公式猜测
PDF 文本层只是阅读辅助。收到原页图像时，对照实际图像记录完整公式、上下标、分子与分母、指数整体、表头与各字段单位、时间取样口径、定义、常数/示例值区别和机构轴向关系。不能只抄表标题就宣称字段齐全，不能只锚定分母却写出没有依据的分子。
数学表达可使用 Markdown/LaTeX 转录，但必须忠实于所见原页；完整公式和表格不要在中间插入空行。图中无法辨认的信息写进 unreadable 并返回 NEEDS_SOURCE。禁止使用记忆、网页查询或后续模型反推去“补全原题”。

## 实际问题与类型
按原题真实数量建立问题ID，不套“三问”“四问”。区分背景 background、已知条件 given、硬约束 constraint、交付物 deliverable；推断目标不是新的硬约束。独立确认数据与外部初版建议不属于此阶段的原题事实。
在 source-ledger-v1 中仅选择控制器提供的 source_unit_ids 和 question_ids，不自行发明偏移或 constraint_ids；分类型引用由控制器统一生成。第一来源必须属于当前批次，邻接 context_units 可补充同一公式或定义，但不能用只读上下文替代未覆盖的当前原文。
旧 legacy 合同的 constraint_ids 仍只能引用 kind=constraint；不要为通过检查把 given 或 deliverable 改叫约束。

## 完整性与自包含
覆盖当前批次中的每项实质性信息，而不是“这一段已抽出一条就完成”。完整定义必须写在本条 statement 中，不使用“分母见G37”“G32至G38”等自造交叉引用。无关来源可排除，但须有具体理由，并接受独立审查。
每批最多24条事实只是回复容量，不是整题上限。无法容纳则返回 NEEDS_SPLIT，不得截断尾项或伪造 COMPLETE。整合层上限512，超限须显式报告，不丢弃条件。
明确的符号/量定义填写 declarations：subject及原文逐字quote。题面已经规定的时间、单位或常数不得重新列成 missing_information；只有原始来源确有两个冲突证据时，才列 source_conflict。

## 审查与返修
核对当前阶段题意忠实性，不要求提前推导完整旋转/光学模型、求解算法或未来实验成绩。已知条件、完整公式定义、单位、约束或交付物漏提仍应拒绝。
返修只修当前来源块；读取具体诊断、原始否决和最新产物。全局补丁绑定 base_digest 与原条目 before_digest，保留未修改条目、硬约束、实际小问和已有来源覆盖。服务超时不是科学否决；有效FAIL不会因换供应商消失。没有执行实验，不得声称已求解或验证算法性能。
