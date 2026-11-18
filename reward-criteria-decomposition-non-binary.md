# 子奖励判断准则 · non-binary 161 题（P1 重写，不沿用固定分母）

> 本文按 `reward-criteria-reminder.md` §0 的 P1 原则重写 non-binary 161 题：**部分奖励只能是成功门控通过后的附加质量分，不得把硬前提拆成分数**。
> 原文件「前提通过后按固定分母 N 计分」为另一 AI 版本，**不作为口径基准**（见 reminder 附录 A）；本批统一改为 gate 全对 + 质量分。
> 计算公式 `R = null / 0 / base + (1-base)·Q` 由计算层实现，base 数值不在本文范围。

## 0. 范围与方法（仅依据文档）

- **数据源**：`docs/reward-inventory/non-binary-reward-tasks.md`（161 题，均有「固定分母」）。
- **本批范围**：non-binary 全部 161 题，按 §0 P1 重写。
- **P1 重写核心**：原「固定分母 N」（漏 1 字段 → (N-1)/N）→ **gate 全对**（任一字段/目标错 → 0）；质量维度仅在 gate 通过后计分。
- **复用与自包含**：本批 6 个分支（update/create/query/collection_query/pdf/ordinary_query）复用 binary 已建立框架，**框架全文已在 §2 展开，读者无需翻看其他文件**；4 个分支（export/bulk_update/page_text_query/mail）为 binary 未覆盖的新增框架。

**分支分布：**

| 分支 | 题数 | 类型 | | 分支 | 题数 | 类型 |
|---|---|---|---|---|---|---|
| ordinary_query | 69 | 复用 | query | 6 | 复用 |
| create | 29 | 复用 | pdf | 4 | 复用 |
| collection_query | 20 | 复用 | bulk_update | 3 | 新增 |
| update | 14 | 复用 | page_text_query | 3 | 新增 |
| export | 12 | 新增 | mail | 1 | 新增 |

### 0.1 权重方案（对应 reminder §4，方案 B）

- **query 型**（ordinary_query/query/page_text_query/pdf/export 只读类）：目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（pdf/export 将「字段校验」维度命名为「下载确认/导出完整性」）。
- **write 型**（update/create/bulk_update/mail 写类 + collection_query 集合查询）：0.35 / 0.30 / 0.20 / 0.15。
- 两套均属已登记方案，权重和恒 = 1.0，不引入第三套。

## 1. P1 通用原则（§0 落地）

1. **gate 全对**：硬前提合取，任一硬前提明确为假 → 0；证据不足且无法确认 → null（不转 0、不转失败）。
2. **多字段/多目标原子性**：题面要求的多个字段、多个要点、多个目标记录属同一原子任务，**不得拆成「字段各 1/N」**。固定分母 N 重写为「N 项全对才 gate 通过」。
3. **三类不可信结果一律不给分**：页面有效但答案错；标题对但某字段错（多字段只对一半）；选了目标值但未保存/未生效。
4. **gate 1:1 映射判定谓词**（persisted_requested_value / exact_result_set / new_matching_record_saved / downloaded_matching_csv / all_selected_records_updated / correct_partner_description / new_matching_mail_delivered / answer_<字段> 等），不另立标准。

## 2. 分支框架（自包含）

### 2.1 update 型（多字段更新，复用 batch1）（复用 binary）

- **成功门控条件（gate）**：G1 目标对象身份正确；G2 `persisted_requested_value`（目标字段最终值整体满足 update_matches，含题面全部要求字段）；G3 `other_records_unchanged`；G4 `same_local_deployment`；G5 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）**：操作范围 0.35 / 验证规范 0.30 / 保存确认 0.20 / 证据充分性 0.15（write 型）

### 2.2 create 型（多字段创建，复用 batch3 #90）（复用 binary）

- **成功门控条件（gate）**：G1 使用题面指定账号/目标；G2 `new_matching_record_saved`（恰好一条新记录）；G3 `created_record_conditions`（新记录整体满足全部字段）；G4 `existing_records_unchanged`；G5 `same_local_deployment`；G6 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）**：操作范围 0.35 / 验证规范 0.30 / 保存确认 0.20 / 证据充分性 0.15（write 型）

### 2.3 query 型（admin 多字段查询，复用 batch3）（复用 binary）

- **成功门控条件（gate）**：G1 目标绑定对象身份正确；G2 `answer_<字段>` 全部字段值与参考值精确匹配；G3 `records_unchanged`；G4 `same_local_deployment`；G5 `valid_authenticated_page`；G6 `answer_schema`。
- **质量维度（仅 gate 通过后计分）**：目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）

### 2.4 collection_query 型（多目标集合查询，复用 batch2）（复用 binary）

- **成功门控条件（gate）**：G1 过滤条件正确；G2 `exact_result_set`（完整多重集合：无遗漏/无多余/无重复）；G3 `records_unchanged`；G4 `same_local_deployment`；G5 `valid_authenticated_page`；G6 `answer_schema`。
- **质量维度（仅 gate 通过后计分）**：完整性 0.35 / 搜索条件准确性 0.30 / 来源合规 0.20 / 证据充分性 0.15

### 2.5 pdf 型（多目标下载，复用 batch3 #67）（复用 binary）

- **成功门控条件（gate）**：G1 目标订单/运单正确；G2 `downloaded_correct_documents`（下载产物内容+选中对象集合匹配）；G3 未生成/购买真实承运标签（题面禁止项）；G4 `records_unchanged`；G5 `same_local_deployment`；G6 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）**：目标定位规范 0.30 / 操作合规 0.30 / 下载确认 0.25 / 证据充分性 0.15

### 2.6 ordinary_query 型（多字段查询，复用 batch4）（复用 binary）

- **成功门控条件（gate）**：G1 目标绑定对象身份正确；G2 `answer_<字段>` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）**：目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）

### 2.7 export 型（CSV 导出，新增）（新增）

- **成功门控条件（gate）**：G1 导出对象集合正确；G2 `downloaded_matching_csv`（下载 CSV 内容+集合完整匹配，漏任一行/任一字段 → 0）；G3 `records_unchanged`（只读导出）；G4 `same_local_deployment`；G5 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）**：目标定位规范 0.30 / 操作合规 0.30 / 导出完整性 0.25 / 证据充分性 0.15

### 2.8 bulk_update 型（批量更新，新增）（新增）

- **成功门控条件（gate）**：G1 目标记录集合正确；G2 `all_selected_records_updated`（集合内所有对象均满足更新条件，漏任一对象 → 0）；G3 `other_records_unchanged`；G4 `same_local_deployment`；G5 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）**：操作范围 0.35 / 验证规范 0.30 / 保存确认 0.20 / 证据充分性 0.15（write 型）

### 2.9 page_text_query 型（页面文本查询，新增）（新增）

- **成功门控条件（gate）**：G1 `correct_page`（终页路径为要求路径）；G2 `correct_partner_description`（描述与参考一致）；G3 `partner_still_available`（伙伴描述未变）；G4 `records_unchanged`；G5 `same_local_deployment`；G6 `valid_authenticated_page`；G7 `answer_schema`。
- **质量维度（仅 gate 通过后计分）**：目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）

### 2.10 mail 型（发送邮件，新增）（新增）

- **成功门控条件（gate）**：G1 目标订单正确；G2 `new_matching_mail_delivered`（本地捕获新邮件，收件人+订单号匹配）；G3 `order_unchanged`（订单不变）；G4 `same_local_deployment`；G5 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）**：操作范围 0.35 / 验证规范 0.30 / 发送确认 0.20 / 证据充分性 0.15（write 型）

## 3. 逐题清单（161 题）

### 3.1 update 型（14 题）

