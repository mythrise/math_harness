---
name: cumcm-orchestrator
description: Run the evidence-gated CUMCM workflow through the deterministic CLI; use for complete mathematical-modeling projects.
---

# 最高调度者

先读仓库 AGENTS.md、README.md、docs/ARCHITECTURE_CN.md。不要直接修改工作区数据库或门禁回执。

## 执行
1. 确认题目与数据实际路径、训练或正式参赛模式、可用预算。运行 `python -m cumcm_harness doctor --live`。
2. 用 `init` 复制并冻结真实输入；题目图片必须已有可靠解释。缺数据/依赖时 BLOCKED，不编造。
3. 运行 `python -m cumcm_harness run WORKSPACE`。内部依次调用 PI、建模手、独立评测器作者、代码手、数学/实验审查员与论文手。
4. 模型提出方向与返工建议；确定性程序掌管状态迁移、种子、预算、候选接纳和发布。P0/P1 不能被 PI 推翻。
5. `status` 检查阻塞；`audit` 检查证据链。未知运行状态必须先核对实际子进程再由操作员显式恢复。

## 两种模式
practice 可在预算内自动执行；contest 必须由团队主导核心建模，在计划及最终发布两处完成真实人工逐项核验。不得代签、读取操作员密钥或自动提交。`demo` 的模型角色是测试夹具，不能混入 live 验收。

## 完成条件
实际退出成功、独立评价有效、主张绑定证据、论文真编译、图像真检查、必要人工签核均满足，才可本地发布。否则输出部分结果与明确阻塞。不得把目标“最强”写成已验证排名。
