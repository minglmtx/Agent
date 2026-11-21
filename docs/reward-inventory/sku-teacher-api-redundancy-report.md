# SKU Teacher API 请求结构性冗余分析报告

> 分析对象：`sku-teacher-1-prompt.md`、`sku-teacher-2-prompt.md`
> 业务场景：Skill Revision Teacher —— 多个 skill 候选各自跑出完整执行轨迹，打包成一个请求交给 teacher 模型，让它为同一任务产出一条修订后的 skill。
> 报告目标：站在「teacher 需要哪些信息才能正确修订 skill」这个业务需求上，区分**必要信息**与**结构性冗余**，避免把业务必需的数据误判为浪费。

---

## 0. 业务背景与判断基准

这个请求要回答的核心问题是：

> 给定任务 T 和多个候选 skill（S1…Sn），每个候选都独立跑了一遍执行轨迹（含每一步 action/observation/reward），teacher 要提炼出「一次全新执行 T 时应该采用的 skill」。

因此，一个「正确」的 teacher 请求，业务上**必须**满足：

1. **完整轨迹**：每个候选的每一步 action + observation + 反馈，按 event_id 有序，且候选之间**彼此隔离**（不能把 A 候选的页面状态混到 B 候选里）。这是 teacher 判断「哪一步 guidance 是错的 / 哪一步是 execution 失误」的唯一依据。
2. **初始视图**：Generator 实际看到的初始页面（`generator_planning_view`），用来判断 skill 的「起始条件 / when_to_apply」是否写对。
3. **检索到的参考 skill**：作为修订时的参照池。
4. **能力/规则声明**：告诉 teacher 这个 Agent 有哪些工具、什么行为约束（否则无法判断「不可执行」与「执行错误」）。

**判断基准**：只有「对上述四项业务目标无贡献、或同一信息被重复送入且不会改变 teacher 的判断」的，才算结构性冗余。

---

## 1. 请求整体形状（两文件一致）

```
messages = [
  system: 4349 字符（revision rules + evidence boundaries + 输出约束）,
  user:   { 单条 JSON，22万~24万字符 }
]
user.content 顶层键（两文件完全一致）：
  version / available_tools / actor_system_prompts / field_projection /
  archival_byte_reversible / observation_protocol / evidence / pages /
  content_blocks / format_examples / actor_contexts / teacher_shared_texts /
  common_capabilities / common_rules / instruction_display
```

| 维度 | teacher-1 | teacher-2 |
|---|---|---|
| user 消息字符数 | 226,638 | 245,935 |
| evidence.attempts | 4 个（72 events） | 5 个（87 events） |
| retrieved_skills | 6 个 | 6 个 |
| pages / content_blocks | 16 / 17 | 18 / 18 |
| actor_contexts | 24 个 | 26 个 |
| teacher_shared_texts | t0–t30（21,480 字符） | t0–t33（23,761 字符） |
| best_successful_attempt | null | null |

---

## 2. 先厘清数据模型（避免误判的关键）

初看这套 JSON 有「pages + content_blocks + teacher_shared_texts + actor_contexts」四层，像是同一份数据存了四遍。**实测并非如此**，它其实是一套**三层引用式结构**：

```
pages[]                      ← 引用层（给 Teacher 的「按页浏览」入口）
  └─ parts[] = {kind:"block", block_ref:"bN"}   引用 content_block
            或 {kind:"text", text:{teacher_text_parts:[...]}}   内联文本
content_blocks[]             ← 文本块层（真正的文本载体）
  └─ teacher_text_parts[] = ["# Current view ...", {teacher_text_ref:"tN"}, "# Original source ..."]
teacher_shared_texts{tN}     ← 文本池（去重后的共享片段）
```

**引用机制是真实存在的、且在生效**：

| 指标 | teacher-1 | teacher-2 |
|---|---|---|
| content_blocks 内引用项（`teacher_text_ref`） | 52 项 | 62 项 |
| content_blocks 内联字符串项 | 46 项 | 52 项 |

所以「页面快照被原样复制 N 遍」的说法**不成立**——页面内容是通过 `teacher_text_ref` 指向文本池的。**下面的冗余分析，必须基于这套真实模型，而不是假设它没有去重。**

---

## 3. 真正的结构性冗余（按业务影响排序）

### 🔴 R1：`# Current view` 观察元数据被逐块内联，结构高度重复（最大可压缩项）

每个 `content_block` 的 `teacher_text_parts` 开头都内联一整段 `# Current view ...` JSON，它是该次 read 操作的观察元数据：