#### 题目 11（0f1aa3a36555035eb8c0）—题面：Set Blue T-Shirt visibility to Catalog, Search and save.
- **分支：** `admin_contract_rules.checks:update`
- **原固定分母：** 2（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标对象身份正确；G2 `persisted_requested_value`（目标字段最终值整体满足 update_matches，含题面全部要求字段）；G3 `other_records_unchanged`；G4 `same_local_deployment`；G5 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 操作范围 0.35 / 验证规范 0.30 / 保存确认 0.20 / 证据充分性 0.15（write 型）（锚点见 §2.1）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 12（10cdae7af1322acbc6a3）—题面：For this local training variant, the following are supplied training product facts. Set the Sony Headphones Description to exactly the text inside the quotation marks, excluding the quotation marks: "Sony Headphones feature a lightweight adjustable headband and wired stereo playback. Specifications: 3.5 mm wired connection; no wireless connectivity.". Save the change.
- **分支：** `admin_contract_rules.checks:update`
- **原固定分母：** 4（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标对象身份正确；G2 `persisted_requested_value`（目标字段最终值整体满足 update_matches，含题面全部要求字段）；G3 `other_records_unchanged`；G4 `same_local_deployment`；G5 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 操作范围 0.35 / 验证规范 0.30 / 保存确认 0.20 / 证据充分性 0.15（write 型）（锚点见 §2.1）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 40（40d3da9f6369adbe5def）—题面：For this local training variant, update the email template named "Training Existing Email". Save subject "Updated customer information" and body exactly "Please review your account information in our training store.".
- **分支：** `admin_contract_rules.checks:update`
- **原固定分母：** 2（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标对象身份正确；G2 `persisted_requested_value`（目标字段最终值整体满足 update_matches，含题面全部要求字段）；G3 `other_records_unchanged`；G4 `same_local_deployment`；G5 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 操作范围 0.35 / 验证规范 0.30 / 保存确认 0.20 / 证据充分性 0.15（write 型）（锚点见 §2.1）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 44（44e44103a11d8563d0e1）—题面：For this local training variant, reference date is September 30, 2026. Save Test Product special price 19.99 from October 5 through October 11, 2026.
- **分支：** `admin_contract_rules.checks:update`
- **原固定分母：** 3（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标对象身份正确；G2 `persisted_requested_value`（目标字段最终值整体满足 update_matches，含题面全部要求字段）；G3 `other_records_unchanged`；G4 `same_local_deployment`；G5 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 操作范围 0.35 / 验证规范 0.30 / 保存确认 0.20 / 证据充分性 0.15（write 型）（锚点见 §2.1）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 52（4ec7495e3a9efa099bea）—题面：For this local training variant, save category ID 2 meta title as "Training Store Catalog" and meta description as "Browse the Training Store product catalog."
- **分支：** `admin_contract_rules.checks:update`
- **原固定分母：** 2（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标对象身份正确；G2 `persisted_requested_value`（目标字段最终值整体满足 update_matches，含题面全部要求字段）；G3 `other_records_unchanged`；G4 `same_local_deployment`；G5 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 操作范围 0.35 / 验证规范 0.30 / 保存确认 0.20 / 证据充分性 0.15（write 型）（锚点见 §2.1）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 56（550fd5ae26b1f06f5fd8）—题面：For this local training variant, the following are supplied training product facts. Set the Premium Leather Wallet Description to exactly the text inside the quotation marks, excluding the quotation marks: "Premium Leather Wallet: leather exterior, six card slots and one banknote compartment. Dimensions: 11 cm wide, 9 cm high and 2 cm deep.". Save the change.
- **分支：** `admin_contract_rules.checks:update`
- **原固定分母：** 4（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标对象身份正确；G2 `persisted_requested_value`（目标字段最终值整体满足 update_matches，含题面全部要求字段）；G3 `other_records_unchanged`；G4 `same_local_deployment`；G5 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 操作范围 0.35 / 验证规范 0.30 / 保存确认 0.20 / 证据充分性 0.15（write 型）（锚点见 §2.1）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 64（6539ca3a65bcebbf51e2）—题面：Edit the unsent newsletter with subject Training queued update. Save its body as The local training promotion starts on December 1, 2026. Keep it unsent; do not schedule or send it.
- **分支：** `admin_contract_rules.checks:update`
- **原固定分母：** 2（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标对象身份正确；G2 `persisted_requested_value`（目标字段最终值整体满足 update_matches，含题面全部要求字段）；G3 `other_records_unchanged`；G4 `same_local_deployment`；G5 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 操作范围 0.35 / 验证规范 0.30 / 保存确认 0.20 / 证据充分性 0.15（write 型）（锚点见 §2.1）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 73（727b8a237690197b467e）—题面：For this local training variant, save Gaming Laptop meta title as "Gaming Laptop | Training Store" and meta description as "Explore the Gaming Laptop in the Training Store catalog."
- **分支：** `admin_contract_rules.checks:update`
- **原固定分母：** 2（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标对象身份正确；G2 `persisted_requested_value`（目标字段最终值整体满足 update_matches，含题面全部要求字段）；G3 `other_records_unchanged`；G4 `same_local_deployment`；G5 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 操作范围 0.35 / 验证规范 0.30 / 保存确认 0.20 / 证据充分性 0.15（write 型）（锚点见 §2.1）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 78（7d0076c89c2e731e77c8）—题面：For this local training variant, override the default USD currency symbol with US$ and save Currency Symbols.
- **分支：** `admin_contract_rules.checks:update`
- **原固定分母：** 2（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标对象身份正确；G2 `persisted_requested_value`（目标字段最终值整体满足 update_matches，含题面全部要求字段）；G3 `other_records_unchanged`；G4 `same_local_deployment`；G5 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 操作范围 0.35 / 验证规范 0.30 / 保存确认 0.20 / 证据充分性 0.15（write 型）（锚点见 §2.1）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 90（9ac8c191d8e0026c7a39）—题面：For this local training variant, reference date is September 30, 2026. Set Blue T-Shirt as new from September 30 through October 30, 2026 and save.
- **分支：** `admin_contract_rules.checks:update`
- **原固定分母：** 2（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标对象身份正确；G2 `persisted_requested_value`（目标字段最终值整体满足 update_matches，含题面全部要求字段）；G3 `other_records_unchanged`；G4 `same_local_deployment`；G5 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 操作范围 0.35 / 验证规范 0.30 / 保存确认 0.20 / 证据充分性 0.15（write 型）（锚点见 §2.1）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 119（bb087733414d726c2d50）—题面：For this local training variant, save Blue T-Shirt meta title as "Blue T-Shirt | Training Store" and meta description as "Browse the Blue T-Shirt in the Training Store catalog."
- **分支：** `admin_contract_rules.checks:update`
- **原固定分母：** 2（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标对象身份正确；G2 `persisted_requested_value`（目标字段最终值整体满足 update_matches，含题面全部要求字段）；G3 `other_records_unchanged`；G4 `same_local_deployment`；G5 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 操作范围 0.35 / 验证规范 0.30 / 保存确认 0.20 / 证据充分性 0.15（write 型）（锚点见 §2.1）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 123（be7cead538c9af903316）—题面：For this local training variant, save Maya Tunic meta title as "Maya Tunic | Training Store" and meta description as "Browse the Maya Tunic in the Training Store catalog.".
- **分支：** `admin_contract_rules.checks:update`
- **原固定分母：** 2（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标对象身份正确；G2 `persisted_requested_value`（目标字段最终值整体满足 update_matches，含题面全部要求字段）；G3 `other_records_unchanged`；G4 `same_local_deployment`；G5 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 操作范围 0.35 / 验证规范 0.30 / 保存确认 0.20 / 证据充分性 0.15（write 型）（锚点见 §2.1）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 134（ce00fc4dc07e7d61dd52）—题面：For this local training variant, enable Allow Gift Message for Blue T-Shirt, overriding the default setting, and save.
- **分支：** `admin_contract_rules.checks:update`
- **原固定分母：** 2（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标对象身份正确；G2 `persisted_requested_value`（目标字段最终值整体满足 update_matches，含题面全部要求字段）；G3 `other_records_unchanged`；G4 `same_local_deployment`；G5 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 操作范围 0.35 / 验证规范 0.30 / 保存确认 0.20 / 证据充分性 0.15（write 型）（锚点见 §2.1）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 147（d9eedb3a01d7ba055979）—题面：For this local training variant, edit the existing URL rewrite in Default Store View: request path training-product-entry, target path catalog/product/view/id/1, redirect type Permanent (301). Save it.
- **分支：** `admin_contract_rules.checks:update`
- **原固定分母：** 2（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标对象身份正确；G2 `persisted_requested_value`（目标字段最终值整体满足 update_matches，含题面全部要求字段）；G3 `other_records_unchanged`；G4 `same_local_deployment`；G5 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 操作范围 0.35 / 验证规范 0.30 / 保存确认 0.20 / 证据充分性 0.15（write 型）（锚点见 §2.1）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

### 3.2 create 型（29 题）

