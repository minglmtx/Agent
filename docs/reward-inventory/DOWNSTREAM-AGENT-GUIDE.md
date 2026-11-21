# 下游 Agent 工作指引：冗余分析复核 + 评分准则成果接入

> 用途：本文件是给「接手后续工作的另一个 Agent」看的提示词/工作指引。
> 它有两件独立任务，请按顺序完成，不要混在一起。

---

## 任务一：复核冗余分析报告，结合项目代码做「去冗余」的落地设计

### 1. 先读参考报告（仅作参考，不是结论）

先阅读 `docs/reward-inventory/sku-teacher-api-redundancy-report.md`。

这份报告分析了 `sku-teacher-1-prompt.md` / `sku-teacher-2-prompt.md` 两个 Teacher API 请求的结构性冗余，结论摘要：

1. **R1** 观察元数据逐块内联：每个 read 操作完整重发 `# Current view` 的 observation JSON，其中 `observation_version`/`displayed`/`uncaptured_or_pending` 等跨 read 不变字段是浪费。
2. **R2** 页面快照双格式并存（DOM 文本 + AX 树），且 pages/content_blocks 内部有重复副本未去重。
3. **R3** 候选 skill 文本在 `attempts[].skill`（结构化）和 `teacher_shared_texts` 的 `# Applicable skills` 块（文本投影）双轨存储。
4. **R4** 格式示例三重复（顶层 `format_examples` 的 fe[1..3] 相同 + t19/t20 再展开）。
5. **R5** 单 toolset/单 prompt 场景下 `_ref` 间接层空转，没省 token。

报告里也标出了**必要信息（不可删）**：`attempts.events`、system 提示词、`retrieved_skills`、`generator_planning_view`。

**重要：报告只是参考，不代表结论正确或完整。** 报告作者是基于「两个已导出的请求文件」做的静态分析，没有看到生成这些请求的上游代码。

### 2. 结合项目代码，具体情况具体分析

请在你的工作区里找到**生成这两个 Teacher 请求的上游代码**（大概率不在本仓库——本仓库是纯文档仓库，只有 markdown）。定位到构造 `teacher_shared_texts` / `content_blocks` / `pages` / `actor_contexts` / `format_examples` 这些字段的代码后，逐条核对报告结论：

- **对每条 R1–R5，验证它是否成立**：报告说「重复」的地方，在代码里到底是「故意设计」还是「实现疏漏」？
  - 例如：`teacher_shared_texts` 这套引用机制本来就是去重设计，报告作者也承认引用机制在生效。那「去重不彻底」的具体原因是什么？是分片粒度、是快照格式切换、还是历史遗留？
  - 例如：页面快照的 DOM 文本 vs AX 树，是否是**下游 Teacher 模型真的需要两种视图**（DOM 用于理解可见文本，AX 用于理解可点击控件的 role/label）？如果是，删掉一种会损害 Teacher 的判断能力，那就不该删，而是做「按需加载/分片」。
- **判断哪些冗余是「可安全消除」、哪些是「有业务代价」**：
  - 可安全消除：字节级重复（fe[1..3]、p1/p4、b4/b7 等）、跨 read 不变的元数据字段。
  - 有业务代价：任何会改变 Teacher 可见信息集的改动，都要先评估对 skill 修订质量的影响。
- **产出落地方案**：给出具体的改造点（改哪个函数、哪个字段结构、预期省多少 token），而不是泛泛的「去重」。如果发现报告有误判，请明确指出并纠正。

### 3. 交付要求（任务一）

输出一份《去冗余落地设计》，包含：
- 逐条 R1–R5 的「成立/不成立/部分成立」判定 + 代码依据（文件路径 + 关键片段）；
- 报告遗漏的冗余点（若有）；
- 可安全消除的清单（预期节省量）；
- 有业务代价、需谨慎的清单（代价说明）；
- 建议的改造顺序（先做零风险项）。

---

