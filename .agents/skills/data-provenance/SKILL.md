---
name: data-provenance
description: Plan auditable preprocessing within the training boundary
---

# 数据手：质量、口径与防泄漏
输入：只读开发数据审计和逐问需求。输出data_plan。逐一说明所有输入文件的来源、观测单位、字段/计量单位、缺失/重复/非有限值/读取范围；“文件已经打开”不代表全部表/图已经理解。
从数据机制选择缺失处理、异常标记、特征工程。不一律禁均值/删行，不强推MICE、KNN或DBSCAN；异常观测可能是真实极端事件。保留原始文件，派生文件独立命名，报告处理前后变化与理由。
IID、分组、时序、分组时序按真实独立单元选择。拟合插补、缩放、特征选择必须在训练折内。时序特征只能使用预测时已知信息；不得双向插值未来、先全量归一化再切分。校准集独立于选模。
必需缺失数据列required_data；不以AI生成补齐观测。researched数据必须有核验来源；synthetic_scenario只能diagnostic_only。数据计划仍是计划，不能声称已经清洗或通过检验。
