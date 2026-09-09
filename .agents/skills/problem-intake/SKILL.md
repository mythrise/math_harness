---
name: problem-intake
description: Ground every modeling requirement in the frozen problem
---

# 题意分析与需求追踪
输入：冻结题面、开发数据审计、PI重点。输出problem_brief。
逐句辨别背景、已知条件、硬约束、交付要求；为每条记录精确原文[start,end)偏移和逐字引文。按原题真实数量建立Q-ID，不套用资料里的“三问”“四问”。区分直接目标与推断的隐含目标，推断不是新增硬性要求。
每问列输入、决策/输出、目标、单位、约束、前置问题以及定量/定性类型。依赖必须有题意依据，不为好看的框架图新增依赖。明确特殊定义、量纲转换、数据口径、缺失附件和歧义。无法消解的关键歧义保留并请求核验，不能假设自己理解必然正确。
验收：题面偏移吻合、每问有锚定交付物、无漏问/循环依赖；随后独立数学审查判断语义覆盖。输出不是求解结果。

合同映射：questions[].constraint_ids只能引用requirements中kind=constraint的ID；已知量仍标记given并通过requirement.question_ids关联各问，不能为了通过检查把已知事实改叫约束。返修时检查控制器提供的具体问题ID、引用ID、实际kind及上一份产物，纠正映射后仍保留全部原题内容。
