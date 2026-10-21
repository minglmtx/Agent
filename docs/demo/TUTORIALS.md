# 教程导航：从上游到本分支

## 第一部分：理解原有 Agent

主代码固定于 claude-code-from-scratch 的 `0b452360866433fde0dc77cd37ada9d303546592`，保留了原教程和许可证。

| 阅读目标 | 保留的教程 | 再看本分支代码 |
| --- | --- | --- |
| Agent 循环 | [01-agent-loop](../01-agent-loop.md) | python/mini_claude/agent.py |
| 工具与反馈 | [02-tools](../02-tools.md) | tools.py、command_runner.py |
| 会话与 CLI | [04-cli-session](../04-cli-session.md) | session.py、execution_journal.py、__main__.py |
| 模型流式响应 | [05-streaming](../05-streaming.md) | agent.py；与 Shell 流式输出区分 |
| 上下文 | [07-context](../07-context.md) | context_summary.py |
| 测试 | [14-testing](../14-testing.md) | python/tests、demo_tasks.py |

完整入口：[原始 README](../../README-UPSTREAM.md)、[英文教程](../../en/docs/00-introduction.md)、[逐章代码](../../steps/README.md)。TypeScript 文件与原始教程继续保留，但不属于本轮 Python 改造和验收范围。仓库中的旧 demo.mp4 也是上游演示，不是本次成果录像。

## 第二部分：参考 learn-claude-code

参考仓库：https://github.com/shareAI-lab/learn-claude-code

建议阅读其 Agent 循环、上下文压缩和 [工作流运行时](https://github.com/shareAI-lab/learn-claude-code/tree/main/s16_workflow_runtime)；中文入口为该仓库 README-zh.md。链接指向上游当前分支，内容可能变化；本项目没有把它安装为依赖，也没有复制其整套代码。

把参考思路落实到本项目时，重点回答：

- 聊天消息保存与外部工具完成记录有什么不同？
- 如何识别“开始了，但不知道有没有执行完”？
- 为什么不能在恢复时直接重试写文件或 Shell？
- 固定调用 ID 的结果复用，为什么不等于整个任务 exactly-once？

本分支以现有 Python Agent 为唯一运行框架，通过 execution_journal.py 和 session_lock.py 接入，不维护两套 Agent。

## 第三部分：我们的补充教程

依次阅读 [架构](ARCHITECTURE.md)、[运行手册](RUNBOOK.md)、[演示](DEMO.md)、[评估](EVALUATION.md)。推荐亲自断点跟踪：

1. 一次 read_file 从模型 tool_call 到结果回传。
2. write_file 前的会话保存和 begin，完成后的 complete。
3. run_shell 超时后如何读完已有输出、清理进程并返回状态。
4. 摘要失败时为何保留旧历史，成功时如何保留近期工具配对。

面试可用代码和结果解释取舍，不把上游所有模块都说成自己实现，也不把本地模型能发工具调用等同于任务成功。