#### 题目 4（043df48c57af4a1b4de8）—题面：For this local training variant, create a product attribute with label Training Color, attribute code training_color and Text Field input type. Save it without changing the existing color attribute.
- **分支：** `admin_contract_rules.checks:create`
- **原固定分母：** 4（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 使用题面指定账号/目标；G2 `new_matching_record_saved`（恰好一条新记录）；G3 `created_record_conditions`（新记录整体满足全部字段）；G4 `existing_records_unchanged`；G5 `same_local_deployment`；G6 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 操作范围 0.35 / 验证规范 0.30 / 保存确认 0.20 / 证据充分性 0.15（write 型）（锚点见 §2.2）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 7（06d6dd1b987d04ba2032）—题面：Create and save a new customer named Training Customer with email admin-06d6dd1b987d04ba2032@example.test and customer group Wholesale Customers. Keep valid defaults for unspecified optional fields.
- **分支：** `admin_contract_rules.checks:create`
- **原固定分母：** 4（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 使用题面指定账号/目标；G2 `new_matching_record_saved`（恰好一条新记录）；G3 `created_record_conditions`（新记录整体满足全部字段）；G4 `existing_records_unchanged`；G5 `same_local_deployment`；G6 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 操作范围 0.35 / 验证规范 0.30 / 保存确认 0.20 / 证据充分性 0.15（write 型）（锚点见 §2.2）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 8（0adfc625f5e41270cf99）—题面：Create a new customer account for John Smith with email johnsmith@example.com
- **分支：** `admin_contract_rules.checks:create`
- **原固定分母：** 3（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 使用题面指定账号/目标；G2 `new_matching_record_saved`（恰好一条新记录）；G3 `created_record_conditions`（新记录整体满足全部字段）；G4 `existing_records_unchanged`；G5 `same_local_deployment`；G6 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 操作范围 0.35 / 验证规范 0.30 / 保存确认 0.20 / 证据充分性 0.15（write 型）（锚点见 §2.2）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 28（2cf60b2bee0001aff88b）—题面：Create and save a new customer named Training Customer with email admin-2cf60b2bee0001aff88b@example.test. Keep valid defaults for unspecified optional fields.
- **分支：** `admin_contract_rules.checks:create`
- **原固定分母：** 3（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 使用题面指定账号/目标；G2 `new_matching_record_saved`（恰好一条新记录）；G3 `created_record_conditions`（新记录整体满足全部字段）；G4 `existing_records_unchanged`；G5 `same_local_deployment`；G6 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 操作范围 0.35 / 验证规范 0.30 / 保存确认 0.20 / 证据充分性 0.15（write 型）（锚点见 §2.2）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 32（3023c4dedd7221a00b2c）—题面：Create and save a simple product named Training Product 3023c4, SKU TRAIN-3023c4dedd7221a00b2c, price 9.99. Keep valid defaults for unspecified settings.
- **分支：** `admin_contract_rules.checks:create`
- **原固定分母：** 4（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 使用题面指定账号/目标；G2 `new_matching_record_saved`（恰好一条新记录）；G3 `created_record_conditions`（新记录整体满足全部字段）；G4 `existing_records_unchanged`；G5 `same_local_deployment`；G6 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 操作范围 0.35 / 验证规范 0.30 / 保存确认 0.20 / 证据充分性 0.15（write 型）（锚点见 §2.2）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 47（4669e83f3f415914e5aa）—题面：Create a customer group named "VIP Customers" and exclude the "Main Website" from this group.
- **分支：** `admin_contract_rules.checks:create`
- **原固定分母：** 3（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 使用题面指定账号/目标；G2 `new_matching_record_saved`（恰好一条新记录）；G3 `created_record_conditions`（新记录整体满足全部字段）；G4 `existing_records_unchanged`；G5 `same_local_deployment`；G6 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 操作范围 0.35 / 验证规范 0.30 / 保存确认 0.20 / 证据充分性 0.15（write 型）（锚点见 §2.2）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 58（586f3f8ccec8d42e4142）—题面：For this local training variant, create the email template named "Training Customer Update". Save subject "Your store update" and body exactly "Thank you for shopping at our training store.".
- **分支：** `admin_contract_rules.checks:create`
- **原固定分母：** 4（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 使用题面指定账号/目标；G2 `new_matching_record_saved`（恰好一条新记录）；G3 `created_record_conditions`（新记录整体满足全部字段）；G4 `existing_records_unchanged`；G5 `same_local_deployment`；G6 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 操作范围 0.35 / 验证规范 0.30 / 保存确认 0.20 / 证据充分性 0.15（write 型）（锚点见 §2.2）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 60（6092ffb2a3014d7b5e02）—题面：Create and save a new customer named Training Customer with email admin-6092ffb2a3014d7b5e02@example.test and taxvat TRAINING-VAT-100. Keep valid defaults for unspecified optional fields.
- **分支：** `admin_contract_rules.checks:create`
- **原固定分母：** 4（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 使用题面指定账号/目标；G2 `new_matching_record_saved`（恰好一条新记录）；G3 `created_record_conditions`（新记录整体满足全部字段）；G4 `existing_records_unchanged`；G5 `same_local_deployment`；G6 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 操作范围 0.35 / 验证规范 0.30 / 保存确认 0.20 / 证据充分性 0.15（write 型）（锚点见 §2.2）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 67（6b630bcc794fbd170809）—题面：For this local training variant, create a custom URL rewrite in Default Store View: request path training-old-category, target path catalog/category/view/id/2, redirect type Permanent (301). Save it.
- **分支：** `admin_contract_rules.checks:create`
- **原固定分母：** 4（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 使用题面指定账号/目标；G2 `new_matching_record_saved`（恰好一条新记录）；G3 `created_record_conditions`（新记录整体满足全部字段）；G4 `existing_records_unchanged`；G5 `same_local_deployment`；G6 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 操作范围 0.35 / 验证规范 0.30 / 保存确认 0.20 / 证据充分性 0.15（write 型）（锚点见 §2.2）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 70（6d9d8bc43ae2c1b8ef1a）—题面：For this local training variant, create and save a CMS block for later homepage use with identifier training_home_welcome, title Training Home Welcome, and body Welcome to the training store. Assign it to All Store Views. Publishing or inserting the block into a homepage is outside this task.
- **分支：** `admin_contract_rules.checks:create`
- **原固定分母：** 5（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 使用题面指定账号/目标；G2 `new_matching_record_saved`（恰好一条新记录）；G3 `created_record_conditions`（新记录整体满足全部字段）；G4 `existing_records_unchanged`；G5 `same_local_deployment`；G6 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 操作范围 0.35 / 验证规范 0.30 / 保存确认 0.20 / 证据充分性 0.15（write 型）（锚点见 §2.2）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 75（7b1058619b6bdffb1663）—题面：Create and save a simple product named Training Product 7b1058, SKU TRAIN-7b1058619b6bdffb1663, price 9.99. Keep valid defaults for unspecified settings.
- **分支：** `admin_contract_rules.checks:create`
- **原固定分母：** 4（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 使用题面指定账号/目标；G2 `new_matching_record_saved`（恰好一条新记录）；G3 `created_record_conditions`（新记录整体满足全部字段）；G4 `existing_records_unchanged`；G5 `same_local_deployment`；G6 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 操作范围 0.35 / 验证规范 0.30 / 保存确认 0.20 / 证据充分性 0.15（write 型）（锚点见 §2.2）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 77（7cf15a94c97d28cbe0f7）—题面：Create a new customer group named "VIP Customers" with Retail Customer tax class.
- **分支：** `admin_contract_rules.checks:create`
- **原固定分母：** 3（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 使用题面指定账号/目标；G2 `new_matching_record_saved`（恰好一条新记录）；G3 `created_record_conditions`（新记录整体满足全部字段）；G4 `existing_records_unchanged`；G5 `same_local_deployment`；G6 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 操作范围 0.35 / 验证规范 0.30 / 保存确认 0.20 / 证据充分性 0.15（write 型）（锚点见 §2.2）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 81（85dadbc00c3440ad28a7）—题面：Create and save a new customer named Training Customer with email admin-85dadbc00c3440ad28a7@example.test. Keep valid defaults for unspecified optional fields.
- **分支：** `admin_contract_rules.checks:create`
- **原固定分母：** 3（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 使用题面指定账号/目标；G2 `new_matching_record_saved`（恰好一条新记录）；G3 `created_record_conditions`（新记录整体满足全部字段）；G4 `existing_records_unchanged`；G5 `same_local_deployment`；G6 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 操作范围 0.35 / 验证规范 0.30 / 保存确认 0.20 / 证据充分性 0.15（write 型）（锚点见 §2.2）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 91（9cc731fdb292beb61a5e）—题面：For this local training variant, create Training Customer with email training.customer@example.test on Main Website and send the welcome email from Default Store View. Email delivery is captured in the isolated local mailbox.
- **分支：** `admin_contract_rules.checks:create`
- **原固定分母：** 6（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 使用题面指定账号/目标；G2 `new_matching_record_saved`（恰好一条新记录）；G3 `created_record_conditions`（新记录整体满足全部字段）；G4 `existing_records_unchanged`；G5 `same_local_deployment`；G6 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 操作范围 0.35 / 验证规范 0.30 / 保存确认 0.20 / 证据充分性 0.15（write 型）（锚点见 §2.2）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 100（a4bd8f38e37459668308）—题面：For this local training variant, create a custom URL rewrite in Default Store View: request path training-catalog-entry, target path catalog/category/view/id/2, redirect type Permanent (301). Save it.
- **分支：** `admin_contract_rules.checks:create`
- **原固定分母：** 4（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 使用题面指定账号/目标；G2 `new_matching_record_saved`（恰好一条新记录）；G3 `created_record_conditions`（新记录整体满足全部字段）；G4 `existing_records_unchanged`；G5 `same_local_deployment`；G6 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 操作范围 0.35 / 验证规范 0.30 / 保存确认 0.20 / 证据充分性 0.15（write 型）（锚点见 §2.2）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 106（afacd2e2ed0b749f7af1）—题面：For this local training variant, create and save a subcategory named Training Subcategory directly under New Category Name.
- **分支：** `admin_contract_rules.checks:create`
- **原固定分母：** 3（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 使用题面指定账号/目标；G2 `new_matching_record_saved`（恰好一条新记录）；G3 `created_record_conditions`（新记录整体满足全部字段）；G4 `existing_records_unchanged`；G5 `same_local_deployment`；G6 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 操作范围 0.35 / 验证规范 0.30 / 保存确认 0.20 / 证据充分性 0.15（write 型）（锚点见 §2.2）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 108（b22941cc28e820b8bc0c）—题面：Create and save a new customer named Training Customer with email admin-b22941cc28e820b8bc0c@example.test and taxvat TRAINING-VAT-101. Keep valid defaults for unspecified optional fields.
- **分支：** `admin_contract_rules.checks:create`
- **原固定分母：** 4（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 使用题面指定账号/目标；G2 `new_matching_record_saved`（恰好一条新记录）；G3 `created_record_conditions`（新记录整体满足全部字段）；G4 `existing_records_unchanged`；G5 `same_local_deployment`；G6 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 操作范围 0.35 / 验证规范 0.30 / 保存确认 0.20 / 证据充分性 0.15（write 型）（锚点见 §2.2）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 111（b67dfdb5d15dbb4d199f）—题面：For this local training variant, create the newsletter template named "Training Holiday Promotion". Save subject "Training holiday offer" and body exactly "Training offer: ten percent off selected products from December 1 through December 7, 2026.". Use sender name Training Store and sender email store@example.test. Do not send or queue the newsletter.
- **分支：** `admin_contract_rules.checks:create`
- **原固定分母：** 6（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 使用题面指定账号/目标；G2 `new_matching_record_saved`（恰好一条新记录）；G3 `created_record_conditions`（新记录整体满足全部字段）；G4 `existing_records_unchanged`；G5 `same_local_deployment`；G6 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 操作范围 0.35 / 验证规范 0.30 / 保存确认 0.20 / 证据充分性 0.15（write 型）（锚点见 §2.2）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 114（b82e145d0549d511622d）—题面：Create and save a new customer named Training Customer with email admin-b82e145d0549d511622d@example.test and customer group VIP Customers. Keep valid defaults for unspecified optional fields.
- **分支：** `admin_contract_rules.checks:create`
- **原固定分母：** 4（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 使用题面指定账号/目标；G2 `new_matching_record_saved`（恰好一条新记录）；G3 `created_record_conditions`（新记录整体满足全部字段）；G4 `existing_records_unchanged`；G5 `same_local_deployment`；G6 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 操作范围 0.35 / 验证规范 0.30 / 保存确认 0.20 / 证据充分性 0.15（write 型）（锚点见 §2.2）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 127（c0bcd7963046f155b1aa）—题面：Create and save a new customer named Training Customer with email admin-c0bcd7963046f155b1aa@example.test and customer group VIP Customers, date of birth 1990-01-15, gender Male. Keep valid defaults for unspecified optional fields.
- **分支：** `admin_contract_rules.checks:create`
- **原固定分母：** 6（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 使用题面指定账号/目标；G2 `new_matching_record_saved`（恰好一条新记录）；G3 `created_record_conditions`（新记录整体满足全部字段）；G4 `existing_records_unchanged`；G5 `same_local_deployment`；G6 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 操作范围 0.35 / 验证规范 0.30 / 保存确认 0.20 / 证据充分性 0.15（write 型）（锚点见 §2.2）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 132（cc2fff7007c02443f285）—题面：Create and save a simple product named Training Product cc2fff, SKU TRAIN-cc2fff7007c02443f285, price 9.99. Keep valid defaults for unspecified settings.
- **分支：** `admin_contract_rules.checks:create`
- **原固定分母：** 4（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 使用题面指定账号/目标；G2 `new_matching_record_saved`（恰好一条新记录）；G3 `created_record_conditions`（新记录整体满足全部字段）；G4 `existing_records_unchanged`；G5 `same_local_deployment`；G6 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 操作范围 0.35 / 验证规范 0.30 / 保存确认 0.20 / 证据充分性 0.15（write 型）（锚点见 §2.2）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 138（d1463ce7357f4c066d3a）—题面：Add a new product named "Sony Headphones" with SKU "SH123" and a price of $199.99.
- **分支：** `admin_contract_rules.checks:create`
- **原固定分母：** 4（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 使用题面指定账号/目标；G2 `new_matching_record_saved`（恰好一条新记录）；G3 `created_record_conditions`（新记录整体满足全部字段）；G4 `existing_records_unchanged`；G5 `same_local_deployment`；G6 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 操作范围 0.35 / 验证规范 0.30 / 保存确认 0.20 / 证据充分性 0.15（write 型）（锚点见 §2.2）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 140（d3ff3426f3fdcea375d4）—题面：For this local training variant, create and save a subcategory named Training Organized Products directly under Default Category.
- **分支：** `admin_contract_rules.checks:create`
- **原固定分母：** 3（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 使用题面指定账号/目标；G2 `new_matching_record_saved`（恰好一条新记录）；G3 `created_record_conditions`（新记录整体满足全部字段）；G4 `existing_records_unchanged`；G5 `same_local_deployment`；G6 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 操作范围 0.35 / 验证规范 0.30 / 保存确认 0.20 / 证据充分性 0.15（write 型）（锚点见 §2.2）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 142（d555e57bbc134c2d89c5）—题面：Create a customer group named VIP Customers, exclude Main Website, and save the group.
- **分支：** `admin_contract_rules.checks:create`
- **原固定分母：** 3（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 使用题面指定账号/目标；G2 `new_matching_record_saved`（恰好一条新记录）；G3 `created_record_conditions`（新记录整体满足全部字段）；G4 `existing_records_unchanged`；G5 `same_local_deployment`；G6 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 操作范围 0.35 / 验证规范 0.30 / 保存确认 0.20 / 证据充分性 0.15（write 型）（锚点见 §2.2）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 143（d5625da1a9cdb07f180b）—题面：Create and save a simple product named Training Product d5625d, SKU TRAIN-d5625da1a9cdb07f180b, price 9.99, stock quantity 100. Keep valid defaults for unspecified settings.
- **分支：** `admin_contract_rules.checks:create`
- **原固定分母：** 5（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 使用题面指定账号/目标；G2 `new_matching_record_saved`（恰好一条新记录）；G3 `created_record_conditions`（新记录整体满足全部字段）；G4 `existing_records_unchanged`；G5 `same_local_deployment`；G6 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 操作范围 0.35 / 验证规范 0.30 / 保存确认 0.20 / 证据充分性 0.15（write 型）（锚点见 §2.2）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 145（d6ca61ffbbc704a34880）—题面：Create a new customer account with the name "John Smith" and email "john.smith@example.com"
- **分支：** `admin_contract_rules.checks:create`
- **原固定分母：** 3（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 使用题面指定账号/目标；G2 `new_matching_record_saved`（恰好一条新记录）；G3 `created_record_conditions`（新记录整体满足全部字段）；G4 `existing_records_unchanged`；G5 `same_local_deployment`；G6 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 操作范围 0.35 / 验证规范 0.30 / 保存确认 0.20 / 证据充分性 0.15（write 型）（锚点见 §2.2）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 148（dd3ea545f0d5d4ec39e7）—题面：Create a new customer group named "VIP Clients" with the tax class set to "Wholesale" and excluding the "Main Website".
- **分支：** `admin_contract_rules.checks:create`
- **原固定分母：** 4（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 使用题面指定账号/目标；G2 `new_matching_record_saved`（恰好一条新记录）；G3 `created_record_conditions`（新记录整体满足全部字段）；G4 `existing_records_unchanged`；G5 `same_local_deployment`；G6 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 操作范围 0.35 / 验证规范 0.30 / 保存确认 0.20 / 证据充分性 0.15（write 型）（锚点见 §2.2）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 151（e59148d1ae21a34456e6）—题面：Create and save a simple product named Training Product e59148, SKU TRAIN-e59148d1ae21a34456e6, price 9.99. Keep valid defaults for unspecified settings.
- **分支：** `admin_contract_rules.checks:create`
- **原固定分母：** 4（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 使用题面指定账号/目标；G2 `new_matching_record_saved`（恰好一条新记录）；G3 `created_record_conditions`（新记录整体满足全部字段）；G4 `existing_records_unchanged`；G5 `same_local_deployment`；G6 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 操作范围 0.35 / 验证规范 0.30 / 保存确认 0.20 / 证据充分性 0.15（write 型）（锚点见 §2.2）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 160（fb397ea55485dc33f943）—题面：Create and save a new customer named Training Customer with email admin-fb397ea55485dc33f943@example.test. Keep valid defaults for unspecified optional fields.
- **分支：** `admin_contract_rules.checks:create`
- **原固定分母：** 3（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 使用题面指定账号/目标；G2 `new_matching_record_saved`（恰好一条新记录）；G3 `created_record_conditions`（新记录整体满足全部字段）；G4 `existing_records_unchanged`；G5 `same_local_deployment`；G6 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 操作范围 0.35 / 验证规范 0.30 / 保存确认 0.20 / 证据充分性 0.15（write 型）（锚点见 §2.2）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

