# CUMCM-EgoHarness 0.2.0

**Codex 建模／编码／论文 + Exa 文献对抗 + Claude/GPT 审查接管 + 确定性实验内核。**

本次更新基于已有 0.1.0 仓库，不改原版 MOSAIC/OurWork，不复制或覆盖本机凭证。新增独立文献反方、可执行假设诊断、双席审查、Claude 故障的 GPT 接管、熔断与恢复。**真实否定意见不能被切换模型绕过。**

先读 [升级与完整运行说明](docs/EXA_RESILIENT_REVIEW_CN.md) 和 [本机升级验收](reports/EXA_UPGRADE_LOCAL_CN.md)。[更新包上游验收](reports/EXA_REVIEW_ACCEPTANCE_CN.md) 保留制作时的测试与远程 403 记录，不代表本机本次推送状态。旧版测试、部署及真实赛题进度仍保留在 `reports/`。

后续 [Exa 真实接口验收](reports/EXA_LIVE_AUTH_20260908_CN.md) 已通过支持/反例检索、正文提取及缓存重放。现支持通过 `set-exa-key` 保存本机私有凭证，新进程自动读取；环境变量 `EXA_API_KEY` 可覆盖本机凭证。真实双模型与完整赛题联合验收尚未执行。

## 快速验证

已有本机部署继续使用 `.venv/bin/python` 或 `./scripts/cumcm`；其他环境先创建 Python 3.11+ 虚拟环境。保留完整仓库并使用 editable install。

```bash
python -m pip install --no-build-isolation -e '.[dev,excel]'
python -m pytest -q
python -m cumcm_harness verify-vendor
python -m cumcm_harness.resilience_demo workspaces/resilience-demo
```

最后一条命令是**明确标记的故障注入工程测试**，不调用真实模型或 Exa HTTP、不需要密钥。数值求解、独立评价、假设诊断、LaTeX 编译和支撑包生成实际执行。它不证明真实多模型自主完成国赛题，更不代表已超越其他系统。PDF/矢量输出需要 `xelatex`、`inkscape` 及原文档所列中文 TeX 环境。

## 使用真实服务

Codex CLI 需要有效认证。Claude CLI 使用既有用户认证／服务地址／模型配置，保留 safe-mode，禁用执行工具和 MCP；无需强制更换为 API-only 登录。Claude 不可用时可由新的 Codex 审查调用接管。GPT 同样不可用时暂停保留状态，不假装完成。

首次使用可通过隐藏输入保存 Exa 密钥；文件位于 `.runtime/credentials/exa-api-key`，目录权限 `700`、文件权限 `600`，被 Git 与 Docker 构建上下文排除，也不进入工作区和支撑包。环境变量 `EXA_API_KEY` 优先于本机文件。**不要把密钥写进受版本控制的文件、config.json、提示词或日志。**

```bash
./scripts/cumcm set-exa-key

docker build -t cumcm-egoharness:0.1.0 .
python -m cumcm_harness doctor --live --config configs/exa-resilient.json
python -m cumcm_harness init workspaces/exa-new \
  --problem /absolute/path/problem.md \
  --data /absolute/path/data \
  --config configs/exa-resilient.json
python -m cumcm_harness run workspaces/exa-new
```

镜像标签为兼容已有部署保留，升级后必须重建。默认旧 profile 的 LOCAL_EVIDENCE_ONLY 不会静默启用网络；使用上面的新 profile。更新了源码、环境或冻结配置时创建新工作区，保留旧证据，不手工改 fingerprint。相同新工作区再次 `run` 才是恢复。

题面支持 Markdown、文本和可提取文本的 PDF；扫描件或复杂图示必须提供已核验转录。可通过既有 `--confirmation`、`--private-dev`、`--private-confirm`、`--sources` 指定独立确认数据、私有参考和人工核验来源。无独立确认数据时明确标记为同实例种子重复，而非跨数据泛化。

## 编排与验收

文献研究员 → Exa 支持证据 → 建模手与假设卡 → 独立反方 Exa 反例检索 → 双席文献／数学／实验审查 → 独立评测器 preflight → 编码与真实实验 → 强制假设诊断 → 开发选择后冻结确认 → 证据写作 → PDF 审查和支撑包。

每个关键审查职责默认两个新上下文席位。接口终止性故障有限重试并显式接管；有效 FAIL/BLOCKED、必要检查未知、数据或摘要损坏、未知运行状态和预算耗尽不能靠换供应商通过。图像输入仅由支持该能力的 Codex 适配器处理。Exa 搜到文献不等于假设成立，经验性和简化假设需实际程序诊断。

`WAITING_REVIEW_PROVIDERS` 或 `WAITING_RESEARCH_PROVIDER` 表示保留成功阶段、等待依赖恢复。未知 RUNNING 任务仍必须先核对外部进程，再使用显式 recover；不要删除数据库重新伪造一轮成功。

## 正式国赛模式

仍保留 2026 规则下的团队主导核心建模、逐项人工审查及 plan/release 签核，不自动提交、不代签。contest 在线研究仅允许操作员预先逐字批准的 `exa_approved_queries`；空列表会阻塞。仅做启发式过滤的 practice 模式不是敏感信息防泄漏的正式保证。

既有 `approve --stage plan/release`、HMAC 摘要绑定、匿名检查、AI 工具使用声明、完整源码附录和论文/支撑包大小限制均保留。HMAC 不是法律电子签名，也不能证明签核者实际读过内容。

## 主要目录

```text
cumcm_harness/literature.py       Exa 检索、假设卡、反方审查、检验门禁
cumcm_harness/review_board.py     Claude/GPT 席位、接管、熔断、证据法定人数
cumcm_harness/controller.py       确定性全链路
cumcm_harness/resilience_demo.py  故障注入到完整论文的工程回归
.agents/skills/                   Codex skills（含新增文献反方）
configs/exa-resilient.json        新在线研究配置，不含密钥
vendor/                          原版 MOSAIC 与 OurWork
reports/                         分开记录真实数值、夹具与尚未运行的验收
```

其他设计和历史部署细节：`docs/ARCHITECTURE_CN.md`、`docs/LOCAL_CODEX_SETUP_CN.md`、`reports/live-configuration/STATUS.md`、`benchmarks/PROTOCOL_CN.md`。本机私有日志、凭证、赛题数据与运行工作区不纳入 Git。
