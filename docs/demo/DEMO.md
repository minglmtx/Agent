# 5 分钟工程演示

不需要重新提交全部 GPU 测试。先完成根 README 的 CPU 安装，然后在仓库根目录：

```bash
source scripts/local-env.sh
```

## 1. 演示命令输出与超时（约 1 分钟）

```bash
"$DEMO_PYTHON" - <<'PY'
import sys, shlex
from mini_claude.command_runner import run_command
command = shlex.quote(sys.executable) + ' -u -c ' + shlex.quote(
    'import time; print("started", flush=True); time.sleep(5); print("finished")')
result = run_command(command, timeout_s=0.5)
print(result.render())
assert result.status == 'timed_out'
assert 'started' in result.stdout
PY
```

这段用于展示超时仍保留已产生的输出。实时增量回调与取消清理由下面的测试验证，而非把测试日志冒充人机交互录像：

```bash
"$DEMO_PYTHON" -m unittest discover -s python/tests -p test_command_runner.py -v
```

## 2. 演示恢复的关键边界（约 1 分钟）

```bash
"$DEMO_PYTHON" -m unittest discover -s python/tests -p test_recovery.py -v
```

重点解释三个测试：保存被中断仍能读旧会话；completed 的同 ID 调用复用结果；只有 started 的调用恢复为 unknown 并阻止执行。打开 execution_journal.py 展示 begin/complete/acknowledge_unknown 的状态变化。

这是可重复的故障注入演示，不能声称已经经历真实机器断电。真实 CLI 恢复命令见 RUNBOOK.md。

## 3. 演示摘要与回退（约 1 分钟）

```bash
"$DEMO_PYTHON" -m unittest discover -s python/tests -p test_summary_integration.py -v
```

打开 `reports/summary-examples.json` 对比原版与结构化输出。指出结构化版本明确保存约束和待办，同时主动展示 attempted/failed 不准确的例子，说明 schema 不证明事实正确。测试负责展示非法摘要回退，真实模型输出负责展示实际内容效果。

## 4. 展示真实模型结果（约 2 分钟）

打开 `reports/evaluation-summary.json` 和 `reports/RESULTS.zh-CN.md`。数量任务通过，但六题总计 1/6；框架没有把“模型说完成”当成成功。折扣/空输入达到预算，报告能区分预算停止和主动结束。

如果现场已有 GPU 服务，可以在一次性工作目录用 run-local.sh 演示读文件与测试反馈。不要保证现场模型一定修复成功，也不要把预先录制的成功案例说成实时随机运行结果。

## 讲解提纲

- 基于上游复现，自己修改的边界是哪三项？
- 原子保存能解决什么，无法解决什么？
- 副作用未知时为什么选择停下而不是自动重试？
- 超时后怎样避免输出丢失和子进程残留？
- 摘要怎样保留工具配对，为什么仍需独立验收？

这五个问题都能落到代码、测试和实际产物上，比扩大功能清单更适合本次小型项目展示。
