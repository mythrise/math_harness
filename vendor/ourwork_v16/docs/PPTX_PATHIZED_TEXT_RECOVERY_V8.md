# PPTX Pathized Text Recovery — v8

## 背景

`T16_radial_bubble`（PPT 第 20 页）和 `T17_cube_ray`（PPT 第 21 页）在 WPS PDF → SVG 后，文本不再存在为 `<text>`。

统计：

```text
T16 reference SVG: <text> = 0
T17 reference SVG: <text> = 0
```

但原始 PPTX 中仍有完整 TextBox。

## T16

PPTX 恢复出 11 个语义节点：

```text
Maturity
People
Technology
Process
Personal
Team
Processing efficiency
Data surplus
Convenience
Accuracy
Security
```

v8 暴露：

```text
center
people
technology
process
personal
team
processing_efficiency
data_surplus
convenience
accuracy
security
```

并提供：

```text
primary_nodes[]
outer_nodes[]
```

对于有 PowerPoint text shadow 的标签，v8 同时删除对应 path glyph 和 shadow image。

## T17

PPTX 恢复：

```text
Convenience
Accuracy
Security
Upper layer
Lower layer
```

v8 暴露：

```text
axis_convenience
axis_accuracy
axis_security
upper_layer
lower_layer
```

以及：

```text
axes[]
layers[]
```

## 安全原则

- 不重新序列化整份 SVG；
- 不删除目标文字之外的图形；
- 不用 CairoSVG 作为复杂 SVG 的最终判断；
- 正式测试统一走 Inkscape；
- unchanged semantic value 会直接跳过 patch。

辅助审计数据：

```text
registry/pptx_overlay_slots_v8.json
registry/path_query_slide_20.json
registry/path_query_slide_21.json
registry/image_query_slide_20.json
```
