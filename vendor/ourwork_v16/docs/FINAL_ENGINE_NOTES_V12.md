# v12 最终工程判断

## 迭代过程

### v9：Semantic Geometry
解决了“文字改了，但图形数据不跟着变”的问题。

- T15 数值变化 → bar 长度同步变化
- T02/T03 header 数量变化 → 局部 header reflow
- T20 milestones 数量变化 → 中部箭头式 roadmap 自动重绘

v9 测试发现 T15 的数值标签仍留在旧位置，于是继续迭代。

### v10：Geometry labels + Config Lint

- 修正 T15 数值标签位置
- 加入 config lint、容量建议和 PNG/PDF 一键导出
- 20/20 模板 XML/渲染/identity 全通过

进一步测试发现，当输入 `0.2` 而不是 `0.20` 时，T15 数值文本可能产生重复，于是继续迭代。

### v11：Safety / Font / Output Guard

- 数值文本按“数值等价 + 行位置”删除旧标签，彻底解决重复
- 新增跨平台字体 fallback，源字体始终排第一
- 新增 embedded image hash guard，防止再次引入 v4/v6 的黑框类回归
- XML、安全引用、输出验证纳入生成流程

### v12：Structural Reflow 收尾

- T01 pipeline blocks 支持 2–8 个局部重排
- T15 comparison rows 支持 2–9 行完整重排
- 保留 T02/T03 动态 header、T20 动态 milestone
- 最终生产级 QA 全通过

## 为什么现在停止继续“泛化”

剩余可继续做的方向主要是：

- T04 从 4 panel 变成任意 N panel
- T16 自动增删径向节点并重算 3D connector
- T17 自动改变立方体层数 / 3D 图拓扑

这些已经不是“高保真局部编辑”，而是在重新设计整张图的版式。继续强行自动化会明显降低 Reference fidelity，与这个项目最核心的目标冲突。

因此 v12 的边界被定义为：

> **原构图高保真 + 文本完全语义化 + 高频数据/局部结构可重排。**

在这个边界内，我认为已经达到生产可用的稳定状态。若未来针对某一个模板明确需要“大改拓扑”，应为该模板单独增加专用 layout engine，而不是继续把全局引擎做得更激进。