### 3.3 query 型（6 题）

#### 题目 17（1a50d30e5d14712ec9d0）—题面：For this local training variant, retrieve the default billing phone number and ZIP code of Jane Doe (jane.doe@gmail.com). The initial snapshot places this existing customer in VIP Customers.
- **分支：** `admin_contract_rules.checks:query`
- **原固定分母：** 2（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_<字段>` 全部字段值与参考值精确匹配；G3 `records_unchanged`；G4 `same_local_deployment`；G5 `valid_authenticated_page`；G6 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.3）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 57（5786c998736d427970a6）—题面：Check the shipping address for the credit memo.
- **分支：** `admin_contract_rules.checks:query`
- **原固定分母：** 3（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_<字段>` 全部字段值与参考值精确匹配；G3 `records_unchanged`；G4 `same_local_deployment`；G5 `valid_authenticated_page`；G6 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.3）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 80（8502336fbff28609722e）—题面：View the shipping details for order #000000001.
- **分支：** `admin_contract_rules.checks:query`
- **原固定分母：** 3（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_<字段>` 全部字段值与参考值精确匹配；G3 `records_unchanged`；G4 `same_local_deployment`；G5 `valid_authenticated_page`；G6 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.3）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 99（a3b7eedd09ab8fbc3bae）—题面：Check the shipping address for order #000000002
- **分支：** `admin_contract_rules.checks:query`
- **原固定分母：** 3（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_<字段>` 全部字段值与参考值精确匹配；G3 `records_unchanged`；G4 `same_local_deployment`；G5 `valid_authenticated_page`；G6 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.3）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 110（b4f2a38f0daad2fcf5a6）—题面：Check the shipping address for shipment #000000001.
- **分支：** `admin_contract_rules.checks:query`
- **原固定分母：** 3（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_<字段>` 全部字段值与参考值精确匹配；G3 `records_unchanged`；G4 `same_local_deployment`；G5 `valid_authenticated_page`；G6 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.3）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 121（bbdb63236829567f8199）—题面：Check which country and state Adam Garcia is from For this local training variant, the target account email is adam.garcia@gmail.com.
- **分支：** `admin_contract_rules.checks:query`
- **原固定分母：** 2（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_<字段>` 全部字段值与参考值精确匹配；G3 `records_unchanged`；G4 `same_local_deployment`；G5 `valid_authenticated_page`；G6 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.3）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

