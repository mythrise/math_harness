# 三模式输入架构

## 设计原则

原题/官方数据是任务依据；网页讨论和人工初版是建议；论文现有结果是待维护的既有主张，而不是新实验。三者不能共用一个无类型的文本入口。

`input-mode`负责选择工作路径，`practice/contest`负责授权和人工门禁。没有“改成idea就跳过文献”或“已有论文就宣布原实验通过”的捷径。

## 入口及冻结

entry_cli.py解析三路入口，其余命令仍转给已有cli.py。entry_inputs.py先在临时目录验证和构建，再发布workspace。输入模式、来源字节、提取文本、来源块、用户报告AI记录一起冻结到entry.json/entry目录与Store。run与恢复先复核；源字节或封存结果变动均阻断。新模式不能强行加到已开始的旧工作区。

自然语言初版是首选：不必让用户手写JSON。多个来源各有哈希及真实出处；完整聊天的受控摘要不是输入事实。密钥、私有数据混放、超长/不支持格式不能悄悄清洗后假装完整接受。

## Idea路径：先独立、再吸收、完整验证

1. 原有MaterialsWorkflow独立形成题意、开发数据计划、可靠基准组合，不提前读取初版以降低锚定。
2. IdeaWorkflow按受控块读取各初版。idea_curator提取精确原文片段及类型，所有块都有处理或排除理由。
3. idea_adversary在独立上下文结合原题、盲建基准和数据计划逐项反驳。其调用通过已有Claude/GPT审查接管，不新增不受控服务。
4. items/triage进入建模手上下文。建模手仍完整产出正式plan，逐条做idea_plan_alignment；来源偏好不构成跳过约束的许可。
5. 接受的假设和约束绑定正式plan元素；正式计划照常经过Exa假设卡/反方与独立模型审查。网页提到的论文必须重新核验，网页成绩必须重新计算。
6. 原有评测器preflight、代码review、每候选自测、baseline、候选/消融/敏感性、开发冻结、确认、论文/摘要/语义/视觉、人工发布照常执行。

对初版的四种最终处理：ADOPT、MODIFY、REJECT、DEFER。ADOPT/MODIFY只说明进入模型，不说明已经有实验支持；DEFER不能写成当前成果。全流程审计包含来源摘要及逐项决定，原始聊天留在私有workspace，不直接打进公开论文支撑包。

## Scratch路径

研究入口相同，只是没有外部idea整理和比较层。官方题目必需，数据可省略只适用于本来不需要数据的题目；实际必须补充的数据仍由研究门禁阻断。原有确认集、私有参考、sources及Exa sidecar参数保留。

## Revise路径

RevisionController共享调用、技能、独立审查、恢复和人工签核原语，但不伪装成ResearchRunner。

先诊断，再输出绑定source block哈希的精确patch。普通语言可改；数字、单位、公式、引用、代码、重要含义强度词受保护。程序检查后独立数学/论文审查验证含义。无工具子代理不执行原论文里嵌入的指令。

DOCX保留文档包资源与样式，只改明确安全的普通段落。MD/TXT/TEX输出新副本，受保护代码/控制段不执行。PDF没有可靠可编辑结构时只生成Markdown工作副本，不假装原版式重建。

需要改模型、补实验、替换数值、补关键文献的意见生成research_requests与research_handoff.md；由用户提供原题及数据，新建idea工作区后才能进行新实验。这种安排防止用“润色”名义偷偷改变结论。

## 新角色与技能

idea_curator、idea_adversary、paper_editor是新增角色，共享显式技能正文注入、技能摘要、prompt/response摘要和独立上下文。原有14个调用角色增加到17个；两个新SKILL与已有15个共17份。测试验证接线和数据边界，不等同于真实模型技能效果评测。

## 文件对应

- entry_documents.py：有界读取、区域保护、精确编辑、DOCX回写。
- entry_inputs.py：来源类型、三路冻结、外部AI用户记录。
- idea_workflow.py：片段、反方、全项采纳映射。
- paper_revision.py：诊断、补丁、语义审查、变更报告、研究移交。
- controller.py / materials_workflow.py：进入原有完整建模链。
- packaging.py / materials_paper.py：公开来源记录与真实AI披露。
- tests/test_three_inputs_*.py：145个新增定向测试。

所有新代码使用当前已安装依赖。生产执行与TeX的权限、MOSAIC/OurWork原实现和冻结评测器没有被放宽。实际尚未验证的执行环境见TEST_REPORT_CN.md。
