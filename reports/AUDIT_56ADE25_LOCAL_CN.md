# 56ade25 定向审查修复验收（本机）

基线 `56ade25f435c052f770bc018c562017eb3c3d5f3`。审查包 SHA-256：`2066ef9da4eb26149fb308ae7442b2086a935c118562d9bafca1aac61ab31032`。本文件报告本机新执行的证据，原生产者测试与旧 GitHub CI 不计作本轮成绩。

## F01–F13 对照

| ID | 修复行为 | 主要验证 |
|---|---|---|
| F01 | 编码/环境/文件名过滤；专用隔离 TeX 编译 | `test_audit_20260908_audit_regressions.py; validate_audit_isolation.py` |
| F02 | 已完成执行后的格式和证据错误记 FAILED 并保存回执 | `test_audit_20260908_audit_regressions.py` |
| F03 | 冻结 public/private evaluation 身份并在运行及缓存时校验 | `test_audit_20260908_audit_regressions.py` |
| F04 | 逐问 measurement 或摘要绑定的定性文件/文本证据 | `test_audit_56ade25_flow.py` |
| F05 | 拒绝覆盖可信模块；Python -I；依赖回执必需 | `validate_audit_isolation.py` |
| F06 | 正文页数取可信 appendix 编译标签 | `test_audit_20260908_paper_boundary.py` |
| F07 | 按全部轮次成功映射累计覆盖 | `test_audit_56ade25_flow.py` |
| F08 | 有状态租约、owner/lease ID、显式核对恢复；超时保留 UNKNOWN | `test_audit_56ade25_flow.py` |
| F09 | 全部反方候选有 disposition；critic 看到排除理由和摘录 | `test_audit_56ade25_flow.py` |
| F10 | NEEDS_CLARIFICATION 保留否定信号并要求后续有界回应 | `test_audit_56ade25_flow.py` |
| F11 | 否决后新 draft/new PDF；反馈稳定序列化支持重放 | `validate_paper_repair.py; test_review_board.py` |
| F12 | 每个候选代码及 variant 独立有界自测后才进全矩阵 | `test_audit_56ade25_flow.py; validate_paper_repair.py` |
| F13 | 有限边权累加溢出显式 ValueError | `test_audit_20260908_graph_overflow.py` |

## 工程优化与兼容性

- repair_reserve / final_verification 接入阶段账本，按实际 HTTP 次数显示零值；规则、实现文档与 deep 保留各自授权条件。
- 原文对象缓存按 URL/版本/内容摘要保存，响应缓存继续绑定研究 cutoff、策略和授权；没有跨研究身份转移许可或审查结论。
- source selection 可指定原始偏移和章节，引用定位保留原始文本坐标。
- 可用性、未知状态、预算、截止时间、编译与科学否决采用类型化异常；不再按错误文字猜测是否该返工。
- 有界任务 DAG 可按已完成分片恢复，SIGKILL 验证不会重算已完成分片。控制器告知接口用法；未宣称任意模型求解器自动使用该接口。

新增 `provider_schema.py` 修复本轮真实 Codex HTTP 400：仅调整传输 schema，可选 null 在返回后规范化，仍做完整本地校验；原始响应和规范化响应分别留存。新 TeX 镜像为 `cumcm-egoharness-tex:0.3.1`。具体运行与恢复方法见 [修复说明](../docs/AUDIT_56ADE25_REPAIR_CN.md)。

## 证据分栏

| 证据类别 | 本机观测 | 边界 |
|---|---|---|
| 最终完整容器测试 | **444 passed，0 failed，0 skipped** | 精确 XML 无损压缩保存 |
| 定向与控制流程 | 350 项控制流程；最终前 84 项定向；阶段用途补充 44 项 | 有重叠，不将它们相加当不同用例 |
| 真实 Docker/TeX 隔离 | **11 项通过（4 项 bundle 校验、7 项真实容器检查）** | 包名拦截、可信 worker、缺失/损坏回执、输出限额、超时、TeX 重放与人工 canary |
| 真实数值诊断 | **两次各 98 行、各 9 项诊断**；排除耗时后原始结果/诊断完全一致 | 2 个固定种子；外部候选和全局晋级均为 0 |
| 论文编译与重放 | **22 个数值作业、4 个 variant 自测、2 个不同 PDF**；完整重放不新增调用/作业且 PDF/ZIP 摘要相同 | 模型与 Exa 是显式合成夹具 |
| PDF 布局抽查 | 已查看摘要、全部正文、附录首/末页，未见重叠、裁切或缺字 | 总计 161 页、正文 4 页；没有声称逐页检查完整附录 |
| 真实 Exa HTTP | **3 个成功请求**，已知费用 **$0.016**；无遗留租约 | scouting/adversary/primary_source_fetch 各 1；final_verification/repair_reserve 均 0 |
| 最终镜像源码 | **45 个模块逐字节相同** | 标准 Dockerfile 安装依赖后增量 COPY 最后两个源码修正；最终 CI 使用仓库 Dockerfile 从源码完整构建 |
| 供应商原码 | **408 个文件校验通过** | MOSAIC/OurWork 原码未变 |

