# 在真实完整检出中的验收要求

本包的内部测试通过不能替代你本机完整仓库和真实服务验收。应用前读README，使用固定基线，不改旧工作区。

## 安装与全仓测试

```bash
.venv/bin/python -m cumcm_harness schema brief_facts
.venv/bin/python -m cumcm_harness schema brief_local_patch
.venv/bin/python -m pytest -q tests/test_brief_rc3.py tests/test_brief_rc3_integration.py
.venv/bin/python -m pytest -q
.venv/bin/python -m cumcm_harness verify-vendor
docker build -t cumcm-egoharness:0.5.0-rc3 .
```

保持原来的Docker执行、TeX和文档渲染测试；不要把旧739项的报告当成修改后的报告。新默认image不强改既有profile；新source profile显式使用rc3镜像。

## 原始失败记录只读复查

在本机读取两轮原始brief、原始problem.md和完整review/SQLite。先运行brief_tools到工作区之外的新诊断目录。检查51个错误类型引用、G37/G38/G39悬空关系及ST冲突是否匹配原始记录。内部测试所用的是重建的模式，不可冒称这一项已经执行。

## 真实新运行

用原始官方PDF、原始附件和独立prior创建新idea工作区，启用新profile及R2策略。记录原件/原页/来源索引哈希、每页转录与两席审查、每块事实、全局brief和局部补丁。

验证：双轴及控制关系不漏；表格字段、单位、月份完整；每个原题公式及量定义完整；示例值与固定条件不混淆；已知时间口径未被无依据重开。来源不足就停，不用外部论文替换原题。先检查当前阶段任务，不要求未来求解成果。

通过brief后继续原来的全部流程，到最终论文/支撑包；记录真实通过还是具体阻塞，不绕过P1。针对作者/审查超时分别记录实际provider、timeout、exit status；超时原因与费用未知就留未知。

## 三路及恢复

idea新通道必须完整经过正式建模、Exa反方、代码、实验、确认和论文；scratch同样验证；revise保持既有实际文档渲染与科学问题转交。

同一已完成工作区重新run：不得新增模型/Exa/实验/TeX调用，封存输出摘要不变。未知在途动作先核对再显式恢复。不能改旧fingerprint、删数据库、删除否决或换供应商刷PASS。

## 最终报告

分别报告固定回复/真实CLI/真实Exa/实际Docker数值/实际PDF渲染/全仓回归，不合并重复测试数。只有实际跑过才写PASS；真实定日镜场完整重跑目前应为NOT_RUN，不沿用本包内部测试做替代。

## 保留最新等待策略

基线含 `claude_timeout:null`。本包不将Claude套入Codex的600秒生成或240秒审查时限；运行尚未结束时不可并行启动接管。只有观察到明确终止/服务失败，才进入既有可用性策略。不要把无时限等待标记为成功。新profile采用独立Codex时限，保留Claude无限等待的用户选择。
