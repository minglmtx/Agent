# Python Coding Agent：执行可靠性与上下文管理 Demo

基于 `claude-code-from-scratch` 的 **Python 实现**复现并二次开发，使用本地 Qwen3-8B 完成模型决策、工具调用、文件编辑和测试反馈循环。改造重点是工具执行恢复、Shell 生命周期和结构化上下文摘要。

这是小型工程演示，不是 Claude Code 官方实现。上游已有 Agent Loop、MCP、Skills、多 Agent 等模块；本次没有把这些上游功能算作个人新增贡献，也没有验证全部上游功能。

## 我们新增了什么

| 改造 | 解决的问题 | 实现 |
| --- | --- | --- |
| 原子会话保存与执行日志 | 中断后会话损坏、工具是否执行不明确 | 临时文件 + fsync + 原子替换；调用 ID、参数摘要、开始/完成/未知状态；同会话文件锁 |
| 可取消的命令运行器 | 等命令结束才看到输出、超时丢日志、后台子进程残留 | 增量读取 stdout/stderr、超时与取消、TERM→KILL、有限输出与日志 |
| 结构化上下文摘要 | 摘要漏约束、混淆已做和待做、切断工具调用配对 | 固定 JSON 字段、保留近期完整交互、格式失败回退、历史归档 |
| 小规模可复查评估 | 模型说完成不等于功能正确 | 独立验收、隔离工作目录、停止原因与业务结果分开记录 |

## 快速开始：CPU 验证，不需要模型

Linux/POSIX、Python 3.11+。Shell 清理与文件锁使用 POSIX 接口，Windows 原生运行不在本次验证范围内。

```bash
git clone --branch feat/python-coding-agent-reliability-demo \
  https://github.com/minglmtx/Agent.git
cd Agent
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-demo.txt
source scripts/local-env.sh
"$DEMO_PYTHON" -m unittest discover -s python/tests -p 'test_*.py' -v
"$DEMO_PYTHON" scripts/run_demo_tasks.py --verify-fixtures
```

CPU 检查使用模拟模型、临时文件和短命令，无需 API Key 或 GPU。六道任务的初始代码均不能通过对应验收，参考实现均通过。

## 本地 Qwen3-8B

需要 NVIDIA GPU、兼容的驱动/PyTorch/vLLM，以及提前下载的模型权重。本次 GPU 实测使用 A100；环境版本见 [dependencies.json](reports/dependencies.json)。版本记录不代表在任意 GPU/驱动上均可直接安装。

```bash
# 在获批的 GPU 资源内安装/启动；不要在集群登录节点启动模型。
python -m pip install 'vllm==0.10.2'
export DEMO_MODEL_PATH=/absolute/path/to/Qwen3-8B
export DEMO_STORAGE=/absolute/path/to/demo-storage
bash scripts/serve-qwen.sh
```

另一个终端使用同一配置，在可丢弃的练习目录中运行：

```bash
export DEMO_MODEL_PATH=/absolute/path/to/Qwen3-8B
export DEMO_STORAGE=/absolute/path/to/demo-storage
cd /path/to/disposable-workspace
bash /path/to/Agent/scripts/run-local.sh --accept-edits \
  '读取项目，修复问题并运行测试'
```

本地服务只监听 `127.0.0.1:8020`；无需 OpenRouter token。启动配置禁用 thinking，上下文 16,384 tokens，输出上限 2,048，最多两个并发请求。模型会真实执行工具，练习目录不是安全沙箱。

集群配置、恢复、排障和完整参数见 [运行手册](docs/demo/RUNBOOK.md)。

## 实际验证结果

| 项目 | 结果 |
| --- | --- |
| CPU 检查 | 42 项通过（包含上游测试，不是 42 道编码题） |
| 开发题，作业 4624227 | 1/3 通过；A100 作业总耗时 3 分 34 秒 |
| 保留题，作业 4624477 | 0/3 通过；作业总耗时 2 分 52 秒，含摘要检查 |
| 结构化摘要 | 两例 JSON 格式通过；一例将失败测试写为 attempted，错误内容仍保留 |
| 付费 API | 0 次；GPU 仍消耗集群资源 |

模型失败包括漏实现 CLI 参数、重复提交匹配不到的编辑、生成错误代码，以及只说要修改却不再执行。本项目**没有证明编码成功率提升**。两例摘要中结构化输出合计 354 tokens，原版段落 200 tokens，**没有证明降低 Token 消耗**。

详情：[评估方法与结果](docs/demo/EVALUATION.md) · [实测报告](reports/RESULTS.zh-CN.md) · [可移植证据摘要](reports/evaluation-summary.json)

## 技术文档与教程

建议按顺序阅读：

1. [教程导航与上游关系](docs/demo/TUTORIALS.md)：两个参考项目怎么读，本项目新增内容在哪里。
2. [架构与关键设计](docs/demo/ARCHITECTURE.md)：主循环、执行状态、取消、压缩和设计边界。
3. [运行手册](docs/demo/RUNBOOK.md)：环境、Slurm、恢复命令、产物与排错。
4. [演示指南](docs/demo/DEMO.md)：几分钟展示工程能力，无需扩大评测集。
5. [评估说明](docs/demo/EVALUATION.md)：任务定义、验收口径、实际结果和限制。

保留了第一个项目的 [原始 README](README-UPSTREAM.md)、[中文教程](docs/00-introduction.md)、[英文教程](en/docs/00-introduction.md) 和逐章 `steps/`。原始教程涉及 TypeScript 的部分仍属于上游材料，本分支的改造仅在 Python。第二个项目通过 [learn-claude-code](https://github.com/shareAI-lab/learn-claude-code) 链接阅读，没有复制其完整实现。

## 目录

```text
python/mini_claude/    Python Agent 与本次改造
python/tests/          CPU 回归与故障注入
python/demo_tasks.py   六道自建任务与独立验收器
scripts/               本地模型、任务与摘要比较入口
cluster/               Slurm GPU 作业入口
docs/demo/             本分支技术文档
docs/、en/、steps/      保留的上游教程
reports/               实测摘要、环境与已知限制
```

## 来源与许可证

主代码基于 [Windy3f3f3f3f/claude-code-from-scratch](https://github.com/Windy3f3f3f3f/claude-code-from-scratch)，基线提交 `0b452360866433fde0dc77cd37ada9d303546592`。恢复思路参考 [shareAI-lab/learn-claude-code](https://github.com/shareAI-lab/learn-claude-code) 的工作流运行时教程。本分支保留上游历史与 [MIT LICENSE](LICENSE)，详见 [来源说明](NOTICE.md)。