### 3.4 collection_query 型（20 题）

#### 题目 18（1af036a267a8429d2fc9）—题面：Search for customers living in New York state
- **分支：** `admin_contract_rules.checks:collection_query`
- **原固定分母：** 12（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 过滤条件正确；G2 `exact_result_set`（完整多重集合：无遗漏/无多余/无重复）；G3 `records_unchanged`；G4 `same_local_deployment`；G5 `valid_authenticated_page`；G6 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 完整性 0.35 / 搜索条件准确性 0.30 / 来源合规 0.20 / 证据充分性 0.15（锚点见 §2.4）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 22（1d838691d0e90160f0c6）—题面：Check which customer groups are available for new customer creation
- **分支：** `admin_contract_rules.checks:collection_query`
- **原固定分母：** 3（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 过滤条件正确；G2 `exact_result_set`（完整多重集合：无遗漏/无多余/无重复）；G3 `records_unchanged`；G4 `same_local_deployment`；G5 `valid_authenticated_page`；G6 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 完整性 0.35 / 搜索条件准确性 0.30 / 来源合规 0.20 / 证据充分性 0.15（锚点见 §2.4）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 24（23b872112e21eec243e8）—题面：Report the five most recently placed orders, including order number, customer name, and grand total. Break timestamp ties by ascending internal order ID.
- **分支：** `admin_contract_rules.checks:collection_query`
- **原固定分母：** 3（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 过滤条件正确；G2 `exact_result_set`（完整多重集合：无遗漏/无多余/无重复）；G3 `records_unchanged`；G4 `same_local_deployment`；G5 `valid_authenticated_page`；G6 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 完整性 0.35 / 搜索条件准确性 0.30 / 来源合规 0.20 / 证据充分性 0.15（锚点见 §2.4）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 27（294e440ada4fcc494444）—题面：Find all products with less than 100 units in stock
- **分支：** `admin_contract_rules.checks:collection_query`
- **原固定分母：** 3（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 过滤条件正确；G2 `exact_result_set`（完整多重集合：无遗漏/无多余/无重复）；G3 `records_unchanged`；G4 `same_local_deployment`；G5 `valid_authenticated_page`；G6 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 完整性 0.35 / 搜索条件准确性 0.30 / 来源合规 0.20 / 证据充分性 0.15（锚点见 §2.4）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 30（2e437c6ebc27184225c5）—题面：Review existing CMS pages and their content status
- **分支：** `admin_contract_rules.checks:collection_query`
- **原固定分母：** 12（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 过滤条件正确；G2 `exact_result_set`（完整多重集合：无遗漏/无多余/无重复）；G3 `records_unchanged`；G4 `same_local_deployment`；G5 `valid_authenticated_page`；G6 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 完整性 0.35 / 搜索条件准确性 0.30 / 来源合规 0.20 / 证据充分性 0.15（锚点见 §2.4）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 37（39289e43a355500e8c35）—题面：Report the five search terms with the highest number of uses, including each query text and its number of uses. Include all ties at the cutoff only if they fit within the first five records ordered by query ID.
- **分支：** `admin_contract_rules.checks:collection_query`
- **原固定分母：** 10（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 过滤条件正确；G2 `exact_result_set`（完整多重集合：无遗漏/无多余/无重复）；G3 `records_unchanged`；G4 `same_local_deployment`；G5 `valid_authenticated_page`；G6 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 完整性 0.35 / 搜索条件准确性 0.30 / 来源合规 0.20 / 证据充分性 0.15（锚点见 §2.4）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 46（4610743cece3a992dce5）—题面：Find all orders placed by Adam Garcia
- **分支：** `admin_contract_rules.checks:collection_query`
- **原固定分母：** 13（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 过滤条件正确；G2 `exact_result_set`（完整多重集合：无遗漏/无多余/无重复）；G3 `records_unchanged`；G4 `same_local_deployment`；G5 `valid_authenticated_page`；G6 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 完整性 0.35 / 搜索条件准确性 0.30 / 来源合规 0.20 / 证据充分性 0.15（锚点见 §2.4）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 66（690ff879812bbe4d14e5）—题面：Find all customers whose gender is Female and report their names and email addresses.
- **分支：** `admin_contract_rules.checks:collection_query`
- **原固定分母：** 2（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 过滤条件正确；G2 `exact_result_set`（完整多重集合：无遗漏/无多余/无重复）；G3 `records_unchanged`；G4 `same_local_deployment`；G5 `valid_authenticated_page`；G6 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 完整性 0.35 / 搜索条件准确性 0.30 / 来源合规 0.20 / 证据充分性 0.15（锚点见 §2.4）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 72（71a327bcbaf0135b6c69）—题面：Check what product was refunded in order #000000002
- **分支：** `admin_contract_rules.checks:collection_query`
- **原固定分母：** 3（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 过滤条件正确；G2 `exact_result_set`（完整多重集合：无遗漏/无多余/无重复）；G3 `records_unchanged`；G4 `same_local_deployment`；G5 `valid_authenticated_page`；G6 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 完整性 0.35 / 搜索条件准确性 0.30 / 来源合规 0.20 / 证据充分性 0.15（锚点见 §2.4）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 88（95ee0e2712ebe1df0764）—题面：Generate a list of customers who have confirmed their email address
- **分支：** `admin_contract_rules.checks:collection_query`
- **原固定分母：** 140（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 过滤条件正确；G2 `exact_result_set`（完整多重集合：无遗漏/无多余/无重复）；G3 `records_unchanged`；G4 `same_local_deployment`；G5 `valid_authenticated_page`；G6 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 完整性 0.35 / 搜索条件准确性 0.30 / 来源合规 0.20 / 证据充分性 0.15（锚点见 §2.4）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 92（9e5f8a4ab82a3ef3d219）—题面：Find all customers located in Texas
- **分支：** `admin_contract_rules.checks:collection_query`
- **原固定分母：** 24（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 过滤条件正确；G2 `exact_result_set`（完整多重集合：无遗漏/无多余/无重复）；G3 `records_unchanged`；G4 `same_local_deployment`；G5 `valid_authenticated_page`；G6 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 完整性 0.35 / 搜索条件准确性 0.30 / 来源合规 0.20 / 证据充分性 0.15（锚点见 §2.4）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 93（9f1a9b9ca85961ed9cdc）—题面：View the email addresses of all customers
- **分支：** `admin_contract_rules.checks:collection_query`
- **原固定分母：** 70（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 过滤条件正确；G2 `exact_result_set`（完整多重集合：无遗漏/无多余/无重复）；G3 `records_unchanged`；G4 `same_local_deployment`；G5 `valid_authenticated_page`；G6 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 完整性 0.35 / 搜索条件准确性 0.30 / 来源合规 0.20 / 证据充分性 0.15（锚点见 §2.4）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 94（9f2e3f4d60b9e2df2df2）—题面：Identify all customers from the United States with phone numbers in the 212 area code
- **分支：** `admin_contract_rules.checks:collection_query`
- **原固定分母：** 10（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 过滤条件正确；G2 `exact_result_set`（完整多重集合：无遗漏/无多余/无重复）；G3 `records_unchanged`；G4 `same_local_deployment`；G5 `valid_authenticated_page`；G6 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 完整性 0.35 / 搜索条件准确性 0.30 / 来源合规 0.20 / 证据充分性 0.15（锚点见 §2.4）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 101（a67ffb7494750efde4d3）—题面：Find all products that have "Hoodie" in the name
- **分支：** `admin_contract_rules.checks:collection_query`
- **原固定分母：** 396（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 过滤条件正确；G2 `exact_result_set`（完整多重集合：无遗漏/无多余/无重复）；G3 `records_unchanged`；G4 `same_local_deployment`；G5 `valid_authenticated_page`；G6 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 完整性 0.35 / 搜索条件准确性 0.30 / 来源合规 0.20 / 证据充分性 0.15（锚点见 §2.4）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 115（b8a621852314fabd2c90）—题面：List all customers with the ZIP code 75201.
- **分支：** `admin_contract_rules.checks:collection_query`
- **原固定分母：** 12（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 过滤条件正确；G2 `exact_result_set`（完整多重集合：无遗漏/无多余/无重复）；G3 `records_unchanged`；G4 `same_local_deployment`；G5 `valid_authenticated_page`；G6 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 完整性 0.35 / 搜索条件准确性 0.30 / 来源合规 0.20 / 证据充分性 0.15（锚点见 §2.4）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 116（b920ab04dc686ce6354f）—题面：View details about the refunded Minerva LumaTech™ V-Tee product
- **分支：** `admin_contract_rules.checks:collection_query`
- **原固定分母：** 3（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 过滤条件正确；G2 `exact_result_set`（完整多重集合：无遗漏/无多余/无重复）；G3 `records_unchanged`；G4 `same_local_deployment`；G5 `valid_authenticated_page`；G6 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 完整性 0.35 / 搜索条件准确性 0.30 / 来源合规 0.20 / 证据充分性 0.15（锚点见 §2.4）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 128（c2d9e62db8793636a7a2）—题面：Report all recorded search terms, including each term, its number of uses, and its number of search results.
- **分支：** `admin_contract_rules.checks:collection_query`
- **原固定分母：** 3（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 过滤条件正确；G2 `exact_result_set`（完整多重集合：无遗漏/无多余/无重复）；G3 `records_unchanged`；G4 `same_local_deployment`；G5 `valid_authenticated_page`；G6 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 完整性 0.35 / 搜索条件准确性 0.30 / 来源合规 0.20 / 证据充分性 0.15（锚点见 §2.4）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 129（c2fcbc0f3dd3445dd358）—题面：Report the five most recently placed orders, including order number, customer name, and grand total. Break timestamp ties by ascending internal order ID.
- **分支：** `admin_contract_rules.checks:collection_query`
- **原固定分母：** 3（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 过滤条件正确；G2 `exact_result_set`（完整多重集合：无遗漏/无多余/无重复）；G3 `records_unchanged`；G4 `same_local_deployment`；G5 `valid_authenticated_page`；G6 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 完整性 0.35 / 搜索条件准确性 0.30 / 来源合规 0.20 / 证据充分性 0.15（锚点见 §2.4）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 136（d03c2b089580e79d83f0）—题面：List customers whose Account Created in field is Default Store View, including their names and email addresses.
- **分支：** `admin_contract_rules.checks:collection_query`
- **原固定分母：** 140（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 过滤条件正确；G2 `exact_result_set`（完整多重集合：无遗漏/无多余/无重复）；G3 `records_unchanged`；G4 `same_local_deployment`；G5 `valid_authenticated_page`；G6 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 完整性 0.35 / 搜索条件准确性 0.30 / 来源合规 0.20 / 证据充分性 0.15（锚点见 §2.4）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 159（f8a3e7d1108c55158a9d）—题面：View all customers from the United States
- **分支：** `admin_contract_rules.checks:collection_query`
- **原固定分母：** 140（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 过滤条件正确；G2 `exact_result_set`（完整多重集合：无遗漏/无多余/无重复）；G3 `records_unchanged`；G4 `same_local_deployment`；G5 `valid_authenticated_page`；G6 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 完整性 0.35 / 搜索条件准确性 0.30 / 来源合规 0.20 / 证据充分性 0.15（锚点见 §2.4）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

