# 安装与开发检查

## 范围

公共任务生命周期负责准备、初始化、Actor、取证、判定和恢复关闭；构建层负责候选顺序与 Teacher 修订。Generator/Actor 仅消费允许的公开上下文，Teacher 使用经过授权的证据。train/dev/test 分离，正式 SFT 仅消费合格 train 正目标，空导出不训练。

保留原运行配置的 64K/O4096、共享预算、付费并发 1 和训练准入门；这里没有可直接复用的生产权限。旧实例、claim、unknown 和费用不能因新安装通过而重置。

## 安装

Python >= 3.11。依赖和可选项见 [pyproject.toml](../pyproject.toml)。在 Slurm 分配内、独立环境中安装：

```bash
python -m pip install -e '.[test]'
lab-generate-skill --help
```

CLI 实际入口由安装生成的 `lab-generate-skill` 命令提供；其 `build`/`workflow` 属于早期轨迹和技能库链，不能等同于统一 `construct_targets`。业务命令需要显式 `--config`、数据、模型和独立部署，当前分支不带默认生产配置。依赖解析取决于包索引；本次沿原 workspace 环境检查，未宣称全新公网环境端到端可复现。

模型、浏览器、检索、PDF 和 SFT 依赖分别使用 `runtime`、`browser`、`sentence-transformers`、`map-pdf`、`sft` extras；仅安装所需项。启用能力缺依赖时拒绝，不能静默降级。

## 检查

测试、项目 import 和安装全部在 Slurm 内进行。以下是首次装配或相关入口变化时可选的检查示例，不是每次修改都要执行的清单；已适用的结果复用：

```bash
lab-generate-skill --help
python -m pytest -q tests/framework/test_task_execution.py
python tools/development-checks/tests/test_task_progress_workflow.py
```

`tests/` 保留原 Python 测试与构造器代码，但未发布录制夹具、现场证据、模型或数据库。因此完整 `pytest` 不是本分支的免配置运行方式；涉及原部署/原回执的测试需在具备合法输入的环境中单独选择。文件存在不代表本次全部重跑。

`cluster/` 与 `tools/check_framework.py` 保留原 workspace 调度、输出与固定安装约定，供部署者阅读；其中路径和分区须按新环境明确配置，不能直接当通用启动器。检查器默认有原 workspace 资产与夹具依赖。单题/候补提示脚本只输出建议，不核验证据，不授予权限。脚本中的原 EXECUTION-GUIDE 指针属于未发布的运营说明；通用边界见本页及[检查流程](FRAMEWORK_CHECK_WORKFLOW.md)。

## 执行入口

公开仓库从 [Admin owned execution](../src/lab_generate_skill/bootstrap/admin_navigation_owned_execution.py)、[Map owned execution](../src/lab_generate_skill/bootstrap/map_owned_execution.py)和[公共生命周期](../src/lab_generate_skill/application/execute_task.py)阅读实际装配。原包 wrapper 与部署脚本绑定私有输入、身份、固定安装和当前权限，因此未发布。新的生产入口必须自行装配正式 authority，并逐门核现场初态和恢复责任；不得用测试替身启动真实业务。

## 证据边界

源码/软件、安装、真实业务、Reset/物理关闭/账本以及训练资格是不同出口。当前版本的已有验收范围见[发布说明](EXPORT.md)。本分支没有实验结果账本，也不替代原 workspace 的清单。
