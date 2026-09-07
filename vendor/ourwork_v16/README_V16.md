# OurWork SVG Production v16 — Auto Image System Final

v16 是在 v12 的高保真 Semantic SVG 引擎之上，对“图片占位/自动放图”链路连续迭代后的稳定版本。

## 最终能力

### Text / Semantic / Geometry
继承既有能力：
- Reference 高保真 SVG
- semantic slots / slot_groups
- local reflow / semantic geometry
- T01/T02/T03/T15/T20 等结构化接口
- Inkscape SVG→PNG/PDF

### Image system（v13→v16）
新增并稳定：
1. PPTX 原生 `Picture` 自动发现
2. PPTX `shape + blipFill` 图片填充自动发现
3. nested group transform 坐标恢复
4. caption-guided semantic panel 自动发现（T02 等）
5. `images` 显式图片槽位
6. `auto_images` 图片池自动分配
7. reading-order / aspect-ratio 两种自动分配策略
8. `cover / contain / stretch / auto`
9. `focus_x / focus_y`
10. `trim:auto` 自动清理大面积白边/透明边
11. 图片自动降采样，避免小槽位嵌入几十 MB 原图
12. rotation-aware 图片插入
13. rect / rounded_rect / ellipse clipPath
14. `smart_focus`：照片 cover 裁剪时自动估计显著主体重心
15. 原 Reference 图片 payload 保留 + output guard

---

## 最简单用法：完全不写 slot 名

### T02：给 5 张图，自动按阅读顺序放入 5 个 panel

```json
{
  "auto_images": [
    "images/a.png",
    "images/b.png",
    "images/c.png",
    "images/d.png",
    "images/e.png"
  ],
  "auto_image_options": {
    "assignment": "reading_order"
  }
}
```

```bash
PYTHONPATH=src python src/ourwork_v16.py \
  --template T02_two_stage_pipeline \
  --config config.json \
  --out figure.svg \
  --png figure.png \
  --pdf figure.pdf \
  --strict
```

---

## 显式图片槽位

```json
{
  "images": {
    "input_photo": {
      "path": "input.jpg",
      "fit": "cover"
    },
    "overview_figure": {
      "path": "plot.png",
      "fit": "contain",
      "trim": "auto"
    }
  }
}
```

### 支持字段
- `path`
- `fit`: `auto | cover | contain | stretch`
- `padding`
- `align`
- `focus_x`, `focus_y`
- `smart_focus`
- `trim`: `none | auto | white | transparent`
- `opacity`
- `embed_scale`
- `max_embed_dim`

---

## Smart Focus

对照片型 slot，如果使用 `cover` 且没有手工指定 `focus_x/y`，v16 默认允许显著性重心裁剪。

```json
{
  "images": {
    "input_photo": {
      "path": "wide_photo.png",
      "fit": "cover",
      "smart_focus": true
    }
  }
}
```

如果需要绝对可控：

```json
{
  "focus_x": 0.8,
  "focus_y": 0.45,
  "smart_focus": false
}
```

---

## 自动重新发现 PPTX 图片槽位

```bash
PYTHONPATH=src python src/pptx_image_slot_discovery_v14.py \
  --pptx 'OurWork流程图&插图复刻.pptx' \
  --templates-json registry/templates.json \
  --out registry/my_auto_slots.json
```

这个解析器支持 nested PowerPoint Group：

`group off/ext/chOff/chExt → child shape → slide absolute coordinates → SVG 960×540 coordinates`

### caption semantic-region discovery

```bash
PYTHONPATH=src python src/caption_region_discovery_v15.py \
  --pptx 'OurWork流程图&插图复刻.pptx' \
  --templates-json registry/templates.json \
  --out registry/my_caption_regions.json
```

---

## 主要入口

- `src/ourwork_v16.py`
- `src/image_slots_v16.py`
- `src/pptx_image_slot_discovery_v14.py`
- `src/caption_region_discovery_v15.py`
- `src/reference_editable_v12.py`
- `src/semantic_geometry_v12.py`

## Registry

- `registry/image_slots_v16.json`
- `registry/image_slots_auto_v14.json`
- `registry/caption_regions_auto_v15.json`
- `registry/semantic_slots_v12.json`

---

## 最终 QA

见：`tests/v16/final_qa_summary.json`

关键结果：
- 20/20 templates no-edit byte identity
- PPTX native discovery：39/39 unrotated bbox PASS，1 rotated case 单独处理
- T02 caption-region 自动发现 5/5
- 8 个 canonical template 当前拥有 image slots
- 共 20 个生产 image slots
- T01 `auto_images`: 6/6 自动分配
- T02 `auto_images`: 5/5 自动分配
- T01/T02/T03 sample output guard: PASS

---

## 版本判断

v16 之后当然还可以接真正的目标检测模型做人物/物体级智能裁剪，但这会引入模型依赖、运行成本和不确定性，并不一定比显式 `focus_x/y + smart_focus` 更适合论文绘图模板。

因此在当前目标：

> **Reference 高保真 + Semantic 可编辑 + Structure 可变化 + 用户图片自动适配**

下，我认为 v16 已经可以作为主线稳定版。
