# 已验证工程运行快照

本目录是最终演示运行的发布证据，不是完整控制工作区，不能直接传给run/demo恢复。
规划、角色答复和审查是预先写好的fixture；31个数值实验单元及独立评测实际执行。
没有真实Codex/Claude调用，没有Docker实测，没有历史国赛完整题比较。

从源码运行新demo可以复现流程。独立支撑包复现：解压deliverables/support.zip，
在已安装报告所列数值依赖的隔离Python环境执行reproduce.py --trust-reviewed-code。
两个候选种子701的独立重跑与原答案/评测JSON字节完全一致，见reports记录。

paper/main.tex可用XeLaTeX编译；paper/code与figures是完整相对依赖。
论文160页中正文3页，长附录是完整定制源码及支撑清单；不是160页正文。
