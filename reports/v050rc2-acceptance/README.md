# v0.5 rc2 可公开验收证据

受测源码 `fefa1ba1d0acda7c77cc6fba8d3b8066c59957bc`，基线 `c5d807b556af217432d4f9d63b92e80784c52759`。

- `code-changes.patch`：完整源码整改 diff；摘要见 `code-diff.json`。
- `test-counts.json`：原始本地与 CI JUnit XML 的 SHA-256、计数与耗时；集合有重叠，不求和。原 XML 保留在本地和对应 CI artifact 中。
- `github-*.json`：两个新 SHA 的 CI 工作流与步骤状态。
- `three-modes-final.json`、`*-final-audit.json`：固定模型回复的真实 Docker/TeX 联跑与零调用重放；不是 LIVE 科学实验。
- `ci-*.json`：CI 隔离、支撑包复现、PaperKit 和两次数值验证回执摘要。
- `runtime-parity-final.json`：三个本地执行/测试镜像与受测 Python 源码的实际摘要匹配。
- `actual-document-layout-summary.json`、`docx-*.png`、`tex-*.png`：这两对实际测试原稿/改稿的渲染图像与检查，不是其他文档的版式证据，不是人工签核。
- `live-summary.json`：真实服务运行、费用及失败阶段的摘要；原题/附件、完整本地初稿与逐条去向、原始模型回复仅保存在独立本地真实测试目录。

真实输入：`定日镜场真实测试/20260909-v050rc2/`；未提供可证明来自网页会话的初稿。工程通过不解除 RC，完整真实科学闭环以真实运行回执为准。
