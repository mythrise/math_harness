---
name: coding-experiments
description: Generate runnable bounded solver bundles and real experiments without modifying the frozen evaluator.
---

# 代码手与实验执行

读取模型合同、代码任务和 `schemas/bundle.schema.json`。输出完整文件内容，不只给 diff，不包含 shell 安装、网络下载、凭证或自动提交。

统一入口：
```
python main.py --input DATA_DIR --out OUTPUT_DIR --seed INT --budget FE --variant NAME
```
只写 OUTPUT_DIR。所有子问题输出由模型合同约定；评测器在另一个进程独立重算。不得写 evaluator、原始输入、已发布代码、历史结果和确认集。`budget` 的含义由问题合同固定，不能混淆目标评价数、迭代数和运行时间。

真实生成代码仅经 Docker Executor 执行，不使用 trusted-local。后者仅用于随包已知内容的工程测试。无 Docker 则 BLOCKED。

首先运行最小纵向切片与正反例。可诊断错误只能生成新摘要版本并重新审查；旧版本与失败日志保留。确认集上失败不能边看答案边补代码再宣称独立确认。

代码输出原始答案、用于重算的中间量、FE账本和实际参数。耗时必须来自进程回执。不能把内置 oracle 作为搜索器的一部分偷看全部真值，也不能自报分数替代真实验证。
