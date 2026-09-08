# 0.3.0 算法库本机集成验收

日期：2026-09-08。结论：当前完整仓库的工程测试和有界数值诊断通过。机器可读结果见 [ALGORITHM_UPGRADE_LOCAL.json](ALGORITHM_UPGRADE_LOCAL.json)，可检查的本次数据见 [algorithm-upgrade-local-evidence](algorithm-upgrade-local-evidence/)。

## 集成内容

以当前 `b54d883` 为基础应用 `math_harness_algorithm_library_v0.3.0.zip` 的 31 个载荷文件。ZIP SHA256 为 `f1169d815e2cb57fe07a2ab7fcdd231e73ca00fe095418d969aef6f894f4d808`。上游包基于较早的 `69dc924`；本次保留当前 Exa 凭证管理、审查接管及已有修复。

十个方法族增加可调用的 CPU 实现和条件检查，旧入口保留。原版 MOSAIC 的 408 个受保护文件哈希验证通过；路由增强继续携带原有表示、确定性、约束和预算要求。算法路由及部分结构筛选不构成执行许可。

本地另外修复三处集成问题：保留原始 MOSAIC 方法卡约束；禁止把候选或基线冒充消融组；算法诊断 API 在创建输出前拒绝不足或非法种子矩阵。上游测试、设计资料和全部数值结果保持原样，三个载荷差异的前后哈希记录在 JSON 中。

文献返工保留完整失败 dossier 和全部审查意见，提示不再重复全文和历轮方案；引文只允许已检索来源 ID 和精确原文。字符与字节上限在外部 CLI 启动前检查，过大请求和直接提供方失败停止当前返工，避免重复消耗调用。引文真实性门禁、否定意见、冻结工作区及人工签核不变。

## 本次实际验证

| 检查 | 结果 | 范围 |
|---|---|---|
| 更新器文件操作测试 | 10 通过 | 主机纯文件操作 |
| 主机基础设施测试 | 204 通过 | 不执行新增算法数值测试；是全量测试的子集 |
| Docker 完整仓库测试 | 292 通过，0 失败、0 跳过 | Python 3.11，包含 81 个上游算法测试和新增集成回归 |
| 12 种子数值矩阵 | 564 条/轮，共两轮 | 种子 201–212；每轮 19 项诊断全部通过 |
| 可复现性 | 通过 | 两轮所有数值记录和诊断剔除耗时后逐项一致 |
| CI 命令本地验证 | 通过 | 首个集成提交 291 测试，加两轮 98 条结果/9 项诊断；默认镜像修复后的最终版本另跑完整 12 种子矩阵 |
| 生产镜像源码核对 | 通过 | 33 个 Python 文件与当前仓库逐一哈希相同，版本 0.3.0 |
| 原版 vendor 校验 | 408 文件通过 | 未修改 MOSAIC/OurWork 供应文件 |
| 论文流程与回放 | 通过，夹具范围 | 22 个作业 DONE；重跑 PDF/ZIP 哈希不变 |

Docker 验证使用现有 Executor：无网络、只读源码及数据、删除 capabilities、禁止提权、单 CPU、2 GB 内存和 900 秒单作业限时；不挂载凭证或 Docker socket。数值矩阵直接调用生产镜像内安装的模块，全套测试使用只读源码快照。

首次 `validation-01` 为 286 通过、5 失败：测试快照漏带 examples；伪 CLI 脚本位于禁止执行的 `/tmp`。修复验证脚本为完整测试快照，并把测试临时目录放到既有输出挂载点，未放松沙箱保护。失败日志保留本机，随后 `validation-02` 完整通过，没有覆盖旧结果。

首次提交 `6d8916a` 的 GitHub CI 通过后，启动配置检查发现默认镜像仍指向 0.1.0。追加修复统一新工作区、practice/contest 配置和 Executor 的默认镜像为 0.3.0，已有冻结工作区不变；增加实际创建工作区的配置回归。最终重建镜像、全量测试和两轮数值结果来自 `validation-03-final`，论文流程也在新的 `algorithm-upgrade-v030-paper-final-20260908` 工作区重跑。新增测试首次误从 controller 导入 create_workspace，修正为 intake 后基础设施全套 204 通过，首次失败日志保留。

## 负结果与证据范围

局部残差候选不保证改善。例如本次数值矩阵的非线性回归平均 RMSE：经典组合为 2.025742，门控残差为 2.060875，非门控残差为 2.086227；因此残差默认仍关闭。完整记录和上游早期失败试验均保留，没有挑选单次胜出作为晋级证据。

21 个外部模型候选仍为 `EXTERNAL_NOT_RUN`；未下载权重、未运行外部模型、未作全局性能晋级。算法晋级工具只消费可信控制器记录，不能替代独立审查或人工审批。

论文验收使用显式 FixtureProvider、Exa 重放和故障注入，数值与 XeLaTeX 编译实际执行，状态为 `DEMO_COMPLETE_NOT_LIVE_VALIDATED`。PDF 共 159 页，其中正文 4 页，其余包括参考文献和源代码附录；编译 overfull boxes 为 0，抽查第 1–5 页的正文、图表和参考文献未见排版问题，并非逐页附录视觉验收。支持 ZIP 共 177 个文件，CRC 检查通过。本次没有完成真实 LLM/Exa 的整题联跑，没有提交论文，也没有继续执行旧真实赛题工作区。

## 重现及后续运行

```bash
docker build -t cumcm-egoharness:0.3.0 .
docker build -f Dockerfile.test -t cumcm-egoharness:0.3.0-test .
./.venv/bin/python scripts/validate_algorithm_upgrade.py \
  --out workspaces/algorithm-validation-new --seeds 12 --seed-start 201
./scripts/cumcm verify-vendor
```

输出必须使用新的空目录。GitHub Actions 已配置同一 Docker 验证器的 2 种子矩阵，并保留测试及数值证据 artifact；实际远端运行状态以对应提交的 Actions 结果为准。升级改变代码指纹，真实任务使用新工作区，经 `doctor --live` 后运行，旧冻结工作区保留。
