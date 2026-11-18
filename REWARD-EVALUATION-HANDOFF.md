# 奖励评估交接文档（Reward Evaluation Handoff）

> 用途：把「评分准则设计方案」与「全部 1983 道题的逐题评分准则」整理成交接说明，供实现评估的 agent 独立消费。
> 本文只说明**判定规则与方法**，不实现奖励计算；计算公式 `R = null / 0 / base + (1-base)·Q` 由评估实现层落地。

---

## 0. 交接对象与范围

| 项 | 内容 |
|---|---|
| 任务 | 对 1983 道训练任务题，按统一准则输出每题的可操作评分准则（gate + quality），供评估器逐题判定 |
| 题目规模 | **1983 = binary 497 + non-binary 161 + remaining 1325**（逐题独立判分，无合并） |
| 输入（源清单） | `docs/reward-inventory/` 下 3 个文件（已跟踪入库） |
| 产出（准则） | 3 个最终总文档 + 1 个方案约束 + 1 个统计（见 §3） |
| 最高约束 | `reward-criteria-reminder.md`（§0 的 P1–P5 原则不可违背） |

---

## 1. 评分准则设计方案（方法论，全局适用）

### 1.1 核心原则 P1–P5（最高优先级，违反即评审不通过）

- **P1 门控优先**：gate 是硬前提的合取；任一门控明确为假 → 该题 **0**；证据不足且无法确认 → **null**（不转 0、不转失败）。
- **P2 质量后置**：质量维度（Q）**仅在 gate 通过后**计算；权重和 = 1.0；gate 未过不进入质量评分。
- **P3 禁止拆硬前提**：不得把「选对对象 / 做对动作 / 保存生效」中的任何一项拆成独立分数（如「选对产品 0.5 + 改对字段 0.5」）。
- **P4 三类不可信结果一律不给分**：① 页面有效但答案错；② 标题对但用户名错（多字段题只对一半）；③ 选了目标值但未保存/未生效。
- **P5 不冲突**：gate 条件必须 **1:1 映射**源清单的原生判定谓词（`persisted_requested_value` / `exact_result_set` / `answer_<字段>` 等），不得放宽、不得另立标准、不得把点击/过程/已知题面内容当奖励。

### 1.2 二段式结构：gate + quality

每题准则固定为「**成功门控条件（gate）** + **质量维度（quality）**」二段：

- **gate**：硬前提合取（G1..Gn），任一为假 → 0，证据不足 → null。映射原生判定谓词。
- **quality**：gate 通过后才计分的质量维度（Q1..Qn），每维度带权重与 0.0/0.5/1.0 三档锚点（可插值）。

**奖励计算公式（由评估实现层落地，准则文档不规定 base 具体数值）：**

```
R = null            （任一 gate 证据不足且无法确认）
R = 0               （任一 gate 明确为假）
R = base + (1-base)·Σ(wᵢ·qᵢ)   （gate 全通过；base 为门控基础分，qᵢ∈[0,1]）
```

### 1.3 权重方案（方案 B，两套已登记，权重和恒 = 1.0）

| 类型 | 维度与权重 | 适用 |
|---|---|---|
| **query 型** | 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15 | 查询/下载/导出/导航类只读题 |
| **write 型** | 操作范围 0.35 / 验证规范 0.30 / 保存确认 0.20 / 证据充分性 0.15 | 更新/创建/批量更新/发送类写题 |

- remaining 1325 题为单目标原子任务，**gate 通过即 1、无质量维度**，不引入第三套权重。

### 1.4 三态布尔与空结果（通用规则，全库适用）

- **三态布尔**：`false`（记录存在、属性确为假 → 合法答案）；记录不存在（按题面语义判 false 或空集）；未找到/证据不足（→ **null**，不得默认记 false）。**把 false 判失败、或把未找到记 false，均违反 P1/P5。**
- **空结果合法性**：题面允许空集且空集与本地真实状态一致 → 合法，不判 0；例外：题面明确要求非空而返回空集 → gate 不通过。

### 1.5 重复题处理（3 组 7 题）

| 组 | 题号（task_id） | 处理 |
|---|---|---|
| A | #21 = #182 | 各自独立判分；#182 引用 #21 准则（不重复设计） |
| B | #45 = #76 = #148 | 各自独立判分；#76/#148 复用 #45（正文标注「准则复用，不展开」） |
| C | #451 = #452 | 各自独立判分，复用同一准则 |

规则：每组各 task_id **独立判分、不合并**；准则复用而非重复设计；不因重复而放宽/收紧。

