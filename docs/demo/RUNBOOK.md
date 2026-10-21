# 运行与排障手册

## 安装与环境

从根 README 安装 `requirements-demo.txt`；CPU 测试无需 vLLM。模型服务另装 vLLM，实测版本为 0.10.2、PyTorch 2.8.0+cu126。模型目录应已包含 tokenizer、配置和权重；脚本启用离线加载，不会自动下载模型。

所有示例在仓库根目录运行，除明确要求进入练习目录的命令。配置不会自动读取 `.env`；请通过 export 设置。

| 变量 | 默认值 / 用途 |
| --- | --- |
| DEMO_STORAGE | 仓库内 .demo-runtime；运行产物与缓存根目录，已被 gitignore 排除 |
| DEMO_PYTHON | 仓库 .venv/bin/python 存在则使用，否则 python3；可显式指定绝对路径 |
| DEMO_MODEL_PATH | DEMO_STORAGE/models/Qwen3-8B |
| DEMO_PORT | 服务启动端口 8020 |
| DEMO_API_BASE | 客户端地址 http://127.0.0.1:8020/v1；改端口需同步设置 |
| MINI_CLAUDE_STATE_DIR | DEMO_STORAGE/outputs/coding-agent-demo/state |
| MINI_CLAUDE_MODEL | qwen3-8b-local，客户端和服务端必须一致 |

`local-env.sh` 固定本次实验的本地模式、16,384 上下文、2,048 输出、零 SDK 重试、关闭持久记忆召回与 thinking。它设置本地占位 key 并清除 Anthropic key/base 环境变量，不接入付费服务。脚本没有改写 HOME。

## Alex 集群现有环境

当前机器已有模型与独立环境，可以使用：

```bash
cd /home/atuin/r102bf/r102bf10/lmtx/coding-agent-demo
export DEMO_STORAGE=/home/atuin/r102bf/r102bf10/lmtx
export DEMO_PYTHON="$DEMO_STORAGE/environments/coding-agent-demo/bin/python"
export DEMO_MODEL_PATH="$DEMO_STORAGE/models/Qwen3-8B"
export DEMO_SOURCE_ROOT="$PWD"
sbatch --partition=a100 cluster/demo-smoke.sbatch dev
# 最终保留题 + 摘要对照：按需执行，不需要为展示重复跑
# sbatch --partition=a100 cluster/demo-smoke.sbatch final
```

这个已安装环境复用原 lab-skill 的 system-site-packages，不要删除其基础环境。其他机器应新建自己的 venv。

脚本默认分区 a40，可由命令行覆盖；申请 1 GPU、8 CPU、45 分钟上限，实际资源以 Slurm 分配为准。不要照搬分区名称到其他集群。未显式设置 DEMO_SOURCE_ROOT 时，使用提交目录，所以请从仓库根目录提交。

每次作业先保存代码快照，再启动一个本地模型服务。启动等待上限 600 秒；三道任务最多两路并行、每题一次、每题最多 10 分钟和 10 轮工具执行。final 模式随后用同一服务执行四次摘要请求，摘要阶段最多两路。不为每道题重新加载模型。

```bash
squeue -u "$USER" -o '%.18i %.24j %.10T %.10M %R'
sacct -j JOBID -X -o JobID,State,Elapsed,NodeList
# 只在确实要停止该作业时运行：scancel JOBID
```

提交目录的 `coding-demo-JOBID.log` 为 Slurm 日志；其他产物在 `$DEMO_STORAGE/outputs/coding-agent-demo/gpu-JOBID/`。仅提交仓库不会自动提交 GPU 作业。

## 已有本地服务时运行任务

```bash
source scripts/local-env.sh
"$DEMO_PYTHON" scripts/run_demo_tasks.py --split dev --workers 2 \
  --output "$DEMO_STORAGE/outputs/demo-dev-001"
```

每次使用新的输出目录。脚本拒绝覆盖已有任务目录；不要删除失败产物后声称是同一次测试。final 模式的保留题已经查看过，今后若据此调参，它们就不再是新的盲测集。

产物说明：

| 文件 | 用途 |
| --- | --- |
| tasks/summary.json | 所有题目的结果集合 |
| tasks/ID/result.json | 耗时、停止原因、token、文件变化和验收 |
| tasks/ID/transcript.json | 实际发送和接收的模型/工具消息 |
| tasks/ID/workspace/ | 模型最终写出的代码 |
| tasks/ID/state/ | 会话、执行日志与命令输出 |
| server.log | 模型启动、请求与服务错误 |
| summary-check/cases.json | 合成历史与预先定义的人工检查点 |
| summary-check/*.json | 两种摘要提示的输入、输出与用量 |

## 会话恢复

CLI 启动后会显示 Session ID。保持相同模型、工作目录和 MINI_CLAUDE_STATE_DIR：

```bash
bash /path/to/Agent/scripts/run-local.sh --resume-id SESSION_ID
```

若存在 unknown，先核对工作目录的 Git diff、产物、命令日志及执行日志。确认后才运行：

```bash
bash /path/to/Agent/scripts/run-local.sh --resume-id SESSION_ID \
  --ack-unknown '已核对文件和命令输出；明确说明哪些操作发生、哪些仍无法确认'
```

ack 是人工核查记录，不是成功判定，也不会重放原调用。不要删除日志来绕过未知状态。两个进程不能同时使用同一 Session ID；并发任务使用独立状态目录。

## 常见问题

| 现象 | 检查与处理 |
| --- | --- |
| 排队 Priority / Resources | 属于调度等待；squeue 查实际状态，与模型能力无关 |
| vLLM 无法识别设备 | 检查是否真的在 GPU allocation 内，以及 CUDA/驱动；登录节点失败不代表 GPU 测试失败 |
| tokenizer 不存在 | 设置模型绝对路径，两端使用一致的配置 |
| connection refused | 查 server.log 和 /v1/models，确认端口及节点相同 |
| Context budget exceeded | 历史仍保存；检查摘要是否失败或未缩短，不应直接删除用户约束 |
| old_string not found | 该编辑没有应用；模型应重新读取并按实际内容编辑，不应由执行器猜测修改位置 |
| budget_exhausted | 达到工具轮数/成本上限，不是业务成功，也不等于运行器异常 |
| 输出变短或截断 | 查看命令日志和截断标志，磁盘日志也有上限 |
| 模型说完成但验收失败 | 优先检查轨迹与最终代码，模型自述不是验收依据 |

不要把真实凭据放进练习目录、提示或终端输出。模型拥有当前用户的工具权限；本项目不是安全隔离环境。
