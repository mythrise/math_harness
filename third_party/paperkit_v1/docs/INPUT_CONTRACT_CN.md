# 输入契约与 AI 日志字段

## project.json

`schema_version=1`。文件路径全部使用相对项目根目录的 POSIX 路径。禁止绝对路径、父目录跳转和符号链接。输出目录必须在项目外且是新目录。

| 字段 | 类型与作用 |
|---|---|
| `title`、`keywords` | 普通文本标题与关键词列表，由程序转义，不是 TeX 宏 |
| `abstract`、`references` | 两份 TeX 片段的相对路径 |
| `sections` | 按顺序提供 `{heading, path}`；不适用的章节删除，不保留占位 |
| `program_used` | 与 code_roots 一致的布尔值 |
| `code_roots` | 所有实际用于建模的 UTF-8 源码/文本运行资源根目录或文件，递归完整收入附录和 ZIP |
| `excluded_code_files` | 可选 `{相对路径: 未使用原因}`；用于项目内可执行文件的显式排除，不许用它掩盖实际用到的代码 |
| `support_files` | 逐项列出其他必要文件，如自采数据、结果表；不接收目录或嵌套压缩包 |
| `figures` | 论文需要的图片，路径应从 `figures/` 开始；同时需要进入支撑包时，也加入 support_files |
| `ai_status` | `unconfirmed`/`used`/`unused`，前者只能用于准备阶段、不能 build |
| `ai_usage` | AI 日志 JSON 路径，与 ai_status 同步 |
| `ai_details_filename` | 默认 `AI工具使用详情.pdf` |
| `ai_filename_override_reason` | 改用带空格名称时必填的本地确认说明 |
| `identity_denylist` | 当前队伍的真实姓名、学校、队号、账号等私有检查词；仅留本地配置，不放支撑包 |
| `example` | 真实工程示例为 true，永远禁止作为正式 release；真实项目由 init 建立为 false |

源码 roots 必须足够完整：只把一个短入口写进 roots 不能证明没有遗漏外部自定义模块。外部安装包的版本和依赖说明、自定义算法来源、Excel/SPSS 交互命令均需按实际补齐。工具不自动运行陌生源程序。

普通 references.tex 内使用 `thebibliography`/`bibitem`，正文以 `cite` 引用；当前独立版不依赖 BibTeX/Biber。所有 bibitem 必须被引用，引用 key 必须存在且不重复。文献是否真实、是否确实阅读使用仍由团队核验。

内容片段不得更改全局页边距、目录、页码或文件读写。可以用正常数学环境与表格、显式 `includegraphics{figures/name.pdf}`。有额外宏包需求时应在受控 style 中审查加入，更新包指纹后重建，而不是绕过检查器。

## ai_usage.json

```json
{
  "status": "used",
  "brief_purpose": "按真实情况填写的简要用途",
  "records": [
    {
      "id": "record-001",
      "tool": "实际工具名",
      "version_or_model": "实际版本或模型，不推测",
      "stage": "实际环节",
      "purpose": "具体目的",
      "prompting": "主要提示方式",
      "process": "使用过程、迭代和产出的说明",
      "language_polishing_only": false,
      "adoption": "采纳、部分采纳或拒绝的情况",
      "human_modification": "实际人工修改；没有修改也要如实说明",
      "human_verification": "实际核验方法和结果，不能代签",
      "typical_prompt": "可选典型提示",
      "typical_output": "可选典型回复",
      "artifact": "可选匿名的相对成果路径"
    }
  ]
}
```

以上是字段说明，不是可直接声称完成的真实日志。用于实际构建时，必须填入真实内容。`records` 可有任意合理数量，不限制在五个小问或八条交互。纯语言润色的后面三个详细字段可省，但不能把模型/代码/数值处理伪装成纯润色。说明可按同类工作汇总，团队仍应保留足够的原始记录用于核验。

确实未使用时：

```json
{"status":"unused","brief_purpose":"","records":[]}
```

普通确定性搜索、编译脚本不是因为“软件”二字就必须认定为 AI；AI agents、代码助手及模型驱动检索/总结应按实际使用说明，不以工具品牌臆断是否用过模型。

## 人工 review

构建后复制 `review.required.json` 到独立的完成文件。根据实际检查填写匿名 reviewer_alias、checked_at 和八个检查项；`bundle_digest` 不改。任何候选 PDF/ZIP 变化都需要新的复核。文件存在、字符串非空、哈希匹配，只证明结构与一致性，不证明人真的读过内容。
