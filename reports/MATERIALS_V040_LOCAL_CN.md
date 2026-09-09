# 0.4.0-rc1 本机接入与验证

日期：2026-09-09。工程升级与确定性验收 PASS；完整真实服务链 BLOCKED，因此保持 rc1。本文是本机实测，原包生产者报告保留在 `docs/materials-upgrade/TEST_REPORT_CN.md`，两者不混合计数。

## 来源与实施

输入包 SHA-256：`50505e5a6b98a56dd1be95f617aad1365c4b1098cf4879f433b150b192116ad8`，精确基线 `f1ff48beebf7084ada6f16fc135801f484605a52`。校验 111 项分发摘要；原安装器 dry-run 校验 49 个路径与 Git blob 后应用。原工具 23 项测试通过。清单副本见 `docs/materials-upgrade/upstream-provenance/`。

实际工作目录为仓库内 `.runtime/materials-v040-worktree`，使用独立 `.venv`。原主目录已有源码缺失及配置改动，保持原状；不能从旧目录的损坏源码直接运行本版。新运行命令与输入→处理→输出→接入点见 [接入说明](../docs/MATERIALS_V040_INTEGRATION_CN.md)。

已接入五类资料合同、开发数据只读审计、模型组合审查、14 角色/15 技能摘要绑定、正文后摘要、逐问论文映射、中文图表和实际交付文件封存。191 张资料卡仅供参考，外部方法仍为 EXTERNAL_NOT_RUN；MOSAIC vendor、冻结评测器、种子、审批与研究否决边界保持原约束。

## 实测结果

| 验证 | 结果 | 证据范围 |
|---|---|---|
| 当前宿主基础设施测试 | 483 PASS，0 fail/skip | 排除数值执行类文件；不是额外 483 个独立于全量的测试 |
| 当前 Docker 完整测试 | 574 PASS，0 fail/skip | 新隔离测试镜像中的完整测试集合 |
| 十族数值验证 | 两次均为 98 行、9 项诊断 | raw_results 与 diagnostics 按冻结协议排除耗时字段后跨运行一致；不是 LIVE LLM，也没有全局算法晋级 |
| legacy 与 R2 资料全链路 | 各 22 个 DONE 数值作业，实际 TeX 编译与封存完成 | 模型、检索、Claude 故障均为显式夹具；R2 使用真实冻结策略及账本 |
| 两条链路重放 | PASS | 禁止新增模型/HTTP/Executor/TeX 调用；PDF、ZIP、封存清单与预约/作业状态一致 |
| 支撑 ZIP 独立复现 | PASS | 41 个附录源文件字节一致；只挂载解包内容，在 Docker 对 baseline/c0 各复现 1 个冻结确认种子，答案和评估字节相同 |
| PaperKit 回归 | 86 个参考测试 PASS | 两示例、原生/长标题、starter 分支与预期失败；真实隔离 TeX |
| 论文返工回归 | PASS | 两版本 PDF、有效否决保留、重放不新增调用、22 个 DONE 作业 |
| 隔离回归 | 11 项 PASS | shadow 导入、退出/超时/输出限制、TeX 不挂载宿主 canary 等 |
| 当前运行镜像对齐 | PASS | 56 个核心 Python 文件及角色技能指纹与宿主逐项一致 |
| PDF 视觉抽查 | PASS（有限范围） | R2 正文全部 4 页、附录首尾 5/127 页、AI 详情 1/22 页；没有可见溢出/乱码/重叠，不声称人工审核了全部附录 |

原包初装测试为 99 PASS/1 字体错误；最初基础设施回归还有 7 个简化 Controller 测试夹具缺少新属性。完成字体兼容与测试夹具更新后通过。R2 首轮完整运行暴露 AI 详情长字段 Overfull，修复安全转义后的断行并用新工作区复测；旧失败记录保留。上述早期失败没有从当前 574 个测试中移除，也没有放宽门禁。

隔离及 PaperKit 回归在本轮较早的镜像快照执行；其摘要记录原 image_id。最终 56 核心文件指纹与最新 Docker 完整测试、legacy/R2、返工与支撑复现分别有回执。GitHub CI 将重新构建同一提交的全部镜像并复跑这些验证。

## 真实服务：部分验证，完整流程未通过

使用公开固定合成两问整数规划测试题、真实 Codex/Claude CLI 配置及 Exa R2，未传递真实参赛题或私有观测。每次新工作区最多 100 个模型预约、32 次 HTTP；没有恢复或篡改旧工作区。

- LIVE-01：2 次 Codex 有效响应；模型在初始查询虚构未创建 H-ID，HTTP 前被拒绝，0 次 HTTP/数值作业。修复仅增加明确的允许 ID 列表和 HTTP 前有界映射返工，保留原提案/错误，不捕获供应商或在途 HTTP 异常。
- LIVE-02：4 次 Codex 有效响应，3 次 Exa HTTP 全部 DONE，账本记录已知费用 0.021 美元（只代表 Exa，非模型总费用）。题面分析两次未通过 `Requirement must quote exact frozen problem offsets`，以 `ScientificRejection` 停止。
- LIVE-02 无数值作业、无未完成 step、账本审计 PASS。尚未进入 Claude 审查，故本轮 Claude 真实响应数为 0；可用性探针不冒充模型响应。没有为了通过验证而替换模型结果、手工修改偏移、扩大预算或改用 fixture。

因此，完整 LIVE 资料链、真实历史题盲评、正式队伍逐项人工审核均未建立。此限制不影响工程回归 PASS，但不应将 rc1 描述为已验证的自动解题产品。没有执行 approve、代签、论文提交或客户端上传。

## 提交证据

[机器摘要](MATERIALS_V040_LOCAL.json)与 `materials-v040/` 中的 JUnit、数值/重放/复现/运行指纹及 LIVE 摘要可检查。摘要已移除本机绝对路径；原始模型 prompt、认证文件、私有账本、旧工作区和临时 ZIP 均不提交。保留的视觉联系表为合成工程示例。

源码已推送 `main`：[`0885514`](https://github.com/mythrise/math_harness/commit/0885514996d2e8b7aa90152e5d97ab3f1d9b09ec)。[GitHub CI 34345927061](https://github.com/mythrise/math_harness/actions/runs/34345927061) 全部成功；下载产物后核对：483 基础设施测试、574 Docker 全量测试、86 PaperKit 参考测试均 0 fail/skip；两条资料链各 22 个 DONE 作业，重放 0 新调用；两次各 98 行数值及 9 项诊断按原冻结协议排除耗时字段后一致，原文件保留实际耗时差异。独立支撑复现、论文返工、11 项隔离回归均通过。CI 在 Linux 重新构建全部镜像，所有证据都绑定该源码提交，详见 [CI 回执](materials-v040/ci-receipt.json)。后续仅补充本段与验证回执，不改源码，使用 `[skip ci]` 提交标记。
