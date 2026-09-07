# v16 最终迭代总结

这次我没有只做一版：在 v13 后继续完成了 v14、v15、v16 三轮自审迭代。

## v14：PPTX Auto Image Slot Discovery

解决：不再手工写所有图片框坐标。

- 自动解析 `p:pic`
- 自动解析 `shape/a:blipFill`
- 支持 group transform
- 自动分类 photo / figure / icon / background
- 39 个未旋转 native image bbox 与 Inkscape Reference 匹配 PASS
- 1 个旋转图单独由 rotation-aware placement 处理

并新增：
- smart white/transparent trim
- 自动 downsample
- background underlay，避免 contain 时露出旧图片

## v15：Caption Regions + Auto Images

自查后发现 T02 并没有真正的 Picture shape，但确实有 `(a)(b)(c)(d)(e)` 语义图位，所以继续做：

- caption-guided region discovery
- 自动找到 T02 5 个 panel
- 与 v13 人工标注区域平均 IoU = 0.7656
- 修复 Stage-II title overlap 后实际渲染稳定

同时增加：

```json
"auto_images": ["a.png", "b.png", "c.png"]
```

不再要求用户知道 `panel_a/panel_b`。

支持：
- reading_order assignment
- aspect assignment

## v16：Smart Focus

最后自查发现 cover 模式仍可能把偏置主体裁掉。

加入轻量级 edge/contrast saliency focus：

- 极端测试图主体在 x≈0.82
- 自动估计 focus ≈ `[0.7965, 0.5121]`
- 居中 crop 几乎裁掉主体
- smart crop 保留主体

这层不依赖额外 CV/检测模型，结果可复现。

---

## 为什么我现在停止继续堆功能

还可以做：
- YOLO/CLIP/SAM 主体识别
- 自动理解“哪张图片应该对应哪种语义 panel”
- 更复杂的 scene-aware cropping

但这些都会让这个模板库依赖额外模型，并引入：
- 模型版本
- 推理成本
- 环境依赖
- 不稳定预测

对于论文 SVG 模板，`auto assignment + aspect matching + smart focus + manual focus override` 已经覆盖绝大多数实际需求，并且保持确定性。

所以我认为：

**v16 是当前架构下的合理“最终稳定版”。**

不是说以后永远不能改，而是之后的新增应该由明确的具体论文 Figure 需求驱动，而不应该继续无目的增加复杂度。
