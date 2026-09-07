# CUMCM-EgoHarness 0.1.0

**Codex 建模 / 编码 / 论文 + Claude 关键审查 + 确定性实验内核。**

本仓库包含当前 harness 源码、项目级 Codex skills、Docker 构建文件、测试、演示以及原版 MOSAIC/OurWork 依赖。Claude 单次调用默认不设美元费用上限；指定 Fable 时关闭自动换模型。最新本地工程验证及真实赛题进度见 [GitHub 快照说明](reports/GITHUB_SNAPSHOT_CN.md)。

本机凭证、虚拟环境、原始 CLI 日志、实验数据库、赛题输入及下载压缩包不纳入 Git。下文及本地部署文档中指向这些本机目录的链接需要在自己的环境运行后生成。`examples/validated_run` 是原始交付中的演示证据，不能当作真实赛题论文。

这是一套可执行的本地 harness，而不是把角色提示词拼在一起。代码、输入、评测器、阶段、种子、资源与环境进入内容寻址；只有可追溯且通过验收的结果才能成为论文数值。2026 正式参赛模式在核心建模、最终发布前要求真实人工签核，不自动提交。

## 本次交付的边界

下表是原始压缩包的交付记录。本机后续部署与配置结果见 `docs/LOCAL_CODEX_SETUP_CN.md` 和 `reports/live-configuration/STATUS.md`。

| 能力 | 本次状态 |
|---|---|
| 原始 MOSAIC v14 封装、独立目标重算、真实多种子实验 | 已执行，见 reports 和 examples/validated_run |
| 原始 OurWork v16 二十模板空编辑回归与矢量输出 | 已测试 |
| 状态机、内容哈希、并行发布、恢复、门禁、CLI 解析 | 已测试 |
| 中文 XeLaTeX、完整源码附录、AI 详情、独立支撑包 | 实际构建；见报告 |
| 真正调用 Codex/Claude | 本环境未安装，未执行。假 CLI 测试只是接口契约测试 |
| Docker 隔离执行 | 已实现，但本环境没有 Docker，未做容器实测 |
| 完整历史国赛题 / 四个上游系统同预算对比 | 未执行，不能声称超越全部系统或全国一等奖能力 |

`demo` 的规划、代码选择、审查答复是**事先写好的夹具**，数值求解和独立评测是真的。`run` 没有夹具退化路径，必须能调用真实 CLI 与 Docker。请勿把演示 PDF 当作官方赛题论文。

## 先运行无需模型费用的演示

Linux / macOS；Windows 使用 WSL。必须保留整个源码目录，并使用 editable install，不要只拷贝 `cumcm_harness/`。

```bash
cd CUMCM_EgoHarness
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev,excel]'
python -m cumcm_harness doctor
python -m pytest -q
python -m cumcm_harness verify-vendor
python -m cumcm_harness demo workspaces/demo --candidates 2 --fe-budget 192
```

PDF/矢量导出还需本机有 `xelatex`、`inkscape`，中文 TeX 包、`fvextra`、`xurl`，以及 DejaVu Sans Mono 或支持希腊字母的等宽字体。Ubuntu 可由操作员安装 `texlive-xetex texlive-lang-chinese texlive-latex-extra inkscape fonts-dejavu`。本包不包含字体文件。

完成后读取：

```
workspaces/demo/run_summary.json
workspaces/demo/selection.json
workspaces/demo/confirmation.json
workspaces/demo/deliverables/paper.pdf
workspaces/demo/deliverables/support.zip
```

相同工作区再次执行 `demo` 是恢复，不是新的独立试验。不可通过删除失败记录来制造新结果。

Claude 单次调用默认不设美元费用上限：`claude_call_budget_usd: null` 时不向 CLI 传递 `--max-budget-usd`。模型调用超时、总调用次数与数值实验 FE 预算仍由各自配置控制。已冻结工作区保留原配置；新的默认值不追溯修改历史运行。

## 真实模型运行

