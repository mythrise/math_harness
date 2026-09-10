# rc3 声明字段修复

本次收到的 `CUMCM_Harness_v0.5.0-rc3_来源分批与brief修复升级包 (1).zip` 与上一包字节相同，SHA-256 为 `7fb2365fd623990d98fa64da5ded4e8c17e552c3070d7246f35a95df0fbcbf5f`。56 项包内校验通过。原包已经在 `5d85dbd` 中接入，本次在该基线上处理真实历史题第 11 批暴露的声明格式和诊断问题，没有再次安装旧 payload。

## 输入、检查与输出

`declarations` 接收符号/名称 `subject` 和完整原文定义 `quote`。例如来源写作 `效率 $\theta_1 = 1 - L$`，模型可能把符号写成 `$\theta_1$`。旧实现要求整个 subject 逐字出现在来源中，因此来源公式中的等号使独立闭合的 `$` 无法匹配，尽管符号和引文没有改变。

新检查只在比较 subject 时去掉一对完整的外层 `$…$`、`$$…$$`、`\(…\)`、`\[…\]` 及边界空白。内部的命令、上下标、大小写、空白继续逐字比较；不猜测 Unicode/LaTeX 别名，不推断数学等价。空内容、嵌套或不完整的边界被拒绝。

比较结果必须同时出现在所引来源与该声明自己的 quote 中。这样既允许排版差异，也不能借用同一段中另一个符号的定义。quote 本身仍须逐字出现在来源和本条 statement 中；不归一化引文，不改变原件、页图、来源偏移、事实内容或已保存的 subject。输出仍是原有事实对象，控制器在来源批次、整题检查与局部补丁处调用同一规则。

同一比较规则也用于重复声明、定义承认清单与歧义核验；不能通过把 `ST` 改写为 `$ST$`，把原题已经给定的定义重新列为缺失。

## 可定位的修复反馈

| 诊断 | 含义 |
|---|---|
| `DECLARATION_SUBJECT_NOT_IN_SOURCE` | 符号/名称不在引用的来源中 |
| `DECLARATION_SUBJECT_NOT_IN_QUOTE` | 符号/名称未绑定到自己的定义引文 |
| `DECLARATION_QUOTE_NOT_IN_SOURCE` | 引文不是原文连续片段 |
| `DECLARATION_QUOTE_NOT_IN_STATEMENT` | 本条事实未完整保留定义引文 |

每项反馈包含 `facts[i].declarations[j].subject/quote` 位置、相关来源 ID 和对应修改要求；同批多条错误会一起报告。完整原始产物和诊断仍保存在对象存储，字段预览不会替换原始证据。

纯合同修复耗尽返回 `SourceContractFailure`，不再冒充独立审查席的 `ScientificRejection`。如果此前确有有效科学否决，否决和后续格式失败均被保留；任何一种情况都不是供应商故障，不触发换供应商刷通过。Claude 仍无本地截止时间。

## 隔离验证与回放

三模式验证入口增加可选 `--image`，将指定镜像写入新工作区配置。回放默认读取冻结镜像；显式指定不同镜像时，须在发起新工作前拒绝。

```bash
.venv/bin/python scripts/validate_three_inputs.py \
  --out workspaces/NEW-idea --input-mode idea --r2 --source-brief \
  --image cumcm-egoharness:0.5.0-rc3-declarations-20260910
.venv/bin/python scripts/validate_three_inputs.py \
  --out workspaces/NEW-idea --input-mode idea --r2 --source-brief --replay
```

这是固定模型/检索回复的工程验证，数值和 TeX 仍实际通过 Docker 执行。旧第 11 批产物通过新规则的只读结构检查，不会改变旧 BLOCKED 状态，也不替代新的双席审查。完整验收另见 [本轮报告](../reports/BRIEF_DECLARATIONS_FIX_CN.md)。
