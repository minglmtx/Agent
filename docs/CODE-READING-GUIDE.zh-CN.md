# Lab Generate Skill 代码阅读指南

本指南参考 [Coding Agent 代码阅读指南](https://github.com/minglmtx/Agent/blob/4911e4b0fa22aa433320b3cd9acc5efa58dafb91/docs/demo/CODE-READING-GUIDE.zh-CN.md)的组织方式：先读一条完整链路，再按能力读模块、跟踪调用，最后结合测试理解边界。这里介绍的是本项目的任务执行、技能目标构建与训练链，参考文档中的上游关系和评测成绩不适用于本项目。

**发布阅读快照：`lab-generate-skill-current-preparation-consumer-v1-candidate-20261111`（2026-11-11）。** 源码链接统一指向本分支；本指南原先使用 Actor corrective v4 快照，现已将阅读入口迁到已验共用后继。版本、私有部署与验收边界见[发布说明](EXPORT.md)。本分支不包含原 wrapper、运行清单或生产权限。

第一次阅读可以先走这两条链：

```text
单次任务执行
原包入口与精确装配 → 来源/权限核验 → 获取与准备 → 初始化、公开观察、baseline
                 → Actor 多轮模型/动作/读取 → 取证 → 语义判定 → 恢复与关闭
                 → 保存本次执行事实，供独立复核消费

训练目标构建
合格来源 + skill bank → top-6 检索 → Generator 候选
                    → 调用同一任务执行链验证 → 必要的 Teacher 修订与复验
                    → 目标选择 → 独立复核 → 合格 train 正目标导出 → SFT
```

第一条链也能单独用于执行与评估。第二条链中的四候选、修订上限、模型窗口和训练阶段门以 [goal](DEVELOPMENT.md)为准；流程图描述职责，不表示全部生产链或训练已经验收。

## 一、先认识目录和依赖方向

下表的包内路径都相对阅读快照的 `src/lab_generate_skill/`。

| 位置 | 放什么 | 阅读时关注什么 |
| --- | --- | --- |
| `domain/` | Task、EvidenceRef、状态事件、预算和版本化数据 | 一份输入属于哪个 task／attempt／owner；哪些字段组成完整身份。 |
| `ports/` | 模型、浏览器、准备、判定、存储、恢复等接口 | 参数、返回值、期限和副作用约定；调用者要求什么能力。 |
| `policies/` | 上下文选择、工具合同、数据隔离、导出资格等纯规则 | 同样的输入怎样得到确定的决策。 |
| `application/` | 任务执行、构建、复核、导出、训练编排 | 阶段顺序、端口调用、失败后保留什么事实。 |
| `bootstrap/` | 具体端口实现与任务消费者的装配 | 谁创建依赖，怎样绑定同一来源、实例、配置和权限。 |
| `sites/`、`task_families/`、`evaluators/` | 站点语义、任务族、证据结构与判定 | 本题“完成”意味着什么，过程与终态需要哪些证据。 |
| `adapters/`、`runtime/` | 模型、进程、浏览器、存储、账本、Slurm及生命周期实现 | 真正的 I/O 在哪里发生，超时、取消和丢回执怎样处理。 |
| `tests/framework/`（快照根目录下） | 框架合同、组合与故障测试 | 从测试输入、注入依赖和断言理解行为，辨认夹具与真实证据。 |
| 原 workspace 的 `experiments/`（未发布） | 私有 wrapper、部署与运行回执 | 本仓库从 bootstrap 阅读装配；真实运行另核原包。 |

依赖阅读顺序可以记成：`domain / ports / policies → application → bootstrap + adapters`。`application` 通过端口编排，具体实现由装配层接入；网站之间不互相导入，evaluator 消费证据，不执行网站操作。详细合同见[模块职责](FRAMEWORK_MODULES.md)和[整体架构](design/codebase-architecture-v1.md)。

## 二、按模块阅读

| 顺序 | 模块 | 代码入口 | 阅读重点 |
| --- | --- | --- | --- |
| 1 | 执行入口与装配 | [Admin owned execution][admin-entry]、[Map owned execution][map-entry]、[部署说明][admin-wrapper] | 从 bootstrap 构造器跟踪具体依赖；原包 wrapper 和私有配置未发布，实际运行须独立装配。 |
| 2 | 任务数据与依赖 | [TaskExecutionPlan][task-data]、[TaskExecutionDeps][task-deps]、[TaskPreparation 等端口][task-ports] | 对照计划与依赖：准备、初始化、Actor、捕获、判定、收尾各需要什么输入，输出交给谁。 |
| 3 | 公共任务生命周期 | [execute_task()][execute] | 顺着 `_execute_task()` 读正常路径，再读 `finally` 中的 `_finish()`。区分 `CompletedTaskExecution` 与携带原错、清理错和已知事实的异常。 |
| 4 | 初始化与初态等价 | [Admin 初始化装配][admin-init]、[initialize_task.py][initialize]、[初始化纯规则][init-policy] | 先恢复规定初态，再初始化，产生唯一公开初始观察并核 baseline／equivalence；私有状态证明怎样与模型输入隔离。 |
| 5 | Actor Loop | [RecordedActorRunner.run()][actor-loop]、[actor_loop_inputs.py][actor-inputs] | 一轮怎样选择上下文、登记生成、解析决策、执行动作或读取、写入轨迹并决定停止；模型调用数与实际交互数分别计数。 |
| 6 | 模型调用与返回保存 | [execute_actor_generation()][generation]、[local_actor.py][local-actor] | 从持久派发意图到模型返回，再到结果保存；执行窗口与返回保存窗口怎样分工，已完成但保存异常时留下什么。 |
| 7 | 工具协议与反馈 | [工具合同][tools]、[Actor 响应解析][actor-response]、[browser_action.py][browser-action]、[observation_read.py][observation-read] | 区分模型提出动作、合法性校验、真正执行；错误提议如何反馈，连续拒绝如何停止。读取证据与网站动作是不同路径。 |
| 8 | 上下文与长输入 | [ControlledActorContext][context]、[context_budget.py][context-budget]、[actor_observation_selection.py][observation-selection] | 完整请求如何计数，公开观察如何选取与保留来源，发送前怎样独立复核；具体策略以所选配置为准。 |
| 9 | 五站接入与判定 | [sites/][sites]、[evaluators/][evaluators]、[TaskRegistry][registry]、[Evaluation][evaluation] | 按 site + family + contract_version 精确匹配；沿本站证据 schema 阅读判定，缺证据与有效失败怎样区分。 |
| 10 | 证据与账本 | [EvidenceRef][evidence]、[StateReads][state-reads]、[ledger/][ledgers] | 引用怎样绑定字节与生产者；Run、Resource、Trace、Construction 等记录各保存什么，为什么单个 `sealed` 不能代表全部完成。 |
| 11 | Reset 与关闭 | [RecordedTaskFinalization][finalization]、[ResetEvidenceReader][reset-reader]、[execute_task._finish()][execute] | 原资源恢复、Reset 证据发布、物理关闭和最终登记分别如何完成；同次正文交付如何避免重复读取，同时保留当前权限检查。 |
| 12 | skill bank 与检索 | [早期 skill_builder.py][skill-builder]、[postprocess.py][postprocess]、[CpuSkillRetriever][retriever] | 先区分轨迹抽取/整理与统一构建检索；再看冻结 bank、来源隔离、编码评分及精确 top-6 输出。 |
| 13 | Generator 与候选构建 | [construct_targets()][construct]、[ConstructionProgress][construction-state]、[generator/][generator] | 一次推进如何选择生成、执行、修订、登记或观察；候选执行如何复用公共任务生命周期，pending／unknown 如何保留。 |
| 14 | Teacher 修订 | [assemble_teacher_revision()][teacher-assembly]、[RecordedTeacher][teacher-revision]、[construction_messages.py][teacher-messages] | 多候选与多轮允许证据怎样组织成请求，修订怎样回到构建状态；Teacher 输入权限和预算与 Actor 分别核验。 |
| 15 | 独立复核、导出与 SFT | [review_run()][review]、[export_targets()][export]、[train_sft()][train] | 复核固定的已执行历史；只导出合格目标；训练读取固定数据并核阶段权限。导出完成、训练启动、checkpoint 验证是不同结果。 |

### 建议亲自跟踪的调用

1. **跟踪一次 Admin 任务。** 从 [Admin 装配][admin-entry] 找到 [admin_navigation_owned_execution()][admin-owned]，再看 [admin_navigation_task_execution()][admin-execution] 怎样提供依赖，最后进入 [execute_task()][execute]。画出 `TaskExecutionPlan → InitializedTask → TraceSnapshot → TaskCaptureResult → Evaluation → TaskCompletionFacts`，找出每次转换前的权限与身份核验。
2. **跟踪一次模型动作。** 在 [Actor Loop][actor-loop] 中找到 `execute_actor_generation()`，沿 [响应解析][actor-response]看决策，再到 [execute_browser_action()][browser-action]。分别标出“模型返回”“动作派发”“浏览器返回”“证据已保存”；思考中断发生在相邻两点之间时，哪些事实已知。
3. **跟踪一次长页面输入。** 从 [上下文准备][context]读候选选择、完整请求计数和发送复核，再读 [observation_read.py][observation-read]。查清请求引用的原观察、读取范围和回传正文如何关联；不要把局部视图当作原始证据被删去。
4. **跟踪一次失败后的收尾。** 在 [execute_task()][execute]找 `effects_started`、`primary`、`cleanup_errors` 和 `_finish()`，再读 [finalization][finalization] 与 [Reset 读取器][reset-reader]。回答：准备尚未返回时谁负责原资源？恢复成功但发布失败时，哪些结果仍未证实？
5. **跟踪一个训练目标。** 从 [construct_targets()][construct]和 [ConstructionProgress][construction-state]追到执行结果、Teacher 修订和目标选择，再进入 [review_run()][review]、[export_targets()][export]、[train_sft()][train]。找到 train/dev/test 隔离、正目标资格和空数据拒绝的位置。

Map 可从 [Map 装配][map-entry]进入 [map_navigation_owned_execution()][map-owned]，与 Admin 对照阅读：共用生命周期保持一致，来源准备、原生状态和本站判定通过不同装配接入。

## 三、与参考指南的能力主题对照

这是学习路径的对应关系，不表示两套项目共享实现或具有相同的完成范围。

| 参考指南主题 | 本项目对应 | 阅读时需要区分 |
| --- | --- | --- |
| Agent Loop | `RecordedActorRunner`、`execute_task` | Actor 的模型交互循环外，还有网站准备、判定和恢复生命周期。 |
| Tool Use | Actor 工具合同、浏览器动作、观察读取 | 工具提议是否合法、是否已经派发、结果是否已保存分别有状态。 |
| Permission | source／claim／authority、资源 owner、各阶段 admission | 权限与具体任务、实例、操作和期限绑定，历史回执不提供当前许可。 |
| Skills | skill bank、检索、Generator 候选 | 这里重点是从轨迹抽取和检索技能、构建训练目标；不要把它直接理解成 Coding Agent 的 `SKILL.md` 加载器。 |
| Context Compact / Memory | 上下文候选、观察读取、执行历史、Teacher 证据组织 | 分别看当前模型输入和完整原始证据；不据此宣称已有通用长期记忆系统。 |
| Subagent | Generator／Actor／Teacher 角色分工 | 角色协作有固定输入输出和构建状态机，不等同于自由委派子 Agent。 |
| Session / Execution Recovery | 证据、请求及资源账本、Reset、独立复核 | 重点是保存原请求与资源事实；unknown 不自动重发，恢复不自动重跑旧 attempt。 |
| Scheduler / Background Tasks | Slurm、worker 生命周期、原包 wrapper | 调度状态只说明作业状态，业务结果、恢复关闭和训练资格另有证据。 |
| MCP | 先看 `ports/` 与具体 adapters | 参考指南中的 MCP 客户端不是本项目的默认阅读入口，外部能力沿所选端口实现核实。 |

## 四、本项目的实现重点，以及怎样辨认版本差异

阅读时重点理解这四个设计落点：

- **公共执行与构建分开。** `execute_task` 返回中性执行事实；候选顺序、Teacher 修订和目标选择在构建层处理。单次评估不必装配整套训练流程。
- **用证据连接阶段。** 下一消费者接收版本化数据和完整引用；独立阶段可以消费冻结输出。正文复用、完整性校验和实时权限是不同责任。
- **失败也是需保留的结果。** 主错误、清理错误、未知请求和已保存返回分别保留。Actor 停止、业务成功、安全 Reset、资源关闭和持久登记不能互相代替。
- **站点语义留在本站。** `sites/shopping_admin`、`sites/shopping`、`sites/gitlab`、`sites/reddit`、`sites/map` 与对应 evaluator 分别处理本题语义；框架通过精确注册与装配复用机械流程。

参考文档按 Git 上游提交介绍改动；本 workspace 还存在基础树、隔离候选、固定安装和原包入口。因此这里不编造统一“上游到当前”的提交统计。追某项变更时，先取得原包登记的前后源码身份，再比较相关文件，最后核消费者实际安装的版本。

例如，在本仓库根目录只读定位本指南快照中的符号：

```bash
reading_root=.
rg -n 'def execute_task|def _finish' "$reading_root/src/lab_generate_skill/application/execute_task.py"
rg -n 'class RecordedActorRunner|def run' "$reading_root/src/lab_generate_skill/application/actor_loop.py"
rg -n 'def construct_targets|def select_target' "$reading_root/src/lab_generate_skill/application/construct_targets.py" "$reading_root/src/lab_generate_skill/domain/construction_state.py"
```

[CLI][cli] 中的 `build`／`workflow` 主要承接早期轨迹与 skill bank 流程，不能仅凭同名命令推断它调用了统一 `construct_targets`。同样，[候补准备提示脚本](../tools/development-checks/candidate-preparation-workflow.py)与[单题推进提示脚本](../tools/development-checks/task-progress-workflow.py)只返回步骤提示，不负责执行网站或授予权限。实际运行入口沿原包核对。

## 五、配合测试阅读与核验结果

先读测试中的构造器、fixture 和断言，再回到实现。下面给的是阅读入口，测试文件存在不代表已在当前安装通过，也不代表真实业务通过。

| 想理解的问题 | 测试入口 | 重点看什么 |
| --- | --- | --- |
| 公共生命周期和具体依赖怎样接起来 | [test_task_execution.py][test-task]、[test_task_execution_composition.py][test-composition] | 正常执行产物、装配身份、主错与收尾结果。 |
| Actor 怎样推进或拒绝非法提议 | [test_actor_loop.py][test-actor]、[test_actor_corrective_examples.py][test-corrective] | 生成、交互、读取分别计数，纠错反馈与连续拒绝停止。 |
| 冻结产物能否直接供下一阶段消费 | [test_frozen_stage_consumers.py][test-frozen] | 真实保留产物、错引用拒绝、上游生产者调用为零；逐例核覆盖范围。 |
| Reset 正文交接能否减少重复读取 | [test_reset_body_handoff.py][test-reset] | 完整传递依赖、准确回读、当前 authority，以及读回失败后的已知引用。 |
| 检索与候选状态机如何组合 | [test_construction_retrieval_integration.py][test-retrieval]、[test_construction_control.py][test-construction] | top-6 输入绑定、生成/修订/验证/选择和仅登记分支。 |
| 原执行如何被独立复核与导出 | [test_review_run.py][test-review]、[test_export_targets.py][test-export] | 固定历史、复核范围、合格目标与导出数据；不重跑原网站。 |
| 训练什么时候必须拒绝 | [test_training_boundaries.py][test-training] | 未授权阶段、夹具/空数据、错误身份，以及结果已返回但登记丢回执。 |

阅读真实结果时，在原 workspace 从 handoff 进入该包 summary，再定向核原清单和回执（本分支不发布这些文件）：源码/配置身份 → 受影响软件检查 → 精确安装及消费者 → 本题执行/判定 → Reset与资源/账本关闭 → 导出与训练资格。隔离夹具、工程派生输出和原题业务证据分别判断，`passed` 或 Slurm `COMPLETED` 只在原回执声明的范围有效。

本指南只做代码与文档导航。运行测试、项目 import、安装、模型、网站、数据库或大规模证据重放必须遵守 [AGENTS](../AGENTS.md)与[检查流程](FRAMEWORK_CHECK_WORKFLOW.md)，通过 Slurm 执行。修改某阶段前复用已有适用证据，仅检查当前变化与受影响消费者；不要为了读懂代码启动完整业务链。

[admin-wrapper]: DEVELOPMENT.md#执行入口
[admin-entry]: ../src/lab_generate_skill/bootstrap/admin_navigation_owned_execution.py
[map-wrapper]: DEVELOPMENT.md#执行入口
[map-entry]: ../src/lab_generate_skill/bootstrap/map_owned_execution.py
[task-data]: ../src/lab_generate_skill/domain/task_execution.py
[task-deps]: ../src/lab_generate_skill/ports/task_execution_deps.py
[task-ports]: ../src/lab_generate_skill/ports/task_execution.py
[execute]: ../src/lab_generate_skill/application/execute_task.py
[admin-init]: ../src/lab_generate_skill/bootstrap/admin_navigation_task_initialization.py
[initialize]: ../src/lab_generate_skill/application/initialize_task.py
[init-policy]: ../src/lab_generate_skill/policies/task_initialization.py
[actor-loop]: ../src/lab_generate_skill/application/actor_loop.py
[actor-inputs]: ../src/lab_generate_skill/application/actor_loop_inputs.py
[generation]: ../src/lab_generate_skill/application/actor_generation.py
[local-actor]: ../src/lab_generate_skill/adapters/models/local_actor.py
[tools]: ../src/lab_generate_skill/policies/actor_tool_schemas.py
[actor-response]: ../src/lab_generate_skill/actor/response.py
[browser-action]: ../src/lab_generate_skill/application/browser_action.py
[observation-read]: ../src/lab_generate_skill/application/observation_read.py
[context]: ../src/lab_generate_skill/application/actor_context_preparation.py
[context-budget]: ../src/lab_generate_skill/policies/context_budget.py
[observation-selection]: ../src/lab_generate_skill/policies/actor_observation_selection.py
[sites]: ../src/lab_generate_skill/sites
[evaluators]: ../src/lab_generate_skill/evaluators
[registry]: ../src/lab_generate_skill/registry/resolve.py
[evaluation]: ../src/lab_generate_skill/domain/evaluation.py
[evidence]: ../src/lab_generate_skill/domain/evidence.py
[state-reads]: ../src/lab_generate_skill/adapters/plans/state_reads.py
[ledgers]: ../src/lab_generate_skill/adapters/ledger
[finalization]: ../src/lab_generate_skill/adapters/sites/task_finalization.py
[reset-reader]: ../src/lab_generate_skill/adapters/plans/reset_evidence.py
[skill-builder]: ../src/lab_generate_skill/skill_builder.py
[postprocess]: ../src/lab_generate_skill/postprocess.py
[retriever]: ../src/lab_generate_skill/adapters/retrieval/retriever.py
[construct]: ../src/lab_generate_skill/application/construct_targets.py
[construction-state]: ../src/lab_generate_skill/domain/construction_state.py
[generator]: ../src/lab_generate_skill/generator
[teacher-assembly]: ../src/lab_generate_skill/application/teacher_assembly.py
[teacher-revision]: ../src/lab_generate_skill/application/teacher_revision.py
[teacher-messages]: ../src/lab_generate_skill/teacher/construction_messages.py
[review]: ../src/lab_generate_skill/application/review_run.py
[export]: ../src/lab_generate_skill/application/export_targets.py
[train]: ../src/lab_generate_skill/application/train_sft.py
[admin-owned]: ../src/lab_generate_skill/bootstrap/admin_navigation_owned_execution.py
[admin-execution]: ../src/lab_generate_skill/bootstrap/admin_navigation_task_execution.py
[map-owned]: ../src/lab_generate_skill/bootstrap/map_owned_execution.py
[cli]: ../src/lab_generate_skill/cli.py
[test-task]: ../tests/framework/test_task_execution.py
[test-composition]: ../tests/framework/test_task_execution_composition.py
[test-actor]: ../tests/framework/test_actor_loop.py
[test-corrective]: ../tests/framework/test_actor_corrective_examples.py
[test-frozen]: ../tests/framework/test_frozen_stage_consumers.py
[test-reset]: ../tests/framework/test_reset_body_handoff.py
[test-retrieval]: ../tests/framework/test_construction_retrieval_integration.py
[test-construction]: ../tests/framework/test_construction_control.py
[test-review]: ../tests/framework/test_review_run.py
[test-export]: ../tests/framework/test_export_targets.py
[test-training]: ../tests/framework/test_training_boundaries.py