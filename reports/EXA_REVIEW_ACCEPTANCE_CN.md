# Exa + 双模型审查升级验收报告

日期：2026-09-07。版本：0.2.0。基于 GitHub 提交 `3b233edaa5d2c9ec95bf67ae2d495e0d662c3292`。

## 最终状态

本地源码已实现并完成工程验证；**远程仓库未更新**。当前 GitHub 集成在创建 blob 与创建分支时均返回 `403 Resource not accessible by integration`。没有伪造 commit、分支或 PR 链接。提供附带校验的更新包供现有有写权限的本机 Git 应用。

## 已执行

| 项目 | 实测结果 |
|---|---|
| 最终 harness 自动测试 | 170 passed，13.81秒 |
| 安全更新工具测试 | 8 passed |
| 原始 vendor 摘要 | 408 个文件全部一致 |
| 端到端数值单元 | 22 个 DONE：开发12 + 确认10 |
| 每单元目标评价预算 | 192 |
| 故障注入 | Claude TIMEOUT；18条显式接管事件 |
| 调用记录 | 45条，包含模拟故障；不是45次真实模型请求 |
| 假设诊断 | 延迟折损/非负截断解析边界；确定性重复/时间单位变换 |
| 论文 | 实际 XeLaTeX 编译159页，绝大部分为完整源码与支撑清单附录 |
| 支撑包 | 177个文件，934686字节 |
| 恢复 | 模型调用45→45，实验22→22，无重复执行 |
| 恢复产物 | PDF与support.zip SHA-256均保持一致 |
| 独立支撑包复现 | baseline与c0、种子701：答案与评测JSON逐字节一致 |

最终完整执行加恢复耗时 57.32 秒；这是当前测试机器的单次观察，不是性能保证。

PDF SHA-256：`6babefac24a0b2b2dd0644c60d5a765ebab2363a798f80cd4df66eb372af0a8b`。

支撑包 SHA-256：`c62141ea876acecd1664ee2b93d8d7d35a5e5c338aa63db57532f7d9798bf2ce`。

## 测试真实性边界

数值求解、独立有限域枚举、假设诊断、图片导出、TeX编译、文档检查、支撑包和独立复现实际执行。规划/假设审查/双模型评价响应是固定测试夹具；Claude 故障由注入产生，Exa HTTP 响应是来源片段重放。不能据此宣称真实 GPT 与 Claude 联跑，或真实大模型自主解决了一道完整历史国赛题。

另通过连接的 Exa 工具实际检索了单机序列准备/线性延迟，以及位置相关劣化的反例文献。这与验证本次用户 API 密钥不是同一件事。本地环境无法解析 Exa HTTP 域名，且无 Codex、Claude、Docker 可执行程序；上述真实联合验收明确为 NOT_RUN，用户密钥未写入代码、日志或更新包。

## 本轮发现并修复

关键审查仅允许 Claude 的硬约束以及启动阶段强制 Claude probe；已终止的供应商失败污染 step 状态；恢复时已成功审查被重新调用；同一负面审查被不同父任务名重新投票；文献只凭模型引用无法检查；没有实际假设诊断就进入写作；为抽样审查重复渲染所有长附录；重复构建 AI 详情导致支撑ZIP摘要变化。

当前边界：新上下文减少锚定，但两个同模型席位不是统计独立；搜索不是假设证明；启发式过滤不是完备DLP；支持论文生产链不等于获奖质量。正式国赛仍需团队主导核心建模和真实逐项人工核验。

## 可复现命令

```bash
python -m pytest -q
python -m cumcm_harness verify-vendor
python -m cumcm_harness.resilience_demo workspaces/resilience-demo
python -m cumcm_harness.resilience_demo workspaces/resilience-demo
```

新机器需要中文XeLaTeX及Inkscape。第二次是恢复，不是新的独立统计实验。真实运行使用 `configs/exa-resilient.json` 并配置现有CLI认证及 EXA_API_KEY。
