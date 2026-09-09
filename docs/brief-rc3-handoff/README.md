# CUMCM Harness v0.5.0-rc3：来源登记与分批 brief 修复

本包基于 `mythrise/math_harness@2fa229f5e7cee48af3914703567f6e4f7ee1eff3`，修复真实运行暴露的原题阅读、约束类型引用、定义闭合、返修容量与超时处理问题。**这是17个路径的源码升级包，不是完整仓库克隆**：13个文件直接新增/替换，4个现有文件按已核对的Git blob进行单点转换。安装到上述完整检出后构成rc3；`build_full_source.py` 可从真实Git检出生成完整运行源码ZIP。

内部验证：105项源码/合同/组件流程测试通过，27项升级工具测试通过，原408项vendor摘要一致。模型与审查回复使用显式固定测试数据；一次本地超时进程、PDF生成和页面渲染是真实执行。**没有完成本次rc3的真实Codex/Claude+Exa+Docker整题联跑，也没有在本环境重跑最新版全仓CI。原始私人数据库和四份完整审查意见未取得，回归输入由用户贴出的失败模式重建。** 详见 `TEST_REPORT_CN.md`。

## 1. 为什么不是只把120改成更大

- PDF原件、逐页图像和原文本层在初始化时一起冻结。原题图像先读、公式和表格先核对；文本层不再被当作完整数学结构。
- 原页转录必须通过两个独立图像审查席。当前图像适配器只支持Codex，所以不宣称Claude看过图。
- 模型只返回当前批次的事实和source_unit_ids，控制器统一生成constraint/given/deliverable三类引用。
- 一次最多24条事实，通常最多4个原文语义段；允许引用相邻完整语义段补足定义。整合层上限512；容量不足时显式分批，不截断尾项。
- 原文中的一个公式/表格段保持整体，不按固定字符数截断分子/分母。新条目必须自包含，不能依赖不存在的G37—G39。
- 已明确的符号定义登记后不得无依据重开为“未知”。来源真正冲突时保留冲突并要求两个原始见证，不由程序猜测谁正确。
- 科学否决要求修正被否决内容；服务超时走既有受控接管。不得以供应商切换消除有效FAIL。
- 局部块失败只返修当前块。全局补丁有base_digest和before_digest，保留其他条目及来源覆盖。

这些检查不能形式化证明自然语言或公式语义；独立原文审查仍不可省略。

## 2. 应用（不自动提交或推送）

将本ZIP解压在仓库之外。使用你已有的虚拟环境：

```bash
/path/to/math_harness/.venv/bin/python install_upgrade.py /path/to/math_harness
/path/to/math_harness/.venv/bin/python install_upgrade.py /path/to/math_harness --apply --test
```

安装前检查origin、HEAD、干净工作区、旧文件Git blob、新文件SHA-256和代码语法。冲突就停止，不强制覆盖，不自动stash。修改前备份在仓库相邻目录。测试失败不提交/推送，保留备份和测试输出。

现有 `controller.py` 不由本包拼装替换：在正确blob上添加配置、提前来源检查、向假设和后续审查传递已核对原文、保持schema导出可发现。原来的基准绑定、17个角色、三模式、Exa权限、独立评测、修订渲染、国赛人工签核和TeX隔离逻辑保留。

## 3. 重新构建、新建工作区

```bash
cd /path/to/math_harness
.venv/bin/python -m pip install --no-build-isolation -e '.[dev,excel]'
docker build -t cumcm-egoharness:0.5.0-rc3 .

.venv/bin/python -m cumcm_harness init workspaces/heliostat-rc3-NEW \
  --input-mode idea \
  --problem /absolute/path/官方原题.pdf \
  --data /absolute/path/官方附件目录 \
  --prior-idea /absolute/path/初版建模.md \
  --config configs/input-idea-brief-rc3.json \
  --exa-policy configs/exa-policy-r2.json

.venv/bin/python -m cumcm_harness run workspaces/heliostat-rc3-NEW
```

使用完整原始PDF，而不是已经丢失分母、表格或机构示意信息的二次提取稿。PDF确实无法辨读时需要核验过的转录，不得从网络或模型记忆“恢复”赛题。正文模板和TeX镜像策略不变；仍需原来的TeX运行环境。

