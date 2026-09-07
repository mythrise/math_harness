# 定日镜场题目的本地运行

本任务使用“测试/cumcm23A (1).pdf”，对应 2023 年全国大学生数学建模竞赛 A 题。运行模式为历史题练习（practice）。

**2026-09-07 继续运行：** `workspaces/heliostat-2023-fable-unlimited-20260907` 已启动。单次美元费用无上限，Claude 只允许 `claude-fable-5`，关闭内容分类后的自动模型切换。上轮计划作为参考拆分随数据带入，本轮仍有独立审查。新日志：`reports/heliostat-evaluator-repair/paper-run-fable-unlimited-20260907.log`。当前实际阶段用下面命令读取，启动不代表论文完成。

**上一轮状态：BLOCKED。** `workspaces/heliostat-2023-fable-repaired-20260906` 已实际退出。采用修复后的冻结前评测流程，命令指定 `claude-fable-5`；评测器返工触及单次 3 USD 上限。随后仅允许 Fable 的诊断明确返回 `[bio]` 安全分类拒绝。论文尚未生成，详情见 `reports/heliostat-evaluator-repair/PAPER_CONTINUATION_BLOCKER_CN.md`。

进展记录：计划 r3 已通过两路实际 Claude CLI 计划审查，进入独立评测器实现阶段。r0–r2 的失败回执完整保留；当前计划的 PASS 不认证尚未执行的光学精度、60 MW 可行性或算法比较。

后续配置更新：已按用户要求取消 Claude 单次美元费用上限，`claude_call_budget_usd: null` 表示不传 `--max-budget-usd`。旧工作区的冻结配置和失败记录保留；新配置不追溯改变旧运行。费用上限取消不解决上述 Fable 分类拒绝。

前一轮 Opus 工作区已停止，失败记录及进程核对仍保留。基础修复通过122项工程测试、11项Docker检查和Fable两路局部审查；这些不能代替本轮完整科学验收。

## 查看本次运行

在项目根目录执行：

```sh
./scripts/cumcm status workspaces/heliostat-2023-fable-unlimited-20260907
```

日志在 `reports/heliostat-evaluator-repair/paper-run-fable.log`。模型提示、原始输出和回执在该工作区 `model_calls/`；正式数值作业在 `jobs/`；完成后论文和支撑包位置以 `run_summary.json` 为准。没有运行摘要或仅显示 PLANNING，不能视为论文已完成。

这是命令行批处理流程，无需启动网页服务。旧工作区进程已退出，新工作区已按无费用上限配置启动；同一工作区正在运行时不要重复启动。未知 RUNNING 状态需先核对对应外部进程，再按项目恢复流程处理。

## 后续运行使用的输入与预算

- `inputs/heliostat-2023/official/`：官方原始压缩包与 A 题附件。
- `inputs/heliostat-2023/problem-fable-repaired.md`：逐页核对后的转录、图示解释、任务要求，以及本次评测器返工要求。
- `inputs/heliostat-2023/data-fable-repaired/`：全部 1745 个原始坐标、原题、原始表格、结果模板、旧模型提案、局部修复参考和解析回归用例。旧提案和无阴影布局预检均不是已验收答案。
- `inputs/heliostat-2023/sources-r2.json`：实际核实的题目和方法来源。
- `configs/heliostat-2023-fable.json`：每次 solver 共 192 个搜索 FE，最多两个候选，开发种子三个、确认种子五个；单线程、2048 MB、每次数值进程 900 秒。每次模型调用 600 秒，总调用上限按完整配置为 90，Claude 单次美元费用无上限。

MOSAIC 使用随包原版 `continuous_box / incumbent` 分支，几何可行性由独立验证的解码器处理。算法基线为等 FE 的 NSGA-II。结果必须覆盖三问并包括逐镜坐标，不能以演示夹具代替。

## 从头建立独立运行

以下命令会重新调用真实模型并产生费用。将 `heliostat-2023-new-run` 换成一个尚不存在的新目录名：

```sh
./scripts/cumcm doctor --live
./scripts/cumcm init workspaces/heliostat-2023-new-run \
  --problem inputs/heliostat-2023/problem-fable-repaired.md \
  --data inputs/heliostat-2023/data-fable-repaired \
  --config configs/heliostat-2023-fable.json \
  --sources inputs/heliostat-2023/sources-r2.json
./scripts/cumcm run workspaces/heliostat-2023-new-run
```

用户指定后续所有 Claude 角色使用 `claude-fable-5`，通过 `--model` 显式传入本机 CLI，沿用用户认证。`configs/practice.json`、`configs/contest-2026.json` 和新的定日镜任务配置均已设置为 Fable。历史 Opus 4.6 工作区及其回执保持原样，不再用于后续运行；模型切换本身不代表评测代码或论文验收通过。数值代码通过 Docker Executor 执行。`doctor --live` 只检查 CLI 参数和镜像，不证明模型或数值实验已成功。

## 旧运行记录

Fable 已通过本机 CLI 完成一次真实结构化调用，请求模型为 `claude-fable-5`，记录位于 `reports/heliostat-intake/reviewer-calibration-fable/`。这验证了调用可返回，不等同于科学审查全部正确或论文已恢复运行。

`heliostat-2023-live-20260906` 和 `heliostat-2023-live-r2-20260906` 保留了真实失败及中断记录。其父子进程已清理，数据库未手工改写，因此中断步骤可能仍显示 RUNNING。不要把这些步骤当作活跃进程或重新使用旧回执。两次工程修复和进程核对见 `reports/heliostat-intake/REVIEW_STAGE_FIX.md`。

第三个工作区 `heliostat-2023-live-r3-20260906` 在计划阶段耗用10次模型调用后正常返回 BLOCKED，未生成数值作业；最后数学审查 PASS、实验审查 FAIL。原始回执保留，新的 Opus 4.6 工作区不会复用旧审批。