### 1.6 atomicity 显式声明

每题均需声明 `atomicity: { is_atomic, reason }`，说明为何题面的多字段/多步骤/多目标属于同一原子任务、不可拆成多个奖励。**多字段原子题**（如 name+SKU、title+username、refunded+customer 等联合查询）必须声明为同一原子。

### 1.7 判定谓词清单（gate 1:1 映射来源）

`persisted_requested_value`（字段最终值满足 update_matches）/ `exact_result_set`（集合无遗漏/无多余/无重复）/ `answer_<字段>`（查询字段精确匹配）/ `downloaded_correct_documents` / `new_matching_record_saved` / `all_selected_records_updated` / `downloaded_matching_csv` / `new_matching_mail_delivered` / `reached_menu` / `correct_page` / `correct_partner_description` / `records_unchanged` / `requested_records_unchanged` / `same_local_deployment` / `valid_authenticated_page` / `answer_schema` / `page_valid` 等。**不得另立标准**。

---

## 2. 全部题目的修改方案（逐题准则的产生逻辑）

> 三份总文档的共性：**不改变题目本身的判定结果（1/0/null 三态），只把判定准则结构化、原子化、可操作化**；gate 一律 1:1 映射源清单原生判定字段，不新增谓词。

### 2.1 binary 497 题 —— 二值判定「细分」为 gate + quality

- **源**：`docs/reward-inventory/binary-reward-tasks.md`（497 题，已含 native contract / answer 明细）。
- **修改方案**：把二值判定**细分**为「gate 硬门控 + quality 质量维度」二段式，让判定可逐条复核。
- **构成**：62 admin_contract + 136 ordinary_query（answer 明细）+ 299 ordinary_query（native_contract）。
- **权重**：query 型 / write 型两套（见 §1.3）。
- **特殊处理**：54 题 `status=ready` 优先；245 题 draft/candidate 标注「临时准则，contract 可能变更」；3 题创建 GitLab 组的写操作（#454/#455/#456）套 write 型而非只读导航。
- **产出**：`reward-criteria-decomposition-binary.md`（497 题总文档，合并批0–5）。

### 2.2 non-binary 161 题 —— 按 P1「重写」，废弃固定分母

- **源**：`docs/reward-inventory/non-binary-reward-tasks.md`（161 题，原为「固定分母 N」口径）。
- **修改方案**：原「固定分母 N」（漏 1 字段 → (N-1)/N 的半对分）**不作为口径基准**；按 §1.1 P1 **重写**为「gate 全对 + 质量分」：任一字段/目标错 → 0，不按 N 逐字段给部分分。
- **分支（10 个）**：6 复用（update/create/query/collection_query/pdf/ordinary_query）+ 4 新增（export/bulk_update/page_text_query/mail）。
- **典型对照**：#9 导出 CSV 原分母 140、#36 原分母 616，P1 下「漏 1 行 → 0」而非 0.993/0.999。
- **产出**：`reward-criteria-decomposition-non-binary.md`（161 题总文档，框架全文自包含）。

### 2.3 remaining 1325 题 —— native contract 字段「抽取」为 gate（28 门控族）

- **源**：`docs/reward-inventory/remaining-training-tasks.md`（1325 题，二值基线：完整满足 contract 记 1，否则 0，unknown/null）。
- **修改方案**：把每题 native contract 的具体判定字段（spec.* / completion.* / control_target_path / wrong_target_path 等）**抽取**为 gate，按门控族（gate family）归组，族给通用框架、逐题填具体条件值。
- **口径**：单目标原子任务，**gate 通过即 1，无质量维度、无权重**（不产生第三套权重）。
- **门控族（28 族）**：goal_only 502 / heading_path_nav 199 / map_obj_nav 100 / list_obj_nav 85 / page_nav 72 / title_path_nav 59 / gitlab_repo_nav 54 / menu_nav 52 / family_bridge 43 / gitlab_issuable 21 / admin_page 19 / admin_navigate 27 / admin_generic 17 / 其余 admin 各操作族 + gitlab_section/project_dir 等 ≤14。
- **产出**：`reward-criteria-decomposition-remaining.md`（1325 题总文档，§2 门控族框架库 + §3 逐题清单）。

### 2.4 规模统计（详见 `reward-criteria-statistics.md`）

