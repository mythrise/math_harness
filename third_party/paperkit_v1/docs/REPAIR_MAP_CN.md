# 修复映射：旧模板问题 → 本包实现

上游审查基线：ModelingPaperKit commit `47e9bc8046d037ca765eb10d6869012a178983f7`。

| 原问题 | 修复方式 | 可执行验证 |
|---|---|---|
| references 后置旧 AI 声明 | main 中在 references 前仅 input 自动生成的声明 | PDF 可见标题次序和分支检查 |
| 删除“未使用”后缺少“已使用”分支 | JSON used/unused/unconfirmed 三态；未确认阻塞 | 两个分支实际编译；矛盾日志拒绝 |
| AI 详情和主模板不同步 | 同一 ai_usage.json 驱动主声明与详情 PDF | 必填字段、版本、重复 ID、纯润色例外 |
| 文件名空格争议被绝对化 | 默认 HTML 名；允许带说明覆盖，不认定空格必然违纪 | 别名未附理由拒绝，附理由允许 |
| 2025 AI 规则残留 | 专用 CUMCM 2026 文档替换旧 snapshot，不复制双赛事旧 Skill | 新 RULES_2026 文档与受控生成入口 |
| 附录只提示“主要代码” | 同一份源码字节用于 VerbatimInput、清单、ZIP和摘要绑定 | archive bytes 与源码逐文件一致 |
| 无程序/无支撑材料混淆 | 两个独立条件句 | unused_ai_no_program 编译测试 |
| 未核验的官方专用页 | 删除旧重绘版；外部官方页合并 | 每页数检查、正文像素逐页相同 |
| 页数/大小未测 | AUX 边界 + PDF实际页数；论文/ZIP大小限制 | 摘要超页、正文超页、大小边界失败测试 |
| 元数据与归档匿名不足 | 黑名单空白规整、元数据检查、路径与凭证模式、精确白名单ZIP | 真实 PDF 注入 author/越界内容后检出 |
| 原 fonts 文件硬编码 macOS 字体 | ctex Fandol；不重定义已有 songti/heiti | Linux 实际编译，缺字阻塞 |
| 标题用 mbox 无法换行 | 居中 parbox 自动换行 | 超长标题实际编译 |
| 摘要 enlargthispage 侵占边界 | 删除扩大页内容和负向位移，留足边距 | 实际文本/图像/矢量 bbox 检查 |
| 图片不存在时生成占位图 | 缺图直接 PackageError | 构建失败，不编造结果图 |
| stale PDF 被当新结果 | 全新输出目录、输入构建前后哈希比对 | 旧目录拒绝、文件改动拒绝 |
| 外部适配器更新绕过宿主指纹 | 安装 hook 固定整个实现/样式 digest，编译前复检 | 指纹漂移拒绝 |
| PASS 冒充可提交 | machine pass 仍 require human review；示例禁止发布 | 无复核/错误摘要/示例 release 均阻塞 |

从上游保留的是 CUMCM 版式取向、章节组织以及常用宏接口；不是将整个 Agent/skills 仓库原样复制。原 `check_submission.py --target cumcm` 等缺乏 PDF 实测的入口不复用；包内同名兼容脚本明确要求 `--out`，避免看见名称相同便误以为仍在执行旧检查。

为降低部署依赖，原 AI Typst 详情模板改成纯 LaTeX 自动生成。没有保留错误规则的旧支线，未尝试“修复”无关的美赛、五一或北京模板。
