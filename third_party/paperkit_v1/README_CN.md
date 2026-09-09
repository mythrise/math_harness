# CUMCM 2026 PaperKit · Harness 接入修订包

版本 1.0.0 ｜规则复核日期 2026-09-09

基于 `bosprimigenious/ModelingPaperKit` 的 CUMCM 版式、章节组织和公开宏接口，提取并重构为专用子包。**这不是全国组委会官方模板，也不是原仓库全量镜像。** 已移除旧 AI 规则、未核验的承诺书重绘版、Typst 双赛事混合依赖及原有不完整检查入口。采用可复现的本地 LaTeX 构建流程，附带 `mythrise/math_harness` 的小范围适配器。

## 先选一种使用方式

| 你的情况 | 入口 | 不要做什么 |
|---|---|---|
| 接入现有 `mythrise/math_harness` | `docs/HARNESS_INTEGRATION_CN.md`；`install-harness` | 不要用独立版覆盖其 controller、证据绑定、HMAC 签核或 packaging |
| 独立生成论文，再让其他 Harness 调用 | `cumcm-paper init/build/check/release` | 不要把整个开发目录当作比赛支撑包 |
| 只查看最终排版 | `previews/` 中的 PDF | 示例不是当届赛题答案，不得直接提交 |

## 安装与工程自测

Python 3.11+，XeLaTeX，TeX Live / MacTeX / MiKTeX 中的 ctex、Fandol、fvextra、cleveref 等宏包。**不附带字体文件**，Fandol 来自用户自己的 TeX 发行版。软件自测在 Linux / Python 3.13.5 / XeTeX 上实际执行；其他操作系统未实机验证。

```bash
cd CUMCM2026_PaperKit_Harness
python -m pip install --no-build-isolation -e '.[dev]'
cumcm-paper doctor
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q

# 两个例子；每次使用一个全新的输出目录，输出不应放在输入项目之内。
cumcm-paper build --project examples/used_ai --out output/example-used-01
cumcm-paper build --project examples/unused_ai_no_program --out output/example-unused-01
cumcm-paper check --out output/example-used-01
```

Windows PowerShell 可先设置 `$env:PYTHONDONTWRITEBYTECODE='1'` 再运行测试；其余命令相同。

## 新建实际论文项目

```bash
cumcm-paper init my_paper
# 填写 my_paper/project.json、sections/*.tex 和 ai_usage.json。
# AI 状态默认 unconfirmed，必须由实际使用事实确定，不能默认写“未使用”。
cumcm-paper build --project my_paper --out output/candidate-001
```

输入契约见 `docs/INPUT_CONTRACT_CN.md`；机器可读 Schema 在 `src/cumcm2026/assets/`。LaTeX 片段只写内容与正常公式、图表；标题、页边距、目录、声明位置及附录由生成器管理。数据/程序不会被自动运行；程序必须经过现有 Harness 的执行核验或团队另行复现。

输出目录中的 `paper.pdf` 和可选的 `support.zip` 是**候选交付物**。`build_report.json` 记录版本指纹、输入/输出哈希、页数、源码清单及检查结果；`review.required.json` 的人工复核项默认全部为 false。发生错误会生成 `BLOCKED.json`，不能把中间 PDF 当成通过。

## 本包修复的关键问题

AI 声明由唯一入口生成，位于参考文献前，使用/未使用两条分支互斥。AI 详情由同一份 JSON 生成纯 LaTeX/PDF，覆盖名称与版本、目的环节、提示与过程、采纳修改核验；不自动编造使用记录，不以固定二十至三十页为目标。纯语言润色的详细核验字段适用规则例外。

全部已声明源码以同一套字节文件写入附录和支撑包，生成 SHA-256 绑定；项目内未分类的可执行代码会阻塞，未用到的程序需明确列入带理由的排除项。无程序和无支撑材料为独立分支。

编译后的 PDF 检查 A4、实际文字/图片/矢量边界、摘要一页、正文页数、页码、声明顺序、匿名黑名单及元数据。正文页数采用保守口径：摘要之后、附录之前的全部页面，含声明与参考文献，不超过三十页；文件采用保守的 20,000,000 字节上限。该工程口径不冒充组委会对模糊细节的新增解释。

模板保留熟悉的中文一级标题、表格和代码排版；长标题可换行，不再用扩大摘要页可排版区域来挤内容。缺失图片、缺字、未解析引用和 overfull box 都会阻塞构建。

## 关于 AI 详情文件名的纠正

官网 HTML 写 `AI工具使用详情.pdf`，官网附件 PDF 排印为 `AI 工具使用详情.pdf`。因此不能断言带空格一定违规。本包默认用 HTML 中的无空格名称；确有赛区/系统确认时，可配置带空格名称，并填写 `ai_filename_override_reason`。只输出所选择的一份，不生成两个互相混淆的副本。详见 `docs/RULES_2026_CN.md`。

## 最终人工复核与本地导出

仅在完整核验后，由实际操作员另存并填写 review 文件；程序不代填。独立版 review 是摘要绑定的声明，**不认证签核人身份，也不是法律电子签名**。正式使用现有 Harness 时，继续使用它原来的 plan/release 与 HMAC 流程，不使用本独立版 review 代替。

```bash
cumcm-paper release --out output/candidate-001 \
  --review /absolute/path/to/review.completed.json \
  --destination output/local-release-001
```

导出目录只放论文及可选支撑 ZIP，开发报告、规则文档和本地复核文件不混入比赛文件。不会自动上传比赛系统。示例始终禁止 release。

## 纸质版

本包不提供假装是官方的承诺书或编号页。取得并核验当届真实官方专用页后，用 `print` 命令在已冻结电子论文前合并，各为一页；工具对论文部分逐页像素比对，保证不重新排版。

```bash
cumcm-paper print --paper output/candidate-001/paper.pdf \
  --commitment /path/to/current-official-commitment.pdf \
  --numbering /path/to/current-official-numbering.pdf \
  --confirmed-official --out output/paper-print.pdf
```

`--confirmed-official` 表示操作员确认来源，不代表工具已鉴定官方真伪。纸质版含身份页，不得混入电子论文或支撑包。

## 不能由本包自动证明的事项

机器通过不等于最终合规认证：科学结论正确性、全部实际使用程序是否纳入、所有 AI 输出是否真的逐项人工核验、截图和二进制文件是否完全匿名、赛区追加要求及当届专用页，仍需人核验。TeX 黑名单与 `-no-shell-escape` 也不等价于安全沙箱；只编译可信队内内容，不可信稿件应在无网络、无凭证、受资源限制的容器中处理。

详细文件：`docs/REPAIR_MAP_CN.md`、`docs/SECURITY_AND_LIMITATIONS_CN.md`、`reports/ACCEPTANCE_CN.md`。