- 门控准则数（G1..Gn）：全局 **max 7 / min 0（2 题复用，等效 1）/ mean 3.05 / median 3 / 众数 2**；P25=2 / P75=5。
- 分文档：binary mean 5.15、non-binary mean 5.16、remaining mean 2.01。呈「导航类 1–3 条 + 写操作/多字段查询类 5–6 条」双峰。
- 质量维度：0 项 1508 题（含 remaining 全部 1325），4 项 475 题。

---

## 3. 文件清单与依赖

### 3.1 输入 · 源清单（3 个，已入库跟踪）

| 文件 | 题数 | 说明 |
|---|---|---|
| `docs/reward-inventory/binary-reward-tasks.md` | 497 | binary 二值判定源 |
| `docs/reward-inventory/non-binary-reward-tasks.md` | 161 | 原「固定分母」源（非基准） |
| `docs/reward-inventory/remaining-training-tasks.md` | 1325 | 二值基线源（含 native contract） |

### 3.2 方案约束（1 个）

- `reward-criteria-reminder.md` —— P1–P5、重复题、atomicity、格式 schema、权重 rationale、执行顺序、回归清单（**最高约束，实现评估须先读此文件**）。

### 3.3 逐题准则 · 最终总文档（3 个，本次交付核心）

| 文件 | 题数 | 结构 |
|---|---|---|
| `reward-criteria-decomposition-binary.md` | 497 | 批0–5 合并；批0 为 JSON schema，批1–5 为散文 |
| `reward-criteria-decomposition-non-binary.md` | 161 | §0 范围 / §1 P1 / §2 分支框架（自包含）/ §3 逐题 |
| `reward-criteria-decomposition-remaining.md` | 1325 | §0 范围 / §1 P1 / §2 门控族框架库 / §3 逐题 |

### 3.4 统计（1 个）

- `reward-criteria-statistics.md` —— 1983 题评分准则数量的 max/min/median/mean 等分布。

### 3.5 过程批次（6 个，已并入 binary 总文档，供追溯）

- `reward-criteria-decomposition.md`（批0，11 题，JSON 格式基准）
- `reward-criteria-decomposition-batch1-update.md`（update 型 26 题）
- `reward-criteria-decomposition-batch2-collection-query.md`（collection_query 13 题）
- `reward-criteria-decomposition-batch3-query-links-pdf.md`（query/links/pdf/create/draft_reset 16 题）
- `reward-criteria-decomposition-batch4-ordinary-query-answer.md`（answer 明细 132 题）
- `reward-criteria-decomposition-batch5-native-contract.md`（native_contract 299 题）

---

## 4. 给实现评估 agent 的消费接口

### 4.1 建议消费顺序

1. 先读 `reward-criteria-reminder.md`，吃透 P1–P5、三态、空集、重复题、权重两套。
2. 读对应总文档的 §0/§1/§2（框架），再读 §3 逐题清单。
3. 判定某题时：以**总文档的 gate/quality 为判定逻辑**，以**源清单的 native contract 为具体字段值来源**。

### 4.2 单题判定流程（伪代码）

```
读取该题 gate 列表（G1..Gn）
for g in gate:
    判定 g：
        明确为假   → return R = 0
        证据不足无法确认 → return R = null
gate 全通过：
    if 该题无质量维度（remaining / 原子任务）:
        return R = 1
    else:
        Q = Σ(wᵢ · qᵢ)，qᵢ 按三档锚点 0.0/0.5/1.0 可插值
        return R = base + (1-base)·Q    # base 由实现层定义
```

### 4.3 关键边界（实现时必须遵守）

- **不得把 null 转 0 或转失败**；不得把 false 判失败；不得把「未找到」记 false。
- **不得按字段份额给分**（如 6/7、139/140）：多字段/多目标题任一错 → 0（P3/P4）。
- **不得把过程步骤当奖励**（点进正确页面但答案错 → 0）。
- **权重只允许两套已登记值**，不允许出现第三套。
- 复用题（#76/#148/#182 等）**各自独立判分**，但准则引用不重复实现。

### 4.4 遗留与注意

- 源清单 `non-binary` 的「固定分母」为另一 AI 版本，**不作裁定项**，判定一律以 P1 为准。
- remaining 中 draft/candidate contract 标注「临时准则，可能变更」，实现时需容忍 contract 字段缺失（缺失时以题面 + `goal_revision.derived_goal` 为唯一目标来源，不臆造谓词）。
- `answer_<字段>` 占位符：源清单只给 `path`+`sha256`、未给具体字段名的题（non-binary 中 query 6 题 + ordinary_query 13 题）保留占位符，实现时靠题面 + `answer_schema` 定位字段，**不臆造字段名**。
