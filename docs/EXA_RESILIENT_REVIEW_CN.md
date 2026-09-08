# Exa 对抗建模与双模型审查升级（0.2.0）

## 变更依据

基于 `mythrise/math_harness` 的 `3b233edaa5d2c9ec95bf67ae2d495e0d662c3292`。保留已有 verifier preflight、前置/执行阶段审查边界、Claude 本机认证、无默认美元上限、Fable 禁止隐式换模型、MOSAIC、OurWork、冻结评测与人工签核设计。

旧代码在启动时同时 probe 两个 CLI，又在 review_quorum 中要求关键审查 provider 必须为 claude。仅替换一条调用不能解决单点故障。本次同时修改启动、供应商适配、调用账本、职责法定席位、恢复和 doctor。

## 新链路

PI → Exa 文献研究员 → 建模手 → 假设卡 → 独立 Exa 反方检索/批评 → 双席文献审查 → 双席数学/实验计划审查 → 独立评测器 → preflight → 代码与真实实验 → 强制假设诊断 → 确认 → 论文与矢量图 → PDF 审查 → 支撑包。

文献命中只是 RETRIEVED_NOT_VALIDATED。源 URL、片段、摘要与请求缓存可审计；每个假设对应一张卡，记录类型、可证伪检验、接受准则和失败动作。反方必须执行 counterexample 查询，输出支持、相反或适用范围证据。控制器拒绝不存在的 source_id、伪造引语、遗漏假设、明确反例和被包装为 PASS 的未知项。只有通过独立文献审查的来源才进入论文引用库。

**Exa 不执行统计检验。** 它用于寻找论据与反例；经验性/简化假设还必须有实际执行的 `hypothesis_Hn` 程序检查。这些检查通过只支持声明的诊断范围，不证明假设为真实世界规律，也不防止一个低质量模型设计无意义测试。因此继续保留源码审查、独立评测、负控制、完整实验矩阵和人工核验。

## 审查可靠性

默认每职责两席，主席 Claude、交叉检查席 Codex。每席是独立新上下文且绑定同一被审快照；Claude 故障时可形成两个不同调用的 Codex 席位。图像审查目前仅支持 Codex 图片输入，因此两席均为 Codex，不能宣称 Claude 已看图。

可接管故障：已观测的 CLI 缺失/不兼容、启动错误、终止后的超时、非零退出、供应商错误、无效 JSON、缺失结构化输出、纯格式合同错误。每 provider 默认最多两次，短退避，连续失败熔断六十秒。新一轮可以重试恢复后的 provider；此前成功的职责结果与已完成实验直接复用。

不可接管为通过的情况：有效 FAIL/BLOCKED、具有 P0/P1 的矛盾 PASS、必要检查未知、摘要不一致、意外工具使用、未知 RUNNING 状态、预算耗尽。此处需要修正证据/模型或人工确认，而不是“找一个肯通过的模型”。拒绝回执持久保存；同一证据快照不能靠换父任务名称重选审查结果。

两个供应商都失败时状态为 WAITING_REVIEW_PROVIDERS，保留全部成功实验。修复本机服务/认证后重新 `run`，正常已终止的接口失败不需要删数据库。只有进程是否仍在运行不确定的任务，才使用已有显式 recover 命令。接口重试也计入 max_model_calls，不会无限花费。

## Exa 与隐私

Exa HTTP 固定目标为 `https://api.exa.ai/search` 和 `/contents`，优先读取 EXA_API_KEY 环境变量；未设置时读取操作员通过 `set-exa-key` 保存的 `.runtime/credentials/exa-api-key` 本机私有文件。目录权限为 700、文件权限为 600，凭证不纳入 Git、Docker 镜像、工作区或支撑包。拒绝跨地址重定向、响应中的密钥回显、私有源 URL 和带凭证的源 URL；成功缓存绑定内容摘要，HTTP/逐 URL 失败不会伪造空文献。对 429/5xx 做有限重试。保留公开来源片段供溯源，不将密钥、请求头或原始题目放入检索日志。

