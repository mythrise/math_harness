# 56ade25 审查修复：运行与兼容性

本轮针对 `math_harness_全面审查与定向修复_56ade25.zip` 的 F01–F13 和五项工程优化。实际验收、负例与外部服务边界见 `reports/AUDIT_56ADE25_LOCAL_CN.md`。旧工作区、固定评价器、种子、供应商原码及人工审核记录保持冻结；升级后重新初始化工作区，不修改旧运行指纹。

## 编译与执行

```bash
docker build -t cumcm-egoharness:0.3.0 .
docker build -f Dockerfile.test -t cumcm-egoharness:0.3.0-test .
docker build -f Dockerfile.tex -t cumcm-egoharness-tex:0.3.1 .
./scripts/cumcm doctor --live
.venv/bin/python scripts/validate_audit_isolation.py --out workspaces/isolation-NEW
```

TeX 通过独立的无网络、只读根文件系统、非 root 容器编译，唯一宿主机挂载是分阶段复制的构建输入与输出。不挂载 HOME、项目根或凭证。图表 JSON 旁注不进入编译输入；源码附录文件名严格过滤。保留 `-no-shell-escape`、资源限额和两遍编译。正文页数和视觉审查范围来自控制器插入的 `harness-appendix-start` 编译标签。

`openin_any` 不是操作系统隔离；TeX Live 2026 将其改为不生效的兼容选项，因此不将其视为安全边界。见 [TeX Live 已知问题](https://tug.org/texlive/bugs.html)。Docker 中的 Python worker 使用 `-I` 从已安装的可信包启动，排除当前目录注入；见 [Python 隔离模式](https://docs.python.org/3.11/using/cmdline.html#cmdoption-I)。Executor 在实例中固定镜像 ID，实际执行该 ID。

每个成功的求解器与评价器都必须有 `custom_dependencies.json`。依赖观察 hook 与模型代码处于同一个 Python 进程，不能证明恶意代码没有伪造记录或通过原生库读取其他文件。实际安全边界是容器权限、挂载及网络隔离；发布仍须核验支撑包复现。

测试驱动独有的 `test_scratch=True` 提供受限的 `/scratch` 临时文件系统，供假 CLI 和文件系统故障夹具使用。普通求解任务不启用它；真实任务的 `/tmp` 仍为 noexec。完整测试从冻结的源码快照启动独立 Python 进程，数值诊断使用生产镜像。

## 证据与失败恢复

公共输入与私有评价输入共同进入协议的分阶段冻结身份和作业 ID；执行前后、缓存返回均校验。已停止的进程输出缺失、坏 JSON/编码、错误指标或不完整逐问证据会留下明确失败及原始执行回执。未知外部执行保留待核对状态，不自动修复或重复提交。

`question_coverage` 必须与证据对应。默认问题类型为 quantitative，必须有相应 measurement；定性问题显式设置 `answer_type: qualitative`，并提供 `question_evidence`：

```json
{"id":"argument","question_id":"Q2","kind":"text","text":"经审查的定性论证","sha256":"文本 UTF-8 字节的 SHA-256"}
```

文件证据使用 `kind: file`、`path`、`description`、`sha256`，路径仅允许作业内 `solver/...` 或 `evaluation/...`，实际文件必须存在且摘要匹配。示例中的说明字符串须换成真实 64 位摘要。论文 writer 收到绑定作业的证据，独立审查仍负责判断论证是否成立。

每个候选代码、每个适用 variant 先跑有界独立测试，然后进入完整开发矩阵。测试失败是可重放的负面结果；已知失败不会被记成仍在运行，也不会借用 baseline 测试通过记录。

论文每个不同 draft 存放在 `paper_versions/<draft digest>/`。编译、语义和视觉失败回给 writer；收齐各视觉批次的否定意见后才要求新稿。相同失败 draft 不再写入或编译，相同被否决 PDF 不再换席位刷票。通过后的版本投影到 `paper/` 供打包使用，旧 PDF、输入与审查回执保留。

否决反馈使用 canonical JSON，保证缓存加载后字段顺序改变不会造成论文修订步骤过期。可用 `.venv/bin/python scripts/validate_paper_repair.py --workspace workspaces/paper-repair-NEW --report reports/paper-repair-NEW.json` 验证真实容器计算、TeX、新 PDF 与完整重放；模型和 Exa 在此命令中明确为合成夹具。

Codex 传输 schema 另做兼容投影：移除不支持的 `uniqueItems`、将 `oneOf` 表达为 `anyOf`、将可选字段表达为必填且可为 null。收到结果后仅移除为传输添加的可选 null，再按原始完整本地契约校验，重复项等仍被拒绝。分别保存原始 JSON、规范化 JSON 和各自摘要，Claude 保留原契约。此变更修复本轮真实调用观测到的 HTTP 400 `invalid_json_schema`；设计参照 [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)。

## 检索、反方与澄清

多轮检索累计成功的 H-ID 映射，同时保留 EMPTY、原始查询与来源。每条反方候选必须有 READ / EXCLUDE / NEEDS_MORE_CONTENT 的 disposition 和具体理由；独立 critic 能看到候选摘录、排除理由与未读事项。这也包括 initial/support 检索中找到并标为 limitations 的候选，不能因检索来源不同而漏掉其摘录。未读的必要反证仍阻断接受。

格式不合格但包含 REVISE、contradicted、FAIL 或阻断发现的审查回复进入 `NEEDS_CLARIFICATION`。保存原文、摘要及目标身份；下一次有界澄清必须用 `clarification_responses` 逐一回应 `signal_digest` 并给出实质理由。保留原始调用及澄清调用各自的真实 packet digest。格式不合格的信号不算正式否决，也不能按普通供应商故障丢弃。

SharedHTTPGate 租约记录 request、owner、lease ID 和阶段：ACQUIRED_UNSENT、RESERVING_UNSENT、BOUND_UNSENT、SENT_OR_UNKNOWN。没有 TTL 自动过期。网络超时不能证明未发送，保留 UNKNOWN 和租约，不自动重试。`exa-status` 同时显示阶段预算与租约；操作员核对 owner 已停止及可能的远端费用后，可使用：

```bash
./scripts/cumcm recover-exa-lease WORKSPACE LEASE_ID \
  --external-process-stopped --reason '具体的进程、远端状态和费用核对记录'
```

本命令是恢复工具，不能替代核对。本轮只在合成夹具中测试它，没有替操作员恢复真实未知请求。

## 预算、原文缓存与分片

修复轮检索进入 `repair_reserve`；发布前引用原文核对进入 `final_verification`。`exa-status` 报告实际 HTTP 消耗，包括未使用的零值。缓存命中可使最终核对不消耗 HTTP；零消耗不能写成已调用外部服务。

官方规则查询有单独的受授权入口，年份由操作员显式提供；仍执行原有域名、截止时间和授权检查：

```bash
./scripts/cumcm exa-rules WORKSPACE --year 2026 --query '2026 CUMCM official competition rules'
```

实现文档只在冻结 implementation 配置有域名范围时提供给检索角色。Deep 仍要求冻结 opt-in、独立冲突报告与至少两条已完成的不同 auto 查询；生成综述仅用于导航，不推翻否定结论。未授权功能不为了覆盖测试而启用。

响应缓存继续绑定 cutoff、策略、授权和请求身份。另设不可变原文对象缓存，按 URL、版本和内容摘要去重；它只节省存储，不转移研究权限或科学结论。source selection 可以请求原文 `window: {offset, section}`，批判者看到实际原始偏移；不存在的章节或越界偏移会被拒绝。

`cumcm_harness.task_dag.execute` 是供 Docker 内求解器使用的有界实现：最多 64 个任务、每任务最多 128 个分片；按 DAG 依赖顺序运行，每个完成分片存储结果与文件摘要。重启时校验并复用已完成分片；RUNNING 分片仍需核对。控制器的 IO contract 告知长作业使用此接口。独立 SIGKILL 测试证明完成分片后的恢复不重复计算；这不代表任意模型生成的求解器已经采用该接口，资源声明也不能替代实际回执。