真实历史题最终状态为 **WAITING_REVIEW_PROVIDERS**。在最终提交 `a878703` 上恢复环境并新建工作区后，Codex 已实际完成 supervisor、初始检索、modeler、假设清单和支持检索共五次结构化响应。必需的 hypothesis_critic 角色先遇到 Claude `EXIT_NONZERO`，有界接管的 Codex 再达到 `TIMEOUT`；两次失败都保留，没有伪造审查 quorum，也没有未知步骤或租约。

此前的 schema 400、检索用途违约、180 秒规划超时，以及连接中断均保留。阶段用途修复后检索通过，600 秒上限下规划成功；最后一轮仍受 16 次模型调用及 16 次 Exa 请求上限约束。

五个历史题工作区合计保留 **18 次模型调用预算记录、16 次已完成 Exa 请求**，历史题 Exa 已知费用合计 **$0.112**，无遗留租约。上表 $0.016 是独立 HTTP 烟测费用，二者分列。Codex 未提供美元费用，不据此估计模型总费用。逐次回执见 [真实历史题摘要](audit-56ade25-evidence/historical-live.json)。

**真实 Claude 调用及其失败后的 Codex 接管已实际执行；Claude 成功响应、科学审查通过、历史题数值求解与论文完成没有建立。** 没有以合成审查补齐真实门槛。待供应商恢复后，由操作员显式继续该工作区；本次没有自动扩充预算或修改其冻结配置。

GitHub [CI 34315142691](https://github.com/mythrise/math_harness/actions/runs/34315142691) 对 `a878703` 全部通过：353 项基础设施、444 项完整容器测试、11 项隔离检查，以及两次各 98 行数值复现。已下载原始 CI XML/摘要核验，见 [CI 回执](audit-56ade25-evidence/ci-a878703.json)。

完整证据见 [JSON 报告](AUDIT_56ADE25_LOCAL.json)、[完整测试 XML.gz](audit-56ade25-evidence/full-tests.xml.gz)、[隔离验证](audit-56ade25-evidence/isolation.json)、[论文重放](audit-56ade25-evidence/paper-repair.json)。XML 为原始文件的无损 gzip 压缩，解压后可直接读取。原始模型包、CLI 日志、赛题输入和凭证不进入 Git。

## 保留的负例与未解决边界

- 应用修复前定向/基础组合：137 项中 36 失败、101 通过；原始 XML 和日志保留。初次整体验收中的两项 doctor 测试仍期待宿主 XeLaTeX，已改为验证容器后端。
- 真实集成发现图表 JSON 旁注误入 TeX 输入白名单，以及 TeX 字体包缺失；已修复。所有先前失败工作区保留。
- 论文重放曾暴露否决反馈 dict 字段顺序影响摘要；改用 canonical JSON，并新增第一次失败与缓存失败消息一致性检查。
- 一次运行遇到构建镜像同时变化，指纹检查正确阻断；最终验收须在依赖镜像构建结束后启动。
- 同进程依赖观察 hook 不能证明恶意 Python 的完整依赖行为；容器权限、挂载和网络隔离是实际执行边界。
- DAG 恢复不等于任意长任务都已分片；故障注入模型和 Exa 不等于真实审查质量；检索不等于实证假设检验。
- 真实初次检索返回了支持阶段不允许的 counterexample 用途，被完整保留并阻断；补齐 allowed_purposes 提示后使用新工作区，未放宽用途校验或改写旧响应。
- 最后复核发现支持阶段的 limitations 摘录未进入 critic，定向用例先失败再修复；批判输入改为全部候选中反证/局限性子集，保留对应排除理由。
- 没有代签人工审批、修改旧冻结工作区或提交比赛论文。完整附录视觉核对与逐项人工审核仍由团队完成。

## 可复现命令

```bash
.venv/bin/python -m pytest -q --ignore=tests/test_algorithm_upgrade.py --ignore=tests/test_algorithm_integration.py --ignore=tests/test_audit_20260908_graph_overflow.py
docker build -t cumcm-egoharness:0.3.0 .
docker build -f Dockerfile.test -t cumcm-egoharness:0.3.0-test .
docker build -f Dockerfile.tex -t cumcm-egoharness-tex:0.3.1 .
.venv/bin/python scripts/validate_audit_isolation.py --out workspaces/isolation-NEW
.venv/bin/python scripts/validate_algorithm_upgrade.py --out workspaces/algorithms-NEW --seeds 2 --seed-start 201
.venv/bin/python scripts/validate_paper_repair.py --workspace workspaces/paper-repair-NEW --report reports/paper-repair-NEW.json
```

每次验收使用新的空目录；已经完成或失败的运行输出不覆盖。