实践模式只发送抽象查询，并有题目原文/路径/标识符过滤。**这只是启发式过滤，不是完备敏感信息防泄漏证明。** 对严格敏感任务应人工审定查询。contest 模式必须将查询逐字加入冻结配置 `exa_approved_queries`，空名单会阻塞研究。正文题意和私有数据不会由代码自动拼接进 Exa 请求。

更新包制作阶段（2026-09-07）使用连接的 Exa 工具检索了正面与反例文献；当时的本地 HTTP 客户端因执行环境无法解析外网 DNS，仅做注入传输测试。该记录不证明本机 Exa HTTP 认证成功。本机新执行结果与依赖状态另见 [本机升级验收](../reports/EXA_UPGRADE_LOCAL_CN.md)。密钥不要放进公开仓库。

官方接口参考：
- https://exa.ai/docs/reference/search
- https://exa.ai/docs/reference/get-contents
- https://developers.openai.com/codex/noninteractive/
- https://code.claude.com/docs/en/headless

## 启动与升级

使用 Python 3.11+，已有 `.venv` 可以继续使用。源码与运行指纹改变后，旧冻结工作区不自动迁移，不能改写旧 fingerprint 冒充可复现；保留旧成果并创建新工作区。已有特殊本机配置、原题和凭证不被此次更新覆盖。

```bash
python -m pip install --no-build-isolation -e '.[dev,excel]'
python -m pytest -q
python -m cumcm_harness verify-vendor

# 隐藏输入并保存到本机私有文件；不要把真实值放入命令参数。
python -m cumcm_harness set-exa-key

# 为兼容已有命令保留镜像标签，必须重新构建而不是复用旧镜像。
docker build -t cumcm-egoharness:0.1.0 .
python -m cumcm_harness doctor --live --config configs/exa-resilient.json
python -m cumcm_harness init workspaces/exa-new \
  --problem /absolute/path/problem.md --data /absolute/path/data \
  --config configs/exa-resilient.json
python -m cumcm_harness run workspaces/exa-new
```

Codex 必须有可用认证。Claude 可缺失或故障，审查将显式降级；doctor 的 ready 仅说明依赖/probe 与密钥存在，不是实际模型认证或论文验收成功。模型名默认使用本机 CLI 配置，不从当前环境猜测账户有权使用哪个型号。`clean_env` 不把 EXA_API_KEY 传给模型子进程或数值代码。

不调用模型、不需要 Exa 密钥的完整回归：

```bash
python -m cumcm_harness.resilience_demo workspaces/resilience-demo
python -m cumcm_harness.resilience_demo workspaces/resilience-demo
```

这是故障注入与重放测试：规划、模型审查、文献网络响应是夹具；MOSAIC、独立枚举评价、实际假设诊断、XeLaTeX、OurWork 与支撑包是真的。真实双 CLI + Exa HTTP + Docker + 历史完整赛题的质量验收仍需在有认证的环境运行。

## 文件与边界

新模块 `review_board.py`、`literature.py`、`resilience_demo.py`；新 profile `configs/exa-resilient.json`；新增文献反方 skill。输出 `literature/accepted.json` 和 `execution.json` 被纳入支撑清单。所有原始 vendor 文件保持未改。PDF 仅渲染本阶段要求的正文及附录样本，完整附录仍在 PDF 中，正式提交仍需人工完整检查。

默认旧配置 `configs/practice.json` 的 LOCAL_EVIDENCE_ONLY 不会被悄悄改为联网；请显式选择新 profile。需要禁用在线研究的受限流程，可在新配置中设置 literature_enabled=false；不能把这种运行描述为完成了 Exa 文献审查。

未指定 profile 时也保持离线默认。`doctor --config` 按所选配置检查依赖，只在在线文献流程要求 Exa 密钥。在线开关与本地网络策略冲突时，初始化即拒绝，不先消耗模型调用。

本机集成还补强了恢复边界：每个审查调用在执行前保存待完成意图，恢复时沿用原始 step key；修改父任务名称或增加运行轮次不能绕过 RUNNING/完整性失败。已成功调用但尚未写入审查缓存时发生中断，恢复只重放成功回执。直接作者调用的接口失败保留 FAILED 状态与显式 recover-step 路径。Exa HTTP 200 但内容不可用的响应不缓存，服务恢复后可重试。
