# 操作、复现与故障处置

## 环境与认证

采用源码 editable install；Python环境版本以 reports/environment.json 为本次实际值，Dockerfile 的 Python3.11 构建尚未在本环境验证。安装包只是一个普通发行 wheel 不会自动带上105MB的参考资产，所以不要把 `pip install .` 的非editable结果视为独立便携安装。

Claude CLI 使用 `--safe-mode --setting-sources user`，复用本机 CLI 的用户级认证、服务地址及模型设置。harness 不复制、转换或保存账户凭证；内置工具与 MCP 仍禁用，自定义插件和 hooks 不参与调用。API Key、用户登录或既有代理令牌由 CLI 自行处理，认证状态正常不代表上游模型服务可用。Codex 同样必须先有有效官方 CLI 认证。模型默认值没有伪造固定最新名称；可在 init 前配置明确模型ID。`doctor --live` 只探测可执行文件、旗标和镜像，不测试真实模型质量或承诺计费成功。本机后续容器实测见 `reports/live-configuration/STATUS.md`。

当前 shell 代理环境会用于模型服务连接；求解容器禁网。操作员必须确保 API endpoint 可信。原始模型日志可能含题目和数据，不属于可直接公开的产物；公开包只放去路径的必要回执。没有对日志做完整敏感数据脱敏的安全证明。

## 恢复

```
python -m cumcm_harness status WORKSPACE
python -m cumcm_harness audit WORKSPACE
python -m cumcm_harness run WORKSPACE
```

完整单元只校验并复用；如果某外部CLI调用中断，不知道是否已收费，不能直接重试。核查操作系统/容器/服务账单，停止相应外部进程后：

```
python -m cumcm_harness recover-step WORKSPACE STEP_KEY \
  --reason 'Operator verified external process has stopped and billing is reconciled' \
  --external-process-stopped
python -m cumcm_harness recover-job WORKSPACE JOB_ID \
  --reason 'Operator inspected and preserved the incomplete previous attempt' \
  --external-process-stopped
```

`--external-process-stopped` 是操作员明确声明，不是系统自动证明。不要为刷新结果恢复已DONE任务。修改核心源码、算法供应树、环境、输入、协议后应新建工作区；不能把旧结果悄悄挂在新算法名下。

## 支撑包独立复现

解压生成的 support.zip 到空目录，先核实和审阅源码，在隔离的Python环境安装所需数值库后：

```
python reproduce.py --trust-reviewed-code --candidate baseline --out rerun-baseline
python reproduce.py --trust-reviewed-code --candidate c0 --variant full --out rerun-c0
```

不需要模型或Claude/Codex。脚本检查 manifest、输入哈希和冻结种子，再执行求解器与独立评测器。不要在原目录修改已发布源文件。参数 `--original-input` 用于原始比赛附件被有意省略的情况；必须逐文件匹配原输入哈希。

## 成本与资源

配置限制总模型调用次数、Claude单次美元预算、候选数、修复次数、单任务时长与总CPU/内存。Claude账单回执是客户端估计，不能等同最终账单。Codex没有跨订阅/API通用的精确美元硬上限，本实现只做调用次数与超时控制，不宣称可以精确保证总花费。

默认2个实验worker，各1线程，适合先跑通。若机器有144核，不应盲目启144个外层任务；先根据每cell内存与CPU测量调整总预算。长cell要求在问题适配器内实现分片/checkpoint；本版不会自动拆解任意Python函数。GPU任务需要另行实现受审查的GPU分配适配器。

## 已知能力边界

真实CLI+Docker没有在本环境联测；没有历史完整赛题benchmark；在线论文搜索没有内置自动执行，采用人工核验的本地文献库；一般约束优化、新codec、跨机GPU队列不自动支持；日志和人工HMAC不是对恶意管理员的密码学隔离；图表/正文真实性仍需要真实审查员和团队判断。遇到这些边界应生成明确阻塞与下一步条件，而不是换成演示模式发布。