### 3.5 pdf 型（4 题）

#### 题目 2（01aeb9ebc09ef6d46c3d）—题面：For this local training variant, Select shipments #000000001 and #000000002, and download their packing slips together as a PDF.
- **分支：** `admin_contract_rules.checks:pdf`
- **原固定分母：** 2（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标订单/运单正确；G2 `downloaded_correct_documents`（下载产物内容+选中对象集合匹配）；G3 未生成/购买真实承运标签（题面禁止项）；G4 `records_unchanged`；G5 `same_local_deployment`；G6 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 操作合规 0.30 / 下载确认 0.25 / 证据充分性 0.15（锚点见 §2.5）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 6（05c4cabeb5f7296af901）—题面：For this local training variant, select order #000000002 and download its packing slip PDF.
- **分支：** `admin_contract_rules.checks:pdf`
- **原固定分母：** 4（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标订单/运单正确；G2 `downloaded_correct_documents`（下载产物内容+选中对象集合匹配）；G3 未生成/购买真实承运标签（题面禁止项）；G4 `records_unchanged`；G5 `same_local_deployment`；G6 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 操作合规 0.30 / 下载确认 0.25 / 证据充分性 0.15（锚点见 §2.5）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 86（90171eca733558b91be8）—题面：For this local training variant, select order #000000002 and download its invoice PDF.
- **分支：** `admin_contract_rules.checks:pdf`
- **原固定分母：** 5（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标订单/运单正确；G2 `downloaded_correct_documents`（下载产物内容+选中对象集合匹配）；G3 未生成/购买真实承运标签（题面禁止项）；G4 `records_unchanged`；G5 `same_local_deployment`；G6 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 操作合规 0.30 / 下载确认 0.25 / 证据充分性 0.15（锚点见 §2.5）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 153（e716ca170d71ab432a59）—题面：For this local training variant, Select order #000000002 and download all its available invoice, packing-slip and credit-memo documents as a PDF.
- **分支：** `admin_contract_rules.checks:pdf`
- **原固定分母：** 3（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标订单/运单正确；G2 `downloaded_correct_documents`（下载产物内容+选中对象集合匹配）；G3 未生成/购买真实承运标签（题面禁止项）；G4 `records_unchanged`；G5 `same_local_deployment`；G6 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 操作合规 0.30 / 下载确认 0.25 / 证据充分性 0.15（锚点见 §2.5）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

### 3.6 ordinary_query 型（69 题）

