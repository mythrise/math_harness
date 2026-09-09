# 0.4.0-rc1 当前接入

本轮在 `.runtime/materials-v040-worktree` 新建隔离检出与独立 `.venv`，原主工作目录缺失的 `cumcm_harness/` 未被覆盖。请进入该检出后使用 `./scripts/cumcm` 或 `.venv/bin/python`。Python 包规范化版本为 `0.4.0rc1`，新运行镜像为 `cumcm-egoharness:0.4.0-rc1`；旧镜像与旧工作区不改。

已有 Claude 用户认证、`claude-opus-5` 和 `max` 默认设置继续保留。原私有 Exa 文件未复制；公开 live 验证器可通过明确的 `--exa-credential-file` 与 `--exa-shared-ledger` 读取已有安全加载器和共享 HTTP 租约。其他运行继续使用现有 `EXA_API_KEY` 环境变量或当前检出的私有凭证位置，不把密钥写入配置。

具体新增接口与本轮验证见 [0.4 接入说明](MATERIALS_V040_INTEGRATION_CN.md)。以下是先前部署记录，不能代替本轮运行回执。

# 当前项目的 Codex 部署

2026-09-08 算法库升级后，当前 editable 环境版本为 **0.3.0**。新工作区和示例配置默认使用 `cumcm-egoharness:0.3.0`，该生产镜像及 `0.3.0-test` 验证镜像已经构建。当前验收见 [0.3.0 本机报告](../reports/ALGORITHM_UPGRADE_LOCAL_CN.md)；下文的 0.1.0 安装和探针信息为原始部署记录。旧工作区保持冻结，升级后的真实任务重新初始化。

本项目从 `CUMCM_EgoHarness_v0.1.0.zip` 直接解压到项目根目录，保留完整源码与附件目录。
项目级入口为根目录 `AGENTS.md` 和 `.agents/skills/` 下的 8 个技能；不需要另外复制到全局技能目录。
Codex 的项目级技能发现路径见 [OpenAI 官方文档](https://learn.chatgpt.com/docs/build-skills)。

下一轮可直接调用 `$cumcm-orchestrator`。若界面未刷新技能列表，重新打开当前项目会话。
例如：`$cumcm-orchestrator 先检查本项目运行环境，再根据我提供的题目和数据初始化 practice 工作区。`

## 本机入口

系统 `python3` 为 3.9，低于项目要求。已用 Python 3.13 创建 `.venv`，以 editable 模式安装 `.[dev,excel]`。
本机同时安装了 Inkscape、DejaVu 字体，并为已有 TinyTeX 补装 `fvextra`、`xurl` 及其依赖。
无需激活环境即可执行：

```sh
./scripts/cumcm doctor --live
./scripts/cumcm schema
./scripts/cumcm verify-vendor
.venv/bin/python -m pytest -q
```

也可以先 `source .venv/bin/activate`，再使用原始 README 中的 `python -m cumcm_harness` 或 `cumcm` 命令。

## 题目工作区

以下题目和数据路径是占位符，应换成实际路径后执行：

```sh
./scripts/cumcm init workspaces/practice \
  --problem /absolute/path/problem.md \
  --data /absolute/path/data \
  --config configs/practice.json
./scripts/cumcm run workspaces/practice
./scripts/cumcm status workspaces/practice
./scripts/cumcm audit workspaces/practice
```

`run` 会调用真实模型。Claude 适配器使用 `--safe-mode --setting-sources user`，由本机 CLI 读取已有用户级认证、服务地址和模型配置；无需为 harness 另外复制凭证。执行工具、MCP、插件和 hooks 仍被禁用。认证继承方式参见 [Claude CLI 官方说明](https://code.claude.com/docs/en/cli-reference)。
Codex 使用已配置的 CLI 认证。部署时的版本/参数探测不证明模型调用成功，`doctor --live` 也不验证 API 认证。
生成代码必须通过 Docker 执行；正式参赛的人工签核仍由操作员独立完成。

Docker 镜像 `cumcm-egoharness:0.1.0` 已构建，使用官方 Python 3.11 Bookworm ARM64 基础镜像。已通过正式 Docker 执行器验证一次 MOSAIC 求解和独立评测。原下载超时通过宿主代理下载基础镜像、导入 Docker 后构建解决；没有修改或重启 Docker daemon。
构建命令及最新 Claude 请求状态见 `reports/live-configuration/STATUS.md`。`doctor --live` 通过只代表 CLI 参数与镜像可探测；真实模型请求需单独验证。

## 本次证据

初始安装与演示记录位于 `reports/local-deployment/`；后续 Docker / Claude 配置以 `reports/live-configuration/STATUS.md` 为准。
压缩包自带的其他 reports 和 `examples/validated_run` 是上游交付证据，不属于本机新运行。
原始分发清单保持不变；本地适配器、测试、指引的变更另行记录，既有工作区结果不改写。核心源码改变后应初始化新工作区。

## Claude 默认模型与推理强度（2026-09-09）

新工作区默认显式使用 `claude_model: "claude-opus-5"` 和 `claude_effort: "max"`，适配器向 Claude CLI 传递 `--model claude-opus-5 --effort max`。通用练习、竞赛和 Exa 配置已同步。认证继续由本机 Claude CLI 读取。`claude_effort: null` 可选择继承 CLI 默认推理强度。

已有工作区的冻结配置和回执保持原样；源码或模型配置变化后应初始化新工作区。以 Fable、Opus 4.6 命名的历史专用配置仍显式选择其原模型。
