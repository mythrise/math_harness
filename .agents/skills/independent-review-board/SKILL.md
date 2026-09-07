---
name: independent-review-board
description: Independently audit exact mathematical, code and experimental artifacts through fresh Claude CLI calls.
---

# 多成员独立审查组

至少分开数学审查、实验有效性审查、论文/图像审查。评测器由另一独立调用编写。数学和实验关键审查必须是实际 Claude CLI，不能以 Codex 或作者自检替代。

输入仅含题目、冻结合同、被审摘要和必要原始证据；不传“作者认为已正确”的结论。输出遵守 `schemas/review.schema.json`，含 target_digest、verdict、scope、findings、evidence、unverified。

数学审查：模型是否对应题意，假设/量纲/目标/约束/可行域是否正确，算法适用域是否满足。实验审查：原始目标重算、训练确认隔离、样本/FE预算、消融真实差异、负控制、异常与完整矩阵。论文审查：每问回答、数值与单位、结论范围、引用、图表和真实渲染。

存在P0/P1或必要检查未知，不能PASS；证据变更使旧回执失效。明确列未覆盖事项，不能以评分平均淹没致命错误。多个同模型新会话不是数学意义的独立证明，需精确校验与人类复核补充。

真实适配器在 `providers.py`，Claude `--safe-mode -p --setting-sources user`，由本机 CLI 读取已有用户级认证、服务地址和模型配置。工具与MCP均禁用，插件和hooks不参与调用，只审查 selected packet，不自动加载本文件或CLAUDE.md。harness 不复制或转换凭证。认证状态正常不等于上游模型请求成功；接口缺失或服务请求失败即BLOCKED。fixture回执只能服务demo。
