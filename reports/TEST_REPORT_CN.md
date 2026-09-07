# CUMCM-EgoHarness 0.1.0 实测报告

核验日期：2026-09-05。测试对象由 tested-core-sha256.json 绑定。原始XML、日志和结构化验收在同目录。

## 1. 验收结论与证据边界

**确定性内核、附件接入、真实小规模实验、论文与独立支撑包已跑通；实际Codex/Claude联跑、Docker隔离和完整历史比赛题比较未完成。没有“超过所有数学建模Agent”的实验结论。**

本环境 Python 3.13.5、NumPy 2.3.5、SciPy 1.17.0、numba 0.65.1，Linux x86_64，可见5个CPU；本轮配置2个并行worker、每worker 1个内部计算线程。完整环境见 environment.json。

`demo`使用28次明确标为FIXTURE_NOT_LLM的角色回执，规划、代码包和审查答复预先写好。真实执行的是算法、独立评测、统计、SVG/PDF生成及门禁。不能用fixture PASS证明Claude会判断正确。

## 2. 测试总表

| 验收项 | 真实结果 | 原始证据 |
|---|---|---|
| 新harness自动测试 | 104 passed；0 failed/error/skipped；最终复跑19.96s | harness-tests.xml / harness-tests.log |
| 附件MOSAIC测试重跑 | 38 passed，4.57s | mosaic.xml / mosaic.log |
| 原始OurWork二十模板 | 二十项空编辑字节完全一致；已计入104，不重复累加 | tests/test_ourwork.py |
| 附件文件完整性 | 408项哈希一致 | vendor-integrity.json |
| 真实数值实验 | 31个唯一单元全部DONE：21开发+10确认 | demo-confirmation.json与support/results |
| 搜索FE | 每单元192，共5952次；oracle与测试开销分开 | 实际answer.json及账本 |
| 独立精确核验 | 每次评价从1956个可行非空有序子集枚举参考前沿，并重算所有已付费目标 | 支撑包evaluate.py和evaluation.json |
| 恢复 | 再执行不增加job；31→31；步骤行、所有实验JSON及主PDF字节相同 | resume-check.json |
| 仓库外独立复现 | baseline与c0，确认seed701；原始答案和独立评测JSON逐字节一致 | independent-reproduction.json |
| 中文LaTeX | XeLaTeX两次实际编译；缺字0、未定义引用0、Overfull hbox 0 | paper/build.json与预检 |
| 页数/大小 | 160页总计；摘要1页、正文3页、其余附录；PDF 540,612 bytes | paper/preflight.json |
| 支撑包 | 221个文件，1,059,769 bytes；包括AI工具使用详情.pdf | support.zip及内置manifest |
| 安装与入口 | editable安装成功，`cumcm schema`可执行 | editable-install.log / installed-cli-schema.json |

104+38=142个实际测试结果。没有把上传包已有STATUS.json中的历史测试/1884条历史运行当成这次重跑，也没有把二十模板重复累计为额外二十个测试。

## 3. 数值试验设计与结果

问题是**合成的六任务双目标序列调度**：奖励与完成时间权衡，不是官方2026题，也不是完整历史国赛题。全部方法相同192次目标评价预算、相同公开数据、相同已付费点后处理与预先固定的代表解选择规则。

开发种子101/202/303。基准为均匀随机搜索；c0为附件fast_h0，c1为显式研究分支refit32。每个候选分别跑full、no_infill单因素消融、population16敏感性；基准3次+两候选各9次=21个开发单元。只按full主方法的开发均值选c0，消融/敏感性不混进主方法选择。

确认种子701—705事先与开发分开。仅基准和已选c0进入确认，10个单元。两种方法同一题实例，因此标记 **SEED_REPLICATION_SAME_INSTANCE**，不是独立数据集或五道赛题。

