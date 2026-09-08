# 0.2.0 本机升级验收

日期：2026-09-08。基线：`3b233edaa5d2c9ec95bf67ae2d495e0d662c3292`。

按 `math_harness_exa_review_update 2` 集成 27 个经原始 Git blob 与新 SHA-256 核对的文件，并补齐本机发现的配置、恢复与缓存问题。**工程升级验证通过；真实 Exa + 双模型 + 完整历史赛题联合验收仍为 BLOCKED / NOT_RUN。** 当前进程未配置 `EXA_API_KEY`。

机器可读证据及源码摘要见 [EXA_UPGRADE_LOCAL.json](EXA_UPGRADE_LOCAL.json)。[EXA_REVIEW_ACCEPTANCE_CN.md](EXA_REVIEW_ACCEPTANCE_CN.md) 是更新包制作环境的历史回执，其中的远程 403、170 项测试和旧产物摘要不代表本机本次结果。推送状态以远程 Git 引用为准。

## 实现与本机补强

- Exa 抽象查询、支持与反例检索、逐假设卡、精确引文与来源摘要校验、双席文献审查、强制执行诊断、论文引用与支撑包接入。
- Claude/Codex 按职责设独立席位；终止性接口故障有限重试、熔断和接管；否定回执与已完成实验复用。有效反对意见、摘要异常与未知状态不能被换模型绕过。
- 修复更新包离线兼容问题：默认及旧 profile 保持本地证据模式，在线研究必须显式启用；`doctor --config` 按所选网络策略和镜像检查依赖。
- 审查执行前保存待完成意图。增加运行轮次或更换父任务名称不会重启未知/完整性失败的调用；调用已完成但审查缓存未写完时，只重放原回执。直接作者调用的失败保留显式恢复路径。
- Exa HTTP 200 但内容不可用时不写成功缓存，服务恢复后仍可重试；补充畸形响应、私有地址与 URL 校验。三类新合同已导出至 `schemas/`。

## 本机验证

| 项目 | 结果与范围 |
|---|---|
| 完整 harness 测试 | **186 passed，0 failed/error/skipped**；约 4.84 秒；5 条第三方 PyMuPDF/SWIG 弃用警告 |
| vendor 完整性 | **408 文件全部通过**，原版 MOSAIC/OurWork 未修改 |
| 最终代码论文闭环 | 12 个开发单元 + 10 个确认单元全部完成；每单元 FE 192 |
| 故障接管 | 18 条显式接管事件；45 条调用预算记录，模型响应与 Claude 故障均为注入夹具 |
| 假设诊断 | 实际执行延迟折损、非负截断、重复确定性、时间单位变换检查 |
| PDF 与支撑包 | 实际 XeLaTeX 编译 159 页，其中正文计数 4 页；177 个支撑文件 |
| 恢复 | 调用 45→45、任务 22→22；PDF 与 ZIP 的 SHA-256 均相同 |
| 独立复现 | 仓库外解压最终支撑包，baseline/c0、seed 701 的答案及独立评测 JSON 均逐字节一致 |
| 审计 | 最终工作区 SQLite 事件链与内容寻址对象检查 PASS |
| 视觉抽查 | 第 1–6、159 页检查通过；未逐页审查完整源码附录 |
| Docker | 新镜像构建完成；正式 Executor 实际运行 baseline 与 c0 各一次求解和独立评测，均 valid=true |

最终工作区：`workspaces/exa-upgrade-final-20260908`。最初的本机验收工作区与日志另行保留；最终一次运行绑定所有源码修复后的摘要。

PDF SHA-256：`bee40f6ae9f90b67530a1673020820c80294b2b4a50a7e286d19a2c4b91215f6`。

支撑包 SHA-256：`8610b8e162cb5e651363040797e3646626371982f526369d0904bc6e0f0650cf`。

## 本机部署与剩余边界

本机原 Colima 虚拟机处于停止状态，启动现有实例后重新构建镜像。`cumcm-egoharness:0.2.0` 与兼容标签 `cumcm-egoharness:0.1.0` 现指向新镜像；旧镜像另保留为 `cumcm-egoharness:pre-exa-20260908`。未改写旧工作区运行指纹，新代码需要新工作区。

镜像 ID：`sha256:41e1b0b29b5c72fbf89fd2c1de7e4b0783a06fc0e5abbd7e3daf1a7cd80ac77f`。

虚拟环境未安装 pip 模块，使用既有 uv 刷新 editable 安装至 0.2.0：

```sh
uv pip install --python .venv/bin/python --no-deps -e .
.venv/bin/python -m pytest -q
./scripts/cumcm verify-vendor
./scripts/cumcm doctor --live --config configs/exa-resilient.json
.venv/bin/python -m cumcm_harness.resilience_demo workspaces/exa-upgrade-final-20260908
```

Codex 0.153.4、Claude Code 2.1.263 的安全参数探测通过；探测不证明实际模型认证或科学审查通过。当前 `EXA_API_KEY` 缺失，在线 profile 的 `ready_for_live=false`。本次未进行真实 Exa HTTP 认证、真实双模型审查或完整历史国赛题质量验收。故障注入论文闭环与 Docker 中的合成算法执行分别记录，不冒充这些未完成的实测。

原始 CLI 日志、工作区数据库、题目数据及凭证不纳入远程仓库。未执行正式比赛签核或提交。