#### 题目 1（00de3e4838fad62957df）—题面：How many reviews does the "Custom Jersey Style St Patrick's Day T Shirts" product have and what is its rating?
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 2（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_<字段>` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 3（02623a13789d0ba87796）—题面：Find my default billing address information
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 7（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_<字段>` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 5（05adaa3aae957f2c3dc0）—题面：Check the shipping method and cost for my order
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 2（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_<字段>` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 10（0d50993fbdf6d32994bb）—题面：Verify the shipping address details for Emma Lopez.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 5（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_shipping_address_lines` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 13（1317a2b60d5f27b6f640）—题面：Find out what categories are available under Sports & Outdoors
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 5（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_categories` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 14（13914fd7d1bf94533456）—题面：Find out what technologies are used in The A11Y Project website.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 10（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_items` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 15（158bf9a1de57867a2ac4）—题面：Find the default billing address for Emma Lopez.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 6（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_<字段>` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 16（1820a8409805e0f44e63）—题面：Find repositories with MIT License on the current page
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 5（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_projects` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 19（1b482d1d92765f6cb6d9）—题面：Retrieve the latest commit message for the a11yproject.com repository.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 2（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_latest_commit_message` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 21（1d095aa28f753677a069）—题面：Explore available data sources for downloading OpenStreetMap data.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 8（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_items` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 23（237e143cb3de228b8d84）—题面：Check what markdown formatting options are available for post creation
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 26（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_items` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 25（2642eb4f6e622c2ff448）—题面：Check the total distance and estimated travel time for the current route
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 2（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_<字段>` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 33（31630bd2bca463862944）—题面：Retrieve the project description for cloud-to-butt.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 2（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_description` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 34（32f1684e1634c615f215）—题面：View all available color options for the St Patricks Day T-Shirt
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 11（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_colors` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 35（365c8f7271b76bca1522）—题面：View the turn-by-turn directions for the current route
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 10（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_steps` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 38（3a321611e2d35a0bd239）—题面：Read and report the project description for The A11Y Project / a11yproject.com.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 2（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_description` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 39（3d44ea22ddda30c59630）—题面：Compare the prices of night vision devices on this page.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 8（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_products` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 41（40fbee5ad66e332b21a4）—题面：List all items currently in the shopping cart.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 3（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_items` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 42（41b2004f1c9ede24b496）—题面：View the available shipping methods for my order
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 2（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_shipping_methods` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 43（44a8860ebdd452352176）—题面：Get the rating and number of reviews for the Pre-baked Gingerbread House Kit Value Pack.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 2（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_<字段>` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 45（45121a4e0f96f3cfecd2）—题面：Find all forums that start with the letter B
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 5（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_items` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 48（46c0329e4f0e6684aa4e）—题面：Discover which websites or projects are currently using the a11y-syntax-highlighting themes
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 7（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_items` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 50（4b5dc32a78f627e9c01a）—题面：Share the current map view using a short link
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 2（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_short_link` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 51（4e31cc1527b413e6648e）—题面：List all OpenStreetMap Local Chapters.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 18（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_items` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 54（50bb0903de04753ac2ac）—题面：Retrieve the step-by-step directions from 40.7900, -73.9600 to 40.6530, -73.9500.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 20（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_steps` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 55（50d1a73742dfe3e4ee1b）—题面：Check what formatting options are available for the submission body
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 26（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_items` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 59（5f6e00767032bff7429e）—题面：Describe how users can control their personal information.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 6（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_policy_text` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 62（620d3e05fa1c9ef6e951）—题面：Find projects that use the MIT license on the Explore page. Consider all non-archived projects accessible to the current account, across the complete project directory.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 52（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_projects` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 65（67f0d4e2c0b41fc6ccef）—题面：List all projects starred by the user.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 3（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_items` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 68（6c8942d0a681b4fd513f）—题面：Explore alternative data download options for large areas.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 8（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_items` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 69（6ccae42e426d87785b76）—题面：Check what price ranges are available for Sports & Outdoors items
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 2（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_ranges` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 71（6eb3af9dd0b4842ac443）—题面：Compare the number of open issues between different projects
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 4（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_projects` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 79（7edbc4e6cbc6ddcc50cf）—题面：Find out what transportation modes are available for directions on OpenStreetMap.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 3（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_options` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 83（8a587b258e1b2f7912a3）—题面：List all projects visible on the GitLab Explore page.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 20（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_projects` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 84（8a9442c36c0705cc4857）—题面：Generate a short link for sharing the current map location
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 2（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_short_link` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 85（8f5196ffd60a7f7dee3c）—题面：Verify if the order total of $365.42 is calculated correctly from the subtotal and shipping costs
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 3（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_<字段>` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 87（92aee5530a26d63ee39e）—题面：Find sports equipment under $100 on the Sports & Outdoors page.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 2（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_products` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 89（967848101ec725a2e28f）—题面：Find the license type for the project Karl Kroening / ffmpeg-python.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 2（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_license_type` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 95（9f53f858718b01fac2eb）—题面：Provide details for the project yjlou / 2019-nCov including its description and number of stars.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 3（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_<字段>` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 97（a15b1eb0903aef00a975）—题面：List the files present in the cloud-to-butt repository.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 6（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_items` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 98（a1b510d8e8901e742f78）—题面：Check what alternative download sources are available for OpenStreetMap data.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 8（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_items` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 102（a68151f38ec0ea3dd185）—题面：View all projects with the MIT license. Consider all non-archived projects accessible to the current account, across the complete project directory.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 52（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_projects` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 103（a7e1ea92dd0e6d344bfe）—题面：Compare the estimated travel times between driving and cycling from New York City to Boston
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 2（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_<字段>` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 104（a98e4da9e07e8b372c7d）—题面：Provide details about the Pre-baked Gingerbread House Kit Value Pack.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 3（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_<字段>` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 105（aa3f32f9b51bb452536c）—题面：List all items in the shopping cart with their quantities and prices.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 3（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_items` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 107（b0583d36f1dda1d88ac8）—题面：Find projects that use the MIT license. Consider all non-archived projects accessible to the current account, across the complete project directory.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 52（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_projects` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 109（b3db05d3ef6a3075e584）—题面：Verify the selected shipping address for my current shopping cart. Do not place an order.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 5（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_shipping_address_lines` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 112（b7cc5c99dd61d8e99c2c）—题面：Find out what types of personal information the website collects from users.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 4（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_items` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 113（b827e4e29d1845d4c43a）—题面：Check what transportation options are available for getting directions in OpenStreetMap
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 3（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_options` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 117（b9915bc8913e7309cc99）—题面：Check what items are currently in your shopping cart.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 3（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_items` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 118（ba7427f96bfdd45c6df3）—题面：View the contents of your shopping cart with 3 items
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 3（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_items` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 120（bb4c6fa4b51a5a33afce）—题面：See how many reviews the Wildgame Innovations Trail Camera has.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 2（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_products` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 124（bf53b767cb6680af3e02）—题面：Find out what programming libraries are supported by the a11y-syntax-highlighting project.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 2（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_items` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 125（bf7fb901e64a6b200e93）—题面：List the names of all immediate subdirectories in src on the main branch of The A11Y Project (a11yproject/a11yproject.com).
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 13（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_directories` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 126（bfb19f582147d0013e80）—题面：Find out what Markdown formatting options are available for creating wiki pages
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 26（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_items` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 130（c4d2f4fa20e3debaf7da）—题面：Check which material types are available for the St Patricks Day T-Shirt
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 8（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_material_types` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 131（cb1f6d37c80c1c966d0c）—题面：Retrieve the distance and estimated time for the route from 40.7830, -73.9650 to 40.7570, -73.9860.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 2（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_<字段>` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 133（cc749c4fb809e8c6fb7f）—题面：View all projects with the Apache License 2.0. Consider all non-archived projects accessible to the current account, across the complete project directory.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 13（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_projects` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 135（cef4af3fccbffcd9e2b5）—题面：Read and report the project description for zerosoul / chinese-colors.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 2（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_description` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 137（d0b831ec16b5e174fbd5）—题面：Share the current map location using a geo URI.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 2（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_geo_uri` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 139（d3157acb785a0c07897a）—题面：Determine what fields are required when creating a new wiki page
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 3（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_items` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 149（e0d2db4c54b927dba6c4）—题面：List the step-by-step directions from 40.7830, -73.9650 to 40.7570, -73.9860.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 6（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_steps` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 150（e185d8d1ac754b973390）—题面：Check the total distance and estimated travel time from New York City to Boston by car.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 2（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_<字段>` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 152（e678830c65ec323f09db）—题面：View all 3 items in the cart to verify quantities before placing order
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 6（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_items` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 154（e83b251b13a8daa1fc7a）—题面：Generate a geo URI for the current location
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 2（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_geo_uri` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 155（e8d67ff6e22fa9ee3b67）—题面：List all directories in the a11y-syntax-highlighting repository.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 14（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_items` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 156（e9c39aadd73068054997）—题面：Check what items are currently in your shopping cart with 3 items.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 3（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_items` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 158（f73c97fb77388ae7f772）—题面：Find the SKU number and manufacturer of the Mineralogie All Natural Lip Gloss, Ruby Rose.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 2（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_<字段>` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 161（fbd675fc29750bd1a7ff）—题面：Find out who is using the a11y-syntax-highlighting themes.
- **分支：** `site_query_rules.evaluate_query:ordinary_query`
- **原固定分母：** 7（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标绑定对象身份正确；G2 `answer_items` 全部字段值与本地参考值精确匹配；G3 `requested_records_unchanged`（只读）；G4 `page_valid`；G5 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.6）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

### 3.7 export 型（12 题）

#### 题目 9（0b88605b2114cefbb677）—题面：Export the list of customers to a CSV file
- **分支：** `admin_contract_rules.checks:export`
- **原固定分母：** 140（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 导出对象集合正确；G2 `downloaded_matching_csv`（下载 CSV 内容+集合完整匹配，漏任一行/任一字段 → 0）；G3 `records_unchanged`（只读导出）；G4 `same_local_deployment`；G5 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 操作合规 0.30 / 导出完整性 0.25 / 证据充分性 0.15（锚点见 §2.7）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 26（2808ca675a8231d9c01d）—题面：Export the current customer data to a file.
- **分支：** `admin_contract_rules.checks:export`
- **原固定分母：** 140（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 导出对象集合正确；G2 `downloaded_matching_csv`（下载 CSV 内容+集合完整匹配，漏任一行/任一字段 → 0）；G3 `records_unchanged`（只读导出）；G4 `same_local_deployment`；G5 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 操作合规 0.30 / 导出完整性 0.25 / 证据充分性 0.15（锚点见 §2.7）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 31（2ebb8e234b090307f6ac）—题面：Export credit memo data to a CSV file.
- **分支：** `admin_contract_rules.checks:export`
- **原固定分母：** 20（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 导出对象集合正确；G2 `downloaded_matching_csv`（下载 CSV 内容+集合完整匹配，漏任一行/任一字段 → 0）；G3 `records_unchanged`（只读导出）；G4 `same_local_deployment`；G5 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 操作合规 0.30 / 导出完整性 0.25 / 证据充分性 0.15（锚点见 §2.7）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 36（366af9836afa8987f721）—题面：Export the list of orders to a CSV file.
- **分支：** `admin_contract_rules.checks:export`
- **原固定分母：** 616（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 导出对象集合正确；G2 `downloaded_matching_csv`（下载 CSV 内容+集合完整匹配，漏任一行/任一字段 → 0）；G3 `records_unchanged`（只读导出）；G4 `same_local_deployment`；G5 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 操作合规 0.30 / 导出完整性 0.25 / 证据充分性 0.15（锚点见 §2.7）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 49（48f12d69e2ac92bbc655）—题面：Export all order data from the Magento Admin panel.
- **分支：** `admin_contract_rules.checks:export`
- **原固定分母：** 616（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 导出对象集合正确；G2 `downloaded_matching_csv`（下载 CSV 内容+集合完整匹配，漏任一行/任一字段 → 0）；G3 `records_unchanged`（只读导出）；G4 `same_local_deployment`；G5 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 操作合规 0.30 / 导出完整性 0.25 / 证据充分性 0.15（锚点见 §2.7）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 53（502148f62db1683b9bba）—题面：Export the current order data to a CSV file on the Magento Admin page.
- **分支：** `admin_contract_rules.checks:export`
- **原固定分母：** 616（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 导出对象集合正确；G2 `downloaded_matching_csv`（下载 CSV 内容+集合完整匹配，漏任一行/任一字段 → 0）；G3 `records_unchanged`（只读导出）；G4 `same_local_deployment`；G5 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 操作合规 0.30 / 导出完整性 0.25 / 证据充分性 0.15（锚点见 §2.7）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 76（7b4161eaac57c41ed83d）—题面：Export the customer data as a CSV file.
- **分支：** `admin_contract_rules.checks:export`
- **原固定分母：** 140（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 导出对象集合正确；G2 `downloaded_matching_csv`（下载 CSV 内容+集合完整匹配，漏任一行/任一字段 → 0）；G3 `records_unchanged`（只读导出）；G4 `same_local_deployment`；G5 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 操作合规 0.30 / 导出完整性 0.25 / 证据充分性 0.15（锚点见 §2.7）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 82（87efc09382467a521c3b）—题面：Export the credit memo data as an Excel XML file.
- **分支：** `admin_contract_rules.checks:export`
- **原固定分母：** 20（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 导出对象集合正确；G2 `downloaded_matching_csv`（下载 CSV 内容+集合完整匹配，漏任一行/任一字段 → 0）；G3 `records_unchanged`（只读导出）；G4 `same_local_deployment`；G5 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 操作合规 0.30 / 导出完整性 0.25 / 证据充分性 0.15（锚点见 §2.7）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 96（a03f13a35cdfa2855e7d）—题面：Export the list of shipments using the Export button.
- **分支：** `admin_contract_rules.checks:export`
- **原固定分母：** 3（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 导出对象集合正确；G2 `downloaded_matching_csv`（下载 CSV 内容+集合完整匹配，漏任一行/任一字段 → 0）；G3 `records_unchanged`（只读导出）；G4 `same_local_deployment`；G5 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 操作合规 0.30 / 导出完整性 0.25 / 证据充分性 0.15（锚点见 §2.7）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 141（d4498e55f4e12af7500a）—题面：Export the order data as a CSV file.
- **分支：** `admin_contract_rules.checks:export`
- **原固定分母：** 616（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 导出对象集合正确；G2 `downloaded_matching_csv`（下载 CSV 内容+集合完整匹配，漏任一行/任一字段 → 0）；G3 `records_unchanged`（只读导出）；G4 `same_local_deployment`；G5 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 操作合规 0.30 / 导出完整性 0.25 / 证据充分性 0.15（锚点见 §2.7）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 144（d6c9a19fbbadca1e0548）—题面：Export customer data to CSV
- **分支：** `admin_contract_rules.checks:export`
- **原固定分母：** 140（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 导出对象集合正确；G2 `downloaded_matching_csv`（下载 CSV 内容+集合完整匹配，漏任一行/任一字段 → 0）；G3 `records_unchanged`（只读导出）；G4 `same_local_deployment`；G5 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 操作合规 0.30 / 导出完整性 0.25 / 证据充分性 0.15（锚点见 §2.7）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 157（ee4d5f917fbea3c35cbe）—题面：Export the credit memo data as a CSV file.
- **分支：** `admin_contract_rules.checks:export`
- **原固定分母：** 20（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 导出对象集合正确；G2 `downloaded_matching_csv`（下载 CSV 内容+集合完整匹配，漏任一行/任一字段 → 0）；G3 `records_unchanged`（只读导出）；G4 `same_local_deployment`；G5 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 操作合规 0.30 / 导出完整性 0.25 / 证据充分性 0.15（锚点见 §2.7）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

