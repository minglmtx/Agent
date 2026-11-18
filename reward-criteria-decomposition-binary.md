# 子奖励判断准则 · binary 497 题（交接总文档）

> 本文为 binary（二值）497 题的子奖励判断准则**交接总文档**，由批0–批5 六份文档按顺序合并而成。
> 只做**判定准则的细分与可操作化**，不实现奖励计算、不重设计奖励方案；计算公式 `R = null / 0 / base + (1-base)·Q` 由计算层实现。
> 本总文档与各分批文件内容一致，仅供最终交接归档使用；判定规则以 `reward-criteria-reminder.md` 为最高约束。

## 批次索引（497 = 11 + 26 + 13 + 16 + 132 + 299）

| 批次 | 覆盖分支/范围 | 题数 |
|---|---|---|
| 批0 · 通用约定 + 首批 11 题（update/collection_query/links/ordinary_query 各若干） | 11 |
| 批1 · update 型剩余 26 题 | 26 |
| 批2 · collection_query 型剩余 13 题 | 13 |
| 批3 · query/links/pdf/create/draft_reset 共 16 题 | 16 |
| 批4 · ordinary_query answer 明细 132 题 | 132 |
| 批5 · ordinary_query native_contract 299 题 | 299 |

**合计 497 题。**


---

<!-- ===== reward-criteria-decomposition.md ==== -->

# 子奖励判断准则细分(Gate + Quality 二段式)

> 本文只做**判定准则的细分与可操作化**,不实现奖励计算。
> 计算公式 `R = null / 0 / base + (1-base)·Q` 已由计算层实现,base 数值不在本文范围内。
> 本文产出:每道题的 gate(硬前提合取)、quality(Q 维度+锚点+观察方式)、do_not_do、unknown_handling。

## 0. 通用约定(所有题适用)

- **gate 通用前提**:`page_valid`(页面有效可用)、`answer_schema`(答案格式符合 schema)是所有题隐含的硬前提,题目自身 gate 中不再重复列出,但判定时必须同时满足。
- **gate 语义**:合取;任一硬前提明确为假 → 该题 R=0。任一关键项证据不足且无法确认 → 该题 R=null(不转失败、不转 0)。
- **Q 语义**:仅在 gate 通过后计算;只评 gate 未保证的过程质量;维度权重求和 = 1.0;每维度 0.0/0.5/1.0 三档锚点,可插值。
- **原子性**:UI 多步、多字段、多过滤条件属于同一 gate/同一组验证,不各自发分。写操作的"编辑"与"保存"是同一赋值的两阶段,不拆。
- **停止条件**:写操作确认生效后停;查询确认结果集闭合后停;不重复执行、不额外探索。
- **证据来源**:只使用 recorded observations(页面状态、提交 payload、保存后状态、返回结果集);不得臆造后续才出现的答案。

---

## 1. 题目 12(0c7e5b3b68c71acc9776)— Yoga Mat Pro tax class → None 并保存

```json
{
  "task_id": "0c7e5b3b68c71acc9776",
  "statement": "Set the tax class of product 'Yoga Mat Pro' to None and save.",
  "atomicity": {"is_atomic": true, "reason": "tax class 赋值与保存是同一写操作的两个阶段,不拆成独立奖励"},
  "gate": [
    {"cond": "操作目标产品为 'Yoga Mat Pro'", "required": true, "check": "操作对象 product.title == 'Yoga Mat Pro',非同名其他产品"},
    {"cond": "该产品 tax class 字段最终值为 'None'", "required": true, "check": "提交后 product.tax_class 显示 'None'"},
    {"cond": "赋值已提交并确认生效", "required": true, "check": "存在 save 动作;保存后重新查看/刷新,tax class 仍为 'None'"},
    {"cond": "未修改无关字段", "required": true, "check": "price/stock/description 等字段操作前后无 diff"}
  ],
  "quality": [
    {"name": "操作范围", "weight": 0.35, "measures": "只操作该产品 tax class,无无关探索/无关产品页/无关字段修改",
     "anchors": {"0.0": "打开并修改了其他产品或其他字段,或大量无关页面探索", "0.5": "有少量无关浏览或打开过其他产品但未修改", "1.0": "只定位目标产品并仅改 tax class,无冗余动作"},
     "observe": "遍历 recorded events,统计非目标产品/非目标字段的操作次数"},
    {"name": "验证规范", "weight": 0.30, "measures": "提交前显式核对产品名与 tax class 值,而非盲选下拉第一项",
     "anchors": {"0.0": "直接盲选,无可观察的核对动作", "0.5": "只核对产品名或只核对 tax class 值", "1.0": "提交前同时确认产品身份与目标值 'None'"},
     "observe": "检查提交前是否有读取/确认 product.title 与 tax_class 的记录"},
    {"name": "保存确认", "weight": 0.20, "measures": "有显式保存成功反馈或保存后重新打开确认",
     "anchors": {"0.0": "未执行保存或保存失败", "0.5": "执行了 save 但未确认生效", "1.0": "保存后再次查看/刷新确认仍为 'None'"},
     "observe": "检查是否有 save 事件 + 保存后状态复查事件"},
    {"name": "证据充分性", "weight": 0.15, "measures": "关键结论有可见页面证据",
     "anchors": {"0.0": "无任何页面证据", "0.5": "有部分字段截图/值但不足以证明生效", "1.0": "tax class='None' 有可见字段值或页面截图证据"},
     "observe": "检查结论对应的字段值是否在 observation 中可见"}
  ],
  "do_not_do": [
    "不要把 '设为 None' 和 '保存' 拆成两个独立奖励(0.5/0.5)",
    "不要给 page_valid / answer_schema 单独发分(它们已在 gate)",
    "不要给 '成功定位到产品' 单独发分"
  ],
  "unknown_handling": [
    "无法验证 '保存后是否仍为 None'(无保存后状态记录)→ 该题 null",
    "无法确定目标产品是否 Yoga Mat Pro → null(除非已明确为假则 0)"
  ]
}
```

---

## 2. 题目 13(0ccd1578f5f6ddc7b11c)— Updated General Customers → Retail Customer 并保存

```json
{
  "task_id": "0ccd1578f5f6ddc7b11c",
  "statement": "Set tax class of customer group 'Updated General Customers' to 'Retail Customer' and save.",
  "atomicity": {"is_atomic": true, "reason": "与题12同型:tax class 赋值与保存是同一写操作的两阶段"},
  "gate": [
    {"cond": "目标客户组为 'Updated General Customers'", "required": true, "check": "操作对象 group.title == 'Updated General Customers'"},
    {"cond": "该组 tax class 字段最终值为 'Retail Customer'", "required": true, "check": "提交后 group.tax_class == 'Retail Customer'"},
    {"cond": "赋值已提交并确认生效", "required": true, "check": "存在 save 动作;保存后复查仍为 'Retail Customer'"},
    {"cond": "未修改无关字段/无关组", "required": true, "check": "操作前后其他字段、其他组无 diff"}
  ],
  "quality": [
    {"name": "操作范围", "weight": 0.35, "measures": "只操作该客户组 tax class,无无关探索",
     "anchors": {"0.0": "修改了其他组或其他字段,或大量无关探索", "0.5": "打开过其他组但未修改", "1.0": "只改目标组 tax class"},
     "observe": "统计非目标组/非目标字段操作次数"},
    {"name": "验证规范", "weight": 0.30, "measures": "提交前显式核对组名与 tax class 值",
     "anchors": {"0.0": "盲选无核对", "0.5": "只核对组名或只核对目标值", "1.0": "同时确认组身份与 'Retail Customer'"},
     "observe": "检查提交前是否有读取/确认 group.title 与 tax_class 的记录"},
    {"name": "保存确认", "weight": 0.20, "measures": "有显式保存反馈或保存后复查",
     "anchors": {"0.0": "未保存或失败", "0.5": "保存但未确认", "1.0": "保存后复查仍为目标值"},
     "observe": "检查 save 事件 + 保存后复查事件"},
    {"name": "证据充分性", "weight": 0.15, "measures": "结论有可见页面证据",
     "anchors": {"0.0": "无证据", "0.5": "部分证据", "1.0": "tax class='Retail Customer' 有可见字段值证据"},
     "observe": "检查目标字段值是否在 observation 可见"}
  ],
  "do_not_do": [
    "不要把 '改 tax class' 和 'save' 拆成两个独立评分",
    "不要给 page_valid / answer_schema 单独发分"
  ],
  "unknown_handling": [
    "无法验证保存后是否仍为 'Retail Customer' → null",
    "无法确定目标组是否 'Updated General Customers' → null(明确为假则 0)"
  ]
}
```

---

## 3. 题目 33(232a5983ed3010501724)— Blue T-Shirt tax class → None 并保存

```json
{
  "task_id": "232a5983ed3010501724",
  "statement": "Set the tax class of product 'Blue T-Shirt' to None and save.",
  "atomicity": {"is_atomic": true, "reason": "与题12/13同型:赋值+保存不拆"},
  "gate": [
    {"cond": "目标产品为 'Blue T-Shirt'", "required": true, "check": "操作对象 product.title == 'Blue T-Shirt'"},
    {"cond": "该产品 tax class 最终值为 'None'", "required": true, "check": "提交后 product.tax_class == 'None'"},
    {"cond": "赋值已提交并确认生效", "required": true, "check": "save 动作 + 保存后复查仍为 'None'"},
    {"cond": "未修改无关字段", "required": true, "check": "其他字段无 diff"}
  ],
  "quality": [
    {"name": "操作范围", "weight": 0.35, "measures": "只操作该产品 tax class",
     "anchors": {"0.0": "改其他字段/产品或大量无关探索", "0.5": "少量无关浏览", "1.0": "只改目标字段"},
     "observe": "统计非目标操作次数"},
    {"name": "验证规范", "weight": 0.30, "measures": "提交前核对产品名与 tax class 值",
     "anchors": {"0.0": "盲选", "0.5": "部分核对", "1.0": "同时确认产品身份与 'None'"},
     "observe": "检查提交前确认记录"},
    {"name": "保存确认", "weight": 0.20, "measures": "保存后确认生效",
     "anchors": {"0.0": "未保存", "0.5": "保存未确认", "1.0": "保存后复查仍为 'None'"},
     "observe": "save 事件 + 复查事件"},
    {"name": "证据充分性", "weight": 0.15, "measures": "结论有可见证据",
     "anchors": {"0.0": "无", "0.5": "部分", "1.0": "tax class='None' 可见"},
     "observe": "检查字段值可见性"}
  ],
  "do_not_do": [
    "不要拆 '改 tax class' 和 'save' 两个独立评分"
  ],
  "unknown_handling": [
    "无法验证保存后生效 → null"
  ]
}
```

---

## 4. 题目 21(170349164ca41b627be8)— Exclude Main Website from Updated General Customers 并保存

```json
{
  "task_id": "170349164ca41b627be8",
  "statement": "Exclude 'Main Website' from customer group 'Updated General Customers' and save.",
  "atomicity": {"is_atomic": true, "reason": "exclude 与 save 是同一修改的编辑与提交,不拆"},
  "gate": [
    {"cond": "目标组为 'Updated General Customers'", "required": true, "check": "操作对象 group.title == 'Updated General Customers'"},
    {"cond": "'Main Website' 在该组中已被排除(exclusion 存在)", "required": true, "check": "该组 exclusion 列表包含 'Main Website'"},
    {"cond": "已保存并确认生效", "required": true, "check": "save 动作 + 保存后复查 exclusion 仍在"},
    {"cond": "未修改无关组或无关网站", "required": true, "check": "其他组/其他网站 exclusion 无 diff"}
  ],
  "quality": [
    {"name": "操作范围", "weight": 0.35, "measures": "只操作该组 Main Website exclusion",
     "anchors": {"0.0": "改其他组/其他网站或无关探索", "0.5": "打开过其他组未改", "1.0": "只改目标 exclusion"},
     "observe": "统计非目标操作"},
    {"name": "验证规范", "weight": 0.30, "measures": "提交前确认组名与网站名",
     "anchors": {"0.0": "盲选", "0.5": "只核对组名或网站名", "1.0": "同时确认组与 'Main Website'"},
     "observe": "提交前确认记录"},
    {"name": "保存确认", "weight": 0.20, "measures": "保存后确认 exclusion 仍在",
     "anchors": {"0.0": "未保存", "0.5": "保存未确认", "1.0": "保存后复查 exclusion 存在"},
     "observe": "save + 复查事件"},
    {"name": "证据充分性", "weight": 0.15, "measures": "结论有可见证据",
     "anchors": {"0.0": "无", "0.5": "部分", "1.0": "exclusion 可见"},
     "observe": "exclusion 状态可见性"}
  ],
  "do_not_do": [
    "不要拆 'exclude' 和 'save' 两个独立评分(0.5/0.5)"
  ],
  "unknown_handling": [
    "无法验证保存后 exclusion 是否仍在 → null"
  ]
}
```

---

## 5. 题目 24(17d5e276fde02bf2afde)— Remove exclusion of Main Website 并保存

```json
{
  "task_id": "17d5e276fde02bf2afde",
  "statement": "Remove the exclusion of 'Main Website' for customer group 'Updated General Customers' and save.",
  "atomicity": {"is_atomic": true, "reason": "与题21同型但方向相反(移除 exclusion);两者是独立原子题,不合并"},
  "gate": [
    {"cond": "目标组为 'Updated General Customers'", "required": true, "check": "操作对象 group.title == 'Updated General Customers'"},
    {"cond": "'Main Website' 的 exclusion 已被移除", "required": true, "check": "该组 exclusion 列表不再包含 'Main Website'"},
    {"cond": "已保存并确认生效", "required": true, "check": "save 动作 + 保存后复查 exclusion 已不存在"},
    {"cond": "未修改无关组或无关网站", "required": true, "check": "其他 exclusion 无 diff"}
  ],
  "quality": [
    {"name": "操作范围", "weight": 0.35, "measures": "只操作该组 Main Website exclusion",
     "anchors": {"0.0": "改其他对象或无关探索", "0.5": "少量无关浏览", "1.0": "只改目标 exclusion"},
     "observe": "统计非目标操作"},
    {"name": "验证规范", "weight": 0.30, "measures": "提交前确认组名与网站名",
     "anchors": {"0.0": "盲选", "0.5": "部分核对", "1.0": "同时确认组与 'Main Website'"},
     "observe": "提交前确认记录"},
    {"name": "保存确认", "weight": 0.20, "measures": "保存后确认 exclusion 已移除",
     "anchors": {"0.0": "未保存", "0.5": "保存未确认", "1.0": "保存后复查 exclusion 不存在"},
     "observe": "save + 复查事件"},
    {"name": "证据充分性", "weight": 0.15, "measures": "结论有可见证据",
     "anchors": {"0.0": "无", "0.5": "部分", "1.0": "exclusion 移除状态可见"},
     "observe": "exclusion 状态可见性"}
  ],
  "do_not_do": [
    "不要拆 'remove exclusion' 和 'save' 两个独立评分",
    "不要把题21与题24合并为一道题(方向相反,最终状态不同)"
  ],
  "unknown_handling": [
    "无法验证保存后 exclusion 是否已移除 → null"
  ]
}
```

---

## 6. 题目 39(2bf4131ca3f524bf5b2e)— Assign 'Sony Headphones' to 'Electronics'

```json
{
  "task_id": "2bf4131ca3f524bf5b2e",
  "statement": "Assign product 'Sony Headphones' to category 'Electronics'.",
  "atomicity": {"is_atomic": true, "reason": "一个产品—分类关系赋值,原子写操作"},
  "gate": [
    {"cond": "目标产品为 'Sony Headphones',未擅自新建同名产品", "required": true, "check": "操作对象为已存在的 product.title=='Sony Headphones',非新建"},
    {"cond": "目标分类为 'Electronics'", "required": true, "check": "提交后该产品 category == 'Electronics'"},
    {"cond": "赋值已提交", "required": true, "check": "存在提交/保存动作"},
    {"cond": "保存后确认该产品归属 'Electronics'", "required": true, "check": "保存后复查 category == 'Electronics'"},
    {"cond": "未修改无关字段", "required": true, "check": "其他属性无 diff"}
  ],
  "quality": [
    {"name": "操作范围", "weight": 0.35, "measures": "只操作该产品的分类字段,不改其他属性、不打开无关产品",
     "anchors": {"0.0": "改其他属性/产品或无关探索", "0.5": "打开过其他产品未改", "1.0": "只改目标分类"},
     "observe": "统计非目标操作"},
    {"name": "验证规范", "weight": 0.30, "measures": "提交前确认产品标题与分类名",
     "anchors": {"0.0": "盲选下拉第一项", "0.5": "只核对产品或分类", "1.0": "同时确认产品与 'Electronics'"},
     "observe": "提交前确认记录"},
    {"name": "保存确认", "weight": 0.20, "measures": "保存后确认归属",
     "anchors": {"0.0": "未保存", "0.5": "保存未确认", "1.0": "保存后复查 category=='Electronics'"},
     "observe": "save + 复查事件"},
    {"name": "证据充分性", "weight": 0.15, "measures": "结论有可见证据",
     "anchors": {"0.0": "无", "0.5": "部分", "1.0": "归属关系可见"},
     "observe": "归属字段可见性"}
  ],
  "do_not_do": [
    "不要拆 '选对产品 0.5' / '选对分类 0.5' 两个独立奖励",
    "不要把 '新建同名产品' 视为等价成功"
  ],
  "unknown_handling": [
    "无法验证保存后归属 → null",
    "无法确定是已存在产品还是新建 → null"
  ]
}
```

---

## 7. 题目 15(0e67c52509e468a02665)— Find all female customers with January birthdays

```json
{
  "task_id": "0e67c52509e468a02665",
  "statement": "Find all customers who are female and have birthdays in January.",
  "atomicity": {"is_atomic": true, "reason": "female 与 January 是两个并列过滤条件,属同一 conjunctive query,不是两个任务"},
  "gate": [
    {"cond": "返回完整匹配集合:所有 gender=female 且 birth_month=January 的客户", "required": true, "check": "结果集与本地全部客户记录比对,无遗漏"},
    {"cond": "无多余结果", "required": true, "check": "结果集中不含 male、不含非一月生日"},
    {"cond": "结果字段与格式符合 schema", "required": true, "check": "字段/格式满足 answer_schema"},
    {"cond": "requested_records_unchanged(只读,未改数据)", "required": true, "check": "无任何写操作"}
  ],
  "quality": [
    {"name": "完整性", "weight": 0.35, "measures": "穷尽结果集,未找到一个就停",
     "anchors": {"0.0": "只返回第一个匹配就停止", "0.5": "返回部分但未翻页/未闭合", "1.0": "翻页/继续读取直至结果集闭合"},
     "observe": "检查是否有翻页/继续读取动作直至结束"},
    {"name": "搜索条件准确性", "weight": 0.30, "measures": "两个过滤条件都正确应用,未放宽或混淆",
     "anchors": {"0.0": "条件错误(如 female 与 male 混用、January 写成错误值)", "0.5": "一个条件正确一个错误", "1.0": "两个条件均正确"},
     "observe": "检查搜索/过滤条件设置与题面一致"},
    {"name": "来源合规", "weight": 0.20, "measures": "结果来自本地客户记录",
     "anchors": {"0.0": "依赖推测或外部数据", "0.5": "部分来自本地", "1.0": "全部来自本地记录"},
     "observe": "检查结果是否来自本地客户列表"},
    {"name": "证据充分性", "weight": 0.15, "measures": "计数/列表有可见记录支撑",
     "anchors": {"0.0": "无记录支撑", "0.5": "部分记录可见", "1.0": "列表/计数有完整可见记录"},
     "observe": "检查结果列表可见性"}
  ],
  "do_not_do": [
    "不要拆成 '找 female' 和 '找 January' 两个独立评分",
    "不要把单独满足一个条件视为成功子集"
  ],
  "unknown_handling": [
    "无法确认结果集是否穷尽(如无法访问完整客户列表)→ null"
  ]
}
```

---

## 8. 题目 31(210e2c5cf187dea57672)— Byte Blaze/empathy-prompts open MR 数

```json
{
  "task_id": "210e2c5cf187dea57672",
  "statement": "How many open merge requests does the project 'Byte Blaze/empathy-prompts' have?",
  "atomicity": {"is_atomic": true, "reason": "group/project 路径指向单一项目,是单项目 open MR 总量计数,不拆成两个项目分别计数"},
  "gate": [
    {"cond": "正确识别项目路径为 'Byte Blaze/empathy-prompts'(同一项目)", "required": true, "check": "未把 group 名与 project 名误当两个项目"},
    {"cond": "返回的 open merge requests 数量准确", "required": true, "check": "计数与该项目当前 open 列表总数一致"},
    {"cond": "计数只含 open,未混入 closed/merged", "required": true, "check": "结果集状态过滤 == open"},
    {"cond": "结果格式符合 schema", "required": true, "check": "数字/格式满足 answer_schema"}
  ],
  "quality": [
    {"name": "项目识别准确性", "weight": 0.35, "measures": "未把 group 与 project 误当两个项目,未打开同组其他项目",
     "anchors": {"0.0": "当成两个项目分别计数或打开错误项目", "0.5": "识别对了但打开过同组其他项目", "1.0": "准确锁定单一项目"},
     "observe": "检查访问的项目路径是否唯一且正确"},
    {"name": "计数完整性", "weight": 0.30, "measures": "穷尽 open 列表或确认数量来源",
     "anchors": {"0.0": "只数当前页", "0.5": "部分翻页未闭合", "1.0": "穷尽列表或确认总数来源"},
     "observe": "检查是否翻页/读取至列表闭合"},
    {"name": "来源合规", "weight": 0.20, "measures": "只读该项目 MR 记录",
     "anchors": {"0.0": "用外部信息", "0.5": "部分外部", "1.0": "只读该项目记录"},
     "observe": "检查数据来源"},
    {"name": "证据充分性", "weight": 0.15, "measures": "数量有可见列表/计数标签支撑",
     "anchors": {"0.0": "无支撑", "0.5": "部分", "1.0": "列表或计数标签可见"},
     "observe": "检查计数标签/列表可见性"}
  ],
  "do_not_do": [
    "不要拆成 'Byte Blaze 的 open MR 数' + 'empathy-prompts 的 open MR 数' 两个独立奖励"
  ],
  "unknown_handling": [
    "无法确认是否穷尽 open 列表 → null"
  ]
}
```

---

## 9. 题目 32(22af52ab1c27d176f62c)— 基于搜索结果 count vegan products

```json
{
  "task_id": "22af52ab1c27d176f62c",
  "statement": "Count the vegan products based on the search results.",
  "atomicity": {"is_atomic": true, "reason": "一个计数查询;搜索条件正确是门控前提,不是独立奖励"},
  "gate": [
    {"cond": "搜索条件正确:仅 vegan products", "required": true, "check": "未混入非 vegan、未漏掉 vegan;过滤标签 == vegan"},
    {"cond": "计数基于该搜索结果集", "required": true, "check": "计数与搜索结果集一致,未脱离结果集自行计数"},
    {"cond": "计数准确(穷尽结果,未只数当前页)", "required": true, "check": "计数 == 搜索结果集总数"},
    {"cond": "结果格式符合 schema", "required": true, "check": "满足 answer_schema"}
  ],
  "quality": [
    {"name": "搜索条件准确性", "weight": 0.35, "measures": "vegan 过滤正确应用,未放宽或误用其他标签",
     "anchors": {"0.0": "过滤错误或误用其他标签", "0.5": "部分正确", "1.0": "vegan 过滤完全正确"},
     "observe": "检查搜索条件设置"},
    {"name": "计数完整性", "weight": 0.30, "measures": "穷尽结果集或确认总数来源",
     "anchors": {"0.0": "只数当前页", "0.5": "部分翻页", "1.0": "穷尽或确认总数"},
     "observe": "检查翻页/总数来源确认"},
    {"name": "来源合规", "weight": 0.20, "measures": "结果来自本地搜索记录",
     "anchors": {"0.0": "外部数据", "0.5": "部分本地", "1.0": "只读本地搜索记录"},
     "observe": "检查数据来源"},
    {"name": "证据充分性", "weight": 0.15, "measures": "计数有可见结果支撑",
     "anchors": {"0.0": "无", "0.5": "部分", "1.0": "结果列表可见"},
     "observe": "检查结果可见性"}
  ],
  "do_not_do": [
    "不要给 '搜索结果是否正确' 单独发分(已在 gate)",
    "不要把 '执行搜索' 与 '计数' 拆成两个独立奖励"
  ],
  "unknown_handling": [
    "无法确认搜索条件是否仅为 vegan → null"
  ]
}
```

---

## 10. 题目 34(23749feecb47697d2c74)— 论坛帖子标题与用户名

```json
{
  "task_id": "23749feecb47697d2c74",
  "statement": "Provide the title and the username of the forum post (ordinary_query).",
  "atomicity": {"is_atomic": true, "reason": "标题+用户名是同一帖子记录的两个字段,不拆成两个独立奖励"},
  "gate": [
    {"cond": "标题精确匹配题面", "required": true, "check": "返回 title 与题面目标帖子标题一致"},
    {"cond": "提交用户名精确匹配", "required": true, "check": "返回 username 与题面目标一致"},
    {"cond": "答案来自本地帖子元数据", "required": true, "check": "来源为本地帖子记录,未用外部 publisher 文章内容替代"},
    {"cond": "满足 ordinary_query 判定与 answer_schema", "required": true, "check": "符合 ordinary_query.evaluate_query 与 schema"}
  ],
  "quality": [
    {"name": "来源合规", "weight": 0.40, "measures": "未打开或总结外部 publisher 文章,只读本地帖子元数据",
     "anchors": {"0.0": "打开/总结外部文章", "0.5": "打开但未采用外部内容", "1.0": "只读本地元数据"},
     "observe": "检查是否访问外部 publisher 页面"},
    {"name": "操作效率", "weight": 0.30, "measures": "无重复搜索、无无关页面、无回退",
     "anchors": {"0.0": "大量重复/无关/回退", "0.5": "少量冗余", "1.0": "直达目标,无冗余"},
     "observe": "统计重复搜索与无关页面访问次数"},
    {"name": "字段校验", "weight": 0.20, "measures": "确认标题与用户名来自同一条帖子记录,未混淆作者/版块/时间",
     "anchors": {"0.0": "字段来源混乱", "0.5": "部分字段来源不确定", "1.0": "两字段同源且正确"},
     "observe": "检查两字段是否来自同一记录"},
    {"name": "提交规范", "weight": 0.10, "measures": "无额外字段、无解释前缀,格式符合 schema",
     "anchors": {"0.0": "多字段/带解释前缀/格式不符", "0.5": "轻微格式问题", "1.0": "严格符合 schema"},
     "observe": "检查提交内容格式"}
  ],
  "do_not_do": [
    "不要拆成 '标题 0.4' / '用户名 0.4' 两个独立奖励",
    "不要把 '答案来自本地' 单独发分(已在 gate)"
  ],
  "unknown_handling": [
    "无法确认答案是否来自本地元数据(而非外部)→ null"
  ]
}
```

---

## 11. 题目 36(25f8c0d4acb198c76444)— 订单 000000188 状态,总额 $2,004.99

```json
{
  "task_id": "25f8c0d4acb198c76444",
  "statement": "View the status of order 000000188, whose total is $2,004.99.",
  "atomicity": {"is_atomic": true, "reason": "总额是限定订单的关系从句(实体确认),不是第二个动作/输出字段"},
  "gate": [
    {"cond": "当前查看的是订单 '000000188'(保留前导零,字符串)", "required": true, "check": "订单号精确匹配,前导零未丢失"},
    {"cond": "该订单总额显示为 '$2,004.99'", "required": true, "check": "订单 total 字段 == $2,004.99(用于确认实体)"},
    {"cond": "报告的订单状态准确", "required": true, "check": "状态与订单记录一致"},
    {"cond": "答案来自该订单记录", "required": true, "check": "状态读取自该订单页面,非推测/外部"}
  ],
  "quality": [
    {"name": "实体确认规范", "weight": 0.35, "measures": "先用订单号+总额共同确认目标,再读状态,未误读相邻订单",
     "anchors": {"0.0": "未确认实体直接读状态或误读相邻订单", "0.5": "只核对订单号未核对总额", "1.0": "订单号+总额共同确认后再读"},
     "observe": "检查读状态前是否核对订单号与总额"},
    {"name": "来源合规", "weight": 0.25, "measures": "状态来自该订单页面",
     "anchors": {"0.0": "外部/推测", "0.5": "部分", "1.0": "只读该订单页面"},
     "observe": "检查状态数据来源"},
    {"name": "操作效率", "weight": 0.25, "measures": "无重复打开、无无关订单探索",
     "anchors": {"0.0": "重复打开/探索无关订单", "0.5": "少量冗余", "1.0": "直达目标订单"},
     "observe": "统计重复与无关订单访问"},
    {"name": "证据充分性", "weight": 0.15, "measures": "状态值有可见字段支撑",
     "anchors": {"0.0": "无", "0.5": "部分", "1.0": "状态字段值可见"},
     "observe": "检查状态字段可见性"}
  ],
  "do_not_do": [
    "不要把 '确认总额' 和 '读取状态' 拆成两个独立奖励",
    "不要把总额 $2,004.99 当作输出字段单独奖励"
  ],
  "unknown_handling": [
    "无法确认查看的订单号与总额是否匹配 → null"
  ]
}
```

---

## 附录:错误拆法对照表(防回归清单)

| 题号 | 错误拆法(禁止) |
|---|---|
| 12/13/33 | 改 tax class 0.5 + save 0.5 |
| 21 | exclude 0.5 + save 0.5 |
| 24 | remove exclusion 0.5 + save 0.5(且不与 21 合并) |
| 39 | 选对产品 0.5 + 选对分类 0.5 |
| 15 | 找 female / 找 January 两个独立评分 |
| 31 | Byte Blaze 计数 + empathy-prompts 计数 |
| 32 | 搜索条件正确单独给分 |
| 34 | 标题 0.4 + 用户名 0.4 |
| 36 | 确认总额 / 读取状态两个独立奖励 |



---

<!-- ===== reward-criteria-decomposition-batch1-update.md ==== -->

# 子奖励判断准则细分 · 第一批：admin_contract update 型剩余题目（26 题）

> 延续 `reward-criteria-decomposition.md` 的 Gate + Quality 二段式。本文只做**判定准则的细分与可操作化**，不实现奖励计算。
> 计算公式 `R = null / 0 / base + (1-base)·Q` 由计算层实现，base 数值不在本文范围。
> 本文产出：每道题的 gate（硬前提合取）、quality（Q 维度 + 锚点 + 观察方式）、适用场景、边界情况、不应给分的反例。

## 0. 范围与方法（仅依据两份文档）

- **数据源**：`docs/reward-inventory/binary-reward-tasks.md`（二值题目清单，共 **497 题**，8 类判断器分支）。
- **本批范围**：`admin_contract_rules.checks:update` 分支的 **26 道剩余题目**（该分支共 32 题，其中 6 题已在 `reward-criteria-decomposition.md` 细分：#12/#13/#21/#24/#33/#39）。
- **方法**：与既有 11 题的 Gate+Quality 完全一致；不重设计奖励计算，不与二值准则冲突。
- **核对结论**：本批 26 题判断器判定条件**完全同构**，均为：
  `persisted_requested_value`（目标对象已持久保存并整体满足 update_matches）+ `same_local_deployment` + `valid_authenticated_page` + `other_records_unchanged`。因此差异仅由**题面**驱动。

**判定器分支分布（供后续批次规划）：**

| 分支 | 总数 | 已细分 | 剩余 | 状态 |
|---|---|---|---|---|
| `update` | 32 | 6 | **26** | **本批** |
| `collection_query` | 14 | 1 | 13 | 下一批 |
| `query` | 7 | 0 | 7 | 待批 |
| `links` | 6 | 0 | 6 | 待批 |
| `pdf` / `create` / `draft_reset` | 3 | 0 | 3 | 待批 |
| `ordinary_query` | 136 | 4 | 132 | 待批 |
| `未记录`（导航，业务条件见 native_contract） | 299 | 0 | 299 | 待批 |

---

## 1. update 型通用子奖励框架（本批 26 题共享）

### 1.1 成功门控条件（gate，硬前提合取）

> 任一硬前提**明确为假** → 该题 R=0；任一关键项**证据不足且无法确认** → R=null（不转 0、不转失败）。

- **G1 目标对象身份正确**：操作对象为题面指定的实体（产品 / 客户组 / 订单 / 客户 / 分类），非同名或相邻实体；不得擅自新建同名实体冒充。
- **G2 `persisted_requested_value`**：目标字段最终值满足 `update_matches` 的请求条件，且已持久化（存在 save 并确认生效）。
- **G3 `other_records_unchanged`**：目标以外的同实体记录保持（未误改其他字段、其他记录、其他实体）。
- **G4 `same_local_deployment`**：终页 netloc 等于原本地部署。
- **G5 `valid_authenticated_page`**：终页未被标记登录页或页面错误。

### 1.2 质量维度（仅在 gate 通过后计分；权重和 = 1.0）

| 维度 | 权重 | 判定标准（0.0 / 0.5 / 1.0 锚点，可插值） | 观察方式 |
|---|---|---|---|
| 操作范围 | 0.35 | 0.0：修改了其他实体/其他字段，或大量无关页面探索；0.5：有少量无关浏览或打开过其他实体但未修改；1.0：只定位目标实体并仅改目标字段，无冗余动作 | 统计非目标实体 / 非目标字段的操作次数 |
| 验证规范 | 0.30 | 0.0：盲选 / 盲改，无可观察核对；0.5：只核对目标身份或只核对目标值；1.0：提交前同时确认实体身份与目标值 | 检查提交前是否有读取/确认目标身份与目标值的记录 |
| 保存确认 | 0.20 | 0.0：未保存或保存失败；0.5：执行了 save 但未确认生效；1.0：保存后复查/刷新确认仍为目标值 | save 事件 + 保存后复查事件 |
| 证据充分性 | 0.15 | 0.0：无页面证据；0.5：部分字段值可见但不足以证明生效；1.0：目标字段最终值有可见字段值/截图证据 | 目标字段值是否在 observation 可见 |

### 1.3 通用反例（do_not_do，本批全部适用）

- 不把「编辑（赋值/改状态）」与「保存」拆成两个独立分数（0.5/0.5）。
- 不给 `same_local_deployment` / `valid_authenticated_page` 单独发分（已在 gate）。
- 不给「成功定位到目标对象」单独发分（已在 G1）。
- 不给「选了目标值但未保存」任何质量分——gate 未通过即 R=0，不进入质量评分。
- 不因「主要动作对但误改了其他字段」给分——G3 违反即 gate 不通过 → 0。

### 1.4 通用边界（unknown_handling，本批全部适用）

- 无法验证保存后是否生效（无保存后状态记录）→ null。
- 无法确定操作对象是否为题面指定实体 → null（明确为假则 0）。
- 目标字段最终值正确、但 `other_records_unchanged` 被破坏 → gate 不通过 → 0。

---

## 2. 逐题细分

### A. 客户组 tax class → Wholesale Customer（#45 / #76 / #148 同题 ×3）

### 题目 45（322038f10d4a08220ad3）—题面：Change the tax class of the customer group Updated General Customers to Wholesale Customer and save the group.—子奖励判断准则

- **适用场景**：客户组 tax class 赋值并保存；与已细分 #13（Retail Customer）同型，仅目标值不同。
- **成功门控条件（gate）**：
  - G1 目标客户组 == "Updated General Customers"；
  - G2 该组 tax class 最终值 == "Wholesale Customer"，已 save 并确认生效；
  - G3 未修改无关字段 / 无关组；G4 / G5 同通用框架。
- **质量维度 / 判定标准**：同 §1.2（操作范围 0.35 / 验证规范 0.30 / 保存确认 0.20 / 证据充分性 0.15）。
- **边界情况**：无法验证保存后仍为 "Wholesale Customer" → null；无法确定目标组 → null（明确为假 → 0）。
- **不应给分的反例**：不拆「改 tax class」与「save」；不把 #45/#76/#148 合并为一题（各自独立判分，但准则复用）；不给「定位到组」单独发分。
- **关联**：#76、#148 与本题目面完全相同（见下）。

### 题目 76（53c55b37cb86a07f3f21）—题面：Change the tax class of the customer group Updated General Customers to Wholesale Customer and save the group.—子奖励判断准则

- **说明**：与 #45 题面完全相同，准则复用 #45，不重复展开。

### 题目 148（c251c8edc13bff852155）—题面：Change the tax class of the customer group Updated General Customers to Wholesale Customer and save the group.—子奖励判断准则

- **说明**：与 #45 题面完全相同，准则复用 #45，不重复展开。

---

### B. 产品字段赋值（11 题）

### 题目 5（04d41f77320aa450ac93）—题面：Configure inventory settings to enable backorders for the Eco-Friendly Water Bottle—子奖励判断准则

- **适用场景**：产品库存设置中的开关赋值并保存（backorders 使能）。
- **成功门控条件（gate）**：
  - G1 目标产品 == "Eco-Friendly Water Bottle"；
  - G2 backorders 最终状态 == enabled，已持久化；
  - G3 未改动其他库存字段（quantity / stock status 等）；G4 / G5 同通用框架。
- **质量维度 / 判定标准**：同 §1.2。
- **边界情况**：backorders 开关最终状态无法确认 → null。
- **不应给分的反例**：不把「进入库存设置页」与「启用 backorders」拆两个分数；不因「改了其他库存字段但 backorders 也对」给满分（G3 违反 → 0）。

### 题目 17（0f2ae6c1ef83ad23962a）—题面：Set up a special price promotion for the Yoga Mat Pro—子奖励判断准则

- **适用场景**：为产品建立 special price 促销并保存。
- **成功门控条件（gate）**：
  - G1 目标产品 == "Yoga Mat Pro"；
  - G2 该产品存在已保存且生效的 special price promotion（含必要字段）；
  - G3 未改动产品其他无关字段；G4 / G5 同通用框架。
- **质量维度 / 判定标准**：同 §1.2。
- **边界情况**：促销是否已保存/生效无法确认 → null。
- **不应给分的反例**：不把「设价格」与「设促销其他字段」拆多个分数（同一写操作）；不给「进入促销设置页」单独发分。

### 题目 51（3a54d442798dc2c3ad83）—题面：Change the inventory quantity of the Hera Pullover Hoodie-XS-Blue to 150 units—子奖励判断准则

- **适用场景**：特定 SKU/规格（尺寸 XS + 颜色 Blue）库存数量赋值并保存。
- **成功门控条件（gate）**：
  - G1 目标 == "Hera Pullover Hoodie-XS-Blue"（须精确到尺寸-颜色规格，非其他规格）；
  - G2 该规格库存数量 == 150，已保存；
  - G3 未改动其他规格 / 其他字段；G4 / G5 同通用框架。
- **质量维度 / 判定标准**：同 §1.2。
- **边界情况**：规格是否精确到 XS-Blue 无法确认 → null。
- **不应给分的反例**：不把「选对规格」与「改对数量」拆两个分数；不因「改了同款其他规格的数量」给分（G1 违反 → 0）。

### 题目 58（3e58d846a3d9e983aacd）—题面：Set the Country of Manufacture for the Yoga Mat Pro to "United States"—子奖励判断准则

- **适用场景**：产品「原产国」字段赋值并保存。
- **成功门控条件（gate）**：
  - G1 目标产品 == "Yoga Mat Pro"；
  - G2 Country of Manufacture == "United States"，已保存；
  - G3 未改动其他字段；G4 / G5 同通用框架。
- **质量维度 / 判定标准**：同 §1.2。
- **边界情况**：同通用框架。
- **不应给分的反例**：不把「选产品」与「改国家」拆两个分数；不给「定位到产品」单独发分。

### 题目 71（4c44ebe0f2c8fd9f35a3）—题面：Update the price of the "Test Product" to $39.99—子奖励判断准则

- **适用场景**：产品普通价格（price）赋值并保存。
- **成功门控条件（gate）**：
  - G1 目标产品 == "Test Product"；
  - G2 price == $39.99，已保存；
  - G3 未改动其他字段（special price / tier price 等）；G4 / G5 同通用框架。
- **质量维度 / 判定标准**：同 §1.2。
- **边界情况**：同通用框架。
- **不应给分的反例**：不拆「改价格」与「保存」；注意区分普通 price 与 special price，改错字段 → G2 不满足 → 0。

### 题目 72（4fc71d425d26b849cdaa）—题面：Access the Advanced Pricing settings for the Blue T-Shirt and update the special price.—子奖励判断准则

- **适用场景**：在 Advanced Pricing 设置中更新产品 special price 并保存。
- **成功门控条件（gate）**：
  - G1 目标产品 == "Blue T-Shirt"；
  - G2 Advanced Pricing 的 special price 已更新并持久化（相对初始值发生变化，满足 update_matches）；
  - G3 未改动普通 price / 其他字段；G4 / G5 同通用框架。
- **质量维度 / 判定标准**：同 §1.2。
- **边界情况**：special price 是否实际变更无法确认 → null。
- **不应给分的反例**：不把「进入 Advanced Pricing」与「更新 special price」拆两个分数；special price 未实际变更（等于初始值）→ G2 不满足 → 0。

### 题目 81（58a4e4a4b7fbb2662b2d）—题面：Update the stock status for the Maya Tunic product. Save a native stock status different from the initial saved status; either In Stock or Out of Stock is allowed.—子奖励判断准则

- **适用场景**：产品 stock status 变更并保存；目标值有硬约束（≠ 初始值，且 ∈ {In Stock, Out of Stock}）。
- **成功门控条件（gate）**：
  - G1 目标产品 == "Maya Tunic"；
  - G2 stock status 最终值 ∈ {In Stock, Out of Stock} **且 ≠ 初始值**，已保存；
  - G3 未改动其他字段；G4 / G5 同通用框架。
- **质量维度 / 判定标准**：同 §1.2。
- **边界情况**：初始 status 值无法确认（无从判断"不同"）→ null。
- **不应给分的反例**：不拆「改 status」与「save」；把 status 改回初始值（未真正变更）→ G2 不满足 → 0；改成非法值（非 In/Out of Stock）→ 0。

### 题目 109（7f1fe5a50297a970b8fe）—题面：Disable the Hera Pullover Hoodie-XL-Orange product—子奖励判断准则

- **适用场景**：产品启用状态置为禁用并保存。
- **成功门控条件（gate）**：
  - G1 目标产品 == "Hera Pullover Hoodie-XL-Orange"（规格精确）；
  - G2 产品最终状态 == disabled，已持久化；
  - G3 未改动其他字段；G4 / G5 同通用框架。
- **质量维度 / 判定标准**：同 §1.2。
- **边界情况**：同通用框架。
- **不应给分的反例**：不把「选产品」与「disable」拆两个分数；不把「删除产品」视为等价（delete ≠ disable）→ 0。

### 题目 173（da0fc47b98877acabdd8）—题面：Modify the inventory quantity of the Blue T-Shirt.—子奖励判断准则

- **适用场景**：产品库存数量变更并保存（题面未指定目标值，仅要求「修改」）。
- **成功门控条件（gate）**：
  - G1 目标产品 == "Blue T-Shirt"；
  - G2 库存数量已变更（≠ 初始值）并持久化；
  - G3 未改动其他字段；G4 / G5 同通用框架。
- **质量维度 / 判定标准**：同 §1.2。
- **边界情况**：初始数量无法确认 → null。
- **不应给分的反例**：不拆「改数量」与「保存」；把数量改回初始值（未变更）→ G2 不满足 → 0。

### 题目 185（e4507b6d61c7f5e585bb）—题面：Change Yoga Mat Pro price to 31.99 and save the product.—子奖励判断准则

- **适用场景**：产品普通价格赋值并保存。
- **成功门控条件（gate）**：
  - G1 目标产品 == "Yoga Mat Pro"；
  - G2 price == 31.99，已保存；
  - G3 未改动其他字段；G4 / G5 同通用框架。
- **质量维度 / 判定标准**：同 §1.2。
- **边界情况**：同通用框架。
- **不应给分的反例**：不拆「改价格」与「save」；注意与 #17 的 special price、与 #185 之外的其它价格字段区分。

### 题目 189（ec7ae8996688fc3a2e08）—题面：Set a special price for the Example Product Deluxe 2023.—子奖励判断准则

- **适用场景**：为产品设置 special price 并保存（与 #17 同型，不同产品）。
- **成功门控条件（gate）**：
  - G1 目标产品 == "Example Product Deluxe 2023"；
  - G2 该产品 special price 已设置并持久化；
  - G3 未改动其他字段；G4 / G5 同通用框架。
- **质量维度 / 判定标准**：同 §1.2。
- **边界情况**：同通用框架。
- **不应给分的反例**：不拆「设置」与「保存」；不把普通 price 误当 special price。

---

### C. 订单状态变更（3 题，方向互斥）

### 题目 18（11e24e5efefea43a6a1e）—题面：Cancel the selected order. For this local training variant, the selected order is #000000301.—子奖励判断准则

- **适用场景**：订单状态变更为 canceled 并保存。
- **成功门控条件（gate）**：
  - G1 目标订单 == "#000000301"（字符串，保留前导零）；
  - G2 订单状态 == canceled，已保存；
  - G3 未改动其他订单 / 字段；G4 / G5 同通用框架。
- **质量维度 / 判定标准**：同 §1.2。
- **边界情况**：同通用框架。
- **不应给分的反例**：不把「选订单」与「cancel」拆两个分数；不把 hold / unhold 误当 cancel（状态方向错 → G2 不满足 → 0）。

### 题目 26（19b39dd61c696035ce37）—题面：Hold the selected order. For this local training variant, the selected order is #000000301.—子奖励判断准则

- **适用场景**：订单状态变更为 hold（on hold）并保存。
- **成功门控条件（gate）**：
  - G1 目标订单 == "#000000301"；
  - G2 订单状态 == hold，已保存；
  - G3 未改动其他订单 / 字段；G4 / G5 同通用框架。
- **质量维度 / 判定标准**：同 §1.2。
- **边界情况**：同通用框架。
- **不应给分的反例**：与 #18（cancel）/ #59（unhold）状态方向互斥，不得混用；不拆「选」与「hold」。

### 题目 59（3f5222e07879c45f56d0）—题面：Unhold the selected order. For this local training variant, the selected order is #000000301.—子奖励判断准则

- **适用场景**：订单状态变更为 unhold 并保存。
- **成功门控条件（gate）**：
  - G1 目标订单 == "#000000301"；
  - G2 订单状态 == unhold，已保存；
  - G3 未改动其他订单 / 字段；G4 / G5 同通用框架。
- **质量维度 / 判定标准**：同 §1.2。
- **边界情况**：同通用框架。
- **不应给分的反例**：与 #18 / #26 状态方向互斥；不拆「选」与「unhold」。

---

### D. 客户字段（3 题，以 email 锁定实体）

### 题目 60（411514c1c37d67746116）—题面：For this local training variant, change Adam Garcia's first name to Adam Updated and save. For this local training variant, the target account email is adam.garcia@gmail.com.—子奖励判断准则

- **适用场景**：客户 first name 字段赋值并保存；实体由 email 锁定。
- **成功门控条件（gate）**：
  - G1 目标客户账号 == adam.garcia@gmail.com（实体确认）；
  - G2 first name == "Adam Updated"，已保存；
  - G3 未改动其他字段（last name / email 等）；G4 / G5 同通用框架。
- **质量维度 / 判定标准**：同 §1.2。
- **边界情况**：无法确认账号与 email 匹配 → null。
- **不应给分的反例**：不把「定位账号」与「改 first name」拆两个分数；不因「改了其他客户的名字」给分（G1 违反 → 0）；"Adam Updated" 是字面目标值，不得擅自改写为其他拼写。

### 题目 125（a00fd4a97eb92a33c922）—题面：For this local training variant, associate Adam Garcia (adam.garcia@gmail.com) with Training Secondary Website using Associate to Website, and save.—子奖励判断准则

- **适用场景**：为客户账号建立网站关联（Associate to Website）并保存。
- **成功门控条件（gate）**：
  - G1 目标账号 == adam.garcia@gmail.com；
  - G2 该账号已与 "Training Secondary Website" 建立关联，已保存；
  - G3 未改动其他网站关联 / 字段；G4 / G5 同通用框架。
- **质量维度 / 判定标准**：同 §1.2。
- **边界情况**：同通用框架。
- **不应给分的反例**：不把「Associate to Website 操作」与「save」拆两个分数；不因「关联到错误网站」给分（G2 违反 → 0）。

### 题目 184（e44dd798dd96c628fafa）—题面：For this local training variant, update the default billing address phone number of Jane Doe (jane.doe@gmail.com) to 555-123-4567 and save.—子奖励判断准则

- **适用场景**：客户默认账单地址的电话号码赋值并保存。
- **成功门控条件（gate）**：
  - G1 目标账号 == jane.doe@gmail.com；
  - G2 default billing address 的 phone number == "555-123-4567"，已保存；
  - G3 未改动其他地址字段 / 其他账号；G4 / G5 同通用框架。
- **质量维度 / 判定标准**：同 §1.2。
- **边界情况**：同通用框架。
- **不应给分的反例**：不把「改 phone」与「save」拆两个分数；改错成 shipping phone 或其他地址的 phone → G2 不满足 → 0。

---

### E. 客户组字段（2 题）

### 题目 86（605fa472c81c3d397dbb）—题面：Change the name of the Updated General Customers group to General Retail Customers—子奖励判断准则

- **适用场景**：客户组名称赋值并保存。
- **成功门控条件（gate）**：
  - G1 目标组 == "Updated General Customers"；
  - G2 组名 == "General Retail Customers"，已保存；
  - G3 未改动其他字段；G4 / G5 同通用框架。
- **质量维度 / 判定标准**：同 §1.2。
- **边界情况**：同通用框架。
- **不应给分的反例**：不拆「改 name」与「save」；与 #96（"Updated General Customers Saved"）目标名不同，不得混用。

### 题目 96（6d88148c5efc95914367）—题面：Save the currently displayed unsaved group-name change from Updated General Customers to Updated General Customers Saved.—子奖励判断准则

- **适用场景**：保存 UI 中已 staged（未保存）的组名改动；核心动作是 save 而非重新编辑。
- **成功门控条件（gate）**：
  - G1 目标组 == "Updated General Customers"；
  - G2 组名 == "Updated General Customers Saved"，已保存生效；
  - G3 未改动其他字段；G4 / G5 同通用框架。
- **质量维度 / 判定标准**：同 §1.2；「验证规范」维度额外观察 agent 是否识别出「改动已 staged、仅需保存」这一状态（若重新手动编辑但结果正确，结果仍满足 G2，但验证规范维度应下调）。
- **边界情况**：无法确认 UI 中改动是否已 staged（G2 来源不明）→ 保守 null。
- **不应给分的反例**：不拆「确认已显示的改动」与「save」两个分数；不把「重新编辑后再保存」当作等价于「直接保存已 staged 改动」的满分操作。

---

### F. 分类 / 导航（3 题）

### 题目 131（a94c1948e65b354ca24f）—题面：For this local training variant, change the URL key of New Category Name to "training-updated-category" and save.—子奖励判断准则

- **适用场景**：分类 URL key 赋值并保存。
- **成功门控条件（gate）**：
  - G1 目标分类 == "New Category Name"；
  - G2 URL key == "training-updated-category"，已保存；
  - G3 未改动其他分类字段；G4 / G5 同通用框架。
- **质量维度 / 判定标准**：同 §1.2。
- **边界情况**：同通用框架。
- **不应给分的反例**：不拆「选分类」与「改 URL key」两个分数。

### 题目 152（c6ebf0496191e8d8af97）—题面：For this local training variant, rename New Category Name to Updated Training Category and save.—子奖励判断准则

- **适用场景**：分类名称赋值并保存。
- **成功门控条件（gate）**：
  - G1 目标分类 == "New Category Name"；
  - G2 分类名 == "Updated Training Category"，已保存；
  - G3 未改动其他字段；G4 / G5 同通用框架。
- **质量维度 / 判定标准**：同 §1.2。
- **边界情况**：同通用框架。
- **不应给分的反例**：不拆「改 name」与「save」；与 #131（URL key）字段不同，不得混用。

### 题目 157（c9ea69ebd9bbe0132937）—题面：Include the "New Category Name" category in the navigation menu—子奖励判断准则

- **适用场景**：将分类纳入导航菜单（导航包含开关置真）并保存。
- **成功门控条件（gate）**：
  - G1 目标分类 == "New Category Name"；
  - G2 该分类的导航包含状态 == included（出现在导航菜单中），已持久化；
  - G3 未改动其他分类 / 菜单项；G4 / G5 同通用框架。
- **质量维度 / 判定标准**：同 §1.2。
- **边界情况**：同通用框架。
- **不应给分的反例**：不把「选中分类」与「include」拆两个分数；把 include 误做 exclude（方向反）→ G2 不满足 → 0。

---

### G. 排除网站（重复题，复用 #21）

### 题目 182（e1651f6e9d684024eaeb）—题面：Exclude Main Website from the Updated General Customers group, and save.—子奖励判断准则

- **说明**：与已细分 #21（`170349164ca41b627be8`）题面完全相同，为重复入库；准则直接复用 #21，不重复展开。
- **成功门控条件（gate，同 #21）**：
  - G1 目标组 == "Updated General Customers"；
  - G2 "Main Website" 在该组 exclusion 列表中，已保存生效；
  - G3 未改动其他组 / 网站 exclusion；G4 / G5 同通用框架。
- **质量维度 / 判定标准**：同 §1.2。
- **边界情况**：无法验证保存后 exclusion 是否仍在 → null。
- **不应给分的反例**：不拆「exclude」与「save」；不把 #182 与 #24（remove exclusion）合并（方向相反，最终状态不同）。

---

## 附录：错误拆法对照表（本批新增，防回归）

| 题号 | 错误拆法（禁止） |
|---|---|
| 45 / 76 / 148 | 改 tax class 0.5 + save 0.5（且三题不得合并判分） |
| 5 / 17 / 51 / 58 / 71 / 72 / 81 / 109 / 173 / 185 / 189 | 选对产品 0.5 + 改对字段 0.5 |
| 18 / 26 / 59 | 选对订单 0.5 + 改对状态 0.5（且 cancel/hold/unhold 三状态方向互斥，不得混用） |
| 60 / 125 / 184 | 定位账号 0.5 + 改对字段 0.5 |
| 86 / 96 | 改 name 0.5 + save 0.5（且 #86 与 #96 目标名不同，不得混用） |
| 131 / 152 / 157 | 选对分类 0.5 + 改对字段 0.5（URL key / name / include 字段不同，不得混用） |
| 182 | exclude 0.5 + save 0.5（复用 #21；不与 #24 合并） |

## 后续批次计划（供确认）

- 第 2 批：`collection_query` 剩余 13 题（#2/#7/#52/#57/#75/#84/#92/#99/#101/#146/#147/#175/#179）。
- 第 3 批：`query` 7 题 + `links` 6 题 + `pdf`/`create`/`draft_reset` 3 题。
- 第 4 批：`ordinary_query` 剩余 132 题（多为单值查询，按字段类型归组）。
- 第 5 批（视需要）：`未记录` 导航类 299 题——注意其业务条件见 native_contract，本文档内无可据以细分的 gate 细节，需另行取得 native_contract 后再动。



---

<!-- ===== reward-criteria-decomposition-batch2-collection-query.md ==== -->

# 子奖励判断准则细分 · 第二批：admin_contract collection_query 型剩余题目（13 题）

> 延续 `reward-criteria-decomposition.md` 与 `reward-criteria-decomposition-batch1-update.md` 的 Gate + Quality 二段式。本文只做**判定准则的细分与可操作化**，不实现奖励计算。
> 计算公式 `R = null / 0 / base + (1-base)·Q` 由计算层实现，base 数值不在本文范围。
> 本文产出：每道题的 gate、quality、适用场景、边界情况、不应给分的反例。

## 0. 范围与方法（仅依据两份文档）

- **数据源**：`docs/reward-inventory/binary-reward-tasks.md`（497 题）。
- **本批范围**：`admin_contract_rules.checks:collection_query` 分支的 **13 道剩余题目**（该分支共 14 题，其中 1 题 #15 已在 `reward-criteria-decomposition.md` 细分）。
- **方法**：与既有 11 题 + 第一批 26 题一致；不重设计奖励计算，不与二值准则冲突。
- **核对结论**：本批 13 题判定条件**同构**，均为 `exact_result_set`（12 题）或 `answer_count`（1 题，仅 #99）+ `same_local_deployment` + `valid_authenticated_page` + `records_unchanged` + `answer_schema`。差异仅由**题面**驱动。

**本批与既有 #15 的关系**：#15（`Find all female customers with birthdays in January`）已建立 collection_query 型的 Gate+Quality 模板，本批 13 题复用该模板并按题面特化。

---

## 1. collection_query 型通用子奖励框架（本批 13 题共享）

### 1.1 成功门控条件（gate，硬前提合取）

> 任一硬前提**明确为假** → R=0；任一关键项**证据不足且无法确认** → R=null（不转 0、不转失败）。

- **G1 查询/过滤条件正确**：搜索/过滤条件与题面一致（关键词、字段、多条件合取、日期区间边界均正确应用，未放宽、未误用其他标签/字段）。
- **G2 结果集完整**（`exact_result_set` 的"无遗漏"；#99 对应 `answer_count` == 选中集合数量）：所有匹配记录穷尽，未找到一个就停。
- **G3 结果集精确**（`exact_result_set` 的"无多余/无重复"）：结果集不含不匹配记录、不含重复记录。
- **G4 `records_unchanged`**：只读查询，未修改任何数据。
- **G5 `same_local_deployment`**：终页 netloc 等于原本地部署。
- **G6 `valid_authenticated_page`**：终页未被标记登录页或页面错误。
- **G7 `answer_schema`**：提交答案字段/格式符合 schema（不为漏答放宽）。

> 注：G5/G6/G7 为原有前提；G1–G4 为本题核心判定。#99 无 G2/G3 之分，合并为"计数等于选中集合数量"。

### 1.2 质量维度（仅在 gate 通过后计分；权重和 = 1.0）

| 维度 | 权重 | 判定标准（0.0 / 0.5 / 1.0 锚点，可插值） | 观察方式 |
|---|---|---|---|
| 完整性 | 0.35 | 0.0：只返回第一个匹配就停止；0.5：返回部分但未翻页/未闭合；1.0：翻页/继续读取直至结果集闭合 | 检查是否有翻页/继续读取动作直至结束 |
| 搜索条件准确性 | 0.30 | 0.0：条件错误（关键词/字段/日期范围错误）；0.5：多条件题中仅部分条件正确；1.0：所有条件均正确 | 检查搜索/过滤条件设置与题面一致 |
| 来源合规 | 0.20 | 0.0：依赖推测或外部数据；0.5：部分来自本地；1.0：全部来自本地记录 | 检查结果是否来自本地记录 |
| 证据充分性 | 0.15 | 0.0：无记录支撑；0.5：部分记录可见；1.0：列表/计数有完整可见记录 | 检查结果列表/计数标签可见性 |

### 1.3 通用反例（do_not_do，本批全部适用）

- 不把多个过滤条件拆成多个独立分数（同一 conjunctive query）。
- 不把「执行搜索」与「返回结果/计数」拆成两个独立分数。
- 不把「搜索条件正确」单独发分（已在 G1）。
- 不把「只找到部分结果」当作成功子集给分（G2 违反 → 0）。
- 不把「结果格式符合 schema」单独发分（已在 G7）。

### 1.4 通用边界（unknown_handling，本批全部适用）

- 无法确认结果集是否穷尽（无法访问完整记录列表）→ null。
- 无法确认过滤条件是否正确应用 → null（明确为假则 0）。
- 空结果集是**合法结果**（当确实无匹配记录时），不得仅因"返回空"判失败；是否判 0 取决于空结果是否与本地真实记录一致。

---

## 2. 逐题细分

### A. 按客户名/关键词过滤（#2 / #57）

### 题目 2（01dbfb254303d2f08ae8）—题面：Search for credit memos by customer name "Veronica Costello"—子奖励判断准则

- **适用场景**：按客户名单条件过滤 credit memos，返回完整集合。
- **成功门控条件（gate）**：
  - G1 搜索条件 customer name == "Veronica Costello"；
  - G2 返回该客户的全部 credit memos（无遗漏）；
  - G3 无多余记录（不含其他客户的 credit memo）；
  - G4–G7 同通用框架。
- **质量维度 / 判定标准**：同 §1.2。
- **边界情况**：若该客户确无 credit memo，空集是合法结果，不判失败；无法确认是否有遗漏 → null。
- **不应给分的反例**：不拆「执行搜索」与「返回结果」；不把 #2 与 #7（refunded 过滤）混用；不把「找到 1 条就停」判为通过（G2 违反 → 0）。

### 题目 57（3e22ddce719a377a4c62）—题面：Search for customer details using the keyword "Veronica Costello".—子奖励判断准则

- **适用场景**：按关键词搜索客户详情，返回完整集合。
- **成功门控条件（gate）**：
  - G1 搜索关键词 == "Veronica Costello"；
  - G2 返回全部匹配客户详情（无遗漏）；
  - G3 无多余记录（不含关键词不匹配的客户）；
  - G4–G7 同通用框架。
- **质量维度 / 判定标准**：同 §1.2。
- **边界情况**：同通用框架；空结果合法性同 #2。
- **不应给分的反例**：不拆「执行搜索」与「返回结果」；不把 #57（customer details）与 #2（credit memos）的目标实体混用。

---

### B. 多条件合取过滤（#7）

### 题目 7（05bf9124ac8251050b90）—题面：Apply multiple filters to find refunded credit memos for customer Veronica Costello—子奖励判断准则

- **适用场景**：两个过滤条件（refunded 状态 + customer）合取过滤 credit memos。
- **成功门控条件（gate）**：
  - G1 两个过滤条件都正确应用：状态 == refunded **且** customer == "Veronica Costello"；
  - G2 返回全部同时满足两条件的 credit memos（无遗漏）；
  - G3 无多余记录（不含未退款、不含其他客户、不含只满足单条件的记录）；
  - G4–G7 同通用框架。
- **质量维度 / 判定标准**：同 §1.2；「搜索条件准确性」维度按"两个条件是否都正确"评 0.0/0.5/1.0。
- **边界情况**：无法确认两个过滤条件是否都应用 → null。
- **不应给分的反例**：不把「customer 过滤」与「refunded 过滤」拆成两个独立分数；不把「只满足一个条件的记录」纳入结果（G1/G3 违反 → 0）。

---

### C. 存在性检查（#52，允许空结果）

### 题目 52（3a96fe846ef551e1b692）—题面：Check whether gamingpro456@gmail.com is registered. Return the matching registered email as an item, or an empty items list if it is not registered.—子奖励判断准则

- **适用场景**：邮箱是否已注册的存在性检查；**空列表是题面明示的合法结果**。
- **成功门控条件（gate）**：
  - G1 查询对象 email == "gamingpro456@gmail.com"；
  - G2 结果与本地真实注册状态一致：若已注册 → 返回该 email 作为 item；若未注册 → 返回空 items 列表（两者皆为正确结果，取决于本地记录）；
  - G3 无多余记录（不返回其他邮箱）；
  - G4–G7 同通用框架。
- **质量维度 / 判定标准**：同 §1.2。
- **边界情况**：本地是否有该邮箱注册记录无法确认 → null；**不得因返回空列表而判失败**——空结果须与本地"未注册"事实比对。
- **不应给分的反例**：不把「执行检查」与「返回 item/空列表」拆两个分数；不把「返回空列表」一律判 0（只有当本地已注册却返回空才判 0）。

---

### D. 枚举/成员查询（#75 / #84 / #92 / #179）

### 题目 75（53a975104f8bf03a7d4a）—题面：Check what tax classes are available for customer groups.—子奖励判断准则

- **适用场景**：枚举客户组可用的全部 tax class 选项（字段取值枚举，非过滤某实体）。
- **成功门控条件（gate）**：
  - G1 查询对象为 customer group 的 tax class 可用项；
  - G2 返回全部可用 tax class 值（无遗漏）；
  - G3 无多余（不含不可用/不存在的 tax class）；
  - G4–G7 同通用框架。
- **质量维度 / 判定标准**：同 §1.2。
- **边界情况**：同通用框架。
- **不应给分的反例**：不把「查看 tax class」与「返回列表」拆两个分数；不把「只列部分 tax class」判为通过（G2 违反 → 0）。

### 题目 84（5acb0a9a8cbbaa7e1ddd）—题面：View the subcategories under the "New Category Name" category—子奖励判断准则

- **适用场景**：查看某分类下的全部子分类（父子关系枚举）。
- **成功门控条件（gate）**：
  - G1 目标父分类 == "New Category Name"；
  - G2 返回其全部子分类（无遗漏）；
  - G3 无多余（不含其他分类的子分类）；
  - G4–G7 同通用框架。
- **质量维度 / 判定标准**：同 §1.2。
- **边界情况**：若该分类无子分类，空集合法；同通用框架。
- **不应给分的反例**：不拆「定位父分类」与「列出子分类」两个分数；不把「定位到分类」单独发分（已在 G1）。

### 题目 92（673d15028cccb54d0690）—题面：Check which customers belong to the VIP Customers group—子奖励判断准则

- **适用场景**：查询某客户组（VIP Customers）的全部成员。
- **成功门控条件（gate）**：
  - G1 目标组 == "VIP Customers"；
  - G2 返回该组全部成员客户（无遗漏）；
  - G3 无多余（不含非该组成员）；
  - G4–G7 同通用框架。
- **质量维度 / 判定标准**：同 §1.2。
- **边界情况**：同通用框架。
- **不应给分的反例**：不拆「定位组」与「列成员」两个分数；不把「只列部分成员」判为通过（G2 违反 → 0）。
- **关联**：与 #179（View the list of VIP Customers）目标高度相似，准则可互相参考，但 task_id 不同、各自独立判分。

### 题目 179（dfb40a038914bcf1795b）—题面：View the list of VIP Customers—子奖励判断准则

- **适用场景**：查看 VIP Customers 列表（与 #92 目标等价：VIP Customers 组成员）。
- **成功门控条件（gate）**：同 #92（G1 组 == "VIP Customers"；G2 全部成员；G3 无多余；G4–G7 通用）。
- **质量维度 / 判定标准**：同 §1.2。
- **边界情况**：同通用框架。
- **不应给分的反例**：同 #92；不把 #92 与 #179 合并为一题（task_id 不同，各自独立判分，但准则等价）。

---

### E. 计数查询（#99）

### 题目 99（727c233e307f925c0329）—题面：Check how many customer groups are available in the system—子奖励判断准则

- **适用场景**：对选中集合计数（本批唯一用 `answer_count` 判定，无 `exact_result_set`）。
- **成功门控条件（gate）**：
  - G1 计数范围正确（只数 customer group，不混入其他实体）；
  - G2 `answer_count` == 选中集合数量（穷尽，未只数当前页）；
  - G3 `records_unchanged`：只读；
  - G5/G6/G7 同通用框架。
- **质量维度 / 判定标准**：同 §1.2；「证据充分性」维度观察计数标签/列表可见性。
- **边界情况**：无法确认是否穷尽集合 → null。
- **不应给分的反例**：不把「执行查询」与「报告计数」拆两个分数；不把「只数当前页」判为通过（G2 违反 → 0）；不把「搜索条件正确」单独发分（已在 G1）。

---

### F. 日期过滤（#101 / #146 / #147）

### 题目 101（75b57e1ccf54de8f5ecb）—题面：Search for credit memos created in April 2023.—子奖励判断准则

- **适用场景**：按整月（April 2023）过滤 credit memos。
- **成功门控条件（gate）**：
  - G1 日期条件 == April 2023（整月，非单日、非其他月份）；
  - G2 返回该月全部 credit memos（无遗漏）；
  - G3 无多余（不含其他月份的 credit memo）；
  - G4–G7 同通用框架。
- **质量维度 / 判定标准**：同 §1.2。
- **边界情况**：同通用框架。
- **不应给分的反例**：不拆「设置日期」与「返回结果」；不把「只覆盖 April 某一天」判为通过（G1/G2 违反 → 0）。
- **关联**：与 #146（April 1–30 区间）目标等价，但 #101 用整月语义、#146 用显式区间，两者端点一致，准则等价。

### 题目 146（bee5d9b2acdb2f66eb9c）—题面：Filter credit memos created between April 1, 2023 and April 30, 2023—子奖励判断准则

- **适用场景**：按闭区间 [April 1, 2023, April 30, 2023] 过滤 credit memos。
- **成功门控条件（gate）**：
  - G1 日期区间 == [April 1, 2023, April 30, 2023]，**端点含边界**；
  - G2 返回区间内全部 credit memos（无遗漏）；
  - G3 无多余（不含区间外记录）；
  - G4–G7 同通用框架。
- **质量维度 / 判定标准**：同 §1.2。
- **边界情况**：边界端点（4/1 与 4/30 当天的记录）是否纳入无法确认 → null。
- **不应给分的反例**：不拆「设置起止日期」与「返回结果」；不把「漏掉边界当天记录」判为通过（G2 违反 → 0）。

### 题目 147（c0d03822ad3cc182a48a）—题面：Find all customers who registered between March 1, 2023 and April 1, 2023—子奖励判断准则

- **适用场景**：按闭区间 [March 1, 2023, April 1, 2023] 过滤注册客户。
- **成功门控条件（gate）**：
  - G1 日期区间 == [March 1, 2023, April 1, 2023]，端点含边界；
  - G2 返回区间内全部注册客户（无遗漏）；
  - G3 无多余（不含区间外客户）；
  - G4–G7 同通用框架。
- **质量维度 / 判定标准**：同 §1.2。
- **边界情况**：边界端点（3/1 与 4/1 当天注册）是否纳入无法确认 → null。
- **不应给分的反例**：不拆「设置起止日期」与「返回结果」；不把「漏掉边界当天客户」判为通过（G2 违反 → 0）。

---

### G. 非空字段过滤（#175）

### 题目 175（daa63e0184a9716e7f11）—题面：Locate all customers with a tax/VAT number in the system—子奖励判断准则

- **适用场景**：按「tax/VAT 字段非空（存在）」过滤客户。
- **成功门控条件（gate）**：
  - G1 过滤条件正确：tax/VAT 字段非空（存在值），未误用其他字段；
  - G2 返回全部具有 tax/VAT number 的客户（无遗漏）；
  - G3 无多余（不含无 tax/VAT 的客户）；
  - G4–G7 同通用框架。
- **质量维度 / 判定标准**：同 §1.2。
- **边界情况**：同通用框架。
- **不应给分的反例**：不拆「设置非空过滤」与「返回结果」；不把「只找到部分」判为通过（G2 违反 → 0）。

---

## 附录：错误拆法对照表（本批新增，防回归）

| 题号 | 错误拆法（禁止） |
|---|---|
| 2 / 57 | 执行搜索 0.5 + 返回结果 0.5（且 #2 credit memos 与 #57 customer details 目标实体不同，不得混用） |
| 7 | customer 过滤 0.5 + refunded 过滤 0.5（同一 conjunctive query） |
| 52 | 执行检查 0.5 + 返回 item/空列表 0.5（且空列表是合法结果，不得一律判 0） |
| 75 / 84 / 92 / 179 | 定位对象 0.5 + 列全成员 0.5 |
| 99 | 执行查询 0.5 + 报告计数 0.5 |
| 101 / 146 / 147 | 设置日期 0.5 + 返回结果 0.5 |
| 175 | 设置过滤 0.5 + 返回结果 0.5 |

## 后续批次计划（供确认）

- 第 3 批：`query` 7 题（#40/#48/#54/#97/#104/#181/#183）+ `links` 6 题（#69/#85/#151/#164/#167/#195）+ `pdf`/`create`/`draft_reset` 3 题（#67/#90/#113）。
- 第 4 批：`ordinary_query` 剩余 132 题（多为单值查询，按字段类型归组）。
- 第 5 批（视需要）：`未记录` 导航类 299 题——业务条件见 native_contract，本文档内无据可细分，需另行取得 native_contract 后再动。



---

<!-- ===== reward-criteria-decomposition-batch3-query-links-pdf.md ==== -->

# 子奖励判断准则细分 · 第三批：query / links / pdf / create / draft_reset 型剩余题目（16 题）

> 延续 `reward-criteria-decomposition.md`（第一批 11 题）、`reward-criteria-decomposition-batch1-update.md`（update 型 26 题）、`reward-criteria-decomposition-batch2-collection-query.md`（collection_query 型 13 题）的 Gate + Quality 二段式。
> 本文只做**判定准则的细分与可操作化**，不实现奖励计算、不重设计奖励方案。
> 计算公式 `R = null / 0 / base + (1-base)·Q` 由计算层实现，base 数值不在本文范围。
> 本文产出：每道题的 gate（硬前提合取）、quality（Q 维度 + 锚点 + 观察方式）、适用场景、边界情况、不应给分的反例。

## 0. 范围与方法（仅依据两份文档）

- **数据源**：`docs/reward-inventory/binary-reward-tasks.md`（二值题目清单，497 题）。
- **本批范围**：第二批文档「后续批次计划」中明确的第 3 批，即以下 5 个分支的**全部剩余题目**，共 **16 题**：
  - `admin_contract_rules.checks:query` 7 题；
  - `admin_contract_rules.checks:links` 6 题；
  - `admin_contract_rules.checks:pdf` 1 题；
  - `admin_contract_rules.checks:create` 1 题；
  - `admin_contract_rules.checks:draft_reset` 1 题。
- **方法**：与既有三批的 Gate+Quality 完全一致；不重设计奖励计算，不与二值准则冲突。
- **核对结论**（逐分支判定条件，直接取自数据源）：
  - `query`：`answer_<字段>`（提交的单字段值与原绑定对象的参考值相符）+ `same_local_deployment` + `valid_authenticated_page` + `records_unchanged` + `answer_schema`。其中 #97/#104 的判定条件由题绑定的 source contract 与 evaluator 分支给出。
  - `links`：`requested_relationship_change`（关系集合发生要求的增删 + 集合包含约束）+ `same_local_deployment` + `valid_authenticated_page` + `other_relationships_unchanged`。
  - `pdf`：`downloaded_correct_documents` + `same_local_deployment` + `valid_authenticated_page` + `records_unchanged`。
  - `create`：`new_matching_record_saved` + `created_record_conditions` + `same_local_deployment` + `valid_authenticated_page` + `existing_records_unchanged`。
  - `draft_reset`：`form_reset` + `same_local_deployment` + `valid_authenticated_page` + `correct_form` + `no_record_created`。

**全部分支分布（本批完成后）：**

| 分支 | 总数 | 已细分 | 本批 | 剩余 |
|---|---|---|---|---|
| `update` | 32 | 32（批0+批1） | — | 0 |
| `collection_query` | 14 | 14（批0+批2） | — | 0 |
| `query` | 7 | 0 | **7** | 0 |
| `links` | 6 | 0 | **6** | 0 |
| `pdf` / `create` / `draft_reset` | 3 | 0 | **3** | 0 |
| `ordinary_query`（带 `answer_<字段>` 明细） | 136 | 4 | — | 132 |
| `ordinary_query`（内嵌 `native_contract` JSON） | 299 | 0 | — | 299 |

> 本批完成后，除 `ordinary_query` 两类（带 answer 明细 132 题 + 内嵌 native_contract 299 题）外，其余分支全部细分完毕。
> 注：两类 `ordinary_query` 的判定条件**均在本文档内可读**——前者为 `answer_<字段>` 明文，后者为可解析的 `native_contract` JSON（详见文末「更正说明」）。

---

## 1. query 型通用子奖励框架（本批 7 题共享）

### 1.1 成功门控条件（gate，硬前提合取）

> 任一硬前提**明确为假** → 该题 R=0；任一关键项**证据不足且无法确认** → R=null（不转 0、不转失败）。

- **G1 目标对象身份正确**：绑定对象为题面指定实体（客户账号由 email 锁定 / 客户组 / 产品 / shipments 页面），非同名或相邻实体。
- **G2 提交字段值精确匹配**（`answer_<字段>`）：提交的单字段值与原绑定对象参考值相符。
  - 单字段题（#40/#48/#54/#183）：单值精确匹配。
  - 双字段题（#104）：name 与 SKU 两字段均精确匹配。
  - 集合题（#181）：排除网站集合与参考集合精确相等（无遗漏、无多余、无重复）。
  - 聚合题（#97）：返回的 shipment 确为该页面 total quantity 最大者（与本地记录实际最大值一致）。
- **G3 `records_unchanged`**：只读查询，未修改任何数据。
- **G4 `same_local_deployment`**：终页 netloc 等于原本地部署。
- **G5 `valid_authenticated_page`**：终页未被标记登录页或页面错误。
- **G6 `answer_schema`**：提交答案字段/格式符合 schema，不为漏答放宽。

### 1.2 质量维度（仅在 gate 通过后计分；权重和 = 1.0）

| 维度 | 权重 | 判定标准（0.0 / 0.5 / 1.0 锚点，可插值） | 观察方式 |
|---|---|---|---|
| 目标定位规范 | 0.30 | 0.0：定位错误实体 / 同名混淆 / 盲答；0.5：定位对但过程有无关浏览；1.0：精确定位题面绑定实体，无冗余 | 检查访问/确认的目标实体是否唯一且正确 |
| 来源合规 | 0.30 | 0.0：推测或外部数据；0.5：部分来自本地；1.0：只读本地记录 | 检查答案值是否来自本地记录 |
| 字段校验 | 0.25 | 0.0：字段来源混乱 / 格式不符；0.5：轻微格式问题；1.0：字段正确且多字段题两字段同源不混淆 | 检查字段值及多字段同源性 |
| 证据充分性 | 0.15 | 0.0：无可见证据；0.5：部分字段可见；1.0：答案值有可见字段/记录支撑 | 答案字段值是否在 observation 可见 |

### 1.3 通用反例（do_not_do，本批 query 型全部适用）

- 不把「定位对象」与「读取字段值」拆成两个独立分数（同一查询的两个环节）。
- 不把「答案值正确」单独发分（已在 G2）。
- 不把「格式符合 schema」单独发分（已在 G6）。
- 不把「定位到目标对象」单独发分（已在 G1）。
- 多字段题不拆成「字段 A 对 + 字段 B 对」两个独立分数（同一记录的两个字段，同 gate 验证）。

### 1.4 通用边界（unknown_handling，本批 query 型全部适用）

- 无法确认提交值是否与本地参考值相符 → null（明确不相符则 0）。
- 无法确定绑定对象是否为题面指定实体 → null（明确为假则 0）。
- 多字段题仅部分字段可验证 → 视为证据不足 → null（不得按「对了一半」给分）。

---

## 2. links 型通用子奖励框架（本批 6 题共享）

### 2.1 成功门控条件（gate，硬前提合取）

- **G1 目标主体产品正确**：关系操作的主体产品为题面指定产品，非同名/相邻产品。
- **G2 `requested_relationship_change`**：关系集合发生题面要求的增/删，且满足集合包含约束，改动已生效：
  - 增（#69/#85/#151/#164/#167）：目标关系（cross-sell / related / up-sell）已出现在该产品的关系集合中；
  - 删（#195）：目标 up-sell 关系已从该产品的关系集合中移除。
- **G3 `other_relationships_unchanged`**：目标关系类型以外、或目标产品以外的关系保持（未误增/误删其他关系）。
- **G4 `same_local_deployment`**：终页 netloc 等于原本地部署。
- **G5 `valid_authenticated_page`**：终页未被标记登录页或页面错误。

### 2.2 质量维度（仅在 gate 通过后计分；权重和 = 1.0）

| 维度 | 权重 | 判定标准（0.0 / 0.5 / 1.0 锚点，可插值） | 观察方式 |
|---|---|---|---|
| 操作范围 | 0.35 | 0.0：修改了其他关系/其他产品，或大量无关探索；0.5：少量无关浏览；1.0：只操作目标产品目标关系，无冗余 | 统计非目标关系/非目标产品操作次数 |
| 验证规范 | 0.30 | 0.0：盲改，无可观察核对；0.5：只核对主体产品或只核对目标关系；1.0：提交前同时确认主体产品与目标关系 | 检查提交前是否有读取/确认记录 |
| 保存确认 | 0.20 | 0.0：未保存或保存失败；0.5：执行保存但未确认生效；1.0：保存后复查关系集合仍满足要求 | save 事件 + 保存后复查事件 |
| 证据充分性 | 0.15 | 0.0：无页面证据；0.5：部分可见；1.0：关系增/删有可见关系列表/字段证据 | 关系集合状态是否在 observation 可见 |

### 2.3 通用反例（do_not_do，本批 links 型全部适用）

- 不把「选对主体产品」与「增/删关系」拆成两个独立分数。
- 不把「关系增/删」与「保存」拆成两个独立分数（同一写操作的两阶段）。
- 不给「定位到主体产品」单独发分（已在 G1）。
- 不因「增对了关系但误删了其他关系」给满分（G3 违反 → 0）。
- 增型题（#69/#85/#151/#164/#167）与删型题（#195）方向互斥，不得混用判分标准。

### 2.4 通用边界（unknown_handling，本批 links 型全部适用）

- 无法确认关系增/删是否已生效（无保存后状态记录）→ null。
- 无法确定主体产品是否为题面指定产品 → null（明确为假则 0）。
- 目标关系已正确增/删、但 `other_relationships_unchanged` 被破坏 → gate 不通过 → 0。

---

## 3. 逐题细分

## A. query 型（7 题）

### 题目 40（2c4b678cfc6978ab9182）—题面：Find out when Jane Doe created her customer account For this local training variant, the target account email is jane.doe@gmail.com.—子奖励判断准则

- **适用场景**：查询指定客户账号的注册/创建时间；实体由 email 锁定。
- **成功门控条件（gate）**：
  - G1 绑定对象 == jane.doe@gmail.com 的客户账号（不得误读其他同名 Jane Doe 或相邻账号）；
  - G2 `answer_created_at` 与该账号参考值精确匹配（不预设具体日期，以本地记录为准）；
  - G3–G6 同 §1.1（records_unchanged / same_local_deployment / valid_authenticated_page / answer_schema）。
- **质量维度 / 判定标准**：同 §1.2。
- **边界情况**：无法确认账号与 email 匹配 → null；无法确认创建时间与本地记录一致 → null。
- **不应给分的反例**：不把「定位账号」与「读取 created_at」拆两个分数；不因「定位对了但时间读错」给分（G2 违反 → 0）。

### 题目 48（3645416e63ddda135f29）—题面：Find the most recent customer registration date—子奖励判断准则

- **适用场景**：聚合查询——客户注册日期中的最新值。
- **成功门控条件（gate）**：
  - G1 查询范围为「客户注册日期」字段（不得误读为创建时间 / 订单日期 / 其他日期字段）；
  - G2 `answer_created_at` == 本地客户记录中**最新的**注册日期（取最大日期，非任取一个）；
  - G3–G6 同 §1.1。
- **质量维度 / 判定标准**：同 §1.2。
- **边界情况**：无法确认「最新」是否为全局最大（无法核对全部客户记录）→ null。
- **不应给分的反例**：不把「查找注册日期」与「取最新值」拆两个分数；不因「返回了某个注册日期」给分（须为最大值，否则 G2 违反 → 0）。

### 题目 54（3b51c7012090fd5e495b）—题面：Check which customer group Adam Garcia belongs to For this local training variant, the target account email is adam.garcia@gmail.com.—子奖励判断准则

- **适用场景**：查询指定客户账号所属客户组；实体由 email 锁定。
- **成功门控条件（gate）**：
  - G1 绑定对象 == adam.garcia@gmail.com 的客户账号；
  - G2 `answer_group_name` == 该账号实际所属客户组的名称（与本地记录一致）；
  - G3–G6 同 §1.1。
- **质量维度 / 判定标准**：同 §1.2。
- **边界情况**：无法确认账号与 email 匹配 → null；无法确认所属组名称 → null。
- **不应给分的反例**：不把「定位账号」与「读所属组」拆两个分数；不因「返回了某个组名」给分（须为真实所属组，否则 G2 违反 → 0）。

### 题目 97（6fe8b1378a01b3b210c6）—题面：Find the shipment with the highest total quantity on the shipments page.—子奖励判断准则

- **适用场景**：聚合查询——shipments 页面中 total quantity 最大的 shipment；判定条件由题绑定的 source contract 与 evaluator 分支给出。
- **成功门控条件（gate）**：
  - G1 查询范围为 shipments 页面上的 shipment（不得误用订单/产品等其他实体）；
  - G2 返回的 shipment 确为 total quantity 最大者（与本地 shipments 记录实际最大值一致，非主观挑选）；
  - G3–G6 同 §1.1。
- **质量维度 / 判定标准**：同 §1.2。
- **边界情况**：无法确认「最高 total quantity」是否为全局最大（无法核对全部 shipments）→ null。
- **不应给分的反例**：不把「找到 shipments 页面」与「定位最高者」拆两个分数；不因「返回了某个 shipment」给分（须为最大，否则 G2 违反 → 0）。

### 题目 104（7a0199e38526591e656f）—题面：Report the name and SKU of Yoga Mat Pro.—子奖励判断准则

- **适用场景**：双字段查询——同一产品的 name 与 SKU；判定条件含 `answer_name` + `answer_schema`。
- **成功门控条件（gate）**：
  - G1 绑定对象 == 产品 "Yoga Mat Pro"（不得误读同名/相邻产品）；
  - G2 name 与 SKU 两字段均与该产品参考值精确匹配（两字段必须同源、同时正确）；
  - G3–G6 同 §1.1。
- **质量维度 / 判定标准**：同 §1.2；「字段校验」维度重点观察 name 与 SKU 是否来自同一条产品记录、有无混淆。
- **边界情况**：仅 name 或仅 SKU 可验证 → 证据不足 → null（不得按「对了一半」给分）。
- **不应给分的反例**：不拆成「name 对 0.5 + SKU 对 0.5」两个独立分数（同一记录的两个字段，同 gate）；不因「name 对但 SKU 错」给任何分（G2 违反 → 0）。

### 题目 181（e154d00d7844088d94d7）—题面：Find out which websites are excluded from the Updated General Customers group—子奖励判断准则

- **适用场景**：集合查询——某客户组的排除网站集合；`answer_excluded_websites` 为集合精确匹配。
- **成功门控条件（gate）**：
  - G1 绑定对象 == 客户组 "Updated General Customers"；
  - G2 `answer_excluded_websites` 与该组排除网站参考集合**精确相等**（无遗漏、无多余、无重复）；
  - G3–G6 同 §1.1。
- **质量维度 / 判定标准**：同 §1.2。
- **边界情况**：无法确认排除网站集合是否穷尽（无法核对完整 exclusion 列表）→ null。
- **不应给分的反例**：不把「定位组」与「列排除网站」拆两个分数；不因「列了部分网站」给分（须完整集合，否则 G2 违反 → 0）；注意 #181 是**查询**（只读），不得与 #21/#182（exclude 写操作）的写操作判分混淆。

### 题目 183（e191611698289fe50395）—题面：View when customer Adam Garcia created his account For this local training variant, the target account email is adam.garcia@gmail.com.—子奖励判断准则

- **适用场景**：查询指定客户账号的创建时间；与 #40 同型、目标账号不同（#40 为 Jane Doe）。
- **成功门控条件（gate）**：
  - G1 绑定对象 == adam.garcia@gmail.com 的客户账号；
  - G2 `answer_created_at` 与该账号参考值精确匹配；
  - G3–G6 同 §1.1。
- **质量维度 / 判定标准**：同 §1.2。
- **边界情况**：无法确认账号与 email 匹配 → null；无法确认创建时间与本地记录一致 → null。
- **不应给分的反例**：不把「定位账号」与「读 created_at」拆两个分数；不把 #183 与 #40（Jane Doe）的目标账号混用。

---

## B. links 型（6 题）

### 题目 69（4a9824d5f9d587cc9c6c）—题面：Set up cross-sell products for Example Product Deluxe 2023—子奖励判断准则

- **适用场景**：为产品建立 cross-sell 关系（增型）。
- **成功门控条件（gate）**：
  - G1 主体产品 == "Example Product Deluxe 2023"；
  - G2 cross-sell 关系已建立并出现在该产品关系集合中（满足集合包含约束，改动已生效）；
  - G3–G5 同 §2.1。
- **质量维度 / 判定标准**：同 §2.2。
- **边界情况**：同 §2.4。
- **不应给分的反例**：不拆「定位产品」与「建立 cross-sell」；不因「建立了关系但未保存生效」给分（G2 违反 → 0）。

### 题目 85（5e356def10426fbef596）—题面：Set up cross-sell products for the Blue T-Shirt to increase cart value.—子奖励判断准则

- **适用场景**：为产品建立 cross-sell 关系（增型）；"to increase cart value" 为目的描述，非第二动作。
- **成功门控条件（gate）**：
  - G1 主体产品 == "Blue T-Shirt"；
  - G2 cross-sell 关系已建立并出现在该产品关系集合中（改动已生效）；
  - G3–G5 同 §2.1。
- **质量维度 / 判定标准**：同 §2.2。
- **边界情况**：同 §2.4。
- **不应给分的反例**：不拆「建立 cross-sell」与「（隐式）提升 cart value」两个分数（目的从句不是独立任务）；不因「建立关系但未保存」给分。

### 题目 151（c4c457724ca5b3facc2f）—题面：Add a new related product to the Blue T-Shirt—子奖励判断准则

- **适用场景**：为产品新增 related 关系（增型）。
- **成功门控条件（gate）**：
  - G1 主体产品 == "Blue T-Shirt"；
  - G2 新增的 related product 关系已出现在该产品关系集合中（改动已生效）；
  - G3–G5 同 §2.1。
- **质量维度 / 判定标准**：同 §2.2。
- **边界情况**：同 §2.4。
- **不应给分的反例**：不拆「定位产品」与「添加 related」；与 #164（同主体、同关系类型，但 task_id 不同）各自独立判分，不得合并；不因「添加未保存」给分。

### 题目 164（d2920efde53b41c1a1b6）—题面：Add related products to the Blue T-Shirt product.—子奖励判断准则

- **适用场景**：为产品新增 related 关系（增型，复数表述）。
- **成功门控条件（gate）**：
  - G1 主体产品 == "Blue T-Shirt"；
  - G2 新增的 related products 关系已出现在该产品关系集合中（改动已生效）；
  - G3–G5 同 §2.1。
- **质量维度 / 判定标准**：同 §2.2。
- **边界情况**：同 §2.4。
- **不应给分的反例**：与 #151 目标高度相似但 task_id 不同，各自独立判分，不得合并；不拆「定位产品」与「添加 related」；不因「添加未保存」给分。

### 题目 167（d52c0aa1fd01a13549bf）—题面：Add a related product to the Yoga Mat Pro listing—子奖励判断准则

- **适用场景**：为产品新增 related 关系（增型）。
- **成功门控条件（gate）**：
  - G1 主体产品 == "Yoga Mat Pro"；
  - G2 新增的 related product 关系已出现在该产品关系集合中（改动已生效）；
  - G3–G5 同 §2.1。
- **质量维度 / 判定标准**：同 §2.2。
- **边界情况**：同 §2.4。
- **不应给分的反例**：不拆「定位产品」与「添加 related」；不把 #167（Yoga Mat Pro）与 #151/#164（Blue T-Shirt）主体产品混用。

### 题目 195（f412f90491545b946b32）—题面：Remove an existing up-sell product from the Blue T-Shirt—子奖励判断准则

- **适用场景**：为产品删除 up-sell 关系（删型，方向与增型题互斥）。
- **成功门控条件（gate）**：
  - G1 主体产品 == "Blue T-Shirt"；
  - G2 目标 up-sell 关系已从该产品关系集合中移除（改动已生效，且满足集合包含约束）；
  - G3–G5 同 §2.1。
- **质量维度 / 判定标准**：同 §2.2。
- **边界情况**：同 §2.4。
- **不应给分的反例**：不拆「定位产品」与「移除 up-sell」；不得把「新增 up-sell」视为等价成功（方向相反 → G2 不满足 → 0）；与增型题（#69/#85/#151/#164/#167）判分方向不得混用。

---

## C. pdf 型（1 题）

### 题目 67（485486b9f7dfb1584bb6）—题面：For this local training task, select order #000000002 and download its existing training shipping label as a PDF. The fixed label is for simulation only and is not valid for postage. Do not purchase or generate a live carrier label.—子奖励判断准则

- **适用场景**：下载指定订单已有的（固定训练用）shipping label PDF；题面明示「仅模拟、禁止购买/生成真实承运标签」。
- **成功门控条件（gate）**：
  - G1 目标订单 == "#000000002"（字符串，保留前导零）；
  - G2 `downloaded_correct_documents`：至少一个实际下载产物通过内容及选中对象集合比较（即下载的是该订单的 shipping label PDF，非其他文档/其他订单）；
  - G3 未购买或生成真实承运标签（题面明示禁止项；违反即视为未完成「下载已有固定标签」的要求）；
  - G4 `records_unchanged`：只读，未修改订单数据；
  - G5 `same_local_deployment`；G6 `valid_authenticated_page`。
- **质量维度 / 判定标准**（权重和 = 1.0）：
  - 目标定位规范 0.30：0.0 选错订单/下载错文档；0.5 定位对但过程有冗余；1.0 精确选中 #000000002 的 shipping label；
  - 操作合规 0.30：0.0 购买/生成真实承运标签；0.5 打开过生成/购买入口但未执行；1.0 只执行下载已有固定标签；
  - 下载确认 0.25：0.0 无下载产物；0.5 有下载动作但产物未确认；1.0 实际下载产物存在且正确；
  - 证据充分性 0.15：下载产物/文件名在 observation 可见。
- **边界情况**：无法确认下载产物是否与目标订单标签一致 → null。
- **不应给分的反例**：不把「选中订单」与「下载 PDF」拆两个分数；不因「下载了任意 PDF」给分（须为该订单 shipping label，否则 G2 违反 → 0）；「购买/生成真实标签」绝不视为等价成功（G3 违反 → 0）。

---

## D. create 型（1 题）

### 题目 90（621e3a379562905e5595）—题面：For this local training variant, add Adam Garcia (adam.garcia@gmail.com), who currently has no subscriber record, to the newsletter subscribers. Use the existing customer account.—子奖励判断准则

- **适用场景**：为已存在客户账号新增一条 newsletter subscriber 记录；题面明示「使用已有账号」。
- **成功门控条件（gate）**：
  - G1 使用已存在的客户账号 adam.garcia@gmail.com（不得新建同名客户账号；"Use the existing customer account" 是题面硬约束）；
  - G2 `new_matching_record_saved`：新增的订阅者记录**恰好一条**，且匹配选择条件（对应 adam.garcia@gmail.com）；
  - G3 `created_record_conditions`：该唯一新记录整体满足 create_conditions；
  - G4 `existing_records_unchanged`：原有实体记录保持（未改动既有账号/其他记录）；
  - G5 `same_local_deployment`；G6 `valid_authenticated_page`。
- **质量维度 / 判定标准**（权重和 = 1.0）：
  - 操作范围 0.30：0.0 新建账号或改动其他记录；0.5 少量无关浏览；1.0 只为已有账号新增订阅者记录；
  - 验证规范 0.30：0.0 盲操作；0.5 只核对账号或只核对订阅动作；1.0 提交前确认使用已有账号且目标为 newsletter subscribers；
  - 保存确认 0.25：0.0 未保存/失败；0.5 保存未确认；1.0 保存后复查新增记录存在且唯一；
  - 证据充分性 0.15：新增记录在 observation 可见。
- **边界情况**：无法确认是否使用了已有账号（而非新建）→ null；无法确认新增记录是否唯一 → null。
- **不应给分的反例**：不把「定位账号」与「新增订阅」拆两个分数；不因「新建了一个同名账号并订阅」给分（G1/G4 违反 → 0）；不因「新增多条订阅记录」给分（G2 违反 → 0）。

---

## E. draft_reset 型（1 题）

### 题目 113（89c78a04c5f2b1e693ac）—题面：Reset the displayed new customer group form to discard Unsaved Training Group without saving a group.—子奖励判断准则

- **适用场景**：重置（放弃）表单中已填写但未保存的客户组改动；核心动作是 reset（丢弃），而非 save。
- **成功门控条件（gate）**：
  - G1 `correct_form`：终页路径为原（新建客户组）表单路径；
  - G2 `form_reset`：非空表单默认字段全部恢复为原值（即 "Unsaved Training Group" 的改动被丢弃、表单回到初始默认值）；
  - G3 `no_record_created`：未创建新客户组记录（"without saving a group" 是题面硬约束）；
  - G4 `same_local_deployment`；G5 `valid_authenticated_page`。
- **质量维度 / 判定标准**（权重和 = 1.0）：
  - 操作范围 0.30：0.0 保存了组或改动其他表单；0.5 少量无关浏览；1.0 只执行 reset 丢弃改动；
  - 重置确认 0.30：0.0 未重置或字段未恢复；0.5 部分字段恢复；1.0 非空默认字段全部恢复原值；
  - 未创建确认 0.25：0.0 实际创建了新组；0.5 有保存动作但已回退；1.0 全程未保存、未创建新记录；
  - 证据充分性 0.15：表单重置后状态/未创建记录在 observation 可见。
- **边界情况**：无法确认表单字段是否全部恢复原值 → null；无法确认是否创建了新记录 → null。
- **不应给分的反例**：不把「reset 表单」与「不保存组」拆两个分数（同一动作的结果与约束）；不因「保存了组但组名正确」给分（G3 违反 → 0）；不把「重新编辑后再保存」视为等价于「reset 丢弃」的成功操作。

---

## 附录：错误拆法对照表（本批新增，防回归）

| 题号 | 错误拆法（禁止） |
|---|---|
| 40 / 48 / 54 / 183 | 定位对象 0.5 + 读字段值 0.5 |
| 97 | 找到 shipments 页 0.5 + 定位最高者 0.5 |
| 104 | name 对 0.5 + SKU 对 0.5（同一记录两字段，同 gate） |
| 181 | 定位组 0.5 + 列排除网站 0.5（且为只读查询，不得与 #21/#182 写操作判分混淆） |
| 69 / 85 / 151 / 164 / 167 | 选对产品 0.5 + 增对关系 0.5（增型） |
| 195 | 选对产品 0.5 + 删对关系 0.5（删型，与增型方向互斥） |
| 67 | 选中订单 0.5 + 下载 PDF 0.5（且购买/生成真实标签绝不视为等价成功） |
| 90 | 定位账号 0.5 + 新增订阅 0.5（且新建同名账号不视为等价成功） |
| 113 | reset 表单 0.5 + 不保存组 0.5（同一动作的结果与约束） |

## 后续批次计划（供确认）

- 第 4 批：`ordinary_query` 的 136 题（`answer_<字段>` 单值/多字段查询，按字段类型归组）。
- 第 5 批：`ordinary_query` 的 **299 题**（判定条件在文档内已展开为 `native_contract` JSON，**无需另取文件**）。

> **更正说明（重要）**：先前曾写「299 题本文件内无据可细分、需另行取得 native_contract」，此为误判。经逐题解析 `binary-reward-tasks.md`：
> - 全库 497 个题目块 = 62 题 admin_contract（已全部细分）+ 136 题 `ordinary_query`（带 `answer_<字段>`）+ **299 题 `ordinary_query` 且内嵌 `native_contract` JSON**；
> - 299 题的 JSON **全部可解析（0 缺失 / 0 损坏）**，其 `completion` 以 `path_regex`（240 题）与 `heading_regex`（184 题）为主，即「终页路径匹配 + 标题可见」的导航终态判定；`spec.kind` 为 `page_navigation` 30 题、`menu_navigation` 24 题，其余 245 题为 `completion`/`control_target_path` 等不同结构。
> - 因此第 5 批**具备细分依据**，可按 `completion.path_regex + heading_regex`（及可选 `identity_source` / `title_regex`）建立统一的 Gate + Quality 框架，再按 `binding_family` 归组特化。



---

<!-- ===== reward-criteria-decomposition-batch4-ordinary-query-answer.md ==== -->

# 子奖励判断准则细分 · 第四批：ordinary_query answer 明细剩余题目（132 题）

> 延续 `reward-criteria-decomposition.md`（批0 11 题）、`reward-criteria-decomposition-batch1-update.md`（update 26 题）、`reward-criteria-decomposition-batch2-collection-query.md`（collection_query 13 题）、`reward-criteria-decomposition-batch3-query-links-pdf.md`（query/links/pdf/create/draft_reset 16 题）的 Gate + Quality 二段式。
> 本文只做**判定准则的细分与可操作化**，不实现奖励计算、不重设计奖励方案。
> 计算公式 `R = null / 0 / base + (1-base)·Q` 由计算层实现，base 数值不在本文范围。
> 本文产出：每道题的 gate（硬前提合取）、quality（Q 维度 + 锚点 + 观察方式）、适用场景、边界情况、不应给分的反例。

## 0. 范围与方法（仅依据文档）

- **数据源**：`docs/reward-inventory/binary-reward-tasks.md`（497 题）。
- **本批范围**：`site_query_rules.evaluate_query:ordinary_query` 分支中带 `answer_<字段>` 明细或 source-contract 判定的**剩余 132 题**。
- **与既有批次的衔接**：ordinary_query 带 answer 明细共 136 题，其中 4 题已在批0 细分（#31/#32/#34/#36），本批为**剩余 132 题**；`native_contract` 内嵌的 299 题另属第 5 批，不在本批。
- **核对结论**：本批 132 题判定条件**同构**，均为 `answer_<字段>`（提交值与原绑定对象参考值相符）+ `page_valid` + `requested_records_unchanged` + `answer_schema`；7 题为「判定由题绑定 source contract + evaluator 分支给出」。差异仅由**题面**驱动。

**分支分布（本批完成后）：**

| 分支 | 总数 | 已细分 | 本批 | 剩余 |
|---|---|---|---|---|
| `update` | 32 | 32（批0+批1） | — | 0 |
| `collection_query` | 14 | 14（批0+批2） | — | 0 |
| `query` | 7 | 7（批3） | — | 0 |
| `links` | 6 | 6（批3） | — | 0 |
| `pdf`/`create`/`draft_reset` | 3 | 3（批3） | — | 0 |
| `ordinary_query`（带 answer 明细） | 136 | 4（批0） | **132** | 0 |
| `ordinary_query`（内嵌 native_contract） | 299 | 0 | — | 299（第 5 批） |

### 0.1 权重方案登记（对应 reminder §4）

本批全部 132 题均为**只读单值/聚合查询**，无写操作，故不适用 update/links 型的「操作范围/保存确认」维度。
采用**方案 B**：沿用已登记的 query 型权重方案（目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15），权重和恒 = 1.0，不引入第三套未登记权重。
理由：只读查询的核心风险是「定位错实体」「答案非本地来源」「字段读错/同源混淆」；无「保存生效」环节，故证据充分性权重最低、定位与来源并重。

## 1. ordinary_query answer 明细通用框架（本批 132 题共享）

### 1.1 成功门控条件（gate，硬前提合取）

> 任一硬前提**明确为假** → 该题 R=0；任一关键项**证据不足且无法确认** → R=null（不转 0、不转失败）。

- **G1 目标绑定对象身份正确**：查询对象为题面指定实体（产品/项目/论坛/帖子/文章/订单/路线/用户等），非同名或相邻实体；`answer_<字段>` 谓词中的「原绑定对象」即此实体。
- **G2 提交字段值精确匹配**（`answer_<字段>`）：提交的单字段值/计数/最值/布尔值/集合与原绑定对象参考值相符（1:1 映射该谓词，不另立标准）。
- **G3 `requested_records_unchanged`**：只读查询，未修改任何数据（含题面明示的「不下单/不改购物车/不改地址」）。
- **G4 `page_valid`**：查询页面健康可用（≠ 目标定位正确，不是单独发分项）。
- **G5 `answer_schema`**：提交答案字段/格式符合 schema，不为漏答放宽。

### 1.2 质量维度（仅在 gate 通过后计分；权重和 = 1.0）

| 维度 | 权重 | 判定标准（0.0 / 0.5 / 1.0 锚点，可插值） | 观察方式 |
|---|---|---|---|
| 目标定位规范 | 0.30 | 0.0：定位错误实体/同名混淆/盲答；0.5：定位对但过程有无关浏览；1.0：精确锁定题面绑定实体，无冗余 | 检查访问/确认的目标实体是否唯一且正确 |
| 来源合规 | 0.30 | 0.0：推测或外部数据；0.5：部分来自本地；1.0：只读本地记录 | 检查答案值是否来自本地记录 |
| 字段校验 | 0.25 | 0.0：字段来源混乱/格式不符；0.5：轻微格式问题；1.0：字段正确，多字段/集合题同源不混淆 | 检查字段值及多字段同源性 |
| 证据充分性 | 0.15 | 0.0：无可见证据；0.5：部分字段可见；1.0：答案值有可见字段/记录支撑 | 答案字段值是否在 observation 可见 |

### 1.3 通用反例（do_not_do，本批全部适用）

- 不把「定位对象」与「读取字段值/计数/最值」拆成两个独立分数（同一查询的两个环节）。
- 不把「答案值正确」单独发分（已在 G2）；不把「格式符合 schema」单独发分（已在 G5）。
- 不把「定位到目标对象」单独发分（已在 G1）。
- 多字段题不拆成「字段 A 对 + 字段 B 对」两个独立分数（同一记录，同 gate 验证）。
- 不因「页面有效但答案错」「标题对但用户名错」等不可信结果给分（G2 违反 → 0）。

### 1.4 通用边界（unknown_handling，本批全部适用）

- 无法确认提交值是否与本地参考值相符 → null（明确不相符则 0）。
- 无法确定绑定对象是否为题面指定实体 → null（明确为假则 0）。
- 多字段题仅部分字段可验证 → 证据不足 → null，不得按「对了一半」给分。

## 2. 字段类型子框架

### 2.1 单值字段取值

- **适用场景**：查询题面指定实体的单值字段，只读。
- **gate 特化**：G2 = `answer_字段` 与本地记录参考值**精确匹配**（以本地记录为准，非推测、非相邻实体）；其余 G1/G3/G4/G5 同 §1.1。
- **quality 观察补充**：「字段校验」观察字段来源单一、无相邻实体混淆（其余同 §1.2）。
- **不应给分的反例**：不把「定位实体」与「读字段值」拆两个分数；不因「定位对但值读错」给分（G2 违反→0）；不因「返回任意同类值」给分。
- **边界情况**：无法确认提交值与本地参考值是否相符 → null（明确不符则 0）；无法确认绑定实体 → null（明确为假则 0）。

### 2.2 实体属性计数

- **适用场景**：查询题面指定实体的计数属性（单值），只读。
- **gate 特化**：G2 = `answer_字段` 与本地记录该计数**精确匹配**（读自目标实体页面的总数，非只数部分）；其余 G1/G3/G4/G5 同 §1.1。
- **quality 观察补充**：「目标定位规范」观察是否读取正确总数而非只数当前页（其余同 §1.2）。
- **不应给分的反例**：不把「定位实体」与「读计数」拆两个分数；不把「只数部分/当前页」判通过（G2 违反→0）。
- **边界情况**：无法确认计数是否穷尽/正确 → null。

### 2.3 集合内计数

- **适用场景**：在指定范围内按条件计数，只读。
- **gate 特化**：G2 = `answer_字段` 与本地记录中满足条件的记录总数**精确匹配**（穷尽整个范围，非只数当前页）；其余 G1/G3/G4/G5 同 §1.1。
- **quality 观察补充**：「目标定位规范」观察是否穷尽范围；「字段校验」观察条件是否与题面一致（其余同 §1.2）。
- **不应给分的反例**：不把「设置条件」与「计数」拆两个分数；不把「只数当前页」判通过（G2 违反→0）。
- **边界情况**：无法确认是否穷尽范围 → null。

### 2.4 最值聚合

- **适用场景**：在指定范围内取最值（最大/最小/最新/最早），只读。
- **gate 特化**：G2 = `answer_字段` == 本地记录中的**实际最值**（最大/最小/最新/最早；穷尽比较所有候选，非任取、非主观）；其余 G1/G3/G4/G5 同 §1.1。
- **quality 观察补充**：「目标定位规范」观察是否穷尽比较全部候选而非任取（其余同 §1.2）。
- **不应给分的反例**：不把「定位范围」与「取最值」拆两个分数；不因「返回范围内某值」给分（须为实际最值，否则 G2 违反→0）。
- **边界情况**：无法确认最值是否全局最大/最小（无法核对全部候选）→ null；范围为空时按题面返回空/none 合法，不判失败（§6）。

### 2.5 状态枚举

- **适用场景**：查询题面指定实体的状态枚举，只读。
- **gate 特化**：G2 = `answer_字段` == 本地记录**实际状态**（如 subscribed / not subscribed、in stock / out of stock）；'否/缺货' 是合法状态值，不得判失败；其余 G1/G3/G4/G5 同 §1.1。
- **quality 观察补充**：「字段校验」观察状态值是否与本地记录一致、未把'否'当失败（其余同 §1.2）。
- **不应给分的反例**：不把「定位实体」与「读状态」拆两个分数；不把「未订阅/缺货」判失败（合法状态值）。
- **边界情况**：无法确认实际状态 → null；'否' 状态不得判失败。

### 2.6 日期时间

- **适用场景**：查询题面指定实体的日期/时间字段，只读。
- **gate 特化**：G2 = `answer_字段` 与本地记录参考日期**精确匹配**（含时区/格式；题面有格式要求时须满足）；其余 G1/G3/G4/G5 同 §1.1。
- **quality 观察补充**：「字段校验」观察时区/格式是否满足题面要求（其余同 §1.2）。
- **不应给分的反例**：不把「定位实体」与「读日期」拆两个分数；不因「日期对但格式/时区错」给分（G2/G5 违反→0）。
- **边界情况**：无法确认日期与本地记录一致 → null。

### 2.7 布尔/存在性

- **适用场景**：存在性/布尔查询，只读。
- **gate 特化**：G2 = `answer_字段` == 本地记录**真实布尔值**；严格区分三态（false / 记录不存在 / 未找到→null，见 §2.7）；其余 G1/G3/G4/G5 同 §1.1。
- **quality 观察补充**：「字段校验」观察三态（false/不存在/未找到）是否与本地真实状态一致（其余同 §1.2）。
- **不应给分的反例**：不把「未找到」记为 false（P1/P5 违反）；不把 false 判为失败；不把「记录不存在」与「值为 false」混淆。
- **边界情况**：无法确认真实布尔值（未找到/证据不足）→ null，不得默认记 false（§5/§6）。

### 2.8 集合/列表

- **适用场景**：集合/列表查询，只读。
- **gate 特化**：G2 = `answer_字段` 与本地参考集合**精确相等**（无遗漏、无多余、无重复）；其余 G1/G3/G4/G5 同 §1.1。
- **quality 观察补充**：「字段校验」观察集合是否无遗漏/无多余/无重复（其余同 §1.2）。
- **不应给分的反例**：不把「定位范围」与「列集合」拆两个分数；不因「列了部分」给分（须完整集合，G2 违反→0）。
- **边界情况**：无法确认集合是否穷尽 → null。

### 2.9 多字段

- **适用场景**：同一记录的多字段查询，只读。
- **gate 特化**：G2 = 多字段（见题面）均与本地参考值**精确匹配**，且**同源**（同一记录）；其余 G1/G3/G4/G5 同 §1.1。
- **quality 观察补充**：「字段校验」观察两字段是否同源、有无混淆（其余同 §1.2）。
- **不应给分的反例**：不拆「字段 A 0.5 + 字段 B 0.5」；不因「一字段对」给分（G2 违反→0）。
- **边界情况**：仅部分字段可验证 → 证据不足 → null，不得按「对了一半」给分。

### 2.10 source-contract 判定

- **适用场景**：判定由题绑定 contract 给出；题面为单一查询/报告动作。
- **gate 特化**：G2 = answer 值满足题绑定 source contract 的判定谓词（与题面语义一致）；其余 G1/G3/G4/G5 同 §1.1。
- **quality 观察补充**：「字段校验」观察答案是否与 contract 谓词一致（其余同 §1.2）。
- **不应给分的反例**：不拆「定位视图」与「读取 scale/coords」；不得脱离 contract 谓词另立标准（P5）。
- **边界情况**：无法确认 answer 是否满足 contract 谓词 → null。

## 3. 逐题细分（132 题）

### 3.1 单值字段取值（45 题）

#### 题目 1（01491075d7002a532057）—题面：Find the SKU number for the Pre-baked Gingerbread House Kit
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段单实体读操作，不拆成定位+取值两个分数"}
- **适用场景：** 查询题面指定实体的单值字段，只读（目标实体：产品 'Pre-baked Gingerbread House Kit'）。
- **成功门控条件（gate）：** G1 目标实体 = 产品 'Pre-baked Gingerbread House Kit'；G2 `answer_sku` 与本地记录参考值**精确匹配**（以本地记录为准，非推测、非相邻实体）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察字段来源单一、无相邻实体混淆。
- **边界情况：** 无法确认提交值与本地参考值是否相符 → null（明确不符则 0）；无法确认绑定实体 → null（明确为假则 0）
- **不应给分的反例：** 不把「定位实体」与「读字段值」拆两个分数；不因「定位对但值读错」给分（G2 违反→0）；不因「返回任意同类值」给分
- **题面特例/备注：** SKU 为精确字符串，不得与 Value Pack 的 SKU 混淆

#### 题目 4（03d66d95ff83bd2b6c60）—题面：Retrieve the price of the Pre-baked Gingerbread House Kit Value Pack.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段单实体读操作，不拆成定位+取值两个分数"}
- **适用场景：** 查询题面指定实体的单值字段，只读（目标实体：产品 'Pre-baked Gingerbread House Kit Value Pack'）。
- **成功门控条件（gate）：** G1 目标实体 = 产品 'Pre-baked Gingerbread House Kit Value Pack'；G2 `answer_price` 与本地记录参考值**精确匹配**（以本地记录为准，非推测、非相邻实体）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察字段来源单一、无相邻实体混淆。
- **边界情况：** 无法确认提交值与本地参考值是否相符 → null（明确不符则 0）；无法确认绑定实体 → null（明确为假则 0）
- **不应给分的反例：** 不把「定位实体」与「读字段值」拆两个分数；不因「定位对但值读错」给分（G2 违反→0）；不因「返回任意同类值」给分

#### 题目 9（09e3cfe5f478c386a220）—题面：Who submitted the article titled “I built a “sentence to playlist” AI capable of turning your playlist ideas into a real playlist in a matter of seconds!”
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段单实体读操作，不拆成定位+取值两个分数"}
- **适用场景：** 查询题面指定实体的单值字段，只读（目标实体：文章（标题为 'I built a "sentence to playlist" AI …'））。
- **成功门控条件（gate）：** G1 目标实体 = 文章（标题为 'I built a "sentence to playlist" AI …'）；G2 `answer_author` 与本地记录参考值**精确匹配**（以本地记录为准，非推测、非相邻实体）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察字段来源单一、无相邻实体混淆。
- **边界情况：** 无法确认提交值与本地参考值是否相符 → null（明确不符则 0）；无法确认绑定实体 → null（明确为假则 0）
- **不应给分的反例：** 不把「定位实体」与「读字段值」拆两个分数；不因「定位对但值读错」给分（G2 违反→0）；不因「返回任意同类值」给分
- **题面特例/备注：** author 为提交该文章的用户名，精确匹配

#### 题目 11（0c0195ce97a7d83dc247）—题面：Check who is the manufacturer of the Gingerbread House Kit.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段单实体读操作，不拆成定位+取值两个分数"}
- **适用场景：** 查询题面指定实体的单值字段，只读（目标实体：产品 'Gingerbread House Kit'）。
- **成功门控条件（gate）：** G1 目标实体 = 产品 'Gingerbread House Kit'；G2 `answer_manufacturer` 与本地记录参考值**精确匹配**（以本地记录为准，非推测、非相邻实体）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察字段来源单一、无相邻实体混淆。
- **边界情况：** 无法确认提交值与本地参考值是否相符 → null（明确不符则 0）；无法确认绑定实体 → null（明确为假则 0）
- **不应给分的反例：** 不把「定位实体」与「读字段值」拆两个分数；不因「定位对但值读错」给分（G2 违反→0）；不因「返回任意同类值」给分

#### 题目 16（0e7d0cf05895d7d5e746）—题面：What is the overall rating of the Pre-baked Gingerbread House Kit Value Pack?
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段单实体读操作，不拆成定位+取值两个分数"}
- **适用场景：** 查询题面指定实体的单值字段，只读（目标实体：产品 'Pre-baked Gingerbread House Kit Value Pack'）。
- **成功门控条件（gate）：** G1 目标实体 = 产品 'Pre-baked Gingerbread House Kit Value Pack'；G2 `answer_rating_percent` 与本地记录参考值**精确匹配**（以本地记录为准，非推测、非相邻实体）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察字段来源单一、无相邻实体混淆。
- **边界情况：** 无法确认提交值与本地参考值是否相符 → null（明确不符则 0）；无法确认绑定实体 → null（明确为假则 0）
- **不应给分的反例：** 不把「定位实体」与「读字段值」拆两个分数；不因「定位对但值读错」给分（G2 违反→0）；不因「返回任意同类值」给分
- **题面特例/备注：** rating_percent 为百分数

#### 题目 20（162eecfe220af06b700f）—题面：View the license type for the a11y-syntax-highlighting project.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段单实体读操作，不拆成定位+取值两个分数"}
- **适用场景：** 查询题面指定实体的单值字段，只读（目标实体：a11y-syntax-highlighting 项目）。
- **成功门控条件（gate）：** G1 目标实体 = a11y-syntax-highlighting 项目；G2 `answer_license_type` 与本地记录参考值**精确匹配**（以本地记录为准，非推测、非相邻实体）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察字段来源单一、无相邻实体混淆。
- **边界情况：** 无法确认提交值与本地参考值是否相符 → null（明确不符则 0）；无法确认绑定实体 → null（明确为假则 0）
- **不应给分的反例：** 不把「定位实体」与「读字段值」拆两个分数；不因「定位对但值读错」给分（G2 违反→0）；不因「返回任意同类值」给分

#### 题目 22（1743b9363cdbd904475a）—题面：Identify the storage size used by the a11y-syntax-highlighting project.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段单实体读操作，不拆成定位+取值两个分数"}
- **适用场景：** 查询题面指定实体的单值字段，只读（目标实体：a11y-syntax-highlighting 项目）。
- **成功门控条件（gate）：** G1 目标实体 = a11y-syntax-highlighting 项目；G2 `answer_storage_size` 与本地记录参考值**精确匹配**（以本地记录为准，非推测、非相邻实体）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察字段来源单一、无相邻实体混淆。
- **边界情况：** 无法确认提交值与本地参考值是否相符 → null（明确不符则 0）；无法确认绑定实体 → null（明确为假则 0）
- **不应给分的反例：** 不把「定位实体」与「读字段值」拆两个分数；不因「定位对但值读错」给分（G2 违反→0）；不因「返回任意同类值」给分

#### 题目 23（17c277148ce43e3c80e1）—题面：Check the price of the Pre-baked Gingerbread House Kit Value Pack.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段单实体读操作，不拆成定位+取值两个分数"}
- **适用场景：** 查询题面指定实体的单值字段，只读（目标实体：产品 'Pre-baked Gingerbread House Kit Value Pack'）。
- **成功门控条件（gate）：** G1 目标实体 = 产品 'Pre-baked Gingerbread House Kit Value Pack'；G2 `answer_price` 与本地记录参考值**精确匹配**（以本地记录为准，非推测、非相邻实体）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察字段来源单一、无相邻实体混淆。
- **边界情况：** 无法确认提交值与本地参考值是否相符 → null（明确不符则 0）；无法确认绑定实体 → null（明确为假则 0）
- **不应给分的反例：** 不把「定位实体」与「读字段值」拆两个分数；不因「定位对但值读错」给分（G2 违反→0）；不因「返回任意同类值」给分

#### 题目 29（1c6b231f1fb372bb206d）—题面：Check the price of the "Mineralogie All Natural Lip Gloss, Ruby Rose" product.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段单实体读操作，不拆成定位+取值两个分数"}
- **适用场景：** 查询题面指定实体的单值字段，只读（目标实体：产品 'Mineralogie All Natural Lip Gloss, Ruby Rose'）。
- **成功门控条件（gate）：** G1 目标实体 = 产品 'Mineralogie All Natural Lip Gloss, Ruby Rose'；G2 `answer_price` 与本地记录参考值**精确匹配**（以本地记录为准，非推测、非相邻实体）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察字段来源单一、无相邻实体混淆。
- **边界情况：** 无法确认提交值与本地参考值是否相符 → null（明确不符则 0）；无法确认绑定实体 → null（明确为假则 0）
- **不应给分的反例：** 不把「定位实体」与「读字段值」拆两个分数；不因「定位对但值读错」给分（G2 违反→0）；不因「返回任意同类值」给分

#### 题目 38（2802ed12abe1bb11f5a4）—题面：Find out who manufactures the Pre-baked Gingerbread House Kit Value Pack
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段单实体读操作，不拆成定位+取值两个分数"}
- **适用场景：** 查询题面指定实体的单值字段，只读（目标实体：产品 'Pre-baked Gingerbread House Kit Value Pack'）。
- **成功门控条件（gate）：** G1 目标实体 = 产品 'Pre-baked Gingerbread House Kit Value Pack'；G2 `answer_manufacturer` 与本地记录参考值**精确匹配**（以本地记录为准，非推测、非相邻实体）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察字段来源单一、无相邻实体混淆。
- **边界情况：** 无法确认提交值与本地参考值是否相符 → null（明确不符则 0）；无法确认绑定实体 → null（明确为假则 0）
- **不应给分的反例：** 不把「定位实体」与「读字段值」拆两个分数；不因「定位对但值读错」给分（G2 违反→0）；不因「返回任意同类值」给分

#### 题目 43（2ebfec43e8215c9a172c）—题面：Find out how to contact One Stop Market customer service
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段单实体读操作，不拆成定位+取值两个分数"}
- **适用场景：** 查询题面指定实体的单值字段，只读（目标实体：One Stop Market）。
- **成功门控条件（gate）：** G1 目标实体 = One Stop Market；G2 `answer_contact_form_url` 与本地记录参考值**精确匹配**（以本地记录为准，非推测、非相邻实体）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察字段来源单一、无相邻实体混淆。
- **边界情况：** 无法确认提交值与本地参考值是否相符 → null（明确不符则 0）；无法确认绑定实体 → null（明确为假则 0）
- **不应给分的反例：** 不把「定位实体」与「读字段值」拆两个分数；不因「定位对但值读错」给分（G2 违反→0）；不因「返回任意同类值」给分
- **题面特例/备注：** contact_form_url

#### 题目 47（36450a47ea9635c40045）—题面：Retrieve the price of the Nightfox Vulpes Handheld Digital Night Vision Goggles.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段单实体读操作，不拆成定位+取值两个分数"}
- **适用场景：** 查询题面指定实体的单值字段，只读（目标实体：产品 'Nightfox Vulpes Handheld Digital Night Vision Goggles'）。
- **成功门控条件（gate）：** G1 目标实体 = 产品 'Nightfox Vulpes Handheld Digital Night Vision Goggles'；G2 `answer_price` 与本地记录参考值**精确匹配**（以本地记录为准，非推测、非相邻实体）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察字段来源单一、无相邻实体混淆。
- **边界情况：** 无法确认提交值与本地参考值是否相符 → null（明确不符则 0）；无法确认绑定实体 → null（明确为假则 0）
- **不应给分的反例：** 不把「定位实体」与「读字段值」拆两个分数；不因「定位对但值读错」给分（G2 违反→0）；不因「返回任意同类值」给分

#### 题目 49（3934afdec1f314316da4）—题面：Check the SKU number of the Pre-baked Gingerbread House Kit Value Pack
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段单实体读操作，不拆成定位+取值两个分数"}
- **适用场景：** 查询题面指定实体的单值字段，只读（目标实体：产品 'Pre-baked Gingerbread House Kit Value Pack'）。
- **成功门控条件（gate）：** G1 目标实体 = 产品 'Pre-baked Gingerbread House Kit Value Pack'；G2 `answer_sku` 与本地记录参考值**精确匹配**（以本地记录为准，非推测、非相邻实体）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察字段来源单一、无相邻实体混淆。
- **边界情况：** 无法确认提交值与本地参考值是否相符 → null（明确不符则 0）；无法确认绑定实体 → null（明确为假则 0）
- **不应给分的反例：** 不把「定位实体」与「读字段值」拆两个分数；不因「定位对但值读错」给分（G2 违反→0）；不因「返回任意同类值」给分
- **题面特例/备注：** SKU 与 #1 同字段、目标产品不同

#### 题目 62（4247576686e176dea583）—题面：Find out what materials the Nightfox Vulpes Night Vision Goggles are made of.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段单实体读操作，不拆成定位+取值两个分数"}
- **适用场景：** 查询题面指定实体的单值字段，只读（目标实体：产品 'Nightfox Vulpes Night Vision Goggles'）。
- **成功门控条件（gate）：** G1 目标实体 = 产品 'Nightfox Vulpes Night Vision Goggles'；G2 `answer_material` 与本地记录参考值**精确匹配**（以本地记录为准，非推测、非相邻实体）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察字段来源单一、无相邻实体混淆。
- **边界情况：** 无法确认提交值与本地参考值是否相符 → null（明确不符则 0）；无法确认绑定实体 → null（明确为假则 0）
- **不应给分的反例：** 不把「定位实体」与「读字段值」拆两个分数；不因「定位对但值读错」给分（G2 违反→0）；不因「返回任意同类值」给分
- **题面特例/备注：** material

#### 题目 65（45ffd6778b9d863ba9ca）—题面：Check the price of the Custom Jersey Style St Patricks Day T-Shirt
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段单实体读操作，不拆成定位+取值两个分数"}
- **适用场景：** 查询题面指定实体的单值字段，只读（目标实体：产品 'Custom Jersey Style St Patricks Day T-Shirt'）。
- **成功门控条件（gate）：** G1 目标实体 = 产品 'Custom Jersey Style St Patricks Day T-Shirt'；G2 `answer_price` 与本地记录参考值**精确匹配**（以本地记录为准，非推测、非相邻实体）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察字段来源单一、无相邻实体混淆。
- **边界情况：** 无法确认提交值与本地参考值是否相符 → null（明确不符则 0）；无法确认绑定实体 → null（明确为假则 0）
- **不应给分的反例：** 不把「定位实体」与「读字段值」拆两个分数；不因「定位对但值读错」给分（G2 违反→0）；不因「返回任意同类值」给分

#### 题目 73（4fcb5d49a6794c46e8e8）—题面：Check what magnification the Nightfox Vulpes Night Vision Goggles offer.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段单实体读操作，不拆成定位+取值两个分数"}
- **适用场景：** 查询题面指定实体的单值字段，只读（目标实体：产品 'Nightfox Vulpes Night Vision Goggles'）。
- **成功门控条件（gate）：** G1 目标实体 = 产品 'Nightfox Vulpes Night Vision Goggles'；G2 `answer_magnification` 与本地记录参考值**精确匹配**（以本地记录为准，非推测、非相邻实体）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察字段来源单一、无相邻实体混淆。
- **边界情况：** 无法确认提交值与本地参考值是否相符 → null（明确不符则 0）；无法确认绑定实体 → null（明确为假则 0）
- **不应给分的反例：** 不把「定位实体」与「读字段值」拆两个分数；不因「定位对但值读错」给分（G2 违反→0）；不因「返回任意同类值」给分
- **题面特例/备注：** magnification

#### 题目 77（55d3114f967d54b51fda）—题面：Find the username of the person who submitted the post about Nosferatu at 100 years
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段单实体读操作，不拆成定位+取值两个分数"}
- **适用场景：** 查询题面指定实体的单值字段，只读（目标实体：帖子（关于 Nosferatu at 100 years））。
- **成功门控条件（gate）：** G1 目标实体 = 帖子（关于 Nosferatu at 100 years）；G2 `answer_author` 与本地记录参考值**精确匹配**（以本地记录为准，非推测、非相邻实体）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察字段来源单一、无相邻实体混淆。
- **边界情况：** 无法确认提交值与本地参考值是否相符 → null（明确不符则 0）；无法确认绑定实体 → null（明确为假则 0）
- **不应给分的反例：** 不把「定位实体」与「读字段值」拆两个分数；不因「定位对但值读错」给分（G2 违反→0）；不因「返回任意同类值」给分
- **题面特例/备注：** author = 提交用户名

#### 题目 88（609abffc99ef4112c780）—题面：Check what routing engine is being used for the current directions.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段单实体读操作，不拆成定位+取值两个分数"}
- **适用场景：** 查询题面指定实体的单值字段，只读（目标实体：当前 directions 路线）。
- **成功门控条件（gate）：** G1 目标实体 = 当前 directions 路线；G2 `answer_engine` 与本地记录参考值**精确匹配**（以本地记录为准，非推测、非相邻实体）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察字段来源单一、无相邻实体混淆。
- **边界情况：** 无法确认提交值与本地参考值是否相符 → null（明确不符则 0）；无法确认绑定实体 → null（明确为假则 0）
- **不应给分的反例：** 不把「定位实体」与「读字段值」拆两个分数；不因「定位对但值读错」给分（G2 违反→0）；不因「返回任意同类值」给分
- **题面特例/备注：** routing engine

#### 题目 89（61d16fff9c982ddf674f）—题面：Find the driving distance from New York City to Boston
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段单实体读操作，不拆成定位+取值两个分数"}
- **适用场景：** 查询题面指定实体的单值字段，只读（目标实体：纽约 → 波士顿）。
- **成功门控条件（gate）：** G1 目标实体 = 纽约 → 波士顿；G2 `answer_distance_km` 与本地记录参考值**精确匹配**（以本地记录为准，非推测、非相邻实体）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察字段来源单一、无相邻实体混淆。
- **边界情况：** 无法确认提交值与本地参考值是否相符 → null（明确不符则 0）；无法确认绑定实体 → null（明确为假则 0）
- **不应给分的反例：** 不把「定位实体」与「读字段值」拆两个分数；不因「定位对但值读错」给分（G2 违反→0）；不因「返回任意同类值」给分
- **题面特例/备注：** driving distance_km

#### 题目 100（748b3ecbeda6a6a10aa1）—题面：View the total cost of items in the shopping cart
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段单实体读操作，不拆成定位+取值两个分数"}
- **适用场景：** 查询题面指定实体的单值字段，只读（目标实体：当前购物车）。
- **成功门控条件（gate）：** G1 目标实体 = 当前购物车；G2 `answer_items_subtotal` 与本地记录参考值**精确匹配**（以本地记录为准，非推测、非相邻实体）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察字段来源单一、无相邻实体混淆。
- **边界情况：** 无法确认提交值与本地参考值是否相符 → null（明确不符则 0）；无法确认绑定实体 → null（明确为假则 0）
- **不应给分的反例：** 不把「定位实体」与「读字段值」拆两个分数；不因「定位对但值读错」给分（G2 违反→0）；不因「返回任意同类值」给分
- **题面特例/备注：** items_subtotal

#### 题目 106（7b224eb22f9dddeb6cf6）—题面：Calculate the driving distance between Utica and Albany, NY
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段单实体读操作，不拆成定位+取值两个分数"}
- **适用场景：** 查询题面指定实体的单值字段，只读（目标实体：Utica → Albany, NY）。
- **成功门控条件（gate）：** G1 目标实体 = Utica → Albany, NY；G2 `answer_distance_km` 与本地记录参考值**精确匹配**（以本地记录为准，非推测、非相邻实体）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察字段来源单一、无相邻实体混淆。
- **边界情况：** 无法确认提交值与本地参考值是否相符 → null（明确不符则 0）；无法确认绑定实体 → null（明确为假则 0）
- **不应给分的反例：** 不把「定位实体」与「读字段值」拆两个分数；不因「定位对但值读错」给分（G2 违反→0）；不因「返回任意同类值」给分
- **题面特例/备注：** driving distance_km

#### 题目 107（7cdb7893ed10cf4ba75a）—题面：Find the price of the 5x40 Night Vision Monocular Telescopes.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段单实体读操作，不拆成定位+取值两个分数"}
- **适用场景：** 查询题面指定实体的单值字段，只读（目标实体：产品 '5x40 Night Vision Monocular Telescopes'）。
- **成功门控条件（gate）：** G1 目标实体 = 产品 '5x40 Night Vision Monocular Telescopes'；G2 `answer_price` 与本地记录参考值**精确匹配**（以本地记录为准，非推测、非相邻实体）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察字段来源单一、无相邻实体混淆。
- **边界情况：** 无法确认提交值与本地参考值是否相符 → null（明确不符则 0）；无法确认绑定实体 → null（明确为假则 0）
- **不应给分的反例：** 不把「定位实体」与「读字段值」拆两个分数；不因「定位对但值读错」给分（G2 违反→0）；不因「返回任意同类值」给分

#### 题目 111（8740532e91dbc3037815）—题面：Check the price of the "Posiflex MT4008 Point of Sale Tablet" product.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段单实体读操作，不拆成定位+取值两个分数"}
- **适用场景：** 查询题面指定实体的单值字段，只读（目标实体：产品 'Posiflex MT4008 Point of Sale Tablet'）。
- **成功门控条件（gate）：** G1 目标实体 = 产品 'Posiflex MT4008 Point of Sale Tablet'；G2 `answer_price` 与本地记录参考值**精确匹配**（以本地记录为准，非推测、非相邻实体）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察字段来源单一、无相邻实体混淆。
- **边界情况：** 无法确认提交值与本地参考值是否相符 → null（明确不符则 0）；无法确认绑定实体 → null（明确为假则 0）
- **不应给分的反例：** 不把「定位实体」与「读字段值」拆两个分数；不因「定位对但值读错」给分（G2 违反→0）；不因「返回任意同类值」给分

#### 题目 114（8a66ed1a43e9687e2412）—题面：What is the price of the Pre-baked Gingerbread House Kit Value Pack?
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段单实体读操作，不拆成定位+取值两个分数"}
- **适用场景：** 查询题面指定实体的单值字段，只读（目标实体：产品 'Pre-baked Gingerbread House Kit Value Pack'）。
- **成功门控条件（gate）：** G1 目标实体 = 产品 'Pre-baked Gingerbread House Kit Value Pack'；G2 `answer_price` 与本地记录参考值**精确匹配**（以本地记录为准，非推测、非相邻实体）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察字段来源单一、无相邻实体混淆。
- **边界情况：** 无法确认提交值与本地参考值是否相符 → null（明确不符则 0）；无法确认绑定实体 → null（明确为假则 0）
- **不应给分的反例：** 不把「定位实体」与「读字段值」拆两个分数；不因「定位对但值读错」给分（G2 违反→0）；不因「返回任意同类值」给分

#### 题目 116（8c857e0111275f007585）—题面：Check the shipping cost for your current cart items.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段单实体读操作，不拆成定位+取值两个分数"}
- **适用场景：** 查询题面指定实体的单值字段，只读（目标实体：当前购物车 items）。
- **成功门控条件（gate）：** G1 目标实体 = 当前购物车 items；G2 `answer_shipping_cost` 与本地记录参考值**精确匹配**（以本地记录为准，非推测、非相邻实体）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察字段来源单一、无相邻实体混淆。
- **边界情况：** 无法确认提交值与本地参考值是否相符 → null（明确不符则 0）；无法确认绑定实体 → null（明确为假则 0）
- **不应给分的反例：** 不把「定位实体」与「读字段值」拆两个分数；不因「定位对但值读错」给分（G2 违反→0）；不因「返回任意同类值」给分
- **题面特例/备注：** shipping_cost

#### 题目 118（993478a7233e453bdbce）—题面：Check the estimated travel time for a car route from Times Square to JFK Airport
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段单实体读操作，不拆成定位+取值两个分数"}
- **适用场景：** 查询题面指定实体的单值字段，只读（目标实体：Times Square → JFK Airport）。
- **成功门控条件（gate）：** G1 目标实体 = Times Square → JFK Airport；G2 `answer_duration_minutes` 与本地记录参考值**精确匹配**（以本地记录为准，非推测、非相邻实体）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察字段来源单一、无相邻实体混淆。
- **边界情况：** 无法确认提交值与本地参考值是否相符 → null（明确不符则 0）；无法确认绑定实体 → null（明确为假则 0）
- **不应给分的反例：** 不把「定位实体」与「读字段值」拆两个分数；不因「定位对但值读错」给分（G2 违反→0）；不因「返回任意同类值」给分
- **题面特例/备注：** car route duration_minutes

#### 题目 119（9a9b75750d305ace38fa）—题面：Who submitted the article titled “Holy shit is “Tom’s Diner” by Suzanne Vega & DNA so godamn good.”
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段单实体读操作，不拆成定位+取值两个分数"}
- **适用场景：** 查询题面指定实体的单值字段，只读（目标实体：文章（'Holy shit is "Tom's Diner" by Suzanne Vega & DNA so godamn good.'））。
- **成功门控条件（gate）：** G1 目标实体 = 文章（'Holy shit is "Tom's Diner" by Suzanne Vega & DNA so godamn good.'）；G2 `answer_author` 与本地记录参考值**精确匹配**（以本地记录为准，非推测、非相邻实体）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察字段来源单一、无相邻实体混淆。
- **边界情况：** 无法确认提交值与本地参考值是否相符 → null（明确不符则 0）；无法确认绑定实体 → null（明确为假则 0）
- **不应给分的反例：** 不把「定位实体」与「读字段值」拆两个分数；不因「定位对但值读错」给分（G2 违反→0）；不因「返回任意同类值」给分

#### 题目 121（9e08e0b6f78a10e5cb42）—题面：Calculate the walking distance between Central Park and Times Square
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段单实体读操作，不拆成定位+取值两个分数"}
- **适用场景：** 查询题面指定实体的单值字段，只读（目标实体：Central Park → Times Square）。
- **成功门控条件（gate）：** G1 目标实体 = Central Park → Times Square；G2 `answer_distance_km` 与本地记录参考值**精确匹配**（以本地记录为准，非推测、非相邻实体）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察字段来源单一、无相邻实体混淆。
- **边界情况：** 无法确认提交值与本地参考值是否相符 → null（明确不符则 0）；无法确认绑定实体 → null（明确为假则 0）
- **不应给分的反例：** 不把「定位实体」与「读字段值」拆两个分数；不因「定位对但值读错」给分（G2 违反→0）；不因「返回任意同类值」给分
- **题面特例/备注：** walking distance_km

#### 题目 123（9f561911da861969ad99）—题面：Find who assigned the pending to-do for the merge request "update or remove 404 links" in The A11Y Project / a11yproject.com.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段单实体读操作，不拆成定位+取值两个分数"}
- **适用场景：** 查询题面指定实体的单值字段，只读（目标实体：merge request 'update or remove 404 links'（The A11Y Project / a11yproject.com））。
- **成功门控条件（gate）：** G1 目标实体 = merge request 'update or remove 404 links'（The A11Y Project / a11yproject.com）；G2 `answer_assigned_by` 与本地记录参考值**精确匹配**（以本地记录为准，非推测、非相邻实体）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察字段来源单一、无相邻实体混淆。
- **边界情况：** 无法确认提交值与本地参考值是否相符 → null（明确不符则 0）；无法确认绑定实体 → null（明确为假则 0）
- **不应给分的反例：** 不把「定位实体」与「读字段值」拆两个分数；不因「定位对但值读错」给分（G2 违反→0）；不因「返回任意同类值」给分
- **题面特例/备注：** assigned_by = 指派者

#### 题目 124（9fccdb70fc3f5cda6c49）—题面：Check the payable total for my current shopping cart, including shipping to my default saved address. Do not place the order.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段单实体读操作，不拆成定位+取值两个分数"}
- **适用场景：** 查询题面指定实体的单值字段，只读（目标实体：当前购物车（含默认地址运费））。
- **成功门控条件（gate）：** G1 目标实体 = 当前购物车（含默认地址运费）；G2 `answer_order_total` 与本地记录参考值**精确匹配**（以本地记录为准，非推测、非相邻实体）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察字段来源单一、无相邻实体混淆。
- **边界情况：** 无法确认提交值与本地参考值是否相符 → null（明确不符则 0）；无法确认绑定实体 → null（明确为假则 0）
- **不应给分的反例：** 不把「定位实体」与「读字段值」拆两个分数；不因「定位对但值读错」给分（G2 违反→0）；不因「返回任意同类值」给分
- **题面特例/备注：** order_total；题面明示 'Do not place the order'

#### 题目 126（a07262b05d647d15927e）—题面：Check the customer rating for the ACPOTEL Night Vision Monocular.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段单实体读操作，不拆成定位+取值两个分数"}
- **适用场景：** 查询题面指定实体的单值字段，只读（目标实体：产品 'ACPOTEL Night Vision Monocular'）。
- **成功门控条件（gate）：** G1 目标实体 = 产品 'ACPOTEL Night Vision Monocular'；G2 `answer_rating_percent` 与本地记录参考值**精确匹配**（以本地记录为准，非推测、非相邻实体）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察字段来源单一、无相邻实体混淆。
- **边界情况：** 无法确认提交值与本地参考值是否相符 → null（明确不符则 0）；无法确认绑定实体 → null（明确为假则 0）
- **不应给分的反例：** 不把「定位实体」与「读字段值」拆两个分数；不因「定位对但值读错」给分（G2 违反→0）；不因「返回任意同类值」给分
- **题面特例/备注：** rating_percent

#### 题目 127（a30dc8c6d713f134765f）—题面：View the rating percentage of the Nightfox Vulpes Handheld Digital Night Vision Goggles
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段单实体读操作，不拆成定位+取值两个分数"}
- **适用场景：** 查询题面指定实体的单值字段，只读（目标实体：产品 'Nightfox Vulpes Handheld Digital Night Vision Goggles'）。
- **成功门控条件（gate）：** G1 目标实体 = 产品 'Nightfox Vulpes Handheld Digital Night Vision Goggles'；G2 `answer_rating_percent` 与本地记录参考值**精确匹配**（以本地记录为准，非推测、非相邻实体）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察字段来源单一、无相邻实体混淆。
- **边界情况：** 无法确认提交值与本地参考值是否相符 → null（明确不符则 0）；无法确认绑定实体 → null（明确为假则 0）
- **不应给分的反例：** 不把「定位实体」与「读字段值」拆两个分数；不因「定位对但值读错」给分（G2 违反→0）；不因「返回任意同类值」给分
- **题面特例/备注：** rating percentage

#### 题目 133（ad26452f2969e7565c70）—题面：Find the estimated travel time for driving from Syracuse to Buffalo
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段单实体读操作，不拆成定位+取值两个分数"}
- **适用场景：** 查询题面指定实体的单值字段，只读（目标实体：Syracuse → Buffalo）。
- **成功门控条件（gate）：** G1 目标实体 = Syracuse → Buffalo；G2 `answer_duration_minutes` 与本地记录参考值**精确匹配**（以本地记录为准，非推测、非相邻实体）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察字段来源单一、无相邻实体混淆。
- **边界情况：** 无法确认提交值与本地参考值是否相符 → null（明确不符则 0）；无法确认绑定实体 → null（明确为假则 0）
- **不应给分的反例：** 不把「定位实体」与「读字段值」拆两个分数；不因「定位对但值读错」给分（G2 违反→0）；不因「返回任意同类值」给分
- **题面特例/备注：** driving duration_minutes

#### 题目 134（ad3e4fb48ca4a16b8f1c）—题面：List the price of Lobster Cobbler Pot Pie - Gourmet Frozen Seafood Appetizers.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段单实体读操作，不拆成定位+取值两个分数"}
- **适用场景：** 查询题面指定实体的单值字段，只读（目标实体：产品 'Lobster Cobbler Pot Pie - Gourmet Frozen Seafood Appetizers'）。
- **成功门控条件（gate）：** G1 目标实体 = 产品 'Lobster Cobbler Pot Pie - Gourmet Frozen Seafood Appetizers'；G2 `answer_price` 与本地记录参考值**精确匹配**（以本地记录为准，非推测、非相邻实体）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察字段来源单一、无相邻实体混淆。
- **边界情况：** 无法确认提交值与本地参考值是否相符 → null（明确不符则 0）；无法确认绑定实体 → null（明确为假则 0）
- **不应给分的反例：** 不把「定位实体」与「读字段值」拆两个分数；不因「定位对但值读错」给分（G2 违反→0）；不因「返回任意同类值」给分

#### 题目 135（ad6b4323f8b6b17e62fd）—题面：Find the manufacturer of the Pre-baked Gingerbread House Kit.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段单实体读操作，不拆成定位+取值两个分数"}
- **适用场景：** 查询题面指定实体的单值字段，只读（目标实体：产品 'Pre-baked Gingerbread House Kit'）。
- **成功门控条件（gate）：** G1 目标实体 = 产品 'Pre-baked Gingerbread House Kit'；G2 `answer_manufacturer` 与本地记录参考值**精确匹配**（以本地记录为准，非推测、非相邻实体）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察字段来源单一、无相邻实体混淆。
- **边界情况：** 无法确认提交值与本地参考值是否相符 → null（明确不符则 0）；无法确认绑定实体 → null（明确为假则 0）
- **不应给分的反例：** 不把「定位实体」与「读字段值」拆两个分数；不因「定位对但值读错」给分（G2 违反→0）；不因「返回任意同类值」给分

#### 题目 139（b7dbf7b6ca54b76fbb97）—题面：Check the overall rating of the St Patricks Day T-Shirt
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段单实体读操作，不拆成定位+取值两个分数"}
- **适用场景：** 查询题面指定实体的单值字段，只读（目标实体：产品 'St Patricks Day T-Shirt'）。
- **成功门控条件（gate）：** G1 目标实体 = 产品 'St Patricks Day T-Shirt'；G2 `answer_rating_percent` 与本地记录参考值**精确匹配**（以本地记录为准，非推测、非相邻实体）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察字段来源单一、无相邻实体混淆。
- **边界情况：** 无法确认提交值与本地参考值是否相符 → null（明确不符则 0）；无法确认绑定实体 → null（明确为假则 0）
- **不应给分的反例：** 不把「定位实体」与「读字段值」拆两个分数；不因「定位对但值读错」给分（G2 违反→0）；不因「返回任意同类值」给分
- **题面特例/备注：** rating_percent

#### 题目 140（b864f0a929e2ed01b5f3）—题面：Check the license type of the PureLayout project
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段单实体读操作，不拆成定位+取值两个分数"}
- **适用场景：** 查询题面指定实体的单值字段，只读（目标实体：PureLayout 项目）。
- **成功门控条件（gate）：** G1 目标实体 = PureLayout 项目；G2 `answer_license_type` 与本地记录参考值**精确匹配**（以本地记录为准，非推测、非相邻实体）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察字段来源单一、无相邻实体混淆。
- **边界情况：** 无法确认提交值与本地参考值是否相符 → null（明确不符则 0）；无法确认绑定实体 → null（明确为假则 0）
- **不应给分的反例：** 不把「定位实体」与「读字段值」拆两个分数；不因「定位对但值读错」给分（G2 违反→0）；不因「返回任意同类值」给分
- **题面特例/备注：** license_type

#### 题目 144（bec24923c0a7ed46e025）—题面：Check the total travel time for driving from New York City to Boston
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段单实体读操作，不拆成定位+取值两个分数"}
- **适用场景：** 查询题面指定实体的单值字段，只读（目标实体：纽约 → 波士顿）。
- **成功门控条件（gate）：** G1 目标实体 = 纽约 → 波士顿；G2 `answer_duration_minutes` 与本地记录参考值**精确匹配**（以本地记录为准，非推测、非相邻实体）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察字段来源单一、无相邻实体混淆。
- **边界情况：** 无法确认提交值与本地参考值是否相符 → null（明确不符则 0）；无法确认绑定实体 → null（明确为假则 0）
- **不应给分的反例：** 不把「定位实体」与「读字段值」拆两个分数；不因「定位对但值读错」给分（G2 违反→0）；不因「返回任意同类值」给分
- **题面特例/备注：** driving duration_minutes（总时长）

#### 题目 160（ced122c4f49dfa2d22b3）—题面：Check the total price of items in my shopping cart
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段单实体读操作，不拆成定位+取值两个分数"}
- **适用场景：** 查询题面指定实体的单值字段，只读（目标实体：当前购物车）。
- **成功门控条件（gate）：** G1 目标实体 = 当前购物车；G2 `answer_items_subtotal` 与本地记录参考值**精确匹配**（以本地记录为准，非推测、非相邻实体）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察字段来源单一、无相邻实体混淆。
- **边界情况：** 无法确认提交值与本地参考值是否相符 → null（明确不符则 0）；无法确认绑定实体 → null（明确为假则 0）
- **不应给分的反例：** 不把「定位实体」与「读字段值」拆两个分数；不因「定位对但值读错」给分（G2 违反→0）；不因「返回任意同类值」给分
- **题面特例/备注：** items_subtotal

#### 题目 161（cef94e2c64f4f23f905e）—题面：Check which programming language is used in the gumble project
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段单实体读操作，不拆成定位+取值两个分数"}
- **适用场景：** 查询题面指定实体的单值字段，只读（目标实体：gumble 项目）。
- **成功门控条件（gate）：** G1 目标实体 = gumble 项目；G2 `answer_declared_language` 与本地记录参考值**精确匹配**（以本地记录为准，非推测、非相邻实体）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察字段来源单一、无相邻实体混淆。
- **边界情况：** 无法确认提交值与本地参考值是否相符 → null（明确不符则 0）；无法确认绑定实体 → null（明确为假则 0）
- **不应给分的反例：** 不把「定位实体」与「读字段值」拆两个分数；不因「定位对但值读错」给分（G2 违反→0）；不因「返回任意同类值」给分
- **题面特例/备注：** declared_language

#### 题目 169（d5bd865c545a1cd9a3a6）—题面：Find the total distance of the driving route from New York City to Boston
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段单实体读操作，不拆成定位+取值两个分数"}
- **适用场景：** 查询题面指定实体的单值字段，只读（目标实体：纽约 → 波士顿）。
- **成功门控条件（gate）：** G1 目标实体 = 纽约 → 波士顿；G2 `answer_distance_km` 与本地记录参考值**精确匹配**（以本地记录为准，非推测、非相邻实体）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察字段来源单一、无相邻实体混淆。
- **边界情况：** 无法确认提交值与本地参考值是否相符 → null（明确不符则 0）；无法确认绑定实体 → null（明确为假则 0）
- **不应给分的反例：** 不把「定位实体」与「读字段值」拆两个分数；不因「定位对但值读错」给分（G2 违反→0）；不因「返回任意同类值」给分
- **题面特例/备注：** driving route 总距离 distance_km

#### 题目 170（d6a29e7a354b46ccc7d5）—题面：Check the manufacturer of the Pre-baked Gingerbread House Kit
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段单实体读操作，不拆成定位+取值两个分数"}
- **适用场景：** 查询题面指定实体的单值字段，只读（目标实体：产品 'Pre-baked Gingerbread House Kit'）。
- **成功门控条件（gate）：** G1 目标实体 = 产品 'Pre-baked Gingerbread House Kit'；G2 `answer_manufacturer` 与本地记录参考值**精确匹配**（以本地记录为准，非推测、非相邻实体）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察字段来源单一、无相邻实体混淆。
- **边界情况：** 无法确认提交值与本地参考值是否相符 → null（明确不符则 0）；无法确认绑定实体 → null（明确为假则 0）
- **不应给分的反例：** 不把「定位实体」与「读字段值」拆两个分数；不因「定位对但值读错」给分（G2 违反→0）；不因「返回任意同类值」给分

#### 题目 174（da2963632dabe85ed989）—题面：Report the displayed net score (upvotes minus downvotes) for the post “Michael Jackson’s ‘Thriller’ Returns To Billboard Top 10 After 38 Years”.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段单实体读操作，不拆成定位+取值两个分数"}
- **适用场景：** 查询题面指定实体的单值字段，只读（目标实体：帖子（'Michael Jackson's 'Thriller' Returns To Billboard Top 10 After 38 Years'））。
- **成功门控条件（gate）：** G1 目标实体 = 帖子（'Michael Jackson's 'Thriller' Returns To Billboard Top 10 After 38 Years'）；G2 `answer_net_score` 与本地记录参考值**精确匹配**（以本地记录为准，非推测、非相邻实体）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察字段来源单一、无相邻实体混淆。
- **边界情况：** 无法确认提交值与本地参考值是否相符 → null（明确不符则 0）；无法确认绑定实体 → null（明确为假则 0）
- **不应给分的反例：** 不把「定位实体」与「读字段值」拆两个分数；不因「定位对但值读错」给分（G2 违反→0）；不因「返回任意同类值」给分
- **题面特例/备注：** net_score = upvotes - downvotes

#### 题目 191（ed6c769c8c1b8f530584）—题面：Find the price of the Bushnell 743333 Boresighter.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段单实体读操作，不拆成定位+取值两个分数"}
- **适用场景：** 查询题面指定实体的单值字段，只读（目标实体：产品 'Bushnell 743333 Boresighter'）。
- **成功门控条件（gate）：** G1 目标实体 = 产品 'Bushnell 743333 Boresighter'；G2 `answer_price` 与本地记录参考值**精确匹配**（以本地记录为准，非推测、非相邻实体）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察字段来源单一、无相邻实体混淆。
- **边界情况：** 无法确认提交值与本地参考值是否相符 → null（明确不符则 0）；无法确认绑定实体 → null（明确为假则 0）
- **不应给分的反例：** 不把「定位实体」与「读字段值」拆两个分数；不因「定位对但值读错」给分（G2 违反→0）；不因「返回任意同类值」给分

#### 题目 197（fbe617235425d7ebe689）—题面：Find the price of the "Maryia Men 3D Creative Printed Graphic T Shirts Casual Short Sleeve Crewneck Muscle Tees Personality Realistic Suit".
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段单实体读操作，不拆成定位+取值两个分数"}
- **适用场景：** 查询题面指定实体的单值字段，只读（目标实体：产品 'Maryia Men 3D Creative Printed Graphic T Shirts…'）。
- **成功门控条件（gate）：** G1 目标实体 = 产品 'Maryia Men 3D Creative Printed Graphic T Shirts…'；G2 `answer_price` 与本地记录参考值**精确匹配**（以本地记录为准，非推测、非相邻实体）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察字段来源单一、无相邻实体混淆。
- **边界情况：** 无法确认提交值与本地参考值是否相符 → null（明确不符则 0）；无法确认绑定实体 → null（明确为假则 0）
- **不应给分的反例：** 不把「定位实体」与「读字段值」拆两个分数；不因「定位对但值读错」给分（G2 违反→0）；不因「返回任意同类值」给分

### 3.2 实体属性计数（33 题）

#### 题目 3（030ab9a939137f3487c0）—题面：Find out how many projects you have starred
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "计数是单次查询的单一输出，不拆成定位+计数两个分数"}
- **适用场景：** 查询题面指定实体的计数属性（单值），只读（目标实体：当前登录用户的 starred projects 集合）。
- **成功门控条件（gate）：** G1 目标实体 = 当前登录用户的 starred projects 集合；G2 `answer_starred_project_count` 与本地记录该计数**精确匹配**（读自目标实体页面的总数，非只数部分）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「目标定位规范」观察是否读取正确总数而非只数当前页。
- **边界情况：** 无法确认计数是否穷尽/正确 → null
- **不应给分的反例：** 不把「定位实体」与「读计数」拆两个分数；不把「只数部分/当前页」判通过（G2 违反→0）

#### 题目 6（05a4924068ed5d2957e5）—题面：See how many forks the MathJax project has
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "计数是单次查询的单一输出，不拆成定位+计数两个分数"}
- **适用场景：** 查询题面指定实体的计数属性（单值），只读（目标实体：MathJax 项目）。
- **成功门控条件（gate）：** G1 目标实体 = MathJax 项目；G2 `answer_fork_count` 与本地记录该计数**精确匹配**（读自目标实体页面的总数，非只数部分）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「目标定位规范」观察是否读取正确总数而非只数当前页。
- **边界情况：** 无法确认计数是否穷尽/正确 → null
- **不应给分的反例：** 不把「定位实体」与「读计数」拆两个分数；不把「只数部分/当前页」判通过（G2 违反→0）

#### 题目 10（0a8f3325b194a807f848）—题面：Get the number of comments on the article "Cindy Williams Dies: ‘Laverne &amp; Shirley‘ Star Who Appeared In ’American Graffiti’ &amp; ‘The Conversation’ Was 75"
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "计数是单次查询的单一输出，不拆成定位+计数两个分数"}
- **适用场景：** 查询题面指定实体的计数属性（单值），只读（目标实体：文章 'Cindy Williams Dies: … Was 75'）。
- **成功门控条件（gate）：** G1 目标实体 = 文章 'Cindy Williams Dies: … Was 75'；G2 `answer_comment_count` 与本地记录该计数**精确匹配**（读自目标实体页面的总数，非只数部分）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「目标定位规范」观察是否读取正确总数而非只数当前页。
- **边界情况：** 无法确认计数是否穷尽/正确 → null
- **不应给分的反例：** 不把「定位实体」与「读计数」拆两个分数；不把「只数部分/当前页」判通过（G2 违反→0）

#### 题目 14（0d32373dbf056a7cb733）—题面：Retrieve the number of submissions for the television forum.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "计数是单次查询的单一输出，不拆成定位+计数两个分数"}
- **适用场景：** 查询题面指定实体的计数属性（单值），只读（目标实体：television forum）。
- **成功门控条件（gate）：** G1 目标实体 = television forum；G2 `answer_submission_count` 与本地记录该计数**精确匹配**（读自目标实体页面的总数，非只数部分）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「目标定位规范」观察是否读取正确总数而非只数当前页。
- **边界情况：** 无法确认计数是否穷尽/正确 → null
- **不应给分的反例：** 不把「定位实体」与「读计数」拆两个分数；不把「只数部分/当前页」判通过（G2 违反→0）

#### 题目 27（1beff0bc05a517207f6a）—题面：View the total number of submissions in the relationship_advice forum
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "计数是单次查询的单一输出，不拆成定位+计数两个分数"}
- **适用场景：** 查询题面指定实体的计数属性（单值），只读（目标实体：relationship_advice forum）。
- **成功门控条件（gate）：** G1 目标实体 = relationship_advice forum；G2 `answer_submission_count` 与本地记录该计数**精确匹配**（读自目标实体页面的总数，非只数部分）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「目标定位规范」观察是否读取正确总数而非只数当前页。
- **边界情况：** 无法确认计数是否穷尽/正确 → null
- **不应给分的反例：** 不把「定位实体」与「读计数」拆两个分数；不把「只数部分/当前页」判通过（G2 违反→0）

#### 题目 35（24bbc21e497fc7e6386f）—题面：Retrieve the number of submissions for the memes forum.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "计数是单次查询的单一输出，不拆成定位+计数两个分数"}
- **适用场景：** 查询题面指定实体的计数属性（单值），只读（目标实体：memes forum）。
- **成功门控条件（gate）：** G1 目标实体 = memes forum；G2 `answer_submission_count` 与本地记录该计数**精确匹配**（读自目标实体页面的总数，非只数部分）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「目标定位规范」观察是否读取正确总数而非只数当前页。
- **边界情况：** 无法确认计数是否穷尽/正确 → null
- **不应给分的反例：** 不把「定位实体」与「读计数」拆两个分数；不把「只数部分/当前页」判通过（G2 违反→0）

#### 题目 42（2e1b70fe70aa84c9809d）—题面：Check how many issues are open for the a11yproject.com project.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "计数是单次查询的单一输出，不拆成定位+计数两个分数"}
- **适用场景：** 查询题面指定实体的计数属性（单值），只读（目标实体：a11yproject.com 项目）。
- **成功门控条件（gate）：** G1 目标实体 = a11yproject.com 项目；G2 `answer_open_issue_count` 与本地记录该计数**精确匹配**（读自目标实体页面的总数，非只数部分）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「目标定位规范」观察是否读取正确总数而非只数当前页。
- **边界情况：** 无法确认计数是否穷尽/正确 → null
- **不应给分的反例：** 不把「定位实体」与「读计数」拆两个分数；不把「只数部分/当前页」判通过（G2 违反→0）

#### 题目 46（331ea9c6f7b545d516de）—题面：Check how many issues are open on the project thoughtbot, inc. / administrate.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "计数是单次查询的单一输出，不拆成定位+计数两个分数"}
- **适用场景：** 查询题面指定实体的计数属性（单值），只读（目标实体：thoughtbot, inc. / administrate 项目）。
- **成功门控条件（gate）：** G1 目标实体 = thoughtbot, inc. / administrate 项目；G2 `answer_open_issue_count` 与本地记录该计数**精确匹配**（读自目标实体页面的总数，非只数部分）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「目标定位规范」观察是否读取正确总数而非只数当前页。
- **边界情况：** 无法确认计数是否穷尽/正确 → null
- **不应给分的反例：** 不把「定位实体」与「读计数」拆两个分数；不把「只数部分/当前页」判通过（G2 违反→0）

#### 题目 63（426281fcea06f8c62a26）—题面：Count pending to-dos related to the Byte Blaze / a11y-webring.club project.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "计数是单次查询的单一输出，不拆成定位+计数两个分数"}
- **适用场景：** 查询题面指定实体的计数属性（单值），只读（目标实体：Byte Blaze / a11y-webring.club 项目）。
- **成功门控条件（gate）：** G1 目标实体 = Byte Blaze / a11y-webring.club 项目；G2 `answer_todo_count` 与本地记录该计数**精确匹配**（读自目标实体页面的总数，非只数部分）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「目标定位规范」观察是否读取正确总数而非只数当前页。
- **边界情况：** 无法确认计数是否穷尽/正确 → null
- **不应给分的反例：** 不把「定位实体」与「读计数」拆两个分数；不把「只数部分/当前页」判通过（G2 违反→0）
- **题面特例/备注：** pending to-dos

#### 题目 70（4c258f420fd1dbddf2e2）—题面：Count the number of stars for the Mozilla Festival project.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "计数是单次查询的单一输出，不拆成定位+计数两个分数"}
- **适用场景：** 查询题面指定实体的计数属性（单值），只读（目标实体：Mozilla Festival 项目）。
- **成功门控条件（gate）：** G1 目标实体 = Mozilla Festival 项目；G2 `answer_star_count` 与本地记录该计数**精确匹配**（读自目标实体页面的总数，非只数部分）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「目标定位规范」观察是否读取正确总数而非只数当前页。
- **边界情况：** 无法确认计数是否穷尽/正确 → null
- **不应给分的反例：** 不把「定位实体」与「读计数」拆两个分数；不把「只数部分/当前页」判通过（G2 违反→0）

#### 题目 74（5251c3c73aebfe0cd9c6）—题面：List the number of stars for the project The A11Y Project / a11yproject.com.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "计数是单次查询的单一输出，不拆成定位+计数两个分数"}
- **适用场景：** 查询题面指定实体的计数属性（单值），只读（目标实体：The A11Y Project / a11yproject.com 项目）。
- **成功门控条件（gate）：** G1 目标实体 = The A11Y Project / a11yproject.com 项目；G2 `answer_star_count` 与本地记录该计数**精确匹配**（读自目标实体页面的总数，非只数部分）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「目标定位规范」观察是否读取正确总数而非只数当前页。
- **边界情况：** 无法确认计数是否穷尽/正确 → null
- **不应给分的反例：** 不把「定位实体」与「读计数」拆两个分数；不把「只数部分/当前页」判通过（G2 违反→0）

#### 题目 79（56b82251a17e22440ef4）—题面：How many comments are there on the article about Brian May receiving a knighthood?
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "计数是单次查询的单一输出，不拆成定位+计数两个分数"}
- **适用场景：** 查询题面指定实体的计数属性（单值），只读（目标实体：文章（关于 Brian May receiving a knighthood））。
- **成功门控条件（gate）：** G1 目标实体 = 文章（关于 Brian May receiving a knighthood）；G2 `answer_comment_count` 与本地记录该计数**精确匹配**（读自目标实体页面的总数，非只数部分）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「目标定位规范」观察是否读取正确总数而非只数当前页。
- **边界情况：** 无法确认计数是否穷尽/正确 → null
- **不应给分的反例：** 不把「定位实体」与「读计数」拆两个分数；不把「只数部分/当前页」判通过（G2 违反→0）

#### 题目 91（63148504db1e675ccf57）—题面：See how many issues are currently open in The A11Y Project repository
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "计数是单次查询的单一输出，不拆成定位+计数两个分数"}
- **适用场景：** 查询题面指定实体的计数属性（单值），只读（目标实体：The A11Y Project 仓库）。
- **成功门控条件（gate）：** G1 目标实体 = The A11Y Project 仓库；G2 `answer_open_issue_count` 与本地记录该计数**精确匹配**（读自目标实体页面的总数，非只数部分）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「目标定位规范」观察是否读取正确总数而非只数当前页。
- **边界情况：** 无法确认计数是否穷尽/正确 → null
- **不应给分的反例：** 不把「定位实体」与「读计数」拆两个分数；不把「只数部分/当前页」判通过（G2 违反→0）

#### 题目 94（6828a71bbb7c7f4f6a37）—题面：Check how many comments the post about "bleaching your butthole" has
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "计数是单次查询的单一输出，不拆成定位+计数两个分数"}
- **适用场景：** 查询题面指定实体的计数属性（单值），只读（目标实体：帖子（关于 'bleaching your butthole'））。
- **成功门控条件（gate）：** G1 目标实体 = 帖子（关于 'bleaching your butthole'）；G2 `answer_comment_count` 与本地记录该计数**精确匹配**（读自目标实体页面的总数，非只数部分）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「目标定位规范」观察是否读取正确总数而非只数当前页。
- **边界情况：** 无法确认计数是否穷尽/正确 → null
- **不应给分的反例：** 不把「定位实体」与「读计数」拆两个分数；不把「只数部分/当前页」判通过（G2 违反→0）

#### 题目 95（6a852616e68dfe6d2878）—题面：Get the quantity of NOZE Rustic Coat Rack Wall Mounted Shelf in the shopping cart.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "计数是单次查询的单一输出，不拆成定位+计数两个分数"}
- **适用场景：** 查询题面指定实体的计数属性（单值），只读（目标实体：购物车内的 'NOZE Rustic Coat Rack Wall Mounted Shelf'）。
- **成功门控条件（gate）：** G1 目标实体 = 购物车内的 'NOZE Rustic Coat Rack Wall Mounted Shelf'；G2 `answer_quantity` 与本地记录该计数**精确匹配**（读自目标实体页面的总数，非只数部分）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「目标定位规范」观察是否读取正确总数而非只数当前页。
- **边界情况：** 无法确认计数是否穷尽/正确 → null
- **不应给分的反例：** 不把「定位实体」与「读计数」拆两个分数；不把「只数部分/当前页」判通过（G2 违反→0）
- **题面特例/备注：** quantity

#### 题目 103（78d05122d0a400a6272d）—题面：Check the number of items in the cart from the order summary.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "计数是单次查询的单一输出，不拆成定位+计数两个分数"}
- **适用场景：** 查询题面指定实体的计数属性（单值），只读（目标实体：订单摘要中的购物车）。
- **成功门控条件（gate）：** G1 目标实体 = 订单摘要中的购物车；G2 `answer_item_count` 与本地记录该计数**精确匹配**（读自目标实体页面的总数，非只数部分）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「目标定位规范」观察是否读取正确总数而非只数当前页。
- **边界情况：** 无法确认计数是否穷尽/正确 → null
- **不应给分的反例：** 不把「定位实体」与「读计数」拆两个分数；不把「只数部分/当前页」判通过（G2 违反→0）
- **题面特例/备注：** item_count

#### 题目 105（7b0a04b077e4d9102163）—题面：Check how many starred projects I have
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "计数是单次查询的单一输出，不拆成定位+计数两个分数"}
- **适用场景：** 查询题面指定实体的计数属性（单值），只读（目标实体：当前登录用户的 starred projects）。
- **成功门控条件（gate）：** G1 目标实体 = 当前登录用户的 starred projects；G2 `answer_starred_project_count` 与本地记录该计数**精确匹配**（读自目标实体页面的总数，非只数部分）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「目标定位规范」观察是否读取正确总数而非只数当前页。
- **边界情况：** 无法确认计数是否穷尽/正确 → null
- **不应给分的反例：** 不把「定位实体」与「读计数」拆两个分数；不把「只数部分/当前页」判通过（G2 违反→0）

#### 题目 115（8b7e1d9131362ea7a7f5）—题面：Find out how many comments the post about "What is the best way to remove a champagne bottle from your rectum?" has
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "计数是单次查询的单一输出，不拆成定位+计数两个分数"}
- **适用场景：** 查询题面指定实体的计数属性（单值），只读（目标实体：帖子（关于 'What is the best way to remove a champagne bottle…'））。
- **成功门控条件（gate）：** G1 目标实体 = 帖子（关于 'What is the best way to remove a champagne bottle…'）；G2 `answer_comment_count` 与本地记录该计数**精确匹配**（读自目标实体页面的总数，非只数部分）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「目标定位规范」观察是否读取正确总数而非只数当前页。
- **边界情况：** 无法确认计数是否穷尽/正确 → null
- **不应给分的反例：** 不把「定位实体」与「读计数」拆两个分数；不把「只数部分/当前页」判通过（G2 违反→0）

#### 题目 117（8f217e01825b6f114391）—题面：Check the total number of merge requests across all statuses in the OpenAPI Generator project.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "计数是单次查询的单一输出，不拆成定位+计数两个分数"}
- **适用场景：** 查询题面指定实体的计数属性（单值），只读（目标实体：OpenAPI Generator 项目）。
- **成功门控条件（gate）：** G1 目标实体 = OpenAPI Generator 项目；G2 `answer_all_merge_request_count` 与本地记录该计数**精确匹配**（读自目标实体页面的总数，非只数部分）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「目标定位规范」观察是否读取正确总数而非只数当前页。
- **边界情况：** 无法确认计数是否穷尽/正确 → null
- **不应给分的反例：** 不把「定位实体」与「读计数」拆两个分数；不把「只数部分/当前页」判通过（G2 违反→0）
- **题面特例/备注：** all merge requests（全状态）

#### 题目 122（9e246c9920d1c80ed596）—题面：Retrieve the number of submissions for the space forum.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "计数是单次查询的单一输出，不拆成定位+计数两个分数"}
- **适用场景：** 查询题面指定实体的计数属性（单值），只读（目标实体：space forum）。
- **成功门控条件（gate）：** G1 目标实体 = space forum；G2 `answer_submission_count` 与本地记录该计数**精确匹配**（读自目标实体页面的总数，非只数部分）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「目标定位规范」观察是否读取正确总数而非只数当前页。
- **边界情况：** 无法确认计数是否穷尽/正确 → null
- **不应给分的反例：** 不把「定位实体」与「读计数」拆两个分数；不把「只数部分/当前页」判通过（G2 违反→0）

#### 题目 137（aeda435714dad5e3f5c6）—题面：Retrieve the total number of issues across all statuses for The A11Y Project / a11yproject.com.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "计数是单次查询的单一输出，不拆成定位+计数两个分数"}
- **适用场景：** 查询题面指定实体的计数属性（单值），只读（目标实体：The A11Y Project / a11yproject.com 项目）。
- **成功门控条件（gate）：** G1 目标实体 = The A11Y Project / a11yproject.com 项目；G2 `answer_all_issue_count` 与本地记录该计数**精确匹配**（读自目标实体页面的总数，非只数部分）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「目标定位规范」观察是否读取正确总数而非只数当前页。
- **边界情况：** 无法确认计数是否穷尽/正确 → null
- **不应给分的反例：** 不把「定位实体」与「读计数」拆两个分数；不把「只数部分/当前页」判通过（G2 违反→0）
- **题面特例/备注：** all issues（全状态）

#### 题目 143（bbcfeac97cd866e06f1c）—题面：Check how many submissions are in the AskReddit forum
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "计数是单次查询的单一输出，不拆成定位+计数两个分数"}
- **适用场景：** 查询题面指定实体的计数属性（单值），只读（目标实体：AskReddit forum）。
- **成功门控条件（gate）：** G1 目标实体 = AskReddit forum；G2 `answer_submission_count` 与本地记录该计数**精确匹配**（读自目标实体页面的总数，非只数部分）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「目标定位规范」观察是否读取正确总数而非只数当前页。
- **边界情况：** 无法确认计数是否穷尽/正确 → null
- **不应给分的反例：** 不把「定位实体」与「读计数」拆两个分数；不把「只数部分/当前页」判通过（G2 违反→0）

#### 题目 149（c3210e310f50c17ee5ab）—题面：Check the number of completed to-dos.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "计数是单次查询的单一输出，不拆成定位+计数两个分数"}
- **适用场景：** 查询题面指定实体的计数属性（单值），只读（目标实体：当前用户的 completed to-dos）。
- **成功门控条件（gate）：** G1 目标实体 = 当前用户的 completed to-dos；G2 `answer_completed_todo_count` 与本地记录该计数**精确匹配**（读自目标实体页面的总数，非只数部分）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「目标定位规范」观察是否读取正确总数而非只数当前页。
- **边界情况：** 无法确认计数是否穷尽/正确 → null
- **不应给分的反例：** 不把「定位实体」与「读计数」拆两个分数；不把「只数部分/当前页」判通过（G2 违反→0）

#### 题目 150（c334c6a3aeb526c0cc15）—题面：View the number of stars for the system-design-primer repository
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "计数是单次查询的单一输出，不拆成定位+计数两个分数"}
- **适用场景：** 查询题面指定实体的计数属性（单值），只读（目标实体：system-design-primer 仓库）。
- **成功门控条件（gate）：** G1 目标实体 = system-design-primer 仓库；G2 `answer_star_count` 与本地记录该计数**精确匹配**（读自目标实体页面的总数，非只数部分）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「目标定位规范」观察是否读取正确总数而非只数当前页。
- **边界情况：** 无法确认计数是否穷尽/正确 → null
- **不应给分的反例：** 不把「定位实体」与「读计数」拆两个分数；不把「只数部分/当前页」判通过（G2 违反→0）
- **题面特例/备注：** stars

#### 题目 154（c7c76b2b4fc56c624da4）—题面：Check how many pending to-dos I have in GitLab
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "计数是单次查询的单一输出，不拆成定位+计数两个分数"}
- **适用场景：** 查询题面指定实体的计数属性（单值），只读（目标实体：当前用户在 GitLab 的 pending to-dos）。
- **成功门控条件（gate）：** G1 目标实体 = 当前用户在 GitLab 的 pending to-dos；G2 `answer_pending_todo_count` 与本地记录该计数**精确匹配**（读自目标实体页面的总数，非只数部分）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「目标定位规范」观察是否读取正确总数而非只数当前页。
- **边界情况：** 无法确认计数是否穷尽/正确 → null
- **不应给分的反例：** 不把「定位实体」与「读计数」拆两个分数；不把「只数部分/当前页」判通过（G2 违反→0）

#### 题目 159（ca513c352ac8683d59ba）—题面：Check how many issues are open in the ArduinoJson project
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "计数是单次查询的单一输出，不拆成定位+计数两个分数"}
- **适用场景：** 查询题面指定实体的计数属性（单值），只读（目标实体：ArduinoJson 项目）。
- **成功门控条件（gate）：** G1 目标实体 = ArduinoJson 项目；G2 `answer_open_issue_count` 与本地记录该计数**精确匹配**（读自目标实体页面的总数，非只数部分）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「目标定位规范」观察是否读取正确总数而非只数当前页。
- **边界情况：** 无法确认计数是否穷尽/正确 → null
- **不应给分的反例：** 不把「定位实体」与「读计数」拆两个分数；不把「只数部分/当前页」判通过（G2 违反→0）

#### 题目 168（d57f5a05cc1dd5127e70）—题面：Retrieve the number of forks for the project "Byte Blaze / empathy-prompts".
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "计数是单次查询的单一输出，不拆成定位+计数两个分数"}
- **适用场景：** 查询题面指定实体的计数属性（单值），只读（目标实体：Byte Blaze / empathy-prompts 项目）。
- **成功门控条件（gate）：** G1 目标实体 = Byte Blaze / empathy-prompts 项目；G2 `answer_fork_count` 与本地记录该计数**精确匹配**（读自目标实体页面的总数，非只数部分）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「目标定位规范」观察是否读取正确总数而非只数当前页。
- **边界情况：** 无法确认计数是否穷尽/正确 → null
- **不应给分的反例：** 不把「定位实体」与「读计数」拆两个分数；不把「只数部分/当前页」判通过（G2 违反→0）
- **题面特例/备注：** forks

#### 题目 178（dcc126a9d92300a10259）—题面：Check how many items are currently in my shopping cart
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "计数是单次查询的单一输出，不拆成定位+计数两个分数"}
- **适用场景：** 查询题面指定实体的计数属性（单值），只读（目标实体：当前购物车）。
- **成功门控条件（gate）：** G1 目标实体 = 当前购物车；G2 `answer_item_count` 与本地记录该计数**精确匹配**（读自目标实体页面的总数，非只数部分）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「目标定位规范」观察是否读取正确总数而非只数当前页。
- **边界情况：** 无法确认计数是否穷尽/正确 → null
- **不应给分的反例：** 不把「定位实体」与「读计数」拆两个分数；不把「只数部分/当前页」判通过（G2 违反→0）
- **题面特例/备注：** item_count

#### 题目 180（e0acc2846f49efa750d7）—题面：Retrieve the total number of issues across all statuses for Byte Blaze / accessible-html-content-patterns.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "计数是单次查询的单一输出，不拆成定位+计数两个分数"}
- **适用场景：** 查询题面指定实体的计数属性（单值），只读（目标实体：Byte Blaze / accessible-html-content-patterns 项目）。
- **成功门控条件（gate）：** G1 目标实体 = Byte Blaze / accessible-html-content-patterns 项目；G2 `answer_all_issue_count` 与本地记录该计数**精确匹配**（读自目标实体页面的总数，非只数部分）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「目标定位规范」观察是否读取正确总数而非只数当前页。
- **边界情况：** 无法确认计数是否穷尽/正确 → null
- **不应给分的反例：** 不把「定位实体」与「读计数」拆两个分数；不把「只数部分/当前页」判通过（G2 违反→0）
- **题面特例/备注：** all issues（全状态）

#### 题目 186（e68e1f03005a83f12ade）—题面：Check how many issues are open in the TrafficMonitor repository
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "计数是单次查询的单一输出，不拆成定位+计数两个分数"}
- **适用场景：** 查询题面指定实体的计数属性（单值），只读（目标实体：TrafficMonitor 仓库）。
- **成功门控条件（gate）：** G1 目标实体 = TrafficMonitor 仓库；G2 `answer_open_issue_count` 与本地记录该计数**精确匹配**（读自目标实体页面的总数，非只数部分）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「目标定位规范」观察是否读取正确总数而非只数当前页。
- **边界情况：** 无法确认计数是否穷尽/正确 → null
- **不应给分的反例：** 不把「定位实体」与「读计数」拆两个分数；不把「只数部分/当前页」判通过（G2 违反→0）
- **题面特例/备注：** open issues

#### 题目 188（ec17d35f33b53e5a1baa）—题面：Check how many commits have been made to the cloud-to-butt repository
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "计数是单次查询的单一输出，不拆成定位+计数两个分数"}
- **适用场景：** 查询题面指定实体的计数属性（单值），只读（目标实体：cloud-to-butt 仓库）。
- **成功门控条件（gate）：** G1 目标实体 = cloud-to-butt 仓库；G2 `answer_commit_count` 与本地记录该计数**精确匹配**（读自目标实体页面的总数，非只数部分）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「目标定位规范」观察是否读取正确总数而非只数当前页。
- **边界情况：** 无法确认计数是否穷尽/正确 → null
- **不应给分的反例：** 不把「定位实体」与「读计数」拆两个分数；不把「只数部分/当前页」判通过（G2 违反→0）
- **题面特例/备注：** commits

#### 题目 192（ee8e562868eff0202bf8）—题面：Find the number of submissions in the gaming forum.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "计数是单次查询的单一输出，不拆成定位+计数两个分数"}
- **适用场景：** 查询题面指定实体的计数属性（单值），只读（目标实体：gaming forum）。
- **成功门控条件（gate）：** G1 目标实体 = gaming forum；G2 `answer_submission_count` 与本地记录该计数**精确匹配**（读自目标实体页面的总数，非只数部分）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「目标定位规范」观察是否读取正确总数而非只数当前页。
- **边界情况：** 无法确认计数是否穷尽/正确 → null
- **不应给分的反例：** 不把「定位实体」与「读计数」拆两个分数；不把「只数部分/当前页」判通过（G2 违反→0）

#### 题目 198（fedf71fe5f3cf9866519）—题面：Find the number of submissions in the Music forum.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "计数是单次查询的单一输出，不拆成定位+计数两个分数"}
- **适用场景：** 查询题面指定实体的计数属性（单值），只读（目标实体：Music forum）。
- **成功门控条件（gate）：** G1 目标实体 = Music forum；G2 `answer_submission_count` 与本地记录该计数**精确匹配**（读自目标实体页面的总数，非只数部分）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「目标定位规范」观察是否读取正确总数而非只数当前页。
- **边界情况：** 无法确认计数是否穷尽/正确 → null
- **不应给分的反例：** 不把「定位实体」与「读计数」拆两个分数；不把「只数部分/当前页」判通过（G2 违反→0）

### 3.3 集合内计数（3 题）

#### 题目 83（5a5d552d30462f36409c）—题面：See how many issues across all statuses are assigned to me in the Byte Blaze / empathy-prompts project.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "条件过滤与计数是同一查询，不拆成两个分数"}
- **适用场景：** 在指定范围内按条件计数，只读（目标实体：Byte Blaze / empathy-prompts 项目内所有状态中指派给 'me' 的 issues）。
- **成功门控条件（gate）：** G1 目标实体 = Byte Blaze / empathy-prompts 项目内所有状态中指派给 'me' 的 issues；G2 `answer_count` 与本地记录中满足条件的记录总数**精确匹配**（穷尽整个范围，非只数当前页）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「目标定位规范」观察是否穷尽范围；「字段校验」观察条件是否与题面一致。
- **边界情况：** 无法确认是否穷尽范围 → null
- **不应给分的反例：** 不把「设置条件」与「计数」拆两个分数；不把「只数当前页」判通过（G2 违反→0）
- **题面特例/备注：** 穷尽全部状态

#### 题目 187（e99d790f732ba60e3c65）—题面：Count how many projects on this page have more than 10 stars
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "条件过滤与计数是同一查询，不拆成两个分数"}
- **适用场景：** 在指定范围内按条件计数，只读（目标实体：当前页面的项目）。
- **成功门控条件（gate）：** G1 目标实体 = 当前页面的项目；G2 `answer_count` 与本地记录中满足条件的记录总数**精确匹配**（穷尽整个范围，非只数当前页）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「目标定位规范」观察是否穷尽范围；「字段校验」观察条件是否与题面一致。
- **边界情况：** 无法确认是否穷尽范围 → null
- **不应给分的反例：** 不把「设置条件」与「计数」拆两个分数；不把「只数当前页」判通过（G2 违反→0）
- **题面特例/备注：** stars > 10 的项目数（穷尽当前页）

#### 题目 190（ed517c55ec73b52a521c）—题面：Check how many closed issues are assigned to me across my accessible projects.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "条件过滤与计数是同一查询，不拆成两个分数"}
- **适用场景：** 在指定范围内按条件计数，只读（目标实体：当前用户可访问项目内指派给 'me' 的 closed issues）。
- **成功门控条件（gate）：** G1 目标实体 = 当前用户可访问项目内指派给 'me' 的 closed issues；G2 `answer_count` 与本地记录中满足条件的记录总数**精确匹配**（穷尽整个范围，非只数当前页）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「目标定位规范」观察是否穷尽范围；「字段校验」观察条件是否与题面一致。
- **边界情况：** 无法确认是否穷尽范围 → null
- **不应给分的反例：** 不把「设置条件」与「计数」拆两个分数；不把「只数当前页」判通过（G2 违反→0）
- **题面特例/备注：** 穷尽全部可访问项目

### 3.4 最值聚合（14 题）

#### 题目 8（06c83311b1a750c09b79）—题面：Find out which forum has the most submissions
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "定位范围与取最值是同一聚合查询，不拆成两个分数"}
- **适用场景：** 在指定范围内取最值（最大/最小/最新/最早），只读（目标实体：全平台论坛列表）。
- **成功门控条件（gate）：** G1 目标实体 = 全平台论坛列表；G2 `answer_forum_name` == 本地记录中的**实际最值**（最大/最小/最新/最早；穷尽比较所有候选，非任取、非主观）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「目标定位规范」观察是否穷尽比较全部候选而非任取。
- **边界情况：** 无法确认最值是否全局最大/最小（无法核对全部候选）→ null；范围为空时按题面返回空/none 合法，不判失败（§6）
- **不应给分的反例：** 不把「定位范围」与「取最值」拆两个分数；不因「返回范围内某值」给分（须为实际最值，否则 G2 违反→0）
- **题面特例/备注：** 按 submissions 数取最大者

#### 题目 30（20ab1fb9f2d8a7878c12）—题面：Identify the most recent project update date on the dashboard.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "定位范围与取最值是同一聚合查询，不拆成两个分数"}
- **适用场景：** 在指定范围内取最值（最大/最小/最新/最早），只读（目标实体：dashboard 上的项目更新日期）。
- **成功门控条件（gate）：** G1 目标实体 = dashboard 上的项目更新日期；G2 `answer_updated_date` == 本地记录中的**实际最值**（最大/最小/最新/最早；穷尽比较所有候选，非任取、非主观）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「目标定位规范」观察是否穷尽比较全部候选而非任取。
- **边界情况：** 无法确认最值是否全局最大/最小（无法核对全部候选）→ null；范围为空时按题面返回空/none 合法，不判失败（§6）
- **不应给分的反例：** 不把「定位范围」与「取最值」拆两个分数；不因「返回范围内某值」给分（须为实际最值，否则 G2 违反→0）
- **题面特例/备注：** 取最新日期

#### 题目 41（2c61c04a55f42336851b）—题面：Find the post with the most comments on the current AskReddit page
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "定位范围与取最值是同一聚合查询，不拆成两个分数"}
- **适用场景：** 在指定范围内取最值（最大/最小/最新/最早），只读（目标实体：当前 AskReddit 页面的帖子）。
- **成功门控条件（gate）：** G1 目标实体 = 当前 AskReddit 页面的帖子；G2 `answer_title` == 本地记录中的**实际最值**（最大/最小/最新/最早；穷尽比较所有候选，非任取、非主观）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「目标定位规范」观察是否穷尽比较全部候选而非任取。
- **边界情况：** 无法确认最值是否全局最大/最小（无法核对全部候选）→ null；范围为空时按题面返回空/none 合法，不判失败（§6）
- **不应给分的反例：** 不把「定位范围」与「取最值」拆两个分数；不因「返回范围内某值」给分（须为实际最值，否则 G2 违反→0）
- **题面特例/备注：** 按 comments 数取最大；与 #171 题面高度相似，准则复用、各自独立判分

#### 题目 80（582b5ef57b87b952b392）—题面：Find the most recent closure or merge time among currently closed or merged merge requests in byteblaze/a11y-syntax-highlighting. Return completed_at in UTC as YYYY-MM-DDTHH:MMZ, discarding seconds. Return none if neither collection contains a request.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "定位范围与取最值是同一聚合查询，不拆成两个分数"}
- **适用场景：** 在指定范围内取最值（最大/最小/最新/最早），只读（目标实体：byteblaze/a11y-syntax-highlighting 的 closed/merged MR 集合）。
- **成功门控条件（gate）：** G1 目标实体 = byteblaze/a11y-syntax-highlighting 的 closed/merged MR 集合；G2 `answer_completed_at` == 本地记录中的**实际最值**（最大/最小/最新/最早；穷尽比较所有候选，非任取、非主观）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「目标定位规范」观察是否穷尽比较全部候选而非任取。
- **边界情况：** 无法确认最值是否全局最大/最小（无法核对全部候选）→ null；范围为空时按题面返回空/none 合法，不判失败（§6）
- **不应给分的反例：** 不把「定位范围」与「取最值」拆两个分数；不因「返回范围内某值」给分（须为实际最值，否则 G2 违反→0）
- **题面特例/备注：** 最晚 completed_at；UTC 'YYYY-MM-DDTHH:MMZ' 去秒；两集合皆空时返回 none 为空结果合法

#### 题目 98（70306d401418877c8921）—题面：Identify which forum has the most subscribers
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "定位范围与取最值是同一聚合查询，不拆成两个分数"}
- **适用场景：** 在指定范围内取最值（最大/最小/最新/最早），只读（目标实体：全平台论坛列表）。
- **成功门控条件（gate）：** G1 目标实体 = 全平台论坛列表；G2 `answer_forum_name` == 本地记录中的**实际最值**（最大/最小/最新/最早；穷尽比较所有候选，非任取、非主观）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「目标定位规范」观察是否穷尽比较全部候选而非任取。
- **边界情况：** 无法确认最值是否全局最大/最小（无法核对全部候选）→ null；范围为空时按题面返回空/none 合法，不判失败（§6）
- **不应给分的反例：** 不把「定位范围」与「取最值」拆两个分数；不因「返回范围内某值」给分（须为实际最值，否则 G2 违反→0）
- **题面特例/备注：** 按 subscribers 数取最大

#### 题目 128（a5a2d922b189348cfa7f）—题面：Find the most active forum based on number of submissions
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "定位范围与取最值是同一聚合查询，不拆成两个分数"}
- **适用场景：** 在指定范围内取最值（最大/最小/最新/最早），只读（目标实体：全平台论坛列表）。
- **成功门控条件（gate）：** G1 目标实体 = 全平台论坛列表；G2 `answer_forum_name` == 本地记录中的**实际最值**（最大/最小/最新/最早；穷尽比较所有候选，非任取、非主观）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「目标定位规范」观察是否穷尽比较全部候选而非任取。
- **边界情况：** 无法确认最值是否全局最大/最小（无法核对全部候选）→ null；范围为空时按题面返回空/none 合法，不判失败（§6）
- **不应给分的反例：** 不把「定位范围」与「取最值」拆两个分数；不因「返回范围内某值」给分（须为实际最值，否则 G2 违反→0）
- **题面特例/备注：** 按 submissions 数取最大（'most active'）

#### 题目 138（b045428cb375aecc3613）—题面：Find which forum has the most submissions on this platform
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "定位范围与取最值是同一聚合查询，不拆成两个分数"}
- **适用场景：** 在指定范围内取最值（最大/最小/最新/最早），只读（目标实体：本平台论坛列表）。
- **成功门控条件（gate）：** G1 目标实体 = 本平台论坛列表；G2 `answer_forum_name` == 本地记录中的**实际最值**（最大/最小/最新/最早；穷尽比较所有候选，非任取、非主观）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「目标定位规范」观察是否穷尽比较全部候选而非任取。
- **边界情况：** 无法确认最值是否全局最大/最小（无法核对全部候选）→ null；范围为空时按题面返回空/none 合法，不判失败（§6）
- **不应给分的反例：** 不把「定位范围」与「取最值」拆两个分数；不因「返回范围内某值」给分（须为实际最值，否则 G2 违反→0）
- **题面特例/备注：** 按 submissions 数取最大

#### 题目 141（b9fc14ca759f15cd389d）—题面：Find the highest rated vegan product on the first page
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "定位范围与取最值是同一聚合查询，不拆成两个分数"}
- **适用场景：** 在指定范围内取最值（最大/最小/最新/最早），只读（目标实体：第一页的 vegan 产品）。
- **成功门控条件（gate）：** G1 目标实体 = 第一页的 vegan 产品；G2 `answer_product` == 本地记录中的**实际最值**（最大/最小/最新/最早；穷尽比较所有候选，非任取、非主观）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「目标定位规范」观察是否穷尽比较全部候选而非任取。
- **边界情况：** 无法确认最值是否全局最大/最小（无法核对全部候选）→ null；范围为空时按题面返回空/none 合法，不判失败（§6）
- **不应给分的反例：** 不把「定位范围」与「取最值」拆两个分数；不因「返回范围内某值」给分（须为实际最值，否则 G2 违反→0）
- **题面特例/备注：** 按 rating 取最高者（需同时满足 vegan 过滤 + 最高评分 + 范围限第一页）

#### 题目 153（c73f96cd937d5a5d4222）—题面：Find the forum with the most submissions on the current page
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "定位范围与取最值是同一聚合查询，不拆成两个分数"}
- **适用场景：** 在指定范围内取最值（最大/最小/最新/最早），只读（目标实体：当前页面的论坛）。
- **成功门控条件（gate）：** G1 目标实体 = 当前页面的论坛；G2 `answer_forum_name` == 本地记录中的**实际最值**（最大/最小/最新/最早；穷尽比较所有候选，非任取、非主观）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「目标定位规范」观察是否穷尽比较全部候选而非任取。
- **边界情况：** 无法确认最值是否全局最大/最小（无法核对全部候选）→ null；范围为空时按题面返回空/none 合法，不判失败（§6）
- **不应给分的反例：** 不把「定位范围」与「取最值」拆两个分数；不因「返回范围内某值」给分（须为实际最值，否则 G2 违反→0）
- **题面特例/备注：** 按 submissions 数取最大（范围限当前页）

#### 题目 155（c9d198f8cc222a1285bd）—题面：Find the project with the most open issues on the current page
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "定位范围与取最值是同一聚合查询，不拆成两个分数"}
- **适用场景：** 在指定范围内取最值（最大/最小/最新/最早），只读（目标实体：当前页面的项目）。
- **成功门控条件（gate）：** G1 目标实体 = 当前页面的项目；G2 `answer_project` == 本地记录中的**实际最值**（最大/最小/最新/最早；穷尽比较所有候选，非任取、非主观）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「目标定位规范」观察是否穷尽比较全部候选而非任取。
- **边界情况：** 无法确认最值是否全局最大/最小（无法核对全部候选）→ null；范围为空时按题面返回空/none 合法，不判失败（§6）
- **不应给分的反例：** 不把「定位范围」与「取最值」拆两个分数；不因「返回范围内某值」给分（须为实际最值，否则 G2 违反→0）
- **题面特例/备注：** 按 open issues 数取最大（范围限当前页）

#### 题目 171（d83baacc79d7fd79e8c1）—题面：Find the post with the most comments on the AskReddit page
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "定位范围与取最值是同一聚合查询，不拆成两个分数"}
- **适用场景：** 在指定范围内取最值（最大/最小/最新/最早），只读（目标实体：AskReddit 页面的帖子）。
- **成功门控条件（gate）：** G1 目标实体 = AskReddit 页面的帖子；G2 `answer_title` == 本地记录中的**实际最值**（最大/最小/最新/最早；穷尽比较所有候选，非任取、非主观）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「目标定位规范」观察是否穷尽比较全部候选而非任取。
- **边界情况：** 无法确认最值是否全局最大/最小（无法核对全部候选）→ null；范围为空时按题面返回空/none 合法，不判失败（§6）
- **不应给分的反例：** 不把「定位范围」与「取最值」拆两个分数；不因「返回范围内某值」给分（须为实际最值，否则 G2 违反→0）
- **题面特例/备注：** 按 comments 数取最大；与 #41 题面高度相似，准则复用、各自独立判分

#### 题目 172（d87e55ef023592f031df）—题面：Find the oldest completed to-do item in your GitLab account.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "定位范围与取最值是同一聚合查询，不拆成两个分数"}
- **适用场景：** 在指定范围内取最值（最大/最小/最新/最早），只读（目标实体：当前用户 GitLab 的 completed to-dos）。
- **成功门控条件（gate）：** G1 目标实体 = 当前用户 GitLab 的 completed to-dos；G2 `answer_oldest_todo_title` == 本地记录中的**实际最值**（最大/最小/最新/最早；穷尽比较所有候选，非任取、非主观）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「目标定位规范」观察是否穷尽比较全部候选而非任取。
- **边界情况：** 无法确认最值是否全局最大/最小（无法核对全部候选）→ null；范围为空时按题面返回空/none 合法，不判失败（§6）
- **不应给分的反例：** 不把「定位范围」与「取最值」拆两个分数；不因「返回范围内某值」给分（须为实际最值，否则 G2 违反→0）
- **题面特例/备注：** oldest（最早完成）→ 报告 title

#### 题目 176（db25b171278a7d9c4cc6）—题面：Find the most recent release of The A11Y Project
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "定位范围与取最值是同一聚合查询，不拆成两个分数"}
- **适用场景：** 在指定范围内取最值（最大/最小/最新/最早），只读（目标实体：The A11Y Project 的 releases）。
- **成功门控条件（gate）：** G1 目标实体 = The A11Y Project 的 releases；G2 `answer_tag` == 本地记录中的**实际最值**（最大/最小/最新/最早；穷尽比较所有候选，非任取、非主观）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「目标定位规范」观察是否穷尽比较全部候选而非任取。
- **边界情况：** 无法确认最值是否全局最大/最小（无法核对全部候选）→ null；范围为空时按题面返回空/none 合法，不判失败（§6）
- **不应给分的反例：** 不把「定位范围」与「取最值」拆两个分数；不因「返回范围内某值」给分（须为实际最值，否则 G2 违反→0）
- **题面特例/备注：** most recent release → tag

#### 题目 196（f8fe2dec74b77ea9c172）—题面：Identify the oldest pending to-do in my list and report its title.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "定位范围与取最值是同一聚合查询，不拆成两个分数"}
- **适用场景：** 在指定范围内取最值（最大/最小/最新/最早），只读（目标实体：当前用户 pending to-dos）。
- **成功门控条件（gate）：** G1 目标实体 = 当前用户 pending to-dos；G2 `answer_oldest_todo_title` == 本地记录中的**实际最值**（最大/最小/最新/最早；穷尽比较所有候选，非任取、非主观）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「目标定位规范」观察是否穷尽比较全部候选而非任取。
- **边界情况：** 无法确认最值是否全局最大/最小（无法核对全部候选）→ null；范围为空时按题面返回空/none 合法，不判失败（§6）
- **不应给分的反例：** 不把「定位范围」与「取最值」拆两个分数；不因「返回范围内某值」给分（须为实际最值，否则 G2 违反→0）
- **题面特例/备注：** oldest（最早）→ 报告 title

### 3.5 状态枚举（4 题）

#### 题目 55（3c7b4db3d03b67efca2b）—题面：Check if Emma Lopez is subscribed to the newsletter.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段状态读取，不拆"}
- **适用场景：** 查询题面指定实体的状态枚举，只读（目标实体：客户 Emma Lopez）。
- **成功门控条件（gate）：** G1 目标实体 = 客户 Emma Lopez；G2 `answer_subscription_status` == 本地记录**实际状态**（如 subscribed / not subscribed、in stock / out of stock）；'否/缺货' 是合法状态值，不得判失败；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察状态值是否与本地记录一致、未把'否'当失败。
- **边界情况：** 无法确认实际状态 → null；'否' 状态不得判失败
- **不应给分的反例：** 不把「定位实体」与「读状态」拆两个分数；不把「未订阅/缺货」判失败（合法状态值）
- **题面特例/备注：** subscription_status；'未订阅' 是合法状态值

#### 题目 61（41dedbdeb66536b8d8d1）—题面：Check the stock status of the Pre-baked Gingerbread House Kit Value Pack.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段状态读取，不拆"}
- **适用场景：** 查询题面指定实体的状态枚举，只读（目标实体：产品 'Pre-baked Gingerbread House Kit Value Pack'）。
- **成功门控条件（gate）：** G1 目标实体 = 产品 'Pre-baked Gingerbread House Kit Value Pack'；G2 `answer_stock_status` == 本地记录**实际状态**（如 subscribed / not subscribed、in stock / out of stock）；'否/缺货' 是合法状态值，不得判失败；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察状态值是否与本地记录一致、未把'否'当失败。
- **边界情况：** 无法确认实际状态 → null；'否' 状态不得判失败
- **不应给分的反例：** 不把「定位实体」与「读状态」拆两个分数；不把「未订阅/缺货」判失败（合法状态值）
- **题面特例/备注：** stock_status

#### 题目 68（49c5b0402a3d521509dd）—题面：Check if the Nightfox Vulpes Night Vision Goggles are in stock.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段状态读取，不拆"}
- **适用场景：** 查询题面指定实体的状态枚举，只读（目标实体：产品 'Nightfox Vulpes Night Vision Goggles'）。
- **成功门控条件（gate）：** G1 目标实体 = 产品 'Nightfox Vulpes Night Vision Goggles'；G2 `answer_stock_status` == 本地记录**实际状态**（如 subscribed / not subscribed、in stock / out of stock）；'否/缺货' 是合法状态值，不得判失败；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察状态值是否与本地记录一致、未把'否'当失败。
- **边界情况：** 无法确认实际状态 → null；'否' 状态不得判失败
- **不应给分的反例：** 不把「定位实体」与「读状态」拆两个分数；不把「未订阅/缺货」判失败（合法状态值）
- **题面特例/备注：** in stock 状态；'缺货' 是合法状态值

#### 题目 136（ae68af8e1133e4f596dc）—题面：Check if you are subscribed to the newsletter.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段状态读取，不拆"}
- **适用场景：** 查询题面指定实体的状态枚举，只读（目标实体：当前用户）。
- **成功门控条件（gate）：** G1 目标实体 = 当前用户；G2 `answer_subscription_status` == 本地记录**实际状态**（如 subscribed / not subscribed、in stock / out of stock）；'否/缺货' 是合法状态值，不得判失败；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察状态值是否与本地记录一致、未把'否'当失败。
- **边界情况：** 无法确认实际状态 → null；'否' 状态不得判失败
- **不应给分的反例：** 不把「定位实体」与「读状态」拆两个分数；不把「未订阅/缺货」判失败（合法状态值）
- **题面特例/备注：** subscription_status；'未订阅' 是合法状态值

### 3.6 日期时间（14 题）

#### 题目 19（15563156f55a18d63ec0）—题面：Find out when the post about "Gregory Allen Howard" was submitted
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段日期读取，不拆"}
- **适用场景：** 查询题面指定实体的日期/时间字段，只读（目标实体：帖子（关于 'Gregory Allen Howard'））。
- **成功门控条件（gate）：** G1 目标实体 = 帖子（关于 'Gregory Allen Howard'）；G2 `answer_submission_date` 与本地记录参考日期**精确匹配**（含时区/格式；题面有格式要求时须满足）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察时区/格式是否满足题面要求。
- **边界情况：** 无法确认日期与本地记录一致 → null
- **不应给分的反例：** 不把「定位实体」与「读日期」拆两个分数；不因「日期对但格式/时区错」给分（G2/G5 违反→0）

#### 题目 25（18b4411f46e0c135a395）—题面：Check when the autojump project was last updated
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段日期读取，不拆"}
- **适用场景：** 查询题面指定实体的日期/时间字段，只读（目标实体：autojump 项目）。
- **成功门控条件（gate）：** G1 目标实体 = autojump 项目；G2 `answer_updated_date` 与本地记录参考日期**精确匹配**（含时区/格式；题面有格式要求时须满足）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察时区/格式是否满足题面要求。
- **边界情况：** 无法确认日期与本地记录一致 → null
- **不应给分的反例：** 不把「定位实体」与「读日期」拆两个分数；不因「日期对但格式/时区错」给分（G2/G5 违反→0）

#### 题目 37（275d2224448d1c011649）—题面：Check when the 1.0.0 version was released
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段日期读取，不拆"}
- **适用场景：** 查询题面指定实体的日期/时间字段，只读（目标实体：1.0.0 版本）。
- **成功门控条件（gate）：** G1 目标实体 = 1.0.0 版本；G2 `answer_released_date` 与本地记录参考日期**精确匹配**（含时区/格式；题面有格式要求时须满足）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察时区/格式是否满足题面要求。
- **边界情况：** 无法确认日期与本地记录一致 → null
- **不应给分的反例：** 不把「定位实体」与「读日期」拆两个分数；不因「日期对但格式/时区错」给分（G2/G5 违反→0）
- **题面特例/备注：** released_date

#### 题目 44（2fa6f09b1f19cd91fe9c）—题面：Find out when the project Byte Blaze / a11y-syntax-highlighting was last updated.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段日期读取，不拆"}
- **适用场景：** 查询题面指定实体的日期/时间字段，只读（目标实体：Byte Blaze / a11y-syntax-highlighting 项目）。
- **成功门控条件（gate）：** G1 目标实体 = Byte Blaze / a11y-syntax-highlighting 项目；G2 `answer_updated_date` 与本地记录参考日期**精确匹配**（含时区/格式；题面有格式要求时须满足）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察时区/格式是否满足题面要求。
- **边界情况：** 无法确认日期与本地记录一致 → null
- **不应给分的反例：** 不把「定位实体」与「读日期」拆两个分数；不因「日期对但格式/时区错」给分（G2/G5 违反→0）

#### 题目 53（3b0bc1fa93e1285754a7）—题面：Find out when the Super-SloMo repository was last updated
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段日期读取，不拆"}
- **适用场景：** 查询题面指定实体的日期/时间字段，只读（目标实体：Super-SloMo 仓库）。
- **成功门控条件（gate）：** G1 目标实体 = Super-SloMo 仓库；G2 `answer_updated_date` 与本地记录参考日期**精确匹配**（含时区/格式；题面有格式要求时须满足）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察时区/格式是否满足题面要求。
- **边界情况：** 无法确认日期与本地记录一致 → null
- **不应给分的反例：** 不把「定位实体」与「读日期」拆两个分数；不因「日期对但格式/时区错」给分（G2/G5 违反→0）

#### 题目 66（46202d04304eac1719ed）—题面：What is the submission date for the article about D.H Peligro, drummer of punk band Dead Kennedys, passing away?
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段日期读取，不拆"}
- **适用场景：** 查询题面指定实体的日期/时间字段，只读（目标实体：文章（关于 D.H Peligro））。
- **成功门控条件（gate）：** G1 目标实体 = 文章（关于 D.H Peligro）；G2 `answer_submission_date` 与本地记录参考日期**精确匹配**（含时区/格式；题面有格式要求时须满足）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察时区/格式是否满足题面要求。
- **边界情况：** 无法确认日期与本地记录一致 → null
- **不应给分的反例：** 不把「定位实体」与「读日期」拆两个分数；不因「日期对但格式/时区错」给分（G2/G5 违反→0）

#### 题目 82（59980d9d5249b017145a）—题面：Find out when the gumble project was last updated
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段日期读取，不拆"}
- **适用场景：** 查询题面指定实体的日期/时间字段，只读（目标实体：gumble 项目）。
- **成功门控条件（gate）：** G1 目标实体 = gumble 项目；G2 `answer_updated_date` 与本地记录参考日期**精确匹配**（含时区/格式；题面有格式要求时须满足）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察时区/格式是否满足题面要求。
- **边界情况：** 无法确认日期与本地记录一致 → null
- **不应给分的反例：** 不把「定位实体」与「读日期」拆两个分数；不因「日期对但格式/时区错」给分（G2/G5 违反→0）

#### 题目 102（77f7fe934bd24e280aa3）—题面：Find when the millennials-to-snake-people project was last updated
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段日期读取，不拆"}
- **适用场景：** 查询题面指定实体的日期/时间字段，只读（目标实体：millennials-to-snake-people 项目）。
- **成功门控条件（gate）：** G1 目标实体 = millennials-to-snake-people 项目；G2 `answer_updated_date` 与本地记录参考日期**精确匹配**（含时区/格式；题面有格式要求时须满足）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察时区/格式是否满足题面要求。
- **边界情况：** 无法确认日期与本地记录一致 → null
- **不应给分的反例：** 不把「定位实体」与「读日期」拆两个分数；不因「日期对但格式/时区错」给分（G2/G5 违反→0）

#### 题目 112（874e41af76db85c47ce4）—题面：See when the joke "My grandfather warned people that the Titanic would sink" was posted
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段日期读取，不拆"}
- **适用场景：** 查询题面指定实体的日期/时间字段，只读（目标实体：joke（'My grandfather warned people that the Titanic would sink'））。
- **成功门控条件（gate）：** G1 目标实体 = joke（'My grandfather warned people that the Titanic would sink'）；G2 `answer_submission_date` 与本地记录参考日期**精确匹配**（含时区/格式；题面有格式要求时须满足）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察时区/格式是否满足题面要求。
- **边界情况：** 无法确认日期与本地记录一致 → null
- **不应给分的反例：** 不把「定位实体」与「读日期」拆两个分数；不因「日期对但格式/时区错」给分（G2/G5 违反→0）

#### 题目 130（a8af28f0b01292514ad0）—题面：Find out when the "checkstyle" project was last updated
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段日期读取，不拆"}
- **适用场景：** 查询题面指定实体的日期/时间字段，只读（目标实体：checkstyle 项目）。
- **成功门控条件（gate）：** G1 目标实体 = checkstyle 项目；G2 `answer_updated_date` 与本地记录参考日期**精确匹配**（含时区/格式；题面有格式要求时须满足）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察时区/格式是否满足题面要求。
- **边界情况：** 无法确认日期与本地记录一致 → null
- **不应给分的反例：** 不把「定位实体」与「读日期」拆两个分数；不因「日期对但格式/时区错」给分（G2/G5 违反→0）

#### 题目 142（ba0e3915421dafab49c5）—题面：Check when the content_script.js file was last updated
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段日期读取，不拆"}
- **适用场景：** 查询题面指定实体的日期/时间字段，只读（目标实体：content_script.js 文件）。
- **成功门控条件（gate）：** G1 目标实体 = content_script.js 文件；G2 `answer_file_updated_date` 与本地记录参考日期**精确匹配**（含时区/格式；题面有格式要求时须满足）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察时区/格式是否满足题面要求。
- **边界情况：** 无法确认日期与本地记录一致 → null
- **不应给分的反例：** 不把「定位实体」与「读日期」拆两个分数；不因「日期对但格式/时区错」给分（G2/G5 违反→0）
- **题面特例/备注：** file_updated_date

#### 题目 145（bec64ee0077086f0b2cb）—题面：Check when the question about "song describes your love life" was posted
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段日期读取，不拆"}
- **适用场景：** 查询题面指定实体的日期/时间字段，只读（目标实体：question（'song describes your love life'））。
- **成功门控条件（gate）：** G1 目标实体 = question（'song describes your love life'）；G2 `answer_submission_date` 与本地记录参考日期**精确匹配**（含时区/格式；题面有格式要求时须满足）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察时区/格式是否满足题面要求。
- **边界情况：** 无法确认日期与本地记录一致 → null
- **不应给分的反例：** 不把「定位实体」与「读日期」拆两个分数；不因「日期对但格式/时区错」给分（G2/G5 违反→0）

#### 题目 166（d344b156d8c7f1aa850a）—题面：Check the date when the negative review for the Gingerbread House Kit was posted.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段日期读取，不拆"}
- **适用场景：** 查询题面指定实体的日期/时间字段，只读（目标实体：Gingerbread House Kit 的负面评论）。
- **成功门控条件（gate）：** G1 目标实体 = Gingerbread House Kit 的负面评论；G2 `answer_negative_review_date` 与本地记录参考日期**精确匹配**（含时区/格式；题面有格式要求时须满足）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察时区/格式是否满足题面要求。
- **边界情况：** 无法确认日期与本地记录一致 → null
- **不应给分的反例：** 不把「定位实体」与「读日期」拆两个分数；不因「日期对但格式/时区错」给分（G2/G5 违反→0）
- **题面特例/备注：** negative_review_date

#### 题目 193（efb765feca3cf117c9e3）—题面：View when my account was registered
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段日期读取，不拆"}
- **适用场景：** 查询题面指定实体的日期/时间字段，只读（目标实体：当前用户账号）。
- **成功门控条件（gate）：** G1 目标实体 = 当前用户账号；G2 `answer_registration_date` 与本地记录参考日期**精确匹配**（含时区/格式；题面有格式要求时须满足）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察时区/格式是否满足题面要求。
- **边界情况：** 无法确认日期与本地记录一致 → null
- **不应给分的反例：** 不把「定位实体」与「读日期」拆两个分数；不因「日期对但格式/时区错」给分（G2/G5 违反→0）
- **题面特例/备注：** registration_date

### 3.7 布尔/存在性（9 题）

#### 题目 28（1c3c050ec5ad45313ecf）—题面：Find out if there are any subscribers to the movies forum
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段布尔/存在性读取，不拆"}
- **适用场景：** 存在性/布尔查询，只读（目标实体：movies forum）。
- **成功门控条件（gate）：** G1 目标实体 = movies forum；G2 `answer_has_subscribers` == 本地记录**真实布尔值**；严格区分三态（false / 记录不存在 / 未找到→null，见 §2.7）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察三态（false/不存在/未找到）是否与本地真实状态一致。
- **边界情况：** 无法确认真实布尔值（未找到/证据不足）→ null，不得默认记 false（§5/§6）
- **不应给分的反例：** 不把「未找到」记为 false（P1/P5 违反）；不把 false 判为失败；不把「记录不存在」与「值为 false」混淆
- **题面特例/备注：** has_subscribers 三态（false / 不存在 / 未找到→null）

#### 题目 56（3d80812ae97396311085）—题面：Check if the main wiki page exists.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段布尔/存在性读取，不拆"}
- **适用场景：** 存在性/布尔查询，只读（目标实体：main wiki page）。
- **成功门控条件（gate）：** G1 目标实体 = main wiki page；G2 `answer_exists` == 本地记录**真实布尔值**；严格区分三态（false / 记录不存在 / 未找到→null，见 §2.7）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察三态（false/不存在/未找到）是否与本地真实状态一致。
- **边界情况：** 无法确认真实布尔值（未找到/证据不足）→ null，不得默认记 false（§5/§6）
- **不应给分的反例：** 不把「未找到」记为 false（P1/P5 违反）；不把 false 判为失败；不把「记录不存在」与「值为 false」混淆
- **题面特例/备注：** exists 三态（存在 / 不存在 / 未找到→null）

#### 题目 87（6096f93770d67474ee61）—题面：Check whether my current shopping cart qualifies for free shipping to my default saved address without changing the cart or address. Do not place an order.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段布尔/存在性读取，不拆"}
- **适用场景：** 存在性/布尔查询，只读（目标实体：当前购物车 + 默认保存地址）。
- **成功门控条件（gate）：** G1 目标实体 = 当前购物车 + 默认保存地址；G2 `answer_free_shipping_available` == 本地记录**真实布尔值**；严格区分三态（false / 记录不存在 / 未找到→null，见 §2.7）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察三态（false/不存在/未找到）是否与本地真实状态一致。
- **边界情况：** 无法确认真实布尔值（未找到/证据不足）→ null，不得默认记 false（§5/§6）
- **不应给分的反例：** 不把「未找到」记为 false（P1/P5 违反）；不把 false 判为失败；不把「记录不存在」与「值为 false」混淆
- **题面特例/备注：** free_shipping_available 三态；不改购物车/不改地址/不下单

#### 题目 93（67ace090b86bd67c69f0）—题面：Check if there are any open issues for the cloud-to-butt project
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段布尔/存在性读取，不拆"}
- **适用场景：** 存在性/布尔查询，只读（目标实体：cloud-to-butt 项目）。
- **成功门控条件（gate）：** G1 目标实体 = cloud-to-butt 项目；G2 `answer_exists` == 本地记录**真实布尔值**；严格区分三态（false / 记录不存在 / 未找到→null，见 §2.7）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察三态（false/不存在/未找到）是否与本地真实状态一致。
- **边界情况：** 无法确认真实布尔值（未找到/证据不足）→ null，不得默认记 false（§5/§6）
- **不应给分的反例：** 不把「未找到」记为 false（P1/P5 违反）；不把 false 判为失败；不把「记录不存在」与「值为 false」混淆
- **题面特例/备注：** exists 三态（是否有任何 open issues）

#### 题目 129（a748206690e0427ddd04）—题面：Check if the shipping method can be changed from Flat Rate - Fixed at this stage of checkout
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段布尔/存在性读取，不拆"}
- **适用场景：** 存在性/布尔查询，只读（目标实体：当前 checkout 阶段）。
- **成功门控条件（gate）：** G1 目标实体 = 当前 checkout 阶段；G2 `answer_alternative_shipping_available` == 本地记录**真实布尔值**；严格区分三态（false / 记录不存在 / 未找到→null，见 §2.7）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察三态（false/不存在/未找到）是否与本地真实状态一致。
- **边界情况：** 无法确认真实布尔值（未找到/证据不足）→ null，不得默认记 false（§5/§6）
- **不应给分的反例：** 不把「未找到」记为 false（P1/P5 违反）；不把 false 判为失败；不把「记录不存在」与「值为 false」混淆
- **题面特例/备注：** alternative_shipping_available 三态（能否从 Flat Rate - Fixed 更改）

#### 题目 158（ca05753924c09a2b379f）—题面：Check if there are any wiki pages available
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段布尔/存在性读取，不拆"}
- **适用场景：** 存在性/布尔查询，只读（目标实体：wiki pages）。
- **成功门控条件（gate）：** G1 目标实体 = wiki pages；G2 `answer_exists` == 本地记录**真实布尔值**；严格区分三态（false / 记录不存在 / 未找到→null，见 §2.7）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察三态（false/不存在/未找到）是否与本地真实状态一致。
- **边界情况：** 无法确认真实布尔值（未找到/证据不足）→ null，不得默认记 false（§5/§6）
- **不应给分的反例：** 不把「未找到」记为 false（P1/P5 违反）；不把 false 判为失败；不把「记录不存在」与「值为 false」混淆
- **题面特例/备注：** exists 三态（是否有任何 wiki pages）

#### 题目 163（d0e66b5ec2fd2c26f88e）—题面：Find out if the Intel NUC Kit NUC6i7KYK Mini PC comes with a power cord
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段布尔/存在性读取，不拆"}
- **适用场景：** 存在性/布尔查询，只读（目标实体：Intel NUC Kit NUC6i7KYK Mini PC）。
- **成功门控条件（gate）：** G1 目标实体 = Intel NUC Kit NUC6i7KYK Mini PC；G2 `answer_power_cord_included` == 本地记录**真实布尔值**；严格区分三态（false / 记录不存在 / 未找到→null，见 §2.7）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察三态（false/不存在/未找到）是否与本地真实状态一致。
- **边界情况：** 无法确认真实布尔值（未找到/证据不足）→ null，不得默认记 false（§5/§6）
- **不应给分的反例：** 不把「未找到」记为 false（P1/P5 违反）；不把 false 判为失败；不把「记录不存在」与「值为 false」混淆
- **题面特例/备注：** power_cord_included 三态

#### 题目 165（d2b42088c0be8bc2f160）—题面：Find out if user MarvelsGrantMan136 is whitelisted on the platform.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段布尔/存在性读取，不拆"}
- **适用场景：** 存在性/布尔查询，只读（目标实体：用户 MarvelsGrantMan136）。
- **成功门控条件（gate）：** G1 目标实体 = 用户 MarvelsGrantMan136；G2 `answer_whitelisted` == 本地记录**真实布尔值**；严格区分三态（false / 记录不存在 / 未找到→null，见 §2.7）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察三态（false/不存在/未找到）是否与本地真实状态一致。
- **边界情况：** 无法确认真实布尔值（未找到/证据不足）→ null，不得默认记 false（§5/§6）
- **不应给分的反例：** 不把「未找到」记为 false（P1/P5 违反）；不把 false 判为失败；不把「记录不存在」与「值为 false」混淆
- **题面特例/备注：** whitelisted 三态

#### 题目 177（db3e72832768a5e92899）—题面：Check if dark mode is currently enabled
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "单字段布尔/存在性读取，不拆"}
- **适用场景：** 存在性/布尔查询，只读（目标实体：当前 dark mode 设置）。
- **成功门控条件（gate）：** G1 目标实体 = 当前 dark mode 设置；G2 `answer_dark_mode` == 本地记录**真实布尔值**；严格区分三态（false / 记录不存在 / 未找到→null，见 §2.7）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察三态（false/不存在/未找到）是否与本地真实状态一致。
- **边界情况：** 无法确认真实布尔值（未找到/证据不足）→ null，不得默认记 false（§5/§6）
- **不应给分的反例：** 不把「未找到」记为 false（P1/P5 违反）；不把 false 判为失败；不把「记录不存在」与「值为 false」混淆
- **题面特例/备注：** dark_mode 三态

### 3.8 集合/列表（3 题）

#### 题目 120（9cb0a2693df3645337ee）—题面：Check what payment methods are available for this purchase
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "一次返回完整集合，不拆"}
- **适用场景：** 集合/列表查询，只读（目标实体：当前 purchase 的支付方式）。
- **成功门控条件（gate）：** G1 目标实体 = 当前 purchase 的支付方式；G2 `answer_payment_methods` 与本地参考集合**精确相等**（无遗漏、无多余、无重复）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察集合是否无遗漏/无多余/无重复。
- **边界情况：** 无法确认集合是否穷尽 → null
- **不应给分的反例：** 不把「定位范围」与「列集合」拆两个分数；不因「列了部分」给分（须完整集合，G2 违反→0）
- **题面特例/备注：** payment_methods 集合

#### 题目 156（c9e49f9b5ac1dd332e59）—题面：Check which projects have the most open issues
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "一次返回完整集合，不拆"}
- **适用场景：** 集合/列表查询，只读（目标实体：全部项目）。
- **成功门控条件（gate）：** G1 目标实体 = 全部项目；G2 `answer_projects` 与本地参考集合**精确相等**（无遗漏、无多余、无重复）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察集合是否无遗漏/无多余/无重复。
- **边界情况：** 无法确认集合是否穷尽 → null
- **不应给分的反例：** 不把「定位范围」与「列集合」拆两个分数；不因「列了部分」给分（须完整集合，G2 违反→0）
- **题面特例/备注：** projects 集合（open issues 最多者）

#### 题目 162（cf17936dfd58f2333310）—题面：Look for projects with the most stars on the current page
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "一次返回完整集合，不拆"}
- **适用场景：** 集合/列表查询，只读（目标实体：当前页面的项目）。
- **成功门控条件（gate）：** G1 目标实体 = 当前页面的项目；G2 `answer_projects` 与本地参考集合**精确相等**（无遗漏、无多余、无重复）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察集合是否无遗漏/无多余/无重复。
- **边界情况：** 无法确认集合是否穷尽 → null
- **不应给分的反例：** 不把「定位范围」与「列集合」拆两个分数；不因「列了部分」给分（须完整集合，G2 违反→0）
- **题面特例/备注：** projects 集合（stars 最多者；范围限当前页）

### 3.9 多字段（2 题）

#### 题目 64（42c114bf04c61fd15ad1）—题面：Retrieve the title and number of comments for the post "You win $1B but in exchange you can never use social media again, are you interested what would you do?"
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "同一记录的两个字段同 gate 验证，不拆成字段各自 0.5"}
- **适用场景：** 同一记录的多字段查询，只读（目标实体：帖子（标题 'You win $1B but in exchange you can never use social media again…'））。
- **成功门控条件（gate）：** G1 目标实体 = 帖子（标题 'You win $1B but in exchange you can never use social media again…'）；G2 多字段（见题面）均与本地参考值**精确匹配**，且**同源**（同一记录）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察两字段是否同源、有无混淆。
- **边界情况：** 仅部分字段可验证 → 证据不足 → null，不得按「对了一半」给分
- **不应给分的反例：** 不拆「字段 A 0.5 + 字段 B 0.5」；不因「一字段对」给分（G2 违反→0）
- **题面特例/备注：** title + comment_count 两字段同源；判定由题绑定 contract 给出

#### 题目 110（827c1feb3bf63a67873f）—题面：On the local Music forum, find the post titled "Portugal. The Man spotlights health care for Alaska Indigenous communities in new video" and report its exact title and submitting username. Use the local post metadata; opening or summarizing the external publisher article is not requested.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "同一记录的两个字段同 gate 验证，不拆成字段各自 0.5"}
- **适用场景：** 同一记录的多字段查询，只读（目标实体：帖子（Music forum，标题 'Portugal. The Man spotlights health care…'））。
- **成功门控条件（gate）：** G1 目标实体 = 帖子（Music forum，标题 'Portugal. The Man spotlights health care…'）；G2 多字段（见题面）均与本地参考值**精确匹配**，且**同源**（同一记录）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察两字段是否同源、有无混淆。
- **边界情况：** 仅部分字段可验证 → 证据不足 → null，不得按「对了一半」给分
- **不应给分的反例：** 不拆「字段 A 0.5 + 字段 B 0.5」；不因「一字段对」给分（G2 违反→0）
- **题面特例/备注：** exact title + submitting username 两字段；只用本地帖子元数据，不打开/总结外部文章

### 3.10 source-contract 判定（5 题）

#### 题目 50（394010495e00e016fe24）—题面：Check the scale of the current map view
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "题面是单一查询动作，判定谓词由 contract 给出，不拆"}
- **适用场景：** 判定由题绑定 contract 给出；题面为单一查询/报告动作（目标实体：当前地图视图）。
- **成功门控条件（gate）：** G1 目标实体 = 当前地图视图；G2 answer 值满足题绑定 source contract 的判定谓词（与题面语义一致）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察答案是否与 contract 谓词一致。
- **边界情况：** 无法确认 answer 是否满足 contract 谓词 → null
- **不应给分的反例：** 不拆「定位视图」与「读取 scale/coords」；不得脱离 contract 谓词另立标准（P5）
- **题面特例/备注：** scale；判定条件由题绑定 contract 给出

#### 题目 78（55d84e6be0f0c0f44d8f）—题面：Find the distance scale for the current map view
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "题面是单一查询动作，判定谓词由 contract 给出，不拆"}
- **适用场景：** 判定由题绑定 contract 给出；题面为单一查询/报告动作（目标实体：当前地图视图）。
- **成功门控条件（gate）：** G1 目标实体 = 当前地图视图；G2 answer 值满足题绑定 source contract 的判定谓词（与题面语义一致）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察答案是否与 contract 谓词一致。
- **边界情况：** 无法确认 answer 是否满足 contract 谓词 → null
- **不应给分的反例：** 不拆「定位视图」与「读取 scale/coords」；不得脱离 contract 谓词另立标准（P5）
- **题面特例/备注：** distance scale；判定由题绑定 contract 给出

#### 题目 108（7ed6122ce8c7f4646f43）—题面：View the map scale information at the current zoom level.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "题面是单一查询动作，判定谓词由 contract 给出，不拆"}
- **适用场景：** 判定由题绑定 contract 给出；题面为单一查询/报告动作（目标实体：当前缩放级别的地图）。
- **成功门控条件（gate）：** G1 目标实体 = 当前缩放级别的地图；G2 answer 值满足题绑定 source contract 的判定谓词（与题面语义一致）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察答案是否与 contract 谓词一致。
- **边界情况：** 无法确认 answer 是否满足 contract 谓词 → null
- **不应给分的反例：** 不拆「定位视图」与「读取 scale/coords」；不得脱离 contract 谓词另立标准（P5）
- **题面特例/备注：** map scale；判定由题绑定 contract 给出

#### 题目 132（ad14f1ea651d3dfaa032）—题面：Find the current coordinates shown on the map
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "题面是单一查询动作，判定谓词由 contract 给出，不拆"}
- **适用场景：** 判定由题绑定 contract 给出；题面为单一查询/报告动作（目标实体：当前地图）。
- **成功门控条件（gate）：** G1 目标实体 = 当前地图；G2 answer 值满足题绑定 source contract 的判定谓词（与题面语义一致）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察答案是否与 contract 谓词一致。
- **边界情况：** 无法确认 answer 是否满足 contract 谓词 → null
- **不应给分的反例：** 不拆「定位视图」与「读取 scale/coords」；不得脱离 contract 谓词另立标准（P5）
- **题面特例/备注：** current coordinates；判定由题绑定 contract 给出；与 #194 题面高度相似

#### 题目 194（f339a1b31f983a1b6cdb）—题面：Find the current map coordinates
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **atomicity：** {"is_atomic": true, "reason": "题面是单一查询动作，判定谓词由 contract 给出，不拆"}
- **适用场景：** 判定由题绑定 contract 给出；题面为单一查询/报告动作（目标实体：当前地图）。
- **成功门控条件（gate）：** G1 目标实体 = 当前地图；G2 answer 值满足题绑定 source contract 的判定谓词（与题面语义一致）；G3 `requested_records_unchanged`（只读，未改任何数据）；G4 `page_valid`（页面有效可用，≠ 目标定位正确）；G5 `answer_schema`（字段/格式符合 schema，不为漏答放宽）。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点与观察方式见 §1.2）；判定标准同 §1.2；观察补充：「字段校验」观察答案是否与 contract 谓词一致。
- **边界情况：** 无法确认 answer 是否满足 contract 谓词 → null
- **不应给分的反例：** 不拆「定位视图」与「读取 scale/coords」；不得脱离 contract 谓词另立标准（P5）
- **题面特例/备注：** current coordinates；判定由题绑定 contract 给出；与 #132 题面高度相似

## 附录 A：错误拆法对照表（防回归，节选）

| 类型 | 错误拆法（禁止） |
|---|---|
| lookup / date / status | 定位实体 0.5 + 读字段值 0.5 |
| count_entity / count_set | 定位范围 0.5 + 计数 0.5（且「只数当前页」不判通过） |
| aggregate | 定位范围 0.5 + 取最值 0.5（须为实际最值） |
| boolean | 把「未找到」记 false；把 false 判失败 |
| set | 定位范围 0.5 + 列集合 0.5（须完整集合） |
| multi（#64/#110） | 字段 A 0.5 + 字段 B 0.5 |
| src（#50/#78/#108/#132/#194） | 定位视图 0.5 + 读取 scale/coords 0.5 |

## 附录 B：回归检查清单（提交前逐条勾选）

- [x] 每题都有 atomicity（is_atomic + reason）。
- [x] gate 全部映射到二值判定谓词（answer_<字段> / requested_records_unchanged / page_valid / answer_schema），无放宽/新增标准。
- [x] 质量维度仅在 gate 通过后计分，权重和 = 1.0。
- [x] 未把硬前提（定位对象/读对值）拆成分数。
- [x] 多字段题（#64/#110）未拆成字段各 0.5。
- [x] 重复/近似题（#41=#171、#132=#194、#128≈#138 等）各自独立判分、准则复用、未合并。
- [x] boolean/存在性 9 题（#28/#56/#87/#93/#129/#158/#163/#165/#177）已区分 false/不存在/未找到（null）。
- [x] 空结果按「与本地真实状态一致」判定（#80 return none、#56/#158 exists=false 等），未一律判 0。
- [x] 权重属于已登记方案（query 型 0.30/0.30/0.25/0.15），无未说明的第三套。
- [x] 执行顺序正确：本批为 binary 内 batch4（answer 明细 132 题），299 题 native 属 batch5、non-binary/remaining 未越序提前动。


---

<!-- ===== reward-criteria-decomposition-batch5-native-contract.md ==== -->

# 子奖励判断准则细分 · 第五批：ordinary_query native_contract 集合（299 题）

> 延续批0–批4 的 Gate + Quality 二段式。本文只做**判定准则的细分与可操作化**，不实现奖励计算、不重设计奖励方案。
> 计算公式 `R = null / 0 / base + (1-base)·Q` 由计算层实现，base 数值不在本文范围。

## 0. 范围与方法（仅依据文档）

- **数据源**：`docs/reward-inventory/binary-reward-tasks.md`（497 题）内嵌 `native_contract` JSON 的 299 题。
- **本批范围**：`site_query_rules.evaluate_query:ordinary_query` 中内嵌 native_contract 的 **299 题**（batch4 的 answer 明细 132 题已另批完成）。
- **核对结论**：299 题 JSON 全部可解析（0 缺失 / 0 损坏）。以「终页路径匹配 + 标题/heading 可见」的**导航终态**为主；**54 题 `status=ready`**（admin 导航 menu 24 + page 30）、**245 题 draft/candidate**（contract 可能变更）；其中 **3 题为写操作**（创建 GitLab 组 #454/#455/#456，判定为 group_creation，非只读导航）。

**判定形态分布：**

| 判定形态 | 题数 | | 判定形态 | 题数 |
|---|---|---|---|---|
| 路径+标题导航（path_heading）| 100 | Reddit 搜索（reddit）| 3 |
| 地图（map）| 41 | 创建组（写操作）（empty_nonready）| 3 |
| admin 页面导航（admin_page）| 30 | 最近订单（recent_orders）| 2 |
| admin 菜单导航（admin_menu）| 24 | GitLab family（gitlab_family）| 2 |
| 仓库页（repository）| 20 | 组表单（group_form）| 1 |
| 路径+页面标题导航（path_title）| 16 | 待办（todo）| 1 |
| 产品页（product）| 15 | Star 收藏（starrer）| 1 |
| 项目目录（project_directory）| 7 | 认证页（auth_page）| 1 |
| 分类/板块（category）| 7 | 导航控件（nav_control）| 1 |
| issue/MR 列表（issuable）| 6 | 订单（order）| 1 |
| 论坛（forum）| 5 | CMS 区块（cms）| 1 |
| GitLab 区块（gitlab_section）| 3 | 帖子列表（post）| 1 |
| 带查询参数（query_params）| 3 | Reddit 主页（reddit_profile）| 1 |
| 去重列表（distinct_list）| 3 |  |

### 0.1 权重方案登记（对应 reminder §4）

本批 299 题中，**296 题为导航/访问**（只读，无写操作、无「保存生效」环节），**3 题为创建组写操作**（#454/#455/#456）。据此采用**方案 B**，沿用两套已登记权重：
- 导航/访问（296 题）→ query 型：目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15。
- 创建组写操作（3 题）→ update/create 型：操作范围 0.35 / 验证规范 0.30 / 保存确认 0.20 / 证据充分性 0.15。
两套权重和恒 = 1.0，均属已登记方案，不引入第三套。

## 1. native 导航/访问题通用框架（296 题共享）

### 1.1 成功门控条件（gate，硬前提合取）

> 任一硬前提**明确为假** → 该题 R=0；任一关键项**证据不足且无法确认** → R=null（不转 0、不转失败）。

- **G1 终页路径匹配**：终页路径匹配 `path_regex`（或 admin 导航的 `target_path` / `menu_id`），未停在同名/相邻对象页。
- **G2 终页语义身份匹配**：终页标题/heading 匹配 `heading_regex` / `title_regex`（identity_source=title 时以页面标题为身份；admin 导航以 `spec.heading` / `menu_label`）。
- **G3 语义字段匹配**（题面含特殊字段时）：map/product/forum/issuable/repository 等字段与题面目标一致。
- **G4 真实导航到达，无负例状态**：通过真实网站导航到达（非直接注入 URL / 后台跳转）；未命中 control_plan.negative（wrong_object_same_page_type / matching_path_404 / login_redirect / no_op_initial_page）。
- **G5 `requested_records_unchanged`**：导航/访问为只读，未修改任何数据。
- **G6 `page_valid` + `answer_schema`**：页面健康可用（≠ 目标定位正确），终态满足 schema（不为漏答放宽）。

### 1.2 质量维度（导航型，仅在 gate 通过后计分；权重和 = 1.0）

| 维度 | 权重 | 判定标准（0.0 / 0.5 / 1.0 锚点，可插值） | 观察方式 |
|---|---|---|---|
| 目标定位规范 | 0.30 | 0.0：到错对象/同名混淆/反复试错；0.5：到达正确但过程有冗余探索或回退；1.0：直达目标页面，无冗余/回退 | 检查导航轨迹是否直达、有无回退/试错 |
| 来源合规 | 0.30 | 0.0：注入 URL / 后台跳转 / 推测；0.5：真实导航但绕路；1.0：走真实导航链路直达 | 检查是否通过真实网站导航到达（control_plan.positive） |
| 字段校验 | 0.25 | 0.0：终页身份/语义字段不匹配；0.5：部分匹配；1.0：path+heading+语义字段均匹配 | 检查终页 URL/标题/语义字段 |
| 证据充分性 | 0.15 | 0.0：无页面证据；0.5：部分可见；1.0：终页 URL/标题/语义字段可见 | 终页 URL/标题/字段是否在 observation 可见 |

### 1.3 通用反例（do_not_do，导航型全部适用）

- 不把「到达同类型但错误对象」判成功（wrong_object_same_page_type → G1/G2 违反 → 0）。
- 不把「匹配路径但 404」「登录重定向」「原地不动」判成功（G4 违反 → 0）。
- 不把「直接注入 URL / 后台跳转」视为等价于真实导航（G4 违反 → 0）。
- 不把「导航到页面」与「确认标题/身份」拆两个分数（同一导航任务的两环节）。
- 不因「页面有效但对象错」给分（G1/G2 违反 → 0）。

### 1.4 通用边界（unknown_handling，导航型全部适用）

- 无法确认终页路径/标题是否匹配 → null（明确不匹配则 0）。
- 无法确认是否真实导航到达（轨迹缺失）→ null。
- 终页正确、但中途改过数据 → G5 违反 → 0。

## 2. 判定形态子框架

### 2.1 admin 菜单导航

- 菜单导航（只读）：G1 导航到指定菜单（menu_label/menu_id）；G2 菜单目标页可见；G4/G5/G6 同 §1.1。反例：点到相邻菜单、菜单未真正展开、原地不动。

### 2.2 admin 页面导航

- 页面导航（只读）：G1 终页路径 == target_path；G2 终页 heading == spec.heading；G4/G5/G6 同 §1.1。反例：到相邻页面、heading 不匹配、原地不动。

### 2.3 路径+标题导航

- 路径+标题（只读）：G1 path_regex 匹配；G2 heading_regex 匹配；G4/G5/G6 同 §1.1。反例：同类型错误对象、404、登录重定向。

### 2.4 路径+页面标题导航

- 路径+页面标题（只读）：G1 path_regex 匹配；G2 title_regex 匹配（identity_source=title）；G4/G5/G6 同 §1.1。

### 2.5 地图

- 地图（只读查询/设置路线参数）：G1 path_regex + G2 heading_regex（若有）+ G3 map 语义字段（路线/坐标/列表/面板）与题面目标一致。反例：错误路线/坐标、地图未加载。

### 2.6 产品页

- 产品页（只读）：G1 path_regex + G2 heading + G3 product_details/product_panel 与题面目标产品一致。

### 2.7 仓库页

- 仓库页（只读）：G1 path_regex + G2 title_regex + G3 repository 字段与题面目标仓库一致。

### 2.8 论坛

- 论坛（只读）：G1 path_regex + G2 heading + G3 forum_list 与题面目标论坛一致。

### 2.9 issue/MR 列表

- issue/MR 列表（只读）：G1 path_regex + G2 heading + G3 issuable_list 与题面目标集合一致。

### 2.10 项目目录

- 项目目录（只读）：G1 path_regex + G2 title + G3 project_directory 与题面目标目录一致。

### 2.11 分类/板块

- 分类/板块（只读）：G1 path_regex + G2 heading + G3 category 与题面目标分类一致。

### 2.12 Reddit 搜索

- Reddit 搜索（只读）：G1 path_regex + G2 heading + G3 reddit_search 与题面搜索目标一致。

### 2.13 待办

- 待办（只读）：G1 path_regex + G2 heading + G3 todo_target 与题面目标待办一致。

### 2.14 订单

- 订单（只读）：G1 path_regex + G2 heading + G3 order_detail 与题面目标订单一致。

### 2.15 帖子列表

- 帖子列表（只读）：G1 path_regex + G2 heading + G3 post_list 与题面目标帖子一致。

### 2.16 最近订单

- 最近订单（只读）：G1 path_regex + G2 heading + G3 recent_ordered_items 与题面集合一致。

### 2.17 Star 收藏

- Star 收藏（只读）：G1 path_regex + G2 title + G3 starrer_collection 与题面集合一致。

### 2.18 带查询参数

- 带查询参数（只读）：G1 path_regex + G2 heading + G3 query_params 与题面参数一致。

### 2.19 去重列表

- 去重列表（只读）：G1 path_regex + G2 heading + G3 distinct_list_heading_regex 与题面一致。

### 2.20 组表单

- 组表单（只读）：G1 path_regex + G2 title + G3 group_form 与题面目标组一致。

### 2.21 认证页

- 认证页（只读）：G1 path_regex + G2 heading + G3 authentication_page/visible_form 与题面一致。

### 2.22 导航控件

- 导航控件（只读）：G1 path_regex + G2 title + G3 navigation_control 与题面一致。

### 2.23 CMS 区块

- CMS 区块（只读）：G1 path_regex + G2 heading + G3 cms_section 与题面一致。

### 2.24 Reddit 主页

- Reddit 主页（只读）：G1 path_regex + G2 heading + G3 reddit_any_profile 与题面一致。

### 2.25 GitLab 区块

- GitLab 区块（只读）：G1 path_regex + G2 title + G3 gitlab_section 与题面一致。

### 2.26 GitLab family

- GitLab family（只读）：G1/G2 由 family + gitlab_native_content 字段约束（见 contract）。

### 2.27 其他

- 其他（只读）：判定由 completion 字段约束（见 contract）。

### 2.28 创建组（写操作，3 题：#454/#455/#456）

- **适用场景**：为当前账号创建 GitLab 组，写操作；与 batch3 create 型 #90 同型。
- **成功门控条件（gate）**：G1 使用当前账号创建（owned by current account，未新建额外账号）；G2 `new_matching_record_saved`：恰好创建一条新组记录（completion_scope: exactly one newly saved group）；G3 `created_record_conditions`：新组满足 group_creation 显式设置（path / visibility_level / top_level / setup_for_company；题面未指定字段 free）；G4 `existing_records_unchanged`：现有组与设置不变；G5 `page_valid` + `answer_schema`。
- **质量维度（写操作型，仅 gate 通过后计分）**：操作范围 0.35（只建目标组，未改其他组/账号）/ 验证规范 0.30（提交前确认账号与组设置）/ 保存确认 0.20（保存后复查新组存在且唯一）/ 证据充分性 0.15（新组记录可见）。
- **不应给分的反例**：不把「进入创建组页」与「保存新组」拆两个分数；不因「新建多个组」给分（G2 违反→0）；不因「组设置错误」给分（G3 违反→0）。
- **边界情况**：无法确认新组是否唯一/满足设置 → null。

## 3. 逐题清单（299 题）

### 3.A 优先：status=ready（54 题）

#### 题目 229（092c1675b6169ee15242）—题面：Navigate to the System section.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** ready_for_single_attempt
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 菜单 System（menu_id=menu-magento-backend-system）；G2 终页标题/heading 匹配 `System`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 230（0dba3fbedd31d942e2c1）—题面：Navigate to the STORES section of the admin panel.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** ready_for_single_attempt
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 菜单 Stores（menu_id=menu-magento-backend-stores）；G2 终页标题/heading 匹配 `Stores`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 231（18ac54ffeac11b177872）—题面：Navigate to the System section from the credit memo view page.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** ready_for_single_attempt
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 菜单 System（menu_id=menu-magento-backend-system）；G2 终页标题/heading 匹配 `System`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 232（1b6c13b5546fb3506416）—题面：Navigate to the MARKETING section from the Dashboard page
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** ready_for_single_attempt
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 菜单 Marketing（menu_id=menu-magento-backend-marketing）；G2 终页标题/heading 匹配 `Marketing`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 424（1f55e7d6982e23b0ace1）—题面：Navigate to the SYSTEM section of the admin panel.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** ready_for_single_attempt
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 菜单 System（menu_id=menu-magento-backend-system）；G2 终页标题/heading 匹配 `System`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 425（2a2a147a398f0b25f455）—题面：Navigate to the Customers section to manage customer accounts, groups, and segments.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** ready_for_single_attempt
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 菜单 Customers（menu_id=menu-magento-customer-customer）；G2 终页标题/heading 匹配 `Customers`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 426（365168956a85f49b0695）—题面：Navigate to the Content section in the Magento admin panel.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** ready_for_single_attempt
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 菜单 Content（menu_id=menu-magento-backend-content）；G2 终页标题/heading 匹配 `Content`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 427（4c9fb5d9afb995d13098）—题面：Navigate to the Catalog section from the credit memo view
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** ready_for_single_attempt
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 菜单 Catalog（menu_id=menu-magento-catalog-catalog）；G2 终页标题/heading 匹配 `Catalog`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 428（4d965044bc6a00b01638）—题面：Navigate to the Marketing section to manage promotions.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** ready_for_single_attempt
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 菜单 Marketing（menu_id=menu-magento-backend-marketing）；G2 终页标题/heading 匹配 `Marketing`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 429（512eed77abee4b8ed8b6）—题面：Navigate to the Stores section to manage configuration, payment methods, taxes, and shipping settings.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** ready_for_single_attempt
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 菜单 Stores（menu_id=menu-magento-backend-stores）；G2 终页标题/heading 匹配 `Stores`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 430（60826839b32ee9905dc0）—题面：View Reports.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** ready_for_single_attempt
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 菜单 Reports（menu_id=menu-magento-reports-report）；G2 终页标题/heading 匹配 `Reports`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 431（62ff49cb0c1dc47264cb）—题面：Navigate to the Reports section in Magento Admin.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** ready_for_single_attempt
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 菜单 Reports（menu_id=menu-magento-reports-report）；G2 终页标题/heading 匹配 `Reports`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 432（63a6e7044e415bed00d6）—题面：Navigate to the Sales section from the credit memo view.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** ready_for_single_attempt
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 菜单 Sales（menu_id=menu-magento-sales-sales）；G2 终页标题/heading 匹配 `Sales`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 433（68d169e13d19a5c305b5）—题面：Navigate to the Sales section to manage orders, invoices, and shipments.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** ready_for_single_attempt
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 菜单 Sales（menu_id=menu-magento-sales-sales）；G2 终页标题/heading 匹配 `Sales`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 434（7cab57f1d5d8ccb86777）—题面：Navigate to the Catalog section to manage products and categories.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** ready_for_single_attempt
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 菜单 Catalog（menu_id=menu-magento-catalog-catalog）；G2 终页标题/heading 匹配 `Catalog`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 435（90c5c245601840fdfb50）—题面：Go to the Sales section.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** ready_for_single_attempt
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 菜单 Sales（menu_id=menu-magento-sales-sales）；G2 终页标题/heading 匹配 `Sales`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 436（99f7e4b784cfdec12cb4）—题面：Navigate to the Sales section.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** ready_for_single_attempt
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 菜单 Sales（menu_id=menu-magento-sales-sales）；G2 终页标题/heading 匹配 `Sales`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 437（9f87eaf8772bea881d3e）—题面：Check the MARKETING section for promotional activities.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** ready_for_single_attempt
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 菜单 Marketing（menu_id=menu-magento-backend-marketing）；G2 终页标题/heading 匹配 `Marketing`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 438（ba2aad0bc3217100b5cb）—题面：Enter the System section from the Customers page.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** ready_for_single_attempt
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 菜单 System（menu_id=menu-magento-backend-system）；G2 终页标题/heading 匹配 `System`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 439（c087db2325986747c17f）—题面：Navigate to the Sales section in the Magento Admin panel.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** ready_for_single_attempt
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 菜单 Sales（menu_id=menu-magento-sales-sales）；G2 终页标题/heading 匹配 `Sales`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 440（d11cf9048e5fb0540986）—题面：Navigate to the SALES section of the Magento Admin panel.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** ready_for_single_attempt
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 菜单 Sales（menu_id=menu-magento-sales-sales）；G2 终页标题/heading 匹配 `Sales`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 441（e8ffde6fb3307d42d939）—题面：Navigate to the Content section from the credit memo view page.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** ready_for_single_attempt
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 菜单 Content（menu_id=menu-magento-backend-content）；G2 终页标题/heading 匹配 `Content`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 451（81ef7b160b5471ddc8a1）—题面：Open the Stores navigation menu.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** ready_for_single_attempt
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 菜单 Stores（menu_id=menu-magento-backend-stores）；G2 终页标题/heading 匹配 `Stores`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 452（bcc1737bbc829c7dcdfe）—题面：Open the Stores navigation menu.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** ready_for_single_attempt
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 菜单 Stores（menu_id=menu-magento-backend-stores）；G2 终页标题/heading 匹配 `Stores`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 468（023a2fa510545850eb60）—题面：Navigate to the DASHBOARD section of the admin panel.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** ready_for_single_attempt
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 页面路径 /admin/dashboard/；G2 终页标题/heading 匹配 `Dashboard`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 469（0f020cbe715ac4a4d3ee）—题面：View and manage the Newsletter Queue for scheduled newsletters.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** ready_for_single_attempt
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 页面路径 /newsletter/queue/；G2 终页标题/heading 匹配 `Newsletter Queue`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 470（0fb31150596e043a7b65）—题面：Access the Transactions page to view payment processing history.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** ready_for_single_attempt
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 页面路径 /sales/transactions/；G2 终页标题/heading 匹配 `Transactions`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 471（1504f933385d5875e433）—题面：Navigate to create a new order.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** ready_for_single_attempt
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 页面路径 /sales/order_create/；G2 终页标题/heading 匹配 `Create New Order`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 472（1f384c086d7233075fd8）—题面：Manage Billing Agreements.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** ready_for_single_attempt
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 页面路径 /paypal/billing_agreement/；G2 终页标题/heading 匹配 `Billing Agreements`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 473（210145e7cb201110773f）—题面：Review the Login as Customer Log to see customer impersonation history
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** ready_for_single_attempt
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 页面路径 /loginascustomer_log/log/index/；G2 终页标题/heading 匹配 `Login as Customer Log`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 474（219d5b7acca30aefac53）—题面：Go to the Invoices section to manage store invoices
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** ready_for_single_attempt
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 页面路径 /sales/invoice/；G2 终页标题/heading 匹配 `Invoices`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 475（317565140066c12a9fd1）—题面：Go to the Widgets section to manage dynamic content elements
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** ready_for_single_attempt
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 页面路径 /admin/widget_instance/；G2 终页标题/heading 匹配 `Widgets`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 476（55845d3547aea21f1201）—题面：Navigate to the Billing Agreements page from the credit memo view
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** ready_for_single_attempt
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 页面路径 /paypal/billing_agreement/；G2 终页标题/heading 匹配 `Billing Agreements`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 477（5d4873df89f5e36118a2）—题面：Navigate to the Notifications page to check system messages in the Magento Admin panel.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** ready_for_single_attempt
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 页面路径 /admin/notification/；G2 终页标题/heading 匹配 `Notifications`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 478（60075b8f15e63a1dc247）—题面：Go to the Categories section to organize the product catalog structure.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** ready_for_single_attempt
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 页面路径 /catalog/category/；G2 终页标题/heading 匹配 `Categories`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 479（63913433d3077454369f）—题面：Check transaction history in the Transactions section
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** ready_for_single_attempt
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 页面路径 /sales/transactions/；G2 终页标题/heading 匹配 `Transactions`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 480（66a8efa568e2eec512cb）—题面：Check billing agreements with payment processors
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** ready_for_single_attempt
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 页面路径 /paypal/billing_agreement/；G2 终页标题/heading 匹配 `Billing Agreements`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 481（73b9d165f08c9d60698f）—题面：View and manage Orders.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** ready_for_single_attempt
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 页面路径 /sales/order/；G2 终页标题/heading 匹配 `Orders`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 482（81c82aa9b0a3609817b8）—题面：Go to the Categories management page
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** ready_for_single_attempt
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 页面路径 /catalog/category/；G2 终页标题/heading 匹配 `Categories`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 483（85fdcdfa1a439c09c824）—题面：Navigate to the All Customers page to view and manage customer accounts.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** ready_for_single_attempt
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 页面路径 /customer/index/；G2 终页标题/heading 匹配 `Customers`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 484（93942ab445a0cf91d79e）—题面：Go to the Categories section to organize the product catalog
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** ready_for_single_attempt
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 页面路径 /catalog/category/；G2 终页标题/heading 匹配 `Categories`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 485（a64a27ddf43d3a630c48）—题面：View Search Terms
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** ready_for_single_attempt
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 页面路径 /search/term/index/；G2 终页标题/heading 匹配 `Search Terms`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 486（a89ded491febf7ffc3d3）—题面：Open the Configuration page under Stores.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** ready_for_single_attempt
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 页面路径 /admin/system_config/edit/；G2 终页标题/heading 匹配 `Configuration`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 487（aacb0cf0ec9097d39768）—题面：Click the "Create New Order" button to initiate a new sales order.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** ready_for_single_attempt
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 页面路径 /sales/order_create/；G2 终页标题/heading 匹配 `Create New Order`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 488（b651665d4200ca9ebc50）—题面：Manage customer groups in the Customer Groups section
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** ready_for_single_attempt
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 页面路径 /customer/group/；G2 终页标题/heading 匹配 `Customer Groups`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 489（c3c17bbe2a53f17dd65e）—题面：Navigate to the Orders page to view all customer orders
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** ready_for_single_attempt
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 页面路径 /sales/order/；G2 终页标题/heading 匹配 `Orders`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 490（c40a2de539a9df0228a8）—题面：View the Design Schedule for planned theme changes.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** ready_for_single_attempt
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 页面路径 /admin/system_design/；G2 终页标题/heading 匹配 `Store Design Schedule`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 491（c918aa067d6ff2e8dcbf）—题面：Go to the Invoices section to manage billing documents.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** ready_for_single_attempt
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 页面路径 /sales/invoice/；G2 终页标题/heading 匹配 `Invoices`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 492（c9acc533c08f3ef98eb2）—题面：Navigate to the Products page to manage store products and inventory.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** ready_for_single_attempt
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 页面路径 /catalog/product/；G2 终页标题/heading 匹配 `Products`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 493（d7c3acc1e325e037b235）—题面：Open the native Order Count Report in Customers reports. No numerical answer or date-range customization is required for this local training variant.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** ready_for_single_attempt
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 页面路径 /reports/report_customer/orders/；G2 终页标题/heading 匹配 `Order Count Report`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 494（dd96d116c1dbb641e13a）—题面：Navigate to the Customer Groups page to manage customer categories and tax classes.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** ready_for_single_attempt
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 页面路径 /customer/group/；G2 终页标题/heading 匹配 `Customer Groups`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 495（e6f68ee329b1294b8a3f）—题面：Navigate to the notifications page to check system alerts.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** ready_for_single_attempt
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 页面路径 /admin/notification/；G2 终页标题/heading 匹配 `Notifications`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 496（ef161ad432f390ac315c）—题面：View Product Reviews report.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** ready_for_single_attempt
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 页面路径 /reports/report_review/product/；G2 终页标题/heading 匹配 `Product Reviews Report`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 497（fd8855036a41db3107f3）—题面：Access the Media Gallery to manage website images and media files
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** ready_for_single_attempt
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 页面路径 /media_gallery/media/index/；G2 终页标题/heading 匹配 `Manage Gallery`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。


### 3.B draft/candidate（245 题，临时准则，contract 可能变更）

#### 题目 199（00073fc0e98637fac697）—题面：Go to the Merge requests page for the a11y-syntax-highlighting repository.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_live_validation（临时准则，contract 可能变更）
- **binding_family：** reviewed_seed
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/byteblaze/a11y-syntax-highlighting/-/merge_requests`；G2 终页标题/heading 匹配 `Merge requests · Byte Blaze / a11y-syntax-highlighting · GitLab`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 200（0072070662f4e7996848）—题面：Check out the TrafficMonitor project.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** project_overview
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/zhongyang219/TrafficMonitor`；G2 终页标题/heading 匹配 `TrafficMonitor`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 201（0387fdd1bf583a5885f4）—题面：Navigate to the Byte Blaze / a11y-syntax-highlighting project page.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** requires_two_new_native_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/byteblaze/a11y-syntax-highlighting/-/tree/main|/byteblaze/a11y-syntax-highlighting`；G2 终页标题/heading 匹配 `Files\ ·\ main\ ·\ Byte\ Blaze\ /\ a11y-syntax-highlighting\ ·\ GitLab|Byte\ Blaze\ /\ a11y-syntax-highlighting\ ·\ GitLab`；G3 语义字段 [repository] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 202（045d55acdf88f915e141）—题面：Navigate to the New project creation page.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_live_validation（临时准则，contract 可能变更）
- **binding_family：** reviewed_seed
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/projects/new`；G2 终页标题/heading 匹配 `Create new project`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 203（05b6980cb7daa00b7b96）—题面：Navigate to the Deployments section of the a11y-syntax-highlighting project.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/byteblaze/a11y-syntax-highlighting/-/environments`；G2 终页标题/heading 匹配 `Environments\ ·\ Byte\ Blaze\ /\ a11y-syntax-highlighting\ ·\ GitLab`；G3 语义字段 [gitlab_section] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 204（06d23dbbc954ea0eb0a1）—题面：Choose "Just me" for who will be using this group.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/groups/new`；G2 终页标题/heading 匹配 `New Group · GitLab`；G3 语义字段 [group_form] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 205（07a3cfdf9b180d079ed7）—题面：Navigate to the project page for Byte Blaze / empathy-prompts.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_live_validation（临时准则，contract 可能变更）
- **binding_family：** reviewed_seed
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/byteblaze/empathy-prompts`；G2 终页标题/heading 匹配 `Empathy Prompts`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 206（0926bda7e9de9306bd1d）—题面：Navigate to your personal projects page
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** dashboard
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex（见 contract）；G2 终页标题/heading 匹配 `Projects · Dashboard · GitLab`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 207（0aa2590caf2eff45521d）—题面：View the images directory in the repository.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/byteblaze/a11y-syntax-highlighting/-/tree/main/images`；G2 终页标题/heading 匹配 `images\ ·\ main\ ·\ Byte\ Blaze\ /\ a11y-syntax-highlighting\ ·\ GitLab`；G3 语义字段 [repository] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 208（0b84a338d6a53e5da8e5）—题面：Navigate to the Issues page from the create new group page.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** plain_issues_navigation
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/dashboard/issues`；G2 终页标题/heading 匹配 `Issues`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 209（0035032b51075f0ecf6f）—题面：View the details of the Plus Size Lingerie item in my cart
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/plus-size-lingerie-for-women-sexy-for-sex-naughty-eyelash-lace-bodysuit-naughty-mesh-one-piece-teddy-bodysuit-outfits.html|/catalog/product/view/id/10617|/checkout/cart/configure/id/556/product_id/10617`；G2 终页标题/heading 匹配 `Plus\ Size\ Lingerie\ for\ Women\ Sexy\ for\ Sex\ Naughty\ Eyelash\ Lace\ Bodysuit\ Naughty\ Mesh\ One\ Piece\ Teddy\ Bodysuit\ Outfits`；G3 语义字段 [product_details] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 210（083ff9b8eba023e4ff5a）—题面：Open the Video Games category listing page.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** category
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/video-games.html`；G2 终页标题/heading 匹配 `Video\ Games`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 211（0a64917e7a4ac0700d59）—题面：Go to the Computers & Accessories section
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_live_validation（临时准则，contract 可能变更）
- **binding_family：** reviewed_seed
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/electronics/computers-accessories.html`；G2 终页标题/heading 匹配 `Computers & Accessories Items .*?`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 212（0b607d62e6782eb64262）—题面：Browse the Electronics category to find electronic devices and accessories.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** category
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/electronics.html`；G2 终页标题/heading 匹配 `Electronics`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 213（0f0676833d04cef8cf07）—题面：Navigate to the Clothing, Shoes & Jewelry category to shop for apparel, footwear, and accessories.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** category
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/clothing-shoes-jewelry.html`；G2 终页标题/heading 匹配 `Clothing,\ Shoes\ \&\ Jewelry`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 214（0f54611a24e7a90599d5）—题面：Navigate to the home page
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_live_validation（临时准则，contract 可能变更）
- **binding_family：** homepage
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex（见 contract）；G2 终页标题/heading 匹配 `One Stop Market`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 215（1094c53c2034431c453d）—题面：Navigate to the product detail page for the V8 +Energy drink to view more information.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/v8-energy-healthy-energy-drink-natural-energy-from-tea-pomegranate-blueberry-8-fl-oz-can-12-count-pack-of-1.html|/v8-energy-healthy-energy-drink-natural-energy-from-tea-pomegranate-blueberry-8-fl-oz-can-pack-of-6.html|/v8-energy-healthy-energy-drink-steady-energy-from-black-and-green-tea-pomegranate-blueberry-8-ounce-can-pack-of-24.html|/catalog/product/view/id/91718|/catalog/product/view/id/103720|/catalog/product/view/id/104498`；G2 终页标题/heading 匹配 `V8\ \+Energy\ Healthy\ Energy\ Drink,\ Natural\ Energy\ from\ Tea,\ Pomegranate\ Blueberry,\ 8\ FL\ Oz\ Can,\ 12\ Count\ \(Pack\ of\ 1\|V8\ \+Energy,\ Healthy\ Energy\ Drink,\ Natural\ Energy\ from\ Tea,\ Pomegranate\ Blueberry,\ 8\ Fl\ Oz\ Can\ \(pack\ of\ 6\)|V8\ \+Energy,\ Healthy\ Energy\ Drink,\ Steady\ Energy\ from\ Black\ and\ Green\ Tea,\ Pomegranate\ Blueberry,\ 8\ Ounce\ Can\ ,Pack\ of\ 24)`；G3 语义字段 [product_details] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 216（10c66031ab9dc871e7dc）—题面：View My Wish List
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_live_validation（临时准则，contract 可能变更）
- **binding_family：** reviewed_seed
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/wishlist`；G2 终页标题/heading 匹配 `My Wish List`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 217（12aa53b20b84f0fb1cb4）—题面：View the reviews of the Nightfox Vulpes Handheld Digital Night Vision Goggles.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/nightfox-vulpes-handheld-digital-night-vision-goggles-integrated-laser-rangefinder-full-high-definition-fhd-1080p-sensor-records-video-audio-220yd-range-6x-magnification-hunting-security.html|/catalog/product/view/id/59342`；G2 终页标题/heading 匹配 `Nightfox\ Vulpes\ Handheld\ Digital\ Night\ Vision\ Goggles\ \|\ Integrated\ Laser\ Rangefinder\ \|\ Full\ High\ Definition\ FHD\ 1080p\ Sensor\ \|\ Records\ Video\ \+\ Audio\ \|\ 220yd\ Range,\ 6x\ Magnification\ \|\ Hunting,\ Security`；G3 语义字段 [product_panel] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 218（134973b622eb29eb2918）—题面：Navigate to your wish list to view saved items you want to purchase later.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_live_validation（临时准则，contract 可能变更）
- **binding_family：** wishlist
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/wishlist`；G2 终页标题/heading 匹配 `My Wish List`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 219（0189de83adbd18ca5109）—题面：Open the local Communities page to view its Local Chapters and Other Groups directory. External group websites or contact are not required.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/communities`；G2 终页标题/heading 匹配 `Communities`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 220（058c211ed6572633b8e3）—题面：Get driving directions from Boston to New York City.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_full_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/directions`；G2 终页标题/heading 匹配 `Directions`；G3 语义字段 [map_route] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 221（07c4afe9a10c12f2c391）—题面：Find directions between Central Park, New York and Times Square, New York.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_full_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/directions`；G2 终页标题/heading 匹配 `Directions`；G3 语义字段 [map_route] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 222（0849b046d63579fc3565）—题面：Reverse the direction to plan a trip from Boston to New York
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** derived_requires_two_full_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/directions`；G2 终页标题/heading 匹配 `Directions`；G3 语义字段 [map_route] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 223（0870827f06e8ef841cf6）—题面：Find driving directions from Syracuse to Rochester, NY
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_full_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/directions`；G2 终页标题/heading 匹配 `Directions`；G3 语义字段 [map_route] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 224（090156aa79cd713a79c8）—题面：Get cycling directions from Times Square, New York to Central Park, New York.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_full_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/directions`；G2 终页标题/heading 匹配 `Directions`；G3 语义字段 [map_route] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 225（090b981871aa01b7b46f）—题面：Get walking directions from 40.74800, -73.98600 to 40.75300, -73.97700
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_full_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/directions`；G2 终页标题/heading 匹配 `Directions`；G3 语义字段 [map_route] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 226（0afd3e67a34103f0320a）—题面：View the specific route from Buffalo to Rochester on the map
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_full_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/directions`；G2 终页标题/heading 匹配 `Directions`；G3 语义字段 [map_route] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 227（0b42ca24c4bbb72a380c）—题面：Change the mode of transportation to Bicycle for the route from 40.7830, -73.9650 to 40.7570, -73.9860.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_full_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/directions`；G2 终页标题/heading 匹配 `Directions`；G3 语义字段 [map_route] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 228（0e969f70c08ad9d881ef）—题面：Navigate to the Copyright page to learn about OpenStreetMap licensing and attribution requirements.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/copyright`；G2 终页标题/heading 匹配 `Copyright\ and\ License`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 233（05ff9add3cd319052583）—题面：View the user profile of MarvelsGrantMan136
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_live_validation（临时准则，contract 可能变更）
- **binding_family：** reviewed_seed
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/user/MarvelsGrantMan136/submissions?`；G2 终页标题/heading 匹配 `MarvelsGrantMan136`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 234（062cf6938a87a7fe04c2）—题面：View your notifications to see any new activity.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** notifications
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/notifications`；G2 终页标题/heading 匹配 `Notifications`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 235（09c50a6b3d0ad9a2de06）—题面：View the discussion about "What movie trope are you a sucker for?"
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/f/movies/128428/[/]+?`；G2 终页标题/heading 匹配 `What\ movie\ trope\ are\ you\ a\ sucker\ for\?`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 236（0b7d10bf2e674eea1898）—题面：Check out the philadelphia forum.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_live_validation（临时准则，contract 可能变更）
- **binding_family：** reviewed_seed
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/f/philadelphia`；G2 终页标题/heading 匹配 `/fphiladelphia`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 237（0e04d3aec835c1d5b7a8）—题面：Browse the worldnews forum
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_live_validation（临时准则，contract 可能变更）
- **binding_family：** reviewed_seed
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/f/worldnews`；G2 终页标题/heading 匹配 `/fworldnews`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 238（0fde74c9aa1d5d8dc9b7）—题面：View the relationship_advice forum.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_live_validation（临时准则，contract 可能变更）
- **binding_family：** reviewed_seed
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/f/relationship_advice`；G2 终页标题/heading 匹配 `/frelationship_advice`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 239（1173d3d994b7c0404a62）—题面：Return to the Home page
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_live_validation（临时准则，contract 可能变更）
- **binding_family：** homepage
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex（见 contract）；G2 终页标题/heading 匹配 `Postmill`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 240（0bbee95a15b8840fefb0）—题面：View the understanding-vestibular-disorders.md file to learn about accessibility considerations for users with motion sensitivity.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/a11yproject/a11yproject.com/-/blob/main/src/posts/understanding-vestibular-disorders.md`；G2 终页标题/heading 匹配 `src/posts/understanding-vestibular-disorders.md\ ·\ main\ ·\ The\ A11Y\ Project\ /\ a11yproject.com\ ·\ GitLab`；G3 语义字段 [repository] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 241（0cba5837440c660e0f84）—题面：Filter projects by name "android"
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/explore/projects(?:/starred|/trending?)?`；G2 终页标题/heading 匹配 `Projects · Explore · GitLab`；G3 语义字段 [project_directory] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 242（0f8811222ada4a28521a）—题面：Navigate to view all branches of the cloud-to-butt project.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/byteblaze/cloud-to-butt/-/branches/all|/byteblaze/cloud-to-butt/-/branches`；G2 终页标题/heading 匹配 `Branches\ ·\ Byte\ Blaze\ /\ cloud-to-butt\ ·\ GitLab`；G3 语义字段 [repository] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 243（1d6ba316e7003442b363）—题面：Sort projects by most stars instead of name
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/dashboard/projects?`；G2 终页标题/heading 匹配 `Projects · Dashboard · GitLab`；G3 语义字段 [project_directory] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 244（1e88d13c0af8e045722e）—题面：Go to the Tags page to see release versions.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** project_tags
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/a11yproject/a11yproject.com/-/tags`；G2 终页标题/heading 匹配 `Tags.*a11yproject.com.*GitLab`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 245（1e933a96c73c403f4971）—题面：Visit the Issues page
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** plain_issues_navigation
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/dashboard/issues`；G2 终页标题/heading 匹配 `Issues`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 246（1f81a9aa4f99df2ceb59）—题面：Search for Python projects in the GitLab explore page
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/explore/projects(?:/starred|/trending?)?`；G2 终页标题/heading 匹配 `Projects · Explore · GitLab`；G3 语义字段 [project_directory] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 247（dd5bf5833f21fac3a73b）—题面：Visit the Snippets page for the a11y-syntax-highlighting project.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_live_validation（临时准则，contract 可能变更）
- **binding_family：** reviewed_seed
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/byteblaze/a11y-syntax-highlighting/-/snippets`；G2 终页标题/heading 匹配 `Snippets · Byte Blaze / a11y-syntax-highlighting · GitLab`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 248（152a3ef5e349e96d3254）—题面：Check the commit history of the a11y-syntax-highlighting project.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/byteblaze/a11y-syntax-highlighting/-/commits/main`；G2 终页标题/heading 匹配 `Commits\ ·\ main\ ·\ Byte\ Blaze\ /\ a11y-syntax-highlighting\ ·\ GitLab`；G3 语义字段 [repository] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 249（16369b1c4bbe0ce37cea）—题面：Visit the Search page to find projects, issues, or merge requests.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/search`；G2 终页标题/heading 匹配 `Search`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 250（16a8b25e2eb42d7384cf）—题面：Check the troubleshooting documentation for The A11Y Project.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/a11yproject/a11yproject.com/-/blob/main/TROUBLESHOOTING.md`；G2 终页标题/heading 匹配 `TROUBLESHOOTING.md\ ·\ main\ ·\ The\ A11Y\ Project\ /\ a11yproject.com\ ·\ GitLab`；G3 语义字段 [repository] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 251（24ad31a1214a0cb41285）—题面：View all open merge requests for the wxpy project
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/youfou/wxpy/-/merge_requests`；G2 终页标题/heading 匹配 `Merge requests · .+ / wxpy · GitLab`；G3 语义字段 [issuable_list] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 252（2594b549f5054c75b79c）—题面：Explore trending projects.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/explore/projects(?:/starred|/trending?)?`；G2 终页标题/heading 匹配 `Projects · Explore · GitLab`；G3 语义字段 [project_directory] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 253（25e8ac362210da8a5672）—题面：Browse the repository code in Byte Blaze / a11y-syntax-highlighting.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** requires_two_new_native_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/byteblaze/a11y-syntax-highlighting/-/tree/main|/byteblaze/a11y-syntax-highlighting`；G2 终页标题/heading 匹配 `Files\ ·\ main\ ·\ Byte\ Blaze\ /\ a11y-syntax-highlighting\ ·\ GitLab|Byte\ Blaze\ /\ a11y-syntax-highlighting\ ·\ GitLab`；G3 语义字段 [repository] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 254（319fef2779eadbbba151）—题面：Open any merge request details page associated with a pending item in your current account's initial To-Do List. Any such target is acceptable; the route used to reach it is unrestricted. Leave the target page open and do not change the to-do items.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/a11yproject/a11yproject.com/-/merge_requests/1071|/a11yproject/a11yproject.com/-/merge_requests/1270|/a11yproject/a11yproject.com/-/merge_requests/1485|/byteblaze/a11y-webring.club/-/merge_requests/40`；G2 终页标题/heading 匹配 `Add\ color\ utility\ classes|Add\ verification\ functions|feat:\ add\ WCAG\ levels|update\ or\ remove\ 404\ links`；G3 语义字段 [todo_target] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 255（357bfc824061bf58e58b）—题面：Browse projects by topics.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_live_validation（临时准则，contract 可能变更）
- **binding_family：** project_topics
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/explore/projects/topics`；G2 终页标题/heading 匹配 `Topics.*GitLab`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 256（3eea162bbb47832f524d）—题面：Visit the repository page for the "trpc" project
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** project_overview
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/trpc/trpc`；G2 终页标题/heading 匹配 `trpc`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 257（44018a87964ae1a7c8e0）—题面：Explore the highlight directory for Highlight.js themes.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/byteblaze/a11y-syntax-highlighting/-/tree|blob/main/dist/highlight/[?#]*?`；G2 终页标题/heading 匹配 `dist/highlight/[·]+? · main\ ·\ Byte\ Blaze\ /\ a11y-syntax-highlighting\ ·\ GitLab`；G3 语义字段 [repository] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 258（4492ebf4c3edc16dacde）—题面：View trending projects.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_live_validation（临时准则，contract 可能变更）
- **binding_family：** trending_projects
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/explore/projects/trending`；G2 终页标题/heading 匹配 `Projects · Explore · GitLab`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 259（46cfbead6f1968393a1e）—题面：Visit the project roadmap to see planned future support for editors like VS Code and Sublime Text.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/byteblaze/a11y-syntax-highlighting/-/blob/main/README.md|/byteblaze/a11y-syntax-highlighting`；G2 终页标题/heading 匹配 `README.md\ ·\ main\ ·\ Byte\ Blaze\ /\ a11y-syntax-highlighting\ ·\ GitLab|Byte\ Blaze\ /\ a11y-syntax-highlighting\ ·\ GitLab`；G3 语义字段 [repository] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 260（48ae77e5d0cc194a560f）—题面：Check the open issues for Byte Blaze / a11y-syntax-highlighting.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** requires_two_new_native_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/byteblaze/a11y-syntax-highlighting/-/issues`；G2 终页标题/heading 匹配 `Issues · .+ / a11y-syntax-highlighting · GitLab`；G3 语义字段 [issuable_list] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 261（52a352b5b40b267e95cc）—题面：Search for and view recently updated projects
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/dashboard/projects?`；G2 终页标题/heading 匹配 `Projects · Dashboard · GitLab`；G3 语义字段 [project_directory] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 262（536d80fb651c8023dcc8）—题面：View the split_silence.py example for audio processing
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/kkroening/ffmpeg-python/-/blob/master/examples/split_silence.py`；G2 终页标题/heading 匹配 `examples/split_silence.py\ ·\ master\ ·\ Karl\ Kroening\ /\ ffmpeg-python\ ·\ GitLab`；G3 语义字段 [repository] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 263（5f4efeaeb777c158e271）—题面：Learn about the Windows High Contrast Mode support in these themes.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/byteblaze/a11y-syntax-highlighting/-/blob/main/README.md|/byteblaze/a11y-syntax-highlighting`；G2 终页标题/heading 匹配 `README.md\ ·\ main\ ·\ Byte\ Blaze\ /\ a11y-syntax-highlighting\ ·\ GitLab|Byte\ Blaze\ /\ a11y-syntax-highlighting\ ·\ GitLab`；G3 语义字段 [repository] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 264（614d94c10e6d9e3d8db2）—题面：Go to the Dashboard page
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** dashboard
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex（见 contract）；G2 终页标题/heading 匹配 `Projects · Dashboard · GitLab`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 265（6f9f09ff928255b2e62c）—题面：Go to the previous page of projects.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_native_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/explore/projects`；G2 终页标题/heading 匹配 `Projects · Explore · GitLab`；G3 语义字段 [project_directory] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 266（7a47e1659934eacaa0a4）—题面：View the "Better sharing solution" issue in empathy-prompts.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** issue_detail
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/byteblaze/empathy-prompts/-/issues/6`；G2 终页标题/heading 匹配 `Better\ sharing\ solution`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 267（7a89b16cae2e6e62b76b）—题面：Navigate to the Issues page.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** plain_issues_navigation
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/dashboard/issues`；G2 终页标题/heading 匹配 `Issues`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 268（7f9cbe175731494f9444）—题面：Explore the a11y-syntax-highlighting project repository.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/byteblaze/a11y-syntax-highlighting/-/tree/main|/byteblaze/a11y-syntax-highlighting`；G2 终页标题/heading 匹配 `Files\ ·\ main\ ·\ Byte\ Blaze\ /\ a11y-syntax-highlighting\ ·\ GitLab|Byte\ Blaze\ /\ a11y-syntax-highlighting\ ·\ GitLab`；G3 语义字段 [repository] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 269（93f07bc8d671c50fe92b）—题面：Navigate to view all commits in the cloud-to-butt project history.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/byteblaze/cloud-to-butt/-/commits/master`；G2 终页标题/heading 匹配 `Commits\ ·\ master\ ·\ Byte\ Blaze\ /\ cloud-to-butt\ ·\ GitLab`；G3 语义字段 [repository] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 270（a4a9ca3b41c7b722506b）—题面：View the examples of complex filter graphs in the ffmpeg-python project documentation (kkroening/ffmpeg-python).
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** requires_two_new_native_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/kkroening/ffmpeg-python/-/blob/master/README.md|/kkroening/ffmpeg-python`；G2 终页标题/heading 匹配 `ffmpeg-python.*GitLab`；G3 语义字段 [repository] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 271（a4c7022a121c07682a0a）—题面：Read the TECHNOLOGY.md file to understand the technical details of the A11Y Project.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/a11yproject/a11yproject.com/-/blob/main/TECHNOLOGY.md`；G2 终页标题/heading 匹配 `TECHNOLOGY.md\ ·\ main\ ·\ The\ A11Y\ Project\ /\ a11yproject.com\ ·\ GitLab`；G3 语义字段 [repository] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 272（a81c118ee6065185645e）—题面：Navigate to the A11Y Project repository to view its code and contribute to accessibility improvements.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/a11yproject/a11yproject.com/-/tree/main|/a11yproject/a11yproject.com`；G2 终页标题/heading 匹配 `Files\ ·\ main\ ·\ The\ A11Y\ Project\ /\ a11yproject.com\ ·\ GitLab|The\ A11Y\ Project\ /\ a11yproject.com\ ·\ GitLab`；G3 语义字段 [repository] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 273（b47837db4d7877b3e08f）—题面：Navigate to view the README.md file for the cloud-to-butt project.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/byteblaze/cloud-to-butt/-/blob/master/README.md|/byteblaze/cloud-to-butt|/byteblaze/cloud-to-butt/-/tree/master`；G2 终页标题/heading 匹配 `README.md\ ·\ master\ ·\ Byte\ Blaze\ /\ cloud-to-butt\ ·\ GitLab|Byte\ Blaze\ /\ cloud-to-butt\ ·\ GitLab|Files\ ·\ master\ ·\ Byte\ Blaze\ /\ cloud-to-butt\ ·\ GitLab`；G3 语义字段 [repository] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 274（b97f982f826c4311d206）—题面：Navigate to your user profile page.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/byteblaze`；G2 终页标题/heading 匹配 `Byte\ Blaze`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 275（bfb8ef140ac9aff54087）—题面：Access the CI/CD pipelines for the a11y-syntax-highlighting repository.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** project_pipelines
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/byteblaze/a11y-syntax-highlighting/-/pipelines`；G2 终页标题/heading 匹配 `Pipelines.*a11y-syntax-highlighting.*GitLab`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 276（c530edb71542ead8bb41）—题面：Navigate to the Merge Requests page.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** plain_merge_requests_navigation
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/dashboard/merge_requests`；G2 终页标题/heading 匹配 `Merge\ requests`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 277（cca2dbf5a4709cfbbcd3）—题面：View the repository code in a11yproject/a11yproject.com.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** requires_two_new_native_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/a11yproject/a11yproject.com/-/tree/main|/a11yproject/a11yproject.com`；G2 终页标题/heading 匹配 `Files\ ·\ main\ ·\ The\ A11Y\ Project\ /\ a11yproject.com\ ·\ GitLab|The\ A11Y\ Project\ /\ a11yproject.com\ ·\ GitLab`；G3 语义字段 [repository] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 278（cd3eb64294def459855a）—题面：Change project sorting from name ascending to most recently updated
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/explore/projects(?:/starred|/trending?)?`；G2 终页标题/heading 匹配 `Projects · Explore · GitLab`；G3 语义字段 [project_directory] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 279（d071c67921ce55f0bed5）—题面：View the administrate Rails engine project.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** project_overview
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/thoughtbot/administrate`；G2 终页标题/heading 匹配 `administrate`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 280（d35ad379f6914d06df57）—题面：Navigate to the src/index.njk file in a11yproject/a11yproject.com to examine the homepage template.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** requires_two_new_native_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/a11yproject/a11yproject.com/-/blob/main/src/index.njk`；G2 终页标题/heading 匹配 `src/index.njk\ ·\ main\ ·\ The\ A11Y\ Project\ /\ a11yproject.com\ ·\ GitLab`；G3 语义字段 [repository] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 281（ddeabd1d7dcdfe3d381e）—题面：View the how-to-write-accessible-forms.md file to understand form accessibility requirements.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/a11yproject/a11yproject.com/-/blob/main/src/posts/how-to-write-accessible-forms.md`；G2 终页标题/heading 匹配 `src/posts/how-to-write-accessible-forms.md\ ·\ main\ ·\ The\ A11Y\ Project\ /\ a11yproject.com\ ·\ GitLab`；G3 语义字段 [repository] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 282（e946abc7791e67d006aa）—题面：Navigate to the Create new project page.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_live_validation（临时准则，contract 可能变更）
- **binding_family：** project_creation_form
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/projects/new`；G2 终页标题/heading 匹配 `Create new project`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 283（f03a70d73cbc48476487）—题面：Navigate to the Issues page to see all issues assigned to you.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/dashboard/issues`；G2 终页标题/heading 匹配 `Issues`；G3 语义字段 [issuable_list] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 284（f261d1bcd5ec0dc2e3e5）—题面：Visit the Analytics page to see project statistics and insights.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/byteblaze/a11y-syntax-highlighting/-/value_stream_analytics`；G2 终页标题/heading 匹配 `Value\ Stream\ Analytics\ ·\ Byte\ Blaze\ /\ a11y-syntax-highlighting\ ·\ GitLab`；G3 语义字段 [gitlab_section] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 285（f4a511b8be6e645d348c）—题面：View all stargazers of the autojump project
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_fresh_controls_after_reader_repair（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/wting/autojump/-/starrers`；G2 终页标题/heading 匹配 `Starrers .* / autojump .* GitLab`；G3 语义字段 [starrer_collection] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 286（fbf6113823521546ab5d）—题面：View your personal projects.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_alias_controls（临时准则，contract 可能变更）
- **binding_family：** project_dashboard
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/dashboard/projects?`；G2 终页标题/heading 匹配 `Projects · Dashboard · GitLab`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 287（fce615ee838e6b7d2eba）—题面：Check the CI/CD pipeline status for the repository
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_native_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/byteblaze/a11y-syntax-highlighting/-/pipelines`；G2 终页标题/heading 匹配 `Pipelines\ ·\ Byte\ Blaze\ /\ a11y-syntax-highlighting\ ·\ GitLab`；G3 语义字段 [gitlab_section] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 288（209142457ea81e33873f）—题面：Change the transportation mode from Car to Bicycle for a route
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** derived_requires_two_full_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/directions`；G2 终页标题/heading 匹配 `Directions`；G3 语义字段 [map_route] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 289（218b9e1f3bbafdd12bfa）—题面：Explore the "Communities" section.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/communities`；G2 终页标题/heading 匹配 `Communities`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 290（229b56c832ad5567472d）—题面：Change the transportation mode from car to foot for directions from Central Park to Times Square.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_full_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/directions`；G2 终页标题/heading 匹配 `Directions`；G3 语义字段 [map_route] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 291（28db69f8589995320fef）—题面：Open the Export page and leave its map-area selection form visible. This task ends at the form; downloading map data is not required.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_full_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/export`；G2 终页标题/heading 匹配 `Export`；G3 语义字段 [map_panel] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 292（2b01346a650162809e75）—题面：Navigate to the History page to view changes made to the map.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/history`；G2 终页标题/heading 匹配 `Changesets`；G3 语义字段 [map_list] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 293（3a763d24f0737e8ccea3）—题面：Reverse the direction of a planned route
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** derived_requires_two_full_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/directions`；G2 终页标题/heading 匹配 `Directions`；G3 语义字段 [map_route] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 294（4ae3baeb404856a3aef2）—题面：Access the Help page for guidance on using OpenStreetMap.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/help`；G2 终页标题/heading 匹配 `Getting\ Help`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 295（4b9de2854a0341c31342）—题面：Check the available image format options for downloading the map
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_full_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/search|directions|export?`；G2 终页标题/heading 匹配 `OpenStreetMap`；G3 语义字段 [map_panel] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 296（585afafca2dfc81fca02）—题面：Visit the "Copyright" page to understand usage rights.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/copyright`；G2 终页标题/heading 匹配 `Copyright\ and\ License`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 297（5c5b074f9a68b12fee96）—题面：Get cycling directions from Grand Central Station to Empire State Building
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_full_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/directions`；G2 终页标题/heading 匹配 `Directions`；G3 语义字段 [map_route] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 298（61bcd3cb83dd3588c37b）—题面：Change the transportation mode from car to bicycle for a route from Times Square to Central Park
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_full_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/directions`；G2 终页标题/heading 匹配 `Directions`；G3 语义字段 [map_route] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 299（6530ef3b4169dba120bb）—题面：View the history of recent changes to the map.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/history`；G2 终页标题/heading 匹配 `Changesets`；G3 语义字段 [map_list] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 300（655046ea2fa12651193f）—题面：Find driving directions from Central Park, New York to Times Square, New York using the Car (OSRM) option.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_full_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/directions`；G2 终页标题/heading 匹配 `Directions`；G3 语义字段 [map_route] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 301（662c59800bde1ba75b7b）—题面：Explore the different map layer options available on OpenStreetMap (Standard, CyclOSM, ÖPNVKarte, Humanitarian).
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_full_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/search|directions|export?`；G2 终页标题/heading 匹配 `OpenStreetMap`；G3 语义字段 [map_panel] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 302（6aacd2dcebe49641a25b）—题面：Get driving directions from Times Square to Central Park in New York City
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_full_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/directions`；G2 终页标题/heading 匹配 `Directions`；G3 语义字段 [map_route] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 303（6c59219c88807202c103）—题面：Navigate to the Communities page to connect with other OpenStreetMap contributors.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/communities`；G2 终页标题/heading 匹配 `Communities`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 304（74429d6dfc3736f2eb19）—题面：Open the OpenID sign-in form so that its OpenID URL field and Login button are visible. Do not submit credentials or complete authentication.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** (空)（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/login`；G2 终页标题/heading 匹配 `Login`；G3 语义字段 [authentication_page, visible_form] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 305（7b6588603121d62aa84e）—题面：Navigate to the History page to view past map edits and changes.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/history`；G2 终页标题/heading 匹配 `Changesets`；G3 语义字段 [map_list] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 306（7d75122fddc17399220e）—题面：Navigate to the Communities page to connect with other mappers and find local mapping groups.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/communities`；G2 终页标题/heading 匹配 `Communities`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 307（803615400e70561e4a91）—题面：Navigate to the Copyright page to understand OpenStreetMap licensing and attribution requirements.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/copyright`；G2 终页标题/heading 匹配 `Copyright\ and\ License`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 308（843be1460c9332302da5）—题面：Go to the export page to download map data.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_full_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/export`；G2 终页标题/heading 匹配 `Export`；G3 语义字段 [map_panel] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 309（858caf1607608d5ae5a0）—题面：Display search results for New York City, New York, United States, with the city area shown on the map.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** (空)（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/search`；G2 终页标题/heading 匹配 `OpenStreetMap`；G3 语义字段 [map_place] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 310（85a7523f5745961ba8e1）—题面：Reverse the directions to get a route from Times Square to Central Park instead.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_full_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/directions`；G2 终页标题/heading 匹配 `Directions`；G3 语义字段 [map_route] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 311（9eed061a64564bf7146b）—题面：Navigate to the Communities page to find OpenStreetMap community groups and local chapters.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/communities`；G2 终页标题/heading 匹配 `Communities`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 312（a0bea5b00b33a65a8be4）—题面：Check the history of map edits in this area
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/history`；G2 终页标题/heading 匹配 `Changesets`；G3 语义字段 [map_list] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 313（bcad4bf877daf4d67423）—题面：Reverse the route direction to get directions from Central Park to Times Square
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** derived_requires_two_full_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/directions`；G2 终页标题/heading 匹配 `Directions`；G3 语义字段 [map_route] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 314（bd40ef5bbf030f7c1505）—题面：Visit the Communities page on OpenStreetMap.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/communities`；G2 终页标题/heading 匹配 `Communities`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 315（c230980afa6f0bf0342b）—题面：Find and display the local OpenStreetMap Communities directory. Browsing an external chapter website is outside this local task.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/communities`；G2 终页标题/heading 匹配 `Communities`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 316（c2cdd5fb6c2f1ededd51）—题面：Navigate to the Help page to find documentation and guides for using OpenStreetMap.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/help`；G2 终页标题/heading 匹配 `Getting\ Help`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 317（c69a04a7e1db2552e953）—题面：Navigate to the User Diaries page.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/diary`；G2 终页标题/heading 匹配 `Users'\ Diaries`；G3 语义字段 [map_list] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 318（cecc62133b744eca72cc）—题面：Navigate to the directions page to find a route between two locations.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_full_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/directions`；G2 终页标题/heading 匹配 `OpenStreetMap`；G3 语义字段 [map_panel] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 319（d1d275dc46efc2e65476）—题面：Explore communities related to OpenStreetMap
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/communities`；G2 终页标题/heading 匹配 `Communities`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 320（d89b0048178cd11720cd）—题面：Navigate to the GPS Traces page to upload or browse GPS tracks.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/traces`；G2 终页标题/heading 匹配 `Public\ GPS\ Traces`；G3 语义字段 [map_list] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 321（e1006161c40c56b44309）—题面：View copyright information
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/copyright`；G2 终页标题/heading 匹配 `Copyright\ and\ License`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 322（e1b9a8faf241f6a088a8）—题面：Reverse the direction of the route to get directions from 40.75300, -73.97700 to 40.74800, -73.98600
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_full_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/directions`；G2 终页标题/heading 匹配 `Directions`；G3 语义字段 [map_route] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 323（f049bdfefc158611ea45）—题面：Access the local OpenStreetMap Help page and display its help options. External Wiki documentation is outside this local task.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/help`；G2 终页标题/heading 匹配 `Getting\ Help`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 324（f31a7694a8abb9a05a0a）—题面：View what different map layers are available
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_full_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/search|directions|export?`；G2 终页标题/heading 匹配 `OpenStreetMap`；G3 语义字段 [map_panel] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 325（fa2f7c04c93ddc04dd2f）—题面：Navigate to the Communities page to find and connect with local OpenStreetMap groups.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/communities`；G2 终页标题/heading 匹配 `Communities`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 326（fbc50f6895e5eb802320）—题面：Navigate to the Help page to get assistance with using OpenStreetMap.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/help`；G2 终页标题/heading 匹配 `Getting\ Help`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 327（13a0fabb465d848a3d9f）—题面：Explore Patio, Lawn & Garden products
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/catalog/category/view/id/10|/patio-lawn-garden.html`；G2 终页标题/heading 匹配 `Patio,\ Lawn\ \&\ Garden`；G3 语义字段 [category] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 328（1ad6d2c220a09d4eec48）—题面：View details of the NOZE Rustic Coat Rack in my recently ordered items
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/noze-rustic-coat-rack-wall-mounted-shelf-with-4-hooks-hanging-entryway-organizer-for-mug-coffee-cup-holding-solid-wooden-shelf-with-2-baskets-for-kitchen-living-room-bathroom-and-bedroom.html|/catalog/product/view/id/15787|/checkout/cart/configure/id/555/product_id/15787`；G2 终页标题/heading 匹配 `NOZE\ Rustic\ Coat\ Rack\ Wall\ Mounted\ Shelf\ with\ 4\ Hooks,\ Hanging\ Entryway\ Organizer\ for\ Mug\ Coffee\ Cup,\ Holding\ Solid\ Wooden\ Shelf\ with\ 2\ Baskets\ for\ Kitchen\ Living\ Room,\ Bathroom\ and\ Bedroom`；G3 语义字段 [product_details] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 329（255c56b474f48d698857）—题面：From the shopping cart page, open the Sports & Outdoors category page.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_live_validation（临时准则，contract 可能变更）
- **binding_family：** category_page
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/sports-outdoors.html`；G2 终页标题/heading 匹配 `Sports\ \&\ Outdoors Items .*?`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 330（269774e9cad9d6a4fc70）—题面：Go to page 2 of Beauty & Personal Care products
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** category_page
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/beauty-personal-care.html`；G2 终页标题/heading 匹配 `Beauty\ \&\ Personal\ Care`；G3 语义字段 [query_params] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 331（2a9363cecaf521d7e184）—题面：Navigate to the Health & Household category to shop for health products and household essentials.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** category
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/health-household.html`；G2 终页标题/heading 匹配 `Health\ \&\ Household`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 332（2fb1cbb63aa4a4d2f7a0）—题面：View the Bushnell 743333 Boresighter product details.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/bushnell-743333-boresighter-with-case-arbors-black.html|/catalog/product/view/id/30535`；G2 终页标题/heading 匹配 `Bushnell\ 743333\ Boresighter\ with\ Case\ \&\ ARbors,Black`；G3 语义字段 [product_details] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 333（34568cb201df021547da）—题面：View all your recently ordered items from your account.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_fresh_controls_after_reader_repair（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/customer/account`；G2 终页标题/heading 匹配 `My Account`；G3 语义字段 [recent_ordered_items] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 334（44abeb91aebb0043c0b0）—题面：Go back to the home page using breadcrumb navigation
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex（见 contract）；G2 终页标题/heading 匹配 `One\ Stop\ Market`；G3 语义字段 [navigation_control] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 335（464bd7f571d9eb04ce09）—题面：Browse Exercise & Fitness equipment.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/catalog/category/view/id/29|/catalog/category/view/id/4|/sports-outdoors/exercise-fitness.html|/sports-outdoors.html`；G2 终页标题/heading 匹配 `Exercise\ \&\ Fitness|Sports\ \&\ Outdoors`；G3 语义字段 [category] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 336（47dbbc6d000b4e84932c）—题面：Continue shopping and return to the homepage.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex（见 contract）；G2 终页标题/heading 匹配 `One\ Stop\ Market`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 337（5239a4f0b915fb43e36f）—题面：Visit the home page to browse all products.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** requires_fresh_initial_goal_controls（临时准则，contract 可能变更）
- **binding_family：** homepage
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex（见 contract）；G2 终页标题/heading 匹配 `One Stop Market`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 338（5ba99a807a9cf95280ec）—题面：View details of the Pre-baked Gingerbread House Kit Value Pack.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** product_detail
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/pre-baked-gingerbread-house-kit-value-pack-17-oz-pack-of-2-total-34-oz.html`；G2 终页标题/heading 匹配 `Pre-baked\ Gingerbread\ House\ Kit\ Value\ Pack,\ 17\ oz.,\ Pack\ of\ 2,\ Total\ 34\ oz.`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 339（5c796dd22c55ca62d44e）—题面：View details of a product in your cart.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/plus-size-lingerie-for-women-sexy-for-sex-naughty-eyelash-lace-bodysuit-naughty-mesh-one-piece-teddy-bodysuit-outfits.html|/uttermost-volterra-crackled-taupe-gray-ceramic-table-lamp.html|/noze-rustic-coat-rack-wall-mounted-shelf-with-4-hooks-hanging-entryway-organizer-for-mug-coffee-cup-holding-solid-wooden-shelf-with-2-baskets-for-kitchen-living-room-bathroom-and-bedroom.html|/catalog/product/view/id/10617|/catalog/product/view/id/15033|/catalog/product/view/id/15787|/checkout/cart/configure/id/554/product_id/15033|/checkout/cart/configure/id/555/product_id/15787|/checkout/cart/configure/id/556/product_id/10617`；G2 终页标题/heading 匹配 `Plus\ Size\ Lingerie\ for\ Women\ Sexy\ for\ Sex\ Naughty\ Eyelash\ Lace\ Bodysuit\ Naughty\ Mesh\ One\ Piece\ Teddy\ Bodysuit\ Outfits|Uttermost\ Volterra\ Crackled\ Taupe-Gray\ Ceramic\ Table\ Lamp|NOZE\ Rustic\ Coat\ Rack\ Wall\ Mounted\ Shelf\ with\ 4\ Hooks,\ Hanging\ Entryway\ Organizer\ for\ Mug\ Coffee\ Cup,\ Holding\ Solid\ Wooden\ Shelf\ with\ 2\ Baskets\ for\ Kitchen\ Living\ Room,\ Bathroom\ and\ Bedroom`；G3 语义字段 [product_details] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 340（602bc6ede42c73e516ac）—题面：Explore Electronics products
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/catalog/category/view/id/11|/electronics.html`；G2 终页标题/heading 匹配 `Electronics`；G3 语义字段 [category] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 341（62b7701daa69787a85d6）—题面：Read reviews for the Crazy Sales Massage Table Carry Bag.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_independent_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/crazy-sales-massage-table-carry-bag-professional-spa-table-shoulder-bag-portable-foldable-belt-adjustable-salon-bed-face-cradle-bed.html|/catalog/product/view/id/94390`；G2 终页标题/heading 匹配 `Crazy\ Sales\ Massage\ Table\ Carry\ Bag,\ Professional\ Spa\ Table\ Shoulder\ Bag\ Portable\ Foldable\ Belt\ Adjustable\ Salon\ Bed\ Face\ Cradle\ Bed`；G3 语义字段 [product_panel] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 342（6acbad9b26c6427856ce）—题面：Look at Bedding products
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/catalog/category/view/id/35|/catalog/category/view/id/6|/home-kitchen/bedding.html|/home-kitchen.html`；G2 终页标题/heading 匹配 `Bedding|Home\ \&\ Kitchen`；G3 语义字段 [category] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 343（6be6d37e350eb2bc36e7）—题面：View the Privacy and Cookie Policy page to learn about how the site handles your data.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_live_validation（临时准则，contract 可能变更）
- **binding_family：** privacy_page
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/privacy-policy-cookie-restriction-mode`；G2 终页标题/heading 匹配 `Privacy and Cookie Policy`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 344（74c98564d1e35bf6dec4）—题面：Go to the Beauty & Personal Care category.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_live_validation（临时准则，contract 可能变更）
- **binding_family：** category_page
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/beauty-personal-care.html`；G2 终页标题/heading 匹配 `Beauty\ \&\ Personal\ Care Items .*?`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 345（78756f29fb9e71590a06）—题面：Go to your account page to manage your personal information
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** account_dashboard
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/customer/account`；G2 终页标题/heading 匹配 `My Account`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 346（7c4352d8e52492a93e9b）—题面：Navigate to the Advanced Search page to search for specific products with filters.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_live_validation（临时准则，contract 可能变更）
- **binding_family：** advanced_search_form
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/catalogsearch/advanced`；G2 终页标题/heading 匹配 `Advanced Search`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 347（7ccd70cd9214b15c0a35）—题面：Navigate to the My Account page
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_live_validation（临时准则，contract 可能变更）
- **binding_family：** account_dashboard
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/customer/account`；G2 终页标题/heading 匹配 `My Account`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 348（7f76ec7678c1f7660c91）—题面：Browse products in the Beauty & Personal Care category
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** category
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/beauty-personal-care.html`；G2 终页标题/heading 匹配 `Beauty\ \&\ Personal\ Care`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 349（8886097798330a2b52ad）—题面：Browse the Grocery & Gourmet Food category
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_live_validation（临时准则，contract 可能变更）
- **binding_family：** category_page
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/grocery-gourmet-food.html`；G2 终页标题/heading 匹配 `Grocery\ \&\ Gourmet\ Food Items .*?`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 350（8aa88113542d93e86d9d）—题面：Go to Advanced Search to search for specific outdoor equipment.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_live_validation（临时准则，contract 可能变更）
- **binding_family：** advanced_search_form
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/catalogsearch/advanced`；G2 终页标题/heading 匹配 `Advanced Search`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 351（9f25892f02f29db5ec94）—题面：Navigate to the Clothing, Shoes & Jewelry category page to explore more products on sale.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** category
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/clothing-shoes-jewelry.html`；G2 终页标题/heading 匹配 `Clothing,\ Shoes\ \&\ Jewelry`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 352（b8474380646f2fce807c）—题面：Navigate to page 2 of Home & Kitchen products to see more items.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** category_page
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/home-kitchen.html`；G2 终页标题/heading 匹配 `Home\ \&\ Kitchen`；G3 语义字段 [query_params] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 353（b87ba988ad238b0acc93）—题面：Explore Hair Care products for hair treatments and styling.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/beauty-personal-care/hair-care.html|/beauty-personal-care.html|/catalog/category/view/id/19|/catalog/category/view/id/3`；G2 终页标题/heading 匹配 `Beauty\ \&\ Personal\ Care|Hair\ Care`；G3 语义字段 [category] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 354（ba50fac977c6e53d4929）—题面：View all customer reviews for the Nightfox Vulpes Night Vision Goggles.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/nightfox-vulpes-handheld-digital-night-vision-goggles-integrated-laser-rangefinder-full-high-definition-fhd-1080p-sensor-records-video-audio-220yd-range-6x-magnification-hunting-security.html`；G2 终页标题/heading 匹配 `Nightfox\ Vulpes\ Handheld\ Digital\ Night\ Vision\ Goggles\ \|\ Integrated\ Laser\ Rangefinder\ \|\ Full\ High\ Definition\ FHD\ 1080p\ Sensor\ \|\ Records\ Video\ \+\ Audio\ \|\ 220yd\ Range,\ 6x\ Magnification\ \|\ Hunting,\ Security`；G3 语义字段 [product_panel] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 355（bd49de7c4477fe8104f6）—题面：Get detailed information about the "Power of Positivity" Eye Shadow Palette.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/power-of-positivity-eye-shadow-palette-gluten-free-vegan-cruelty-free.html|/catalog/product/view/id/9571`；G2 终页标题/heading 匹配 `'Power\ of\ Positivity'\ Eye\ Shadow\ Palette\ \|\ Gluten\ Free\ \|\ Vegan\ \|\ Cruelty\ Free`；G3 语义字段 [product_details] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 356（c0e6e10cd6ba5aec5ffe）—题面：Go to the Advanced Search page.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_live_validation（临时准则，contract 可能变更）
- **binding_family：** advanced_search_form
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/catalogsearch/advanced`；G2 终页标题/heading 匹配 `Advanced Search`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 357（c2555416de619bc829ac）—题面：Browse to page 2 of the Beauty & Personal Care products
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** category_page
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/beauty-personal-care.html`；G2 终页标题/heading 匹配 `Beauty\ \&\ Personal\ Care`；G3 语义字段 [query_params] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 358（c358dd6529a01a140edf）—题面：Browse Tools & Accessories in Beauty category
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/beauty-personal-care/tools-accessories.html|/beauty-personal-care.html|/catalog/category/view/id/20|/catalog/category/view/id/3`；G2 终页标题/heading 匹配 `Beauty\ \&\ Personal\ Care|Tools\ \&\ Accessories`；G3 语义字段 [category] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 359（c39966933178cd8c3756）—题面：View my order details for order #000000187
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/sales/order/view/order_id/187`；G2 终页标题/heading 匹配 `Order # 000000187`；G3 语义字段 [order_detail] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 360（cd607128c0a32223b604）—题面：Go to My Account page
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_live_validation（临时准则，contract 可能变更）
- **binding_family：** account_dashboard
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/customer/account`；G2 终页标题/heading 匹配 `My Account`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 361（cf4999bde780275b58cb）—题面：View details of the Intel NUC Kit Mini PC
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/intel-nuc-kit-nuc6i7kyk-mini-pc-no-power-cord.html|/catalog/product/view/id/37282`；G2 终页标题/heading 匹配 `Intel\ NUC\ Kit\ NUC6i7KYK\ Mini\ PC-no\ Power\ Cord`；G3 语义字段 [product_details] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 362（d9dee57aa1e361c911d1）—题面：View my product reviews
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** own_reviews
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/review/customer`；G2 终页标题/heading 匹配 `My Product Reviews`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 363（db147dc6bede0ae35635）—题面：Go to the List of cookies we collect section.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_fresh_controls_after_reader_repair（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/privacy-policy-cookie-restriction-mode`；G2 终页标题/heading 匹配 `Privacy and Cookie Policy`；G3 语义字段 [cms_section] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 364（e497369511069de0d3cd）—题面：View details for 5x40 Night Vision Monocular Telescopes Multifunctional IR Digital Night Vision Telescope Camera with Video Recorder Camouflage Infrared Camera Hunting Night Vision Monocular Device.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/5x40-night-vision-monocular-telescopes-multifunctional-ir-digital-night-vision-telescope-camera-with-video-recorder-camouflage-infrared-camera-hunting-night-vision-monocular-device.html|/catalog/product/view/id/30475`；G2 终页标题/heading 匹配 `5x40\ Night\ Vision\ Monocular\ Telescopes\ Multifunctional\ IR\ Digital\ Night\ Vision\ Telescope\ Camera\ with\ Video\ Recorder\ Camouflage\ Infrared\ Camera\ Hunting\ Night\ Vision\ Monocular\ Device`；G3 语义字段 [product_details] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 365（e63887a2e5fee9b8851b）—题面：Shop for items in the Clothing, Shoes & Jewelry category.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** category
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/clothing-shoes-jewelry.html`；G2 终页标题/heading 匹配 `Clothing,\ Shoes\ \&\ Jewelry`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 366（e916b770cf6c9961fb69）—题面：Navigate to the Hunting & Fishing category in Sports & Outdoors.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/catalog/category/view/id/25|/catalog/category/view/id/4|/sports-outdoors/hunting-fishing.html|/sports-outdoors.html`；G2 终页标题/heading 匹配 `Hunting\ \&\ Fishing|Sports\ \&\ Outdoors`；G3 语义字段 [category] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 367（eb659eedcb65a365df65）—题面：Browse Sports & Outdoors products
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_live_validation（临时准则，contract 可能变更）
- **binding_family：** category_page
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/sports-outdoors.html`；G2 终页标题/heading 匹配 `Sports\ \&\ Outdoors Items .*?`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 368（edfe76ffbd372ca622ae）—题面：Read reviews for Nightfox Vulpes Handheld Digital Night Vision Goggles.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/nightfox-vulpes-handheld-digital-night-vision-goggles-integrated-laser-rangefinder-full-high-definition-fhd-1080p-sensor-records-video-audio-220yd-range-6x-magnification-hunting-security.html`；G2 终页标题/heading 匹配 `Nightfox\ Vulpes\ Handheld\ Digital\ Night\ Vision\ Goggles\ \|\ Integrated\ Laser\ Rangefinder\ \|\ Full\ High\ Definition\ FHD\ 1080p\ Sensor\ \|\ Records\ Video\ \+\ Audio\ \|\ 220yd\ Range,\ 6x\ Magnification\ \|\ Hunting,\ Security`；G3 语义字段 [product_panel] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 369（ee04c15561b881b0bf46）—题面：View the "Power of Positivity" Eye Shadow Palette product details
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/power-of-positivity-eye-shadow-palette-gluten-free-vegan-cruelty-free.html|/catalog/product/view/id/9571`；G2 终页标题/heading 匹配 `'Power\ of\ Positivity'\ Eye\ Shadow\ Palette\ \|\ Gluten\ Free\ \|\ Vegan\ \|\ Cruelty\ Free`；G3 语义字段 [product_details] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 370（f07d85b36aa89cf41e5b）—题面：Go to the product page of "Bushnell 743333 Boresighter with Case & ARbors,Black".
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** product_detail
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/bushnell-743333-boresighter-with-case-arbors-black.html`；G2 终页标题/heading 匹配 `Bushnell\ 743333\ Boresighter\ with\ Case\ \&\ ARbors,Black`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 371（f792d5b646924f60298a）—题面：Check your recently ordered items
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_fresh_controls_after_reader_repair（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/customer/account`；G2 终页标题/heading 匹配 `My Account`；G3 语义字段 [recent_ordered_items] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 372（fadb8e6b2ed3664b20d6）—题面：View Contact Us page.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_live_validation（临时准则，contract 可能变更）
- **binding_family：** contact_page
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/contact`；G2 终页标题/heading 匹配 `Contact Us`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 373（fdd86ebe9fbff3977476）—题面：Visit Newsletter Subscriptions page.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** newsletter_settings
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/newsletter/manage`；G2 终页标题/heading 匹配 `Newsletter Subscription`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 374（18972d3400c722a4ffea）—题面：Go to the memes forum page to view its content.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_live_validation（临时准则，contract 可能变更）
- **binding_family：** named_forum
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/f/memes`；G2 终页标题/heading 匹配 `/fmemes`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 375（1b7cc1a2a3bded53a92c）—题面：Navigate to the Forums page.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_live_validation（临时准则，contract 可能变更）
- **binding_family：** forum_directory
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/forums`；G2 终页标题/heading 匹配 `List of forums`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 376（27c63bcda6ea5f513130）—题面：Navigate to the movies forum to discuss films, movie news, and cinema.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_live_validation（临时准则，contract 可能变更）
- **binding_family：** named_forum
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/f/movies`；G2 终页标题/heading 匹配 `/fmovies`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 377（2ab43456dd85145f8cc8）—题面：Explore the memes forum
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_native_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/f/memes`；G2 终页标题/heading 匹配 `/fmemes`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 378（3112149ed88814016dc3）—题面：Explore the science forum for scientific discussions.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_native_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/f/science`；G2 终页标题/heading 匹配 `/fscience`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 379（351cef41c763fe65bb86）—题面：Navigate to the page for creating a new wiki page.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** wiki_create_form
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/wiki/_create`；G2 终页标题/heading 匹配 `Create new page`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 380（377df3ac94c013710664）—题面：Browse forums in alphabetical order.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** alphabetical_forums
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/forums/all`；G2 终页标题/heading 匹配 `All forums`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 381（3d8eadee8a7a9377df5e）—题面：Sort forums by title.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/forums/by_title/[1-9][0-9]*?`；G2 终页标题/heading 匹配 `All forums|List of forums`；G3 语义字段 [forum_list] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 382（3e26458bd2eb43f20c5b）—题面：Browse the memes forum for humorous content.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_live_validation（临时准则，contract 可能变更）
- **binding_family：** named_forum
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/f/memes`；G2 终页标题/heading 匹配 `/fmemes`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 383（44b4afbbc9b99c36e9bb）—题面：Navigate to the joke page titled "My girlfriend left me because of my abandonment issues..."
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/f/Jokes/119862/[/]+?`；G2 终页标题/heading 匹配 `My\ girlfriend\ left\ me\ because\ of\ my\ abandonment\ issues...`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 384（45a739d64fcb5d5d3833）—题面：Check your hidden forums.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/user/MarvelsGrantMan136/hidden_forums`；G2 终页标题/heading 匹配 `Hidden\ forums`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 385（47bdbdea898616e0cc46）—题面：Go to the forums page.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_live_validation（临时准则，contract 可能变更）
- **binding_family：** forum_directory
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/forums`；G2 终页标题/heading 匹配 `List of forums`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 386（49aa91c52b9c981c098f）—题面：Sort the forum list alphabetically by forum name
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/forums/all|by_name(?:/[1-9][0-9]*?)`；G2 终页标题/heading 匹配 `All forums|List of forums`；G3 语义字段 [forum_list] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 387（4af9ec625c89f92a8b85）—题面：Navigate to the food forum.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_live_validation（临时准则，contract 可能变更）
- **binding_family：** named_forum
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/f/food`；G2 终页标题/heading 匹配 `/ffood`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 388（5b52a8165650a66e8f37）—题面：Go back to the forums.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_live_validation（临时准则，contract 可能变更）
- **binding_family：** forum_directory
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/forums`；G2 终页标题/heading 匹配 `List of forums`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 389（5d450bf7b0ba022de554）—题面：Change the view of forums from submissions to alphabetical
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/forums/all|by_name(?:/[1-9][0-9]*?)`；G2 终页标题/heading 匹配 `All forums|List of forums`；G3 语义字段 [forum_list] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 390（5dd565a907f19bcd45b5）—题面：Go back to the home page from the submission form
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_live_validation（临时准则，contract 可能变更）
- **binding_family：** homepage
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex（见 contract）；G2 终页标题/heading 匹配 `Postmill`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 391（60ff346de5439a79316a）—题面：Navigate to the homepage.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_live_validation（临时准则，contract 可能变更）
- **binding_family：** homepage
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex（见 contract）；G2 终页标题/heading 匹配 `Postmill`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 392（65cd35447dd878098c31）—题面：Go to page 2 of the forums list
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** forum_page
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/forums/by_submissions/2`；G2 终页标题/heading 匹配 `List of forums`；G3 语义字段 [distinct_list_heading_regex] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 393（66126f96f8512e54a1c2）—题面：Sort posts in the movies forum by Most commented over all time to find the most discussed topics.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/f/movies/(?:hot|new|top|most_commented)?`；G2 终页标题/heading 匹配 `/f/movies`；G3 语义字段 [post_list] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 394（69c434d3c2127b3def0a）—题面：Browse forums by tags.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** forum_tags
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/tags`；G2 终页标题/heading 匹配 `Tags`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 395（69d7c430e7b5c9272eb5）—题面：Navigate to the All pages section of the wiki.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** wiki_index
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/wiki/_all`；G2 终页标题/heading 匹配 `All pages`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 396（765eb522fe286cb0a66d）—题面：View the user profile of SashaGreatest.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_live_validation（临时准则，contract 可能变更）
- **binding_family：** named_user_profile
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/user/SashaGreatest/submissions?`；G2 终页标题/heading 匹配 `SashaGreatest`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 397（810a12011686f67f627a）—题面：Sort the forums by creation date to see the newest forums first.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/forums/by_creation_date/[1-9][0-9]*?`；G2 终页标题/heading 匹配 `All forums|List of forums`；G3 语义字段 [forum_list] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 398（878413977cd9a814b942）—题面：Go to the LifeProTips forum
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_live_validation（临时准则，contract 可能变更）
- **binding_family：** named_forum
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/f/LifeProTips`；G2 终页标题/heading 匹配 `/fLifeProTips`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 399（8bf1a6bbcea8351cd55b）—题面：View forums sorted alphabetically.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** alphabetical_forums
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/forums/all`；G2 终页标题/heading 匹配 `All forums`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 400（8dbb7a62694a33a430cf）—题面：Go to the pics forum page to view its content.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_live_validation（临时准则，contract 可能变更）
- **binding_family：** named_forum
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/f/pics`；G2 终页标题/heading 匹配 `/fpics`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 401（92f69c08511f177fb5b3）—题面：Explore the moderation log for the Music forum.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/f/Music/moderation_log`；G2 终页标题/heading 匹配 `Showing\ moderation\ log\ for\ /f/Music`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 402（933db784845321b7cf50）—题面：Check recent changes in the Wiki.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** wiki_changes
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/wiki/_recent/[0-9]+?`；G2 终页标题/heading 匹配 `Recent changes`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 403（9d63ee81b6bbf16f0386）—题面：Navigate to the Create new page section to start creating a new wiki page.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** wiki_create_form
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/wiki/_create`；G2 终页标题/heading 匹配 `Create new page`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 404（9df7d3935a696be1049a）—题面：Go to the second page of forum listings
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** forum_page
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/forums/by_submissions/2`；G2 终页标题/heading 匹配 `List of forums`；G3 语义字段 [distinct_list_heading_regex] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 405（a8d2697ced77921baa92）—题面：Browse forums in alphabetical order
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** alphabetical_forums
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/forums/all`；G2 终页标题/heading 匹配 `All forums`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 406（af31dc799e51ccad402c）—题面：Navigate to the Forums page to explore community discussions.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_native_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/forums`；G2 终页标题/heading 匹配 `List of forums`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 407（b3bd93fe9fa6eb441da5）—题面：Search for posts about machine learning
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_private_reference_and_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/search`；G2 终页标题/heading 匹配 `Search`；G3 语义字段 [reddit_search] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 408（b4f0486d4418ae0bca40）—题面：Navigate to page 2 of the forums list.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** forum_page
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/forums/by_submissions/2`；G2 终页标题/heading 匹配 `List of forums`；G3 语义字段 [distinct_list_heading_regex] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 409（bb07fa576f83587a108f）—题面：Use the native plain-text search for "upcoming movie releases" and display its local results. This is a literal search; no external release calendar is required.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** candidate_requires_actual_two_cold_positive_negative_and_reset_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/search`；G2 终页标题/heading 匹配 `Search`；G3 语义字段 [reddit_search] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 410（bb3cdfd32d3103c63645）—题面：Go to the news forum.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_live_validation（临时准则，contract 可能变更）
- **binding_family：** named_forum
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/f/news`；G2 终页标题/heading 匹配 `/fnews`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 411（be949364ea9b3305b0fd）—题面：View a user profile.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_native_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/user/[/]+/submissions?`；G2 终页标题/heading 匹配 `.+`；G3 语义字段 [reddit_any_profile] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 412（ca5a11acef0c0662cafb）—题面：Check your block list.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** block_list
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/user/MarvelsGrantMan136/block_list`；G2 终页标题/heading 匹配 `Block list`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 413（d2849c468c9d7f79fc4c）—题面：Navigate to the relationship_advice forum
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_live_validation（临时准则，contract 可能变更）
- **binding_family：** named_forum
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/f/relationship_advice`；G2 终页标题/heading 匹配 `/frelationship_advice`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 414（d62097dc3f906d29763c）—题面：Clear the current search and search for "skin care products"
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_private_reference_and_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/search`；G2 终页标题/heading 匹配 `Search`；G3 语义字段 [reddit_search] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 415（d79c8e87b72c40aadfa5）—题面：Navigate to the movies forum.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_live_validation（临时准则，contract 可能变更）
- **binding_family：** named_forum
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/f/movies`；G2 终页标题/heading 匹配 `/fmovies`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 416（deea459bf06ce5b27eb7）—题面：View your user profile
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** own_profile
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/user/MarvelsGrantMan136/submissions?`；G2 终页标题/heading 匹配 `MarvelsGrantMan136`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 417（e642e4b7d549e51f63fb）—题面：Check recent changes in the Wiki
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** wiki_changes
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/wiki/_recent/[0-9]+?`；G2 终页标题/heading 匹配 `Recent changes`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 418（e9867fbfbd0d5464fd39）—题面：View all wiki pages
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** wiki_index
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/wiki/_all`；G2 终页标题/heading 匹配 `All pages`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 419（f7188e2322661c71283f）—题面：View forums in Alphabetical order.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/forums/all|by_name(?:/[1-9][0-9]*?)`；G2 终页标题/heading 匹配 `All forums|List of forums`；G3 语义字段 [forum_list] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 420（f8ad6d31e9aeed13d548）—题面：Navigate to the Alphabetical view to see forums listed in alphabetical order.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** alphabetical_forums
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/forums/all`；G2 终页标题/heading 匹配 `All forums`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 421（f94fd0a85e1d2b24568c）—题面：Open the Submit page to create a new post
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** submission_form
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/submit`；G2 终页标题/heading 匹配 `Create submission`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 422（f9d2a2c865817e89de70）—题面：Visit the gaming forum to see gaming-related discussions
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** candidate_requires_actual_two_cold_positive_negative_and_reset_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/f/gaming`；G2 终页标题/heading 匹配 `/fgaming`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 423（ff1288a318ead65fce2e）—题面：Access the homepage.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_live_validation（临时准则，contract 可能变更）
- **binding_family：** homepage
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex（见 contract）；G2 终页标题/heading 匹配 `Postmill`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 442（3d11daa68b8c93f5858e）—题面：View details of the Plus Size Lingerie item in my cart
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/plus-size-lingerie-for-women-sexy-for-sex-naughty-eyelash-lace-bodysuit-naughty-mesh-one-piece-teddy-bodysuit-outfits.html|/catalog/product/view/id/10617|/checkout/cart/configure/id/556/product_id/10617`；G2 终页标题/heading 匹配 `Plus\ Size\ Lingerie\ for\ Women\ Sexy\ for\ Sex\ Naughty\ Eyelash\ Lace\ Bodysuit\ Naughty\ Mesh\ One\ Piece\ Teddy\ Bodysuit\ Outfits`；G3 语义字段 [product_details] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 443（b4045013dcdbe0e6f5f9）—题面：Navigate to the reviews section for the Pre-baked Gingerbread House Kit Value Pack.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/pre-baked-gingerbread-house-kit-value-pack-17-oz-pack-of-2-total-34-oz.html`；G2 终页标题/heading 匹配 `Pre-baked\ Gingerbread\ House\ Kit\ Value\ Pack,\ 17\ oz.,\ Pack\ of\ 2,\ Total\ 34\ oz.`；G3 语义字段 [product_panel] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 444（505e04c5eb5201102f65）—题面：Shop for Home & Kitchen products.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** category
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/home-kitchen.html`；G2 终页标题/heading 匹配 `Home\ \&\ Kitchen`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 445（440a8b1af94cf76ed2bf）—题面：View merged merge requests assigned to your account.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/dashboard/merge_requests`；G2 终页标题/heading 匹配 `Merge requests`；G3 语义字段 [issuable_list] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 446（9819a41cd3b66bded28f）—题面：View issue #105 about Python 2.7 compatibility in youfou/wxpy.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** issue_detail
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/youfou/wxpy/-/issues/105`；G2 终页标题/heading 匹配 `python2.7\ FileNotFoundError`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 447（b1dc035ba13c6766daea）—题面：From the current Explore projects page, open your personal Projects dashboard home showing your projects. Leave that dashboard home open, rather than the Starred projects collection.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_alias_controls（临时准则，contract 可能变更）
- **binding_family：** project_dashboard
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/dashboard/projects?`；G2 终页标题/heading 匹配 `Projects · Dashboard · GitLab`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 448（bf43becccb2cb0f30d70）—题面：View all merge requests assigned to your account regardless of status.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/dashboard/merge_requests`；G2 终页标题/heading 匹配 `Merge requests`；G3 语义字段 [issuable_list] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 449（eb79e47b111e0d6f19e0）—题面：View open issues for checkstyle/checkstyle.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/checkstyle/checkstyle/-/issues`；G2 终页标题/heading 匹配 `Issues · .+ / checkstyle · GitLab`；G3 语义字段 [issuable_list] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 450（54066c2710d43c3a8205）—题面：Display the local About OpenStreetMap page. Completion means that the local introduction page is open.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/about`；G2 终页标题/heading 匹配 `OpenStreetMap\ provides\ map\ data\ for\ thousands\ of\ websites,\ mobile\ apps,\ and\ hardware\ devices`；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 453（05680da53589ba4a7c39）—题面：Navigate to the Meta organization page.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** (空)（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 （completion 由 family + gitlab_native_content 约束）；G3 family + gitlab_native_content 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 454（26258107ff993d1b71d7）—题面：Set up a GitLab group for personal use with "Just me" selected as the user
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** requires_two_independent_native_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "创建组是单一写操作，设置与保存同 gate 验证，不拆"}
- **适用场景：** 为当前账号创建 GitLab 组（写操作）。
- **成功门控条件（gate）：** G1 使用当前账号创建；G2 恰好创建一条新组记录；G3 新组满足 group_creation 显式设置：setup_for_company=False；G4 现有组与设置不变；G5 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 操作范围 0.35 / 验证规范 0.30 / 保存确认 0.20 / 证据充分性 0.15（锚点与判定标准见 §2.28）。
- **边界情况：** 无法确认新组是否唯一/满足设置 → null。
- **不应给分的反例：** 不把「进入创建组页」与「保存新组」拆两个分数；不因「新建多个组」给分（G2 违反→0）；不因「组设置错误」给分（G3 违反→0）。
- **completion_scope：** Exactly one newly saved group owned by the current account; explicitly requested settings checked in the persisted namespace record. Existing groups and settings must remain unchanged.

#### 题目 455（286d4ac488bdcd446ffc）—题面：Set up a new GitLab group with internal visibility that can only be seen by logged-in users
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "创建组是单一写操作，设置与保存同 gate 验证，不拆"}
- **适用场景：** 为当前账号创建 GitLab 组（写操作）。
- **成功门控条件（gate）：** G1 使用当前账号创建；G2 恰好创建一条新组记录；G3 新组满足 group_creation 显式设置：visibility_level=10；G4 现有组与设置不变；G5 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 操作范围 0.35 / 验证规范 0.30 / 保存确认 0.20 / 证据充分性 0.15（锚点与判定标准见 §2.28）。
- **边界情况：** 无法确认新组是否唯一/满足设置 → null。
- **不应给分的反例：** 不把「进入创建组页」与「保存新组」拆两个分数；不因「新建多个组」给分（G2 违反→0）；不因「组设置错误」给分（G3 违反→0）。
- **completion_scope：** One newly saved group owned by the current account; constrain name, visibility and hierarchy only when required by the original task. Unspecified name/path/settings remain free.

#### 题目 456（35c44498db3696d519d2）—题面：Create a top-level internal GitLab group with the custom URL path "local-training-internal-group".
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** requires_two_independent_native_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "创建组是单一写操作，设置与保存同 gate 验证，不拆"}
- **适用场景：** 为当前账号创建 GitLab 组（写操作）。
- **成功门控条件（gate）：** G1 使用当前账号创建；G2 恰好创建一条新组记录；G3 新组满足 group_creation 显式设置：path="local-training-internal-group", top_level=true, visibility_level=10；G4 现有组与设置不变；G5 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 操作范围 0.35 / 验证规范 0.30 / 保存确认 0.20 / 证据充分性 0.15（锚点与判定标准见 §2.28）。
- **边界情况：** 无法确认新组是否唯一/满足设置 → null。
- **不应给分的反例：** 不把「进入创建组页」与「保存新组」拆两个分数；不因「新建多个组」给分（G2 违反→0）；不因「组设置错误」给分（G3 违反→0）。
- **completion_scope：** Exactly one newly saved group owned by the current account; explicitly requested settings checked in the persisted namespace record. Existing groups and settings must remain unchanged.

#### 题目 457（8c9eba264b7695102806）—题面：Learn about Keycloak test development
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** (空)（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 （completion 由 family + gitlab_native_content 约束）；G3 family + gitlab_native_content 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 458（290638fcb182c6960f48）—题面：Navigate to the Edit page on OpenStreetMap.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_normal_controls_then_actor_once（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/edit`；G2 终页标题/heading 匹配 `OpenStreetMap`；G3 语义字段 [map_editor] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 459（325c3e9af6cf020c8d7f）—题面：View GPS traces uploaded by users
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/traces|/user/LocalBenchmarkMapper/traces|/user/LocalBenchmarkMapper/traces/1|/user/LocalBenchmarkMapper/traces/2`；G2 终页标题/heading 匹配 `Public\ GPS\ Traces|Public\ GPS\ Traces\ from\ LocalBenchmarkMapper|Viewing\ Trace\ local-fixture-park-walk.gpx|Viewing\ Trace\ local-fixture-riverside-walk.gpx`；G3 语义字段 [map_gps] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 460（5ffe7246e3cf8cfd922f）—题面：Navigate to the upload page to add a new GPS trace to OpenStreetMap.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_fresh_normal_controls_then_actor_once（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/traces/new`；G2 终页标题/heading 匹配 `Upload GPS Trace`；G3 语义字段 [map_native_navigation] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 461（9d2a902babb8a46d7af8）—题面：View all GPS traces in the system.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/traces`；G2 终页标题/heading 匹配 `Public\ GPS\ Traces`；G3 语义字段 [map_gps] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 462（d633bb692c21fc64b3d2）—题面：Check user-contributed GPS traces
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/traces|/user/LocalBenchmarkMapper/traces|/user/LocalBenchmarkMapper/traces/1|/user/LocalBenchmarkMapper/traces/2`；G2 终页标题/heading 匹配 `Public\ GPS\ Traces|Public\ GPS\ Traces\ from\ LocalBenchmarkMapper|Viewing\ Trace\ local-fixture-park-walk.gpx|Viewing\ Trace\ local-fixture-riverside-walk.gpx`；G3 语义字段 [map_gps] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 463（dde1229f74de8eaff67e）—题面：Browse user diaries to see contributors' experiences
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** requires_two_new_native_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/diary|/user/LocalBenchmarkMapper/diary/1|/user/LocalBenchmarkMapper/diary/2`；G2 终页标题/heading 匹配 `Users'\ Diaries|LocalBenchmarkMapper's\ Diary`；G3 语义字段 [map_diary] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 464（50bdd7670ad731020527）—题面：Access User Diaries to read contributions.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** requires_two_new_native_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/diary|/user/LocalBenchmarkMapper/diary/1|/user/LocalBenchmarkMapper/diary/2`；G2 终页标题/heading 匹配 `Users'\ Diaries|LocalBenchmarkMapper's\ Diary`；G3 语义字段 [map_diary] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 465（6586691f6d521f734fb0）—题面：Go to User Diaries to read about mapping activities from the community.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** requires_two_new_native_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/diary|/user/LocalBenchmarkMapper/diary/1|/user/LocalBenchmarkMapper/diary/2`；G2 终页标题/heading 匹配 `Users'\ Diaries|LocalBenchmarkMapper's\ Diary`；G3 语义字段 [map_diary] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 466（7903acb30399bd5c8e05）—题面：View GPS traces from the GPS Traces page.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** requires_two_live_controls（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex `/traces|/user/LocalBenchmarkMapper/traces|/user/LocalBenchmarkMapper/traces/1|/user/LocalBenchmarkMapper/traces/2`；G2 终页标题/heading 匹配 `Public\ GPS\ Traces|Public\ GPS\ Traces\ from\ LocalBenchmarkMapper|Viewing\ Trace\ local-fixture-park-walk.gpx|Viewing\ Trace\ local-fixture-riverside-walk.gpx`；G3 语义字段 [map_gps] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。

#### 题目 467（80e2c362bab0c0442d21）—题面：Navigate to the OpenStreetMap homepage to view and explore maps
- **分支：** `site_query_rules.evaluate_query:ordinary_query`（native_contract）
- **status：** draft_requires_two_fresh_normal_controls_then_actor_once（临时准则，contract 可能变更）
- **binding_family：** (空)
- **atomicity：** {"is_atomic": true, "reason": "导航到目标页面/菜单是单一原子任务，定位与确认身份同 gate 验证，不拆"}
- **成功门控条件（gate）：** G1 终页路径匹配 path_regex（见 contract）；G2 终页标题/heading 匹配 `OpenStreetMap`；G3 语义字段 [map_native_navigation] 与题面目标一致；G4 真实导航到达（非注入 URL），无 404/登录重定向/原地不动/错误对象；G5 `requested_records_unchanged`（只读）；G6 `page_valid` + `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（锚点见 §1.2）；判定标准同 §1.2。
- **边界情况：** 无法确认终页路径/标题匹配 → null（明确不匹配则 0）；无法确认真实导航 → null。
- **不应给分的反例：** 不拆「导航到页面」与「确认标题」；到达同类型错误对象/404/登录重定向/原地不动不判成功（G1/G2/G4 违反 → 0）；注入 URL 不视为真实导航。


## 附录 A：错误拆法对照表（防回归，节选）

| 类型 | 错误拆法（禁止） |
|---|---|
| admin 导航 | 点到菜单 0.5 + 确认页面 0.5（且相邻菜单/页面不得判成功） |
| path_heading / path_title | 导航到路径 0.5 + 确认标题 0.5 |
| map | 到地图页 0.5 + 定位路线/坐标 0.5 |
| 创建组（#454/#455/#456） | 进入创建页 0.5 + 保存新组 0.5 |
| 全部 | 注入 URL/后台跳转视为等价真实导航；404/登录重定向/原地不动判成功 |

## 附录 B：回归检查清单（提交前逐条勾选）

- [x] 每题都有 atomicity。
- [x] gate 映射 native_contract 判定谓词（path_regex / heading_regex / title_regex / spec / group_creation / completion_scope），无放宽/新增标准。
- [x] 质量维度仅在 gate 通过后计分，权重和 = 1.0（导航型 query 方案 + 创建组 write 方案，均属已登记）。
- [x] 未把「导航到页面」与「确认身份」拆成分数。
- [x] 54 题 ready 优先、245 题 draft 标注临时准则。
- [x] 3 题创建组（写操作）已区分、未套用只读 gate。
- [x] 负例（404/登录重定向/原地不动/错误对象）已纳入 gate 反例。
- [x] 执行顺序正确：本批为 binary 内 batch5（299 题 native），完成后转 non-binary 161 题、再 remaining 1325 题。