`scratch` 使用 `configs/input-scratch-brief-rc3.json`，去掉 `--prior-idea`，提供原题与需要的官方数据。`revise` 继续使用原有修订profile，不走新的原题建模通道。

默认 `brief_pipeline=legacy` 用于旧profile兼容；本包两个新profile显式设置 `source-ledger-v1`。**只安装文件而继续用旧profile，不会启用新来源通道。** 不要改旧工作区配置/指纹，不要删除旧数据库重新伪装成同一次成功。

## 4. 实际运行顺序

```
原件/原页冻结 → 原页阅读与视觉核对 → 小问概览
→ 分批事实提取与逐块审查 → 控制器分类型组装
→ 定义/歧义一致性 → 逐问及全局审查 → 只修缺陷的有界补丁
→ PI与Exa初查 → 数据方案、独立基准 → 你的外部初版
→ 正式建模 → Exa假设反方 → 独立评测器与代码
→ 真正实验与确认 → 论文、摘要、排版审查及人工发布
```

同一来源brief在之后的MaterialsWorkflow中复用缓存，不重复调用模型。原文核对被提前到PI和付费Exa初查之前，但并未删掉原有Exa或后续任何科学门禁。

## 5. 新profile参数是建议值，不是经实题证明的最优值

模型调用上限240；结构/科学返修参数2；Codex作者超时600秒、Codex审查超时240秒；每供应商每席最多一次尝试，明确故障可接管；熔断冷却900秒；双席不变。Exa80次/每次6条/45秒，权限规则不变。

**保留最新上游的 `claude_timeout: null`：Claude不受上述600/240秒本地时限约束，继续等待正常返回或明确失败。Claude仍在运行时不启动替代调用；无时限也不保证最终会返回。** 这遵循仓库最新用户配置要求，不推断先前超时原因，也不改你本机转发器。

调大超时不能修复认证或上游故障；900秒冷却只是减少反复等待同一不可用供应商。无法确认外部效果时保留UNKNOWN，需要显式核对。模型成本未知就保留未知，不能从超时推断原因或计费状态。

## 6. 新诊断与中间产物

- `problem_source/`：冻结原件、原页PNG和来源清单；不覆盖`problem.md`。
- `brief/source-ledger.json`：全文/逐页来源单元、图像摘要和转录回执。
- `brief/accepted.json`：完整brief、审查回执、保留的排除理由及明确验收范围。
- 事件：`BRIEF_CHUNK_REPAIR`、`BRIEF_BATCH_SPLIT`、`BRIEF_GLOBAL_REPAIR`、`BRIEF_PATCH_APPLIED`。
- PDF转录锚点明确属于`reviewed_source_unit`坐标空间，不能冒充原PDF文本层偏移。验证必须带冻结来源索引。

检查旧失败brief（只读诊断；输入应是精确`problem.md`及brief对象JSON，而不是任意日志外壳）：

```bash
.venv/bin/python -m cumcm_harness.brief_tools \
  --problem /absolute/旧工作区/problem.md \
  --brief /absolute/导出的失败brief.json \
  --out /absolute/工作区之外/新的brief诊断.json
```

这个工具检查旧合同、引用和显式定义，不是自然语言蕴含证明，不会修改旧记录。新版的PDF转录brief还须按来源索引验证，不能用这个旧稿诊断入口跳过来源门禁。

## 7. 完整源码ZIP

在真实仓库HEAD仍是本包基线时（可以已经应用补丁，但还未创建新的Git提交）：

```bash
/path/to/math_harness/.venv/bin/python build_full_source.py \
  /path/to/math_harness --out /outside/repository/math_harness_rc3_full.zip
```

构建器读取Git HEAD的受控运行文件并叠加本包已核验修改；不把未提交的其他本地修改混入，不读取凭证/工作区，不发布字体文件。依赖缺失或vendor摘要不同则拒绝构建。**打包不等于跑通实题；其清单明确标记测试没有由打包器执行。**

完整生产验收见 `CODEX_ACCEPTANCE.md`，没有取得的结果保持NOT_RUN。