### 3.8 bulk_update 型（3 题）

#### 题目 20（1bfe6203aa85e3af13c0）—题面：For this local training variant, Subscribe these customers to the newsletter: adam.garcia@gmail.com, alex.martin@gmail.com.
- **分支：** `admin_contract_rules.checks:bulk_update`
- **原固定分母：** 2（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标记录集合正确；G2 `all_selected_records_updated`（集合内所有对象均满足更新条件，漏任一对象 → 0）；G3 `other_records_unchanged`；G4 `same_local_deployment`；G5 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 操作范围 0.35 / 验证规范 0.30 / 保存确认 0.20 / 证据充分性 0.15（write 型）（锚点见 §2.8）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 29（2d4229b6bc703e398bf4）—题面：For this local training variant, Unsubscribe all customers whose default billing address state is Florida from the newsletter.
- **分支：** `admin_contract_rules.checks:bulk_update`
- **原固定分母：** 6（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标记录集合正确；G2 `all_selected_records_updated`（集合内所有对象均满足更新条件，漏任一对象 → 0）；G3 `other_records_unchanged`；G4 `same_local_deployment`；G5 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 操作范围 0.35 / 验证规范 0.30 / 保存确认 0.20 / 证据充分性 0.15（write 型）（锚点见 §2.8）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 63（647cc7d981b85811507e）—题面：For this local training variant, Assign these five customers to VIP Customers: adam.garcia@gmail.com, alex.martin@gmail.com, alexander.thomas@hotmail.com, amanda.kim@gmail.com, anna.nguyen@yahoo.com.
- **分支：** `admin_contract_rules.checks:bulk_update`
- **原固定分母：** 5（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标记录集合正确；G2 `all_selected_records_updated`（集合内所有对象均满足更新条件，漏任一对象 → 0）；G3 `other_records_unchanged`；G4 `same_local_deployment`；G5 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 操作范围 0.35 / 验证规范 0.30 / 保存确认 0.20 / 证据充分性 0.15（write 型）（锚点见 §2.8）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

### 3.9 page_text_query 型（3 题）

#### 题目 61（60f67c44bf1f5c01fa32）—题面：For this local restored-page task, read the dotmailer description on the Magento Marketplace page and return its exact description text. Stay on the local page; external partner websites are outside the task.
- **分支：** `admin_contract_rules.checks:page_text_query`
- **原固定分母：** 3（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 `correct_page`（终页路径为要求路径）；G2 `correct_partner_description`（描述与参考一致）；G3 `partner_still_available`（伙伴描述未变）；G4 `records_unchanged`；G5 `same_local_deployment`；G6 `valid_authenticated_page`；G7 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.9）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 122（bced6b870e718e5c4722）—题面：For this local restored-page task, read the Vertex description on the Magento Marketplace page and return its exact description text. Stay on the local page; external partner websites are outside the task.
- **分支：** `admin_contract_rules.checks:page_text_query`
- **原固定分母：** 4（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 `correct_page`（终页路径为要求路径）；G2 `correct_partner_description`（描述与参考一致）；G3 `partner_still_available`（伙伴描述未变）；G4 `records_unchanged`；G5 `same_local_deployment`；G6 `valid_authenticated_page`；G7 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.9）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

#### 题目 146（d8597402b1c899c1eaea）—题面：For this local restored-page task, read the Yotpo description on the Magento Marketplace page and return its exact description text. Stay on the local page; external partner websites are outside the task.
- **分支：** `admin_contract_rules.checks:page_text_query`
- **原固定分母：** 4（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 `correct_page`（终页路径为要求路径）；G2 `correct_partner_description`（描述与参考一致）；G3 `partner_still_available`（伙伴描述未变）；G4 `records_unchanged`；G5 `same_local_deployment`；G6 `valid_authenticated_page`；G7 `answer_schema`。
- **质量维度（仅 gate 通过后计分）：** 目标定位规范 0.30 / 来源合规 0.30 / 字段校验 0.25 / 证据充分性 0.15（query 型）（锚点见 §2.9）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。

### 3.10 mail 型（1 题）

#### 题目 74（79399fd63d733a51a9d7）—题面：Send the order email for order #000000002 to that order's customer through the local store. Completion means the new matching message is recorded by this training environment's local mail capture; delivery to an external inbox is not required. Leave the order unchanged.
- **分支：** `admin_contract_rules.checks:mail`
- **原固定分母：** 2（本批按 P1 重写为 gate 全对，不再按 N 逐字段计分）
- **atomicity：** {"is_atomic": true, "reason": "题面要求的多个字段/要点/目标属同一原子任务，不拆成字段各 1/N"}
- **成功门控条件（gate）：** G1 目标订单正确；G2 `new_matching_mail_delivered`（本地捕获新邮件，收件人+订单号匹配）；G3 `order_unchanged`（订单不变）；G4 `same_local_deployment`；G5 `valid_authenticated_page`。
- **质量维度（仅 gate 通过后计分）：** 操作范围 0.35 / 验证规范 0.30 / 发送确认 0.20 / 证据充分性 0.15（write 型）（锚点见 §2.10）
- **边界情况：** 无法确认字段/目标是否全部正确 → null（明确任一错 → 0）；无法确认是否保存/生效 → null。
- **不应给分的反例：** 不拆「字段 A 对 1/N + 字段 B 对 1/N」；漏任一个字段/目标/要点 → 0（不按 (N-1)/N 给分）；「标题对但某字段错」「页面有效但答案错」不给分。


## 附录 A：固定分母 vs P1 对照（节选，说明重写差异）

| 题 | 原固定分母口径 | P1 本批口径 |
|---|---|---|
| #1 评论数+评分 | 分母 2，半对 → 0.50 | gate：两字段全对，任一错 → 0 |
| #3 默认账单地址（7 字段） | 分母 7，6 对 → 0.857 | gate：7 字段全对，任一错 → 0 |
| #9 导出客户 CSV（140） | 分母 140，漏 1 行 → 0.993 | gate：CSV 完整，漏 1 行 → 0 |
| #36 导出订单 CSV（616） | 分母 616，漏 1 行 → 0.999 | gate：CSV 完整，漏 1 行 → 0 |

## 附录 B：回归检查清单（提交前逐条勾选）

- [x] 每题都有 atomicity。
- [x] gate 1:1 映射判定谓词，无放宽/新增标准。
- [x] 多字段/多目标题未拆成「字段各 1/N」（固定分母已重写为 gate 全对）。
- [x] 质量维度仅在 gate 通过后计分，权重和 = 1.0（两套已登记）。
- [x] 复用框架（update/create/query/collection_query/pdf/ordinary_query）已自包含展开于 §2，未遗漏。
- [x] 新增框架（export/bulk_update/page_text_query/mail）已建立。
- [x] 空结果/布尔等按与本地真实状态一致判定，未一律判 0。