---
name: cumcm-paper-2026
description: Write evidence-grounded Chinese CUMCM papers using the self-developed 2026-compliant LaTeX profile and actual builds.
---

# 论文手与2026格式

先读 `cumcm_harness/paper.py` 中 RULES 的官方来源，以及 docs/RESEARCH_REVIEW_CN.md。这是按官方规则自行实现的profile，不称作组委会官方LaTeX类。

输入只能使用被冻结的主张表、方法合同、实际图表和核验过的文献。输出 `schemas/paper.schema.json`。数值用 `{{claim:ID}}`，文献用 `{{cite:ID}}`，引用集合要与正文一致。没有证据不猜实验结果；正文结果不得从模型自由填写小数。

电子论文从摘要开始，不含承诺/编号页/目录；A4四边至少25mm，摘要一页，正文不超过30页，页脚中部连续编号。附录列出所有支撑文件与完整可运行源码；引用处有标注，匿名检查覆盖正文/附录/支撑包。正式提交还须确认赛区补充要求。

参考文献前设置AI工具使用声明，支撑包有 `AI工具使用详情.pdf`：名称版本、目的环节、主要提示方式、采纳/修改/核验。不得伪造“未使用AI”或“人工已核验”。

实际运行XeLaTeX至少两次，禁止shell-escape；缺字、未定义引用、超页或文件超限则BLOCKED。论文和支撑包分别≤20MB，不用开发仓库ZIP替代支撑包。通用库本身无需逐行附录，定制代码及其必要资源必须能在独立支撑包中复现。所有正文渲染及完整附录需人类检查；自动模型只检查声明的页范围。
