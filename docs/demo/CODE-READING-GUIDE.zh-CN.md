# Coding Agent 代码阅读指南

面试准备可配合阅读[完整技术手册](INTERVIEW-TECHNICAL-GUIDE.zh-CN.md)：按模块解释调用链、进程线程、上下文、Memory、会话恢复及多 Agent 管理维护，附目录、代码链接和问答。

按简历逐题练习见[面试问题与参考回答](RESUME-INTERVIEW-QA.zh-CN.md)，包括深入追问及已实现/实验/规划边界。

本指南按 Agent 的能力分组，参考 [learn-claude-code](https://github.com/shareAI-lab/learn-claude-code) 的学习顺序，帮助阅读本项目的 Python 实现。分析基于本仓库提交 `4e0a43f53aa6150d063cd45c6f7224acf80c53c5`；行号和后续代码可能变化。本项目的基础框架来自 [claude-code-from-scratch](https://github.com/Windy3f3f3f3f/claude-code-from-scratch)，上游基线为 `0b452360866433fde0dc77cd37ada9d303546592`。

先读一条完整链路，再读扩展功能和改动。`agent.py` 较长，不必从头逐行阅读。

```text
用户输入 → 创建或调用 Agent → 模型返回文本 / 工具调用
         → 参数与权限处理 → 工具执行 → 结果进入消息历史
         → 再次调用模型 → 完成或达到执行限制
```

## 一、按模块阅读

| 顺序 | 模块 | 代码入口 | 阅读重点 |
| --- | --- | --- | --- |
| 1 | 启动入口 | [__main__.py：main](../../python/mini_claude/__main__.py#L229) | 命令行参数怎样进入 Agent，用户输入怎样进入 `chat()`。 |
| 2 | Agent Loop | [Agent](../../python/mini_claude/agent.py#L184)、[chat](../../python/mini_claude/agent.py#L453)、[OpenAI 循环](../../python/mini_claude/agent.py#L1848) | 模型如何发出工具调用，工具结果怎样返回模型，循环如何停止。代码还支持 Anthropic 调用路径。 |
| 3 | 工具与分发 | [工具定义](../../python/mini_claude/tools.py#L39)、[执行入口](../../python/mini_claude/tools.py#L670)、[Agent 工具调用](../../python/mini_claude/agent.py#L1307) | 工具名称、参数定义与具体函数的对应关系；读取、编辑和 Shell 的不同作用。 |
| 4 | 权限与规划 | [权限检查](../../python/mini_claude/tools.py#L589)、[Plan 模式](../../python/mini_claude/agent.py#L1387) | 什么时候检查权限，规划模式如何限制工具，审批后如何切换执行。 |
| 5 | Skills | [skills.py](../../python/mini_claude/skills.py#L33) | 技能文件如何发现、加载、展开参数并交给 Agent。 |
| 6 | MCP | [mcp_client.py](../../python/mini_claude/mcp_client.py#L147) | 怎样连接 MCP 服务、发现外部工具、路由并调用。 |
| 7 | 子 Agent | [角色配置](../../python/mini_claude/subagent.py#L123)、[执行入口](../../python/mini_claude/agent.py#L1496) | 主 Agent 如何委派，子 Agent 如何获得独立角色提示、上下文和工具集合。 |
| 8 | 上下文压缩 | [压缩入口](../../python/mini_claude/agent.py#L1041)、[结构化摘要](../../python/mini_claude/context_summary.py#L54) | 何时压缩；历史归档、近期交互保留、摘要校验和回退怎样配合。 |
| 9 | Memory | [memory.py](../../python/mini_claude/memory.py#L70)、[记忆注入](../../python/mini_claude/agent.py#L1537) | 记忆怎样保存、选择和注入；长期记忆与当前会话历史有什么区别。 |
| 10 | 会话与执行恢复 | [session.py](../../python/mini_claude/session.py#L42)、[execution_journal.py](../../python/mini_claude/execution_journal.py#L37)、[session_lock.py](../../python/mini_claude/session_lock.py) | 会话保存什么；工具调用的开始、完成和结果未知如何区分，以及恢复时如何处理。 |
| 11 | 命令生命周期 | [command_runner.py](../../python/mini_claude/command_runner.py#L73) | 怎样增量读取输出，超时、取消时怎样处理进程组。 |
| 12 | 协议与评测 | [tool_protocol.py](../../python/mini_claude/tool_protocol.py)、[评测 worker](../../benchmarks/paired-v2/worker.py) | 非法工具调用如何保留记录并继续对话；评测如何指定提示词、模型和工具。 |

### 建议亲自跟踪的调用

1. 从 [chat()](../../python/mini_claude/agent.py#L453) 进入 [OpenAI 循环](../../python/mini_claude/agent.py#L1848)，找出模型请求与返回工具调用的位置。
2. 跟踪一次 `read_file`：从 [_execute_tool_call()](../../python/mini_claude/agent.py#L1307) 到工具执行，再看结果如何加入消息。
3. 跟踪一次 `write_file`：查看 [执行日志](../../python/mini_claude/execution_journal.py#L117) 如何记录开始与完成，再思考中断发生在两者之间时的恢复行为。
4. 跟踪一次 Shell 超时：从 [Shell 工具](../../python/mini_claude/tools.py#L436) 到 [命令运行器](../../python/mini_claude/command_runner.py#L73)，观察输出和进程清理。
5. 查看 [结构化压缩](../../python/mini_claude/agent.py#L1055)：比较摘要成功和校验失败时如何处理历史。

## 二、与 learn-claude-code 章节对照

这是按功能建立的阅读地图，不代表两套项目的行为和完成范围相同。

| 学习主题 | 本项目对应 | 范围说明 |
| --- | --- | --- |
| Agent Loop / Tool Use | `agent.py`、`tools.py` | 主体来自 claude-code-from-scratch。 |
| Permission | `tools.py`、`agent.py` | 有工具权限检查和 Plan 模式。 |
| Hooks | `autonomy.py`、`agent.py` | 有 `/goal` 的 Stop-hook 式逻辑；不等同于完整通用 Hooks 系统。 |
| Todo / Task System | `agent.py`、`session.py`、`autonomy.py` | 有会话和目标相关机制；不能直接等同于 learn-claude-code 的持久化任务系统。 |
| Subagent | `subagent.py`、`agent.py` | 主 Agent 委派，子 Agent 按角色使用对应工具。 |
| Skill Loading | `skills.py` | 发现并加载技能。 |
| Context Compact | `agent.py`、`context_summary.py` | 上游已有压缩流程；本次增加结构化摘要和回退。 |
| Memory | `memory.py` | 有持久记忆选择和注入；60 题评测中关闭长期 Memory。 |
| Background Tasks / Scheduler | `autonomy.py`、`agent.py` | 有会话内 `/loop` 等调度逻辑；不等同于完整后台任务平台。 |
| Agent Teams | `subagent.py`、`agent.py` | 目前重点是主 Agent 委派子 Agent，不应直接称为完整平级 Agent Teams。 |

了解两个参考项目的阅读方式也可以看[教程导航与上游关系](TUTORIALS.md)。

## 三、相对上游改了什么

Agent Loop、MCP、Skills、Memory 和子 Agent 等主体来自 claude-code-from-scratch。我们没有从零重写整个框架；learn-claude-code 用于学习、比较设计和参考工作流日志思路，并非把两套框架完整拼接。

| 部分 | 上游基础 | 本次重点改动 |
| --- | --- | --- |
| Agent 与工具 | 已有主循环、工具、权限与多轮反馈 | 在现有链路接入恢复、压缩、本地预算及协议处理。 |
| 会话与执行恢复 | 已有会话能力 | 增加原子会话保存、锁及工具执行日志；区分完成和结果未知。 |
| Shell | 已有 Shell 工具 | 增加命令运行器，处理增量输出、超时、取消和进程组清理。 |
| 上下文 | 已有历史压缩 | 增加结构化摘要、校验、近期工具交互保留和失败回退。 |
| 工具协议 | 已有工具调用解析 | 对非法参数调用的历史进行受控处理，保留记录并避免非法 JSON 再次导致请求中断。 |
| MCP / Skills / 子 Agent | 已有主体实现 | 主要复用，不能说是本次从零实现。 |
| Memory | 已有记忆能力 | 本次修改很少；小预算按需历史方案仍待实现和验证。 |
| 测试与评测 | 有上游测试基础 | 增加恢复、命令、摘要、协议测试和 60 题评测适配器。 |

以 `0b45236` 到 `4e0a43f` 的 `python/` 差异计算，共 19 个文件、增加 1,713 行、删除 116 行；统计包含测试和示例，不等同于核心功能代码量。[查看 GitHub 差异](https://github.com/minglmtx/Agent/compare/0b452360866433fde0dc77cd37ada9d303546592...4e0a43f53aa6150d063cd45c6f7224acf80c53c5)。

面试时可以这样说明：基于既有 Python Agent 框架，重点补充工具执行状态与中断恢复、命令生命周期管理和结构化上下文压缩，再用故障测试及编码任务对照检查效果。MCP、Skills、Memory 和子 Agent 属于上游已有能力，主要进行复用。

## 四、如何查看差异和验证结果

在自己的仓库根目录执行：

```bash
git diff --stat 0b45236 4e0a43f -- python
git diff 0b45236 4e0a43f -- python/mini_claude/agent.py
git show 4e0a43f:python/mini_claude/execution_journal.py
```

对应回归测试位于 [python/tests](../../python/tests)。例如，恢复看 `test_recovery.py` 和 `test_agent_recovery_integration.py`，命令处理看 `test_command_runner.py`，摘要看 `test_context_summary.py` 和 `test_summary_integration.py`，协议处理看 `test_tool_protocol.py`。

60 题的“改版＋旧提示词”配置见 [paired-v2 说明](../../benchmarks/paired-v2/README.txt)：改版 24/60，原版 18/60；这是一次固定开发题集评测，改版总 Token 更高。评测入口单独指定旧提示词，普通 CLI 使用项目默认提示词；评测时关闭长期 Memory 和 MCP，不能由成绩推断这些能力的效果。
