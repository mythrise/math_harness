# 验证“比现有数学建模Agent更强”的实验协议

## 当前结论

四个外部基线与完整历史国赛题均NOT_RUN。本次真实数值演示只检验工程链及自定义优化器在一个合成小问题上的行为，不能替代本协议。`status.json`和比较器不会把未测改成零分或落后。

## 预注册比较单位

以完整题目为独立统计单位，不以一个题的seed或一个函数单测当作一道题。建议固定不少于20道公开历史问题，跨优化、统计预测、动力学仿真、综合评价和图结构，年代与难度均衡，明确本科/专科题组。代码公开题和模型预训练可能已有泄漏，因此另建参数扰动/未公开变体以及人工重新设计的隐藏评测。

在开发/选择测试题与最终隐藏测试题之间保持隔离。主协议提交后冻结问题文本/数据哈希、依赖/容器镜像、模型实际版本、每系统配置、随机重复数、费用/墙钟上限、评价器与人工rubric。未经操作者允许不自动下载比赛材料或上传到外部模型。

## 四个基线怎样公平运行

1. XiaoMaColtAI/math-modeling-skill：冻结commit，按它现有独立门禁与原生工作流运行，不能删除质检后比较。
2. jihe520/MathModelAgent：优先冻结当前Skills版本，记录实际宿主Harness；不要拿旧停更CLI代表最新Skills。支持Typst时允许保留其格式，但最终统一PDF验收。
3. qiancheng0/ModelingAgent：记录repo commit，配置路径/密钥必须只做公开的必要适配；保存异常与部分输出，不偷偷人工重写结果。
4. usail-hkust/LLM-MM-Agent：选择明确的当前CLI或demo入口并说明，开启正式写作阶段，保持HMML/solver能力；不能用被注释论文的默认CLI谎称它不会写论文。

主比较至少两条：相同底层模型预算的harness能力比较，以及各系统推荐配置下的实际费用/时间—质量前沿。Codex+Claude双供应商与单模型基线不等价，必须同时报告。并发线程、token、重试、环境修复、外部搜索、CPU/GPU与FE都入账。

## 评价层

硬门槛：文件真实可运行、问题全部覆盖、目标/约束独立重算、数据无泄漏、数字有来源、无伪造引用、资源合规、格式与AI披露合规。任何致命数学错误不能被写作高分抵消。

连续指标：问题专用损失或优化质量、基准相对改善、稳健性、完整度、复现率、字节绑定证据比例、失败率、费用和时延。不同题目的指标先按预定义规则规范化，不能事后为有利结论换尺度。

评委至少包括领域建模、数值实验、论文表达三种职责，系统名称与模型名称盲化；Claude CLI只是其中的复查工具，必须保留人工/精确oracle。自动评委评分不能成为唯一终点。

对代码手、固定评测、独立Claude审查、确认隔离、MOSAIC、OurWork、资源恢复分别做预注册消融。OurWork主要衡量可编辑性、视觉质量和证据一致性，不声称单凭美观提升数学准确度。

## 分析与接纳

每题重复不少于3次，同题先聚合，然后对题目做配对分析。问题类型分层报告，置信区间按题目重采样。四个主基线比较预先选Holm等多重比较控制；预注册最低实际意义效应与非劣性约束，记录缺失/超时为失败，不只比较成功子集。

只有主要评价显著且实际提升、关键题型不劣、正确性/复现硬门槛通过，才可写“在冻结测试集与预算上优于这些基线”。这仍不等于“强于所有现有Agent”或“保证获一等奖”。

## 现成比较脚本

```
python benchmarks/compare_runs.py evidence/manifest.json --reference BASELINE_NAME --challenger CUMCM-EgoHarness
```

manifest为对象list，每行包含agent/task_id/replicate、artifact_file/artifact_sha256、judge_file/judge_sha256、problem_sha256/data_sha256、budget_profile/backbone_profile/evaluator_digest、metric/direction。
judge JSON必须含valid=true、independent=true、score、evaluator_digest。比较器验证文件与匹配条件，以题目为单位汇总，题目少于10不出区间。它不替代数学评审、不会自动签发SOTA，也不是四仓库自动安装启动器。
