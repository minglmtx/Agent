# 框架模块职责与接入入口

本页维护职责和接口边界，不再维护逐修订作业日志。完整合同见[架构](design/codebase-architecture-v1.md)相关节；真实实现/验收范围查[原包与回执](EXPORT.md)。迁入基础树和隔离候选不自动是同一release，接口符号须在所选冻结源码中核实。

Map同次目录预检、单句柄最终权限/同步、整次暂存两文件队列及原worker收尾边界见[暂存合同](design/codebase-architecture-v1.md#map-stage-bounded-copy)；候选v2的原来源只读路由/镜像投影、当前权限和实际挂载也在该合同维护。新副本仍边复制边哈希，可写数据库/前端保持独立，实际复用和提速须由正常业务记录核实。

Map 原生启动非200的完整私有失败记录、原 worker 写前后权限及原错误摘要绑定，以及暂存前实际 GPU 型号核对见[启动失败合同](design/codebase-architecture-v1.md#map-startup-failure-diagnostics)。它们不授予初态、来源或恢复资格；实现、安装和实际消费分开核验。

## 模块拆分与依赖

| 模块/目录 | 职责及主要接口 | 边界与验证重点 |
|---|---|---|
| domain | Task/RunPlan、EvidenceRef、Observation、初态/Reset、状态/事件、预算等版本化数据与纯规则 | 类型、字段、身份/谱系、合法状态及容量；无I/O或业务入口导入 |
| ports | 任务、模型、浏览器/证据、存储、权限、资源与恢复协议 | 参数/返回值/schema、错误、取消/期限、副作用和重入约定显式 |
| application | 公共execute_task，构建、复核、导出各自编排 | 公共任务只返回CompletedTaskExecution/TaskCompletionFacts；不读ConstructionProgress，不判候选/Teacher轮次 |
| 业务准入/结果适配 | ConstructionTaskAdmission、ExecutionTaskAdmission等按实际release选择 | 通过TaskLifecycleAdmission注入；真实每门权限、业务状态及输出转换留本层，不缓存允许标志 |
| 任务前置/收尾端口 | TaskPreparation、TaskInitialization、TaskActorBinding、TaskCapture、TaskFinalization及TaskExecutionDeps装配 | 纯配置和有副作用准备分开；原owner、唯一初态、取证、异常/取消/启动失败收尾完整接线 |
| sites / task family | 本站参数绑定、原生初始化/操作、任务语义和声明恢复范围 | site+family+contract_version精确注册；不跨站导入，不向公共生命周期塞网站分支 |
| collectors / evaluators / review | 过程/终态证据、纯判定、独立复核 | evaluator不操作网站；原判定语义保持，缺证据保持unknown；原执行与新复核版本分别固定 |
| Actor / Generator / Teacher | 角色输入、推理或修订、结果解析；模型执行通过端口 | 公开/私有视图隔离；技能/动作协议和输入保存/独立发送复核一致；不吞token超限/截断 |
| adapters / runtime | 浏览器/网站/模型执行、监督worker、固定安装、Slurm、资源与端口租约 | 注册先于副作用；原物理身份、deadline/取消、部分获取失败收尾；真实关闭与传输结束分开 |
| evidence / journals | 不可变证据、run/resource/request/construction等各自状态 | 原子/幂等、并发、丢回执、主错/清理错、容量收尾余量；不以新账本清空旧占用 |
| retrieval / bank / export / SFT | 来源隔离、检索、合格目标独立导出、模型训练与checkpoint绑定 | split/goal_group/来源及资格；空导出不训练，工程样本不转正，trainer不读exporter私有逻辑 |
| bootstrap / CLI | 精确注册、计划与权限装配，参数入口 | bootstrap唯一组装具体实现；CLI薄，不另建runner、账本或准备平台 |

Generator输入与实际Actor装配的配置/公开能力绑定、旧wire兼容及独立复核/导出版本见[构建能力合同](design/codebase-architecture-v1.md#construction-selected-actor-capabilities)。声明条件工具不等于当前快照注册；软件、精确安装和正式构建资格分别查原包。

以上为职责分组，不要求一行一个大文件。纯数据、校验、I/O、编排、网站逻辑、判定与恢复须按各自变化原因拆文件。application只依赖domain、ports和纯policies；网站之间不互导，具体adapter通过bootstrap注入。

Group 初始原生采集、关闭后原生 guard、原 claim/完整scope与端点绑定、既有阶段组件的中性owner装配、原私有规格与原生执行封装的分别核验、首次 snapshot 的当前意图与先前产物区分、来源恢复预算及 Map/Admin/Group 关闭后发布的原根预算合同见[架构4.3](design/codebase-architecture-v1.md#43-任务准备权威初态与恢复所有权)；具体接入版本、软件及真实验收范围仍查原包清单。来源预算只由现有端口消费，不新增生命周期或权限平台。

初始化来源整图的同次输入传递见[上下文合同](design/codebase-architecture-v1.md#same-call-context-inputs)：复用正文，三个语义门、当前权限与返回前完整复核保留；候选实测与物理收尾不由正文证明代替。浏览器已返回事实经原装配消费既定Actor结果收尾窗口的边界见[返回保存合同](design/codebase-architecture-v1.md#browser-return-publication)，执行期限、公开端口及持久schema保持原合同。

Actor原获取三份不可变正文的同次有界交付、逐次账本/原进程核验及旧消费者边界见[Actor正文合同](design/codebase-architecture-v1.md#actor-acquisition-body-handoff)；减少交换不缓存权限，也不表示实际提速或续跑已验。 准备、实际派发、结果保存及 worker 精确 token 交付见[Actor窗口合同](design/codebase-architecture-v1.md#actor-generation-windows)，未选历史消费者仍为共享期限；Shopping现有准入辅助函数与Map/Admin构造器共用整回合公式，显式返回保存窗口计入发送前余量。 同一生成请求的上下文、提示/参数及公开观察完整正文贯通原计数/保护复核和派发消费者、动态门及循环退出清除见[Actor上下文复核合同](design/codebase-architecture-v1.md#actor-context-review-inputs)。 该合同同时定义显式自适应策略构造器、同一冻结选择向真实调用方的接线，以及封闭Actor的原读取/原生计数复核；兼容导入和软件声明不授予运行权。

初始化原生输入原字节与私有完成规格的分别绑定见[输入绑定合同](design/codebase-architecture-v1.md#initialization-native-input-binding)；直接输入和版本化封装共用策略，离线原产物复核不授予当前运行资格。

自适应策略/3的有限候选前缀、完整公开导航、统一动作/读取示例及显式执行历史/2见[Actor上下文合同](design/codebase-architecture-v1.md#actor-context-review-inputs)及[长输入3.5](design/five-site-long-input-handling-20261101.md#adaptive-observation)。纯导航选择归policies，schema归domain，示例/提示归actor，trace事实生产归application；安装与真实消费分别验收，旧策略/2和未标记历史保持原合同。

同次候选准备图、来源获取正文与初态发布/准确回读的输入交付、父控制器必需权限，以及初始采集生产者/collector绑定见[准备输入合同](design/codebase-architecture-v1.md#same-call-preparation-inputs)；固定整图读取不授予历史attempt续跑或重放资格。可选`PreparationRecordInputReads`在原owned任务作用域内传递同一准备图及首次准确回读的发布正文；当前来源/存储、原语义与动态authority仍逐门核，退出清除。 显式阶段验证的准备/baseline整图使用当前测量owner，历史TaskBinding仍用原owner；命令版本、实际读取scope及前后动态门见[当前初态读取合同](design/codebase-architecture-v1.md#current-initial-read-owner)。

候选baseline整图正文、同次发布与准确回读及原消费authority的保留边界见[baseline输入合同](design/codebase-architecture-v1.md#same-call-baseline-inputs)；完整等价生产者输入的发布、回读和来源三门核验见[等价输入合同](design/codebase-architecture-v1.md#same-call-equivalence-inputs)。原owned任务内到Actor准入的有界正文传递、可选完整比较输入、准确Actor发布正文、原finalizer引用及退出清除，以及必需绑定与可选载体的校验边界也在该合同维护，不能由候选接口推断生产已切换。初始化和等价消费者沿原端口接入，已知发布引用与原失败继续保留。捕获、终页及判定可沿显式 `InitialObservationReads` 消费原 owned 作用域中的同一完整初态正文，准确生产者/selection/线程/操作及退出清除、现场权限与独立完整读取边界见[捕获初态合同](design/codebase-architecture-v1.md#same-task-capture-initial-inputs)；正文不补造 final guard 或旧实例续跑权。 原关闭任务可显式消费保留恢复证据，Map 完整状态与 Admin 持有材料的分别语义、原 native 版本/实例/顺序及离线修订边界见[保留恢复取证合同](design/codebase-architecture-v1.md#retained-restore-navigation-capture)；它不补造原直接捕获。 终态只读证明及capture到判定的正文传递、同任务与旧数据复核边界见[终态正文合同](design/codebase-architecture-v1.md#same-task-terminal-proof-inputs)。收尾的五份冻结声明传递、原动态准入及退出清除见[收尾声明合同](design/codebase-architecture-v1.md#finalization-declaration-inputs)。

同次来源事实及准确claim正文向资源准入交付、现场caller/claim账本/存储检查及返回前完整来源复核见[单次来源准入合同](design/codebase-architecture-v1.md#same-call-source-admission)。收尾可沿同一开放来源读取交接claim正文，attempt门前后仍分别核原实际账本/caller、来源recheck与run journal；限原进程/线程和同次读取期，关闭清除。传递对象不授予权限，未适配端保留完整读取。

同次 TaskBinding 正文交付、可选受监督/2正文交接与准备依赖去重合同见[架构4.3.4](design/codebase-architecture-v1.md#434-taskbinding受控存取与本站语义核验修订86)；每次调用仍核实际权限，不建立跨调用内容或授权缓存，固定安装与消费者须按实际能力一起核对。

纯状态检查的固定只读工作进程、证明内正文复用和Map原生文件权限边界见[状态读取合同](design/codebase-architecture-v1.md#supervised-state-read)；原动态authority及逐题运行资格不由事实读取器替代。

同次Reset生产者正文、准确发布读回及finalizer向公共生命周期的交接见[Reset正文合同](design/codebase-architecture-v1.md#reset-publication-readback)。只复用已交付且绑定完整引用的不可变事实；资源独立RecoveryPlan及未交付依赖仍各核一次。原生检查正文与当前权限分开：同次finalizer保留生产者结果，动态source/state门仍逐次核；独立复核仍走完整读取。接口符号及实际装配以所选冻结源码和原包为准，旧回执、资源关闭和任务最终登记不由此自动补齐。

准备图向后续检查交付同次已核验正文/引用、可选`PreparationBodyChecks`及新增依赖继续读取的边界见[准备记录合同](design/codebase-architecture-v1.md#4316-原准备事实的发布和读取修订99)；持久格式与每次动态authority保持原合同。 Map/Admin/Shopping 类目来源差异、所选原生正文交付、来源链内 `SourcePreparationInputs`、owned 生产者的 `PreparationDeclarationInputs` 及准备/浏览器正文复用，以及返回正文向轨迹登记的交接见[来源复用执行合同](design/codebase-architecture-v1.md#source-reuse-execution-inputs)；已核事件引用与观察正文向封闭消费者的交付见[同任务轨迹合同](design/codebase-architecture-v1.md#same-task-trace-inputs)。差异分支与来源内部调用数分别验收；动态权限和原账本仍现场核验。

Admin 导航完整 dump 的格式、原始摘要及比较范围见[架构4.3.5](design/codebase-architecture-v1.md#435-admin完整数据库快照叶端修订87)；固定镜像格式适配不代表真实来源已合格。

Shopping 分类导航的原始参数/公开绑定、完整快照与保护、本站双合同状态读取、原起点初始化/唯一观察、完整SQL（查询沿用原操作剩余期限）/搜索（显式比较规范版本及原更新计数）/文件与原快照绑定、必需初态比较消费者、原生请求纯校验、固定DOM采集、原来源记录/测量/恢复关闭及发布接线、原TaskCapture装配、当前Actor/2封闭证据判定及同次有界正文交接边界见[Shopping输入合同](design/codebase-architecture-v1.md#修订122第二站-shopping-订单-eta-输入与客户初始化)，当前claim及owned组合见[装配合同](design/codebase-architecture-v1.md#shopping-category-owned)；与订单 ETA 分别装配初始化及实际消费者，不由数据、采集或恢复接口授予来源资格。

Reddit帖子导航的原始14题参数/公开绑定、原生ID/forum/title读取、完整状态、固定Task/Capture/Resume与原实例一次恢复、原账号/精确起点初始化、唯一初始观察、path与heading独立判定及终页采集见[帖子导航合同](design/codebase-architecture-v1.md#reddit-post-navigation-contract)。导航配置与固定工厂显式选择本站共享认证，PreparedBrowserBinding必须具有导航语义检查；唯一初始观察只消费原返回；导航准备检查交出完整原生/账号事实，浏览器语义检查直接消费。准备依赖正文和首次浏览器/初态所需原请求/环境沿现有输入端口传递，当前权限仍逐次核。固定只读入口的导航准备`/2`交出原生reference/current完整正文，父端经原LoadedPreparation继续消费，旧`/1`保持原编码；具体来源策略/原生准入/测量/恢复关闭与发布在原共享来源端口上装配；闭合导航材料由固定只读source worker选择本站读者，已有产物走显式消费分支，不符不回退重建。任务端准备/浏览器声明显式消费同次完整输出，初始化必需注入原生账号/帖子/完整数据库与媒体内容比较并核被动首屏，同次比较固定两侧完整输入和选择正文；收尾接续不可变环境与已发布Reset正文；动态authority逐门核验，完整任务/安装/现场资格另核。原生Task/Capture/Resume、来源/初态及统一生命周期装配独立核验，数据接口不授予图片族替代或历史续跑资格。

元数据子进程在 intent 登记前结束的严格证明与收尾复用边界见[存储未登记合同](design/codebase-architecture-v1.md#storage-unregistered-exchange)；原错误保留，未知状态和历史改写仍隔离。

当前原owner的既有namespace只读打开、显式command/reply4及禁止空历史重建见[来源namespace合同](design/codebase-architecture-v1.md#source-namespace-open)；不转移旧owner或claim，不授予跨作业恢复权。

固定安装源码的完整字节范围、同次核验去重及前后变化检查见[架构7.1.2](design/codebase-architecture-v1.md#712-实际安装来源核验修订53)；不缓存跨调用的来源或权限结论。优化的通用做法维护在[检查流程](FRAMEWORK_CHECK_WORKFLOW.md#runtime-evidence-optimization)。

原操作与作业执行/收尾窗口的交集、领取前准备与完整任务检查、准备后由同一控制器收紧单题上限、有限硬截止及信号覆盖合同见[架构6.1](design/codebase-architecture-v1.md#61-状态分维度保存与部分失败)。Actor显式/2选窗、首轮与逐轮有界准备、同代有界历史正文交付及确定未发送预算停止见[窗口合同](design/codebase-architecture-v1.md#actor-generation-windows)：检查为有界上限，完整模型/必要尾部保留，逐轮authority及intent提交前的派发器preflight纳入准备，已提交/发送后的unknown不改写；纯策略、实际接线和现场结果分别验收。窗口不改原身份或授予运行资格；原站点关闭读回共用已声明期限，轨迹独立cleanup读回保持原事实；实际入口与原生收尾另核。

失败消费者关闭后的显式只读消费见[关闭证据合同](design/codebase-architecture-v1.md#closed-failed-consumer-read)：保留原首错，完整清理/物理关闭核验不减；原safe Reset依赖图与原生恢复复核、任务关闭分别取证，不授予旧实例续跑或重放。

## 开发、测试和整体门

按[现行检查流程](FRAMEWORK_CHECK_WORKFLOW.md)以完整兼容子组一次核共同能力及必要分支；AB→ABC复用未受影响证据，仅补C/组合或被C影响的B及消费者。新兼容题尽量只补参数/绑定和逐题检查，不重新开发公共生命周期。

每个改动在原包清单注明职责/接口、输入类别及预期、实际消费者、精确测试节点/回执、可复用版本、未覆盖项、最小阻断与出口。正常/边界/极端非法/空/错类型/重复保留；状态/I/O补并发、取消、超时及部分失败。模块主流程/关键边界门只限制依赖消费者；先核新夹具，失败先解释根因和最小修复，再失败节点/受影响回归。

纯配置/前置模块提前验证，合并同冻结版本静态和只读安装准备，写状态隔离。整体联调核完整入口、接口/配置/环境、错误/日志/释放、单元/集成、重复代码/过大职责文件/TODO，并显式最终全回归；模块全绿不代替真实权限、网站或训练通过。

## 业务、训练与优化范围

五站代表工程链与训练范围同release组合（至少两种来源同时推进、共享预算/隔离）是首批正式构建前置；全部任务族不必等同一时刻完成。原三任务用户启动→合格目标独立导出→小SFT；完整框架/调用方整体门后继续test/dev，RL另验。详细目标见[goal](DEVELOPMENT.md)，原失败/unknown不为凑正结果重放。

Actor64K/O4096、禁减档/不做96K或128K；Teacher独立真实预算。五站压缩按角色共用，有界范围读取/skill指导按具体消费者与专项设计验收，不宣称通用分块已实现。可选策略显式关闭/不适用或固定版本，T编号不恢复成独立平台。

网站专项合同在本目录对应文档，选择本次受影响项阅读；其“当前版本/已验/待做”只描述原文对应版本，状态必须核原包后继。旧模块逐修订目录与验收记录见清理归档（workspace 材料，未发布），只在追溯接口来源时读取，不作为新的开发排期。
