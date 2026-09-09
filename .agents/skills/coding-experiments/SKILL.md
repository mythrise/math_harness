---
name: coding-experiments
description: Implement all frozen variants with independent executable evidence
---

# 代码手与可复现实验
输入冻结模型、数据计划、逐问合同、现有算法入口及IO合同；输出完整bundle。main.py遵守--input/--out/--seed/--budget/--variant，不引入网络、安装命令或凭证。不修改输入、评测器、确认标签或旧输出。
按读取→参数→预处理→模型→求解→原始答案→重算所需信息分模块。预处理仅训练折拟合、时序因果，保留缺失/异常处理理由和参数。整数性、目标方向、索引、单位、随机种子必须与模型一致。
先通过基准的解析正例、错误答案及边界，再实现候选。每种variant是真实单因素改动或声明的情景，不得所有分支执行同一代码后改标签。每个新代码摘要/variant都接受独立测试；失败不能复用基准的通过记录。
只通过Docker Executor运行模型代码。记录真实FE/时间/参数和必要中间量；不把全部迭代塞进正文。长作业使用受控task_dag分片并验证恢复，不能用checkpointing=true代替实现。
“请输出运行结果”不是允许猜测结果。无执行回执时只提供代码，结果保持NOT_RUN。