```json
{"observation_version":"observation/1","tab":"tab-0","frame":null,
 "complete_requested_range":true,"search_coverage_complete":true,
 "results_exhausted":true,"continuation":null,"omissions":[],
 "covered_ranges":[{...start/end 区间...}],
 "original_public_overview":{"state":"ready","active_tab_id":"tab-0",
   "tabs":[{"tab_id":"tab-0","url":"...","title":"..."}],
   "last_action_error":""},
 "query":"Mineralogie All Natural Lip Gloss, Ruby Rose",
 "matching":"unicode_casefold_literal/1",
 "displayed":"...","captured_but_unshown":{...},"uncaptured_or_pending":"unknown"}
```

**体量**：teacher-1 有 6 块共 9,518 字符，teacher-2 有 7 块共 10,923 字符，约占总 user 消息的 **4%**。

**为什么算冗余**：这些字段里，`tab` / `frame` / `observation_version` / `matching` / `displayed` 固定文案 / `uncaptured_or_pending` 在**每一次 read 之间几乎不变**，真正随观察变化的是 `covered_ranges`、`omissions`、`continuation`、`last_action_error` 这几个。当前是「整个对象每次完整重发」，而非「只发 delta」。对 teacher 判断 skill 对错而言，`observation_version`、`displayed` 说明文案等纯固定字段**不提供任何增量信息**。

### 🔴 R2：同一页面快照以「DOM 文本 + AX 树」两种格式并存，且各有重复副本

- `content_blocks[0].text = 16,775 字符`：`RootWebArea "Search results for 'sale'"...`（可读 DOM 树文本）。
- `pages[10].text = pages[14].text ≈ 17,951 字符`：`AX records: each layout slot is [absolute tab depth, role...]`（AX 树机器格式），p10 与 p14 相似度 0.979，是同页面的两份近似快照（差异仅在商品列表尾部）。

**体量**：`content_blocks` 纯文本块合计 32,630 字符（两文件完全相同）；`pages` 合计 64–67K 字符。

**为什么是结构性冗余**：
1. **同一页面内容以两种格式各存一份**（DOM 文本 + AX 树），teacher 修订 skill 时通常只需要「页面上有哪些可点控件的 role/label」这一种视图，两种格式对 skill 修订的边际价值很低。
2. **pages 内部已检出重复组**：`pages` 中 p1/p4 内容重复（teacher-1、teacher-2 均如此），content_blocks 中 teacher-1 有 `b4/b7` 重复、teacher-2 有 `b2/b9` + `b4/b7` 两组重复。这些重复副本是同一观察在不同 candidate attempt 下的重复引用，**没有去重**。

### 🟠 R3：`retrieved_skills` 与候选 skill 是两套不同集合，但体积重叠、语义易混淆

这是初读最容易误判、也最需要厘清的一点：

- `evidence.attempts[].skill` = **待评估的候选 skill**（title 如 `Search for Product`、`Locate Product in Search Results`、`Locate Product Page`），共 4/5 个，每个对应一次独立执行轨迹。
- `evidence.retrieved_skills` = **检索到的参考 skill**（title 如 `Extract SKU From Product Details`、`Verify Exact Product Before Extracting SKU`、`Read SKU From Product Details`…），共 6 个，是修订时的参照池，**不参与轨迹执行**。
- `teacher_shared_texts` 里的 `# Applicable skills` 块 = 候选 skill 在轨迹中出现的**文本投影**（title 与 `attempts[].skill.title` 一致）。

**所以这不是「同一数据重复存」，而是三个语义不同的对象**。业务上三者都需要。

**但存在两点结构性浪费**：
1. 候选 skill 的完整文本（title + principle + when_to_apply）在 `attempts[].skill` 里已结构化存了一份，又在 `teacher_shared_texts` 的 `# Applicable skills` 块里**按文本再投影一次**（`Locate Product in Search Results` 在 t24/t27 出现两次，principle 措辞仅微调）。
2. `best_successful_attempt = null`（两个文件都是），意味着**没有任何一个候选成功**（reward 全为 0.0）。此时 teacher 要做的其实是「从失败轨迹里反推哪里 guidance 不足」，4~5 条全量轨迹都算证据；但 6 条 retrieved_skills 与候选 skill 高度同质（都在讲「怎么找 SKU / Manufacturer」），检索结果没有为修订引入新信息。

### 🟡 R4：格式示例（format_examples）三处重复

- 顶层 `format_examples` 字段有 5 项，其中 `fe[1]`、`fe[2]`、`fe[3]` 三项**字节完全相同**（175 字符，三种 read 工具 `list_regions`/`read_region`/`search_regions` 的模板）。
- 同时 `teacher_shared_texts` 里又有 t19/t20 两段 `# Independent format examples`（910 + 674 字符），内容与顶层 `format_examples` 是同一套示例的再次展开。
- `actor_contexts` 里 19 个 context 的 `format_examples_ref` 都指向顶层 `format_examples`（f0–f4）。

