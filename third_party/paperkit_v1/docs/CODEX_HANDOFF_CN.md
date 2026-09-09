# 交给 Codex 的接入任务

请将本包接入已有 mythrise/math_harness，但不要替换 controller、Store、审查板、科学实验内核、Exa 配置、任何凭证或 MOSAIC/OurWork。先读取 README_CN.md、HARNESS_INTEGRATION_CN.md 和 reports/ACCEPTANCE_CN.md。

1. 核对当前 cumcm_harness/paper.py 的 Git blob 是否为 2e3043de9325704e484351cf400f8df7e8be3815。匹配时先运行安装器 dry-run，确认后 --apply。若不匹配，先审查真实的 build_paper/build_ai_details/preflight/compile_tex、controller 调用和 packaging 依赖，再更新兼容适配和对应回归测试，不删除哈希保护强装。
2. 在宿主真实 Python 环境安装本包。保持原 claim/cite 绑定、source inventory、审批HMAC、PDF/支撑包摘要与返回字段不变。不得在 PDF 冻结和签核之后重新排版或改字。
3. 对两个独立示例运行实际编译和全部本包测试。接着对宿主仓库运行原自测和全新工作区的工程演示，保留原始 stdout/stderr、PDF和支撑ZIP摘要。测试夹具明确标记，不得声称真实服务联跑。
4. 检查 actual PDF 的 A4/摘要/页码/声明次序/正文页数/代码完整性/匿名；视觉审查至少全部正文与摘要，附录按宿主要求完成完整人工视觉签核。若出现 overfull、缺图、缺字，修复排版或真实资产，不删除测试。
5. 更新源码后重建必要运行环境，并创建新 workspace；不修改旧 workspace fingerprint、批准文件或数据库。最终如需真实模型验收，明确征得执行权限和预算，并沿用原配置。
6. 验收报告分开列出：实际通过项、真实失败项、尚未执行的服务/赛题/环境验收。保留人工 plan/release，不提供自动提交。

本包已解决前述模板工程问题，但没有提供经过核验的当届承诺书/编号页；获取真实官方文件后仅做前置合并，验证论文部分不变，不自行重绘冒充官方页。
