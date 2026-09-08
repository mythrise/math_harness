# Exa R2：冻结研究范围、原文证据与可恢复请求

本升级按附件 R2 接入当前 0.3.0 harness。附件原文件保存在 `docs/exa-r2-handoff/`，其“未实施”说明是交接时状态；本机实施结果见 [验收报告](../reports/EXA_R2_LOCAL_CN.md)。未找到附件提到的原始 Search API Reference Markdown；已核对 [Exa Search 官方说明](https://exa.ai/docs/reference/search-api-guide-for-coding-agents) 与 [Contents 官方说明](https://exa.ai/docs/reference/contents-api-guide-for-coding-agents)。接口说明与账户实际能力分开记录。

## 新任务入口

```bash
./scripts/cumcm doctor --live --config configs/exa-modeling-compatible.json --exa-policy configs/exa-policy-r2.json
./scripts/cumcm init workspaces/NEW_TASK --problem /ABS/PROBLEM.md --data /ABS/DATA \
  --config configs/exa-modeling-compatible.json --exa-policy configs/exa-policy-r2.json
./scripts/cumcm run workspaces/NEW_TASK
./scripts/cumcm exa-status workspaces/NEW_TASK
```

`NEW_TASK` 和绝对路径须换成实际新任务。`init` 默认以初始化 UTC 时间冻结 research cutoff；可通过 `--research-cutoff 2026-09-08T00:00:00Z` 指定过去时点。不得向已冻结工作区添加或修改 sidecar。主配置只改 Exa 三项：80 次尝试、兼容结果数 6、默认超时 45 秒；原模型设置、审查与其他限额保留。R2 实际每条检索返回数由固定 profile 决定，反方可为 8 条；兼容字段不会覆盖 profile。主配置与策略两层总预算取更小值，doctor 显示有效上限。

旧 profile、不带 sidecar 的旧工作区仍选择 legacy adapter。代码升级会改变输入指纹，旧工作区恢复需其原代码版本与镜像；不能通过重算指纹迁移。回退新任务时使用原 profile、不传 `--exa-policy` 并重新 init。

## 接受什么、怎样处理、输出什么

`exa_policy.py` 接受严格策略 JSON，验证字段后冻结 run ID、UTC cutoff、策略/适配器/提取器/能力版本摘要。`RequestCompiler` 只把 REST 字段送给接口：search 内容在 `contents` 内，contents 提取参数在顶层；未知键、错误类型和改动过的模板在 HTTP 前拒绝。

`literature_r2.py` 接受带 H-ID 的抽象方法查询。首轮同时跑 foundations 与无 category 的学术补查；每条关键假设都必须有支持和反方映射。反方上下文不携带作者 PASS。模型选择已有来源后，控制器按每批最多 4 URL 读取 24000 字符；必要且命中上限时允许 60000 字符扩读。总计最多 24 个全文 URL，模型包最多 40000 个来源字符，截断窗口附原文偏移与覆盖说明。

输出来源同时包含 URL 身份、不可变 snapshot、DOI/arXiv work、版本/内容冲突、未知或估计日期及未来版本标记。原文、提取摘录、生成摘要、生成综合分别保存。全文留在本机内容寻址存储；发布证据导出使用元数据与短引文。`quote_start/quote_end` 必须逐字定位到当前 snapshot 的原文；随后仍需双席审查语义、适用范围和上下文。引用存在不证明假设；经验性/简化假设还必须实际通过 `hypothesis_Hn` 程序诊断。

## 配额、恢复与费用

80 是 HTTP 尝试上限，包含检索、精读、能力检查、重试和降级；每逻辑请求最多 3 次，分阶段配额 16/24/16/8/16。SQLite 原子预占，逐次记录意图及结果；同请求 single-flight。共享限流按本机凭证来源隔离，最多 2 并发、每秒约 1 请求；连续 3 次临时失败熔断，冷却后只允许一个半开探测。改变密钥不会重置该来源的限流状态。

429/503/超时有限退避，遵守 Retry-After，超出本次等待上限则保存等待状态。401/403 保留 `WAITING_EXA_AUTH`，不会切换认证模式或匿名服务。未知 400/422 不循环重试；只有明确不支持 publication 或 Dynamic Highlights 才能使用预定义且已授权的降级。有效负面科研结论不触发降级。

逐 URL 的 contents 状态保留成功项，只重试临时失败 URL。HTTP 200 空结果记 EMPTY，可换研究角度，不能写成“文献不存在”。在途未知请求不会自动重发：先用 `exa-status` 核对进程与服务结果，确认原进程已停止后，才可由操作员运行 `recover-exa WORKSPACE REQUEST_ID --reason '实际核对说明' --external-process-stopped`。命令并不保证远端没有计费，原尝试次数始终保留。

同工作区通过完整身份摘要回放不可变结果；跨工作区缓存普通检索最多 168 小时、当前 API 文档最多 24 小时、规则不跨运行缓存、空结果 10 分钟。新 cutoff、策略、范围或版本改变请求身份。费用只汇总实际返回值，缺失记 UNKNOWN；不承诺固定费用或网络恰好一次计费。

## 可选能力与 contest

Dynamic Highlights、deep 默认关闭。启用须在新策略中显式 opt-in，再 init。动态请求必须带准确的 `Exa-Beta: dynamic-highlights-2026-08-28`，不能同时使用 `maxCharacters`。`exa-probe WORKSPACE --dynamic --query '公开抽象方法查询'` 会计费并计入预算，实际比较动态与逐来源摘录覆盖；fixture 不会认证 live 能力。成功响应只能说明接口接受和观察到的覆盖，不能证明供应商内部算法或更高召回。

deep 仅在已完成两个不同 auto 查询且仍有 contradicted/inconclusive 的 REVISE 后，由控制器登记升级依据；最多两个逻辑请求。生成综合只用于后续研究导航，原负面结论仍保留。`outputSchema` 使用严格四字段平坦结构；任何搜索类型实际返回的 output 都独立保存，grounding confidence 不提升证据等级。

contest 除原批准查询名单，还需逐项、带签名的 query/profile/domain/time/fetch URL/expiry/降级/扩读授权；批准绑定当前运行和完整冻结快照。缺操作员密钥、越界、过期的新网络操作均阻断。模型不得执行 approve、读取操作员密钥或伪造修改记录。实践模式的隐私过滤不是完美语义 DLP；源网页内容只按数据处理，不执行网页指令。Bearer 从原凭证加载器在 HTTP 边界注入；显式 legacy_x_api_key 兼容，不因 401 自动切换。

## 验证命令

```bash
.venv/bin/python -m pytest -q tests/test_exa_r2_*.py
.venv/bin/python scripts/validate_exa_r2_live.py --workspace workspaces/NEW_PUBLIC_SMOKE --report reports/NEW_PUBLIC_SMOKE.json
.venv/bin/python -m cumcm_harness.exa_r2_demo workspaces/NEW_R2_DEMO
```

烟测最多 8 次公开 HTTP 尝试，不调用 LLM。demo 使用固定模型/来源夹具，数值在 Docker 内实际执行，XeLaTeX 实际生成 PDF 与支撑包。二者不能替代真实多模型整题论文验收。