**结论**：同一份「工具调用格式示例」以「顶层字段 + t19 块 + t20 块」三种形态出现，且 fe[1..3] 内部还有完全相同的三项。对 teacher 而言，格式示例只需一份即可（它教的是「输出/调用格式」而非任务动作，system 提示词已声明 *"examples show syntax only, not task actions or answers"*）。

### 🟡 R5：能力/规则声明与 system 提示词存在语义重叠

- system 消息（4,349 字符）已包含：revision rules、evidence boundaries、输出格式约束。
- user 消息里的 `common_capabilities`（14 条，1,886 字符）+ `common_rules`（9 条，1,710 字符）+ `actor_system_prompts` 又声明了一遍「Agent 有哪些工具 / 什么行为规则」。

**部分重叠但非完全重复**：system 里的是「Teacher 的修订规则」，`common_rules` 里的是「Actor（被评估的执行者）的行为规则」——两者读者不同，属必要区分。**真正的浪费**在于：`available_tools` 只有 1 项、`actor_system_prompts` 只有 1 项，却各自用 `_ref` 指向 `common_*`，而 `common_*` 又内联全文——引用层没有省下任何 token（因为全案只有 1 个 toolset / 1 个 prompt，`_ref` 反而多一层 indirection）。

### ⚪ R6（非冗余，仅记录澄清）：actor_contexts 的 system 字段重复

初看 24 个 `actor_contexts` 里 20 个 value 都是 `{system, additional_instructions, format_examples_ref}`，疑似「system prompt 存了 20 遍」。**实测 `system` 字段只有 45 字符**（是短引用/ID，不是大段 prompt），20 份重复仅 855 字符冗余，**可忽略**。`additional_instructions` 有 18 个唯一值（每个候选 skill 不同），是必要的。

---

## 4. 体积归因（teacher-1 为例，226,638 字符）

| 区块 | 字符数 | 占比 | 业务必要性 | 冗余判定 |
|---|---|---|---|---|
| pages（含 AX 快照） | ~64,253 | 28% | 中（初始/中途页面视图） | 🟠 R2 双格式 + 内部重复 |
| content_blocks | ~56,704 | 25% | 中 | 🔴 R1 内联元数据 + R2 |
| attempts.events | 54,704 | 24% | **高（核心证据）** | 保留 |
| teacher_shared_texts 池 | 21,480 | 9% | 中 | 🟠 R3 与 skill 双轨 |
| retrieved_skills + 候选 skill | ~8,000 | 4% | 高 | 保留（但同质） |
| actor_contexts | ~15,853 | 7% | 低 | 🟡 R4/R5 引用层 |
| common_capabilities + common_rules | ~3,596 | 2% | 中 | 🟡 R5 |
| system 消息 | 4,349 | 2% | 高 | 保留 |

**核心结论**：`attempts.events`（24%）和 system 提示词（2%）是无可争议的必要信息。约 **55% 的体积集中在「页面快照的双格式/重复副本 + 观察元数据逐块内联 + skill 文本双轨投影」**，这些正是结构性冗余的主要来源，也是压缩空间所在。

---

## 5. 建议的优化方向（对齐业务目标，不做无谓删减）

1. **观察元数据只发 delta（R1）**：`# Current view` 里把 `observation_version` / `displayed` / `uncaptured_or_pending` / `matching` 等跨 read 不变的字段提到请求级常量，每个 content_block 只保留 `covered_ranges` / `omissions` / `continuation` / `last_action_error` 等真正变化的字段。预计可省 ~8K 字符/文件。

2. **页面快照统一为单一格式 + 去重（R2）**：DOM 文本与 AX 树二者选一（或按「skill 修订只需 role/label」裁剪），并对 p1/p4、b4/b7、b2/b9 这类重复副本按内容哈希去重。预计可省 ~30K 字符/文件。

3. **候选 skill 单一存储（R3）**：候选 skill 完整文本只在 `attempts[].skill` 结构化保留，`teacher_shared_texts` 里的 `# Applicable skills` 改为 `teacher_text_ref` 引用，不再投影第二遍。

4. **格式示例收敛为一份（R4）**：顶层 `format_examples` 去重（fe[1..3] 合并），删除 t19/t20 的重复展开。

5. **引用层扁平化（R5）**：单 toolset / 单 prompt 的场景下，`available_tools` / `actor_system_prompts` 直接内联内容，去掉 `_ref` 间接层（当前 `_ref` 没省 token，反而多一层）。

6. **（可选）retrieved_skills 去同质化（R3）**：当候选全失败、检索结果又与候选同质时，可考虑只保留对修订有差异贡献的参考 skill，避免 teacher 被 10+ 条语义雷同的 skill 条目干扰。

> 说明：以上 1–5 是纯结构性压缩，不损失 teacher 判断所需的任何业务信息；第 6 项涉及检索策略，需结合上游检索逻辑决策，不属本报告「结构性冗余」范畴，仅列为可选。
