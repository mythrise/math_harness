---
name: independent-review-board
description: Role-based Claude and GPT/Codex review seats with bounded availability failover, immutable evidence and no verdict shopping.
---

# 多成员独立审查组

数学、实验、文献以及论文审查按职责而不是厂商验收。每个职责默认两个新上下文席位：Claude 专家席与 GPT/Codex 反例交叉检查席。Claude 的终止性接口故障可由新的 GPT 调用接管；GPT 也故障时暂停并保留完成记录。多次同模型调用不是统计独立性证明。

入口 `review_board.py`。只对 ProviderFailure 执行有限重试、退避、熔断和切换；真实 FAIL/BLOCKED、P0/P1、未核验必要项、摘要损坏、未知 RUNNING 状态与预算耗尽均不得以切换模型绕过。每个席位均需通过，不能投票平均消除严重错误。旧审查只可复用相同目标、上下文、模型配置与席位策略；记录所有失败与实际 provider。

plan_design 只审模型与预定实验合同，不要求未来实验已经运行；source_code 审源码与已经完成的有界 preflight；execution 必须有真实原始输出。不要宣称超出当前阶段的验收。

Claude 仍使用本机 CLI 的 `--safe-mode --setting-sources user` 读取现有认证与模型设置，工具及 MCP 禁用；不是 bare/API-only 适配器。指定 Fable 时仍保留禁止静默换模型的配置。跨厂商接管是 harness 显式记录的机制，不伪装成原模型。图像审查仅路由到支持图片的 Codex 适配器，缺少图像能力不能作已看图的证明。

Fixture 回执只用于明示的工程测试，永远不能满足 LIVE 门禁。当前适配器依赖的安全 CLI 标志缺失时，可以切换另一个支持安全合同的 provider，但不得启用危险权限标志。