| 方法 | 归一化HV均值 | 样本标准差 |
|---|---:|---:|
| Uniform random基准 | 0.9328276047 | 0.0328803003 |
| MOSAIC-v14 fast_h0（c0） | 0.9998657358 | 0.0003002239 |

配对平均提升0.0670381310；固定5000次bootstrap得到95%百分位区间[0.0370703545, 0.0847610097]。该结论仅描述这个合成实例的这组随机重复，不是总体泛化证明。五个重复很少；随机搜索也不是当前最强优化基线。**不能由此声称胜过NSGA-II、所有多目标算法或任何完整数学建模Agent。**

真实解答、每个付费点、相同预算、独立目标重算、可行域和精确有限域检查都由评测器执行；评测器不消费算法自报的score。无效/空答案负控制必须明确判valid=false。

## 4. 本轮发现并修复的真实工程问题

1. 并行首发同一代码包时，共用staging目录有竞争。加按摘要的操作系统文件锁，补24次/8线程并发发布回归；修复后从全新工作区重跑31单元。
2. 初版中文PDF提取器存在字体映射问题，源码附录λ缺字，超长路径可能越界。换用PyMuPDF提取核验、支持字形的系统等宽字体与路径换行，重新编译而非忽略告警。
3. 独立支撑包第一次重跑发现缺少MOSAIC导入时读取的rgv2018_parameters.json。将Python运行期open读取的定制资源纳入哈希清单并打包，补资源读取/写入排除/缓存排除/字体拒绝测试，再全新重跑。最终脱离仓库目录的两个独立复现均字节一致。

这些失败没有被算作通过；最终报告只绑定修复后的新运行。Python审计事件仍不保证捕获原生库的所有I/O，因此独立包重跑是必要补充。

## 5. 论文和图像实查

所有160页实际渲染；机械检查所有页面的字词包围盒，没有发现超出外侧保护区域的文字；该检测不是完整重叠证明。人工式视觉检查通过图像查看完成：全部摘要/正文页、附录首页及13/40/80/120/160页抽查，外加OurWork全尺寸图与AI详情首页。见paper-contact-sheet.png、ai-details-first-page.png、pdf-bounds.json。**没有宣称逐页读完全部源码或由真实Codex视觉评审通过。**

主图由附件SVG/node/arrow原语生成，SVG保持矢量可编辑，Inkscape实际导出PDF/PNG。误差棒是样本标准差，不是bootstrap区间。支撑包源码/资源清单与论文附录绑定，并通过独立解压重跑。

## 6. 恢复、审计与可重复范围

重跑同一工作区不增加模型阶段调用或实验单元，既有35个接受阶段记录和31个job行保持不变，所有job JSON及主PDF哈希相同。AI详情重新编译可带不同时间戳，因此support.zip整体字节未承诺相同；输入、数值和批准范围仍相同。

哈希链最后验收为PASS，authority为LOCAL_SQLITE。它能检出篡改/误改，但不是对拥有整台主机权限的攻击者的不可篡改保证。正式运行仍需保护操作员身份、模型凭证和宿主机。

## 7. 未执行验收与下一步发布门槛

- 实际Codex与Claude CLI调用、认证、真实结构化输出及模型故障处理：NOT_RUN（当前未安装）。假CLI契约测试不等于上线验证。
- Docker镜像构建和隔离执行：NOT_RUN（当前未安装）。缺Docker时live拒绝转到本地执行。
- 正式团队主导建模/逐项人工核验：NOT_SIGNED。没有自动提交。
- 完整历史国赛题、真实扫描/复杂图示理解、四个上游同预算对战：NOT_RUN。协议见benchmarks/PROTOCOL_CN.md。
- 跨机器数值逐位一致、GPU/多机资源调度、完整EgoAgentOS生产服务连接：未声明支持或未测试。

现状是**已验证的工程基座与真实小问题闭环**；把它升级到可靠的比赛级自主系统，需要完成上述真实环境和完整题目验收，不可省略为一句“最强”。
