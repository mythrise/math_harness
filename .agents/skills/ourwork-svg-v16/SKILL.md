---
name: ourwork-svg-v16
description: Draw the actual problem workflow with the existing guarded vector engine
---

# 模型框架与图表
使用原有vendor/ourwork_v16引擎与SVG原语、受控参考模板，不修改vendor。ourwork图应描述本题冻结问题/模型/依赖/验证路径，而不是把软件Agent架构图当作论文模型图。
节点与箭头必须能追踪到实际合同；独立问题不画串行因果箭头。视图可聚合，但完整ID与依赖保存provenance，不静默遗漏。长标签换行或换版，不把文字缩到不可读。超过显示容量时明确聚合说明；实图审查验证语义与可读性。
真实数值来自对应作业输出。图题在下、表题在上；轴标签含单位，误差线说明是标准差还是区间，避免不必要三维装饰。保留SVG/PDF与数据旁注，不要求每问一张图、不硬凑十张。
字体从运行环境探测，不能假定SimHei存在；不打包字体。矢量图不以DPI作为真实性凭据。保持纵横比，短表同页/长表重复表头，具体尺寸根据页面与信息量选择，不照搬Graphviz英寸为厘米。
