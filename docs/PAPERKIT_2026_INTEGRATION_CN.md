# PaperKit v1 模板修正与当前 Harness 接入

本次按 `CUMCM2026_PaperKit_Harness_v1.0.0.zip` 修正论文排版及实际 PDF 检查。输入包 SHA-256 为 `dbc6c34dae2e987d36814c8e7642d1b1dd61bd3c3839a6488b30bcd2d47b28de`。本机两个同名下载副本字节一致。

## 接入方式

包内安装器核对的是旧 `paper.py` Git blob `2e3043de9325704e484351cf400f8df7e8be3815`；本轮基线 `7e91cfa` 的文件 blob 为 `ab8f9ac9be0653735b601d5ba884aade5862d402`，已有隔离编译和论文返工机制。因此没有强行运行旧安装器或移除其哈希保护，而是在当前接口中移植模板和检查器。

`paper_profile.py` 内嵌原包的样式字节，纳入已有 `core_source` 运行指纹。`prepare_style` 仅生成该确定样式，拒绝不同字节和符号链接；`tex_sandbox.py` 只把完全匹配的样式加入只读构建输入。编译回执继续绑定主文件、样式、源码、图表、容器镜像及全部输出摘要。没有需要另行安装或可能漂移的外部 editable hook。

原包的源码、测试、两个示例及文档保存在 `third_party/paperkit_v1/`，按 `UPSTREAM_MANIFEST.json` 验证原字节。这些文件是独立的对照材料，不替代宿主 controller、Store、审查板、算法、Exa、人工签核或打包逻辑。来源说明见该目录的 `THIRD_PARTY_NOTICES.md`。

## 版式与检查

| 修正 | 当前实现与验证 |
|---|---|
| 长标题与摘要 | 使用可换行的 `PaperKitTitle`；摘要终点继续由编译 AUX 标签验证。未扩大摘要页内容区域 |
| 浮动图与后置章节 | AI 声明前设置 `FloatBarrier`，防止图表漂入声明或参考文献之间；附录标题不重复编号 |
| 字体与边界 | 使用 TeX Live 的 Fandol；左右 28mm、上下 27mm 并包含页脚；PDF 检查实际文字、图片、矢量边界 |
| 页码与页数 | 页脚中部从 1 连续编号；正文预算只采用控制器生成的附录标签，不从正文中的“附录”文字推断 |
| AI 声明 | 实际运行分支使用官方“已使用”句式并置于参考文献前；工程演示保留明确的夹具说明 |
| AI 详情 | 继续从真实调用回执和已有人工签核记录生成；增加详情 PDF 的版式检查，不补造采纳或人工修改记录 |
| 手工起稿 | starter 的 AI、程序、支撑材料三个状态分别确认；默认 `unconfirmed` 阻断编译。无程序和无支撑材料各有独立声明 |
| 缺失资产与编译告警 | 图片缺失、缺字、未解析引用、Overfull hbox/vbox 或缺失编译日志阻断构建；保留失败日志和版本 |
| 匿名与 PDF 内容 | 检查 author、XML 元数据、规整空白后的身份黑名单、凭证模式、附加文件及主动内容 |
| 源码附录与 ZIP | 保留同一源码清单、源文件字节及支撑包摘要绑定；验收逐文件比较，不以附录页数推断完整性 |
| 模板文本检查 | authored 页中的占位文本不能通过；附录中逐字列出的程序字符串不被误当作待填写模板。匿名和边界检查仍覆盖全部页面 |

`demo` 必须由控制器显式传入；在正文写“本工程演示”不能开启例外。AI 声明和参考文献按实际可见标题行检查，保留原 preflight 的失败结果。所有机器通过结果仍带 `release_ready=false`，不代替正式签核。

自动建模流程本身使用 AI，不能为这条流程生成“未使用 AI”的声明。未使用分支属于独立 PaperKit 示例和人工起稿模板；两者都有实际编译验证。默认 AI 详情文件名仍为 `AI工具使用详情.pdf`，不将带空格的名称直接判定为违规。

当前依据已复核：全国组委会的[2026 论文格式规范](https://www.mcm.edu.cn/html_cn/node/4cd596519c9eb9fbd866398f6df0caa3.html)与[2026 AI 工具使用规定](https://www.mcm.edu.cn/html_cn/node/fef94648f2836ab6cc81586f4c38512b.html)。28/27mm、字体和标题风格属于本模板的排版选择；三十页计数和 20,000,000 字节采用保守工程口径。本模板不是官方 LaTeX 类。

## 运行与验收

```bash
docker build -t cumcm-egoharness:0.3.0 .
docker build -f Dockerfile.test -t cumcm-egoharness:0.3.0-test .
docker build -f Dockerfile.tex -t cumcm-egoharness-tex:0.3.1 .
docker build -f Dockerfile.paperkit-test -t cumcm-paperkit-validation:1.0.0 .

.venv/bin/python scripts/validate_paperkit.py --out reports/paperkit-NEW
.venv/bin/python scripts/validate_paper_repair.py \
  --workspace workspaces/paperkit-repair-NEW --report reports/paperkit-repair-NEW.json
.venv/bin/python scripts/validate_algorithm_upgrade.py \
  --out reports/paperkit-full-NEW --seeds 2 --seed-start 201
```

第一个验证器在专用 Docker 中运行原包全部测试，编译两个示例；再由宿主的隔离编译器验证本机模板、长标题、缺图失败、起稿分支和编译重放。第二个执行真实 Docker 数值计算、源码附录、AI 详情、支撑 ZIP、PDF 否决后修订及完整重放；模型和 Exa 明确是测试夹具。第三个执行完整仓库测试和两次有界数值复现。命令不发起真实模型调用，也不签署审批。

本轮完整论文回归另外发现首次确认矩阵的共享输入记录有并发竞争：两个 worker 同时创建同一 `runner-inputs` step，第二个会碰到真实的暂态 RUNNING。现在先在矩阵入口完成该记录，再启动 worker；各 cell 仍逐次检查数据摘要，未知既有任务仍阻断。修复保留同样的 step key、协议、种子和评价器，独立延迟注入测试与完整论文重放共同验证。

源代码或模板改变后须重建环境并初始化新工作区；旧工作区和失败产物保留。正式论文仍须团队主导、完整人工阅读及逐项核验，并核对赛区要求；未制作或冒充官方承诺书、编号页，也没有自动提交。具体本机结果见 `reports/PAPERKIT_2026_LOCAL_CN.md`。
