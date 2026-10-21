> 本文件是 Alex 集群初次实验记录，含历史绝对路径。发布版使用方式以 [README](README.md) 和 [运行手册](docs/demo/RUNBOOK.md) 为准。

# Python Coding Agent 小型工程 Demo

本项目基于 [claude-code-from-scratch](https://github.com/Windy3f3f3f3f/claude-code-from-scratch) 的 Python 版本进行复现与二次开发，面向代码阅读、文件编辑和测试执行。只维护 Python 改动；仓库原有 TypeScript 文件不是本次改造对象。

上游基线提交：`0b452360866433fde0dc77cd37ada9d303546592`。

这是用于演示与工程验证的小型项目，不是 Claude Code 官方实现，也不宣称与其内部架构相同。本地 Qwen3-8B 接入由独立启动脚本提供；真实 GPU 运行和编码任务成绩须以输出报告为准，不能由单元测试通过推断。

## 本次改造与上游能力的区别

上游已经提供 Agent 主循环、工具调用、权限模式、会话、上下文压缩、Skills、子 Agent 与 MCP 等能力。本次个人工程改动聚焦以下三项：

| 改进 | 实现位置 | 行为 |
| --- | --- | --- |
| 会话与工具执行恢复 | `python/mini_claude/session.py`、`execution_journal.py` | 会话临时文件写入后原子替换；工具调用以稳定 ID 和参数摘要记账，记录开始、完成、结果未知及人工确认 |
| 命令执行生命周期 | `python/mini_claude/command_runner.py`、`tools.py` | 输出流式读取、有限日志、超时与取消、进程组清理、结构化状态返回 |
| 结构化上下文摘要 | `python/mini_claude/context_summary.py`、`agent.py` | 摘要区分目标、约束、文件修改、测试及待办；保留近期完整交互；校验失败保留旧历史 |

恢复设计借鉴 [learn-claude-code 的工作流日志思路](https://github.com/shareAI-lab/learn-claude-code/blob/main/s16_workflow_runtime/code.py)，接入当前 Python 主循环，没有引入第二套 Agent 运行框架。执行日志以工具调用 ID 为边界，不是按相似提示词缓存模型结果。

## 本地模型与目录

模型使用已下载的 Qwen3-8B，由 vLLM 提供本地 OpenAI 兼容接口。摘要请求复用相同本地服务，不需要另一个付费 Judge。工具调用解析与真实编码能力仍需小规模实测。

将运行状态放到 ATUIN：

```bash
export MINI_CLAUDE_STATE_DIR=/home/atuin/r102bf/r102bf10/lmtx/outputs/coding-agent-demo/state
```

状态目录用于会话、执行日志、命令日志及归档。没有设置时优先使用 `$ATUIN/coding-agent-demo-state`，再回退到 `~/.mini-claude`。在集群上应显式设置 ATUIN 路径，模型推理只在获批 GPU 资源中运行。

启动入口由以下文件提供：

- `scripts/serve-qwen.sh`：启动本地模型服务。
- `scripts/run-local.sh`：连接服务运行 Python Agent。
- `cluster/demo-smoke.sbatch`：集群 GPU 小规模验证入口。
- `scripts/run_demo_tasks.py`：小型任务集运行及结果记录。

请先查看脚本说明和 `--help`，确认本地模型路径、服务地址、资源与输出目录。Qwen3-8B 的首次 GPU 验证已完成，开发题 1/3 通过；详见 [实测记录](reports/RESULTS.zh-CN.md)。不要填入 OpenRouter 或其他付费服务凭据来运行本 Demo。

## CPU 验证

在仓库根目录运行：

```bash
source scripts/local-env.sh
"$DEMO_PYTHON" -m unittest discover -s python/tests -p 'test_*.py' -v
```

安装了项目依赖的 Python 环境可运行完整测试集。需要只验证命令运行器时：

```bash
"$DEMO_PYTHON" python/tests/test_command_runner.py -v
```

测试不调用真实模型；使用临时目录、短命令、模拟模型响应和故障注入，检查：

- 保存中断、损坏记录、恢复后已完成调用复用、未知执行拦截。
- 命令退出前产生输出、超时保留日志、主动取消、子进程清理。
- 输出与日志大小限制、非零退出码以及 UI 回调失败不影响清理。
- 摘要字段与状态枚举、完整工具调用/结果配对、失败回退。

## 中断后恢复

会话记录与执行日志是两种状态：前者保存对话，后者保存每次工具调用的开始与结果。已完成且结果持久化的同一调用可以复用；已经开始但没有完成记录的调用可能执行过副作用，恢复时必须停下来核查。

恢复用法：

```bash
bash scripts/run-local.sh --resume-id SESSION_ID
```

若提示存在未知执行，先查看本地文件、Git diff、输出产物及命令日志。确认实际状态后，再用带说明的恢复入口：

```bash
bash scripts/run-local.sh --resume-id SESSION_ID \
  --ack-unknown '已检查具体文件与测试结果：说明实际发生了什么，以及尚未确认的部分'
```

`--ack-unknown` 是对实际核查结果的记录，不代表该操作成功，也不会将原调用自动重新执行。不要为了消除提示随意确认。

## 在 Alex 上运行

专用环境：`/home/atuin/r102bf/r102bf10/lmtx/environments/coding-agent-demo`。
它通过 `--system-site-packages` 复用已有 `lab-skill` 的 PyTorch；新增依赖只装在专用环境中，
未升级原实验环境。不要单独移动或删除其基础环境。

```bash
cd /home/atuin/r102bf/r102bf10/lmtx/coding-agent-demo
sbatch cluster/demo-smoke.sbatch
```

申请一张 A40，最多 45 分钟；模型启动最多等待 10 分钟。启动一次模型服务，
用 2 路并行运行 3 个开发题，每题一次尝试，最长 10 分钟。
结果保存在 `/home/atuin/r102bf/r102bf10/lmtx/outputs/coding-agent-demo/gpu-JOBID/`。
`server.log` 是服务日志，`tasks/summary.json` 是任务结果；
每题有 `transcript.json`、`run.log` 和 `result.json`，可直接在 VS Code 查看。
验收集不在本次开发验证中运行。

收尾验证使用同一入口的 `final` 模式：

```bash
sbatch --partition=a100 --job-name=coding-demo-final cluster/demo-smoke.sbatch final
```

运行三道保留题，再复用模型服务生成两组摘要对照（四次本地请求）。编码任务与摘要请求各自最多两路并行。摘要结果位于 `summary-check/`，源历史和预先定义的检查清单保存在 `cases.json`。

已有 GPU allocation、模型服务已启动时，可以在同一节点运行：

```bash
bash scripts/run-local.sh --accept-edits '读取当前项目，修复问题并运行测试'
```

请先进入专用实验工作目录。不要在登录节点启动模型服务。
`scripts/local-env.sh` 将模型地址设为回环本地接口、禁用 thinking 与持久记忆召回
（便于任务隔离），上下文为 16,384、输出上限 2,048 tokens。
摘要的模型用量也会计入会话统计；本地显示的零美元只表示未产生 API 账单，
不表示 GPU 配额免费。

即使使用原子写入和执行日志，仍存在“外部操作已完成、结果尚未写入日志时崩溃”的窗口；本实现不保证任意命令恰好执行一次，也不提供通用事务回滚。

## 小规模评估口径

采用小型自建 Python 任务集，开发题和最终验收题分开。模型、初始代码、工具权限和调用预算一致时再比较上游与改进版；模型说完成不算成功，以独立测试和文件范围检查为准。

报告至少区分：

| 维度 | 检查内容 |
| --- | --- |
| 编码任务 | 验收测试是否通过、是否越界修改、耗时与调用量 |
| 恢复 | 已完成调用是否重复执行、未知状态是否拦截、能否恢复继续 |
| 命令 | 首次输出、超时日志、取消延迟、残留进程 |
| 摘要 | 关键事实保留、是否捏造成功、压缩前后 Token，以及摘要请求成本 |

摘要 JSON 校验只证明结构符合约定，不能证明事实正确。少量长任务历史应对照预先标注的事实人工核查，保留原始归档以便追溯。不依据几道任务宣称通用编码能力达到某个公开 benchmark 水平。

## 实现边界

- 当前命令管理面向 Linux/POSIX。Shell 在独立进程组中执行，超时/取消先 TERM 再 KILL；正常结束也清理同组后台进程。主动 `setsid` 脱离进程组的程序不在清理保证内。
- 每次命令的返回与 UI 输出默认最多 32 KB，私有磁盘日志默认最多 2 MB。超出部分继续读取但不保留，不会无限占用内存或磁盘。
- 日志文件权限为 0600；命令输出仍可能包含用户打印的敏感信息，应作为私有本地文件管理。
- Shell 命令拥有运行账号的真实权限。权限确认、允许列表与进程组不是容器或安全沙箱。仅在可丢弃的练习仓库中运行模型生成的修改与命令。
- 多个 CLI 同时恢复同一个会话不在当前 Demo 的并发使用范围内。
- 命令清理、格式校验和状态恢复测试通过，不意味着模型会正确修改代码；实际成绩与失败归因以实测记录为准。
