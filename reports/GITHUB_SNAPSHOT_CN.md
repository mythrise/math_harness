# GitHub 源码快照

日期：2026-09-07。仓库：`mythrise/math_harness`。

## 本次代码状态

- 项目级 Codex skills、确定性控制器、Claude/Codex CLI 适配器、Docker 执行层及论文构建代码。
- 原始 MOSAIC v14、OurWork v16 和供应文件摘要清单，保留上游来源及权利说明。
- 计划、源码和实际执行阶段分别审查；独立评测器冻结前必须提供 `test_evaluator.py`，并检查无效答案拒绝行为。
- Claude 单次美元费用默认为无上限（配置为 `null`，不传费用限制参数）。指定 Fable 时关闭自动切换模型，保留模型拒绝与调用错误。
- 本机最近完成 125 项工程回归测试。这不是 125 次真实模型或镜场实验；GitHub Actions 将在推送后另行运行。

## 真实赛题进度

定日镜场历史题仍未完成论文。旧轮次计划曾通过两路审查；新一轮已生成计划，但 Fable 数学审查调用返回 429 上游限流，工作区状态为 BLOCKED。正式数值实验与最终论文 PDF 尚未产生。
移除单次美元上限不代表服务限流或此前的模型分类拒绝已经解除。

## 可复现范围

按 README 创建 Python 3.13 虚拟环境，安装 `.[dev,excel]`，运行 `python -m cumcm_harness verify-vendor` 和 `python -m pytest -q`。
真实模型流程另需自行配置 Codex/Claude CLI 和 Docker；`doctor --live` 只做接口与镜像探测。演示使用明确标记的夹具，不需要外部模型认证。

源码仓库不上传本机凭证、原始模型提示/调试日志、实验数据库、私人输入和下载压缩包。需要运行自己的题目时，用 `init --problem ... --data ...` 导入。完整源码依赖保留在 `vendor/`，不是只上传提示词。
`DISTRIBUTION_MANIFEST.json` 与原始测试报告记录上传 ZIP 的历史交付，不是本次修改后所有源码的摘要清单；当前依赖完整性由 `vendor/MANIFEST.json` 检查，当前版本由 Git 提交标识。
