# 安装与验证

## 应用源码升级

在仓库目录之外解压本交付。先保存、提交或另行整理用户已有修改；安装器不会自动stash或覆盖。必须使用现有Python3.11+虚拟环境。

```bash
/path/to/math_harness/.venv/bin/python install_upgrade.py /path/to/math_harness
/path/to/math_harness/.venv/bin/python install_upgrade.py /path/to/math_harness --apply --test
```

第一条为只读校验。安装器检查HEAD、origin、干净工作区、所有旧Git blob、新payload SHA和路径，再写入；旧文件备份在临时目录。测试失败保留修改与备份，无提交或推送。HEAD已变化时停止，先人工审查合并，不能删除校验或把旧指纹改成新值。

## 在真实checkout生成完整源码

应用且验收后，尚未自行提交新commit之前：

```bash
/path/to/math_harness/.venv/bin/python build_full_source.py /path/to/math_harness \
  --out /absolute/path/outside/repository/math_harness_v0.4.0-rc1_full.zip
```

这条命令只使用用户当前完整checkout的已追踪运行源码、模板、声明和精确升级payload，不联网。原始教程压缩包、历史运行产物、工作区、凭证、字体被排除并记录。它不证明程序正确。若先提交到新commit，应先审查并更新构建器基线，不能强行套用。

## 真实新工作区

保留已有Codex/Claude认证与Exa私有凭证加载器；不修改模型、effort、密钥。根据原仓库说明重建执行镜像以及Dockerfile.tex对应的隔离编译镜像，先完成doctor检查。

```bash
cd /path/to/math_harness
.venv/bin/python -m cumcm_harness.materials_cli skills
.venv/bin/python -m cumcm_harness.materials_cli schema
.venv/bin/python -m cumcm_harness doctor --live \
  --config configs/materials-practice.json --exa-policy configs/exa-policy-r2.json
.venv/bin/python -m cumcm_harness init workspaces/materials-new \
  --problem /absolute/path/problem.md --data /absolute/path/data \
  --config configs/materials-practice.json --exa-policy configs/exa-policy-r2.json
.venv/bin/python -m cumcm_harness run workspaces/materials-new
```

实际截止时间、确认数据、私有评测数据等按原CLI指定。没有独立确认集时不能宣称跨实例泛化。正式模式还需签名研究范围和逐项人工审核；这里的practice配置不是正式上传授权。

## 交付前必须补跑

```bash
# 当前完整仓库，而非本地重建目录：
.venv/bin/python -m pytest -q
.venv/bin/python -m cumcm_harness verify-vendor
# 已建好两类Docker镜像后，固定合成夹具的完整Controller测试：
.venv/bin/python scripts/validate_materials_pipeline.py --out workspaces/materials-validation-01
.venv/bin/python scripts/validate_materials_pipeline.py --out workspaces/materials-validation-01 --replay
# 保留原R2集成演示：
.venv/bin/python -m cumcm_harness.exa_r2_demo workspaces/materials-r2-regression-01
```

注意：新增验证脚本使用固定模型回复和Exa HTTP响应重放，正常模式使用真实Docker数值与隔离编译；它没有替代真实双模型/真实Exa联合验收。该脚本的本地组件选项只允许内置固定测试内容，没有任意题面/代码参数，不是生产无Docker回退。

## 已有草稿诊断

```bash
.venv/bin/python -m cumcm_harness.materials_cli diagnose-paper \
 --draft /path/draft.json --plan /path/plan.json --claims /path/claims.json
```

这是结构化内容诊断，不接受任意Word并自动改写、也不预测奖项。完成实际修改必须重新走编译和审查。

## 已知边界

对当前仓库全量回归、真实Docker/tex沙箱、新结构合同的真实模型遵循质量、真实Exa R2与所有新阶段联合运行、历史完整赛题盲评均需在有认证环境补验。不要引用上游464项测试或本轮100项组件测试作为这些项目已完成的证据。
