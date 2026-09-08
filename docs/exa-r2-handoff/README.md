# 数学建模 Harness 的 Exa 配置交接 R2（附件校正版）

本包取代上一版 Exa 配置交接包。依据是用户上传的 **Search API Reference**，不是推测用户已经启用的账户配置。官方页面补充核验日期：2026-09-08。

## 交付边界

- 已完成：参数级设计、兼容 profile、目标策略、8个脱敏 REST 请求示例、有限请求合同参考代码、离线测试。
- 未完成：将策略集成进用户当前 harness、真实 Exa 认证请求、真实 Claude/GPT 联调、Docker 和完整论文流水线验收。
- 未修改 GitHub，未读取本机或用户的密钥，未设置任何云服务或自动任务。
- 无字体、模型权重或付费论文原文。

## 交给 Codex

把整个文件夹交给 Codex，让它先读取 `CODEX_IMPLEMENTATION_PROMPT.md`，再按 `ACCEPTANCE_TESTS.md` 实施。不要只复制一大块JSON。

| 文件 | 用途 | 现在是否生效 |
|---|---|---|
| `configs/exa-modeling-compatible.json` | 仅用已核对的现有字段，建议80次尝试/6条结果/45秒 | 新建工作区时可作为基础profile；仍需本机原有配置验证 |
| `specs/exa-research-policy.proposed.json` | 分阶段策略、动态预览、证据、权限、恢复 | **设计合同，需要实现解析器和控制器接线** |
| `examples/raw-exa-requests.json` | 真正可映射到REST的请求结构 | 未发送；认证只能由运行时注入 |
| `reference/request_contract.py` | 本交接所需REST子集的离线校验与动态降级参考 | 不是客户端、隐私网关或完整OpenAPI验证器 |
| `DESIGN_CN.md` | 配置依据与取舍 | 阅读材料 |
| `checks/` | 实际离线测试日志与范围 | 不证明真实服务可用 |

目标策略中的 `request_template` 才是可发往Exa的字段片段。`date_policy`、`enabled_by_default`、`budget`、`http` 等是本地字段，禁止直接发送。

动态摘录默认关闭：仅在显式启用、实际接口能力检查后，可用于广度发现。假设审查、反方检索、正式引用坚持逐来源核验。

## 无密钥的离线检查

```bash
python -m unittest discover -s reference -p 'test_*.py' -v
```

测试只使用标准库和本包示例，完全不发网络请求。API文档说支持，不代表本机SDK或账户已验证支持。
