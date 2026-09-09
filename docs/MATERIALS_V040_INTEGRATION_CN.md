# 0.4.0-rc1 资料合同层：当前仓库接入

本轮输入为 `CUMCM_Harness_v0.4.0-rc1_源码升级与验证包.zip`，SHA-256
`50505e5a6b98a56dd1be95f617aad1365c4b1098cf4879f433b150b192116ad8`。
包绑定 `f1ff48beebf7084ada6f16fc135801f484605a52`。在精确匹配的干净检出中验证 111 项分发摘要，安装器 dry-run 校验 49 个 payload 路径和旧 Git blob 后应用。没有修改安装器的基线常量或移除检查。原包报告位于 `docs/materials-upgrade/TEST_REPORT_CN.md`；[本机报告](../reports/MATERIALS_V040_LOCAL_CN.md)单独记录新增修复、测试与服务调用。

原主工作目录的源码在任务开始时仍缺失，因此本机实施目录为 `.runtime/materials-v040-worktree`，有自己的 `.venv`。没有覆盖原目录修改，也没有改写旧实验或审批回执。

## 输入、输出与接入点

| 模块 | 接受与处理 | 输出与接入点 |
|---|---|---|
| `materials_data` | 只读开发集，CSV 行数和字节数有界；其他格式明确只读了元数据 | 文件摘要、读取覆盖和质量标记，供数据方案及独立审查使用；不读取确认集，不自动清洗 |
| `materials_workflow.prepare` | 冻结题面、数据审计、已安装方法卡和资料参考卡 | `problem_brief → data_plan → model_portfolio → preparation.json`；在原模型设计前经独立审查与冻结 |
| `materials_contracts` | 校验原文字符偏移、实际问号、依赖、数据用途、训练内转换和可用基准 | 结构门禁及逐问论文位置映射；语义与真实执行仍由原审查和评测器验证 |
| `role_skills` | 加载角色指定的项目技能正文，数据放入单独的 DATA 区域 | 14 角色/15 技能的 SHA 进入运行指纹、调用身份和用途回执；缺失、修改、超长、符号链接均拒绝 |
| `materials_workflow.prepare_paper` | 已有正文、测量主张、逐问执行证据与全局符号 | 先提炼摘要，再生成并审查 `paper_map`；接回原论文版本、实际编译与视觉返工环 |
| `materials_figures/paper` | 真实确认结果、问间依赖和已核验符号单位 | 原 OurWork 引擎绘图、中文统计图和符号表；AI 详情从调用回执生成 |
| `submission_manifest` | 已验收论文 PDF 与支撑 ZIP 的实际字节 | 两文件 MD5/SHA-256 封存与复查；没有上传、代签或提交客户端操作 |

资料目录中的 191 张卡保持 `REFERENCE_ONLY_NOT_EXECUTABLE`。十族算法、MOSAIC 原代码与适用性、冻结评测器、开发/确认种子、否定结果与独立审查继续沿用原约束。

## 运行与镜像

新配置 `configs/materials-practice.json` 显式启用资料准备和在线文献；需要同时传入冻结 R2 sidecar。默认配置仍关闭 `materials_workflow`，旧工作区不能通过补字段来迁移。

```bash
docker build -t cumcm-egoharness:0.4.0-rc1 .
docker build -f Dockerfile.test -t cumcm-egoharness:0.4.0-rc1-test .
docker build -f Dockerfile.tex -t cumcm-egoharness-tex:0.3.1 .
docker build -f Dockerfile.paperkit-test -t cumcm-paperkit-validation:1.0.0 .

./scripts/cumcm doctor --live --config configs/materials-practice.json --exa-policy configs/exa-policy-r2.json
./scripts/cumcm init workspaces/materials-NEW --problem /absolute/problem.md --data /absolute/data \
  --config configs/materials-practice.json --exa-policy configs/exa-policy-r2.json
./scripts/cumcm run workspaces/materials-NEW
```

生产镜像包含新角色技能和参考目录，数值执行仍通过无网络、只读、非 root 的原 Executor；TeX 仍为单独镜像。测试镜像额外安装 Inkscape 与系统 CJK 字体，完整测试快照包含新技能和文档资源。字体从操作系统/镜像包管理器安装，不在仓库或支撑包分发字体文件。依赖安装与源码安装分层缓存，源码修订不必重复下载全部数值依赖。

本机中文绘图支持已安装的 Noto、PingFang、Heiti 等字体，并检查所需字形；无合适字体仍阻断。指标、单位和非有限值先于字体检查，保留真正的数据错误。AI 详情中的蛇形字段名在安全转义后增加断行机会，保留全部字段，不放宽 Overfull 检查。

## R2 查询修复与失败边界

真实初查曾生成尚不存在的 H-ID，验证在 HTTP 前拒绝了请求。现在提示明确列出 `allowed_hypothesis_ids`：空列表时每个查询必须使用空映射；已有假设时仍需覆盖全部当前 H-ID。

模型查询的结构/映射错误只在发送 HTTP 前按 `repair_attempts` 有界修复。每次保留原方案、摘要和拒绝原因，仍占原模型预算。供应商异常、HTTP 失败、未知在途请求和科学否决不进入这个修复分支。没有删改旧失败工作区，也没有把虚构编号改写成合法编号后继续搜索。

## 验收

```bash
.venv/bin/python scripts/validate_algorithm_upgrade.py --out reports/v040-full-NEW --seeds 2 --seed-start 201
.venv/bin/python scripts/validate_materials_pipeline.py --out workspaces/materials-legacy-NEW
.venv/bin/python scripts/validate_materials_pipeline.py --out workspaces/materials-legacy-NEW --replay
.venv/bin/python scripts/validate_materials_pipeline.py --out workspaces/materials-r2-NEW --r2
.venv/bin/python scripts/validate_materials_pipeline.py --out workspaces/materials-r2-NEW --r2 --replay
.venv/bin/python -m cumcm_harness.exa_r2_demo workspaces/r2-regression-NEW
.venv/bin/python scripts/validate_paperkit.py --out reports/v040-paperkit-NEW
.venv/bin/python scripts/validate_paper_repair.py --workspace workspaces/paper-repair-NEW --report reports/paper-repair-NEW.json
.venv/bin/python scripts/validate_audit_isolation.py --out reports/v040-isolation-NEW
```

资料验证器默认真实 Docker 数值与隔离 TeX，模型和 HTTP 为固定夹具；`--r2` 使用实际冻结策略、R2 客户端和账本。重放拒绝新增任一模型调用、HTTP、数值执行或编译，并比较预约数、全部作业状态和 PDF/ZIP/封存清单字节。

`scripts/validate_materials_live.py` 另用现有 Codex、Claude、Exa 在固定公开合成整数规划题上验证，最多 100 次模型预约和 32 次 HTTP 尝试，无真实参赛题或私有观测。可显式指定已有私有 Exa 文件与共享租约路径；文件值只经安全加载器进入 HTTP 边界。失败保留 typed error、原始工作区和回执，不转成夹具：

```bash
.venv/bin/python scripts/validate_materials_live.py \
  --workspace workspaces/materials-live-NEW --report reports/materials-live-NEW.json
```

公开题烟测不等于完整历史题盲评或正式队伍审核。版本保持 `0.4.0-rc1`；没有签署 contest 计划/研究/发布，没有提交论文。提交时刻沿用用户提供的 2026 通知；[全国官网](https://www.mcm.edu.cn/)和[学校发布的 2026 通知](https://jcfy.situ.edu.cn/info/1006/3933.htm)可供对照，正式操作仍应以当前赛区和客户端要求为准。
