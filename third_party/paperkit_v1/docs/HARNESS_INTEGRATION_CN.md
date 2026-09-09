# 对接 mythrise/math_harness

## 已核对的真实接口

远程读取了 `cumcm_harness/controller.py`、`paper.py` 和仓库 README。当前论文流程由 controller 调用：

```python
build_paper(root, draft, claims, rows,
            ai_records=records, code_bundles=bundles,
            source_registry=sources, demo=demo)
build_ai_details(folder, records, human, demo=demo)
```

结果依赖 `paper_sha256`、`preflight.pages`、`preflight.body_pages` 和 source inventory；其后仍经过 PDF 图像审查、release 签核和 `package_workspace`。本包保持这些接口和字段，不接管求解、文献检索、审批或支撑包生成。

被核对的 `paper.py` Git blob：`2e3043de9325704e484351cf400f8df7e8be3815`。这是一份文件的 Git blob，不是整个仓库的 commit SHA。安装器精确匹配该文件；更新后的未知版本不会强行打补丁。

来源：
- https://github.com/mythrise/math_harness/blob/main/cumcm_harness/paper.py
- https://github.com/mythrise/math_harness/blob/main/cumcm_harness/controller.py
- https://github.com/mythrise/math_harness/blob/main/README.md

## 实际改动范围

只改一份宿主文件 `cumcm_harness/paper.py`：把它当前“本研究使用了人工智能工具……”的概述句改成 2026 官方声明句式，保留原先列出的真实用途；再在模块末尾追加经过指纹固定的适配器入口。模板预导言采用修订版 PaperKit，编译后追加版式检查；原 preflight 的失败不会被覆盖成成功。

以下全部保留：`claim_registry`、`bind_prose`、数学命令白名单、验证过的参考文献、全部源码收集、构建回执、原返回结构、controller 锁/step、人工 plan/release、HMAC、AI 真实调用记录、原 packaging。演示分支也不改成真实竞赛使用声明。

外部包的 Python 源码与 LaTeX 样式共同计算 `profile_digest`，安装时把该值写进 `paper.py` 的 hook。之后更新外部包会阻塞而不是悄悄复用旧证据；编译前还会复检同一指纹。宿主自身的源码指纹机制继续生效。

## 安装

将整个解压目录放在稳定位置，不要安装后删除。使用 Harness 实际运行的那个 Python 环境安装本包：

```bash
/path/to/math_harness/.venv/bin/python -m pip install --no-build-isolation \
  -e /absolute/path/CUMCM2026_PaperKit_Harness

# 只检查，不写文件
/path/to/math_harness/.venv/bin/python -m cumcm2026 install-harness \
  --root /absolute/path/math_harness

# 核对 dry-run 后显式安装
/path/to/math_harness/.venv/bin/python -m cumcm2026 install-harness \
  --root /absolute/path/math_harness --apply

/path/to/math_harness/.venv/bin/python -m cumcm2026 doctor
```

真实的全局配置使用固定键集合，**不要自行加 `paperkit` 等未知键到它原来的 config.json**。该适配器不需要修改那些配置，更不会复制 Exa/模型凭证。

备份放在 `.paperkit-backups/<original-blob>/`，含原始文件和安装回执。安装之后必须创建一个新的工作区，运行宿主现有自测与它自己的工程演示，再做真实服务验收。不要在已冻结工作区里手改 fingerprint 或删除数据库来继续。

```bash
cd /absolute/path/math_harness
./.venv/bin/python -m pytest -q
# 使用原仓库现有的自测流程。下面是原有工程演示，不是真实多模型赛题验收：
./.venv/bin/python -m cumcm_harness.resilience_demo workspaces/paperkit-demo-NEW
# 正式任务仍用原先 init/run/approve；新建一个工作区。
```

本包没有在你的远程宿主机器执行这些命令，也没有运行真实 Codex/Claude/Exa 完整赛题。已执行的是本包本地测试、真实 XeLaTeX 编译和适配器的隔离接口测试。请勿把后者当成宿主端到端回归。

如果宿主 `paper.py` 已更新，安装器输出 expected/observed 哈希后停止。由 Codex 按 `docs/CODEX_HANDOFF_CN.md` 复核新接口并更新适配器；不要删除哈希保护来强装。

## 卸载

```bash
/path/to/math_harness/.venv/bin/python -m cumcm2026 uninstall-harness \
  --root /absolute/path/math_harness
```

只有已安装文件仍与安装回执完全一致才恢复，防止覆盖后来的开发。恢复后也需新的工作区。

## 其他 Harness：独立进程接口

不依赖 `mythrise/math_harness` 的调用方可使用 JSON+CLI：

```python
import json
import subprocess
import sys
from pathlib import Path

project = Path('/path/to/paper_project')
output = Path('/path/to/new_candidate')
proc = subprocess.run(
    [sys.executable, '-m', 'cumcm2026', 'build',
     '--project', str(project), '--out', str(output)],
    capture_output=True, text=True, timeout=900, check=False,
)
report = json.loads(proc.stdout)
if proc.returncode != 0:
    raise RuntimeError(report)
# 只允许进入人工复核，绝不把这里的 0 退出码当作自动发布批准。
assert report['release_ready'] is False
```

返回码 0：当前命令完成；2：BLOCKED。独立版运行结果是候选件，`release` 仍要求与同一 bundle_digest 绑定的人工声明。不要在宿主 controller 已冻结 PDF 后再用独立版替换 PDF；这会使宿主哈希与签核失效。
