---
name: literature-adversary
description: Exa primary-source search plus hypothesis-specific adversarial reading
---

# 文献与独立假设反方
控制器经Exa检索，模型只提出抽象方法查询。支持和反方均绑定真实H-ID；反方独立生成反例、失效条件、识别条件与竞争解释。保留每条反证的READ/EXCLUDE/NEEDS_MORE_CONTENT及审查理由，不能由作者筛掉不利资料。
原文、提取摘录、生成摘要/综合分开。仅controller提供的来源ID、snapshot和原文偏移可引用；短引文逐字吻合还需独立审查语义与上下文。未知时间/版本不能证明“最新”；镜像不算多个独立来源；经典原理检索不强限近五年。
搜索只能产生证据或可检验论证；经验/简化假设必须有hypothesis_Hn实际程序诊断。没有找到反例不代表成立，诊断通过不代表普遍真理。真正否定必须返回建模修订，不能deep搜索刷通过。
复用R2策略、受控鉴权、租约/UNKNOWN恢复及预算。凭证由get_exa_api_key运行时取得，不能复制到任何提示或文件。不得将原题、原始数据、身份、附件名发送搜索；正式比赛仅执行授权范围内查询。
