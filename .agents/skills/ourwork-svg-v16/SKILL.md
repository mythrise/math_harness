---
name: ourwork-svg-v16
description: Create editable scientific OurWork framework figures with the attached v16 vector engine and guarded reference templates.
---

# OurWork SVG v16

只用 `vendor/ourwork_v16/src` 的原始引擎。原始模板不可写，输出写到当前项目，用户图片必须真实存在。不要将栅格生成图改后缀冒充SVG。

原模板受保护编辑：
```python
from pathlib import Path
from cumcm_harness.figures import render_reference
render_reference("t0", config, Path("outputs/ourwork.svg"))
```
模板ID和配置形状必须以 `vendor/ourwork_v16` 的 registry/configs 为准；不要猜 semantic slot 名。先做空配置回归，再按现有语义槽修改。包装层使用 reference_semantic_image、strict=True、guard=True。图像槽的cover/contain/裁剪继续使用附件接口。

生成系统总览：
```python
from pathlib import Path
from cumcm_harness.figures import framework
framework(Path("outputs/harness_overview.svg"))
```
这个总览是基于附件SVG/node/arrow原语的新构图，不是某个参考模板的像素级复刻。Inkscape导出PDF/PNG，保留SVG可编辑性及来源摘要。

验收需看最终PNG/PDF：文字不溢出、无黑框缺字、箭头语义正确、图片比例合理。二十原模板空编辑已做字节一致测试，但不能以此断言每种新文字与新图片都不溢出。字体只记录名字，由操作员系统安装，不得打包字体文件。