## 任务二：接入「奖励评分细分准则」成果，复用解析代码

### 1. 成果说明

仓库里已经有另一块成果：把 1983 道题的评分准则从「gate + quality 二段式」重构为「纯 gate 语义组细分」。产物如下（均位于 `docs/reward-inventory/`）：

| 文件 | 作用 |
|---|---|
| `gates.json` | 机器可读主产物，1983 题，每题含 `task_id` / `statement` / `branch` / `src` / `gates[]` / `implicit_preconditions` |
| `gates.md` | 人类可读版本，内容与 `gates.json` 一致 |
| `build_gates.py` | 生成引擎：从三份源清单（`binary-reward-tasks.md` / `non-binary-reward-tasks.md` / `remaining-training-tasks.md`）逐题提炼 gate |
| `gates_loader.py` | 供下游消费的解析器，**请直接用它，不要重复造轮子** |

**核心口径（务必理解，避免误用）：**
- 一道题 = 一组 gate（G1..Gn），**每条 gate 独立判对错**。
- **分值由下游按「通过条数」计算**，`gates.json` / `gates.md` 里**不含公式、不掺分值**。
- 一条 gate = 一个「语义组」：彼此语义独立、题目确实要求独立判断的才拆成独立 gate；天然一体的字段（如地址）合并为一条。
- 隐含前提（`page_valid` / `answer_schema` / `records_unchanged` 等）**不占 gate 分数**，仅作题目级说明列出。

### 2. 直接用 gates_loader.py，不要自己解析

`gates_loader.py` 已经封装好了读取逻辑，无需理解 `gates.json` 的内部结构就能使用：

```python
from gates_loader import load_gates, gates_by_id, gate_count, score_by_passed, summary

data = load_gates()                  # list[dict]，1983 题
item = gates_by_id(data, "<task_id>")  # 取单题
n = gate_count(item)                 # 该题 gate 条数（计分分母）
score = score_by_passed(item, passed) # 按通过条数计分（0~1 线性，仅示例）

s = summary(data)                    # 整体统计：总题数 / 各来源题数 / gate 条数分布
```

说明：
- `gates_loader.py` 会自动定位 `gates.json`（同目录或 `output/` 子目录），放在 `docs/reward-inventory/` 下直接可用。
- 计分函数 `score_by_passed` 只是示例（线性按条数占比）。**你实现正式计分时，可以替换成任意规则**，但它演示了「读题 → 数 gate → 按通过条数算」的最小闭环。

### 3. 如果你要重新生成 gates（可选）

`build_gates.py` 已做路径自适应：放在 `docs/reward-inventory/` 下运行，会以同目录的源清单为输入、输出到同目录的 `output/`；放在仓库根目录运行，则以 `docs/reward-inventory/` 为输入、输出到根目录 `output/`。

```bash
python build_gates.py   # 重跑后覆盖生成 gates.json / gates.md
```

### 4. 交付要求（任务二）

- 确认你能用 `gates_loader.py` 读到 1983 题、并按 task_id 取到任意一题的 gate 列表；
- 说明你打算如何消费这份成果（例如：下游计分器怎么用 gate 条数 + 通过条数算分）；
- 若发现 `gates.json` 与你的计分口径有出入，反馈具体的题号和分歧点，不要静默改数据。

---

## 附：本指引涉及的关键文件清单

- `docs/reward-inventory/sku-teacher-api-redundancy-report.md` —— 任务一的参考报告
- `docs/reward-inventory/sku-teacher-1-prompt.md` / `sku-teacher-2-prompt.md` —— 被分析的请求
- `docs/reward-inventory/gates.json` / `gates.md` —— 评分准则成果
- `docs/reward-inventory/gates_loader.py` —— 任务二请直接复用
- `docs/reward-inventory/build_gates.py` —— 生成引擎
- `docs/reward-inventory/binary-reward-tasks.md` / `non-binary-reward-tasks.md` / `remaining-training-tasks.md` —— 三份源清单
