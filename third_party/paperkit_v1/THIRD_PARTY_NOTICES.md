# 来源与修订范围

上游：bosprimigenious/ModelingPaperKit
https://github.com/bosprimigenious/ModelingPaperKit
审查基线 commit：47e9bc8046d037ca765eb10d6869012a178983f7

主要参考文件：
- templates/cumcm/main_cumcm.tex（blob bf99f08114617285bff5eef766122ad32e4ff3ee）
- core/paperkit-base.sty（blob f805f098f1be2fe3033bfd44fc74d486c6ac7451）
- templates/cumcm/sections/references.tex（blob 2f208e3a5bc4424b52d9138a1ed0c3c331a1d0ae）
- templates/cumcm/sections/appendix.tex（blob 4055b33bdafe11672d016edfc13faaf537cfc4db）
- templates/cumcm/sections/ai_declaration.tex
- templates/cumcm/support/AI工具使用详情.typ、README-AI使用详情.md
- scripts/check_submission.py、preflight.py 与 2026 rules snapshot

基于这些源文件的 CUMCM 布局、章节设计及常用宏接口修订/提取，生成本专用子包。新 Python 工具、验证器和 Harness 适配器是此次交付新增实现。上游全量 skills、其他赛事模板、预编译旧 PDF、字体和未核验官方专用页不包含在此包中。

这是按用户请求提供的修订交付，不宣称上游授权本包作为官方模板，也不替上游授予 MIT 等其他许可。需要再次公开发布或商业分发时，请核对上游自己的许可信息及相关内容权利。

第三方运行依赖由各自的发行方和许可证管理：TeX/ctex/Fandol、PyMuPDF、jsonschema、pytest。压缩包不包含任何独立字体文件。
