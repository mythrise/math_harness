# 扩展算法、题型、数据和评测

## 1. 新算法不是只增加一个名字

新建 `.agents/skills/<name>/SKILL.md`，声明来源及版本、问题数学形式、变量/约束类型、目标个数、确定性/噪声、依赖、时间复杂度、失败情形、基准和正确性检查。向 `algorithms.METHODS` 添加方法卡；可执行封装在独立模块，不能改写原MOSAIC。

原始算法接口由附件Problem/ProblemContract决定；不要从空白随手猜对象字段。连续、二进制、排列、图结构、整数和混合变量分别需要验证适配器。新增一般约束时，至少验证可行性排序、约束容差、处罚尺度或修复算子的数学语义，不能静默罚函数。

## 2. 问题求解器合同

模型生成完整文件包，严格Schema允许Python、JSON、Markdown、CSV、TXT；禁止自动加载的AGENTS/CLAUDE/sitecustomize/usercustomize文件。主入口总是：

```
python main.py --input PUBLIC_DATA --out NEW_OUTPUT --seed N --budget B --variant NAME
```

数据名称不固定，题目合同必须说明。输出答案模式由独立评测规范定义；代码手不能定义自己的通过分数。多问可在一个入口里按DAG顺序解答；当前不自动为每个问生成独立容器。新增实验变体要以实际代码分支实现，不能仅变日志标签。

数值结果的输入/输出类型、单位、维度、精度/容差、可行域、缺失与异常处理都写清楚。脚本需要的所有非公共Python依赖和资源都必须能打包并复现。worker会记录导入源码及Python open审计事件发现的运行资源；本机原生库直接I/O未必被捕获，因此仍须对独立支撑包复现验收，不承诺动态追踪绝对完整。

## 3. 独立评测器

入口：
```
python evaluate.py --input EVAL_INPUT --out NEW_EVAL_OUTPUT --answer SOLVER_OUTPUT --seed N --budget B --variant NAME
```
`EVAL_INPUT/public` 为公开输入，`EVAL_INPUT/private` 为参考数据。输出 `evaluation.json` 符合 `schemas/evaluation.schema.json`，包含valid、metric、score、checks、measurements、question_coverage。只在检查全部通过且数值有限时valid=true。

不能import求解器的目标函数来做“独立重算”。允许从同一公开题意重新实现算法定义；用解析小例、独立高精度解、枚举或另一数值实现交叉核验。负控制必须明确返回valid=false，崩溃和没有输出不算成功拦截。

预测任务：先按人/实体/时间划分，预处理仅拟合开发部分；公开确认输入与私有标签分离；输出逐样本预测；由评测器计算误差。时序任务不能随机打乱未来。

优化任务：检查所有可行约束、目标重算、FE账本、外部固定参考点与选择规则。工程任务应同时报告风险/可靠性/资源，不为了单分数牺牲必需条件。评价任务应明确权重主观性、方向、尺度与排序稳定性。

## 4. 配置与冻结

修改configs的副本，再init新工作区。不要改既有运行的config、protocol、sources、code、evaluation或确认数据。真实修订生成新版本/新工作区；在报告中区分验证探索与最终确认，防止重复查看确认集。

`research_opt_in` 只允许实验分支，不允许绕过审查。预算同时包括模型调用数、模型超时、Claude每次费用上限、每cell目标评价数、CPU/内存/时间、总候选数。模型收费与运行时间单独报告，FE公平不等于时间公平。

## 5. 论文与引用

来源文件为list，每项id/title/url/verified/verification_note。引用必须人工或外部可靠过程核验，再置verified=true；程序验证格式而非替你核验真实性。给出领域论文，不只引用比赛规则。普通正文数字通过{{claim:id}}，数学常数放equations字段。

资料检索目前在入口前完成，不是运行时联网文献Agent。复杂题面图示需要已核验解释。MATLAB、SPSS、R、任意Office格式不是现成执行后端；当前可运行解题后端为Python。扩展这些能力必须另写执行/审计/复现适配器并测试。

## 6. 回归要求

必须新增适用域拒绝、正确小例、非法结果、预算/异常/超时、输入修改、完整矩阵、负控制、并行发布、恢复、独立包复现等测试。先保证原有测试不回退，再冻结新任务集比较；不要以单测全绿直接宣称建模获奖水平。