先按官方文档安装并配置 Codex CLI、Claude Code CLI、Docker。Claude 适配器调用本机 CLI，使用 `--safe-mode --setting-sources user`，让 CLI 自行读取用户现有认证、服务地址与模型设置，同时关闭自定义插件、hooks、技能和 MCP；内置执行工具仍禁用。harness 不复制或转换凭证，也不硬编码某种订阅或 API 认证方式。Codex 使用其 CLI 默认认证或支持的环境变量；不硬编码某个可能下线的模型名称。

```bash
# 凭证由操作员设置，不写入仓库、提示词、题目或源码。
# 本机 Claude CLI 应已配置并能完成实际请求。
# Codex CLI 应已经完成有效认证。

docker build -t cumcm-egoharness:0.1.0 .
python -m cumcm_harness doctor --live
python -m cumcm_harness init workspaces/practice \
  --problem /absolute/path/problem.md \
  --data /absolute/path/data \
  --config configs/practice.json
python -m cumcm_harness run workspaces/practice
```

题面可为 Markdown、文本或含可提取文本的 PDF。**复杂图示不会被文字解析自动理解**；应先核实图表，提供已校验转录及解释。扫描 PDF 会明确阻塞，而不是编造识别内容。数据可包含 CSV、JSON、XLSX；导入不重算 Excel 公式，不做隐式插值。

可用 `--confirmation DIR` 指定独立确认数据、`--private-dev DIR --private-confirm DIR` 提供只交给评测器的参考标签。没有独立确认目录时，系统明确记录 `SEED_REPLICATION_SAME_INSTANCE`，不冒充跨数据集泛化。已有已核验文献可通过 `--sources docs/sources-example.json` 导入；该示例仅含已核验的官方规则；具体模型仍需补充真实领域文献。

## 2026 正式参赛模式

```bash
python -m cumcm_harness init workspaces/contest \
  --problem /absolute/path/problem.md --data /absolute/path/data \
  --config configs/contest-2026.json
python -m cumcm_harness run workspaces/contest
```

首次会在建模门禁等待团队审查。团队必须真正主导、修改并理解核心建模；在尚未确认的问题上不要签字。编辑 `approvals/plan.review-template.json`，为每项填写采纳、修改、实际核验方法。操作员在独立终端保管至少32字符的 `CUMCM_OPERATOR_KEY`，然后：

```bash
python -m cumcm_harness approve workspaces/contest \
  --stage plan --review workspaces/contest/approvals/plan.review-template.json
python -m cumcm_harness run workspaces/contest
```

最终发布还会要求 `--stage release`，逐项核验 AI 输出并检查整篇 PDF。修改方案或证据后旧签核失效。HMAC 只是本地防误用的签核绑定，不是法律电子签名，也不能证明签核者真的读过内容。

**开发源码 ZIP ≠ 比赛支撑材料 ZIP。** 源码包保留研究来源与模板，体积可能超过20MB；系统生成的 `support.zip` 和论文单独受20MB门禁约束。承诺书与编号页不放入电子论文或支撑包。

## 源码地图

```
.agents/skills/        Codex 可读入口；独立的 MOSAIC / OurWork / autoresearch 技能
cumcm_harness/        确定性控制、真实 CLI、独立执行与论文发布
configs/ schemas/    配置及机器可校验合同
vendor/mosaic_v14/    附件算法原码，未修改
vendor/ourwork_v16/   附件矢量引擎与20个原始模板，未修改
examples/            固定演示代码、验收产物与独立复现入口
benchmarks/          四基线比较协议与已测/未测状态，不填虚假得分
reports/             本次测试、环境与实验审计
scripts/             支撑包独立复现
```

详细设计见 `docs/ARCHITECTURE_CN.md`，上游分析见 `docs/RESEARCH_REVIEW_CN.md`，运行和安全边界见 `docs/OPERATIONS_CN.md`，完整评测计划见 `benchmarks/PROTOCOL_CN.md`。最终测试数字以 `reports/TEST_REPORT_CN.md` 为准。
