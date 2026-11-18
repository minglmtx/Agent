# 非二值（部分奖励）题目


## 题目 1（00de3e4838fad62957df）

**题面：** How many reviews does the "Custom Jersey Style St Patrick's Day T Shirts" product have and what is its rating?

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；path: /anvme/workspace/r102bf10-lab-generate-skill/experiments/train-partial-reward-20261117-v1/trace-review-v1/answer-completion-review.json; sha256: 8bce509b9b45b9e06b7bef0a47fb080d5715c3ca326a65313c447788501df5be

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 2 计分：answer_review_count（字段：answer_review_count；组内 AND）；answer_rating_percent（字段：answer_rating_percent；组内 AND）

## 题目 2（01aeb9ebc09ef6d46c3d）

**题面：** For this local training variant, Select shipments #000000001 and #000000002, and download their packing slips together as a PDF.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:pdf`；downloaded_correct_documents: 至少一个实际下载产物通过原内容及选中对象集合比较。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 2 计分：目标1：每个指定运单的完整装箱单（字段：shipment_id, packing_slip；组内 AND）；目标2：每个指定运单的完整装箱单（字段：shipment_id, packing_slip；组内 AND）

## 题目 3（02623a13789d0ba87796）

**题面：** Find my default billing address information

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；path: /anvme/workspace/r102bf10-lab-generate-skill/experiments/train-partial-reward-20261117-v1/trace-review-v1/answer-completion-review.json; sha256: 8bce509b9b45b9e06b7bef0a47fb080d5715c3ca326a65313c447788501df5be

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 7 计分：完整姓名正确（字段：answer_name；组内 AND）；街道地址正确（字段：answer_street；组内 AND）；城市正确（字段：answer_city；组内 AND）；州/地区正确（字段：answer_region；组内 AND）；邮编正确（字段：answer_postal_code；组内 AND）；国家正确（字段：answer_country_code；组内 AND）；电话正确（字段：answer_telephone；组内 AND）

## 题目 4（043df48c57af4a1b4de8）

**题面：** For this local training variant, create a product attribute with label Training Color, attribute code training_color and Text Field input type. Save it without changing the existing color attribute.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:create`；new_matching_record_saved: 原选择条件匹配且本次新增的记录恰好一条。; created_record_conditions: 该唯一新记录整体满足原 create_conditions。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; existing_records_unchanged: 原有实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; existing_records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 4 计分：实际新增并保存一个本任务可唯一绑定的有效对象（字段：；组内 AND）；属性代码正确（字段：attribute_code；组内 AND）；属性标签正确（字段：frontend_label；组内 AND）；输入类型正确（字段：frontend_input；组内 AND）

## 题目 5（05adaa3aae957f2c3dc0）

**题面：** Check the shipping method and cost for my order

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；path: /anvme/workspace/r102bf10-lab-generate-skill/experiments/train-partial-reward-20261117-v1/trace-review-v1/answer-completion-review.json; sha256: 8bce509b9b45b9e06b7bef0a47fb080d5715c3ca326a65313c447788501df5be

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 2 计分：answer_shipping_method（字段：answer_shipping_method；组内 AND）；answer_shipping_cost（字段：answer_shipping_cost；组内 AND）

## 题目 6（05c4cabeb5f7296af901）

**题面：** For this local training variant, select order #000000002 and download its packing slip PDF.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:pdf`；downloaded_correct_documents: 至少一个实际下载产物通过原内容及选中对象集合比较。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 4 计分：订单日期（字段：；组内 AND）；账单和收货对象及完整地址（字段：；组内 AND）；支付方式、配送方式及运费（字段：；组内 AND）；商品名称、SKU、数量及规格（字段：；组内 AND）

## 题目 7（06d6dd1b987d04ba2032）

**题面：** Create and save a new customer named Training Customer with email admin-06d6dd1b987d04ba2032@example.test and customer group Wholesale Customers. Keep valid defaults for unspecified optional fields.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:create`；new_matching_record_saved: 原选择条件匹配且本次新增的记录恰好一条。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; existing_records_unchanged: 原有实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; existing_records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 4 计分：实际新增并保存一个本任务可唯一绑定的有效对象（字段：；组内 AND）；完整姓名正确（字段：firstname, lastname；组内 AND）；邮箱正确（字段：email；组内 AND）；客户组正确（字段：group_name；组内 AND）

## 题目 8（0adfc625f5e41270cf99）

**题面：** Create a new customer account for John Smith with email johnsmith@example.com

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:create`；new_matching_record_saved: 原选择条件匹配且本次新增的记录恰好一条。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; existing_records_unchanged: 原有实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; existing_records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 3 计分：实际新增并保存一个本任务可唯一绑定的有效对象（字段：；组内 AND）；完整姓名正确（字段：firstname, lastname；组内 AND）；邮箱正确（字段：email；组内 AND）

## 题目 9（0b88605b2114cefbb677）

**题面：** Export the list of customers to a CSV file

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:export`；downloaded_matching_csv: 至少一个实际下载产物通过原内容及选中对象集合比较。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 140 计分：目标1：名称正确（字段：name；组内 AND）；目标1：邮箱正确（字段：email；组内 AND）；目标2：名称正确（字段：name；组内 AND）；目标2：邮箱正确（字段：email；组内 AND）；目标3：名称正确（字段：name；组内 AND）；目标3：邮箱正确（字段：email；组内 AND）；目标4：名称正确（字段：name；组内 AND）；目标4：邮箱正确（字段：email；组内 AND）；目标5：名称正确（字段：name；组内 AND）；目标5：邮箱正确（字段：email；组内 AND）；目标6：名称正确（字段：name；组内 AND）；目标6：邮箱正确（字段：email；组内 AND）；目标7：名称正确（字段：name；组内 AND）；目标7：邮箱正确（字段：email；组内 AND）；目标8：名称正确（字段：name；组内 AND）；目标8：邮箱正确（字段：email；组内 AND）；目标9：名称正确（字段：name；组内 AND）；目标9：邮箱正确（字段：email；组内 AND）；目标10：名称正确（字段：name；组内 AND）；目标10：邮箱正确（字段：email；组内 AND）；目标11：名称正确（字段：name；组内 AND）；目标11：邮箱正确（字段：email；组内 AND）；目标12：名称正确（字段：name；组内 AND）；目标12：邮箱正确（字段：email；组内 AND）；目标13：名称正确（字段：name；组内 AND）；目标13：邮箱正确（字段：email；组内 AND）；目标14：名称正确（字段：name；组内 AND）；目标14：邮箱正确（字段：email；组内 AND）；目标15：名称正确（字段：name；组内 AND）；目标15：邮箱正确（字段：email；组内 AND）；目标16：名称正确（字段：name；组内 AND）；目标16：邮箱正确（字段：email；组内 AND）；目标17：名称正确（字段：name；组内 AND）；目标17：邮箱正确（字段：email；组内 AND）；目标18：名称正确（字段：name；组内 AND）；目标18：邮箱正确（字段：email；组内 AND）；目标19：名称正确（字段：name；组内 AND）；目标19：邮箱正确（字段：email；组内 AND）；目标20：名称正确（字段：name；组内 AND）；目标20：邮箱正确（字段：email；组内 AND）；目标21：名称正确（字段：name；组内 AND）；目标21：邮箱正确（字段：email；组内 AND）；目标22：名称正确（字段：name；组内 AND）；目标22：邮箱正确（字段：email；组内 AND）；目标23：名称正确（字段：name；组内 AND）；目标23：邮箱正确（字段：email；组内 AND）；目标24：名称正确（字段：name；组内 AND）；目标24：邮箱正确（字段：email；组内 AND）；目标25：名称正确（字段：name；组内 AND）；目标25：邮箱正确（字段：email；组内 AND）；目标26：名称正确（字段：name；组内 AND）；目标26：邮箱正确（字段：email；组内 AND）；目标27：名称正确（字段：name；组内 AND）；目标27：邮箱正确（字段：email；组内 AND）；目标28：名称正确（字段：name；组内 AND）；目标28：邮箱正确（字段：email；组内 AND）；目标29：名称正确（字段：name；组内 AND）；目标29：邮箱正确（字段：email；组内 AND）；目标30：名称正确（字段：name；组内 AND）；目标30：邮箱正确（字段：email；组内 AND）；目标31：名称正确（字段：name；组内 AND）；目标31：邮箱正确（字段：email；组内 AND）；目标32：名称正确（字段：name；组内 AND）；目标32：邮箱正确（字段：email；组内 AND）；目标33：名称正确（字段：name；组内 AND）；目标33：邮箱正确（字段：email；组内 AND）；目标34：名称正确（字段：name；组内 AND）；目标34：邮箱正确（字段：email；组内 AND）；目标35：名称正确（字段：name；组内 AND）；目标35：邮箱正确（字段：email；组内 AND）；目标36：名称正确（字段：name；组内 AND）；目标36：邮箱正确（字段：email；组内 AND）；目标37：名称正确（字段：name；组内 AND）；目标37：邮箱正确（字段：email；组内 AND）；目标38：名称正确（字段：name；组内 AND）；目标38：邮箱正确（字段：email；组内 AND）；目标39：名称正确（字段：name；组内 AND）；目标39：邮箱正确（字段：email；组内 AND）；目标40：名称正确（字段：name；组内 AND）；目标40：邮箱正确（字段：email；组内 AND）；目标41：名称正确（字段：name；组内 AND）；目标41：邮箱正确（字段：email；组内 AND）；目标42：名称正确（字段：name；组内 AND）；目标42：邮箱正确（字段：email；组内 AND）；目标43：名称正确（字段：name；组内 AND）；目标43：邮箱正确（字段：email；组内 AND）；目标44：名称正确（字段：name；组内 AND）；目标44：邮箱正确（字段：email；组内 AND）；目标45：名称正确（字段：name；组内 AND）；目标45：邮箱正确（字段：email；组内 AND）；目标46：名称正确（字段：name；组内 AND）；目标46：邮箱正确（字段：email；组内 AND）；目标47：名称正确（字段：name；组内 AND）；目标47：邮箱正确（字段：email；组内 AND）；目标48：名称正确（字段：name；组内 AND）；目标48：邮箱正确（字段：email；组内 AND）；目标49：名称正确（字段：name；组内 AND）；目标49：邮箱正确（字段：email；组内 AND）；目标50：名称正确（字段：name；组内 AND）；目标50：邮箱正确（字段：email；组内 AND）；目标51：名称正确（字段：name；组内 AND）；目标51：邮箱正确（字段：email；组内 AND）；目标52：名称正确（字段：name；组内 AND）；目标52：邮箱正确（字段：email；组内 AND）；目标53：名称正确（字段：name；组内 AND）；目标53：邮箱正确（字段：email；组内 AND）；目标54：名称正确（字段：name；组内 AND）；目标54：邮箱正确（字段：email；组内 AND）；目标55：名称正确（字段：name；组内 AND）；目标55：邮箱正确（字段：email；组内 AND）；目标56：名称正确（字段：name；组内 AND）；目标56：邮箱正确（字段：email；组内 AND）；目标57：名称正确（字段：name；组内 AND）；目标57：邮箱正确（字段：email；组内 AND）；目标58：名称正确（字段：name；组内 AND）；目标58：邮箱正确（字段：email；组内 AND）；目标59：名称正确（字段：name；组内 AND）；目标59：邮箱正确（字段：email；组内 AND）；目标60：名称正确（字段：name；组内 AND）；目标60：邮箱正确（字段：email；组内 AND）；目标61：名称正确（字段：name；组内 AND）；目标61：邮箱正确（字段：email；组内 AND）；目标62：名称正确（字段：name；组内 AND）；目标62：邮箱正确（字段：email；组内 AND）；目标63：名称正确（字段：name；组内 AND）；目标63：邮箱正确（字段：email；组内 AND）；目标64：名称正确（字段：name；组内 AND）；目标64：邮箱正确（字段：email；组内 AND）；目标65：名称正确（字段：name；组内 AND）；目标65：邮箱正确（字段：email；组内 AND）；目标66：名称正确（字段：name；组内 AND）；目标66：邮箱正确（字段：email；组内 AND）；目标67：名称正确（字段：name；组内 AND）；目标67：邮箱正确（字段：email；组内 AND）；目标68：名称正确（字段：name；组内 AND）；目标68：邮箱正确（字段：email；组内 AND）；目标69：名称正确（字段：name；组内 AND）；目标69：邮箱正确（字段：email；组内 AND）；目标70：名称正确（字段：name；组内 AND）；目标70：邮箱正确（字段：email；组内 AND）

## 题目 10（0d50993fbdf6d32994bb）

**题面：** Verify the shipping address details for Emma Lopez.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_shipping_address_lines: 提交的 shipping_address_lines 满足原 record_set 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 5 计分：每条原地址行的完整正文和行号对应正确（字段：line, text；组内 AND）

## 题目 11（0f1aa3a36555035eb8c0）

**题面：** Set Blue T-Shirt visibility to Catalog, Search and save.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:update`；persisted_requested_value: 原选中对象已持久保存，并整体满足 update_matches 的请求条件。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; other_records_unchanged: 原目标以外的同实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; other_records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 2 计分：保存的商品可见性包含Catalog（字段：；组内 AND）；保存的商品可见性包含Search（字段：；组内 AND）

## 题目 12（10cdae7af1322acbc6a3）

**题面：** For this local training variant, the following are supplied training product facts. Set the Sony Headphones Description to exactly the text inside the quotation marks, excluding the quotation marks: "Sony Headphones feature a lightweight adjustable headband and wired stereo playback. Specifications: 3.5 mm wired connection; no wireless connectivity.". Save the change.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:update`；persisted_requested_value: 原选中对象已持久保存，并整体满足 update_matches 的请求条件。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; other_records_unchanged: 原目标以外的同实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; other_records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 4 计分：轻便可调头带（字段：description；组内 AND）；有线立体声播放（字段：description；组内 AND）；3.5mm有线连接（字段：description；组内 AND）；不支持无线连接（字段：description；组内 AND）

## 题目 13（1317a2b60d5f27b6f640）

**题面：** Find out what categories are available under Sports & Outdoors

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_categories: 提交的 categories 满足原 record_set 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 5 计分：每个正确、不重复的要求列表成员（字段：name；组内 AND）

## 题目 14（13914fd7d1bf94533456）

**题面：** Find out what technologies are used in The A11Y Project website.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_items: 提交的 items 满足原 record_set 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 10 计分：每个正确、不重复的要求列表成员（字段：name；组内 AND）

## 题目 15（158bf9a1de57867a2ac4）

**题面：** Find the default billing address for Emma Lopez.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；path: /anvme/workspace/r102bf10-lab-generate-skill/experiments/train-partial-reward-20261117-v1/trace-review-v1/answer-completion-review.json; sha256: 8bce509b9b45b9e06b7bef0a47fb080d5715c3ca326a65313c447788501df5be

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema; answer_name

**目前的评分准则：** 前提通过后，按固定分母 6 计分：街道地址正确（字段：answer_street；组内 AND）；城市正确（字段：answer_city；组内 AND）；州/地区正确（字段：answer_region；组内 AND）；邮编正确（字段：answer_postal_code；组内 AND）；国家正确（字段：answer_country_code；组内 AND）；电话正确（字段：answer_telephone；组内 AND）

## 题目 16（1820a8409805e0f44e63）

**题面：** Find repositories with MIT License on the current page

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_projects: 提交的 projects 满足原 record_set 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 5 计分：每个正确、不重复的要求列表成员（字段：path；组内 AND）

## 题目 17（1a50d30e5d14712ec9d0）

**题面：** For this local training variant, retrieve the default billing phone number and ZIP code of Jane Doe (jane.doe@gmail.com). The initial snapshot places this existing customer in VIP Customers.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:query`；path: /anvme/workspace/r102bf10-lab-generate-skill/experiments/train-partial-reward-20261117-v1/trace-review-v1/answer-completion-review.json; sha256: 8bce509b9b45b9e06b7bef0a47fb080d5715c3ca326a65313c447788501df5be

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 2 计分：answer_telephone（字段：answer_telephone；组内 AND）；answer_postcode（字段：answer_postcode；组内 AND）

## 题目 18（1af036a267a8429d2fc9）

**题面：** Search for customers living in New York state

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:collection_query`；exact_result_set: 按原字段比较完整多重集合，包含数量、重复、遗漏和多余记录约束。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 12 计分：目标1：完整姓名正确（字段：firstname, lastname；组内 AND）；目标1：邮箱正确（字段：email；组内 AND）；目标2：完整姓名正确（字段：firstname, lastname；组内 AND）；目标2：邮箱正确（字段：email；组内 AND）；目标3：完整姓名正确（字段：firstname, lastname；组内 AND）；目标3：邮箱正确（字段：email；组内 AND）；目标4：完整姓名正确（字段：firstname, lastname；组内 AND）；目标4：邮箱正确（字段：email；组内 AND）；目标5：完整姓名正确（字段：firstname, lastname；组内 AND）；目标5：邮箱正确（字段：email；组内 AND）；目标6：完整姓名正确（字段：firstname, lastname；组内 AND）；目标6：邮箱正确（字段：email；组内 AND）

## 题目 19（1b482d1d92765f6cb6d9）

**题面：** Retrieve the latest commit message for the a11yproject.com repository.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_latest_commit_message: 提交的 latest_commit_message 满足原 string 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 2 计分：提交说明中的变更动作Update（字段：；组内 AND）；提交说明中的完整受影响文件名（字段：；组内 AND）

## 题目 20（1bfe6203aa85e3af13c0）

**题面：** For this local training variant, Subscribe these customers to the newsletter: adam.garcia@gmail.com, alex.martin@gmail.com.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:bulk_update`；all_selected_records_updated: 原绑定集合内所有对象均存在且满足请求的更新条件。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; other_records_unchanged: 原目标以外的同实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; other_records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 2 计分：目标1：每位指定客户的请求修改已保存且生效（字段：subscriber_status；组内 AND）；目标2：每位指定客户的请求修改已保存且生效（字段：subscriber_status；组内 AND）

## 题目 21（1d095aa28f753677a069）

**题面：** Explore available data sources for downloading OpenStreetMap data.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_items: 提交的 items 满足原 record_set 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 8 计分：目标1：名称正确（字段：name；组内 AND）；目标1：描述正确（字段：description；组内 AND）；目标2：名称正确（字段：name；组内 AND）；目标2：描述正确（字段：description；组内 AND）；目标3：名称正确（字段：name；组内 AND）；目标3：描述正确（字段：description；组内 AND）；目标4：名称正确（字段：name；组内 AND）；目标4：描述正确（字段：description；组内 AND）

## 题目 22（1d838691d0e90160f0c6）

**题面：** Check which customer groups are available for new customer creation

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:collection_query`；exact_result_set: 按原字段比较完整多重集合，包含数量、重复、遗漏和多余记录约束。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 3 计分：每个正确的目标记录/列表成员（字段：name；组内 AND）

## 题目 23（237e143cb3de228b8d84）

**题面：** Check what markdown formatting options are available for post creation

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_items: 提交的 items 满足原 record_set 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 26 计分：目标1：要求的格式功能覆盖完整（字段：feature；组内 AND）；目标1：各功能对应语法正确（字段：syntax；组内 AND）；目标2：要求的格式功能覆盖完整（字段：feature；组内 AND）；目标2：各功能对应语法正确（字段：syntax；组内 AND）；目标3：要求的格式功能覆盖完整（字段：feature；组内 AND）；目标3：各功能对应语法正确（字段：syntax；组内 AND）；目标4：要求的格式功能覆盖完整（字段：feature；组内 AND）；目标4：各功能对应语法正确（字段：syntax；组内 AND）；目标5：要求的格式功能覆盖完整（字段：feature；组内 AND）；目标5：各功能对应语法正确（字段：syntax；组内 AND）；目标6：要求的格式功能覆盖完整（字段：feature；组内 AND）；目标6：各功能对应语法正确（字段：syntax；组内 AND）；目标7：要求的格式功能覆盖完整（字段：feature；组内 AND）；目标7：各功能对应语法正确（字段：syntax；组内 AND）；目标8：要求的格式功能覆盖完整（字段：feature；组内 AND）；目标8：各功能对应语法正确（字段：syntax；组内 AND）；目标9：要求的格式功能覆盖完整（字段：feature；组内 AND）；目标9：各功能对应语法正确（字段：syntax；组内 AND）；目标10：要求的格式功能覆盖完整（字段：feature；组内 AND）；目标10：各功能对应语法正确（字段：syntax；组内 AND）；目标11：要求的格式功能覆盖完整（字段：feature；组内 AND）；目标11：各功能对应语法正确（字段：syntax；组内 AND）；目标12：要求的格式功能覆盖完整（字段：feature；组内 AND）；目标12：各功能对应语法正确（字段：syntax；组内 AND）；目标13：要求的格式功能覆盖完整（字段：feature；组内 AND）；目标13：各功能对应语法正确（字段：syntax；组内 AND）

## 题目 24（23b872112e21eec243e8）

**题面：** Report the five most recently placed orders, including order number, customer name, and grand total. Break timestamp ties by ascending internal order ID.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:collection_query`；exact_result_set: 按原字段比较完整多重集合，包含数量、重复、遗漏和多余记录约束。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 3 计分：目标集合覆盖完整且记录编号正确（字段：increment_id；组内 AND）；客户姓名正确（字段：customer_name；组内 AND）；总额正确（字段：grand_total；组内 AND）

## 题目 25（2642eb4f6e622c2ff448）

**题面：** Check the total distance and estimated travel time for the current route

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；path: /anvme/workspace/r102bf10-lab-generate-skill/experiments/train-partial-reward-20261117-v1/trace-review-v1/answer-completion-review.json; sha256: 8bce509b9b45b9e06b7bef0a47fb080d5715c3ca326a65313c447788501df5be

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 2 计分：answer_distance_km（字段：answer_distance_km；组内 AND）；answer_duration_minutes（字段：answer_duration_minutes；组内 AND）

## 题目 26（2808ca675a8231d9c01d）

**题面：** Export the current customer data to a file.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:export`；downloaded_matching_csv: 至少一个实际下载产物通过原内容及选中对象集合比较。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 140 计分：目标1：名称正确（字段：name；组内 AND）；目标1：邮箱正确（字段：email；组内 AND）；目标2：名称正确（字段：name；组内 AND）；目标2：邮箱正确（字段：email；组内 AND）；目标3：名称正确（字段：name；组内 AND）；目标3：邮箱正确（字段：email；组内 AND）；目标4：名称正确（字段：name；组内 AND）；目标4：邮箱正确（字段：email；组内 AND）；目标5：名称正确（字段：name；组内 AND）；目标5：邮箱正确（字段：email；组内 AND）；目标6：名称正确（字段：name；组内 AND）；目标6：邮箱正确（字段：email；组内 AND）；目标7：名称正确（字段：name；组内 AND）；目标7：邮箱正确（字段：email；组内 AND）；目标8：名称正确（字段：name；组内 AND）；目标8：邮箱正确（字段：email；组内 AND）；目标9：名称正确（字段：name；组内 AND）；目标9：邮箱正确（字段：email；组内 AND）；目标10：名称正确（字段：name；组内 AND）；目标10：邮箱正确（字段：email；组内 AND）；目标11：名称正确（字段：name；组内 AND）；目标11：邮箱正确（字段：email；组内 AND）；目标12：名称正确（字段：name；组内 AND）；目标12：邮箱正确（字段：email；组内 AND）；目标13：名称正确（字段：name；组内 AND）；目标13：邮箱正确（字段：email；组内 AND）；目标14：名称正确（字段：name；组内 AND）；目标14：邮箱正确（字段：email；组内 AND）；目标15：名称正确（字段：name；组内 AND）；目标15：邮箱正确（字段：email；组内 AND）；目标16：名称正确（字段：name；组内 AND）；目标16：邮箱正确（字段：email；组内 AND）；目标17：名称正确（字段：name；组内 AND）；目标17：邮箱正确（字段：email；组内 AND）；目标18：名称正确（字段：name；组内 AND）；目标18：邮箱正确（字段：email；组内 AND）；目标19：名称正确（字段：name；组内 AND）；目标19：邮箱正确（字段：email；组内 AND）；目标20：名称正确（字段：name；组内 AND）；目标20：邮箱正确（字段：email；组内 AND）；目标21：名称正确（字段：name；组内 AND）；目标21：邮箱正确（字段：email；组内 AND）；目标22：名称正确（字段：name；组内 AND）；目标22：邮箱正确（字段：email；组内 AND）；目标23：名称正确（字段：name；组内 AND）；目标23：邮箱正确（字段：email；组内 AND）；目标24：名称正确（字段：name；组内 AND）；目标24：邮箱正确（字段：email；组内 AND）；目标25：名称正确（字段：name；组内 AND）；目标25：邮箱正确（字段：email；组内 AND）；目标26：名称正确（字段：name；组内 AND）；目标26：邮箱正确（字段：email；组内 AND）；目标27：名称正确（字段：name；组内 AND）；目标27：邮箱正确（字段：email；组内 AND）；目标28：名称正确（字段：name；组内 AND）；目标28：邮箱正确（字段：email；组内 AND）；目标29：名称正确（字段：name；组内 AND）；目标29：邮箱正确（字段：email；组内 AND）；目标30：名称正确（字段：name；组内 AND）；目标30：邮箱正确（字段：email；组内 AND）；目标31：名称正确（字段：name；组内 AND）；目标31：邮箱正确（字段：email；组内 AND）；目标32：名称正确（字段：name；组内 AND）；目标32：邮箱正确（字段：email；组内 AND）；目标33：名称正确（字段：name；组内 AND）；目标33：邮箱正确（字段：email；组内 AND）；目标34：名称正确（字段：name；组内 AND）；目标34：邮箱正确（字段：email；组内 AND）；目标35：名称正确（字段：name；组内 AND）；目标35：邮箱正确（字段：email；组内 AND）；目标36：名称正确（字段：name；组内 AND）；目标36：邮箱正确（字段：email；组内 AND）；目标37：名称正确（字段：name；组内 AND）；目标37：邮箱正确（字段：email；组内 AND）；目标38：名称正确（字段：name；组内 AND）；目标38：邮箱正确（字段：email；组内 AND）；目标39：名称正确（字段：name；组内 AND）；目标39：邮箱正确（字段：email；组内 AND）；目标40：名称正确（字段：name；组内 AND）；目标40：邮箱正确（字段：email；组内 AND）；目标41：名称正确（字段：name；组内 AND）；目标41：邮箱正确（字段：email；组内 AND）；目标42：名称正确（字段：name；组内 AND）；目标42：邮箱正确（字段：email；组内 AND）；目标43：名称正确（字段：name；组内 AND）；目标43：邮箱正确（字段：email；组内 AND）；目标44：名称正确（字段：name；组内 AND）；目标44：邮箱正确（字段：email；组内 AND）；目标45：名称正确（字段：name；组内 AND）；目标45：邮箱正确（字段：email；组内 AND）；目标46：名称正确（字段：name；组内 AND）；目标46：邮箱正确（字段：email；组内 AND）；目标47：名称正确（字段：name；组内 AND）；目标47：邮箱正确（字段：email；组内 AND）；目标48：名称正确（字段：name；组内 AND）；目标48：邮箱正确（字段：email；组内 AND）；目标49：名称正确（字段：name；组内 AND）；目标49：邮箱正确（字段：email；组内 AND）；目标50：名称正确（字段：name；组内 AND）；目标50：邮箱正确（字段：email；组内 AND）；目标51：名称正确（字段：name；组内 AND）；目标51：邮箱正确（字段：email；组内 AND）；目标52：名称正确（字段：name；组内 AND）；目标52：邮箱正确（字段：email；组内 AND）；目标53：名称正确（字段：name；组内 AND）；目标53：邮箱正确（字段：email；组内 AND）；目标54：名称正确（字段：name；组内 AND）；目标54：邮箱正确（字段：email；组内 AND）；目标55：名称正确（字段：name；组内 AND）；目标55：邮箱正确（字段：email；组内 AND）；目标56：名称正确（字段：name；组内 AND）；目标56：邮箱正确（字段：email；组内 AND）；目标57：名称正确（字段：name；组内 AND）；目标57：邮箱正确（字段：email；组内 AND）；目标58：名称正确（字段：name；组内 AND）；目标58：邮箱正确（字段：email；组内 AND）；目标59：名称正确（字段：name；组内 AND）；目标59：邮箱正确（字段：email；组内 AND）；目标60：名称正确（字段：name；组内 AND）；目标60：邮箱正确（字段：email；组内 AND）；目标61：名称正确（字段：name；组内 AND）；目标61：邮箱正确（字段：email；组内 AND）；目标62：名称正确（字段：name；组内 AND）；目标62：邮箱正确（字段：email；组内 AND）；目标63：名称正确（字段：name；组内 AND）；目标63：邮箱正确（字段：email；组内 AND）；目标64：名称正确（字段：name；组内 AND）；目标64：邮箱正确（字段：email；组内 AND）；目标65：名称正确（字段：name；组内 AND）；目标65：邮箱正确（字段：email；组内 AND）；目标66：名称正确（字段：name；组内 AND）；目标66：邮箱正确（字段：email；组内 AND）；目标67：名称正确（字段：name；组内 AND）；目标67：邮箱正确（字段：email；组内 AND）；目标68：名称正确（字段：name；组内 AND）；目标68：邮箱正确（字段：email；组内 AND）；目标69：名称正确（字段：name；组内 AND）；目标69：邮箱正确（字段：email；组内 AND）；目标70：名称正确（字段：name；组内 AND）；目标70：邮箱正确（字段：email；组内 AND）

## 题目 27（294e440ada4fcc494444）

**题面：** Find all products with less than 100 units in stock

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:collection_query`；exact_result_set: 按原字段比较完整多重集合，包含数量、重复、遗漏和多余记录约束。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 3 计分：目标集合覆盖完整且SKU正确（字段：sku；组内 AND）；名称正确（字段：name；组内 AND）；数量正确（字段：qty；组内 AND）

## 题目 28（2cf60b2bee0001aff88b）

**题面：** Create and save a new customer named Training Customer with email admin-2cf60b2bee0001aff88b@example.test. Keep valid defaults for unspecified optional fields.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:create`；new_matching_record_saved: 原选择条件匹配且本次新增的记录恰好一条。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; existing_records_unchanged: 原有实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; existing_records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 3 计分：实际新增并保存一个本任务可唯一绑定的有效对象（字段：；组内 AND）；完整姓名正确（字段：firstname, lastname；组内 AND）；邮箱正确（字段：email；组内 AND）

## 题目 29（2d4229b6bc703e398bf4）

**题面：** For this local training variant, Unsubscribe all customers whose default billing address state is Florida from the newsletter.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:bulk_update`；all_selected_records_updated: 原绑定集合内所有对象均存在且满足请求的更新条件。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; other_records_unchanged: 原目标以外的同实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; other_records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 6 计分：每位指定客户的请求修改已保存且生效（字段：subscriber_status；组内 AND）

## 题目 30（2e437c6ebc27184225c5）

**题面：** Review existing CMS pages and their content status

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:collection_query`；exact_result_set: 按原字段比较完整多重集合，包含数量、重复、遗漏和多余记录约束。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 12 计分：目标1：标题正确（字段：title；组内 AND）；目标1：启用状态正确（字段：is_active；组内 AND）；目标2：标题正确（字段：title；组内 AND）；目标2：启用状态正确（字段：is_active；组内 AND）；目标3：标题正确（字段：title；组内 AND）；目标3：启用状态正确（字段：is_active；组内 AND）；目标4：标题正确（字段：title；组内 AND）；目标4：启用状态正确（字段：is_active；组内 AND）；目标5：标题正确（字段：title；组内 AND）；目标5：启用状态正确（字段：is_active；组内 AND）；目标6：标题正确（字段：title；组内 AND）；目标6：启用状态正确（字段：is_active；组内 AND）

## 题目 31（2ebb8e234b090307f6ac）

**题面：** Export credit memo data to a CSV file.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:export`；downloaded_matching_csv: 至少一个实际下载产物通过原内容及选中对象集合比较。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 20 计分：退款单编号（字段：；组内 AND）；退款单创建日期（字段：；组内 AND）；关联订单编号（字段：；组内 AND）；订单创建日期（字段：；组内 AND）；账单姓名及完整账单地址（字段：；组内 AND）；退款单状态（字段：；组内 AND）；基础币种退款金额（字段：；组内 AND）；订单状态（字段：；组内 AND）；购买商店/站点（字段：；组内 AND）；完整收货地址（字段：；组内 AND）；客户完整姓名（字段：；组内 AND）；客户邮箱（字段：；组内 AND）；客户分组（字段：；组内 AND）；支付方式（字段：；组内 AND）；配送方式信息（字段：；组内 AND）；退款小计（字段：；组内 AND）；配送及手续费（字段：；组内 AND）；退款调整金额（字段：；组内 AND）；调整费用（字段：；组内 AND）；基础币种订单总额（字段：；组内 AND）

## 题目 32（3023c4dedd7221a00b2c）

**题面：** Create and save a simple product named Training Product 3023c4, SKU TRAIN-3023c4dedd7221a00b2c, price 9.99. Keep valid defaults for unspecified settings.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:create`；new_matching_record_saved: 原选择条件匹配且本次新增的记录恰好一条。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; existing_records_unchanged: 原有实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; existing_records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 4 计分：实际新增并保存一个本任务可唯一绑定的有效对象（字段：；组内 AND）；名称正确（字段：name；组内 AND）；SKU正确（字段：sku；组内 AND）；价格正确（字段：price；组内 AND）

## 题目 33（31630bd2bca463862944）

**题面：** Retrieve the project description for cloud-to-butt.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_description: 提交的 description 满足原 string 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 2 计分：Chrome扩展这一软件类型（字段：description；组内 AND）；完整的原短语→替换短语关系（字段：description；组内 AND）

## 题目 34（32f1684e1634c615f215）

**题面：** View all available color options for the St Patricks Day T-Shirt

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_colors: 提交的 colors 满足原 record_set 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 11 计分：每个正确、不重复的要求列表成员（字段：name；组内 AND）

## 题目 35（365c8f7271b76bca1522）

**题面：** View the turn-by-turn directions for the current route

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_steps: 提交的 steps 满足原 record_set 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 10 计分：每条要求返回的路线指引内容和序号正确（字段：number, instruction；组内 AND）

## 题目 36（366af9836afa8987f721）

**题面：** Export the list of orders to a CSV file.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:export`；downloaded_matching_csv: 至少一个实际下载产物通过原内容及选中对象集合比较。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 616 计分：目标1：记录编号正确（字段：increment_id；组内 AND）；目标1：总额正确（字段：grand_total；组内 AND）；目标2：记录编号正确（字段：increment_id；组内 AND）；目标2：总额正确（字段：grand_total；组内 AND）；目标3：记录编号正确（字段：increment_id；组内 AND）；目标3：总额正确（字段：grand_total；组内 AND）；目标4：记录编号正确（字段：increment_id；组内 AND）；目标4：总额正确（字段：grand_total；组内 AND）；目标5：记录编号正确（字段：increment_id；组内 AND）；目标5：总额正确（字段：grand_total；组内 AND）；目标6：记录编号正确（字段：increment_id；组内 AND）；目标6：总额正确（字段：grand_total；组内 AND）；目标7：记录编号正确（字段：increment_id；组内 AND）；目标7：总额正确（字段：grand_total；组内 AND）；目标8：记录编号正确（字段：increment_id；组内 AND）；目标8：总额正确（字段：grand_total；组内 AND）；目标9：记录编号正确（字段：increment_id；组内 AND）；目标9：总额正确（字段：grand_total；组内 AND）；目标10：记录编号正确（字段：increment_id；组内 AND）；目标10：总额正确（字段：grand_total；组内 AND）；目标11：记录编号正确（字段：increment_id；组内 AND）；目标11：总额正确（字段：grand_total；组内 AND）；目标12：记录编号正确（字段：increment_id；组内 AND）；目标12：总额正确（字段：grand_total；组内 AND）；目标13：记录编号正确（字段：increment_id；组内 AND）；目标13：总额正确（字段：grand_total；组内 AND）；目标14：记录编号正确（字段：increment_id；组内 AND）；目标14：总额正确（字段：grand_total；组内 AND）；目标15：记录编号正确（字段：increment_id；组内 AND）；目标15：总额正确（字段：grand_total；组内 AND）；目标16：记录编号正确（字段：increment_id；组内 AND）；目标16：总额正确（字段：grand_total；组内 AND）；目标17：记录编号正确（字段：increment_id；组内 AND）；目标17：总额正确（字段：grand_total；组内 AND）；目标18：记录编号正确（字段：increment_id；组内 AND）；目标18：总额正确（字段：grand_total；组内 AND）；目标19：记录编号正确（字段：increment_id；组内 AND）；目标19：总额正确（字段：grand_total；组内 AND）；目标20：记录编号正确（字段：increment_id；组内 AND）；目标20：总额正确（字段：grand_total；组内 AND）；目标21：记录编号正确（字段：increment_id；组内 AND）；目标21：总额正确（字段：grand_total；组内 AND）；目标22：记录编号正确（字段：increment_id；组内 AND）；目标22：总额正确（字段：grand_total；组内 AND）；目标23：记录编号正确（字段：increment_id；组内 AND）；目标23：总额正确（字段：grand_total；组内 AND）；目标24：记录编号正确（字段：increment_id；组内 AND）；目标24：总额正确（字段：grand_total；组内 AND）；目标25：记录编号正确（字段：increment_id；组内 AND）；目标25：总额正确（字段：grand_total；组内 AND）；目标26：记录编号正确（字段：increment_id；组内 AND）；目标26：总额正确（字段：grand_total；组内 AND）；目标27：记录编号正确（字段：increment_id；组内 AND）；目标27：总额正确（字段：grand_total；组内 AND）；目标28：记录编号正确（字段：increment_id；组内 AND）；目标28：总额正确（字段：grand_total；组内 AND）；目标29：记录编号正确（字段：increment_id；组内 AND）；目标29：总额正确（字段：grand_total；组内 AND）；目标30：记录编号正确（字段：increment_id；组内 AND）；目标30：总额正确（字段：grand_total；组内 AND）；目标31：记录编号正确（字段：increment_id；组内 AND）；目标31：总额正确（字段：grand_total；组内 AND）；目标32：记录编号正确（字段：increment_id；组内 AND）；目标32：总额正确（字段：grand_total；组内 AND）；目标33：记录编号正确（字段：increment_id；组内 AND）；目标33：总额正确（字段：grand_total；组内 AND）；目标34：记录编号正确（字段：increment_id；组内 AND）；目标34：总额正确（字段：grand_total；组内 AND）；目标35：记录编号正确（字段：increment_id；组内 AND）；目标35：总额正确（字段：grand_total；组内 AND）；目标36：记录编号正确（字段：increment_id；组内 AND）；目标36：总额正确（字段：grand_total；组内 AND）；目标37：记录编号正确（字段：increment_id；组内 AND）；目标37：总额正确（字段：grand_total；组内 AND）；目标38：记录编号正确（字段：increment_id；组内 AND）；目标38：总额正确（字段：grand_total；组内 AND）；目标39：记录编号正确（字段：increment_id；组内 AND）；目标39：总额正确（字段：grand_total；组内 AND）；目标40：记录编号正确（字段：increment_id；组内 AND）；目标40：总额正确（字段：grand_total；组内 AND）；目标41：记录编号正确（字段：increment_id；组内 AND）；目标41：总额正确（字段：grand_total；组内 AND）；目标42：记录编号正确（字段：increment_id；组内 AND）；目标42：总额正确（字段：grand_total；组内 AND）；目标43：记录编号正确（字段：increment_id；组内 AND）；目标43：总额正确（字段：grand_total；组内 AND）；目标44：记录编号正确（字段：increment_id；组内 AND）；目标44：总额正确（字段：grand_total；组内 AND）；目标45：记录编号正确（字段：increment_id；组内 AND）；目标45：总额正确（字段：grand_total；组内 AND）；目标46：记录编号正确（字段：increment_id；组内 AND）；目标46：总额正确（字段：grand_total；组内 AND）；目标47：记录编号正确（字段：increment_id；组内 AND）；目标47：总额正确（字段：grand_total；组内 AND）；目标48：记录编号正确（字段：increment_id；组内 AND）；目标48：总额正确（字段：grand_total；组内 AND）；目标49：记录编号正确（字段：increment_id；组内 AND）；目标49：总额正确（字段：grand_total；组内 AND）；目标50：记录编号正确（字段：increment_id；组内 AND）；目标50：总额正确（字段：grand_total；组内 AND）；目标51：记录编号正确（字段：increment_id；组内 AND）；目标51：总额正确（字段：grand_total；组内 AND）；目标52：记录编号正确（字段：increment_id；组内 AND）；目标52：总额正确（字段：grand_total；组内 AND）；目标53：记录编号正确（字段：increment_id；组内 AND）；目标53：总额正确（字段：grand_total；组内 AND）；目标54：记录编号正确（字段：increment_id；组内 AND）；目标54：总额正确（字段：grand_total；组内 AND）；目标55：记录编号正确（字段：increment_id；组内 AND）；目标55：总额正确（字段：grand_total；组内 AND）；目标56：记录编号正确（字段：increment_id；组内 AND）；目标56：总额正确（字段：grand_total；组内 AND）；目标57：记录编号正确（字段：increment_id；组内 AND）；目标57：总额正确（字段：grand_total；组内 AND）；目标58：记录编号正确（字段：increment_id；组内 AND）；目标58：总额正确（字段：grand_total；组内 AND）；目标59：记录编号正确（字段：increment_id；组内 AND）；目标59：总额正确（字段：grand_total；组内 AND）；目标60：记录编号正确（字段：increment_id；组内 AND）；目标60：总额正确（字段：grand_total；组内 AND）；目标61：记录编号正确（字段：increment_id；组内 AND）；目标61：总额正确（字段：grand_total；组内 AND）；目标62：记录编号正确（字段：increment_id；组内 AND）；目标62：总额正确（字段：grand_total；组内 AND）；目标63：记录编号正确（字段：increment_id；组内 AND）；目标63：总额正确（字段：grand_total；组内 AND）；目标64：记录编号正确（字段：increment_id；组内 AND）；目标64：总额正确（字段：grand_total；组内 AND）；目标65：记录编号正确（字段：increment_id；组内 AND）；目标65：总额正确（字段：grand_total；组内 AND）；目标66：记录编号正确（字段：increment_id；组内 AND）；目标66：总额正确（字段：grand_total；组内 AND）；目标67：记录编号正确（字段：increment_id；组内 AND）；目标67：总额正确（字段：grand_total；组内 AND）；目标68：记录编号正确（字段：increment_id；组内 AND）；目标68：总额正确（字段：grand_total；组内 AND）；目标69：记录编号正确（字段：increment_id；组内 AND）；目标69：总额正确（字段：grand_total；组内 AND）；目标70：记录编号正确（字段：increment_id；组内 AND）；目标70：总额正确（字段：grand_total；组内 AND）；目标71：记录编号正确（字段：increment_id；组内 AND）；目标71：总额正确（字段：grand_total；组内 AND）；目标72：记录编号正确（字段：increment_id；组内 AND）；目标72：总额正确（字段：grand_total；组内 AND）；目标73：记录编号正确（字段：increment_id；组内 AND）；目标73：总额正确（字段：grand_total；组内 AND）；目标74：记录编号正确（字段：increment_id；组内 AND）；目标74：总额正确（字段：grand_total；组内 AND）；目标75：记录编号正确（字段：increment_id；组内 AND）；目标75：总额正确（字段：grand_total；组内 AND）；目标76：记录编号正确（字段：increment_id；组内 AND）；目标76：总额正确（字段：grand_total；组内 AND）；目标77：记录编号正确（字段：increment_id；组内 AND）；目标77：总额正确（字段：grand_total；组内 AND）；目标78：记录编号正确（字段：increment_id；组内 AND）；目标78：总额正确（字段：grand_total；组内 AND）；目标79：记录编号正确（字段：increment_id；组内 AND）；目标79：总额正确（字段：grand_total；组内 AND）；目标80：记录编号正确（字段：increment_id；组内 AND）；目标80：总额正确（字段：grand_total；组内 AND）；目标81：记录编号正确（字段：increment_id；组内 AND）；目标81：总额正确（字段：grand_total；组内 AND）；目标82：记录编号正确（字段：increment_id；组内 AND）；目标82：总额正确（字段：grand_total；组内 AND）；目标83：记录编号正确（字段：increment_id；组内 AND）；目标83：总额正确（字段：grand_total；组内 AND）；目标84：记录编号正确（字段：increment_id；组内 AND）；目标84：总额正确（字段：grand_total；组内 AND）；目标85：记录编号正确（字段：increment_id；组内 AND）；目标85：总额正确（字段：grand_total；组内 AND）；目标86：记录编号正确（字段：increment_id；组内 AND）；目标86：总额正确（字段：grand_total；组内 AND）；目标87：记录编号正确（字段：increment_id；组内 AND）；目标87：总额正确（字段：grand_total；组内 AND）；目标88：记录编号正确（字段：increment_id；组内 AND）；目标88：总额正确（字段：grand_total；组内 AND）；目标89：记录编号正确（字段：increment_id；组内 AND）；目标89：总额正确（字段：grand_total；组内 AND）；目标90：记录编号正确（字段：increment_id；组内 AND）；目标90：总额正确（字段：grand_total；组内 AND）；目标91：记录编号正确（字段：increment_id；组内 AND）；目标91：总额正确（字段：grand_total；组内 AND）；目标92：记录编号正确（字段：increment_id；组内 AND）；目标92：总额正确（字段：grand_total；组内 AND）；目标93：记录编号正确（字段：increment_id；组内 AND）；目标93：总额正确（字段：grand_total；组内 AND）；目标94：记录编号正确（字段：increment_id；组内 AND）；目标94：总额正确（字段：grand_total；组内 AND）；目标95：记录编号正确（字段：increment_id；组内 AND）；目标95：总额正确（字段：grand_total；组内 AND）；目标96：记录编号正确（字段：increment_id；组内 AND）；目标96：总额正确（字段：grand_total；组内 AND）；目标97：记录编号正确（字段：increment_id；组内 AND）；目标97：总额正确（字段：grand_total；组内 AND）；目标98：记录编号正确（字段：increment_id；组内 AND）；目标98：总额正确（字段：grand_total；组内 AND）；目标99：记录编号正确（字段：increment_id；组内 AND）；目标99：总额正确（字段：grand_total；组内 AND）；目标100：记录编号正确（字段：increment_id；组内 AND）；目标100：总额正确（字段：grand_total；组内 AND）；目标101：记录编号正确（字段：increment_id；组内 AND）；目标101：总额正确（字段：grand_total；组内 AND）；目标102：记录编号正确（字段：increment_id；组内 AND）；目标102：总额正确（字段：grand_total；组内 AND）；目标103：记录编号正确（字段：increment_id；组内 AND）；目标103：总额正确（字段：grand_total；组内 AND）；目标104：记录编号正确（字段：increment_id；组内 AND）；目标104：总额正确（字段：grand_total；组内 AND）；目标105：记录编号正确（字段：increment_id；组内 AND）；目标105：总额正确（字段：grand_total；组内 AND）；目标106：记录编号正确（字段：increment_id；组内 AND）；目标106：总额正确（字段：grand_total；组内 AND）；目标107：记录编号正确（字段：increment_id；组内 AND）；目标107：总额正确（字段：grand_total；组内 AND）；目标108：记录编号正确（字段：increment_id；组内 AND）；目标108：总额正确（字段：grand_total；组内 AND）；目标109：记录编号正确（字段：increment_id；组内 AND）；目标109：总额正确（字段：grand_total；组内 AND）；目标110：记录编号正确（字段：increment_id；组内 AND）；目标110：总额正确（字段：grand_total；组内 AND）；目标111：记录编号正确（字段：increment_id；组内 AND）；目标111：总额正确（字段：grand_total；组内 AND）；目标112：记录编号正确（字段：increment_id；组内 AND）；目标112：总额正确（字段：grand_total；组内 AND）；目标113：记录编号正确（字段：increment_id；组内 AND）；目标113：总额正确（字段：grand_total；组内 AND）；目标114：记录编号正确（字段：increment_id；组内 AND）；目标114：总额正确（字段：grand_total；组内 AND）；目标115：记录编号正确（字段：increment_id；组内 AND）；目标115：总额正确（字段：grand_total；组内 AND）；目标116：记录编号正确（字段：increment_id；组内 AND）；目标116：总额正确（字段：grand_total；组内 AND）；目标117：记录编号正确（字段：increment_id；组内 AND）；目标117：总额正确（字段：grand_total；组内 AND）；目标118：记录编号正确（字段：increment_id；组内 AND）；目标118：总额正确（字段：grand_total；组内 AND）；目标119：记录编号正确（字段：increment_id；组内 AND）；目标119：总额正确（字段：grand_total；组内 AND）；目标120：记录编号正确（字段：increment_id；组内 AND）；目标120：总额正确（字段：grand_total；组内 AND）；目标121：记录编号正确（字段：increment_id；组内 AND）；目标121：总额正确（字段：grand_total；组内 AND）；目标122：记录编号正确（字段：increment_id；组内 AND）；目标122：总额正确（字段：grand_total；组内 AND）；目标123：记录编号正确（字段：increment_id；组内 AND）；目标123：总额正确（字段：grand_total；组内 AND）；目标124：记录编号正确（字段：increment_id；组内 AND）；目标124：总额正确（字段：grand_total；组内 AND）；目标125：记录编号正确（字段：increment_id；组内 AND）；目标125：总额正确（字段：grand_total；组内 AND）；目标126：记录编号正确（字段：increment_id；组内 AND）；目标126：总额正确（字段：grand_total；组内 AND）；目标127：记录编号正确（字段：increment_id；组内 AND）；目标127：总额正确（字段：grand_total；组内 AND）；目标128：记录编号正确（字段：increment_id；组内 AND）；目标128：总额正确（字段：grand_total；组内 AND）；目标129：记录编号正确（字段：increment_id；组内 AND）；目标129：总额正确（字段：grand_total；组内 AND）；目标130：记录编号正确（字段：increment_id；组内 AND）；目标130：总额正确（字段：grand_total；组内 AND）；目标131：记录编号正确（字段：increment_id；组内 AND）；目标131：总额正确（字段：grand_total；组内 AND）；目标132：记录编号正确（字段：increment_id；组内 AND）；目标132：总额正确（字段：grand_total；组内 AND）；目标133：记录编号正确（字段：increment_id；组内 AND）；目标133：总额正确（字段：grand_total；组内 AND）；目标134：记录编号正确（字段：increment_id；组内 AND）；目标134：总额正确（字段：grand_total；组内 AND）；目标135：记录编号正确（字段：increment_id；组内 AND）；目标135：总额正确（字段：grand_total；组内 AND）；目标136：记录编号正确（字段：increment_id；组内 AND）；目标136：总额正确（字段：grand_total；组内 AND）；目标137：记录编号正确（字段：increment_id；组内 AND）；目标137：总额正确（字段：grand_total；组内 AND）；目标138：记录编号正确（字段：increment_id；组内 AND）；目标138：总额正确（字段：grand_total；组内 AND）；目标139：记录编号正确（字段：increment_id；组内 AND）；目标139：总额正确（字段：grand_total；组内 AND）；目标140：记录编号正确（字段：increment_id；组内 AND）；目标140：总额正确（字段：grand_total；组内 AND）；目标141：记录编号正确（字段：increment_id；组内 AND）；目标141：总额正确（字段：grand_total；组内 AND）；目标142：记录编号正确（字段：increment_id；组内 AND）；目标142：总额正确（字段：grand_total；组内 AND）；目标143：记录编号正确（字段：increment_id；组内 AND）；目标143：总额正确（字段：grand_total；组内 AND）；目标144：记录编号正确（字段：increment_id；组内 AND）；目标144：总额正确（字段：grand_total；组内 AND）；目标145：记录编号正确（字段：increment_id；组内 AND）；目标145：总额正确（字段：grand_total；组内 AND）；目标146：记录编号正确（字段：increment_id；组内 AND）；目标146：总额正确（字段：grand_total；组内 AND）；目标147：记录编号正确（字段：increment_id；组内 AND）；目标147：总额正确（字段：grand_total；组内 AND）；目标148：记录编号正确（字段：increment_id；组内 AND）；目标148：总额正确（字段：grand_total；组内 AND）；目标149：记录编号正确（字段：increment_id；组内 AND）；目标149：总额正确（字段：grand_total；组内 AND）；目标150：记录编号正确（字段：increment_id；组内 AND）；目标150：总额正确（字段：grand_total；组内 AND）；目标151：记录编号正确（字段：increment_id；组内 AND）；目标151：总额正确（字段：grand_total；组内 AND）；目标152：记录编号正确（字段：increment_id；组内 AND）；目标152：总额正确（字段：grand_total；组内 AND）；目标153：记录编号正确（字段：increment_id；组内 AND）；目标153：总额正确（字段：grand_total；组内 AND）；目标154：记录编号正确（字段：increment_id；组内 AND）；目标154：总额正确（字段：grand_total；组内 AND）；目标155：记录编号正确（字段：increment_id；组内 AND）；目标155：总额正确（字段：grand_total；组内 AND）；目标156：记录编号正确（字段：increment_id；组内 AND）；目标156：总额正确（字段：grand_total；组内 AND）；目标157：记录编号正确（字段：increment_id；组内 AND）；目标157：总额正确（字段：grand_total；组内 AND）；目标158：记录编号正确（字段：increment_id；组内 AND）；目标158：总额正确（字段：grand_total；组内 AND）；目标159：记录编号正确（字段：increment_id；组内 AND）；目标159：总额正确（字段：grand_total；组内 AND）；目标160：记录编号正确（字段：increment_id；组内 AND）；目标160：总额正确（字段：grand_total；组内 AND）；目标161：记录编号正确（字段：increment_id；组内 AND）；目标161：总额正确（字段：grand_total；组内 AND）；目标162：记录编号正确（字段：increment_id；组内 AND）；目标162：总额正确（字段：grand_total；组内 AND）；目标163：记录编号正确（字段：increment_id；组内 AND）；目标163：总额正确（字段：grand_total；组内 AND）；目标164：记录编号正确（字段：increment_id；组内 AND）；目标164：总额正确（字段：grand_total；组内 AND）；目标165：记录编号正确（字段：increment_id；组内 AND）；目标165：总额正确（字段：grand_total；组内 AND）；目标166：记录编号正确（字段：increment_id；组内 AND）；目标166：总额正确（字段：grand_total；组内 AND）；目标167：记录编号正确（字段：increment_id；组内 AND）；目标167：总额正确（字段：grand_total；组内 AND）；目标168：记录编号正确（字段：increment_id；组内 AND）；目标168：总额正确（字段：grand_total；组内 AND）；目标169：记录编号正确（字段：increment_id；组内 AND）；目标169：总额正确（字段：grand_total；组内 AND）；目标170：记录编号正确（字段：increment_id；组内 AND）；目标170：总额正确（字段：grand_total；组内 AND）；目标171：记录编号正确（字段：increment_id；组内 AND）；目标171：总额正确（字段：grand_total；组内 AND）；目标172：记录编号正确（字段：increment_id；组内 AND）；目标172：总额正确（字段：grand_total；组内 AND）；目标173：记录编号正确（字段：increment_id；组内 AND）；目标173：总额正确（字段：grand_total；组内 AND）；目标174：记录编号正确（字段：increment_id；组内 AND）；目标174：总额正确（字段：grand_total；组内 AND）；目标175：记录编号正确（字段：increment_id；组内 AND）；目标175：总额正确（字段：grand_total；组内 AND）；目标176：记录编号正确（字段：increment_id；组内 AND）；目标176：总额正确（字段：grand_total；组内 AND）；目标177：记录编号正确（字段：increment_id；组内 AND）；目标177：总额正确（字段：grand_total；组内 AND）；目标178：记录编号正确（字段：increment_id；组内 AND）；目标178：总额正确（字段：grand_total；组内 AND）；目标179：记录编号正确（字段：increment_id；组内 AND）；目标179：总额正确（字段：grand_total；组内 AND）；目标180：记录编号正确（字段：increment_id；组内 AND）；目标180：总额正确（字段：grand_total；组内 AND）；目标181：记录编号正确（字段：increment_id；组内 AND）；目标181：总额正确（字段：grand_total；组内 AND）；目标182：记录编号正确（字段：increment_id；组内 AND）；目标182：总额正确（字段：grand_total；组内 AND）；目标183：记录编号正确（字段：increment_id；组内 AND）；目标183：总额正确（字段：grand_total；组内 AND）；目标184：记录编号正确（字段：increment_id；组内 AND）；目标184：总额正确（字段：grand_total；组内 AND）；目标185：记录编号正确（字段：increment_id；组内 AND）；目标185：总额正确（字段：grand_total；组内 AND）；目标186：记录编号正确（字段：increment_id；组内 AND）；目标186：总额正确（字段：grand_total；组内 AND）；目标187：记录编号正确（字段：increment_id；组内 AND）；目标187：总额正确（字段：grand_total；组内 AND）；目标188：记录编号正确（字段：increment_id；组内 AND）；目标188：总额正确（字段：grand_total；组内 AND）；目标189：记录编号正确（字段：increment_id；组内 AND）；目标189：总额正确（字段：grand_total；组内 AND）；目标190：记录编号正确（字段：increment_id；组内 AND）；目标190：总额正确（字段：grand_total；组内 AND）；目标191：记录编号正确（字段：increment_id；组内 AND）；目标191：总额正确（字段：grand_total；组内 AND）；目标192：记录编号正确（字段：increment_id；组内 AND）；目标192：总额正确（字段：grand_total；组内 AND）；目标193：记录编号正确（字段：increment_id；组内 AND）；目标193：总额正确（字段：grand_total；组内 AND）；目标194：记录编号正确（字段：increment_id；组内 AND）；目标194：总额正确（字段：grand_total；组内 AND）；目标195：记录编号正确（字段：increment_id；组内 AND）；目标195：总额正确（字段：grand_total；组内 AND）；目标196：记录编号正确（字段：increment_id；组内 AND）；目标196：总额正确（字段：grand_total；组内 AND）；目标197：记录编号正确（字段：increment_id；组内 AND）；目标197：总额正确（字段：grand_total；组内 AND）；目标198：记录编号正确（字段：increment_id；组内 AND）；目标198：总额正确（字段：grand_total；组内 AND）；目标199：记录编号正确（字段：increment_id；组内 AND）；目标199：总额正确（字段：grand_total；组内 AND）；目标200：记录编号正确（字段：increment_id；组内 AND）；目标200：总额正确（字段：grand_total；组内 AND）；目标201：记录编号正确（字段：increment_id；组内 AND）；目标201：总额正确（字段：grand_total；组内 AND）；目标202：记录编号正确（字段：increment_id；组内 AND）；目标202：总额正确（字段：grand_total；组内 AND）；目标203：记录编号正确（字段：increment_id；组内 AND）；目标203：总额正确（字段：grand_total；组内 AND）；目标204：记录编号正确（字段：increment_id；组内 AND）；目标204：总额正确（字段：grand_total；组内 AND）；目标205：记录编号正确（字段：increment_id；组内 AND）；目标205：总额正确（字段：grand_total；组内 AND）；目标206：记录编号正确（字段：increment_id；组内 AND）；目标206：总额正确（字段：grand_total；组内 AND）；目标207：记录编号正确（字段：increment_id；组内 AND）；目标207：总额正确（字段：grand_total；组内 AND）；目标208：记录编号正确（字段：increment_id；组内 AND）；目标208：总额正确（字段：grand_total；组内 AND）；目标209：记录编号正确（字段：increment_id；组内 AND）；目标209：总额正确（字段：grand_total；组内 AND）；目标210：记录编号正确（字段：increment_id；组内 AND）；目标210：总额正确（字段：grand_total；组内 AND）；目标211：记录编号正确（字段：increment_id；组内 AND）；目标211：总额正确（字段：grand_total；组内 AND）；目标212：记录编号正确（字段：increment_id；组内 AND）；目标212：总额正确（字段：grand_total；组内 AND）；目标213：记录编号正确（字段：increment_id；组内 AND）；目标213：总额正确（字段：grand_total；组内 AND）；目标214：记录编号正确（字段：increment_id；组内 AND）；目标214：总额正确（字段：grand_total；组内 AND）；目标215：记录编号正确（字段：increment_id；组内 AND）；目标215：总额正确（字段：grand_total；组内 AND）；目标216：记录编号正确（字段：increment_id；组内 AND）；目标216：总额正确（字段：grand_total；组内 AND）；目标217：记录编号正确（字段：increment_id；组内 AND）；目标217：总额正确（字段：grand_total；组内 AND）；目标218：记录编号正确（字段：increment_id；组内 AND）；目标218：总额正确（字段：grand_total；组内 AND）；目标219：记录编号正确（字段：increment_id；组内 AND）；目标219：总额正确（字段：grand_total；组内 AND）；目标220：记录编号正确（字段：increment_id；组内 AND）；目标220：总额正确（字段：grand_total；组内 AND）；目标221：记录编号正确（字段：increment_id；组内 AND）；目标221：总额正确（字段：grand_total；组内 AND）；目标222：记录编号正确（字段：increment_id；组内 AND）；目标222：总额正确（字段：grand_total；组内 AND）；目标223：记录编号正确（字段：increment_id；组内 AND）；目标223：总额正确（字段：grand_total；组内 AND）；目标224：记录编号正确（字段：increment_id；组内 AND）；目标224：总额正确（字段：grand_total；组内 AND）；目标225：记录编号正确（字段：increment_id；组内 AND）；目标225：总额正确（字段：grand_total；组内 AND）；目标226：记录编号正确（字段：increment_id；组内 AND）；目标226：总额正确（字段：grand_total；组内 AND）；目标227：记录编号正确（字段：increment_id；组内 AND）；目标227：总额正确（字段：grand_total；组内 AND）；目标228：记录编号正确（字段：increment_id；组内 AND）；目标228：总额正确（字段：grand_total；组内 AND）；目标229：记录编号正确（字段：increment_id；组内 AND）；目标229：总额正确（字段：grand_total；组内 AND）；目标230：记录编号正确（字段：increment_id；组内 AND）；目标230：总额正确（字段：grand_total；组内 AND）；目标231：记录编号正确（字段：increment_id；组内 AND）；目标231：总额正确（字段：grand_total；组内 AND）；目标232：记录编号正确（字段：increment_id；组内 AND）；目标232：总额正确（字段：grand_total；组内 AND）；目标233：记录编号正确（字段：increment_id；组内 AND）；目标233：总额正确（字段：grand_total；组内 AND）；目标234：记录编号正确（字段：increment_id；组内 AND）；目标234：总额正确（字段：grand_total；组内 AND）；目标235：记录编号正确（字段：increment_id；组内 AND）；目标235：总额正确（字段：grand_total；组内 AND）；目标236：记录编号正确（字段：increment_id；组内 AND）；目标236：总额正确（字段：grand_total；组内 AND）；目标237：记录编号正确（字段：increment_id；组内 AND）；目标237：总额正确（字段：grand_total；组内 AND）；目标238：记录编号正确（字段：increment_id；组内 AND）；目标238：总额正确（字段：grand_total；组内 AND）；目标239：记录编号正确（字段：increment_id；组内 AND）；目标239：总额正确（字段：grand_total；组内 AND）；目标240：记录编号正确（字段：increment_id；组内 AND）；目标240：总额正确（字段：grand_total；组内 AND）；目标241：记录编号正确（字段：increment_id；组内 AND）；目标241：总额正确（字段：grand_total；组内 AND）；目标242：记录编号正确（字段：increment_id；组内 AND）；目标242：总额正确（字段：grand_total；组内 AND）；目标243：记录编号正确（字段：increment_id；组内 AND）；目标243：总额正确（字段：grand_total；组内 AND）；目标244：记录编号正确（字段：increment_id；组内 AND）；目标244：总额正确（字段：grand_total；组内 AND）；目标245：记录编号正确（字段：increment_id；组内 AND）；目标245：总额正确（字段：grand_total；组内 AND）；目标246：记录编号正确（字段：increment_id；组内 AND）；目标246：总额正确（字段：grand_total；组内 AND）；目标247：记录编号正确（字段：increment_id；组内 AND）；目标247：总额正确（字段：grand_total；组内 AND）；目标248：记录编号正确（字段：increment_id；组内 AND）；目标248：总额正确（字段：grand_total；组内 AND）；目标249：记录编号正确（字段：increment_id；组内 AND）；目标249：总额正确（字段：grand_total；组内 AND）；目标250：记录编号正确（字段：increment_id；组内 AND）；目标250：总额正确（字段：grand_total；组内 AND）；目标251：记录编号正确（字段：increment_id；组内 AND）；目标251：总额正确（字段：grand_total；组内 AND）；目标252：记录编号正确（字段：increment_id；组内 AND）；目标252：总额正确（字段：grand_total；组内 AND）；目标253：记录编号正确（字段：increment_id；组内 AND）；目标253：总额正确（字段：grand_total；组内 AND）；目标254：记录编号正确（字段：increment_id；组内 AND）；目标254：总额正确（字段：grand_total；组内 AND）；目标255：记录编号正确（字段：increment_id；组内 AND）；目标255：总额正确（字段：grand_total；组内 AND）；目标256：记录编号正确（字段：increment_id；组内 AND）；目标256：总额正确（字段：grand_total；组内 AND）；目标257：记录编号正确（字段：increment_id；组内 AND）；目标257：总额正确（字段：grand_total；组内 AND）；目标258：记录编号正确（字段：increment_id；组内 AND）；目标258：总额正确（字段：grand_total；组内 AND）；目标259：记录编号正确（字段：increment_id；组内 AND）；目标259：总额正确（字段：grand_total；组内 AND）；目标260：记录编号正确（字段：increment_id；组内 AND）；目标260：总额正确（字段：grand_total；组内 AND）；目标261：记录编号正确（字段：increment_id；组内 AND）；目标261：总额正确（字段：grand_total；组内 AND）；目标262：记录编号正确（字段：increment_id；组内 AND）；目标262：总额正确（字段：grand_total；组内 AND）；目标263：记录编号正确（字段：increment_id；组内 AND）；目标263：总额正确（字段：grand_total；组内 AND）；目标264：记录编号正确（字段：increment_id；组内 AND）；目标264：总额正确（字段：grand_total；组内 AND）；目标265：记录编号正确（字段：increment_id；组内 AND）；目标265：总额正确（字段：grand_total；组内 AND）；目标266：记录编号正确（字段：increment_id；组内 AND）；目标266：总额正确（字段：grand_total；组内 AND）；目标267：记录编号正确（字段：increment_id；组内 AND）；目标267：总额正确（字段：grand_total；组内 AND）；目标268：记录编号正确（字段：increment_id；组内 AND）；目标268：总额正确（字段：grand_total；组内 AND）；目标269：记录编号正确（字段：increment_id；组内 AND）；目标269：总额正确（字段：grand_total；组内 AND）；目标270：记录编号正确（字段：increment_id；组内 AND）；目标270：总额正确（字段：grand_total；组内 AND）；目标271：记录编号正确（字段：increment_id；组内 AND）；目标271：总额正确（字段：grand_total；组内 AND）；目标272：记录编号正确（字段：increment_id；组内 AND）；目标272：总额正确（字段：grand_total；组内 AND）；目标273：记录编号正确（字段：increment_id；组内 AND）；目标273：总额正确（字段：grand_total；组内 AND）；目标274：记录编号正确（字段：increment_id；组内 AND）；目标274：总额正确（字段：grand_total；组内 AND）；目标275：记录编号正确（字段：increment_id；组内 AND）；目标275：总额正确（字段：grand_total；组内 AND）；目标276：记录编号正确（字段：increment_id；组内 AND）；目标276：总额正确（字段：grand_total；组内 AND）；目标277：记录编号正确（字段：increment_id；组内 AND）；目标277：总额正确（字段：grand_total；组内 AND）；目标278：记录编号正确（字段：increment_id；组内 AND）；目标278：总额正确（字段：grand_total；组内 AND）；目标279：记录编号正确（字段：increment_id；组内 AND）；目标279：总额正确（字段：grand_total；组内 AND）；目标280：记录编号正确（字段：increment_id；组内 AND）；目标280：总额正确（字段：grand_total；组内 AND）；目标281：记录编号正确（字段：increment_id；组内 AND）；目标281：总额正确（字段：grand_total；组内 AND）；目标282：记录编号正确（字段：increment_id；组内 AND）；目标282：总额正确（字段：grand_total；组内 AND）；目标283：记录编号正确（字段：increment_id；组内 AND）；目标283：总额正确（字段：grand_total；组内 AND）；目标284：记录编号正确（字段：increment_id；组内 AND）；目标284：总额正确（字段：grand_total；组内 AND）；目标285：记录编号正确（字段：increment_id；组内 AND）；目标285：总额正确（字段：grand_total；组内 AND）；目标286：记录编号正确（字段：increment_id；组内 AND）；目标286：总额正确（字段：grand_total；组内 AND）；目标287：记录编号正确（字段：increment_id；组内 AND）；目标287：总额正确（字段：grand_total；组内 AND）；目标288：记录编号正确（字段：increment_id；组内 AND）；目标288：总额正确（字段：grand_total；组内 AND）；目标289：记录编号正确（字段：increment_id；组内 AND）；目标289：总额正确（字段：grand_total；组内 AND）；目标290：记录编号正确（字段：increment_id；组内 AND）；目标290：总额正确（字段：grand_total；组内 AND）；目标291：记录编号正确（字段：increment_id；组内 AND）；目标291：总额正确（字段：grand_total；组内 AND）；目标292：记录编号正确（字段：increment_id；组内 AND）；目标292：总额正确（字段：grand_total；组内 AND）；目标293：记录编号正确（字段：increment_id；组内 AND）；目标293：总额正确（字段：grand_total；组内 AND）；目标294：记录编号正确（字段：increment_id；组内 AND）；目标294：总额正确（字段：grand_total；组内 AND）；目标295：记录编号正确（字段：increment_id；组内 AND）；目标295：总额正确（字段：grand_total；组内 AND）；目标296：记录编号正确（字段：increment_id；组内 AND）；目标296：总额正确（字段：grand_total；组内 AND）；目标297：记录编号正确（字段：increment_id；组内 AND）；目标297：总额正确（字段：grand_total；组内 AND）；目标298：记录编号正确（字段：increment_id；组内 AND）；目标298：总额正确（字段：grand_total；组内 AND）；目标299：记录编号正确（字段：increment_id；组内 AND）；目标299：总额正确（字段：grand_total；组内 AND）；目标300：记录编号正确（字段：increment_id；组内 AND）；目标300：总额正确（字段：grand_total；组内 AND）；目标301：记录编号正确（字段：increment_id；组内 AND）；目标301：总额正确（字段：grand_total；组内 AND）；目标302：记录编号正确（字段：increment_id；组内 AND）；目标302：总额正确（字段：grand_total；组内 AND）；目标303：记录编号正确（字段：increment_id；组内 AND）；目标303：总额正确（字段：grand_total；组内 AND）；目标304：记录编号正确（字段：increment_id；组内 AND）；目标304：总额正确（字段：grand_total；组内 AND）；目标305：记录编号正确（字段：increment_id；组内 AND）；目标305：总额正确（字段：grand_total；组内 AND）；目标306：记录编号正确（字段：increment_id；组内 AND）；目标306：总额正确（字段：grand_total；组内 AND）；目标307：记录编号正确（字段：increment_id；组内 AND）；目标307：总额正确（字段：grand_total；组内 AND）；目标308：记录编号正确（字段：increment_id；组内 AND）；目标308：总额正确（字段：grand_total；组内 AND）

## 题目 37（39289e43a355500e8c35）

**题面：** Report the five search terms with the highest number of uses, including each query text and its number of uses. Include all ties at the cutoff only if they fit within the first five records ordered by query ID.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:collection_query`；exact_result_set: 按原字段比较完整多重集合，包含数量、重复、遗漏和多余记录约束。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 10 计分：目标1：搜索词正确（字段：query_text；组内 AND）；目标1：使用次数正确（字段：popularity；组内 AND）；目标2：搜索词正确（字段：query_text；组内 AND）；目标2：使用次数正确（字段：popularity；组内 AND）；目标3：搜索词正确（字段：query_text；组内 AND）；目标3：使用次数正确（字段：popularity；组内 AND）；目标4：搜索词正确（字段：query_text；组内 AND）；目标4：使用次数正确（字段：popularity；组内 AND）；目标5：搜索词正确（字段：query_text；组内 AND）；目标5：使用次数正确（字段：popularity；组内 AND）

## 题目 38（3a321611e2d35a0bd239）

**题面：** Read and report the project description for The A11Y Project / a11yproject.com.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_description: 提交的 description 满足原 string 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 2 计分：社区推动的项目性质（字段：description；组内 AND）；使数字无障碍更容易的目标（字段：description；组内 AND）

## 题目 39（3d44ea22ddda30c59630）

**题面：** Compare the prices of night vision devices on this page.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_products: 提交的 products 满足原 record_set 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 8 计分：目标1：名称正确（字段：name；组内 AND）；目标1：价格正确（字段：price；组内 AND）；目标2：名称正确（字段：name；组内 AND）；目标2：价格正确（字段：price；组内 AND）；目标3：名称正确（字段：name；组内 AND）；目标3：价格正确（字段：price；组内 AND）；目标4：名称正确（字段：name；组内 AND）；目标4：价格正确（字段：price；组内 AND）

## 题目 40（40d3da9f6369adbe5def）

**题面：** For this local training variant, update the email template named "Training Existing Email". Save subject "Updated customer information" and body exactly "Please review your account information in our training store.".

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:update`；persisted_requested_value: 原选中对象已持久保存，并整体满足 update_matches 的请求条件。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; other_records_unchanged: 原目标以外的同实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; other_records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 2 计分：主题正确（字段：template_subject；组内 AND）；正文正确（字段：template_text；组内 AND）

## 题目 41（40fbee5ad66e332b21a4）

**题面：** List all items currently in the shopping cart.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_items: 提交的 items 满足原 record_set 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 3 计分：每个正确、不重复的要求列表成员（字段：name；组内 AND）

## 题目 42（41b2004f1c9ede24b496）

**题面：** View the available shipping methods for my order

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_shipping_methods: 提交的 shipping_methods 满足原 record_set 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 2 计分：承运商与配送方式的完整组合（字段：carrier, method；组内 AND）；各配送方式的对应费用正确（字段：cost；组内 AND）

## 题目 43（44a8860ebdd452352176）

**题面：** Get the rating and number of reviews for the Pre-baked Gingerbread House Kit Value Pack.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；path: /anvme/workspace/r102bf10-lab-generate-skill/experiments/train-partial-reward-20261117-v1/trace-review-v1/answer-completion-review.json; sha256: 8bce509b9b45b9e06b7bef0a47fb080d5715c3ca326a65313c447788501df5be

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 2 计分：answer_rating_percent（字段：answer_rating_percent；组内 AND）；answer_review_count（字段：answer_review_count；组内 AND）

## 题目 44（44e44103a11d8563d0e1）

**题面：** For this local training variant, reference date is September 30, 2026. Save Test Product special price 19.99 from October 5 through October 11, 2026.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:update`；persisted_requested_value: 原选中对象已持久保存，并整体满足 update_matches 的请求条件。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; other_records_unchanged: 原目标以外的同实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; other_records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 3 计分：促销价格正确（字段：special_price；组内 AND）；促销开始日期正确（字段：special_from_date；组内 AND）；促销结束日期正确（字段：special_to_date；组内 AND）

## 题目 45（45121a4e0f96f3cfecd2）

**题面：** Find all forums that start with the letter B

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_items: 提交的 items 满足原 record_set 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 5 计分：每个正确、不重复的要求列表成员（字段：name；组内 AND）

## 题目 46（4610743cece3a992dce5）

**题面：** Find all orders placed by Adam Garcia

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:collection_query`；exact_result_set: 按原字段比较完整多重集合，包含数量、重复、遗漏和多余记录约束。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 13 计分：每个正确的目标记录/列表成员（字段：increment_id；组内 AND）

## 题目 47（4669e83f3f415914e5aa）

**题面：** Create a customer group named "VIP Customers" and exclude the "Main Website" from this group.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:create`；new_matching_record_saved: 原选择条件匹配且本次新增的记录恰好一条。; created_record_conditions: 该唯一新记录整体满足原 create_conditions。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; existing_records_unchanged: 原有实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; existing_records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 3 计分：实际新增并保存一个本任务可唯一绑定的有效对象（字段：；组内 AND）；名称正确（字段：name；组内 AND）；网站排除配置正确（字段：excluded_website_ids；组内 AND）

## 题目 48（46c0329e4f0e6684aa4e）

**题面：** Discover which websites or projects are currently using the a11y-syntax-highlighting themes

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_items: 提交的 items 满足原 record_set 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 7 计分：每个正确、不重复的要求列表成员（字段：name；组内 AND）

## 题目 49（48f12d69e2ac92bbc655）

**题面：** Export all order data from the Magento Admin panel.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:export`；downloaded_matching_csv: 至少一个实际下载产物通过原内容及选中对象集合比较。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 616 计分：目标1：记录编号正确（字段：increment_id；组内 AND）；目标1：总额正确（字段：grand_total；组内 AND）；目标2：记录编号正确（字段：increment_id；组内 AND）；目标2：总额正确（字段：grand_total；组内 AND）；目标3：记录编号正确（字段：increment_id；组内 AND）；目标3：总额正确（字段：grand_total；组内 AND）；目标4：记录编号正确（字段：increment_id；组内 AND）；目标4：总额正确（字段：grand_total；组内 AND）；目标5：记录编号正确（字段：increment_id；组内 AND）；目标5：总额正确（字段：grand_total；组内 AND）；目标6：记录编号正确（字段：increment_id；组内 AND）；目标6：总额正确（字段：grand_total；组内 AND）；目标7：记录编号正确（字段：increment_id；组内 AND）；目标7：总额正确（字段：grand_total；组内 AND）；目标8：记录编号正确（字段：increment_id；组内 AND）；目标8：总额正确（字段：grand_total；组内 AND）；目标9：记录编号正确（字段：increment_id；组内 AND）；目标9：总额正确（字段：grand_total；组内 AND）；目标10：记录编号正确（字段：increment_id；组内 AND）；目标10：总额正确（字段：grand_total；组内 AND）；目标11：记录编号正确（字段：increment_id；组内 AND）；目标11：总额正确（字段：grand_total；组内 AND）；目标12：记录编号正确（字段：increment_id；组内 AND）；目标12：总额正确（字段：grand_total；组内 AND）；目标13：记录编号正确（字段：increment_id；组内 AND）；目标13：总额正确（字段：grand_total；组内 AND）；目标14：记录编号正确（字段：increment_id；组内 AND）；目标14：总额正确（字段：grand_total；组内 AND）；目标15：记录编号正确（字段：increment_id；组内 AND）；目标15：总额正确（字段：grand_total；组内 AND）；目标16：记录编号正确（字段：increment_id；组内 AND）；目标16：总额正确（字段：grand_total；组内 AND）；目标17：记录编号正确（字段：increment_id；组内 AND）；目标17：总额正确（字段：grand_total；组内 AND）；目标18：记录编号正确（字段：increment_id；组内 AND）；目标18：总额正确（字段：grand_total；组内 AND）；目标19：记录编号正确（字段：increment_id；组内 AND）；目标19：总额正确（字段：grand_total；组内 AND）；目标20：记录编号正确（字段：increment_id；组内 AND）；目标20：总额正确（字段：grand_total；组内 AND）；目标21：记录编号正确（字段：increment_id；组内 AND）；目标21：总额正确（字段：grand_total；组内 AND）；目标22：记录编号正确（字段：increment_id；组内 AND）；目标22：总额正确（字段：grand_total；组内 AND）；目标23：记录编号正确（字段：increment_id；组内 AND）；目标23：总额正确（字段：grand_total；组内 AND）；目标24：记录编号正确（字段：increment_id；组内 AND）；目标24：总额正确（字段：grand_total；组内 AND）；目标25：记录编号正确（字段：increment_id；组内 AND）；目标25：总额正确（字段：grand_total；组内 AND）；目标26：记录编号正确（字段：increment_id；组内 AND）；目标26：总额正确（字段：grand_total；组内 AND）；目标27：记录编号正确（字段：increment_id；组内 AND）；目标27：总额正确（字段：grand_total；组内 AND）；目标28：记录编号正确（字段：increment_id；组内 AND）；目标28：总额正确（字段：grand_total；组内 AND）；目标29：记录编号正确（字段：increment_id；组内 AND）；目标29：总额正确（字段：grand_total；组内 AND）；目标30：记录编号正确（字段：increment_id；组内 AND）；目标30：总额正确（字段：grand_total；组内 AND）；目标31：记录编号正确（字段：increment_id；组内 AND）；目标31：总额正确（字段：grand_total；组内 AND）；目标32：记录编号正确（字段：increment_id；组内 AND）；目标32：总额正确（字段：grand_total；组内 AND）；目标33：记录编号正确（字段：increment_id；组内 AND）；目标33：总额正确（字段：grand_total；组内 AND）；目标34：记录编号正确（字段：increment_id；组内 AND）；目标34：总额正确（字段：grand_total；组内 AND）；目标35：记录编号正确（字段：increment_id；组内 AND）；目标35：总额正确（字段：grand_total；组内 AND）；目标36：记录编号正确（字段：increment_id；组内 AND）；目标36：总额正确（字段：grand_total；组内 AND）；目标37：记录编号正确（字段：increment_id；组内 AND）；目标37：总额正确（字段：grand_total；组内 AND）；目标38：记录编号正确（字段：increment_id；组内 AND）；目标38：总额正确（字段：grand_total；组内 AND）；目标39：记录编号正确（字段：increment_id；组内 AND）；目标39：总额正确（字段：grand_total；组内 AND）；目标40：记录编号正确（字段：increment_id；组内 AND）；目标40：总额正确（字段：grand_total；组内 AND）；目标41：记录编号正确（字段：increment_id；组内 AND）；目标41：总额正确（字段：grand_total；组内 AND）；目标42：记录编号正确（字段：increment_id；组内 AND）；目标42：总额正确（字段：grand_total；组内 AND）；目标43：记录编号正确（字段：increment_id；组内 AND）；目标43：总额正确（字段：grand_total；组内 AND）；目标44：记录编号正确（字段：increment_id；组内 AND）；目标44：总额正确（字段：grand_total；组内 AND）；目标45：记录编号正确（字段：increment_id；组内 AND）；目标45：总额正确（字段：grand_total；组内 AND）；目标46：记录编号正确（字段：increment_id；组内 AND）；目标46：总额正确（字段：grand_total；组内 AND）；目标47：记录编号正确（字段：increment_id；组内 AND）；目标47：总额正确（字段：grand_total；组内 AND）；目标48：记录编号正确（字段：increment_id；组内 AND）；目标48：总额正确（字段：grand_total；组内 AND）；目标49：记录编号正确（字段：increment_id；组内 AND）；目标49：总额正确（字段：grand_total；组内 AND）；目标50：记录编号正确（字段：increment_id；组内 AND）；目标50：总额正确（字段：grand_total；组内 AND）；目标51：记录编号正确（字段：increment_id；组内 AND）；目标51：总额正确（字段：grand_total；组内 AND）；目标52：记录编号正确（字段：increment_id；组内 AND）；目标52：总额正确（字段：grand_total；组内 AND）；目标53：记录编号正确（字段：increment_id；组内 AND）；目标53：总额正确（字段：grand_total；组内 AND）；目标54：记录编号正确（字段：increment_id；组内 AND）；目标54：总额正确（字段：grand_total；组内 AND）；目标55：记录编号正确（字段：increment_id；组内 AND）；目标55：总额正确（字段：grand_total；组内 AND）；目标56：记录编号正确（字段：increment_id；组内 AND）；目标56：总额正确（字段：grand_total；组内 AND）；目标57：记录编号正确（字段：increment_id；组内 AND）；目标57：总额正确（字段：grand_total；组内 AND）；目标58：记录编号正确（字段：increment_id；组内 AND）；目标58：总额正确（字段：grand_total；组内 AND）；目标59：记录编号正确（字段：increment_id；组内 AND）；目标59：总额正确（字段：grand_total；组内 AND）；目标60：记录编号正确（字段：increment_id；组内 AND）；目标60：总额正确（字段：grand_total；组内 AND）；目标61：记录编号正确（字段：increment_id；组内 AND）；目标61：总额正确（字段：grand_total；组内 AND）；目标62：记录编号正确（字段：increment_id；组内 AND）；目标62：总额正确（字段：grand_total；组内 AND）；目标63：记录编号正确（字段：increment_id；组内 AND）；目标63：总额正确（字段：grand_total；组内 AND）；目标64：记录编号正确（字段：increment_id；组内 AND）；目标64：总额正确（字段：grand_total；组内 AND）；目标65：记录编号正确（字段：increment_id；组内 AND）；目标65：总额正确（字段：grand_total；组内 AND）；目标66：记录编号正确（字段：increment_id；组内 AND）；目标66：总额正确（字段：grand_total；组内 AND）；目标67：记录编号正确（字段：increment_id；组内 AND）；目标67：总额正确（字段：grand_total；组内 AND）；目标68：记录编号正确（字段：increment_id；组内 AND）；目标68：总额正确（字段：grand_total；组内 AND）；目标69：记录编号正确（字段：increment_id；组内 AND）；目标69：总额正确（字段：grand_total；组内 AND）；目标70：记录编号正确（字段：increment_id；组内 AND）；目标70：总额正确（字段：grand_total；组内 AND）；目标71：记录编号正确（字段：increment_id；组内 AND）；目标71：总额正确（字段：grand_total；组内 AND）；目标72：记录编号正确（字段：increment_id；组内 AND）；目标72：总额正确（字段：grand_total；组内 AND）；目标73：记录编号正确（字段：increment_id；组内 AND）；目标73：总额正确（字段：grand_total；组内 AND）；目标74：记录编号正确（字段：increment_id；组内 AND）；目标74：总额正确（字段：grand_total；组内 AND）；目标75：记录编号正确（字段：increment_id；组内 AND）；目标75：总额正确（字段：grand_total；组内 AND）；目标76：记录编号正确（字段：increment_id；组内 AND）；目标76：总额正确（字段：grand_total；组内 AND）；目标77：记录编号正确（字段：increment_id；组内 AND）；目标77：总额正确（字段：grand_total；组内 AND）；目标78：记录编号正确（字段：increment_id；组内 AND）；目标78：总额正确（字段：grand_total；组内 AND）；目标79：记录编号正确（字段：increment_id；组内 AND）；目标79：总额正确（字段：grand_total；组内 AND）；目标80：记录编号正确（字段：increment_id；组内 AND）；目标80：总额正确（字段：grand_total；组内 AND）；目标81：记录编号正确（字段：increment_id；组内 AND）；目标81：总额正确（字段：grand_total；组内 AND）；目标82：记录编号正确（字段：increment_id；组内 AND）；目标82：总额正确（字段：grand_total；组内 AND）；目标83：记录编号正确（字段：increment_id；组内 AND）；目标83：总额正确（字段：grand_total；组内 AND）；目标84：记录编号正确（字段：increment_id；组内 AND）；目标84：总额正确（字段：grand_total；组内 AND）；目标85：记录编号正确（字段：increment_id；组内 AND）；目标85：总额正确（字段：grand_total；组内 AND）；目标86：记录编号正确（字段：increment_id；组内 AND）；目标86：总额正确（字段：grand_total；组内 AND）；目标87：记录编号正确（字段：increment_id；组内 AND）；目标87：总额正确（字段：grand_total；组内 AND）；目标88：记录编号正确（字段：increment_id；组内 AND）；目标88：总额正确（字段：grand_total；组内 AND）；目标89：记录编号正确（字段：increment_id；组内 AND）；目标89：总额正确（字段：grand_total；组内 AND）；目标90：记录编号正确（字段：increment_id；组内 AND）；目标90：总额正确（字段：grand_total；组内 AND）；目标91：记录编号正确（字段：increment_id；组内 AND）；目标91：总额正确（字段：grand_total；组内 AND）；目标92：记录编号正确（字段：increment_id；组内 AND）；目标92：总额正确（字段：grand_total；组内 AND）；目标93：记录编号正确（字段：increment_id；组内 AND）；目标93：总额正确（字段：grand_total；组内 AND）；目标94：记录编号正确（字段：increment_id；组内 AND）；目标94：总额正确（字段：grand_total；组内 AND）；目标95：记录编号正确（字段：increment_id；组内 AND）；目标95：总额正确（字段：grand_total；组内 AND）；目标96：记录编号正确（字段：increment_id；组内 AND）；目标96：总额正确（字段：grand_total；组内 AND）；目标97：记录编号正确（字段：increment_id；组内 AND）；目标97：总额正确（字段：grand_total；组内 AND）；目标98：记录编号正确（字段：increment_id；组内 AND）；目标98：总额正确（字段：grand_total；组内 AND）；目标99：记录编号正确（字段：increment_id；组内 AND）；目标99：总额正确（字段：grand_total；组内 AND）；目标100：记录编号正确（字段：increment_id；组内 AND）；目标100：总额正确（字段：grand_total；组内 AND）；目标101：记录编号正确（字段：increment_id；组内 AND）；目标101：总额正确（字段：grand_total；组内 AND）；目标102：记录编号正确（字段：increment_id；组内 AND）；目标102：总额正确（字段：grand_total；组内 AND）；目标103：记录编号正确（字段：increment_id；组内 AND）；目标103：总额正确（字段：grand_total；组内 AND）；目标104：记录编号正确（字段：increment_id；组内 AND）；目标104：总额正确（字段：grand_total；组内 AND）；目标105：记录编号正确（字段：increment_id；组内 AND）；目标105：总额正确（字段：grand_total；组内 AND）；目标106：记录编号正确（字段：increment_id；组内 AND）；目标106：总额正确（字段：grand_total；组内 AND）；目标107：记录编号正确（字段：increment_id；组内 AND）；目标107：总额正确（字段：grand_total；组内 AND）；目标108：记录编号正确（字段：increment_id；组内 AND）；目标108：总额正确（字段：grand_total；组内 AND）；目标109：记录编号正确（字段：increment_id；组内 AND）；目标109：总额正确（字段：grand_total；组内 AND）；目标110：记录编号正确（字段：increment_id；组内 AND）；目标110：总额正确（字段：grand_total；组内 AND）；目标111：记录编号正确（字段：increment_id；组内 AND）；目标111：总额正确（字段：grand_total；组内 AND）；目标112：记录编号正确（字段：increment_id；组内 AND）；目标112：总额正确（字段：grand_total；组内 AND）；目标113：记录编号正确（字段：increment_id；组内 AND）；目标113：总额正确（字段：grand_total；组内 AND）；目标114：记录编号正确（字段：increment_id；组内 AND）；目标114：总额正确（字段：grand_total；组内 AND）；目标115：记录编号正确（字段：increment_id；组内 AND）；目标115：总额正确（字段：grand_total；组内 AND）；目标116：记录编号正确（字段：increment_id；组内 AND）；目标116：总额正确（字段：grand_total；组内 AND）；目标117：记录编号正确（字段：increment_id；组内 AND）；目标117：总额正确（字段：grand_total；组内 AND）；目标118：记录编号正确（字段：increment_id；组内 AND）；目标118：总额正确（字段：grand_total；组内 AND）；目标119：记录编号正确（字段：increment_id；组内 AND）；目标119：总额正确（字段：grand_total；组内 AND）；目标120：记录编号正确（字段：increment_id；组内 AND）；目标120：总额正确（字段：grand_total；组内 AND）；目标121：记录编号正确（字段：increment_id；组内 AND）；目标121：总额正确（字段：grand_total；组内 AND）；目标122：记录编号正确（字段：increment_id；组内 AND）；目标122：总额正确（字段：grand_total；组内 AND）；目标123：记录编号正确（字段：increment_id；组内 AND）；目标123：总额正确（字段：grand_total；组内 AND）；目标124：记录编号正确（字段：increment_id；组内 AND）；目标124：总额正确（字段：grand_total；组内 AND）；目标125：记录编号正确（字段：increment_id；组内 AND）；目标125：总额正确（字段：grand_total；组内 AND）；目标126：记录编号正确（字段：increment_id；组内 AND）；目标126：总额正确（字段：grand_total；组内 AND）；目标127：记录编号正确（字段：increment_id；组内 AND）；目标127：总额正确（字段：grand_total；组内 AND）；目标128：记录编号正确（字段：increment_id；组内 AND）；目标128：总额正确（字段：grand_total；组内 AND）；目标129：记录编号正确（字段：increment_id；组内 AND）；目标129：总额正确（字段：grand_total；组内 AND）；目标130：记录编号正确（字段：increment_id；组内 AND）；目标130：总额正确（字段：grand_total；组内 AND）；目标131：记录编号正确（字段：increment_id；组内 AND）；目标131：总额正确（字段：grand_total；组内 AND）；目标132：记录编号正确（字段：increment_id；组内 AND）；目标132：总额正确（字段：grand_total；组内 AND）；目标133：记录编号正确（字段：increment_id；组内 AND）；目标133：总额正确（字段：grand_total；组内 AND）；目标134：记录编号正确（字段：increment_id；组内 AND）；目标134：总额正确（字段：grand_total；组内 AND）；目标135：记录编号正确（字段：increment_id；组内 AND）；目标135：总额正确（字段：grand_total；组内 AND）；目标136：记录编号正确（字段：increment_id；组内 AND）；目标136：总额正确（字段：grand_total；组内 AND）；目标137：记录编号正确（字段：increment_id；组内 AND）；目标137：总额正确（字段：grand_total；组内 AND）；目标138：记录编号正确（字段：increment_id；组内 AND）；目标138：总额正确（字段：grand_total；组内 AND）；目标139：记录编号正确（字段：increment_id；组内 AND）；目标139：总额正确（字段：grand_total；组内 AND）；目标140：记录编号正确（字段：increment_id；组内 AND）；目标140：总额正确（字段：grand_total；组内 AND）；目标141：记录编号正确（字段：increment_id；组内 AND）；目标141：总额正确（字段：grand_total；组内 AND）；目标142：记录编号正确（字段：increment_id；组内 AND）；目标142：总额正确（字段：grand_total；组内 AND）；目标143：记录编号正确（字段：increment_id；组内 AND）；目标143：总额正确（字段：grand_total；组内 AND）；目标144：记录编号正确（字段：increment_id；组内 AND）；目标144：总额正确（字段：grand_total；组内 AND）；目标145：记录编号正确（字段：increment_id；组内 AND）；目标145：总额正确（字段：grand_total；组内 AND）；目标146：记录编号正确（字段：increment_id；组内 AND）；目标146：总额正确（字段：grand_total；组内 AND）；目标147：记录编号正确（字段：increment_id；组内 AND）；目标147：总额正确（字段：grand_total；组内 AND）；目标148：记录编号正确（字段：increment_id；组内 AND）；目标148：总额正确（字段：grand_total；组内 AND）；目标149：记录编号正确（字段：increment_id；组内 AND）；目标149：总额正确（字段：grand_total；组内 AND）；目标150：记录编号正确（字段：increment_id；组内 AND）；目标150：总额正确（字段：grand_total；组内 AND）；目标151：记录编号正确（字段：increment_id；组内 AND）；目标151：总额正确（字段：grand_total；组内 AND）；目标152：记录编号正确（字段：increment_id；组内 AND）；目标152：总额正确（字段：grand_total；组内 AND）；目标153：记录编号正确（字段：increment_id；组内 AND）；目标153：总额正确（字段：grand_total；组内 AND）；目标154：记录编号正确（字段：increment_id；组内 AND）；目标154：总额正确（字段：grand_total；组内 AND）；目标155：记录编号正确（字段：increment_id；组内 AND）；目标155：总额正确（字段：grand_total；组内 AND）；目标156：记录编号正确（字段：increment_id；组内 AND）；目标156：总额正确（字段：grand_total；组内 AND）；目标157：记录编号正确（字段：increment_id；组内 AND）；目标157：总额正确（字段：grand_total；组内 AND）；目标158：记录编号正确（字段：increment_id；组内 AND）；目标158：总额正确（字段：grand_total；组内 AND）；目标159：记录编号正确（字段：increment_id；组内 AND）；目标159：总额正确（字段：grand_total；组内 AND）；目标160：记录编号正确（字段：increment_id；组内 AND）；目标160：总额正确（字段：grand_total；组内 AND）；目标161：记录编号正确（字段：increment_id；组内 AND）；目标161：总额正确（字段：grand_total；组内 AND）；目标162：记录编号正确（字段：increment_id；组内 AND）；目标162：总额正确（字段：grand_total；组内 AND）；目标163：记录编号正确（字段：increment_id；组内 AND）；目标163：总额正确（字段：grand_total；组内 AND）；目标164：记录编号正确（字段：increment_id；组内 AND）；目标164：总额正确（字段：grand_total；组内 AND）；目标165：记录编号正确（字段：increment_id；组内 AND）；目标165：总额正确（字段：grand_total；组内 AND）；目标166：记录编号正确（字段：increment_id；组内 AND）；目标166：总额正确（字段：grand_total；组内 AND）；目标167：记录编号正确（字段：increment_id；组内 AND）；目标167：总额正确（字段：grand_total；组内 AND）；目标168：记录编号正确（字段：increment_id；组内 AND）；目标168：总额正确（字段：grand_total；组内 AND）；目标169：记录编号正确（字段：increment_id；组内 AND）；目标169：总额正确（字段：grand_total；组内 AND）；目标170：记录编号正确（字段：increment_id；组内 AND）；目标170：总额正确（字段：grand_total；组内 AND）；目标171：记录编号正确（字段：increment_id；组内 AND）；目标171：总额正确（字段：grand_total；组内 AND）；目标172：记录编号正确（字段：increment_id；组内 AND）；目标172：总额正确（字段：grand_total；组内 AND）；目标173：记录编号正确（字段：increment_id；组内 AND）；目标173：总额正确（字段：grand_total；组内 AND）；目标174：记录编号正确（字段：increment_id；组内 AND）；目标174：总额正确（字段：grand_total；组内 AND）；目标175：记录编号正确（字段：increment_id；组内 AND）；目标175：总额正确（字段：grand_total；组内 AND）；目标176：记录编号正确（字段：increment_id；组内 AND）；目标176：总额正确（字段：grand_total；组内 AND）；目标177：记录编号正确（字段：increment_id；组内 AND）；目标177：总额正确（字段：grand_total；组内 AND）；目标178：记录编号正确（字段：increment_id；组内 AND）；目标178：总额正确（字段：grand_total；组内 AND）；目标179：记录编号正确（字段：increment_id；组内 AND）；目标179：总额正确（字段：grand_total；组内 AND）；目标180：记录编号正确（字段：increment_id；组内 AND）；目标180：总额正确（字段：grand_total；组内 AND）；目标181：记录编号正确（字段：increment_id；组内 AND）；目标181：总额正确（字段：grand_total；组内 AND）；目标182：记录编号正确（字段：increment_id；组内 AND）；目标182：总额正确（字段：grand_total；组内 AND）；目标183：记录编号正确（字段：increment_id；组内 AND）；目标183：总额正确（字段：grand_total；组内 AND）；目标184：记录编号正确（字段：increment_id；组内 AND）；目标184：总额正确（字段：grand_total；组内 AND）；目标185：记录编号正确（字段：increment_id；组内 AND）；目标185：总额正确（字段：grand_total；组内 AND）；目标186：记录编号正确（字段：increment_id；组内 AND）；目标186：总额正确（字段：grand_total；组内 AND）；目标187：记录编号正确（字段：increment_id；组内 AND）；目标187：总额正确（字段：grand_total；组内 AND）；目标188：记录编号正确（字段：increment_id；组内 AND）；目标188：总额正确（字段：grand_total；组内 AND）；目标189：记录编号正确（字段：increment_id；组内 AND）；目标189：总额正确（字段：grand_total；组内 AND）；目标190：记录编号正确（字段：increment_id；组内 AND）；目标190：总额正确（字段：grand_total；组内 AND）；目标191：记录编号正确（字段：increment_id；组内 AND）；目标191：总额正确（字段：grand_total；组内 AND）；目标192：记录编号正确（字段：increment_id；组内 AND）；目标192：总额正确（字段：grand_total；组内 AND）；目标193：记录编号正确（字段：increment_id；组内 AND）；目标193：总额正确（字段：grand_total；组内 AND）；目标194：记录编号正确（字段：increment_id；组内 AND）；目标194：总额正确（字段：grand_total；组内 AND）；目标195：记录编号正确（字段：increment_id；组内 AND）；目标195：总额正确（字段：grand_total；组内 AND）；目标196：记录编号正确（字段：increment_id；组内 AND）；目标196：总额正确（字段：grand_total；组内 AND）；目标197：记录编号正确（字段：increment_id；组内 AND）；目标197：总额正确（字段：grand_total；组内 AND）；目标198：记录编号正确（字段：increment_id；组内 AND）；目标198：总额正确（字段：grand_total；组内 AND）；目标199：记录编号正确（字段：increment_id；组内 AND）；目标199：总额正确（字段：grand_total；组内 AND）；目标200：记录编号正确（字段：increment_id；组内 AND）；目标200：总额正确（字段：grand_total；组内 AND）；目标201：记录编号正确（字段：increment_id；组内 AND）；目标201：总额正确（字段：grand_total；组内 AND）；目标202：记录编号正确（字段：increment_id；组内 AND）；目标202：总额正确（字段：grand_total；组内 AND）；目标203：记录编号正确（字段：increment_id；组内 AND）；目标203：总额正确（字段：grand_total；组内 AND）；目标204：记录编号正确（字段：increment_id；组内 AND）；目标204：总额正确（字段：grand_total；组内 AND）；目标205：记录编号正确（字段：increment_id；组内 AND）；目标205：总额正确（字段：grand_total；组内 AND）；目标206：记录编号正确（字段：increment_id；组内 AND）；目标206：总额正确（字段：grand_total；组内 AND）；目标207：记录编号正确（字段：increment_id；组内 AND）；目标207：总额正确（字段：grand_total；组内 AND）；目标208：记录编号正确（字段：increment_id；组内 AND）；目标208：总额正确（字段：grand_total；组内 AND）；目标209：记录编号正确（字段：increment_id；组内 AND）；目标209：总额正确（字段：grand_total；组内 AND）；目标210：记录编号正确（字段：increment_id；组内 AND）；目标210：总额正确（字段：grand_total；组内 AND）；目标211：记录编号正确（字段：increment_id；组内 AND）；目标211：总额正确（字段：grand_total；组内 AND）；目标212：记录编号正确（字段：increment_id；组内 AND）；目标212：总额正确（字段：grand_total；组内 AND）；目标213：记录编号正确（字段：increment_id；组内 AND）；目标213：总额正确（字段：grand_total；组内 AND）；目标214：记录编号正确（字段：increment_id；组内 AND）；目标214：总额正确（字段：grand_total；组内 AND）；目标215：记录编号正确（字段：increment_id；组内 AND）；目标215：总额正确（字段：grand_total；组内 AND）；目标216：记录编号正确（字段：increment_id；组内 AND）；目标216：总额正确（字段：grand_total；组内 AND）；目标217：记录编号正确（字段：increment_id；组内 AND）；目标217：总额正确（字段：grand_total；组内 AND）；目标218：记录编号正确（字段：increment_id；组内 AND）；目标218：总额正确（字段：grand_total；组内 AND）；目标219：记录编号正确（字段：increment_id；组内 AND）；目标219：总额正确（字段：grand_total；组内 AND）；目标220：记录编号正确（字段：increment_id；组内 AND）；目标220：总额正确（字段：grand_total；组内 AND）；目标221：记录编号正确（字段：increment_id；组内 AND）；目标221：总额正确（字段：grand_total；组内 AND）；目标222：记录编号正确（字段：increment_id；组内 AND）；目标222：总额正确（字段：grand_total；组内 AND）；目标223：记录编号正确（字段：increment_id；组内 AND）；目标223：总额正确（字段：grand_total；组内 AND）；目标224：记录编号正确（字段：increment_id；组内 AND）；目标224：总额正确（字段：grand_total；组内 AND）；目标225：记录编号正确（字段：increment_id；组内 AND）；目标225：总额正确（字段：grand_total；组内 AND）；目标226：记录编号正确（字段：increment_id；组内 AND）；目标226：总额正确（字段：grand_total；组内 AND）；目标227：记录编号正确（字段：increment_id；组内 AND）；目标227：总额正确（字段：grand_total；组内 AND）；目标228：记录编号正确（字段：increment_id；组内 AND）；目标228：总额正确（字段：grand_total；组内 AND）；目标229：记录编号正确（字段：increment_id；组内 AND）；目标229：总额正确（字段：grand_total；组内 AND）；目标230：记录编号正确（字段：increment_id；组内 AND）；目标230：总额正确（字段：grand_total；组内 AND）；目标231：记录编号正确（字段：increment_id；组内 AND）；目标231：总额正确（字段：grand_total；组内 AND）；目标232：记录编号正确（字段：increment_id；组内 AND）；目标232：总额正确（字段：grand_total；组内 AND）；目标233：记录编号正确（字段：increment_id；组内 AND）；目标233：总额正确（字段：grand_total；组内 AND）；目标234：记录编号正确（字段：increment_id；组内 AND）；目标234：总额正确（字段：grand_total；组内 AND）；目标235：记录编号正确（字段：increment_id；组内 AND）；目标235：总额正确（字段：grand_total；组内 AND）；目标236：记录编号正确（字段：increment_id；组内 AND）；目标236：总额正确（字段：grand_total；组内 AND）；目标237：记录编号正确（字段：increment_id；组内 AND）；目标237：总额正确（字段：grand_total；组内 AND）；目标238：记录编号正确（字段：increment_id；组内 AND）；目标238：总额正确（字段：grand_total；组内 AND）；目标239：记录编号正确（字段：increment_id；组内 AND）；目标239：总额正确（字段：grand_total；组内 AND）；目标240：记录编号正确（字段：increment_id；组内 AND）；目标240：总额正确（字段：grand_total；组内 AND）；目标241：记录编号正确（字段：increment_id；组内 AND）；目标241：总额正确（字段：grand_total；组内 AND）；目标242：记录编号正确（字段：increment_id；组内 AND）；目标242：总额正确（字段：grand_total；组内 AND）；目标243：记录编号正确（字段：increment_id；组内 AND）；目标243：总额正确（字段：grand_total；组内 AND）；目标244：记录编号正确（字段：increment_id；组内 AND）；目标244：总额正确（字段：grand_total；组内 AND）；目标245：记录编号正确（字段：increment_id；组内 AND）；目标245：总额正确（字段：grand_total；组内 AND）；目标246：记录编号正确（字段：increment_id；组内 AND）；目标246：总额正确（字段：grand_total；组内 AND）；目标247：记录编号正确（字段：increment_id；组内 AND）；目标247：总额正确（字段：grand_total；组内 AND）；目标248：记录编号正确（字段：increment_id；组内 AND）；目标248：总额正确（字段：grand_total；组内 AND）；目标249：记录编号正确（字段：increment_id；组内 AND）；目标249：总额正确（字段：grand_total；组内 AND）；目标250：记录编号正确（字段：increment_id；组内 AND）；目标250：总额正确（字段：grand_total；组内 AND）；目标251：记录编号正确（字段：increment_id；组内 AND）；目标251：总额正确（字段：grand_total；组内 AND）；目标252：记录编号正确（字段：increment_id；组内 AND）；目标252：总额正确（字段：grand_total；组内 AND）；目标253：记录编号正确（字段：increment_id；组内 AND）；目标253：总额正确（字段：grand_total；组内 AND）；目标254：记录编号正确（字段：increment_id；组内 AND）；目标254：总额正确（字段：grand_total；组内 AND）；目标255：记录编号正确（字段：increment_id；组内 AND）；目标255：总额正确（字段：grand_total；组内 AND）；目标256：记录编号正确（字段：increment_id；组内 AND）；目标256：总额正确（字段：grand_total；组内 AND）；目标257：记录编号正确（字段：increment_id；组内 AND）；目标257：总额正确（字段：grand_total；组内 AND）；目标258：记录编号正确（字段：increment_id；组内 AND）；目标258：总额正确（字段：grand_total；组内 AND）；目标259：记录编号正确（字段：increment_id；组内 AND）；目标259：总额正确（字段：grand_total；组内 AND）；目标260：记录编号正确（字段：increment_id；组内 AND）；目标260：总额正确（字段：grand_total；组内 AND）；目标261：记录编号正确（字段：increment_id；组内 AND）；目标261：总额正确（字段：grand_total；组内 AND）；目标262：记录编号正确（字段：increment_id；组内 AND）；目标262：总额正确（字段：grand_total；组内 AND）；目标263：记录编号正确（字段：increment_id；组内 AND）；目标263：总额正确（字段：grand_total；组内 AND）；目标264：记录编号正确（字段：increment_id；组内 AND）；目标264：总额正确（字段：grand_total；组内 AND）；目标265：记录编号正确（字段：increment_id；组内 AND）；目标265：总额正确（字段：grand_total；组内 AND）；目标266：记录编号正确（字段：increment_id；组内 AND）；目标266：总额正确（字段：grand_total；组内 AND）；目标267：记录编号正确（字段：increment_id；组内 AND）；目标267：总额正确（字段：grand_total；组内 AND）；目标268：记录编号正确（字段：increment_id；组内 AND）；目标268：总额正确（字段：grand_total；组内 AND）；目标269：记录编号正确（字段：increment_id；组内 AND）；目标269：总额正确（字段：grand_total；组内 AND）；目标270：记录编号正确（字段：increment_id；组内 AND）；目标270：总额正确（字段：grand_total；组内 AND）；目标271：记录编号正确（字段：increment_id；组内 AND）；目标271：总额正确（字段：grand_total；组内 AND）；目标272：记录编号正确（字段：increment_id；组内 AND）；目标272：总额正确（字段：grand_total；组内 AND）；目标273：记录编号正确（字段：increment_id；组内 AND）；目标273：总额正确（字段：grand_total；组内 AND）；目标274：记录编号正确（字段：increment_id；组内 AND）；目标274：总额正确（字段：grand_total；组内 AND）；目标275：记录编号正确（字段：increment_id；组内 AND）；目标275：总额正确（字段：grand_total；组内 AND）；目标276：记录编号正确（字段：increment_id；组内 AND）；目标276：总额正确（字段：grand_total；组内 AND）；目标277：记录编号正确（字段：increment_id；组内 AND）；目标277：总额正确（字段：grand_total；组内 AND）；目标278：记录编号正确（字段：increment_id；组内 AND）；目标278：总额正确（字段：grand_total；组内 AND）；目标279：记录编号正确（字段：increment_id；组内 AND）；目标279：总额正确（字段：grand_total；组内 AND）；目标280：记录编号正确（字段：increment_id；组内 AND）；目标280：总额正确（字段：grand_total；组内 AND）；目标281：记录编号正确（字段：increment_id；组内 AND）；目标281：总额正确（字段：grand_total；组内 AND）；目标282：记录编号正确（字段：increment_id；组内 AND）；目标282：总额正确（字段：grand_total；组内 AND）；目标283：记录编号正确（字段：increment_id；组内 AND）；目标283：总额正确（字段：grand_total；组内 AND）；目标284：记录编号正确（字段：increment_id；组内 AND）；目标284：总额正确（字段：grand_total；组内 AND）；目标285：记录编号正确（字段：increment_id；组内 AND）；目标285：总额正确（字段：grand_total；组内 AND）；目标286：记录编号正确（字段：increment_id；组内 AND）；目标286：总额正确（字段：grand_total；组内 AND）；目标287：记录编号正确（字段：increment_id；组内 AND）；目标287：总额正确（字段：grand_total；组内 AND）；目标288：记录编号正确（字段：increment_id；组内 AND）；目标288：总额正确（字段：grand_total；组内 AND）；目标289：记录编号正确（字段：increment_id；组内 AND）；目标289：总额正确（字段：grand_total；组内 AND）；目标290：记录编号正确（字段：increment_id；组内 AND）；目标290：总额正确（字段：grand_total；组内 AND）；目标291：记录编号正确（字段：increment_id；组内 AND）；目标291：总额正确（字段：grand_total；组内 AND）；目标292：记录编号正确（字段：increment_id；组内 AND）；目标292：总额正确（字段：grand_total；组内 AND）；目标293：记录编号正确（字段：increment_id；组内 AND）；目标293：总额正确（字段：grand_total；组内 AND）；目标294：记录编号正确（字段：increment_id；组内 AND）；目标294：总额正确（字段：grand_total；组内 AND）；目标295：记录编号正确（字段：increment_id；组内 AND）；目标295：总额正确（字段：grand_total；组内 AND）；目标296：记录编号正确（字段：increment_id；组内 AND）；目标296：总额正确（字段：grand_total；组内 AND）；目标297：记录编号正确（字段：increment_id；组内 AND）；目标297：总额正确（字段：grand_total；组内 AND）；目标298：记录编号正确（字段：increment_id；组内 AND）；目标298：总额正确（字段：grand_total；组内 AND）；目标299：记录编号正确（字段：increment_id；组内 AND）；目标299：总额正确（字段：grand_total；组内 AND）；目标300：记录编号正确（字段：increment_id；组内 AND）；目标300：总额正确（字段：grand_total；组内 AND）；目标301：记录编号正确（字段：increment_id；组内 AND）；目标301：总额正确（字段：grand_total；组内 AND）；目标302：记录编号正确（字段：increment_id；组内 AND）；目标302：总额正确（字段：grand_total；组内 AND）；目标303：记录编号正确（字段：increment_id；组内 AND）；目标303：总额正确（字段：grand_total；组内 AND）；目标304：记录编号正确（字段：increment_id；组内 AND）；目标304：总额正确（字段：grand_total；组内 AND）；目标305：记录编号正确（字段：increment_id；组内 AND）；目标305：总额正确（字段：grand_total；组内 AND）；目标306：记录编号正确（字段：increment_id；组内 AND）；目标306：总额正确（字段：grand_total；组内 AND）；目标307：记录编号正确（字段：increment_id；组内 AND）；目标307：总额正确（字段：grand_total；组内 AND）；目标308：记录编号正确（字段：increment_id；组内 AND）；目标308：总额正确（字段：grand_total；组内 AND）

## 题目 50（4b5dc32a78f627e9c01a）

**题面：** Share the current map view using a short link

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_short_link: 提交的 short_link 满足原 local_url 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 2 计分：短链接所编码的完整地图中心，经纬度同时正确（字段：；组内 AND）；同一短链接编码的缩放级别（字段：；组内 AND）

## 题目 51（4e31cc1527b413e6648e）

**题面：** List all OpenStreetMap Local Chapters.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_items: 提交的 items 满足原 record_set 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 18 计分：每个正确、不重复的要求列表成员（字段：name；组内 AND）

## 题目 52（4ec7495e3a9efa099bea）

**题面：** For this local training variant, save category ID 2 meta title as "Training Store Catalog" and meta description as "Browse the Training Store product catalog."

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:update`；persisted_requested_value: 原选中对象已持久保存，并整体满足 update_matches 的请求条件。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; other_records_unchanged: 原目标以外的同实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; other_records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 2 计分：元标题正确（字段：meta_title；组内 AND）；元描述正确（字段：meta_description；组内 AND）

## 题目 53（502148f62db1683b9bba）

**题面：** Export the current order data to a CSV file on the Magento Admin page.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:export`；downloaded_matching_csv: 至少一个实际下载产物通过原内容及选中对象集合比较。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 616 计分：目标1：记录编号正确（字段：increment_id；组内 AND）；目标1：总额正确（字段：grand_total；组内 AND）；目标2：记录编号正确（字段：increment_id；组内 AND）；目标2：总额正确（字段：grand_total；组内 AND）；目标3：记录编号正确（字段：increment_id；组内 AND）；目标3：总额正确（字段：grand_total；组内 AND）；目标4：记录编号正确（字段：increment_id；组内 AND）；目标4：总额正确（字段：grand_total；组内 AND）；目标5：记录编号正确（字段：increment_id；组内 AND）；目标5：总额正确（字段：grand_total；组内 AND）；目标6：记录编号正确（字段：increment_id；组内 AND）；目标6：总额正确（字段：grand_total；组内 AND）；目标7：记录编号正确（字段：increment_id；组内 AND）；目标7：总额正确（字段：grand_total；组内 AND）；目标8：记录编号正确（字段：increment_id；组内 AND）；目标8：总额正确（字段：grand_total；组内 AND）；目标9：记录编号正确（字段：increment_id；组内 AND）；目标9：总额正确（字段：grand_total；组内 AND）；目标10：记录编号正确（字段：increment_id；组内 AND）；目标10：总额正确（字段：grand_total；组内 AND）；目标11：记录编号正确（字段：increment_id；组内 AND）；目标11：总额正确（字段：grand_total；组内 AND）；目标12：记录编号正确（字段：increment_id；组内 AND）；目标12：总额正确（字段：grand_total；组内 AND）；目标13：记录编号正确（字段：increment_id；组内 AND）；目标13：总额正确（字段：grand_total；组内 AND）；目标14：记录编号正确（字段：increment_id；组内 AND）；目标14：总额正确（字段：grand_total；组内 AND）；目标15：记录编号正确（字段：increment_id；组内 AND）；目标15：总额正确（字段：grand_total；组内 AND）；目标16：记录编号正确（字段：increment_id；组内 AND）；目标16：总额正确（字段：grand_total；组内 AND）；目标17：记录编号正确（字段：increment_id；组内 AND）；目标17：总额正确（字段：grand_total；组内 AND）；目标18：记录编号正确（字段：increment_id；组内 AND）；目标18：总额正确（字段：grand_total；组内 AND）；目标19：记录编号正确（字段：increment_id；组内 AND）；目标19：总额正确（字段：grand_total；组内 AND）；目标20：记录编号正确（字段：increment_id；组内 AND）；目标20：总额正确（字段：grand_total；组内 AND）；目标21：记录编号正确（字段：increment_id；组内 AND）；目标21：总额正确（字段：grand_total；组内 AND）；目标22：记录编号正确（字段：increment_id；组内 AND）；目标22：总额正确（字段：grand_total；组内 AND）；目标23：记录编号正确（字段：increment_id；组内 AND）；目标23：总额正确（字段：grand_total；组内 AND）；目标24：记录编号正确（字段：increment_id；组内 AND）；目标24：总额正确（字段：grand_total；组内 AND）；目标25：记录编号正确（字段：increment_id；组内 AND）；目标25：总额正确（字段：grand_total；组内 AND）；目标26：记录编号正确（字段：increment_id；组内 AND）；目标26：总额正确（字段：grand_total；组内 AND）；目标27：记录编号正确（字段：increment_id；组内 AND）；目标27：总额正确（字段：grand_total；组内 AND）；目标28：记录编号正确（字段：increment_id；组内 AND）；目标28：总额正确（字段：grand_total；组内 AND）；目标29：记录编号正确（字段：increment_id；组内 AND）；目标29：总额正确（字段：grand_total；组内 AND）；目标30：记录编号正确（字段：increment_id；组内 AND）；目标30：总额正确（字段：grand_total；组内 AND）；目标31：记录编号正确（字段：increment_id；组内 AND）；目标31：总额正确（字段：grand_total；组内 AND）；目标32：记录编号正确（字段：increment_id；组内 AND）；目标32：总额正确（字段：grand_total；组内 AND）；目标33：记录编号正确（字段：increment_id；组内 AND）；目标33：总额正确（字段：grand_total；组内 AND）；目标34：记录编号正确（字段：increment_id；组内 AND）；目标34：总额正确（字段：grand_total；组内 AND）；目标35：记录编号正确（字段：increment_id；组内 AND）；目标35：总额正确（字段：grand_total；组内 AND）；目标36：记录编号正确（字段：increment_id；组内 AND）；目标36：总额正确（字段：grand_total；组内 AND）；目标37：记录编号正确（字段：increment_id；组内 AND）；目标37：总额正确（字段：grand_total；组内 AND）；目标38：记录编号正确（字段：increment_id；组内 AND）；目标38：总额正确（字段：grand_total；组内 AND）；目标39：记录编号正确（字段：increment_id；组内 AND）；目标39：总额正确（字段：grand_total；组内 AND）；目标40：记录编号正确（字段：increment_id；组内 AND）；目标40：总额正确（字段：grand_total；组内 AND）；目标41：记录编号正确（字段：increment_id；组内 AND）；目标41：总额正确（字段：grand_total；组内 AND）；目标42：记录编号正确（字段：increment_id；组内 AND）；目标42：总额正确（字段：grand_total；组内 AND）；目标43：记录编号正确（字段：increment_id；组内 AND）；目标43：总额正确（字段：grand_total；组内 AND）；目标44：记录编号正确（字段：increment_id；组内 AND）；目标44：总额正确（字段：grand_total；组内 AND）；目标45：记录编号正确（字段：increment_id；组内 AND）；目标45：总额正确（字段：grand_total；组内 AND）；目标46：记录编号正确（字段：increment_id；组内 AND）；目标46：总额正确（字段：grand_total；组内 AND）；目标47：记录编号正确（字段：increment_id；组内 AND）；目标47：总额正确（字段：grand_total；组内 AND）；目标48：记录编号正确（字段：increment_id；组内 AND）；目标48：总额正确（字段：grand_total；组内 AND）；目标49：记录编号正确（字段：increment_id；组内 AND）；目标49：总额正确（字段：grand_total；组内 AND）；目标50：记录编号正确（字段：increment_id；组内 AND）；目标50：总额正确（字段：grand_total；组内 AND）；目标51：记录编号正确（字段：increment_id；组内 AND）；目标51：总额正确（字段：grand_total；组内 AND）；目标52：记录编号正确（字段：increment_id；组内 AND）；目标52：总额正确（字段：grand_total；组内 AND）；目标53：记录编号正确（字段：increment_id；组内 AND）；目标53：总额正确（字段：grand_total；组内 AND）；目标54：记录编号正确（字段：increment_id；组内 AND）；目标54：总额正确（字段：grand_total；组内 AND）；目标55：记录编号正确（字段：increment_id；组内 AND）；目标55：总额正确（字段：grand_total；组内 AND）；目标56：记录编号正确（字段：increment_id；组内 AND）；目标56：总额正确（字段：grand_total；组内 AND）；目标57：记录编号正确（字段：increment_id；组内 AND）；目标57：总额正确（字段：grand_total；组内 AND）；目标58：记录编号正确（字段：increment_id；组内 AND）；目标58：总额正确（字段：grand_total；组内 AND）；目标59：记录编号正确（字段：increment_id；组内 AND）；目标59：总额正确（字段：grand_total；组内 AND）；目标60：记录编号正确（字段：increment_id；组内 AND）；目标60：总额正确（字段：grand_total；组内 AND）；目标61：记录编号正确（字段：increment_id；组内 AND）；目标61：总额正确（字段：grand_total；组内 AND）；目标62：记录编号正确（字段：increment_id；组内 AND）；目标62：总额正确（字段：grand_total；组内 AND）；目标63：记录编号正确（字段：increment_id；组内 AND）；目标63：总额正确（字段：grand_total；组内 AND）；目标64：记录编号正确（字段：increment_id；组内 AND）；目标64：总额正确（字段：grand_total；组内 AND）；目标65：记录编号正确（字段：increment_id；组内 AND）；目标65：总额正确（字段：grand_total；组内 AND）；目标66：记录编号正确（字段：increment_id；组内 AND）；目标66：总额正确（字段：grand_total；组内 AND）；目标67：记录编号正确（字段：increment_id；组内 AND）；目标67：总额正确（字段：grand_total；组内 AND）；目标68：记录编号正确（字段：increment_id；组内 AND）；目标68：总额正确（字段：grand_total；组内 AND）；目标69：记录编号正确（字段：increment_id；组内 AND）；目标69：总额正确（字段：grand_total；组内 AND）；目标70：记录编号正确（字段：increment_id；组内 AND）；目标70：总额正确（字段：grand_total；组内 AND）；目标71：记录编号正确（字段：increment_id；组内 AND）；目标71：总额正确（字段：grand_total；组内 AND）；目标72：记录编号正确（字段：increment_id；组内 AND）；目标72：总额正确（字段：grand_total；组内 AND）；目标73：记录编号正确（字段：increment_id；组内 AND）；目标73：总额正确（字段：grand_total；组内 AND）；目标74：记录编号正确（字段：increment_id；组内 AND）；目标74：总额正确（字段：grand_total；组内 AND）；目标75：记录编号正确（字段：increment_id；组内 AND）；目标75：总额正确（字段：grand_total；组内 AND）；目标76：记录编号正确（字段：increment_id；组内 AND）；目标76：总额正确（字段：grand_total；组内 AND）；目标77：记录编号正确（字段：increment_id；组内 AND）；目标77：总额正确（字段：grand_total；组内 AND）；目标78：记录编号正确（字段：increment_id；组内 AND）；目标78：总额正确（字段：grand_total；组内 AND）；目标79：记录编号正确（字段：increment_id；组内 AND）；目标79：总额正确（字段：grand_total；组内 AND）；目标80：记录编号正确（字段：increment_id；组内 AND）；目标80：总额正确（字段：grand_total；组内 AND）；目标81：记录编号正确（字段：increment_id；组内 AND）；目标81：总额正确（字段：grand_total；组内 AND）；目标82：记录编号正确（字段：increment_id；组内 AND）；目标82：总额正确（字段：grand_total；组内 AND）；目标83：记录编号正确（字段：increment_id；组内 AND）；目标83：总额正确（字段：grand_total；组内 AND）；目标84：记录编号正确（字段：increment_id；组内 AND）；目标84：总额正确（字段：grand_total；组内 AND）；目标85：记录编号正确（字段：increment_id；组内 AND）；目标85：总额正确（字段：grand_total；组内 AND）；目标86：记录编号正确（字段：increment_id；组内 AND）；目标86：总额正确（字段：grand_total；组内 AND）；目标87：记录编号正确（字段：increment_id；组内 AND）；目标87：总额正确（字段：grand_total；组内 AND）；目标88：记录编号正确（字段：increment_id；组内 AND）；目标88：总额正确（字段：grand_total；组内 AND）；目标89：记录编号正确（字段：increment_id；组内 AND）；目标89：总额正确（字段：grand_total；组内 AND）；目标90：记录编号正确（字段：increment_id；组内 AND）；目标90：总额正确（字段：grand_total；组内 AND）；目标91：记录编号正确（字段：increment_id；组内 AND）；目标91：总额正确（字段：grand_total；组内 AND）；目标92：记录编号正确（字段：increment_id；组内 AND）；目标92：总额正确（字段：grand_total；组内 AND）；目标93：记录编号正确（字段：increment_id；组内 AND）；目标93：总额正确（字段：grand_total；组内 AND）；目标94：记录编号正确（字段：increment_id；组内 AND）；目标94：总额正确（字段：grand_total；组内 AND）；目标95：记录编号正确（字段：increment_id；组内 AND）；目标95：总额正确（字段：grand_total；组内 AND）；目标96：记录编号正确（字段：increment_id；组内 AND）；目标96：总额正确（字段：grand_total；组内 AND）；目标97：记录编号正确（字段：increment_id；组内 AND）；目标97：总额正确（字段：grand_total；组内 AND）；目标98：记录编号正确（字段：increment_id；组内 AND）；目标98：总额正确（字段：grand_total；组内 AND）；目标99：记录编号正确（字段：increment_id；组内 AND）；目标99：总额正确（字段：grand_total；组内 AND）；目标100：记录编号正确（字段：increment_id；组内 AND）；目标100：总额正确（字段：grand_total；组内 AND）；目标101：记录编号正确（字段：increment_id；组内 AND）；目标101：总额正确（字段：grand_total；组内 AND）；目标102：记录编号正确（字段：increment_id；组内 AND）；目标102：总额正确（字段：grand_total；组内 AND）；目标103：记录编号正确（字段：increment_id；组内 AND）；目标103：总额正确（字段：grand_total；组内 AND）；目标104：记录编号正确（字段：increment_id；组内 AND）；目标104：总额正确（字段：grand_total；组内 AND）；目标105：记录编号正确（字段：increment_id；组内 AND）；目标105：总额正确（字段：grand_total；组内 AND）；目标106：记录编号正确（字段：increment_id；组内 AND）；目标106：总额正确（字段：grand_total；组内 AND）；目标107：记录编号正确（字段：increment_id；组内 AND）；目标107：总额正确（字段：grand_total；组内 AND）；目标108：记录编号正确（字段：increment_id；组内 AND）；目标108：总额正确（字段：grand_total；组内 AND）；目标109：记录编号正确（字段：increment_id；组内 AND）；目标109：总额正确（字段：grand_total；组内 AND）；目标110：记录编号正确（字段：increment_id；组内 AND）；目标110：总额正确（字段：grand_total；组内 AND）；目标111：记录编号正确（字段：increment_id；组内 AND）；目标111：总额正确（字段：grand_total；组内 AND）；目标112：记录编号正确（字段：increment_id；组内 AND）；目标112：总额正确（字段：grand_total；组内 AND）；目标113：记录编号正确（字段：increment_id；组内 AND）；目标113：总额正确（字段：grand_total；组内 AND）；目标114：记录编号正确（字段：increment_id；组内 AND）；目标114：总额正确（字段：grand_total；组内 AND）；目标115：记录编号正确（字段：increment_id；组内 AND）；目标115：总额正确（字段：grand_total；组内 AND）；目标116：记录编号正确（字段：increment_id；组内 AND）；目标116：总额正确（字段：grand_total；组内 AND）；目标117：记录编号正确（字段：increment_id；组内 AND）；目标117：总额正确（字段：grand_total；组内 AND）；目标118：记录编号正确（字段：increment_id；组内 AND）；目标118：总额正确（字段：grand_total；组内 AND）；目标119：记录编号正确（字段：increment_id；组内 AND）；目标119：总额正确（字段：grand_total；组内 AND）；目标120：记录编号正确（字段：increment_id；组内 AND）；目标120：总额正确（字段：grand_total；组内 AND）；目标121：记录编号正确（字段：increment_id；组内 AND）；目标121：总额正确（字段：grand_total；组内 AND）；目标122：记录编号正确（字段：increment_id；组内 AND）；目标122：总额正确（字段：grand_total；组内 AND）；目标123：记录编号正确（字段：increment_id；组内 AND）；目标123：总额正确（字段：grand_total；组内 AND）；目标124：记录编号正确（字段：increment_id；组内 AND）；目标124：总额正确（字段：grand_total；组内 AND）；目标125：记录编号正确（字段：increment_id；组内 AND）；目标125：总额正确（字段：grand_total；组内 AND）；目标126：记录编号正确（字段：increment_id；组内 AND）；目标126：总额正确（字段：grand_total；组内 AND）；目标127：记录编号正确（字段：increment_id；组内 AND）；目标127：总额正确（字段：grand_total；组内 AND）；目标128：记录编号正确（字段：increment_id；组内 AND）；目标128：总额正确（字段：grand_total；组内 AND）；目标129：记录编号正确（字段：increment_id；组内 AND）；目标129：总额正确（字段：grand_total；组内 AND）；目标130：记录编号正确（字段：increment_id；组内 AND）；目标130：总额正确（字段：grand_total；组内 AND）；目标131：记录编号正确（字段：increment_id；组内 AND）；目标131：总额正确（字段：grand_total；组内 AND）；目标132：记录编号正确（字段：increment_id；组内 AND）；目标132：总额正确（字段：grand_total；组内 AND）；目标133：记录编号正确（字段：increment_id；组内 AND）；目标133：总额正确（字段：grand_total；组内 AND）；目标134：记录编号正确（字段：increment_id；组内 AND）；目标134：总额正确（字段：grand_total；组内 AND）；目标135：记录编号正确（字段：increment_id；组内 AND）；目标135：总额正确（字段：grand_total；组内 AND）；目标136：记录编号正确（字段：increment_id；组内 AND）；目标136：总额正确（字段：grand_total；组内 AND）；目标137：记录编号正确（字段：increment_id；组内 AND）；目标137：总额正确（字段：grand_total；组内 AND）；目标138：记录编号正确（字段：increment_id；组内 AND）；目标138：总额正确（字段：grand_total；组内 AND）；目标139：记录编号正确（字段：increment_id；组内 AND）；目标139：总额正确（字段：grand_total；组内 AND）；目标140：记录编号正确（字段：increment_id；组内 AND）；目标140：总额正确（字段：grand_total；组内 AND）；目标141：记录编号正确（字段：increment_id；组内 AND）；目标141：总额正确（字段：grand_total；组内 AND）；目标142：记录编号正确（字段：increment_id；组内 AND）；目标142：总额正确（字段：grand_total；组内 AND）；目标143：记录编号正确（字段：increment_id；组内 AND）；目标143：总额正确（字段：grand_total；组内 AND）；目标144：记录编号正确（字段：increment_id；组内 AND）；目标144：总额正确（字段：grand_total；组内 AND）；目标145：记录编号正确（字段：increment_id；组内 AND）；目标145：总额正确（字段：grand_total；组内 AND）；目标146：记录编号正确（字段：increment_id；组内 AND）；目标146：总额正确（字段：grand_total；组内 AND）；目标147：记录编号正确（字段：increment_id；组内 AND）；目标147：总额正确（字段：grand_total；组内 AND）；目标148：记录编号正确（字段：increment_id；组内 AND）；目标148：总额正确（字段：grand_total；组内 AND）；目标149：记录编号正确（字段：increment_id；组内 AND）；目标149：总额正确（字段：grand_total；组内 AND）；目标150：记录编号正确（字段：increment_id；组内 AND）；目标150：总额正确（字段：grand_total；组内 AND）；目标151：记录编号正确（字段：increment_id；组内 AND）；目标151：总额正确（字段：grand_total；组内 AND）；目标152：记录编号正确（字段：increment_id；组内 AND）；目标152：总额正确（字段：grand_total；组内 AND）；目标153：记录编号正确（字段：increment_id；组内 AND）；目标153：总额正确（字段：grand_total；组内 AND）；目标154：记录编号正确（字段：increment_id；组内 AND）；目标154：总额正确（字段：grand_total；组内 AND）；目标155：记录编号正确（字段：increment_id；组内 AND）；目标155：总额正确（字段：grand_total；组内 AND）；目标156：记录编号正确（字段：increment_id；组内 AND）；目标156：总额正确（字段：grand_total；组内 AND）；目标157：记录编号正确（字段：increment_id；组内 AND）；目标157：总额正确（字段：grand_total；组内 AND）；目标158：记录编号正确（字段：increment_id；组内 AND）；目标158：总额正确（字段：grand_total；组内 AND）；目标159：记录编号正确（字段：increment_id；组内 AND）；目标159：总额正确（字段：grand_total；组内 AND）；目标160：记录编号正确（字段：increment_id；组内 AND）；目标160：总额正确（字段：grand_total；组内 AND）；目标161：记录编号正确（字段：increment_id；组内 AND）；目标161：总额正确（字段：grand_total；组内 AND）；目标162：记录编号正确（字段：increment_id；组内 AND）；目标162：总额正确（字段：grand_total；组内 AND）；目标163：记录编号正确（字段：increment_id；组内 AND）；目标163：总额正确（字段：grand_total；组内 AND）；目标164：记录编号正确（字段：increment_id；组内 AND）；目标164：总额正确（字段：grand_total；组内 AND）；目标165：记录编号正确（字段：increment_id；组内 AND）；目标165：总额正确（字段：grand_total；组内 AND）；目标166：记录编号正确（字段：increment_id；组内 AND）；目标166：总额正确（字段：grand_total；组内 AND）；目标167：记录编号正确（字段：increment_id；组内 AND）；目标167：总额正确（字段：grand_total；组内 AND）；目标168：记录编号正确（字段：increment_id；组内 AND）；目标168：总额正确（字段：grand_total；组内 AND）；目标169：记录编号正确（字段：increment_id；组内 AND）；目标169：总额正确（字段：grand_total；组内 AND）；目标170：记录编号正确（字段：increment_id；组内 AND）；目标170：总额正确（字段：grand_total；组内 AND）；目标171：记录编号正确（字段：increment_id；组内 AND）；目标171：总额正确（字段：grand_total；组内 AND）；目标172：记录编号正确（字段：increment_id；组内 AND）；目标172：总额正确（字段：grand_total；组内 AND）；目标173：记录编号正确（字段：increment_id；组内 AND）；目标173：总额正确（字段：grand_total；组内 AND）；目标174：记录编号正确（字段：increment_id；组内 AND）；目标174：总额正确（字段：grand_total；组内 AND）；目标175：记录编号正确（字段：increment_id；组内 AND）；目标175：总额正确（字段：grand_total；组内 AND）；目标176：记录编号正确（字段：increment_id；组内 AND）；目标176：总额正确（字段：grand_total；组内 AND）；目标177：记录编号正确（字段：increment_id；组内 AND）；目标177：总额正确（字段：grand_total；组内 AND）；目标178：记录编号正确（字段：increment_id；组内 AND）；目标178：总额正确（字段：grand_total；组内 AND）；目标179：记录编号正确（字段：increment_id；组内 AND）；目标179：总额正确（字段：grand_total；组内 AND）；目标180：记录编号正确（字段：increment_id；组内 AND）；目标180：总额正确（字段：grand_total；组内 AND）；目标181：记录编号正确（字段：increment_id；组内 AND）；目标181：总额正确（字段：grand_total；组内 AND）；目标182：记录编号正确（字段：increment_id；组内 AND）；目标182：总额正确（字段：grand_total；组内 AND）；目标183：记录编号正确（字段：increment_id；组内 AND）；目标183：总额正确（字段：grand_total；组内 AND）；目标184：记录编号正确（字段：increment_id；组内 AND）；目标184：总额正确（字段：grand_total；组内 AND）；目标185：记录编号正确（字段：increment_id；组内 AND）；目标185：总额正确（字段：grand_total；组内 AND）；目标186：记录编号正确（字段：increment_id；组内 AND）；目标186：总额正确（字段：grand_total；组内 AND）；目标187：记录编号正确（字段：increment_id；组内 AND）；目标187：总额正确（字段：grand_total；组内 AND）；目标188：记录编号正确（字段：increment_id；组内 AND）；目标188：总额正确（字段：grand_total；组内 AND）；目标189：记录编号正确（字段：increment_id；组内 AND）；目标189：总额正确（字段：grand_total；组内 AND）；目标190：记录编号正确（字段：increment_id；组内 AND）；目标190：总额正确（字段：grand_total；组内 AND）；目标191：记录编号正确（字段：increment_id；组内 AND）；目标191：总额正确（字段：grand_total；组内 AND）；目标192：记录编号正确（字段：increment_id；组内 AND）；目标192：总额正确（字段：grand_total；组内 AND）；目标193：记录编号正确（字段：increment_id；组内 AND）；目标193：总额正确（字段：grand_total；组内 AND）；目标194：记录编号正确（字段：increment_id；组内 AND）；目标194：总额正确（字段：grand_total；组内 AND）；目标195：记录编号正确（字段：increment_id；组内 AND）；目标195：总额正确（字段：grand_total；组内 AND）；目标196：记录编号正确（字段：increment_id；组内 AND）；目标196：总额正确（字段：grand_total；组内 AND）；目标197：记录编号正确（字段：increment_id；组内 AND）；目标197：总额正确（字段：grand_total；组内 AND）；目标198：记录编号正确（字段：increment_id；组内 AND）；目标198：总额正确（字段：grand_total；组内 AND）；目标199：记录编号正确（字段：increment_id；组内 AND）；目标199：总额正确（字段：grand_total；组内 AND）；目标200：记录编号正确（字段：increment_id；组内 AND）；目标200：总额正确（字段：grand_total；组内 AND）；目标201：记录编号正确（字段：increment_id；组内 AND）；目标201：总额正确（字段：grand_total；组内 AND）；目标202：记录编号正确（字段：increment_id；组内 AND）；目标202：总额正确（字段：grand_total；组内 AND）；目标203：记录编号正确（字段：increment_id；组内 AND）；目标203：总额正确（字段：grand_total；组内 AND）；目标204：记录编号正确（字段：increment_id；组内 AND）；目标204：总额正确（字段：grand_total；组内 AND）；目标205：记录编号正确（字段：increment_id；组内 AND）；目标205：总额正确（字段：grand_total；组内 AND）；目标206：记录编号正确（字段：increment_id；组内 AND）；目标206：总额正确（字段：grand_total；组内 AND）；目标207：记录编号正确（字段：increment_id；组内 AND）；目标207：总额正确（字段：grand_total；组内 AND）；目标208：记录编号正确（字段：increment_id；组内 AND）；目标208：总额正确（字段：grand_total；组内 AND）；目标209：记录编号正确（字段：increment_id；组内 AND）；目标209：总额正确（字段：grand_total；组内 AND）；目标210：记录编号正确（字段：increment_id；组内 AND）；目标210：总额正确（字段：grand_total；组内 AND）；目标211：记录编号正确（字段：increment_id；组内 AND）；目标211：总额正确（字段：grand_total；组内 AND）；目标212：记录编号正确（字段：increment_id；组内 AND）；目标212：总额正确（字段：grand_total；组内 AND）；目标213：记录编号正确（字段：increment_id；组内 AND）；目标213：总额正确（字段：grand_total；组内 AND）；目标214：记录编号正确（字段：increment_id；组内 AND）；目标214：总额正确（字段：grand_total；组内 AND）；目标215：记录编号正确（字段：increment_id；组内 AND）；目标215：总额正确（字段：grand_total；组内 AND）；目标216：记录编号正确（字段：increment_id；组内 AND）；目标216：总额正确（字段：grand_total；组内 AND）；目标217：记录编号正确（字段：increment_id；组内 AND）；目标217：总额正确（字段：grand_total；组内 AND）；目标218：记录编号正确（字段：increment_id；组内 AND）；目标218：总额正确（字段：grand_total；组内 AND）；目标219：记录编号正确（字段：increment_id；组内 AND）；目标219：总额正确（字段：grand_total；组内 AND）；目标220：记录编号正确（字段：increment_id；组内 AND）；目标220：总额正确（字段：grand_total；组内 AND）；目标221：记录编号正确（字段：increment_id；组内 AND）；目标221：总额正确（字段：grand_total；组内 AND）；目标222：记录编号正确（字段：increment_id；组内 AND）；目标222：总额正确（字段：grand_total；组内 AND）；目标223：记录编号正确（字段：increment_id；组内 AND）；目标223：总额正确（字段：grand_total；组内 AND）；目标224：记录编号正确（字段：increment_id；组内 AND）；目标224：总额正确（字段：grand_total；组内 AND）；目标225：记录编号正确（字段：increment_id；组内 AND）；目标225：总额正确（字段：grand_total；组内 AND）；目标226：记录编号正确（字段：increment_id；组内 AND）；目标226：总额正确（字段：grand_total；组内 AND）；目标227：记录编号正确（字段：increment_id；组内 AND）；目标227：总额正确（字段：grand_total；组内 AND）；目标228：记录编号正确（字段：increment_id；组内 AND）；目标228：总额正确（字段：grand_total；组内 AND）；目标229：记录编号正确（字段：increment_id；组内 AND）；目标229：总额正确（字段：grand_total；组内 AND）；目标230：记录编号正确（字段：increment_id；组内 AND）；目标230：总额正确（字段：grand_total；组内 AND）；目标231：记录编号正确（字段：increment_id；组内 AND）；目标231：总额正确（字段：grand_total；组内 AND）；目标232：记录编号正确（字段：increment_id；组内 AND）；目标232：总额正确（字段：grand_total；组内 AND）；目标233：记录编号正确（字段：increment_id；组内 AND）；目标233：总额正确（字段：grand_total；组内 AND）；目标234：记录编号正确（字段：increment_id；组内 AND）；目标234：总额正确（字段：grand_total；组内 AND）；目标235：记录编号正确（字段：increment_id；组内 AND）；目标235：总额正确（字段：grand_total；组内 AND）；目标236：记录编号正确（字段：increment_id；组内 AND）；目标236：总额正确（字段：grand_total；组内 AND）；目标237：记录编号正确（字段：increment_id；组内 AND）；目标237：总额正确（字段：grand_total；组内 AND）；目标238：记录编号正确（字段：increment_id；组内 AND）；目标238：总额正确（字段：grand_total；组内 AND）；目标239：记录编号正确（字段：increment_id；组内 AND）；目标239：总额正确（字段：grand_total；组内 AND）；目标240：记录编号正确（字段：increment_id；组内 AND）；目标240：总额正确（字段：grand_total；组内 AND）；目标241：记录编号正确（字段：increment_id；组内 AND）；目标241：总额正确（字段：grand_total；组内 AND）；目标242：记录编号正确（字段：increment_id；组内 AND）；目标242：总额正确（字段：grand_total；组内 AND）；目标243：记录编号正确（字段：increment_id；组内 AND）；目标243：总额正确（字段：grand_total；组内 AND）；目标244：记录编号正确（字段：increment_id；组内 AND）；目标244：总额正确（字段：grand_total；组内 AND）；目标245：记录编号正确（字段：increment_id；组内 AND）；目标245：总额正确（字段：grand_total；组内 AND）；目标246：记录编号正确（字段：increment_id；组内 AND）；目标246：总额正确（字段：grand_total；组内 AND）；目标247：记录编号正确（字段：increment_id；组内 AND）；目标247：总额正确（字段：grand_total；组内 AND）；目标248：记录编号正确（字段：increment_id；组内 AND）；目标248：总额正确（字段：grand_total；组内 AND）；目标249：记录编号正确（字段：increment_id；组内 AND）；目标249：总额正确（字段：grand_total；组内 AND）；目标250：记录编号正确（字段：increment_id；组内 AND）；目标250：总额正确（字段：grand_total；组内 AND）；目标251：记录编号正确（字段：increment_id；组内 AND）；目标251：总额正确（字段：grand_total；组内 AND）；目标252：记录编号正确（字段：increment_id；组内 AND）；目标252：总额正确（字段：grand_total；组内 AND）；目标253：记录编号正确（字段：increment_id；组内 AND）；目标253：总额正确（字段：grand_total；组内 AND）；目标254：记录编号正确（字段：increment_id；组内 AND）；目标254：总额正确（字段：grand_total；组内 AND）；目标255：记录编号正确（字段：increment_id；组内 AND）；目标255：总额正确（字段：grand_total；组内 AND）；目标256：记录编号正确（字段：increment_id；组内 AND）；目标256：总额正确（字段：grand_total；组内 AND）；目标257：记录编号正确（字段：increment_id；组内 AND）；目标257：总额正确（字段：grand_total；组内 AND）；目标258：记录编号正确（字段：increment_id；组内 AND）；目标258：总额正确（字段：grand_total；组内 AND）；目标259：记录编号正确（字段：increment_id；组内 AND）；目标259：总额正确（字段：grand_total；组内 AND）；目标260：记录编号正确（字段：increment_id；组内 AND）；目标260：总额正确（字段：grand_total；组内 AND）；目标261：记录编号正确（字段：increment_id；组内 AND）；目标261：总额正确（字段：grand_total；组内 AND）；目标262：记录编号正确（字段：increment_id；组内 AND）；目标262：总额正确（字段：grand_total；组内 AND）；目标263：记录编号正确（字段：increment_id；组内 AND）；目标263：总额正确（字段：grand_total；组内 AND）；目标264：记录编号正确（字段：increment_id；组内 AND）；目标264：总额正确（字段：grand_total；组内 AND）；目标265：记录编号正确（字段：increment_id；组内 AND）；目标265：总额正确（字段：grand_total；组内 AND）；目标266：记录编号正确（字段：increment_id；组内 AND）；目标266：总额正确（字段：grand_total；组内 AND）；目标267：记录编号正确（字段：increment_id；组内 AND）；目标267：总额正确（字段：grand_total；组内 AND）；目标268：记录编号正确（字段：increment_id；组内 AND）；目标268：总额正确（字段：grand_total；组内 AND）；目标269：记录编号正确（字段：increment_id；组内 AND）；目标269：总额正确（字段：grand_total；组内 AND）；目标270：记录编号正确（字段：increment_id；组内 AND）；目标270：总额正确（字段：grand_total；组内 AND）；目标271：记录编号正确（字段：increment_id；组内 AND）；目标271：总额正确（字段：grand_total；组内 AND）；目标272：记录编号正确（字段：increment_id；组内 AND）；目标272：总额正确（字段：grand_total；组内 AND）；目标273：记录编号正确（字段：increment_id；组内 AND）；目标273：总额正确（字段：grand_total；组内 AND）；目标274：记录编号正确（字段：increment_id；组内 AND）；目标274：总额正确（字段：grand_total；组内 AND）；目标275：记录编号正确（字段：increment_id；组内 AND）；目标275：总额正确（字段：grand_total；组内 AND）；目标276：记录编号正确（字段：increment_id；组内 AND）；目标276：总额正确（字段：grand_total；组内 AND）；目标277：记录编号正确（字段：increment_id；组内 AND）；目标277：总额正确（字段：grand_total；组内 AND）；目标278：记录编号正确（字段：increment_id；组内 AND）；目标278：总额正确（字段：grand_total；组内 AND）；目标279：记录编号正确（字段：increment_id；组内 AND）；目标279：总额正确（字段：grand_total；组内 AND）；目标280：记录编号正确（字段：increment_id；组内 AND）；目标280：总额正确（字段：grand_total；组内 AND）；目标281：记录编号正确（字段：increment_id；组内 AND）；目标281：总额正确（字段：grand_total；组内 AND）；目标282：记录编号正确（字段：increment_id；组内 AND）；目标282：总额正确（字段：grand_total；组内 AND）；目标283：记录编号正确（字段：increment_id；组内 AND）；目标283：总额正确（字段：grand_total；组内 AND）；目标284：记录编号正确（字段：increment_id；组内 AND）；目标284：总额正确（字段：grand_total；组内 AND）；目标285：记录编号正确（字段：increment_id；组内 AND）；目标285：总额正确（字段：grand_total；组内 AND）；目标286：记录编号正确（字段：increment_id；组内 AND）；目标286：总额正确（字段：grand_total；组内 AND）；目标287：记录编号正确（字段：increment_id；组内 AND）；目标287：总额正确（字段：grand_total；组内 AND）；目标288：记录编号正确（字段：increment_id；组内 AND）；目标288：总额正确（字段：grand_total；组内 AND）；目标289：记录编号正确（字段：increment_id；组内 AND）；目标289：总额正确（字段：grand_total；组内 AND）；目标290：记录编号正确（字段：increment_id；组内 AND）；目标290：总额正确（字段：grand_total；组内 AND）；目标291：记录编号正确（字段：increment_id；组内 AND）；目标291：总额正确（字段：grand_total；组内 AND）；目标292：记录编号正确（字段：increment_id；组内 AND）；目标292：总额正确（字段：grand_total；组内 AND）；目标293：记录编号正确（字段：increment_id；组内 AND）；目标293：总额正确（字段：grand_total；组内 AND）；目标294：记录编号正确（字段：increment_id；组内 AND）；目标294：总额正确（字段：grand_total；组内 AND）；目标295：记录编号正确（字段：increment_id；组内 AND）；目标295：总额正确（字段：grand_total；组内 AND）；目标296：记录编号正确（字段：increment_id；组内 AND）；目标296：总额正确（字段：grand_total；组内 AND）；目标297：记录编号正确（字段：increment_id；组内 AND）；目标297：总额正确（字段：grand_total；组内 AND）；目标298：记录编号正确（字段：increment_id；组内 AND）；目标298：总额正确（字段：grand_total；组内 AND）；目标299：记录编号正确（字段：increment_id；组内 AND）；目标299：总额正确（字段：grand_total；组内 AND）；目标300：记录编号正确（字段：increment_id；组内 AND）；目标300：总额正确（字段：grand_total；组内 AND）；目标301：记录编号正确（字段：increment_id；组内 AND）；目标301：总额正确（字段：grand_total；组内 AND）；目标302：记录编号正确（字段：increment_id；组内 AND）；目标302：总额正确（字段：grand_total；组内 AND）；目标303：记录编号正确（字段：increment_id；组内 AND）；目标303：总额正确（字段：grand_total；组内 AND）；目标304：记录编号正确（字段：increment_id；组内 AND）；目标304：总额正确（字段：grand_total；组内 AND）；目标305：记录编号正确（字段：increment_id；组内 AND）；目标305：总额正确（字段：grand_total；组内 AND）；目标306：记录编号正确（字段：increment_id；组内 AND）；目标306：总额正确（字段：grand_total；组内 AND）；目标307：记录编号正确（字段：increment_id；组内 AND）；目标307：总额正确（字段：grand_total；组内 AND）；目标308：记录编号正确（字段：increment_id；组内 AND）；目标308：总额正确（字段：grand_total；组内 AND）

## 题目 54（50bb0903de04753ac2ac）

**题面：** Retrieve the step-by-step directions from 40.7900, -73.9600 to 40.6530, -73.9500.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_steps: 提交的 steps 满足原 record_set 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 20 计分：每条要求返回的路线指引内容和序号正确（字段：number, instruction；组内 AND）

## 题目 55（50d1a73742dfe3e4ee1b）

**题面：** Check what formatting options are available for the submission body

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_items: 提交的 items 满足原 record_set 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 26 计分：目标1：要求的格式功能覆盖完整（字段：feature；组内 AND）；目标1：各功能对应语法正确（字段：syntax；组内 AND）；目标2：要求的格式功能覆盖完整（字段：feature；组内 AND）；目标2：各功能对应语法正确（字段：syntax；组内 AND）；目标3：要求的格式功能覆盖完整（字段：feature；组内 AND）；目标3：各功能对应语法正确（字段：syntax；组内 AND）；目标4：要求的格式功能覆盖完整（字段：feature；组内 AND）；目标4：各功能对应语法正确（字段：syntax；组内 AND）；目标5：要求的格式功能覆盖完整（字段：feature；组内 AND）；目标5：各功能对应语法正确（字段：syntax；组内 AND）；目标6：要求的格式功能覆盖完整（字段：feature；组内 AND）；目标6：各功能对应语法正确（字段：syntax；组内 AND）；目标7：要求的格式功能覆盖完整（字段：feature；组内 AND）；目标7：各功能对应语法正确（字段：syntax；组内 AND）；目标8：要求的格式功能覆盖完整（字段：feature；组内 AND）；目标8：各功能对应语法正确（字段：syntax；组内 AND）；目标9：要求的格式功能覆盖完整（字段：feature；组内 AND）；目标9：各功能对应语法正确（字段：syntax；组内 AND）；目标10：要求的格式功能覆盖完整（字段：feature；组内 AND）；目标10：各功能对应语法正确（字段：syntax；组内 AND）；目标11：要求的格式功能覆盖完整（字段：feature；组内 AND）；目标11：各功能对应语法正确（字段：syntax；组内 AND）；目标12：要求的格式功能覆盖完整（字段：feature；组内 AND）；目标12：各功能对应语法正确（字段：syntax；组内 AND）；目标13：要求的格式功能覆盖完整（字段：feature；组内 AND）；目标13：各功能对应语法正确（字段：syntax；组内 AND）

## 题目 56（550fd5ae26b1f06f5fd8）

**题面：** For this local training variant, the following are supplied training product facts. Set the Premium Leather Wallet Description to exactly the text inside the quotation marks, excluding the quotation marks: "Premium Leather Wallet: leather exterior, six card slots and one banknote compartment. Dimensions: 11 cm wide, 9 cm high and 2 cm deep.". Save the change.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:update`；persisted_requested_value: 原选中对象已持久保存，并整体满足 update_matches 的请求条件。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; other_records_unchanged: 原目标以外的同实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; other_records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 4 计分：皮革外部材质（字段：description；组内 AND）；六个卡槽（字段：description；组内 AND）；一个钞票隔层（字段：description；组内 AND）；完整宽高深尺寸及单位（字段：description；组内 AND）

## 题目 57（5786c998736d427970a6）

**题面：** Check the shipping address for the credit memo.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:query`；path: /anvme/workspace/r102bf10-lab-generate-skill/experiments/train-partial-reward-20261117-v1/trace-review-v1/answer-completion-review.json; sha256: 8bce509b9b45b9e06b7bef0a47fb080d5715c3ca326a65313c447788501df5be

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 3 计分：answer_shipping_firstname + answer_shipping_lastname（字段：answer_shipping_firstname, answer_shipping_lastname；组内 AND）；answer_shipping_street（字段：answer_shipping_street；组内 AND）；answer_shipping_city + answer_shipping_region + answer_shipping_postcode + answer_shipping_country_id（字段：answer_shipping_city, answer_shipping_region, answer_shipping_postcode, answer_shipping_country_id；组内 AND）

## 题目 58（586f3f8ccec8d42e4142）

**题面：** For this local training variant, create the email template named "Training Customer Update". Save subject "Your store update" and body exactly "Thank you for shopping at our training store.".

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:create`；new_matching_record_saved: 原选择条件匹配且本次新增的记录恰好一条。; created_record_conditions: 该唯一新记录整体满足原 create_conditions。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; existing_records_unchanged: 原有实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; existing_records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 4 计分：实际新增并保存一个本任务可唯一绑定的有效对象（字段：；组内 AND）；模板名称正确（字段：template_code；组内 AND）；主题正确（字段：template_subject；组内 AND）；正文正确（字段：template_text；组内 AND）

## 题目 59（5f6e00767032bff7429e）

**题面：** Describe how users can control their personal information.
To finish this query, output {"action": "finish", "answer": {"policy_text": "<observed value>"}}. Put exactly these requested fields inside answer: policy_text. Do not return bare fields or a serialized JSON string. Return the requested field values without adding surrounding field labels or explanatory prefixes. When a field explicitly requests a UI label, preserve that observed label as its value. The <observed value> examples are placeholders; use the exact scalar types required by the public task schema. All example values, including 0, 0.0, false and [], illustrate types only; replace them with observed answers. Boolean fields must be JSON true or false, not quoted strings, numeric status codes or explanatory text. Money and numeric fields must follow the public schema; numeric strings are permitted only when that schema permits strings. Use no currency symbols or thousands separators, and no units. For string fields, preserve the requested text and any units explicitly required by the field definition. Telephone values must omit the T: or Tel: label; retain the phone number itself. Record identifiers are exact strings: preserve all leading zeros; do not convert an ID to a number. List-valued fields must be JSON arrays; use [] for no results, never an empty string, null or the word None. Read the requested values without modifying site records. Field types: policy_text=string. Field meanings: {"policy_text": "Copy the complete body of the Controlling your personal information section, including its bullet points and subsequent paragraphs, excluding the heading. Collapse whitespace to single spaces."}.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_policy_text: 提交的 policy_text 满足原 string 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 6 计分：表单中的营销用途拒绝方式（字段：policy_text；组内 AND）；已同意营销用途后的撤回方式（字段：policy_text；组内 AND）；向第三方披露的许可/法律例外（字段：policy_text；组内 AND）；第三方促销信息的同意条件（字段：policy_text；组内 AND）；请求个人信息副本的方式、收费及依据（字段：policy_text；组内 AND）；更正不准确或不完整信息的方法和处理（字段：policy_text；组内 AND）

## 题目 60（6092ffb2a3014d7b5e02）

**题面：** Create and save a new customer named Training Customer with email admin-6092ffb2a3014d7b5e02@example.test and taxvat TRAINING-VAT-100. Keep valid defaults for unspecified optional fields.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:create`；new_matching_record_saved: 原选择条件匹配且本次新增的记录恰好一条。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; existing_records_unchanged: 原有实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; existing_records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 4 计分：实际新增并保存一个本任务可唯一绑定的有效对象（字段：；组内 AND）；完整姓名正确（字段：firstname, lastname；组内 AND）；邮箱正确（字段：email；组内 AND）；税号正确（字段：taxvat；组内 AND）

## 题目 61（60f67c44bf1f5c01fa32）

**题面：** For this local restored-page task, read the dotmailer description on the Magento Marketplace page and return its exact description text. Stay on the local page; external partner websites are outside the task.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:page_text_query`；correct_partner_description: 提交的描述与原指定伙伴的页面参考描述一致。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; correct_page: 终页路径为本题原要求路径。; records_unchanged: 原分支所比较的记录范围保持。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。; partner_still_available: 原指定伙伴的终页描述仍与初始参考相等。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; correct_page; records_unchanged; answer_schema; partner_still_available

**目前的评分准则：** 前提通过后，按固定分母 3 计分：以邮件为核心的多渠道营销平台（字段：description；组内 AND）；Platinum Technology Partner身份（字段：description；组内 AND）；原描述中的B2B/B2C客户和应用说明（字段：description；组内 AND）

## 题目 62（620d3e05fa1c9ef6e951）

**题面：** Find projects that use the MIT license on the Explore page. Consider all non-archived projects accessible to the current account, across the complete project directory.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_projects: 提交的 projects 满足原 record_set 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 52 计分：每个正确、不重复的要求列表成员（字段：path；组内 AND）

## 题目 63（647cc7d981b85811507e）

**题面：** For this local training variant, Assign these five customers to VIP Customers: adam.garcia@gmail.com, alex.martin@gmail.com, alexander.thomas@hotmail.com, amanda.kim@gmail.com, anna.nguyen@yahoo.com.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:bulk_update`；all_selected_records_updated: 原绑定集合内所有对象均存在且满足请求的更新条件。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; other_records_unchanged: 原目标以外的同实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; other_records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 5 计分：每位指定客户的请求修改已保存且生效（字段：group_name；组内 AND）

## 题目 64（6539ca3a65bcebbf51e2）

**题面：** Edit the unsent newsletter with subject Training queued update. Save its body as The local training promotion starts on December 1, 2026. Keep it unsent; do not schedule or send it.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:update`；persisted_requested_value: 原选中对象已持久保存，并整体满足 update_matches 的请求条件。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; other_records_unchanged: 原目标以外的同实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; other_records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 2 计分：保存正文中的活动与开始语义：The local training promotion starts（字段：；组内 AND）；同一正文中的完整开始日期：December 1, 2026（字段：；组内 AND）

## 题目 65（67f0d4e2c0b41fc6ccef）

**题面：** List all projects starred by the user.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_items: 提交的 items 满足原 record_set 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 3 计分：每个正确、不重复的要求列表成员（字段：name；组内 AND）

## 题目 66（690ff879812bbe4d14e5）

**题面：** Find all customers whose gender is Female and report their names and email addresses.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:collection_query`；exact_result_set: 按原字段比较完整多重集合，包含数量、重复、遗漏和多余记录约束。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 2 计分：目标集合覆盖完整且完整姓名正确（字段：firstname, lastname；组内 AND）；邮箱正确（字段：email；组内 AND）

## 题目 67（6b630bcc794fbd170809）

**题面：** For this local training variant, create a custom URL rewrite in Default Store View: request path training-old-category, target path catalog/category/view/id/2, redirect type Permanent (301). Save it.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:create`；new_matching_record_saved: 原选择条件匹配且本次新增的记录恰好一条。; created_record_conditions: 该唯一新记录整体满足原 create_conditions。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; existing_records_unchanged: 原有实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; existing_records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 4 计分：实际新增并保存一个本任务可唯一绑定的有效对象（字段：；组内 AND）；请求路径正确（字段：request_path；组内 AND）；目标路径正确（字段：target_path；组内 AND）；重定向类型正确（字段：redirect_type；组内 AND）

## 题目 68（6c8942d0a681b4fd513f）

**题面：** Explore alternative data download options for large areas.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_items: 提交的 items 满足原 record_set 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 8 计分：目标1：名称正确（字段：name；组内 AND）；目标1：描述正确（字段：description；组内 AND）；目标2：名称正确（字段：name；组内 AND）；目标2：描述正确（字段：description；组内 AND）；目标3：名称正确（字段：name；组内 AND）；目标3：描述正确（字段：description；组内 AND）；目标4：名称正确（字段：name；组内 AND）；目标4：描述正确（字段：description；组内 AND）

## 题目 69（6ccae42e426d87785b76）

**题面：** Check what price ranges are available for Sports & Outdoors items

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_ranges: 提交的 ranges 满足原 record_set 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 2 计分：目标1：每个正确、不重复的要求列表成员（字段：name；组内 AND）；目标2：每个正确、不重复的要求列表成员（字段：name；组内 AND）

## 题目 70（6d9d8bc43ae2c1b8ef1a）

**题面：** For this local training variant, create and save a CMS block for later homepage use with identifier training_home_welcome, title Training Home Welcome, and body Welcome to the training store. Assign it to All Store Views. Publishing or inserting the block into a homepage is outside this task.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:create`；new_matching_record_saved: 原选择条件匹配且本次新增的记录恰好一条。; created_record_conditions: 该唯一新记录整体满足原 create_conditions。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; existing_records_unchanged: 原有实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; existing_records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 5 计分：实际新增并保存一个本任务可唯一绑定的有效对象（字段：；组内 AND）；标识符正确（字段：identifier；组内 AND）；标题正确（字段：title；组内 AND）；正文正确（字段：content；组内 AND）；分配到All Store Views（字段：store_assignments；组内 AND）

## 题目 71（6eb3af9dd0b4842ac443）

**题面：** Compare the number of open issues between different projects

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_projects: 提交的 projects 满足原 record_subset 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 4 计分：项目1的完整身份（字段：path；组内 AND）；项目1的未关闭issue数（字段：open_issues；组内 AND）；项目2的完整身份（字段：path；组内 AND）；项目2的未关闭issue数（字段：open_issues；组内 AND）

## 题目 72（71a327bcbaf0135b6c69）

**题面：** Check what product was refunded in order #000000002

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:collection_query`；exact_result_set: 按原字段比较完整多重集合，包含数量、重复、遗漏和多余记录约束。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 3 计分：目标集合覆盖完整且名称正确（字段：name；组内 AND）；SKU正确（字段：sku；组内 AND）；数量正确（字段：qty；组内 AND）

## 题目 73（727b8a237690197b467e）

**题面：** For this local training variant, save Gaming Laptop meta title as "Gaming Laptop | Training Store" and meta description as "Explore the Gaming Laptop in the Training Store catalog."

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:update`；persisted_requested_value: 原选中对象已持久保存，并整体满足 update_matches 的请求条件。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; other_records_unchanged: 原目标以外的同实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; other_records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 2 计分：元标题正确（字段：meta_title；组内 AND）；元描述正确（字段：meta_description；组内 AND）

## 题目 74（79399fd63d733a51a9d7）

**题面：** Send the order email for order #000000002 to that order's customer through the local store. Completion means the new matching message is recorded by this training environment's local mail capture; delivery to an external inbox is not required. Leave the order unchanged.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:mail`；new_matching_mail_delivered: 新增本地邮件匹配原订单收件人和订单号。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; order_unchanged: 原订单记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; order_unchanged

**目前的评分准则：** 前提通过后，按固定分母 2 计分：实际发送到指定订单客户的邮箱（字段：recipients；组内 AND）；同一邮件包含指定订单的原要求内容标识（字段：subject, body, order_increment_id；组内 AND）

## 题目 75（7b1058619b6bdffb1663）

**题面：** Create and save a simple product named Training Product 7b1058, SKU TRAIN-7b1058619b6bdffb1663, price 9.99. Keep valid defaults for unspecified settings.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:create`；new_matching_record_saved: 原选择条件匹配且本次新增的记录恰好一条。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; existing_records_unchanged: 原有实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; existing_records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 4 计分：实际新增并保存一个本任务可唯一绑定的有效对象（字段：；组内 AND）；名称正确（字段：name；组内 AND）；SKU正确（字段：sku；组内 AND）；价格正确（字段：price；组内 AND）

## 题目 76（7b4161eaac57c41ed83d）

**题面：** Export the customer data as a CSV file.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:export`；downloaded_matching_csv: 至少一个实际下载产物通过原内容及选中对象集合比较。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 140 计分：目标1：名称正确（字段：name；组内 AND）；目标1：邮箱正确（字段：email；组内 AND）；目标2：名称正确（字段：name；组内 AND）；目标2：邮箱正确（字段：email；组内 AND）；目标3：名称正确（字段：name；组内 AND）；目标3：邮箱正确（字段：email；组内 AND）；目标4：名称正确（字段：name；组内 AND）；目标4：邮箱正确（字段：email；组内 AND）；目标5：名称正确（字段：name；组内 AND）；目标5：邮箱正确（字段：email；组内 AND）；目标6：名称正确（字段：name；组内 AND）；目标6：邮箱正确（字段：email；组内 AND）；目标7：名称正确（字段：name；组内 AND）；目标7：邮箱正确（字段：email；组内 AND）；目标8：名称正确（字段：name；组内 AND）；目标8：邮箱正确（字段：email；组内 AND）；目标9：名称正确（字段：name；组内 AND）；目标9：邮箱正确（字段：email；组内 AND）；目标10：名称正确（字段：name；组内 AND）；目标10：邮箱正确（字段：email；组内 AND）；目标11：名称正确（字段：name；组内 AND）；目标11：邮箱正确（字段：email；组内 AND）；目标12：名称正确（字段：name；组内 AND）；目标12：邮箱正确（字段：email；组内 AND）；目标13：名称正确（字段：name；组内 AND）；目标13：邮箱正确（字段：email；组内 AND）；目标14：名称正确（字段：name；组内 AND）；目标14：邮箱正确（字段：email；组内 AND）；目标15：名称正确（字段：name；组内 AND）；目标15：邮箱正确（字段：email；组内 AND）；目标16：名称正确（字段：name；组内 AND）；目标16：邮箱正确（字段：email；组内 AND）；目标17：名称正确（字段：name；组内 AND）；目标17：邮箱正确（字段：email；组内 AND）；目标18：名称正确（字段：name；组内 AND）；目标18：邮箱正确（字段：email；组内 AND）；目标19：名称正确（字段：name；组内 AND）；目标19：邮箱正确（字段：email；组内 AND）；目标20：名称正确（字段：name；组内 AND）；目标20：邮箱正确（字段：email；组内 AND）；目标21：名称正确（字段：name；组内 AND）；目标21：邮箱正确（字段：email；组内 AND）；目标22：名称正确（字段：name；组内 AND）；目标22：邮箱正确（字段：email；组内 AND）；目标23：名称正确（字段：name；组内 AND）；目标23：邮箱正确（字段：email；组内 AND）；目标24：名称正确（字段：name；组内 AND）；目标24：邮箱正确（字段：email；组内 AND）；目标25：名称正确（字段：name；组内 AND）；目标25：邮箱正确（字段：email；组内 AND）；目标26：名称正确（字段：name；组内 AND）；目标26：邮箱正确（字段：email；组内 AND）；目标27：名称正确（字段：name；组内 AND）；目标27：邮箱正确（字段：email；组内 AND）；目标28：名称正确（字段：name；组内 AND）；目标28：邮箱正确（字段：email；组内 AND）；目标29：名称正确（字段：name；组内 AND）；目标29：邮箱正确（字段：email；组内 AND）；目标30：名称正确（字段：name；组内 AND）；目标30：邮箱正确（字段：email；组内 AND）；目标31：名称正确（字段：name；组内 AND）；目标31：邮箱正确（字段：email；组内 AND）；目标32：名称正确（字段：name；组内 AND）；目标32：邮箱正确（字段：email；组内 AND）；目标33：名称正确（字段：name；组内 AND）；目标33：邮箱正确（字段：email；组内 AND）；目标34：名称正确（字段：name；组内 AND）；目标34：邮箱正确（字段：email；组内 AND）；目标35：名称正确（字段：name；组内 AND）；目标35：邮箱正确（字段：email；组内 AND）；目标36：名称正确（字段：name；组内 AND）；目标36：邮箱正确（字段：email；组内 AND）；目标37：名称正确（字段：name；组内 AND）；目标37：邮箱正确（字段：email；组内 AND）；目标38：名称正确（字段：name；组内 AND）；目标38：邮箱正确（字段：email；组内 AND）；目标39：名称正确（字段：name；组内 AND）；目标39：邮箱正确（字段：email；组内 AND）；目标40：名称正确（字段：name；组内 AND）；目标40：邮箱正确（字段：email；组内 AND）；目标41：名称正确（字段：name；组内 AND）；目标41：邮箱正确（字段：email；组内 AND）；目标42：名称正确（字段：name；组内 AND）；目标42：邮箱正确（字段：email；组内 AND）；目标43：名称正确（字段：name；组内 AND）；目标43：邮箱正确（字段：email；组内 AND）；目标44：名称正确（字段：name；组内 AND）；目标44：邮箱正确（字段：email；组内 AND）；目标45：名称正确（字段：name；组内 AND）；目标45：邮箱正确（字段：email；组内 AND）；目标46：名称正确（字段：name；组内 AND）；目标46：邮箱正确（字段：email；组内 AND）；目标47：名称正确（字段：name；组内 AND）；目标47：邮箱正确（字段：email；组内 AND）；目标48：名称正确（字段：name；组内 AND）；目标48：邮箱正确（字段：email；组内 AND）；目标49：名称正确（字段：name；组内 AND）；目标49：邮箱正确（字段：email；组内 AND）；目标50：名称正确（字段：name；组内 AND）；目标50：邮箱正确（字段：email；组内 AND）；目标51：名称正确（字段：name；组内 AND）；目标51：邮箱正确（字段：email；组内 AND）；目标52：名称正确（字段：name；组内 AND）；目标52：邮箱正确（字段：email；组内 AND）；目标53：名称正确（字段：name；组内 AND）；目标53：邮箱正确（字段：email；组内 AND）；目标54：名称正确（字段：name；组内 AND）；目标54：邮箱正确（字段：email；组内 AND）；目标55：名称正确（字段：name；组内 AND）；目标55：邮箱正确（字段：email；组内 AND）；目标56：名称正确（字段：name；组内 AND）；目标56：邮箱正确（字段：email；组内 AND）；目标57：名称正确（字段：name；组内 AND）；目标57：邮箱正确（字段：email；组内 AND）；目标58：名称正确（字段：name；组内 AND）；目标58：邮箱正确（字段：email；组内 AND）；目标59：名称正确（字段：name；组内 AND）；目标59：邮箱正确（字段：email；组内 AND）；目标60：名称正确（字段：name；组内 AND）；目标60：邮箱正确（字段：email；组内 AND）；目标61：名称正确（字段：name；组内 AND）；目标61：邮箱正确（字段：email；组内 AND）；目标62：名称正确（字段：name；组内 AND）；目标62：邮箱正确（字段：email；组内 AND）；目标63：名称正确（字段：name；组内 AND）；目标63：邮箱正确（字段：email；组内 AND）；目标64：名称正确（字段：name；组内 AND）；目标64：邮箱正确（字段：email；组内 AND）；目标65：名称正确（字段：name；组内 AND）；目标65：邮箱正确（字段：email；组内 AND）；目标66：名称正确（字段：name；组内 AND）；目标66：邮箱正确（字段：email；组内 AND）；目标67：名称正确（字段：name；组内 AND）；目标67：邮箱正确（字段：email；组内 AND）；目标68：名称正确（字段：name；组内 AND）；目标68：邮箱正确（字段：email；组内 AND）；目标69：名称正确（字段：name；组内 AND）；目标69：邮箱正确（字段：email；组内 AND）；目标70：名称正确（字段：name；组内 AND）；目标70：邮箱正确（字段：email；组内 AND）

## 题目 77（7cf15a94c97d28cbe0f7）

**题面：** Create a new customer group named "VIP Customers" with Retail Customer tax class.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:create`；new_matching_record_saved: 原选择条件匹配且本次新增的记录恰好一条。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; existing_records_unchanged: 原有实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; existing_records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 3 计分：实际新增并保存一个本任务可唯一绑定的有效对象（字段：；组内 AND）；名称正确（字段：name；组内 AND）；税类正确（字段：tax_label；组内 AND）

## 题目 78（7d0076c89c2e731e77c8）

**题面：** For this local training variant, override the default USD currency symbol with US$ and save Currency Symbols.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:update`；persisted_requested_value: 原选中对象已持久保存，并整体满足 update_matches 的请求条件。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; other_records_unchanged: 原目标以外的同实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; other_records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 2 计分：默认作用域明确持久覆盖USD符号（字段：；组内 AND）；同一作用域USD最终有效符号为US$（字段：；组内 AND）

## 题目 79（7edbc4e6cbc6ddcc50cf）

**题面：** Find out what transportation modes are available for directions on OpenStreetMap.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_options: 提交的 options 满足原 record_set 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 3 计分：每个正确、不重复的要求列表成员（字段：label；组内 AND）

## 题目 80（8502336fbff28609722e）

**题面：** View the shipping details for order #000000001.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:query`；path: /anvme/workspace/r102bf10-lab-generate-skill/experiments/train-partial-reward-20261117-v1/trace-review-v1/answer-completion-review.json; sha256: 8bce509b9b45b9e06b7bef0a47fb080d5715c3ca326a65313c447788501df5be

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 3 计分：answer_shipping_firstname + answer_shipping_lastname（字段：answer_shipping_firstname, answer_shipping_lastname；组内 AND）；answer_shipping_street（字段：answer_shipping_street；组内 AND）；answer_shipping_city + answer_shipping_region + answer_shipping_postcode + answer_shipping_country_id（字段：answer_shipping_city, answer_shipping_region, answer_shipping_postcode, answer_shipping_country_id；组内 AND）

## 题目 81（85dadbc00c3440ad28a7）

**题面：** Create and save a new customer named Training Customer with email admin-85dadbc00c3440ad28a7@example.test. Keep valid defaults for unspecified optional fields.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:create`；new_matching_record_saved: 原选择条件匹配且本次新增的记录恰好一条。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; existing_records_unchanged: 原有实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; existing_records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 3 计分：实际新增并保存一个本任务可唯一绑定的有效对象（字段：；组内 AND）；完整姓名正确（字段：firstname, lastname；组内 AND）；邮箱正确（字段：email；组内 AND）

## 题目 82（87efc09382467a521c3b）

**题面：** Export the credit memo data as an Excel XML file.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:export`；downloaded_matching_csv: 至少一个实际下载产物通过原内容及选中对象集合比较。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 20 计分：退款单编号（字段：；组内 AND）；退款单创建日期（字段：；组内 AND）；关联订单编号（字段：；组内 AND）；订单创建日期（字段：；组内 AND）；账单姓名及完整账单地址（字段：；组内 AND）；退款单状态（字段：；组内 AND）；基础币种退款金额（字段：；组内 AND）；订单状态（字段：；组内 AND）；购买商店/站点（字段：；组内 AND）；完整收货地址（字段：；组内 AND）；客户完整姓名（字段：；组内 AND）；客户邮箱（字段：；组内 AND）；客户分组（字段：；组内 AND）；支付方式（字段：；组内 AND）；配送方式信息（字段：；组内 AND）；退款小计（字段：；组内 AND）；配送及手续费（字段：；组内 AND）；退款调整金额（字段：；组内 AND）；调整费用（字段：；组内 AND）；基础币种订单总额（字段：；组内 AND）

## 题目 83（8a587b258e1b2f7912a3）

**题面：** List all projects visible on the GitLab Explore page.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_projects: 提交的 projects 满足原 record_set 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 20 计分：每个正确、不重复的要求列表成员（字段：path；组内 AND）

## 题目 84（8a9442c36c0705cc4857）

**题面：** Generate a short link for sharing the current map location

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_short_link: 提交的 short_link 满足原 local_url 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 2 计分：短链接所编码的完整地图中心，经纬度同时正确（字段：；组内 AND）；同一短链接编码的缩放级别（字段：；组内 AND）

## 题目 85（8f5196ffd60a7f7dee3c）

**题面：** Verify if the order total of $365.42 is calculated correctly from the subtotal and shipping costs

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；path: /anvme/workspace/r102bf10-lab-generate-skill/experiments/train-partial-reward-20261117-v1/trace-review-v1/answer-completion-review.json; sha256: 8bce509b9b45b9e06b7bef0a47fb080d5715c3ca326a65313c447788501df5be

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 3 计分：answer_subtotal（字段：answer_subtotal；组内 AND）；answer_shipping_cost（字段：answer_shipping_cost；组内 AND）；answer_order_total + answer_total_correct（字段：answer_order_total, answer_total_correct；组内 AND）

## 题目 86（90171eca733558b91be8）

**题面：** For this local training variant, select order #000000002 and download its invoice PDF.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:pdf`；downloaded_correct_documents: 至少一个实际下载产物通过原内容及选中对象集合比较。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 5 计分：订单日期（字段：；组内 AND）；账单和收货对象及完整地址（字段：；组内 AND）；支付方式、配送方式及运费（字段：；组内 AND）；商品名称、SKU、数量及规格（字段：；组内 AND）；小计、税费、运费与总计（字段：；组内 AND）

## 题目 87（92aee5530a26d63ee39e）

**题面：** Find sports equipment under $100 on the Sports & Outdoors page.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_products: 提交的 products 满足原 record_subset 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 2 计分：指出一个确实低于阈值的商品（字段：products, name；组内 AND）；该商品价格正确（字段：products, price；组内 AND）

## 题目 88（95ee0e2712ebe1df0764）

**题面：** Generate a list of customers who have confirmed their email address

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:collection_query`；exact_result_set: 按原字段比较完整多重集合，包含数量、重复、遗漏和多余记录约束。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 140 计分：目标1：完整姓名正确（字段：firstname, lastname；组内 AND）；目标1：邮箱正确（字段：email；组内 AND）；目标2：完整姓名正确（字段：firstname, lastname；组内 AND）；目标2：邮箱正确（字段：email；组内 AND）；目标3：完整姓名正确（字段：firstname, lastname；组内 AND）；目标3：邮箱正确（字段：email；组内 AND）；目标4：完整姓名正确（字段：firstname, lastname；组内 AND）；目标4：邮箱正确（字段：email；组内 AND）；目标5：完整姓名正确（字段：firstname, lastname；组内 AND）；目标5：邮箱正确（字段：email；组内 AND）；目标6：完整姓名正确（字段：firstname, lastname；组内 AND）；目标6：邮箱正确（字段：email；组内 AND）；目标7：完整姓名正确（字段：firstname, lastname；组内 AND）；目标7：邮箱正确（字段：email；组内 AND）；目标8：完整姓名正确（字段：firstname, lastname；组内 AND）；目标8：邮箱正确（字段：email；组内 AND）；目标9：完整姓名正确（字段：firstname, lastname；组内 AND）；目标9：邮箱正确（字段：email；组内 AND）；目标10：完整姓名正确（字段：firstname, lastname；组内 AND）；目标10：邮箱正确（字段：email；组内 AND）；目标11：完整姓名正确（字段：firstname, lastname；组内 AND）；目标11：邮箱正确（字段：email；组内 AND）；目标12：完整姓名正确（字段：firstname, lastname；组内 AND）；目标12：邮箱正确（字段：email；组内 AND）；目标13：完整姓名正确（字段：firstname, lastname；组内 AND）；目标13：邮箱正确（字段：email；组内 AND）；目标14：完整姓名正确（字段：firstname, lastname；组内 AND）；目标14：邮箱正确（字段：email；组内 AND）；目标15：完整姓名正确（字段：firstname, lastname；组内 AND）；目标15：邮箱正确（字段：email；组内 AND）；目标16：完整姓名正确（字段：firstname, lastname；组内 AND）；目标16：邮箱正确（字段：email；组内 AND）；目标17：完整姓名正确（字段：firstname, lastname；组内 AND）；目标17：邮箱正确（字段：email；组内 AND）；目标18：完整姓名正确（字段：firstname, lastname；组内 AND）；目标18：邮箱正确（字段：email；组内 AND）；目标19：完整姓名正确（字段：firstname, lastname；组内 AND）；目标19：邮箱正确（字段：email；组内 AND）；目标20：完整姓名正确（字段：firstname, lastname；组内 AND）；目标20：邮箱正确（字段：email；组内 AND）；目标21：完整姓名正确（字段：firstname, lastname；组内 AND）；目标21：邮箱正确（字段：email；组内 AND）；目标22：完整姓名正确（字段：firstname, lastname；组内 AND）；目标22：邮箱正确（字段：email；组内 AND）；目标23：完整姓名正确（字段：firstname, lastname；组内 AND）；目标23：邮箱正确（字段：email；组内 AND）；目标24：完整姓名正确（字段：firstname, lastname；组内 AND）；目标24：邮箱正确（字段：email；组内 AND）；目标25：完整姓名正确（字段：firstname, lastname；组内 AND）；目标25：邮箱正确（字段：email；组内 AND）；目标26：完整姓名正确（字段：firstname, lastname；组内 AND）；目标26：邮箱正确（字段：email；组内 AND）；目标27：完整姓名正确（字段：firstname, lastname；组内 AND）；目标27：邮箱正确（字段：email；组内 AND）；目标28：完整姓名正确（字段：firstname, lastname；组内 AND）；目标28：邮箱正确（字段：email；组内 AND）；目标29：完整姓名正确（字段：firstname, lastname；组内 AND）；目标29：邮箱正确（字段：email；组内 AND）；目标30：完整姓名正确（字段：firstname, lastname；组内 AND）；目标30：邮箱正确（字段：email；组内 AND）；目标31：完整姓名正确（字段：firstname, lastname；组内 AND）；目标31：邮箱正确（字段：email；组内 AND）；目标32：完整姓名正确（字段：firstname, lastname；组内 AND）；目标32：邮箱正确（字段：email；组内 AND）；目标33：完整姓名正确（字段：firstname, lastname；组内 AND）；目标33：邮箱正确（字段：email；组内 AND）；目标34：完整姓名正确（字段：firstname, lastname；组内 AND）；目标34：邮箱正确（字段：email；组内 AND）；目标35：完整姓名正确（字段：firstname, lastname；组内 AND）；目标35：邮箱正确（字段：email；组内 AND）；目标36：完整姓名正确（字段：firstname, lastname；组内 AND）；目标36：邮箱正确（字段：email；组内 AND）；目标37：完整姓名正确（字段：firstname, lastname；组内 AND）；目标37：邮箱正确（字段：email；组内 AND）；目标38：完整姓名正确（字段：firstname, lastname；组内 AND）；目标38：邮箱正确（字段：email；组内 AND）；目标39：完整姓名正确（字段：firstname, lastname；组内 AND）；目标39：邮箱正确（字段：email；组内 AND）；目标40：完整姓名正确（字段：firstname, lastname；组内 AND）；目标40：邮箱正确（字段：email；组内 AND）；目标41：完整姓名正确（字段：firstname, lastname；组内 AND）；目标41：邮箱正确（字段：email；组内 AND）；目标42：完整姓名正确（字段：firstname, lastname；组内 AND）；目标42：邮箱正确（字段：email；组内 AND）；目标43：完整姓名正确（字段：firstname, lastname；组内 AND）；目标43：邮箱正确（字段：email；组内 AND）；目标44：完整姓名正确（字段：firstname, lastname；组内 AND）；目标44：邮箱正确（字段：email；组内 AND）；目标45：完整姓名正确（字段：firstname, lastname；组内 AND）；目标45：邮箱正确（字段：email；组内 AND）；目标46：完整姓名正确（字段：firstname, lastname；组内 AND）；目标46：邮箱正确（字段：email；组内 AND）；目标47：完整姓名正确（字段：firstname, lastname；组内 AND）；目标47：邮箱正确（字段：email；组内 AND）；目标48：完整姓名正确（字段：firstname, lastname；组内 AND）；目标48：邮箱正确（字段：email；组内 AND）；目标49：完整姓名正确（字段：firstname, lastname；组内 AND）；目标49：邮箱正确（字段：email；组内 AND）；目标50：完整姓名正确（字段：firstname, lastname；组内 AND）；目标50：邮箱正确（字段：email；组内 AND）；目标51：完整姓名正确（字段：firstname, lastname；组内 AND）；目标51：邮箱正确（字段：email；组内 AND）；目标52：完整姓名正确（字段：firstname, lastname；组内 AND）；目标52：邮箱正确（字段：email；组内 AND）；目标53：完整姓名正确（字段：firstname, lastname；组内 AND）；目标53：邮箱正确（字段：email；组内 AND）；目标54：完整姓名正确（字段：firstname, lastname；组内 AND）；目标54：邮箱正确（字段：email；组内 AND）；目标55：完整姓名正确（字段：firstname, lastname；组内 AND）；目标55：邮箱正确（字段：email；组内 AND）；目标56：完整姓名正确（字段：firstname, lastname；组内 AND）；目标56：邮箱正确（字段：email；组内 AND）；目标57：完整姓名正确（字段：firstname, lastname；组内 AND）；目标57：邮箱正确（字段：email；组内 AND）；目标58：完整姓名正确（字段：firstname, lastname；组内 AND）；目标58：邮箱正确（字段：email；组内 AND）；目标59：完整姓名正确（字段：firstname, lastname；组内 AND）；目标59：邮箱正确（字段：email；组内 AND）；目标60：完整姓名正确（字段：firstname, lastname；组内 AND）；目标60：邮箱正确（字段：email；组内 AND）；目标61：完整姓名正确（字段：firstname, lastname；组内 AND）；目标61：邮箱正确（字段：email；组内 AND）；目标62：完整姓名正确（字段：firstname, lastname；组内 AND）；目标62：邮箱正确（字段：email；组内 AND）；目标63：完整姓名正确（字段：firstname, lastname；组内 AND）；目标63：邮箱正确（字段：email；组内 AND）；目标64：完整姓名正确（字段：firstname, lastname；组内 AND）；目标64：邮箱正确（字段：email；组内 AND）；目标65：完整姓名正确（字段：firstname, lastname；组内 AND）；目标65：邮箱正确（字段：email；组内 AND）；目标66：完整姓名正确（字段：firstname, lastname；组内 AND）；目标66：邮箱正确（字段：email；组内 AND）；目标67：完整姓名正确（字段：firstname, lastname；组内 AND）；目标67：邮箱正确（字段：email；组内 AND）；目标68：完整姓名正确（字段：firstname, lastname；组内 AND）；目标68：邮箱正确（字段：email；组内 AND）；目标69：完整姓名正确（字段：firstname, lastname；组内 AND）；目标69：邮箱正确（字段：email；组内 AND）；目标70：完整姓名正确（字段：firstname, lastname；组内 AND）；目标70：邮箱正确（字段：email；组内 AND）

## 题目 89（967848101ec725a2e28f）

**题面：** Find the license type for the project Karl Kroening / ffmpeg-python.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_license_type: 提交的 license_type 满足原 string 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 2 计分：项目许可证家族Apache（字段：license_type；组内 AND）；同一项目许可证的完整版本2.0（字段：license_type；组内 AND）

## 题目 90（9ac8c191d8e0026c7a39）

**题面：** For this local training variant, reference date is September 30, 2026. Set Blue T-Shirt as new from September 30 through October 30, 2026 and save.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:update`；persisted_requested_value: 原选中对象已持久保存，并整体满足 update_matches 的请求条件。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; other_records_unchanged: 原目标以外的同实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; other_records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 2 计分：新品开始日期正确（字段：news_from_date；组内 AND）；新品结束日期正确（字段：news_to_date；组内 AND）

## 题目 91（9cc731fdb292beb61a5e）

**题面：** For this local training variant, create Training Customer with email training.customer@example.test on Main Website and send the welcome email from Default Store View. Email delivery is captured in the isolated local mailbox.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:create`；new_matching_record_saved: 原选择条件匹配且本次新增的记录恰好一条。; created_record_conditions: 该唯一新记录整体满足原 create_conditions。; welcome_delivered_locally: 隔离邮箱内新增发往原指定收件人、含原要求文字的邮件。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; existing_records_unchanged: 原有实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; existing_records_unchanged; new_matching_record_saved

**目前的评分准则：** 前提通过后，按固定分母 6 计分：实际新增并保存唯一可绑定的客户（字段：；组内 AND）；新客户完整姓名正确（字段：firstname, lastname；组内 AND）；新客户邮箱正确（字段：email；组内 AND）；请求的Main Website归属正确（字段：website_id；组内 AND）；实际发送的欢迎邮件收件人正确（字段：recipients；组内 AND）；同一封邮件的称呼及欢迎内容完整（字段：subject, body；组内 AND）

## 题目 92（9e5f8a4ab82a3ef3d219）

**题面：** Find all customers located in Texas

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:collection_query`；exact_result_set: 按原字段比较完整多重集合，包含数量、重复、遗漏和多余记录约束。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 24 计分：目标1：完整姓名正确（字段：firstname, lastname；组内 AND）；目标1：邮箱正确（字段：email；组内 AND）；目标2：完整姓名正确（字段：firstname, lastname；组内 AND）；目标2：邮箱正确（字段：email；组内 AND）；目标3：完整姓名正确（字段：firstname, lastname；组内 AND）；目标3：邮箱正确（字段：email；组内 AND）；目标4：完整姓名正确（字段：firstname, lastname；组内 AND）；目标4：邮箱正确（字段：email；组内 AND）；目标5：完整姓名正确（字段：firstname, lastname；组内 AND）；目标5：邮箱正确（字段：email；组内 AND）；目标6：完整姓名正确（字段：firstname, lastname；组内 AND）；目标6：邮箱正确（字段：email；组内 AND）；目标7：完整姓名正确（字段：firstname, lastname；组内 AND）；目标7：邮箱正确（字段：email；组内 AND）；目标8：完整姓名正确（字段：firstname, lastname；组内 AND）；目标8：邮箱正确（字段：email；组内 AND）；目标9：完整姓名正确（字段：firstname, lastname；组内 AND）；目标9：邮箱正确（字段：email；组内 AND）；目标10：完整姓名正确（字段：firstname, lastname；组内 AND）；目标10：邮箱正确（字段：email；组内 AND）；目标11：完整姓名正确（字段：firstname, lastname；组内 AND）；目标11：邮箱正确（字段：email；组内 AND）；目标12：完整姓名正确（字段：firstname, lastname；组内 AND）；目标12：邮箱正确（字段：email；组内 AND）

## 题目 93（9f1a9b9ca85961ed9cdc）

**题面：** View the email addresses of all customers

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:collection_query`；exact_result_set: 按原字段比较完整多重集合，包含数量、重复、遗漏和多余记录约束。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 70 计分：每个正确的目标记录/列表成员（字段：email；组内 AND）

## 题目 94（9f2e3f4d60b9e2df2df2）

**题面：** Identify all customers from the United States with phone numbers in the 212 area code

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:collection_query`；exact_result_set: 按原字段比较完整多重集合，包含数量、重复、遗漏和多余记录约束。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 10 计分：目标1：完整姓名正确（字段：firstname, lastname；组内 AND）；目标1：邮箱正确（字段：email；组内 AND）；目标2：完整姓名正确（字段：firstname, lastname；组内 AND）；目标2：邮箱正确（字段：email；组内 AND）；目标3：完整姓名正确（字段：firstname, lastname；组内 AND）；目标3：邮箱正确（字段：email；组内 AND）；目标4：完整姓名正确（字段：firstname, lastname；组内 AND）；目标4：邮箱正确（字段：email；组内 AND）；目标5：完整姓名正确（字段：firstname, lastname；组内 AND）；目标5：邮箱正确（字段：email；组内 AND）

## 题目 95（9f53f858718b01fac2eb）

**题面：** Provide details for the project yjlou / 2019-nCov including its description and number of stars.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；path: /anvme/workspace/r102bf10-lab-generate-skill/experiments/train-partial-reward-20261117-v1/trace-review-v1/answer-completion-review.json; sha256: 8bce509b9b45b9e06b7bef0a47fb080d5715c3ca326a65313c447788501df5be

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 3 计分：所使用的数据来源：Google Maps Timeline（字段：description；组内 AND）；与COVID-19患者历史位置比较的用途（字段：description；组内 AND）；项目星数（字段：star_count；组内 AND）

## 题目 96（a03f13a35cdfa2855e7d）

**题面：** Export the list of shipments using the Export button.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:export`；downloaded_matching_csv: 至少一个实际下载产物通过原内容及选中对象集合比较。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 3 计分：产物中每条正确的要求记录（字段：increment_id；组内 AND）

## 题目 97（a15b1eb0903aef00a975）

**题面：** List the files present in the cloud-to-butt repository.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_items: 提交的 items 满足原 record_set 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 6 计分：每个正确、不重复的要求列表成员（字段：path；组内 AND）

## 题目 98（a1b510d8e8901e742f78）

**题面：** Check what alternative download sources are available for OpenStreetMap data.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_items: 提交的 items 满足原 record_set 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 8 计分：目标1：名称正确（字段：name；组内 AND）；目标1：描述正确（字段：description；组内 AND）；目标2：名称正确（字段：name；组内 AND）；目标2：描述正确（字段：description；组内 AND）；目标3：名称正确（字段：name；组内 AND）；目标3：描述正确（字段：description；组内 AND）；目标4：名称正确（字段：name；组内 AND）；目标4：描述正确（字段：description；组内 AND）

## 题目 99（a3b7eedd09ab8fbc3bae）

**题面：** Check the shipping address for order #000000002

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:query`；path: /anvme/workspace/r102bf10-lab-generate-skill/experiments/train-partial-reward-20261117-v1/trace-review-v1/answer-completion-review.json; sha256: 8bce509b9b45b9e06b7bef0a47fb080d5715c3ca326a65313c447788501df5be

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 3 计分：answer_shipping_firstname + answer_shipping_lastname（字段：answer_shipping_firstname, answer_shipping_lastname；组内 AND）；answer_shipping_street（字段：answer_shipping_street；组内 AND）；answer_shipping_city + answer_shipping_region + answer_shipping_postcode + answer_shipping_country_id（字段：answer_shipping_city, answer_shipping_region, answer_shipping_postcode, answer_shipping_country_id；组内 AND）

## 题目 100（a4bd8f38e37459668308）

**题面：** For this local training variant, create a custom URL rewrite in Default Store View: request path training-catalog-entry, target path catalog/category/view/id/2, redirect type Permanent (301). Save it.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:create`；new_matching_record_saved: 原选择条件匹配且本次新增的记录恰好一条。; created_record_conditions: 该唯一新记录整体满足原 create_conditions。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; existing_records_unchanged: 原有实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; existing_records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 4 计分：实际新增并保存一个本任务可唯一绑定的有效对象（字段：；组内 AND）；请求路径正确（字段：request_path；组内 AND）；目标路径正确（字段：target_path；组内 AND）；重定向类型正确（字段：redirect_type；组内 AND）

## 题目 101（a67ffb7494750efde4d3）

**题面：** Find all products that have "Hoodie" in the name

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:collection_query`；exact_result_set: 按原字段比较完整多重集合，包含数量、重复、遗漏和多余记录约束。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 396 计分：目标1：SKU正确（字段：sku；组内 AND）；目标1：名称正确（字段：name；组内 AND）；目标2：SKU正确（字段：sku；组内 AND）；目标2：名称正确（字段：name；组内 AND）；目标3：SKU正确（字段：sku；组内 AND）；目标3：名称正确（字段：name；组内 AND）；目标4：SKU正确（字段：sku；组内 AND）；目标4：名称正确（字段：name；组内 AND）；目标5：SKU正确（字段：sku；组内 AND）；目标5：名称正确（字段：name；组内 AND）；目标6：SKU正确（字段：sku；组内 AND）；目标6：名称正确（字段：name；组内 AND）；目标7：SKU正确（字段：sku；组内 AND）；目标7：名称正确（字段：name；组内 AND）；目标8：SKU正确（字段：sku；组内 AND）；目标8：名称正确（字段：name；组内 AND）；目标9：SKU正确（字段：sku；组内 AND）；目标9：名称正确（字段：name；组内 AND）；目标10：SKU正确（字段：sku；组内 AND）；目标10：名称正确（字段：name；组内 AND）；目标11：SKU正确（字段：sku；组内 AND）；目标11：名称正确（字段：name；组内 AND）；目标12：SKU正确（字段：sku；组内 AND）；目标12：名称正确（字段：name；组内 AND）；目标13：SKU正确（字段：sku；组内 AND）；目标13：名称正确（字段：name；组内 AND）；目标14：SKU正确（字段：sku；组内 AND）；目标14：名称正确（字段：name；组内 AND）；目标15：SKU正确（字段：sku；组内 AND）；目标15：名称正确（字段：name；组内 AND）；目标16：SKU正确（字段：sku；组内 AND）；目标16：名称正确（字段：name；组内 AND）；目标17：SKU正确（字段：sku；组内 AND）；目标17：名称正确（字段：name；组内 AND）；目标18：SKU正确（字段：sku；组内 AND）；目标18：名称正确（字段：name；组内 AND）；目标19：SKU正确（字段：sku；组内 AND）；目标19：名称正确（字段：name；组内 AND）；目标20：SKU正确（字段：sku；组内 AND）；目标20：名称正确（字段：name；组内 AND）；目标21：SKU正确（字段：sku；组内 AND）；目标21：名称正确（字段：name；组内 AND）；目标22：SKU正确（字段：sku；组内 AND）；目标22：名称正确（字段：name；组内 AND）；目标23：SKU正确（字段：sku；组内 AND）；目标23：名称正确（字段：name；组内 AND）；目标24：SKU正确（字段：sku；组内 AND）；目标24：名称正确（字段：name；组内 AND）；目标25：SKU正确（字段：sku；组内 AND）；目标25：名称正确（字段：name；组内 AND）；目标26：SKU正确（字段：sku；组内 AND）；目标26：名称正确（字段：name；组内 AND）；目标27：SKU正确（字段：sku；组内 AND）；目标27：名称正确（字段：name；组内 AND）；目标28：SKU正确（字段：sku；组内 AND）；目标28：名称正确（字段：name；组内 AND）；目标29：SKU正确（字段：sku；组内 AND）；目标29：名称正确（字段：name；组内 AND）；目标30：SKU正确（字段：sku；组内 AND）；目标30：名称正确（字段：name；组内 AND）；目标31：SKU正确（字段：sku；组内 AND）；目标31：名称正确（字段：name；组内 AND）；目标32：SKU正确（字段：sku；组内 AND）；目标32：名称正确（字段：name；组内 AND）；目标33：SKU正确（字段：sku；组内 AND）；目标33：名称正确（字段：name；组内 AND）；目标34：SKU正确（字段：sku；组内 AND）；目标34：名称正确（字段：name；组内 AND）；目标35：SKU正确（字段：sku；组内 AND）；目标35：名称正确（字段：name；组内 AND）；目标36：SKU正确（字段：sku；组内 AND）；目标36：名称正确（字段：name；组内 AND）；目标37：SKU正确（字段：sku；组内 AND）；目标37：名称正确（字段：name；组内 AND）；目标38：SKU正确（字段：sku；组内 AND）；目标38：名称正确（字段：name；组内 AND）；目标39：SKU正确（字段：sku；组内 AND）；目标39：名称正确（字段：name；组内 AND）；目标40：SKU正确（字段：sku；组内 AND）；目标40：名称正确（字段：name；组内 AND）；目标41：SKU正确（字段：sku；组内 AND）；目标41：名称正确（字段：name；组内 AND）；目标42：SKU正确（字段：sku；组内 AND）；目标42：名称正确（字段：name；组内 AND）；目标43：SKU正确（字段：sku；组内 AND）；目标43：名称正确（字段：name；组内 AND）；目标44：SKU正确（字段：sku；组内 AND）；目标44：名称正确（字段：name；组内 AND）；目标45：SKU正确（字段：sku；组内 AND）；目标45：名称正确（字段：name；组内 AND）；目标46：SKU正确（字段：sku；组内 AND）；目标46：名称正确（字段：name；组内 AND）；目标47：SKU正确（字段：sku；组内 AND）；目标47：名称正确（字段：name；组内 AND）；目标48：SKU正确（字段：sku；组内 AND）；目标48：名称正确（字段：name；组内 AND）；目标49：SKU正确（字段：sku；组内 AND）；目标49：名称正确（字段：name；组内 AND）；目标50：SKU正确（字段：sku；组内 AND）；目标50：名称正确（字段：name；组内 AND）；目标51：SKU正确（字段：sku；组内 AND）；目标51：名称正确（字段：name；组内 AND）；目标52：SKU正确（字段：sku；组内 AND）；目标52：名称正确（字段：name；组内 AND）；目标53：SKU正确（字段：sku；组内 AND）；目标53：名称正确（字段：name；组内 AND）；目标54：SKU正确（字段：sku；组内 AND）；目标54：名称正确（字段：name；组内 AND）；目标55：SKU正确（字段：sku；组内 AND）；目标55：名称正确（字段：name；组内 AND）；目标56：SKU正确（字段：sku；组内 AND）；目标56：名称正确（字段：name；组内 AND）；目标57：SKU正确（字段：sku；组内 AND）；目标57：名称正确（字段：name；组内 AND）；目标58：SKU正确（字段：sku；组内 AND）；目标58：名称正确（字段：name；组内 AND）；目标59：SKU正确（字段：sku；组内 AND）；目标59：名称正确（字段：name；组内 AND）；目标60：SKU正确（字段：sku；组内 AND）；目标60：名称正确（字段：name；组内 AND）；目标61：SKU正确（字段：sku；组内 AND）；目标61：名称正确（字段：name；组内 AND）；目标62：SKU正确（字段：sku；组内 AND）；目标62：名称正确（字段：name；组内 AND）；目标63：SKU正确（字段：sku；组内 AND）；目标63：名称正确（字段：name；组内 AND）；目标64：SKU正确（字段：sku；组内 AND）；目标64：名称正确（字段：name；组内 AND）；目标65：SKU正确（字段：sku；组内 AND）；目标65：名称正确（字段：name；组内 AND）；目标66：SKU正确（字段：sku；组内 AND）；目标66：名称正确（字段：name；组内 AND）；目标67：SKU正确（字段：sku；组内 AND）；目标67：名称正确（字段：name；组内 AND）；目标68：SKU正确（字段：sku；组内 AND）；目标68：名称正确（字段：name；组内 AND）；目标69：SKU正确（字段：sku；组内 AND）；目标69：名称正确（字段：name；组内 AND）；目标70：SKU正确（字段：sku；组内 AND）；目标70：名称正确（字段：name；组内 AND）；目标71：SKU正确（字段：sku；组内 AND）；目标71：名称正确（字段：name；组内 AND）；目标72：SKU正确（字段：sku；组内 AND）；目标72：名称正确（字段：name；组内 AND）；目标73：SKU正确（字段：sku；组内 AND）；目标73：名称正确（字段：name；组内 AND）；目标74：SKU正确（字段：sku；组内 AND）；目标74：名称正确（字段：name；组内 AND）；目标75：SKU正确（字段：sku；组内 AND）；目标75：名称正确（字段：name；组内 AND）；目标76：SKU正确（字段：sku；组内 AND）；目标76：名称正确（字段：name；组内 AND）；目标77：SKU正确（字段：sku；组内 AND）；目标77：名称正确（字段：name；组内 AND）；目标78：SKU正确（字段：sku；组内 AND）；目标78：名称正确（字段：name；组内 AND）；目标79：SKU正确（字段：sku；组内 AND）；目标79：名称正确（字段：name；组内 AND）；目标80：SKU正确（字段：sku；组内 AND）；目标80：名称正确（字段：name；组内 AND）；目标81：SKU正确（字段：sku；组内 AND）；目标81：名称正确（字段：name；组内 AND）；目标82：SKU正确（字段：sku；组内 AND）；目标82：名称正确（字段：name；组内 AND）；目标83：SKU正确（字段：sku；组内 AND）；目标83：名称正确（字段：name；组内 AND）；目标84：SKU正确（字段：sku；组内 AND）；目标84：名称正确（字段：name；组内 AND）；目标85：SKU正确（字段：sku；组内 AND）；目标85：名称正确（字段：name；组内 AND）；目标86：SKU正确（字段：sku；组内 AND）；目标86：名称正确（字段：name；组内 AND）；目标87：SKU正确（字段：sku；组内 AND）；目标87：名称正确（字段：name；组内 AND）；目标88：SKU正确（字段：sku；组内 AND）；目标88：名称正确（字段：name；组内 AND）；目标89：SKU正确（字段：sku；组内 AND）；目标89：名称正确（字段：name；组内 AND）；目标90：SKU正确（字段：sku；组内 AND）；目标90：名称正确（字段：name；组内 AND）；目标91：SKU正确（字段：sku；组内 AND）；目标91：名称正确（字段：name；组内 AND）；目标92：SKU正确（字段：sku；组内 AND）；目标92：名称正确（字段：name；组内 AND）；目标93：SKU正确（字段：sku；组内 AND）；目标93：名称正确（字段：name；组内 AND）；目标94：SKU正确（字段：sku；组内 AND）；目标94：名称正确（字段：name；组内 AND）；目标95：SKU正确（字段：sku；组内 AND）；目标95：名称正确（字段：name；组内 AND）；目标96：SKU正确（字段：sku；组内 AND）；目标96：名称正确（字段：name；组内 AND）；目标97：SKU正确（字段：sku；组内 AND）；目标97：名称正确（字段：name；组内 AND）；目标98：SKU正确（字段：sku；组内 AND）；目标98：名称正确（字段：name；组内 AND）；目标99：SKU正确（字段：sku；组内 AND）；目标99：名称正确（字段：name；组内 AND）；目标100：SKU正确（字段：sku；组内 AND）；目标100：名称正确（字段：name；组内 AND）；目标101：SKU正确（字段：sku；组内 AND）；目标101：名称正确（字段：name；组内 AND）；目标102：SKU正确（字段：sku；组内 AND）；目标102：名称正确（字段：name；组内 AND）；目标103：SKU正确（字段：sku；组内 AND）；目标103：名称正确（字段：name；组内 AND）；目标104：SKU正确（字段：sku；组内 AND）；目标104：名称正确（字段：name；组内 AND）；目标105：SKU正确（字段：sku；组内 AND）；目标105：名称正确（字段：name；组内 AND）；目标106：SKU正确（字段：sku；组内 AND）；目标106：名称正确（字段：name；组内 AND）；目标107：SKU正确（字段：sku；组内 AND）；目标107：名称正确（字段：name；组内 AND）；目标108：SKU正确（字段：sku；组内 AND）；目标108：名称正确（字段：name；组内 AND）；目标109：SKU正确（字段：sku；组内 AND）；目标109：名称正确（字段：name；组内 AND）；目标110：SKU正确（字段：sku；组内 AND）；目标110：名称正确（字段：name；组内 AND）；目标111：SKU正确（字段：sku；组内 AND）；目标111：名称正确（字段：name；组内 AND）；目标112：SKU正确（字段：sku；组内 AND）；目标112：名称正确（字段：name；组内 AND）；目标113：SKU正确（字段：sku；组内 AND）；目标113：名称正确（字段：name；组内 AND）；目标114：SKU正确（字段：sku；组内 AND）；目标114：名称正确（字段：name；组内 AND）；目标115：SKU正确（字段：sku；组内 AND）；目标115：名称正确（字段：name；组内 AND）；目标116：SKU正确（字段：sku；组内 AND）；目标116：名称正确（字段：name；组内 AND）；目标117：SKU正确（字段：sku；组内 AND）；目标117：名称正确（字段：name；组内 AND）；目标118：SKU正确（字段：sku；组内 AND）；目标118：名称正确（字段：name；组内 AND）；目标119：SKU正确（字段：sku；组内 AND）；目标119：名称正确（字段：name；组内 AND）；目标120：SKU正确（字段：sku；组内 AND）；目标120：名称正确（字段：name；组内 AND）；目标121：SKU正确（字段：sku；组内 AND）；目标121：名称正确（字段：name；组内 AND）；目标122：SKU正确（字段：sku；组内 AND）；目标122：名称正确（字段：name；组内 AND）；目标123：SKU正确（字段：sku；组内 AND）；目标123：名称正确（字段：name；组内 AND）；目标124：SKU正确（字段：sku；组内 AND）；目标124：名称正确（字段：name；组内 AND）；目标125：SKU正确（字段：sku；组内 AND）；目标125：名称正确（字段：name；组内 AND）；目标126：SKU正确（字段：sku；组内 AND）；目标126：名称正确（字段：name；组内 AND）；目标127：SKU正确（字段：sku；组内 AND）；目标127：名称正确（字段：name；组内 AND）；目标128：SKU正确（字段：sku；组内 AND）；目标128：名称正确（字段：name；组内 AND）；目标129：SKU正确（字段：sku；组内 AND）；目标129：名称正确（字段：name；组内 AND）；目标130：SKU正确（字段：sku；组内 AND）；目标130：名称正确（字段：name；组内 AND）；目标131：SKU正确（字段：sku；组内 AND）；目标131：名称正确（字段：name；组内 AND）；目标132：SKU正确（字段：sku；组内 AND）；目标132：名称正确（字段：name；组内 AND）；目标133：SKU正确（字段：sku；组内 AND）；目标133：名称正确（字段：name；组内 AND）；目标134：SKU正确（字段：sku；组内 AND）；目标134：名称正确（字段：name；组内 AND）；目标135：SKU正确（字段：sku；组内 AND）；目标135：名称正确（字段：name；组内 AND）；目标136：SKU正确（字段：sku；组内 AND）；目标136：名称正确（字段：name；组内 AND）；目标137：SKU正确（字段：sku；组内 AND）；目标137：名称正确（字段：name；组内 AND）；目标138：SKU正确（字段：sku；组内 AND）；目标138：名称正确（字段：name；组内 AND）；目标139：SKU正确（字段：sku；组内 AND）；目标139：名称正确（字段：name；组内 AND）；目标140：SKU正确（字段：sku；组内 AND）；目标140：名称正确（字段：name；组内 AND）；目标141：SKU正确（字段：sku；组内 AND）；目标141：名称正确（字段：name；组内 AND）；目标142：SKU正确（字段：sku；组内 AND）；目标142：名称正确（字段：name；组内 AND）；目标143：SKU正确（字段：sku；组内 AND）；目标143：名称正确（字段：name；组内 AND）；目标144：SKU正确（字段：sku；组内 AND）；目标144：名称正确（字段：name；组内 AND）；目标145：SKU正确（字段：sku；组内 AND）；目标145：名称正确（字段：name；组内 AND）；目标146：SKU正确（字段：sku；组内 AND）；目标146：名称正确（字段：name；组内 AND）；目标147：SKU正确（字段：sku；组内 AND）；目标147：名称正确（字段：name；组内 AND）；目标148：SKU正确（字段：sku；组内 AND）；目标148：名称正确（字段：name；组内 AND）；目标149：SKU正确（字段：sku；组内 AND）；目标149：名称正确（字段：name；组内 AND）；目标150：SKU正确（字段：sku；组内 AND）；目标150：名称正确（字段：name；组内 AND）；目标151：SKU正确（字段：sku；组内 AND）；目标151：名称正确（字段：name；组内 AND）；目标152：SKU正确（字段：sku；组内 AND）；目标152：名称正确（字段：name；组内 AND）；目标153：SKU正确（字段：sku；组内 AND）；目标153：名称正确（字段：name；组内 AND）；目标154：SKU正确（字段：sku；组内 AND）；目标154：名称正确（字段：name；组内 AND）；目标155：SKU正确（字段：sku；组内 AND）；目标155：名称正确（字段：name；组内 AND）；目标156：SKU正确（字段：sku；组内 AND）；目标156：名称正确（字段：name；组内 AND）；目标157：SKU正确（字段：sku；组内 AND）；目标157：名称正确（字段：name；组内 AND）；目标158：SKU正确（字段：sku；组内 AND）；目标158：名称正确（字段：name；组内 AND）；目标159：SKU正确（字段：sku；组内 AND）；目标159：名称正确（字段：name；组内 AND）；目标160：SKU正确（字段：sku；组内 AND）；目标160：名称正确（字段：name；组内 AND）；目标161：SKU正确（字段：sku；组内 AND）；目标161：名称正确（字段：name；组内 AND）；目标162：SKU正确（字段：sku；组内 AND）；目标162：名称正确（字段：name；组内 AND）；目标163：SKU正确（字段：sku；组内 AND）；目标163：名称正确（字段：name；组内 AND）；目标164：SKU正确（字段：sku；组内 AND）；目标164：名称正确（字段：name；组内 AND）；目标165：SKU正确（字段：sku；组内 AND）；目标165：名称正确（字段：name；组内 AND）；目标166：SKU正确（字段：sku；组内 AND）；目标166：名称正确（字段：name；组内 AND）；目标167：SKU正确（字段：sku；组内 AND）；目标167：名称正确（字段：name；组内 AND）；目标168：SKU正确（字段：sku；组内 AND）；目标168：名称正确（字段：name；组内 AND）；目标169：SKU正确（字段：sku；组内 AND）；目标169：名称正确（字段：name；组内 AND）；目标170：SKU正确（字段：sku；组内 AND）；目标170：名称正确（字段：name；组内 AND）；目标171：SKU正确（字段：sku；组内 AND）；目标171：名称正确（字段：name；组内 AND）；目标172：SKU正确（字段：sku；组内 AND）；目标172：名称正确（字段：name；组内 AND）；目标173：SKU正确（字段：sku；组内 AND）；目标173：名称正确（字段：name；组内 AND）；目标174：SKU正确（字段：sku；组内 AND）；目标174：名称正确（字段：name；组内 AND）；目标175：SKU正确（字段：sku；组内 AND）；目标175：名称正确（字段：name；组内 AND）；目标176：SKU正确（字段：sku；组内 AND）；目标176：名称正确（字段：name；组内 AND）；目标177：SKU正确（字段：sku；组内 AND）；目标177：名称正确（字段：name；组内 AND）；目标178：SKU正确（字段：sku；组内 AND）；目标178：名称正确（字段：name；组内 AND）；目标179：SKU正确（字段：sku；组内 AND）；目标179：名称正确（字段：name；组内 AND）；目标180：SKU正确（字段：sku；组内 AND）；目标180：名称正确（字段：name；组内 AND）；目标181：SKU正确（字段：sku；组内 AND）；目标181：名称正确（字段：name；组内 AND）；目标182：SKU正确（字段：sku；组内 AND）；目标182：名称正确（字段：name；组内 AND）；目标183：SKU正确（字段：sku；组内 AND）；目标183：名称正确（字段：name；组内 AND）；目标184：SKU正确（字段：sku；组内 AND）；目标184：名称正确（字段：name；组内 AND）；目标185：SKU正确（字段：sku；组内 AND）；目标185：名称正确（字段：name；组内 AND）；目标186：SKU正确（字段：sku；组内 AND）；目标186：名称正确（字段：name；组内 AND）；目标187：SKU正确（字段：sku；组内 AND）；目标187：名称正确（字段：name；组内 AND）；目标188：SKU正确（字段：sku；组内 AND）；目标188：名称正确（字段：name；组内 AND）；目标189：SKU正确（字段：sku；组内 AND）；目标189：名称正确（字段：name；组内 AND）；目标190：SKU正确（字段：sku；组内 AND）；目标190：名称正确（字段：name；组内 AND）；目标191：SKU正确（字段：sku；组内 AND）；目标191：名称正确（字段：name；组内 AND）；目标192：SKU正确（字段：sku；组内 AND）；目标192：名称正确（字段：name；组内 AND）；目标193：SKU正确（字段：sku；组内 AND）；目标193：名称正确（字段：name；组内 AND）；目标194：SKU正确（字段：sku；组内 AND）；目标194：名称正确（字段：name；组内 AND）；目标195：SKU正确（字段：sku；组内 AND）；目标195：名称正确（字段：name；组内 AND）；目标196：SKU正确（字段：sku；组内 AND）；目标196：名称正确（字段：name；组内 AND）；目标197：SKU正确（字段：sku；组内 AND）；目标197：名称正确（字段：name；组内 AND）；目标198：SKU正确（字段：sku；组内 AND）；目标198：名称正确（字段：name；组内 AND）

## 题目 102（a68151f38ec0ea3dd185）

**题面：** View all projects with the MIT license. Consider all non-archived projects accessible to the current account, across the complete project directory.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_projects: 提交的 projects 满足原 record_set 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 52 计分：每个正确、不重复的要求列表成员（字段：path；组内 AND）

## 题目 103（a7e1ea92dd0e6d344bfe）

**题面：** Compare the estimated travel times between driving and cycling from New York City to Boston

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；path: /anvme/workspace/r102bf10-lab-generate-skill/experiments/train-partial-reward-20261117-v1/trace-review-v1/answer-completion-review.json; sha256: 8bce509b9b45b9e06b7bef0a47fb080d5715c3ca326a65313c447788501df5be

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 2 计分：answer_car_duration_minutes（字段：answer_car_duration_minutes；组内 AND）；answer_bicycle_duration_minutes（字段：answer_bicycle_duration_minutes；组内 AND）

## 题目 104（a98e4da9e07e8b372c7d）

**题面：** Provide details about the Pre-baked Gingerbread House Kit Value Pack.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；path: /anvme/workspace/r102bf10-lab-generate-skill/experiments/train-partial-reward-20261117-v1/trace-review-v1/answer-completion-review.json; sha256: 8bce509b9b45b9e06b7bef0a47fb080d5715c3ca326a65313c447788501df5be

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 3 计分：answer_sku（字段：answer_sku；组内 AND）；answer_price（字段：answer_price；组内 AND）；answer_manufacturer（字段：answer_manufacturer；组内 AND）

## 题目 105（aa3f32f9b51bb452536c）

**题面：** List all items in the shopping cart with their quantities and prices.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_items: 提交的 items 满足原 record_set 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 3 计分：所有应有商品完整且无多余项（字段：name；组内 AND）；各商品对应数量全部正确（字段：quantity；组内 AND）；各商品对应单价全部正确（字段：unit_price；组内 AND）

## 题目 106（afacd2e2ed0b749f7af1）

**题面：** For this local training variant, create and save a subcategory named Training Subcategory directly under New Category Name.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:create`；new_matching_record_saved: 原选择条件匹配且本次新增的记录恰好一条。; created_record_conditions: 该唯一新记录整体满足原 create_conditions。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; existing_records_unchanged: 原有实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; existing_records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 3 计分：实际新增并保存一个本任务可唯一绑定的有效对象（字段：；组内 AND）；名称正确（字段：name；组内 AND）；父分类归属正确（字段：parent_name；组内 AND）

## 题目 107（b0583d36f1dda1d88ac8）

**题面：** Find projects that use the MIT license. Consider all non-archived projects accessible to the current account, across the complete project directory.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_projects: 提交的 projects 满足原 record_set 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 52 计分：每个正确、不重复的要求列表成员（字段：path；组内 AND）

## 题目 108（b22941cc28e820b8bc0c）

**题面：** Create and save a new customer named Training Customer with email admin-b22941cc28e820b8bc0c@example.test and taxvat TRAINING-VAT-101. Keep valid defaults for unspecified optional fields.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:create`；new_matching_record_saved: 原选择条件匹配且本次新增的记录恰好一条。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; existing_records_unchanged: 原有实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; existing_records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 4 计分：实际新增并保存一个本任务可唯一绑定的有效对象（字段：；组内 AND）；完整姓名正确（字段：firstname, lastname；组内 AND）；邮箱正确（字段：email；组内 AND）；税号正确（字段：taxvat；组内 AND）

## 题目 109（b3db05d3ef6a3075e584）

**题面：** Verify the selected shipping address for my current shopping cart. Do not place an order.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_shipping_address_lines: 提交的 shipping_address_lines 满足原 record_set 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 5 计分：每条原地址行的完整正文和行号对应正确（字段：line, text；组内 AND）

## 题目 110（b4f2a38f0daad2fcf5a6）

**题面：** Check the shipping address for shipment #000000001.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:query`；path: /anvme/workspace/r102bf10-lab-generate-skill/experiments/train-partial-reward-20261117-v1/trace-review-v1/answer-completion-review.json; sha256: 8bce509b9b45b9e06b7bef0a47fb080d5715c3ca326a65313c447788501df5be

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 3 计分：answer_shipping_firstname + answer_shipping_lastname（字段：answer_shipping_firstname, answer_shipping_lastname；组内 AND）；answer_shipping_street（字段：answer_shipping_street；组内 AND）；answer_shipping_city + answer_shipping_region + answer_shipping_postcode + answer_shipping_country_id（字段：answer_shipping_city, answer_shipping_region, answer_shipping_postcode, answer_shipping_country_id；组内 AND）

## 题目 111（b67dfdb5d15dbb4d199f）

**题面：** For this local training variant, create the newsletter template named "Training Holiday Promotion". Save subject "Training holiday offer" and body exactly "Training offer: ten percent off selected products from December 1 through December 7, 2026.". Use sender name Training Store and sender email store@example.test. Do not send or queue the newsletter.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:create`；new_matching_record_saved: 原选择条件匹配且本次新增的记录恰好一条。; created_record_conditions: 该唯一新记录整体满足原 create_conditions。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; existing_records_unchanged: 原有实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; existing_records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 6 计分：实际新增并保存一个本任务可唯一绑定的有效对象（字段：；组内 AND）；模板名称正确（字段：template_code；组内 AND）；主题正确（字段：template_subject；组内 AND）；正文正确（字段：template_text；组内 AND）；发件人名称正确（字段：template_sender_name；组内 AND）；发件人邮箱正确（字段：template_sender_email；组内 AND）

## 题目 112（b7cc5c99dd61d8e99c2c）

**题面：** Find out what types of personal information the website collects from users.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_items: 提交的 items 满足原 record_set 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 4 计分：每个正确、不重复的要求列表成员（字段：name；组内 AND）

## 题目 113（b827e4e29d1845d4c43a）

**题面：** Check what transportation options are available for getting directions in OpenStreetMap

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_options: 提交的 options 满足原 record_set 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 3 计分：每个正确、不重复的要求列表成员（字段：label；组内 AND）

## 题目 114（b82e145d0549d511622d）

**题面：** Create and save a new customer named Training Customer with email admin-b82e145d0549d511622d@example.test and customer group VIP Customers. Keep valid defaults for unspecified optional fields.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:create`；new_matching_record_saved: 原选择条件匹配且本次新增的记录恰好一条。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; existing_records_unchanged: 原有实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; existing_records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 4 计分：实际新增并保存一个本任务可唯一绑定的有效对象（字段：；组内 AND）；完整姓名正确（字段：firstname, lastname；组内 AND）；邮箱正确（字段：email；组内 AND）；客户组正确（字段：group_name；组内 AND）

## 题目 115（b8a621852314fabd2c90）

**题面：** List all customers with the ZIP code 75201.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:collection_query`；exact_result_set: 按原字段比较完整多重集合，包含数量、重复、遗漏和多余记录约束。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 12 计分：目标1：完整姓名正确（字段：firstname, lastname；组内 AND）；目标1：邮箱正确（字段：email；组内 AND）；目标2：完整姓名正确（字段：firstname, lastname；组内 AND）；目标2：邮箱正确（字段：email；组内 AND）；目标3：完整姓名正确（字段：firstname, lastname；组内 AND）；目标3：邮箱正确（字段：email；组内 AND）；目标4：完整姓名正确（字段：firstname, lastname；组内 AND）；目标4：邮箱正确（字段：email；组内 AND）；目标5：完整姓名正确（字段：firstname, lastname；组内 AND）；目标5：邮箱正确（字段：email；组内 AND）；目标6：完整姓名正确（字段：firstname, lastname；组内 AND）；目标6：邮箱正确（字段：email；组内 AND）

## 题目 116（b920ab04dc686ce6354f）

**题面：** View details about the refunded Minerva LumaTech™ V-Tee product

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:collection_query`；exact_result_set: 按原字段比较完整多重集合，包含数量、重复、遗漏和多余记录约束。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 3 计分：SKU正确（字段：sku；组内 AND）；数量正确（字段：qty；组内 AND）；价格正确（字段：price；组内 AND）

## 题目 117（b9915bc8913e7309cc99）

**题面：** Check what items are currently in your shopping cart.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_items: 提交的 items 满足原 record_set 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 3 计分：每个正确、不重复的要求列表成员（字段：name；组内 AND）

## 题目 118（ba7427f96bfdd45c6df3）

**题面：** View the contents of your shopping cart with 3 items

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_items: 提交的 items 满足原 record_set 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 3 计分：每个正确、不重复的要求列表成员（字段：name；组内 AND）

## 题目 119（bb087733414d726c2d50）

**题面：** For this local training variant, save Blue T-Shirt meta title as "Blue T-Shirt | Training Store" and meta description as "Browse the Blue T-Shirt in the Training Store catalog."

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:update`；persisted_requested_value: 原选中对象已持久保存，并整体满足 update_matches 的请求条件。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; other_records_unchanged: 原目标以外的同实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; other_records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 2 计分：元标题正确（字段：meta_title；组内 AND）；元描述正确（字段：meta_description；组内 AND）

## 题目 120（bb4c6fa4b51a5a33afce）

**题面：** See how many reviews the Wildgame Innovations Trail Camera has.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_products: 提交的 products 满足原 record_subset 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 2 计分：至少一个匹配相机型号的完整显示名称（字段：；组内 AND）；与该型号对应的评论数（字段：；组内 AND）

## 题目 121（bbdb63236829567f8199）

**题面：** Check which country and state Adam Garcia is from For this local training variant, the target account email is adam.garcia@gmail.com.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:query`；path: /anvme/workspace/r102bf10-lab-generate-skill/experiments/train-partial-reward-20261117-v1/trace-review-v1/answer-completion-review.json; sha256: 8bce509b9b45b9e06b7bef0a47fb080d5715c3ca326a65313c447788501df5be

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 2 计分：answer_country_id（字段：answer_country_id；组内 AND）；answer_region（字段：answer_region；组内 AND）

## 题目 122（bced6b870e718e5c4722）

**题面：** For this local restored-page task, read the Vertex description on the Magento Marketplace page and return its exact description text. Stay on the local page; external partner websites are outside the task.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:page_text_query`；correct_partner_description: 提交的描述与原指定伙伴的页面参考描述一致。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; correct_page: 终页路径为本题原要求路径。; records_unchanged: 原分支所比较的记录范围保持。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。; partner_still_available: 原指定伙伴的终页描述仍与初始参考相等。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; correct_page; records_unchanged; answer_schema; partner_still_available

**目前的评分准则：** 前提通过后，按固定分母 4 计分：税务技术解决方案业务（字段：description；组内 AND）；自1978年起的客户采用信息（字段：description；组内 AND）；Magento商户的软件与专家服务（字段：description；组内 AND）；计算至申报汇缴的功能范围（字段：description；组内 AND）

## 题目 123（be7cead538c9af903316）

**题面：** For this local training variant, save Maya Tunic meta title as "Maya Tunic | Training Store" and meta description as "Browse the Maya Tunic in the Training Store catalog.".

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:update`；persisted_requested_value: 原选中对象已持久保存，并整体满足 update_matches 的请求条件。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; other_records_unchanged: 原目标以外的同实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; other_records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 2 计分：元标题正确（字段：meta_title；组内 AND）；元描述正确（字段：meta_description；组内 AND）

## 题目 124（bf53b767cb6680af3e02）

**题面：** Find out what programming libraries are supported by the a11y-syntax-highlighting project.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_items: 提交的 items 满足原 record_set 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 2 计分：目标1：每个正确、不重复的要求列表成员（字段：name；组内 AND）；目标2：每个正确、不重复的要求列表成员（字段：name；组内 AND）

## 题目 125（bf7fb901e64a6b200e93）

**题面：** List the names of all immediate subdirectories in src on the main branch of The A11Y Project (a11yproject/a11yproject.com).

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_directories: 提交的 directories 满足原 record_set 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 13 计分：每个正确、不重复的要求列表成员（字段：name；组内 AND）

## 题目 126（bfb19f582147d0013e80）

**题面：** Find out what Markdown formatting options are available for creating wiki pages

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_items: 提交的 items 满足原 record_set 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 26 计分：目标1：要求的格式功能覆盖完整（字段：feature；组内 AND）；目标1：各功能对应语法正确（字段：syntax；组内 AND）；目标2：要求的格式功能覆盖完整（字段：feature；组内 AND）；目标2：各功能对应语法正确（字段：syntax；组内 AND）；目标3：要求的格式功能覆盖完整（字段：feature；组内 AND）；目标3：各功能对应语法正确（字段：syntax；组内 AND）；目标4：要求的格式功能覆盖完整（字段：feature；组内 AND）；目标4：各功能对应语法正确（字段：syntax；组内 AND）；目标5：要求的格式功能覆盖完整（字段：feature；组内 AND）；目标5：各功能对应语法正确（字段：syntax；组内 AND）；目标6：要求的格式功能覆盖完整（字段：feature；组内 AND）；目标6：各功能对应语法正确（字段：syntax；组内 AND）；目标7：要求的格式功能覆盖完整（字段：feature；组内 AND）；目标7：各功能对应语法正确（字段：syntax；组内 AND）；目标8：要求的格式功能覆盖完整（字段：feature；组内 AND）；目标8：各功能对应语法正确（字段：syntax；组内 AND）；目标9：要求的格式功能覆盖完整（字段：feature；组内 AND）；目标9：各功能对应语法正确（字段：syntax；组内 AND）；目标10：要求的格式功能覆盖完整（字段：feature；组内 AND）；目标10：各功能对应语法正确（字段：syntax；组内 AND）；目标11：要求的格式功能覆盖完整（字段：feature；组内 AND）；目标11：各功能对应语法正确（字段：syntax；组内 AND）；目标12：要求的格式功能覆盖完整（字段：feature；组内 AND）；目标12：各功能对应语法正确（字段：syntax；组内 AND）；目标13：要求的格式功能覆盖完整（字段：feature；组内 AND）；目标13：各功能对应语法正确（字段：syntax；组内 AND）

## 题目 127（c0bcd7963046f155b1aa）

**题面：** Create and save a new customer named Training Customer with email admin-c0bcd7963046f155b1aa@example.test and customer group VIP Customers, date of birth 1990-01-15, gender Male. Keep valid defaults for unspecified optional fields.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:create`；new_matching_record_saved: 原选择条件匹配且本次新增的记录恰好一条。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; existing_records_unchanged: 原有实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; existing_records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 6 计分：实际新增并保存一个本任务可唯一绑定的有效对象（字段：；组内 AND）；完整姓名正确（字段：firstname, lastname；组内 AND）；邮箱正确（字段：email；组内 AND）；客户组正确（字段：group_name；组内 AND）；出生日期正确（字段：dob；组内 AND）；性别正确（字段：gender；组内 AND）

## 题目 128（c2d9e62db8793636a7a2）

**题面：** Report all recorded search terms, including each term, its number of uses, and its number of search results.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:collection_query`；exact_result_set: 按原字段比较完整多重集合，包含数量、重复、遗漏和多余记录约束。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 3 计分：目标集合覆盖完整且搜索词正确（字段：query_text；组内 AND）；使用次数正确（字段：popularity；组内 AND）；结果数量正确（字段：num_results；组内 AND）

## 题目 129（c2fcbc0f3dd3445dd358）

**题面：** Report the five most recently placed orders, including order number, customer name, and grand total. Break timestamp ties by ascending internal order ID.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:collection_query`；exact_result_set: 按原字段比较完整多重集合，包含数量、重复、遗漏和多余记录约束。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 3 计分：目标集合覆盖完整且记录编号正确（字段：increment_id；组内 AND）；客户姓名正确（字段：customer_name；组内 AND）；总额正确（字段：grand_total；组内 AND）

## 题目 130（c4d2f4fa20e3debaf7da）

**题面：** Check which material types are available for the St Patricks Day T-Shirt

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_material_types: 提交的 material_types 满足原 record_set 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 8 计分：每个正确、不重复的要求列表成员（字段：name；组内 AND）

## 题目 131（cb1f6d37c80c1c966d0c）

**题面：** Retrieve the distance and estimated time for the route from 40.7830, -73.9650 to 40.7570, -73.9860.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；path: /anvme/workspace/r102bf10-lab-generate-skill/experiments/train-partial-reward-20261117-v1/trace-review-v1/answer-completion-review.json; sha256: 8bce509b9b45b9e06b7bef0a47fb080d5715c3ca326a65313c447788501df5be

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 2 计分：answer_distance_km（字段：answer_distance_km；组内 AND）；answer_duration_minutes（字段：answer_duration_minutes；组内 AND）

## 题目 132（cc2fff7007c02443f285）

**题面：** Create and save a simple product named Training Product cc2fff, SKU TRAIN-cc2fff7007c02443f285, price 9.99. Keep valid defaults for unspecified settings.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:create`；new_matching_record_saved: 原选择条件匹配且本次新增的记录恰好一条。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; existing_records_unchanged: 原有实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; existing_records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 4 计分：实际新增并保存一个本任务可唯一绑定的有效对象（字段：；组内 AND）；名称正确（字段：name；组内 AND）；SKU正确（字段：sku；组内 AND）；价格正确（字段：price；组内 AND）

## 题目 133（cc749c4fb809e8c6fb7f）

**题面：** View all projects with the Apache License 2.0. Consider all non-archived projects accessible to the current account, across the complete project directory.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_projects: 提交的 projects 满足原 record_set 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 13 计分：每个正确、不重复的要求列表成员（字段：path；组内 AND）

## 题目 134（ce00fc4dc07e7d61dd52）

**题面：** For this local training variant, enable Allow Gift Message for Blue T-Shirt, overriding the default setting, and save.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:update`；persisted_requested_value: 原选中对象已持久保存，并整体满足 update_matches 的请求条件。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; other_records_unchanged: 原目标以外的同实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; other_records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 2 计分：本商品明确持久覆盖默认礼品留言设置（字段：；组内 AND）；本商品最终有效的Allow Gift Message为启用（字段：；组内 AND）

## 题目 135（cef4af3fccbffcd9e2b5）

**题面：** Read and report the project description for zerosoul / chinese-colors.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_description: 提交的 description 满足原 string 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 2 计分：描述的具体主题：Chinese traditional color（字段：；组内 AND）；描述的用途与形式：cheatsheet online（字段：；组内 AND）

## 题目 136（d03c2b089580e79d83f0）

**题面：** List customers whose Account Created in field is Default Store View, including their names and email addresses.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:collection_query`；exact_result_set: 按原字段比较完整多重集合，包含数量、重复、遗漏和多余记录约束。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 140 计分：目标1：完整姓名正确（字段：firstname, lastname；组内 AND）；目标1：邮箱正确（字段：email；组内 AND）；目标2：完整姓名正确（字段：firstname, lastname；组内 AND）；目标2：邮箱正确（字段：email；组内 AND）；目标3：完整姓名正确（字段：firstname, lastname；组内 AND）；目标3：邮箱正确（字段：email；组内 AND）；目标4：完整姓名正确（字段：firstname, lastname；组内 AND）；目标4：邮箱正确（字段：email；组内 AND）；目标5：完整姓名正确（字段：firstname, lastname；组内 AND）；目标5：邮箱正确（字段：email；组内 AND）；目标6：完整姓名正确（字段：firstname, lastname；组内 AND）；目标6：邮箱正确（字段：email；组内 AND）；目标7：完整姓名正确（字段：firstname, lastname；组内 AND）；目标7：邮箱正确（字段：email；组内 AND）；目标8：完整姓名正确（字段：firstname, lastname；组内 AND）；目标8：邮箱正确（字段：email；组内 AND）；目标9：完整姓名正确（字段：firstname, lastname；组内 AND）；目标9：邮箱正确（字段：email；组内 AND）；目标10：完整姓名正确（字段：firstname, lastname；组内 AND）；目标10：邮箱正确（字段：email；组内 AND）；目标11：完整姓名正确（字段：firstname, lastname；组内 AND）；目标11：邮箱正确（字段：email；组内 AND）；目标12：完整姓名正确（字段：firstname, lastname；组内 AND）；目标12：邮箱正确（字段：email；组内 AND）；目标13：完整姓名正确（字段：firstname, lastname；组内 AND）；目标13：邮箱正确（字段：email；组内 AND）；目标14：完整姓名正确（字段：firstname, lastname；组内 AND）；目标14：邮箱正确（字段：email；组内 AND）；目标15：完整姓名正确（字段：firstname, lastname；组内 AND）；目标15：邮箱正确（字段：email；组内 AND）；目标16：完整姓名正确（字段：firstname, lastname；组内 AND）；目标16：邮箱正确（字段：email；组内 AND）；目标17：完整姓名正确（字段：firstname, lastname；组内 AND）；目标17：邮箱正确（字段：email；组内 AND）；目标18：完整姓名正确（字段：firstname, lastname；组内 AND）；目标18：邮箱正确（字段：email；组内 AND）；目标19：完整姓名正确（字段：firstname, lastname；组内 AND）；目标19：邮箱正确（字段：email；组内 AND）；目标20：完整姓名正确（字段：firstname, lastname；组内 AND）；目标20：邮箱正确（字段：email；组内 AND）；目标21：完整姓名正确（字段：firstname, lastname；组内 AND）；目标21：邮箱正确（字段：email；组内 AND）；目标22：完整姓名正确（字段：firstname, lastname；组内 AND）；目标22：邮箱正确（字段：email；组内 AND）；目标23：完整姓名正确（字段：firstname, lastname；组内 AND）；目标23：邮箱正确（字段：email；组内 AND）；目标24：完整姓名正确（字段：firstname, lastname；组内 AND）；目标24：邮箱正确（字段：email；组内 AND）；目标25：完整姓名正确（字段：firstname, lastname；组内 AND）；目标25：邮箱正确（字段：email；组内 AND）；目标26：完整姓名正确（字段：firstname, lastname；组内 AND）；目标26：邮箱正确（字段：email；组内 AND）；目标27：完整姓名正确（字段：firstname, lastname；组内 AND）；目标27：邮箱正确（字段：email；组内 AND）；目标28：完整姓名正确（字段：firstname, lastname；组内 AND）；目标28：邮箱正确（字段：email；组内 AND）；目标29：完整姓名正确（字段：firstname, lastname；组内 AND）；目标29：邮箱正确（字段：email；组内 AND）；目标30：完整姓名正确（字段：firstname, lastname；组内 AND）；目标30：邮箱正确（字段：email；组内 AND）；目标31：完整姓名正确（字段：firstname, lastname；组内 AND）；目标31：邮箱正确（字段：email；组内 AND）；目标32：完整姓名正确（字段：firstname, lastname；组内 AND）；目标32：邮箱正确（字段：email；组内 AND）；目标33：完整姓名正确（字段：firstname, lastname；组内 AND）；目标33：邮箱正确（字段：email；组内 AND）；目标34：完整姓名正确（字段：firstname, lastname；组内 AND）；目标34：邮箱正确（字段：email；组内 AND）；目标35：完整姓名正确（字段：firstname, lastname；组内 AND）；目标35：邮箱正确（字段：email；组内 AND）；目标36：完整姓名正确（字段：firstname, lastname；组内 AND）；目标36：邮箱正确（字段：email；组内 AND）；目标37：完整姓名正确（字段：firstname, lastname；组内 AND）；目标37：邮箱正确（字段：email；组内 AND）；目标38：完整姓名正确（字段：firstname, lastname；组内 AND）；目标38：邮箱正确（字段：email；组内 AND）；目标39：完整姓名正确（字段：firstname, lastname；组内 AND）；目标39：邮箱正确（字段：email；组内 AND）；目标40：完整姓名正确（字段：firstname, lastname；组内 AND）；目标40：邮箱正确（字段：email；组内 AND）；目标41：完整姓名正确（字段：firstname, lastname；组内 AND）；目标41：邮箱正确（字段：email；组内 AND）；目标42：完整姓名正确（字段：firstname, lastname；组内 AND）；目标42：邮箱正确（字段：email；组内 AND）；目标43：完整姓名正确（字段：firstname, lastname；组内 AND）；目标43：邮箱正确（字段：email；组内 AND）；目标44：完整姓名正确（字段：firstname, lastname；组内 AND）；目标44：邮箱正确（字段：email；组内 AND）；目标45：完整姓名正确（字段：firstname, lastname；组内 AND）；目标45：邮箱正确（字段：email；组内 AND）；目标46：完整姓名正确（字段：firstname, lastname；组内 AND）；目标46：邮箱正确（字段：email；组内 AND）；目标47：完整姓名正确（字段：firstname, lastname；组内 AND）；目标47：邮箱正确（字段：email；组内 AND）；目标48：完整姓名正确（字段：firstname, lastname；组内 AND）；目标48：邮箱正确（字段：email；组内 AND）；目标49：完整姓名正确（字段：firstname, lastname；组内 AND）；目标49：邮箱正确（字段：email；组内 AND）；目标50：完整姓名正确（字段：firstname, lastname；组内 AND）；目标50：邮箱正确（字段：email；组内 AND）；目标51：完整姓名正确（字段：firstname, lastname；组内 AND）；目标51：邮箱正确（字段：email；组内 AND）；目标52：完整姓名正确（字段：firstname, lastname；组内 AND）；目标52：邮箱正确（字段：email；组内 AND）；目标53：完整姓名正确（字段：firstname, lastname；组内 AND）；目标53：邮箱正确（字段：email；组内 AND）；目标54：完整姓名正确（字段：firstname, lastname；组内 AND）；目标54：邮箱正确（字段：email；组内 AND）；目标55：完整姓名正确（字段：firstname, lastname；组内 AND）；目标55：邮箱正确（字段：email；组内 AND）；目标56：完整姓名正确（字段：firstname, lastname；组内 AND）；目标56：邮箱正确（字段：email；组内 AND）；目标57：完整姓名正确（字段：firstname, lastname；组内 AND）；目标57：邮箱正确（字段：email；组内 AND）；目标58：完整姓名正确（字段：firstname, lastname；组内 AND）；目标58：邮箱正确（字段：email；组内 AND）；目标59：完整姓名正确（字段：firstname, lastname；组内 AND）；目标59：邮箱正确（字段：email；组内 AND）；目标60：完整姓名正确（字段：firstname, lastname；组内 AND）；目标60：邮箱正确（字段：email；组内 AND）；目标61：完整姓名正确（字段：firstname, lastname；组内 AND）；目标61：邮箱正确（字段：email；组内 AND）；目标62：完整姓名正确（字段：firstname, lastname；组内 AND）；目标62：邮箱正确（字段：email；组内 AND）；目标63：完整姓名正确（字段：firstname, lastname；组内 AND）；目标63：邮箱正确（字段：email；组内 AND）；目标64：完整姓名正确（字段：firstname, lastname；组内 AND）；目标64：邮箱正确（字段：email；组内 AND）；目标65：完整姓名正确（字段：firstname, lastname；组内 AND）；目标65：邮箱正确（字段：email；组内 AND）；目标66：完整姓名正确（字段：firstname, lastname；组内 AND）；目标66：邮箱正确（字段：email；组内 AND）；目标67：完整姓名正确（字段：firstname, lastname；组内 AND）；目标67：邮箱正确（字段：email；组内 AND）；目标68：完整姓名正确（字段：firstname, lastname；组内 AND）；目标68：邮箱正确（字段：email；组内 AND）；目标69：完整姓名正确（字段：firstname, lastname；组内 AND）；目标69：邮箱正确（字段：email；组内 AND）；目标70：完整姓名正确（字段：firstname, lastname；组内 AND）；目标70：邮箱正确（字段：email；组内 AND）

## 题目 137（d0b831ec16b5e174fbd5）

**题面：** Share the current map location using a geo URI.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_geo_uri: 提交的 geo_uri 满足原 string 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 2 计分：geo URI中的完整经纬度坐标对（字段：；组内 AND）；geo URI中的z缩放参数（字段：；组内 AND）

## 题目 138（d1463ce7357f4c066d3a）

**题面：** Add a new product named "Sony Headphones" with SKU "SH123" and a price of $199.99.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:create`；new_matching_record_saved: 原选择条件匹配且本次新增的记录恰好一条。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; existing_records_unchanged: 原有实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; existing_records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 4 计分：实际新增并保存一个本任务可唯一绑定的有效对象（字段：；组内 AND）；名称正确（字段：name；组内 AND）；SKU正确（字段：sku；组内 AND）；价格正确（字段：price；组内 AND）

## 题目 139（d3157acb785a0c07897a）

**题面：** Determine what fields are required when creating a new wiki page

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_items: 提交的 items 满足原 record_set 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 3 计分：每个正确、不重复的要求列表成员（字段：name；组内 AND）

## 题目 140（d3ff3426f3fdcea375d4）

**题面：** For this local training variant, create and save a subcategory named Training Organized Products directly under Default Category.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:create`；new_matching_record_saved: 原选择条件匹配且本次新增的记录恰好一条。; created_record_conditions: 该唯一新记录整体满足原 create_conditions。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; existing_records_unchanged: 原有实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; existing_records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 3 计分：实际新增并保存一个本任务可唯一绑定的有效对象（字段：；组内 AND）；名称正确（字段：name；组内 AND）；父分类归属正确（字段：parent_name；组内 AND）

## 题目 141（d4498e55f4e12af7500a）

**题面：** Export the order data as a CSV file.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:export`；downloaded_matching_csv: 至少一个实际下载产物通过原内容及选中对象集合比较。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 616 计分：目标1：记录编号正确（字段：increment_id；组内 AND）；目标1：总额正确（字段：grand_total；组内 AND）；目标2：记录编号正确（字段：increment_id；组内 AND）；目标2：总额正确（字段：grand_total；组内 AND）；目标3：记录编号正确（字段：increment_id；组内 AND）；目标3：总额正确（字段：grand_total；组内 AND）；目标4：记录编号正确（字段：increment_id；组内 AND）；目标4：总额正确（字段：grand_total；组内 AND）；目标5：记录编号正确（字段：increment_id；组内 AND）；目标5：总额正确（字段：grand_total；组内 AND）；目标6：记录编号正确（字段：increment_id；组内 AND）；目标6：总额正确（字段：grand_total；组内 AND）；目标7：记录编号正确（字段：increment_id；组内 AND）；目标7：总额正确（字段：grand_total；组内 AND）；目标8：记录编号正确（字段：increment_id；组内 AND）；目标8：总额正确（字段：grand_total；组内 AND）；目标9：记录编号正确（字段：increment_id；组内 AND）；目标9：总额正确（字段：grand_total；组内 AND）；目标10：记录编号正确（字段：increment_id；组内 AND）；目标10：总额正确（字段：grand_total；组内 AND）；目标11：记录编号正确（字段：increment_id；组内 AND）；目标11：总额正确（字段：grand_total；组内 AND）；目标12：记录编号正确（字段：increment_id；组内 AND）；目标12：总额正确（字段：grand_total；组内 AND）；目标13：记录编号正确（字段：increment_id；组内 AND）；目标13：总额正确（字段：grand_total；组内 AND）；目标14：记录编号正确（字段：increment_id；组内 AND）；目标14：总额正确（字段：grand_total；组内 AND）；目标15：记录编号正确（字段：increment_id；组内 AND）；目标15：总额正确（字段：grand_total；组内 AND）；目标16：记录编号正确（字段：increment_id；组内 AND）；目标16：总额正确（字段：grand_total；组内 AND）；目标17：记录编号正确（字段：increment_id；组内 AND）；目标17：总额正确（字段：grand_total；组内 AND）；目标18：记录编号正确（字段：increment_id；组内 AND）；目标18：总额正确（字段：grand_total；组内 AND）；目标19：记录编号正确（字段：increment_id；组内 AND）；目标19：总额正确（字段：grand_total；组内 AND）；目标20：记录编号正确（字段：increment_id；组内 AND）；目标20：总额正确（字段：grand_total；组内 AND）；目标21：记录编号正确（字段：increment_id；组内 AND）；目标21：总额正确（字段：grand_total；组内 AND）；目标22：记录编号正确（字段：increment_id；组内 AND）；目标22：总额正确（字段：grand_total；组内 AND）；目标23：记录编号正确（字段：increment_id；组内 AND）；目标23：总额正确（字段：grand_total；组内 AND）；目标24：记录编号正确（字段：increment_id；组内 AND）；目标24：总额正确（字段：grand_total；组内 AND）；目标25：记录编号正确（字段：increment_id；组内 AND）；目标25：总额正确（字段：grand_total；组内 AND）；目标26：记录编号正确（字段：increment_id；组内 AND）；目标26：总额正确（字段：grand_total；组内 AND）；目标27：记录编号正确（字段：increment_id；组内 AND）；目标27：总额正确（字段：grand_total；组内 AND）；目标28：记录编号正确（字段：increment_id；组内 AND）；目标28：总额正确（字段：grand_total；组内 AND）；目标29：记录编号正确（字段：increment_id；组内 AND）；目标29：总额正确（字段：grand_total；组内 AND）；目标30：记录编号正确（字段：increment_id；组内 AND）；目标30：总额正确（字段：grand_total；组内 AND）；目标31：记录编号正确（字段：increment_id；组内 AND）；目标31：总额正确（字段：grand_total；组内 AND）；目标32：记录编号正确（字段：increment_id；组内 AND）；目标32：总额正确（字段：grand_total；组内 AND）；目标33：记录编号正确（字段：increment_id；组内 AND）；目标33：总额正确（字段：grand_total；组内 AND）；目标34：记录编号正确（字段：increment_id；组内 AND）；目标34：总额正确（字段：grand_total；组内 AND）；目标35：记录编号正确（字段：increment_id；组内 AND）；目标35：总额正确（字段：grand_total；组内 AND）；目标36：记录编号正确（字段：increment_id；组内 AND）；目标36：总额正确（字段：grand_total；组内 AND）；目标37：记录编号正确（字段：increment_id；组内 AND）；目标37：总额正确（字段：grand_total；组内 AND）；目标38：记录编号正确（字段：increment_id；组内 AND）；目标38：总额正确（字段：grand_total；组内 AND）；目标39：记录编号正确（字段：increment_id；组内 AND）；目标39：总额正确（字段：grand_total；组内 AND）；目标40：记录编号正确（字段：increment_id；组内 AND）；目标40：总额正确（字段：grand_total；组内 AND）；目标41：记录编号正确（字段：increment_id；组内 AND）；目标41：总额正确（字段：grand_total；组内 AND）；目标42：记录编号正确（字段：increment_id；组内 AND）；目标42：总额正确（字段：grand_total；组内 AND）；目标43：记录编号正确（字段：increment_id；组内 AND）；目标43：总额正确（字段：grand_total；组内 AND）；目标44：记录编号正确（字段：increment_id；组内 AND）；目标44：总额正确（字段：grand_total；组内 AND）；目标45：记录编号正确（字段：increment_id；组内 AND）；目标45：总额正确（字段：grand_total；组内 AND）；目标46：记录编号正确（字段：increment_id；组内 AND）；目标46：总额正确（字段：grand_total；组内 AND）；目标47：记录编号正确（字段：increment_id；组内 AND）；目标47：总额正确（字段：grand_total；组内 AND）；目标48：记录编号正确（字段：increment_id；组内 AND）；目标48：总额正确（字段：grand_total；组内 AND）；目标49：记录编号正确（字段：increment_id；组内 AND）；目标49：总额正确（字段：grand_total；组内 AND）；目标50：记录编号正确（字段：increment_id；组内 AND）；目标50：总额正确（字段：grand_total；组内 AND）；目标51：记录编号正确（字段：increment_id；组内 AND）；目标51：总额正确（字段：grand_total；组内 AND）；目标52：记录编号正确（字段：increment_id；组内 AND）；目标52：总额正确（字段：grand_total；组内 AND）；目标53：记录编号正确（字段：increment_id；组内 AND）；目标53：总额正确（字段：grand_total；组内 AND）；目标54：记录编号正确（字段：increment_id；组内 AND）；目标54：总额正确（字段：grand_total；组内 AND）；目标55：记录编号正确（字段：increment_id；组内 AND）；目标55：总额正确（字段：grand_total；组内 AND）；目标56：记录编号正确（字段：increment_id；组内 AND）；目标56：总额正确（字段：grand_total；组内 AND）；目标57：记录编号正确（字段：increment_id；组内 AND）；目标57：总额正确（字段：grand_total；组内 AND）；目标58：记录编号正确（字段：increment_id；组内 AND）；目标58：总额正确（字段：grand_total；组内 AND）；目标59：记录编号正确（字段：increment_id；组内 AND）；目标59：总额正确（字段：grand_total；组内 AND）；目标60：记录编号正确（字段：increment_id；组内 AND）；目标60：总额正确（字段：grand_total；组内 AND）；目标61：记录编号正确（字段：increment_id；组内 AND）；目标61：总额正确（字段：grand_total；组内 AND）；目标62：记录编号正确（字段：increment_id；组内 AND）；目标62：总额正确（字段：grand_total；组内 AND）；目标63：记录编号正确（字段：increment_id；组内 AND）；目标63：总额正确（字段：grand_total；组内 AND）；目标64：记录编号正确（字段：increment_id；组内 AND）；目标64：总额正确（字段：grand_total；组内 AND）；目标65：记录编号正确（字段：increment_id；组内 AND）；目标65：总额正确（字段：grand_total；组内 AND）；目标66：记录编号正确（字段：increment_id；组内 AND）；目标66：总额正确（字段：grand_total；组内 AND）；目标67：记录编号正确（字段：increment_id；组内 AND）；目标67：总额正确（字段：grand_total；组内 AND）；目标68：记录编号正确（字段：increment_id；组内 AND）；目标68：总额正确（字段：grand_total；组内 AND）；目标69：记录编号正确（字段：increment_id；组内 AND）；目标69：总额正确（字段：grand_total；组内 AND）；目标70：记录编号正确（字段：increment_id；组内 AND）；目标70：总额正确（字段：grand_total；组内 AND）；目标71：记录编号正确（字段：increment_id；组内 AND）；目标71：总额正确（字段：grand_total；组内 AND）；目标72：记录编号正确（字段：increment_id；组内 AND）；目标72：总额正确（字段：grand_total；组内 AND）；目标73：记录编号正确（字段：increment_id；组内 AND）；目标73：总额正确（字段：grand_total；组内 AND）；目标74：记录编号正确（字段：increment_id；组内 AND）；目标74：总额正确（字段：grand_total；组内 AND）；目标75：记录编号正确（字段：increment_id；组内 AND）；目标75：总额正确（字段：grand_total；组内 AND）；目标76：记录编号正确（字段：increment_id；组内 AND）；目标76：总额正确（字段：grand_total；组内 AND）；目标77：记录编号正确（字段：increment_id；组内 AND）；目标77：总额正确（字段：grand_total；组内 AND）；目标78：记录编号正确（字段：increment_id；组内 AND）；目标78：总额正确（字段：grand_total；组内 AND）；目标79：记录编号正确（字段：increment_id；组内 AND）；目标79：总额正确（字段：grand_total；组内 AND）；目标80：记录编号正确（字段：increment_id；组内 AND）；目标80：总额正确（字段：grand_total；组内 AND）；目标81：记录编号正确（字段：increment_id；组内 AND）；目标81：总额正确（字段：grand_total；组内 AND）；目标82：记录编号正确（字段：increment_id；组内 AND）；目标82：总额正确（字段：grand_total；组内 AND）；目标83：记录编号正确（字段：increment_id；组内 AND）；目标83：总额正确（字段：grand_total；组内 AND）；目标84：记录编号正确（字段：increment_id；组内 AND）；目标84：总额正确（字段：grand_total；组内 AND）；目标85：记录编号正确（字段：increment_id；组内 AND）；目标85：总额正确（字段：grand_total；组内 AND）；目标86：记录编号正确（字段：increment_id；组内 AND）；目标86：总额正确（字段：grand_total；组内 AND）；目标87：记录编号正确（字段：increment_id；组内 AND）；目标87：总额正确（字段：grand_total；组内 AND）；目标88：记录编号正确（字段：increment_id；组内 AND）；目标88：总额正确（字段：grand_total；组内 AND）；目标89：记录编号正确（字段：increment_id；组内 AND）；目标89：总额正确（字段：grand_total；组内 AND）；目标90：记录编号正确（字段：increment_id；组内 AND）；目标90：总额正确（字段：grand_total；组内 AND）；目标91：记录编号正确（字段：increment_id；组内 AND）；目标91：总额正确（字段：grand_total；组内 AND）；目标92：记录编号正确（字段：increment_id；组内 AND）；目标92：总额正确（字段：grand_total；组内 AND）；目标93：记录编号正确（字段：increment_id；组内 AND）；目标93：总额正确（字段：grand_total；组内 AND）；目标94：记录编号正确（字段：increment_id；组内 AND）；目标94：总额正确（字段：grand_total；组内 AND）；目标95：记录编号正确（字段：increment_id；组内 AND）；目标95：总额正确（字段：grand_total；组内 AND）；目标96：记录编号正确（字段：increment_id；组内 AND）；目标96：总额正确（字段：grand_total；组内 AND）；目标97：记录编号正确（字段：increment_id；组内 AND）；目标97：总额正确（字段：grand_total；组内 AND）；目标98：记录编号正确（字段：increment_id；组内 AND）；目标98：总额正确（字段：grand_total；组内 AND）；目标99：记录编号正确（字段：increment_id；组内 AND）；目标99：总额正确（字段：grand_total；组内 AND）；目标100：记录编号正确（字段：increment_id；组内 AND）；目标100：总额正确（字段：grand_total；组内 AND）；目标101：记录编号正确（字段：increment_id；组内 AND）；目标101：总额正确（字段：grand_total；组内 AND）；目标102：记录编号正确（字段：increment_id；组内 AND）；目标102：总额正确（字段：grand_total；组内 AND）；目标103：记录编号正确（字段：increment_id；组内 AND）；目标103：总额正确（字段：grand_total；组内 AND）；目标104：记录编号正确（字段：increment_id；组内 AND）；目标104：总额正确（字段：grand_total；组内 AND）；目标105：记录编号正确（字段：increment_id；组内 AND）；目标105：总额正确（字段：grand_total；组内 AND）；目标106：记录编号正确（字段：increment_id；组内 AND）；目标106：总额正确（字段：grand_total；组内 AND）；目标107：记录编号正确（字段：increment_id；组内 AND）；目标107：总额正确（字段：grand_total；组内 AND）；目标108：记录编号正确（字段：increment_id；组内 AND）；目标108：总额正确（字段：grand_total；组内 AND）；目标109：记录编号正确（字段：increment_id；组内 AND）；目标109：总额正确（字段：grand_total；组内 AND）；目标110：记录编号正确（字段：increment_id；组内 AND）；目标110：总额正确（字段：grand_total；组内 AND）；目标111：记录编号正确（字段：increment_id；组内 AND）；目标111：总额正确（字段：grand_total；组内 AND）；目标112：记录编号正确（字段：increment_id；组内 AND）；目标112：总额正确（字段：grand_total；组内 AND）；目标113：记录编号正确（字段：increment_id；组内 AND）；目标113：总额正确（字段：grand_total；组内 AND）；目标114：记录编号正确（字段：increment_id；组内 AND）；目标114：总额正确（字段：grand_total；组内 AND）；目标115：记录编号正确（字段：increment_id；组内 AND）；目标115：总额正确（字段：grand_total；组内 AND）；目标116：记录编号正确（字段：increment_id；组内 AND）；目标116：总额正确（字段：grand_total；组内 AND）；目标117：记录编号正确（字段：increment_id；组内 AND）；目标117：总额正确（字段：grand_total；组内 AND）；目标118：记录编号正确（字段：increment_id；组内 AND）；目标118：总额正确（字段：grand_total；组内 AND）；目标119：记录编号正确（字段：increment_id；组内 AND）；目标119：总额正确（字段：grand_total；组内 AND）；目标120：记录编号正确（字段：increment_id；组内 AND）；目标120：总额正确（字段：grand_total；组内 AND）；目标121：记录编号正确（字段：increment_id；组内 AND）；目标121：总额正确（字段：grand_total；组内 AND）；目标122：记录编号正确（字段：increment_id；组内 AND）；目标122：总额正确（字段：grand_total；组内 AND）；目标123：记录编号正确（字段：increment_id；组内 AND）；目标123：总额正确（字段：grand_total；组内 AND）；目标124：记录编号正确（字段：increment_id；组内 AND）；目标124：总额正确（字段：grand_total；组内 AND）；目标125：记录编号正确（字段：increment_id；组内 AND）；目标125：总额正确（字段：grand_total；组内 AND）；目标126：记录编号正确（字段：increment_id；组内 AND）；目标126：总额正确（字段：grand_total；组内 AND）；目标127：记录编号正确（字段：increment_id；组内 AND）；目标127：总额正确（字段：grand_total；组内 AND）；目标128：记录编号正确（字段：increment_id；组内 AND）；目标128：总额正确（字段：grand_total；组内 AND）；目标129：记录编号正确（字段：increment_id；组内 AND）；目标129：总额正确（字段：grand_total；组内 AND）；目标130：记录编号正确（字段：increment_id；组内 AND）；目标130：总额正确（字段：grand_total；组内 AND）；目标131：记录编号正确（字段：increment_id；组内 AND）；目标131：总额正确（字段：grand_total；组内 AND）；目标132：记录编号正确（字段：increment_id；组内 AND）；目标132：总额正确（字段：grand_total；组内 AND）；目标133：记录编号正确（字段：increment_id；组内 AND）；目标133：总额正确（字段：grand_total；组内 AND）；目标134：记录编号正确（字段：increment_id；组内 AND）；目标134：总额正确（字段：grand_total；组内 AND）；目标135：记录编号正确（字段：increment_id；组内 AND）；目标135：总额正确（字段：grand_total；组内 AND）；目标136：记录编号正确（字段：increment_id；组内 AND）；目标136：总额正确（字段：grand_total；组内 AND）；目标137：记录编号正确（字段：increment_id；组内 AND）；目标137：总额正确（字段：grand_total；组内 AND）；目标138：记录编号正确（字段：increment_id；组内 AND）；目标138：总额正确（字段：grand_total；组内 AND）；目标139：记录编号正确（字段：increment_id；组内 AND）；目标139：总额正确（字段：grand_total；组内 AND）；目标140：记录编号正确（字段：increment_id；组内 AND）；目标140：总额正确（字段：grand_total；组内 AND）；目标141：记录编号正确（字段：increment_id；组内 AND）；目标141：总额正确（字段：grand_total；组内 AND）；目标142：记录编号正确（字段：increment_id；组内 AND）；目标142：总额正确（字段：grand_total；组内 AND）；目标143：记录编号正确（字段：increment_id；组内 AND）；目标143：总额正确（字段：grand_total；组内 AND）；目标144：记录编号正确（字段：increment_id；组内 AND）；目标144：总额正确（字段：grand_total；组内 AND）；目标145：记录编号正确（字段：increment_id；组内 AND）；目标145：总额正确（字段：grand_total；组内 AND）；目标146：记录编号正确（字段：increment_id；组内 AND）；目标146：总额正确（字段：grand_total；组内 AND）；目标147：记录编号正确（字段：increment_id；组内 AND）；目标147：总额正确（字段：grand_total；组内 AND）；目标148：记录编号正确（字段：increment_id；组内 AND）；目标148：总额正确（字段：grand_total；组内 AND）；目标149：记录编号正确（字段：increment_id；组内 AND）；目标149：总额正确（字段：grand_total；组内 AND）；目标150：记录编号正确（字段：increment_id；组内 AND）；目标150：总额正确（字段：grand_total；组内 AND）；目标151：记录编号正确（字段：increment_id；组内 AND）；目标151：总额正确（字段：grand_total；组内 AND）；目标152：记录编号正确（字段：increment_id；组内 AND）；目标152：总额正确（字段：grand_total；组内 AND）；目标153：记录编号正确（字段：increment_id；组内 AND）；目标153：总额正确（字段：grand_total；组内 AND）；目标154：记录编号正确（字段：increment_id；组内 AND）；目标154：总额正确（字段：grand_total；组内 AND）；目标155：记录编号正确（字段：increment_id；组内 AND）；目标155：总额正确（字段：grand_total；组内 AND）；目标156：记录编号正确（字段：increment_id；组内 AND）；目标156：总额正确（字段：grand_total；组内 AND）；目标157：记录编号正确（字段：increment_id；组内 AND）；目标157：总额正确（字段：grand_total；组内 AND）；目标158：记录编号正确（字段：increment_id；组内 AND）；目标158：总额正确（字段：grand_total；组内 AND）；目标159：记录编号正确（字段：increment_id；组内 AND）；目标159：总额正确（字段：grand_total；组内 AND）；目标160：记录编号正确（字段：increment_id；组内 AND）；目标160：总额正确（字段：grand_total；组内 AND）；目标161：记录编号正确（字段：increment_id；组内 AND）；目标161：总额正确（字段：grand_total；组内 AND）；目标162：记录编号正确（字段：increment_id；组内 AND）；目标162：总额正确（字段：grand_total；组内 AND）；目标163：记录编号正确（字段：increment_id；组内 AND）；目标163：总额正确（字段：grand_total；组内 AND）；目标164：记录编号正确（字段：increment_id；组内 AND）；目标164：总额正确（字段：grand_total；组内 AND）；目标165：记录编号正确（字段：increment_id；组内 AND）；目标165：总额正确（字段：grand_total；组内 AND）；目标166：记录编号正确（字段：increment_id；组内 AND）；目标166：总额正确（字段：grand_total；组内 AND）；目标167：记录编号正确（字段：increment_id；组内 AND）；目标167：总额正确（字段：grand_total；组内 AND）；目标168：记录编号正确（字段：increment_id；组内 AND）；目标168：总额正确（字段：grand_total；组内 AND）；目标169：记录编号正确（字段：increment_id；组内 AND）；目标169：总额正确（字段：grand_total；组内 AND）；目标170：记录编号正确（字段：increment_id；组内 AND）；目标170：总额正确（字段：grand_total；组内 AND）；目标171：记录编号正确（字段：increment_id；组内 AND）；目标171：总额正确（字段：grand_total；组内 AND）；目标172：记录编号正确（字段：increment_id；组内 AND）；目标172：总额正确（字段：grand_total；组内 AND）；目标173：记录编号正确（字段：increment_id；组内 AND）；目标173：总额正确（字段：grand_total；组内 AND）；目标174：记录编号正确（字段：increment_id；组内 AND）；目标174：总额正确（字段：grand_total；组内 AND）；目标175：记录编号正确（字段：increment_id；组内 AND）；目标175：总额正确（字段：grand_total；组内 AND）；目标176：记录编号正确（字段：increment_id；组内 AND）；目标176：总额正确（字段：grand_total；组内 AND）；目标177：记录编号正确（字段：increment_id；组内 AND）；目标177：总额正确（字段：grand_total；组内 AND）；目标178：记录编号正确（字段：increment_id；组内 AND）；目标178：总额正确（字段：grand_total；组内 AND）；目标179：记录编号正确（字段：increment_id；组内 AND）；目标179：总额正确（字段：grand_total；组内 AND）；目标180：记录编号正确（字段：increment_id；组内 AND）；目标180：总额正确（字段：grand_total；组内 AND）；目标181：记录编号正确（字段：increment_id；组内 AND）；目标181：总额正确（字段：grand_total；组内 AND）；目标182：记录编号正确（字段：increment_id；组内 AND）；目标182：总额正确（字段：grand_total；组内 AND）；目标183：记录编号正确（字段：increment_id；组内 AND）；目标183：总额正确（字段：grand_total；组内 AND）；目标184：记录编号正确（字段：increment_id；组内 AND）；目标184：总额正确（字段：grand_total；组内 AND）；目标185：记录编号正确（字段：increment_id；组内 AND）；目标185：总额正确（字段：grand_total；组内 AND）；目标186：记录编号正确（字段：increment_id；组内 AND）；目标186：总额正确（字段：grand_total；组内 AND）；目标187：记录编号正确（字段：increment_id；组内 AND）；目标187：总额正确（字段：grand_total；组内 AND）；目标188：记录编号正确（字段：increment_id；组内 AND）；目标188：总额正确（字段：grand_total；组内 AND）；目标189：记录编号正确（字段：increment_id；组内 AND）；目标189：总额正确（字段：grand_total；组内 AND）；目标190：记录编号正确（字段：increment_id；组内 AND）；目标190：总额正确（字段：grand_total；组内 AND）；目标191：记录编号正确（字段：increment_id；组内 AND）；目标191：总额正确（字段：grand_total；组内 AND）；目标192：记录编号正确（字段：increment_id；组内 AND）；目标192：总额正确（字段：grand_total；组内 AND）；目标193：记录编号正确（字段：increment_id；组内 AND）；目标193：总额正确（字段：grand_total；组内 AND）；目标194：记录编号正确（字段：increment_id；组内 AND）；目标194：总额正确（字段：grand_total；组内 AND）；目标195：记录编号正确（字段：increment_id；组内 AND）；目标195：总额正确（字段：grand_total；组内 AND）；目标196：记录编号正确（字段：increment_id；组内 AND）；目标196：总额正确（字段：grand_total；组内 AND）；目标197：记录编号正确（字段：increment_id；组内 AND）；目标197：总额正确（字段：grand_total；组内 AND）；目标198：记录编号正确（字段：increment_id；组内 AND）；目标198：总额正确（字段：grand_total；组内 AND）；目标199：记录编号正确（字段：increment_id；组内 AND）；目标199：总额正确（字段：grand_total；组内 AND）；目标200：记录编号正确（字段：increment_id；组内 AND）；目标200：总额正确（字段：grand_total；组内 AND）；目标201：记录编号正确（字段：increment_id；组内 AND）；目标201：总额正确（字段：grand_total；组内 AND）；目标202：记录编号正确（字段：increment_id；组内 AND）；目标202：总额正确（字段：grand_total；组内 AND）；目标203：记录编号正确（字段：increment_id；组内 AND）；目标203：总额正确（字段：grand_total；组内 AND）；目标204：记录编号正确（字段：increment_id；组内 AND）；目标204：总额正确（字段：grand_total；组内 AND）；目标205：记录编号正确（字段：increment_id；组内 AND）；目标205：总额正确（字段：grand_total；组内 AND）；目标206：记录编号正确（字段：increment_id；组内 AND）；目标206：总额正确（字段：grand_total；组内 AND）；目标207：记录编号正确（字段：increment_id；组内 AND）；目标207：总额正确（字段：grand_total；组内 AND）；目标208：记录编号正确（字段：increment_id；组内 AND）；目标208：总额正确（字段：grand_total；组内 AND）；目标209：记录编号正确（字段：increment_id；组内 AND）；目标209：总额正确（字段：grand_total；组内 AND）；目标210：记录编号正确（字段：increment_id；组内 AND）；目标210：总额正确（字段：grand_total；组内 AND）；目标211：记录编号正确（字段：increment_id；组内 AND）；目标211：总额正确（字段：grand_total；组内 AND）；目标212：记录编号正确（字段：increment_id；组内 AND）；目标212：总额正确（字段：grand_total；组内 AND）；目标213：记录编号正确（字段：increment_id；组内 AND）；目标213：总额正确（字段：grand_total；组内 AND）；目标214：记录编号正确（字段：increment_id；组内 AND）；目标214：总额正确（字段：grand_total；组内 AND）；目标215：记录编号正确（字段：increment_id；组内 AND）；目标215：总额正确（字段：grand_total；组内 AND）；目标216：记录编号正确（字段：increment_id；组内 AND）；目标216：总额正确（字段：grand_total；组内 AND）；目标217：记录编号正确（字段：increment_id；组内 AND）；目标217：总额正确（字段：grand_total；组内 AND）；目标218：记录编号正确（字段：increment_id；组内 AND）；目标218：总额正确（字段：grand_total；组内 AND）；目标219：记录编号正确（字段：increment_id；组内 AND）；目标219：总额正确（字段：grand_total；组内 AND）；目标220：记录编号正确（字段：increment_id；组内 AND）；目标220：总额正确（字段：grand_total；组内 AND）；目标221：记录编号正确（字段：increment_id；组内 AND）；目标221：总额正确（字段：grand_total；组内 AND）；目标222：记录编号正确（字段：increment_id；组内 AND）；目标222：总额正确（字段：grand_total；组内 AND）；目标223：记录编号正确（字段：increment_id；组内 AND）；目标223：总额正确（字段：grand_total；组内 AND）；目标224：记录编号正确（字段：increment_id；组内 AND）；目标224：总额正确（字段：grand_total；组内 AND）；目标225：记录编号正确（字段：increment_id；组内 AND）；目标225：总额正确（字段：grand_total；组内 AND）；目标226：记录编号正确（字段：increment_id；组内 AND）；目标226：总额正确（字段：grand_total；组内 AND）；目标227：记录编号正确（字段：increment_id；组内 AND）；目标227：总额正确（字段：grand_total；组内 AND）；目标228：记录编号正确（字段：increment_id；组内 AND）；目标228：总额正确（字段：grand_total；组内 AND）；目标229：记录编号正确（字段：increment_id；组内 AND）；目标229：总额正确（字段：grand_total；组内 AND）；目标230：记录编号正确（字段：increment_id；组内 AND）；目标230：总额正确（字段：grand_total；组内 AND）；目标231：记录编号正确（字段：increment_id；组内 AND）；目标231：总额正确（字段：grand_total；组内 AND）；目标232：记录编号正确（字段：increment_id；组内 AND）；目标232：总额正确（字段：grand_total；组内 AND）；目标233：记录编号正确（字段：increment_id；组内 AND）；目标233：总额正确（字段：grand_total；组内 AND）；目标234：记录编号正确（字段：increment_id；组内 AND）；目标234：总额正确（字段：grand_total；组内 AND）；目标235：记录编号正确（字段：increment_id；组内 AND）；目标235：总额正确（字段：grand_total；组内 AND）；目标236：记录编号正确（字段：increment_id；组内 AND）；目标236：总额正确（字段：grand_total；组内 AND）；目标237：记录编号正确（字段：increment_id；组内 AND）；目标237：总额正确（字段：grand_total；组内 AND）；目标238：记录编号正确（字段：increment_id；组内 AND）；目标238：总额正确（字段：grand_total；组内 AND）；目标239：记录编号正确（字段：increment_id；组内 AND）；目标239：总额正确（字段：grand_total；组内 AND）；目标240：记录编号正确（字段：increment_id；组内 AND）；目标240：总额正确（字段：grand_total；组内 AND）；目标241：记录编号正确（字段：increment_id；组内 AND）；目标241：总额正确（字段：grand_total；组内 AND）；目标242：记录编号正确（字段：increment_id；组内 AND）；目标242：总额正确（字段：grand_total；组内 AND）；目标243：记录编号正确（字段：increment_id；组内 AND）；目标243：总额正确（字段：grand_total；组内 AND）；目标244：记录编号正确（字段：increment_id；组内 AND）；目标244：总额正确（字段：grand_total；组内 AND）；目标245：记录编号正确（字段：increment_id；组内 AND）；目标245：总额正确（字段：grand_total；组内 AND）；目标246：记录编号正确（字段：increment_id；组内 AND）；目标246：总额正确（字段：grand_total；组内 AND）；目标247：记录编号正确（字段：increment_id；组内 AND）；目标247：总额正确（字段：grand_total；组内 AND）；目标248：记录编号正确（字段：increment_id；组内 AND）；目标248：总额正确（字段：grand_total；组内 AND）；目标249：记录编号正确（字段：increment_id；组内 AND）；目标249：总额正确（字段：grand_total；组内 AND）；目标250：记录编号正确（字段：increment_id；组内 AND）；目标250：总额正确（字段：grand_total；组内 AND）；目标251：记录编号正确（字段：increment_id；组内 AND）；目标251：总额正确（字段：grand_total；组内 AND）；目标252：记录编号正确（字段：increment_id；组内 AND）；目标252：总额正确（字段：grand_total；组内 AND）；目标253：记录编号正确（字段：increment_id；组内 AND）；目标253：总额正确（字段：grand_total；组内 AND）；目标254：记录编号正确（字段：increment_id；组内 AND）；目标254：总额正确（字段：grand_total；组内 AND）；目标255：记录编号正确（字段：increment_id；组内 AND）；目标255：总额正确（字段：grand_total；组内 AND）；目标256：记录编号正确（字段：increment_id；组内 AND）；目标256：总额正确（字段：grand_total；组内 AND）；目标257：记录编号正确（字段：increment_id；组内 AND）；目标257：总额正确（字段：grand_total；组内 AND）；目标258：记录编号正确（字段：increment_id；组内 AND）；目标258：总额正确（字段：grand_total；组内 AND）；目标259：记录编号正确（字段：increment_id；组内 AND）；目标259：总额正确（字段：grand_total；组内 AND）；目标260：记录编号正确（字段：increment_id；组内 AND）；目标260：总额正确（字段：grand_total；组内 AND）；目标261：记录编号正确（字段：increment_id；组内 AND）；目标261：总额正确（字段：grand_total；组内 AND）；目标262：记录编号正确（字段：increment_id；组内 AND）；目标262：总额正确（字段：grand_total；组内 AND）；目标263：记录编号正确（字段：increment_id；组内 AND）；目标263：总额正确（字段：grand_total；组内 AND）；目标264：记录编号正确（字段：increment_id；组内 AND）；目标264：总额正确（字段：grand_total；组内 AND）；目标265：记录编号正确（字段：increment_id；组内 AND）；目标265：总额正确（字段：grand_total；组内 AND）；目标266：记录编号正确（字段：increment_id；组内 AND）；目标266：总额正确（字段：grand_total；组内 AND）；目标267：记录编号正确（字段：increment_id；组内 AND）；目标267：总额正确（字段：grand_total；组内 AND）；目标268：记录编号正确（字段：increment_id；组内 AND）；目标268：总额正确（字段：grand_total；组内 AND）；目标269：记录编号正确（字段：increment_id；组内 AND）；目标269：总额正确（字段：grand_total；组内 AND）；目标270：记录编号正确（字段：increment_id；组内 AND）；目标270：总额正确（字段：grand_total；组内 AND）；目标271：记录编号正确（字段：increment_id；组内 AND）；目标271：总额正确（字段：grand_total；组内 AND）；目标272：记录编号正确（字段：increment_id；组内 AND）；目标272：总额正确（字段：grand_total；组内 AND）；目标273：记录编号正确（字段：increment_id；组内 AND）；目标273：总额正确（字段：grand_total；组内 AND）；目标274：记录编号正确（字段：increment_id；组内 AND）；目标274：总额正确（字段：grand_total；组内 AND）；目标275：记录编号正确（字段：increment_id；组内 AND）；目标275：总额正确（字段：grand_total；组内 AND）；目标276：记录编号正确（字段：increment_id；组内 AND）；目标276：总额正确（字段：grand_total；组内 AND）；目标277：记录编号正确（字段：increment_id；组内 AND）；目标277：总额正确（字段：grand_total；组内 AND）；目标278：记录编号正确（字段：increment_id；组内 AND）；目标278：总额正确（字段：grand_total；组内 AND）；目标279：记录编号正确（字段：increment_id；组内 AND）；目标279：总额正确（字段：grand_total；组内 AND）；目标280：记录编号正确（字段：increment_id；组内 AND）；目标280：总额正确（字段：grand_total；组内 AND）；目标281：记录编号正确（字段：increment_id；组内 AND）；目标281：总额正确（字段：grand_total；组内 AND）；目标282：记录编号正确（字段：increment_id；组内 AND）；目标282：总额正确（字段：grand_total；组内 AND）；目标283：记录编号正确（字段：increment_id；组内 AND）；目标283：总额正确（字段：grand_total；组内 AND）；目标284：记录编号正确（字段：increment_id；组内 AND）；目标284：总额正确（字段：grand_total；组内 AND）；目标285：记录编号正确（字段：increment_id；组内 AND）；目标285：总额正确（字段：grand_total；组内 AND）；目标286：记录编号正确（字段：increment_id；组内 AND）；目标286：总额正确（字段：grand_total；组内 AND）；目标287：记录编号正确（字段：increment_id；组内 AND）；目标287：总额正确（字段：grand_total；组内 AND）；目标288：记录编号正确（字段：increment_id；组内 AND）；目标288：总额正确（字段：grand_total；组内 AND）；目标289：记录编号正确（字段：increment_id；组内 AND）；目标289：总额正确（字段：grand_total；组内 AND）；目标290：记录编号正确（字段：increment_id；组内 AND）；目标290：总额正确（字段：grand_total；组内 AND）；目标291：记录编号正确（字段：increment_id；组内 AND）；目标291：总额正确（字段：grand_total；组内 AND）；目标292：记录编号正确（字段：increment_id；组内 AND）；目标292：总额正确（字段：grand_total；组内 AND）；目标293：记录编号正确（字段：increment_id；组内 AND）；目标293：总额正确（字段：grand_total；组内 AND）；目标294：记录编号正确（字段：increment_id；组内 AND）；目标294：总额正确（字段：grand_total；组内 AND）；目标295：记录编号正确（字段：increment_id；组内 AND）；目标295：总额正确（字段：grand_total；组内 AND）；目标296：记录编号正确（字段：increment_id；组内 AND）；目标296：总额正确（字段：grand_total；组内 AND）；目标297：记录编号正确（字段：increment_id；组内 AND）；目标297：总额正确（字段：grand_total；组内 AND）；目标298：记录编号正确（字段：increment_id；组内 AND）；目标298：总额正确（字段：grand_total；组内 AND）；目标299：记录编号正确（字段：increment_id；组内 AND）；目标299：总额正确（字段：grand_total；组内 AND）；目标300：记录编号正确（字段：increment_id；组内 AND）；目标300：总额正确（字段：grand_total；组内 AND）；目标301：记录编号正确（字段：increment_id；组内 AND）；目标301：总额正确（字段：grand_total；组内 AND）；目标302：记录编号正确（字段：increment_id；组内 AND）；目标302：总额正确（字段：grand_total；组内 AND）；目标303：记录编号正确（字段：increment_id；组内 AND）；目标303：总额正确（字段：grand_total；组内 AND）；目标304：记录编号正确（字段：increment_id；组内 AND）；目标304：总额正确（字段：grand_total；组内 AND）；目标305：记录编号正确（字段：increment_id；组内 AND）；目标305：总额正确（字段：grand_total；组内 AND）；目标306：记录编号正确（字段：increment_id；组内 AND）；目标306：总额正确（字段：grand_total；组内 AND）；目标307：记录编号正确（字段：increment_id；组内 AND）；目标307：总额正确（字段：grand_total；组内 AND）；目标308：记录编号正确（字段：increment_id；组内 AND）；目标308：总额正确（字段：grand_total；组内 AND）

## 题目 142（d555e57bbc134c2d89c5）

**题面：** Create a customer group named VIP Customers, exclude Main Website, and save the group.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:create`；new_matching_record_saved: 原选择条件匹配且本次新增的记录恰好一条。; created_record_conditions: 该唯一新记录整体满足原 create_conditions。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; existing_records_unchanged: 原有实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; existing_records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 3 计分：实际新增并保存一个本任务可唯一绑定的有效对象（字段：；组内 AND）；名称正确（字段：name；组内 AND）；网站排除配置正确（字段：excluded_website_ids；组内 AND）

## 题目 143（d5625da1a9cdb07f180b）

**题面：** Create and save a simple product named Training Product d5625d, SKU TRAIN-d5625da1a9cdb07f180b, price 9.99, stock quantity 100. Keep valid defaults for unspecified settings.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:create`；new_matching_record_saved: 原选择条件匹配且本次新增的记录恰好一条。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; existing_records_unchanged: 原有实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; existing_records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 5 计分：实际新增并保存一个本任务可唯一绑定的有效对象（字段：；组内 AND）；名称正确（字段：name；组内 AND）；SKU正确（字段：sku；组内 AND）；价格正确（字段：price；组内 AND）；数量正确（字段：qty；组内 AND）

## 题目 144（d6c9a19fbbadca1e0548）

**题面：** Export customer data to CSV

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:export`；downloaded_matching_csv: 至少一个实际下载产物通过原内容及选中对象集合比较。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 140 计分：目标1：名称正确（字段：name；组内 AND）；目标1：邮箱正确（字段：email；组内 AND）；目标2：名称正确（字段：name；组内 AND）；目标2：邮箱正确（字段：email；组内 AND）；目标3：名称正确（字段：name；组内 AND）；目标3：邮箱正确（字段：email；组内 AND）；目标4：名称正确（字段：name；组内 AND）；目标4：邮箱正确（字段：email；组内 AND）；目标5：名称正确（字段：name；组内 AND）；目标5：邮箱正确（字段：email；组内 AND）；目标6：名称正确（字段：name；组内 AND）；目标6：邮箱正确（字段：email；组内 AND）；目标7：名称正确（字段：name；组内 AND）；目标7：邮箱正确（字段：email；组内 AND）；目标8：名称正确（字段：name；组内 AND）；目标8：邮箱正确（字段：email；组内 AND）；目标9：名称正确（字段：name；组内 AND）；目标9：邮箱正确（字段：email；组内 AND）；目标10：名称正确（字段：name；组内 AND）；目标10：邮箱正确（字段：email；组内 AND）；目标11：名称正确（字段：name；组内 AND）；目标11：邮箱正确（字段：email；组内 AND）；目标12：名称正确（字段：name；组内 AND）；目标12：邮箱正确（字段：email；组内 AND）；目标13：名称正确（字段：name；组内 AND）；目标13：邮箱正确（字段：email；组内 AND）；目标14：名称正确（字段：name；组内 AND）；目标14：邮箱正确（字段：email；组内 AND）；目标15：名称正确（字段：name；组内 AND）；目标15：邮箱正确（字段：email；组内 AND）；目标16：名称正确（字段：name；组内 AND）；目标16：邮箱正确（字段：email；组内 AND）；目标17：名称正确（字段：name；组内 AND）；目标17：邮箱正确（字段：email；组内 AND）；目标18：名称正确（字段：name；组内 AND）；目标18：邮箱正确（字段：email；组内 AND）；目标19：名称正确（字段：name；组内 AND）；目标19：邮箱正确（字段：email；组内 AND）；目标20：名称正确（字段：name；组内 AND）；目标20：邮箱正确（字段：email；组内 AND）；目标21：名称正确（字段：name；组内 AND）；目标21：邮箱正确（字段：email；组内 AND）；目标22：名称正确（字段：name；组内 AND）；目标22：邮箱正确（字段：email；组内 AND）；目标23：名称正确（字段：name；组内 AND）；目标23：邮箱正确（字段：email；组内 AND）；目标24：名称正确（字段：name；组内 AND）；目标24：邮箱正确（字段：email；组内 AND）；目标25：名称正确（字段：name；组内 AND）；目标25：邮箱正确（字段：email；组内 AND）；目标26：名称正确（字段：name；组内 AND）；目标26：邮箱正确（字段：email；组内 AND）；目标27：名称正确（字段：name；组内 AND）；目标27：邮箱正确（字段：email；组内 AND）；目标28：名称正确（字段：name；组内 AND）；目标28：邮箱正确（字段：email；组内 AND）；目标29：名称正确（字段：name；组内 AND）；目标29：邮箱正确（字段：email；组内 AND）；目标30：名称正确（字段：name；组内 AND）；目标30：邮箱正确（字段：email；组内 AND）；目标31：名称正确（字段：name；组内 AND）；目标31：邮箱正确（字段：email；组内 AND）；目标32：名称正确（字段：name；组内 AND）；目标32：邮箱正确（字段：email；组内 AND）；目标33：名称正确（字段：name；组内 AND）；目标33：邮箱正确（字段：email；组内 AND）；目标34：名称正确（字段：name；组内 AND）；目标34：邮箱正确（字段：email；组内 AND）；目标35：名称正确（字段：name；组内 AND）；目标35：邮箱正确（字段：email；组内 AND）；目标36：名称正确（字段：name；组内 AND）；目标36：邮箱正确（字段：email；组内 AND）；目标37：名称正确（字段：name；组内 AND）；目标37：邮箱正确（字段：email；组内 AND）；目标38：名称正确（字段：name；组内 AND）；目标38：邮箱正确（字段：email；组内 AND）；目标39：名称正确（字段：name；组内 AND）；目标39：邮箱正确（字段：email；组内 AND）；目标40：名称正确（字段：name；组内 AND）；目标40：邮箱正确（字段：email；组内 AND）；目标41：名称正确（字段：name；组内 AND）；目标41：邮箱正确（字段：email；组内 AND）；目标42：名称正确（字段：name；组内 AND）；目标42：邮箱正确（字段：email；组内 AND）；目标43：名称正确（字段：name；组内 AND）；目标43：邮箱正确（字段：email；组内 AND）；目标44：名称正确（字段：name；组内 AND）；目标44：邮箱正确（字段：email；组内 AND）；目标45：名称正确（字段：name；组内 AND）；目标45：邮箱正确（字段：email；组内 AND）；目标46：名称正确（字段：name；组内 AND）；目标46：邮箱正确（字段：email；组内 AND）；目标47：名称正确（字段：name；组内 AND）；目标47：邮箱正确（字段：email；组内 AND）；目标48：名称正确（字段：name；组内 AND）；目标48：邮箱正确（字段：email；组内 AND）；目标49：名称正确（字段：name；组内 AND）；目标49：邮箱正确（字段：email；组内 AND）；目标50：名称正确（字段：name；组内 AND）；目标50：邮箱正确（字段：email；组内 AND）；目标51：名称正确（字段：name；组内 AND）；目标51：邮箱正确（字段：email；组内 AND）；目标52：名称正确（字段：name；组内 AND）；目标52：邮箱正确（字段：email；组内 AND）；目标53：名称正确（字段：name；组内 AND）；目标53：邮箱正确（字段：email；组内 AND）；目标54：名称正确（字段：name；组内 AND）；目标54：邮箱正确（字段：email；组内 AND）；目标55：名称正确（字段：name；组内 AND）；目标55：邮箱正确（字段：email；组内 AND）；目标56：名称正确（字段：name；组内 AND）；目标56：邮箱正确（字段：email；组内 AND）；目标57：名称正确（字段：name；组内 AND）；目标57：邮箱正确（字段：email；组内 AND）；目标58：名称正确（字段：name；组内 AND）；目标58：邮箱正确（字段：email；组内 AND）；目标59：名称正确（字段：name；组内 AND）；目标59：邮箱正确（字段：email；组内 AND）；目标60：名称正确（字段：name；组内 AND）；目标60：邮箱正确（字段：email；组内 AND）；目标61：名称正确（字段：name；组内 AND）；目标61：邮箱正确（字段：email；组内 AND）；目标62：名称正确（字段：name；组内 AND）；目标62：邮箱正确（字段：email；组内 AND）；目标63：名称正确（字段：name；组内 AND）；目标63：邮箱正确（字段：email；组内 AND）；目标64：名称正确（字段：name；组内 AND）；目标64：邮箱正确（字段：email；组内 AND）；目标65：名称正确（字段：name；组内 AND）；目标65：邮箱正确（字段：email；组内 AND）；目标66：名称正确（字段：name；组内 AND）；目标66：邮箱正确（字段：email；组内 AND）；目标67：名称正确（字段：name；组内 AND）；目标67：邮箱正确（字段：email；组内 AND）；目标68：名称正确（字段：name；组内 AND）；目标68：邮箱正确（字段：email；组内 AND）；目标69：名称正确（字段：name；组内 AND）；目标69：邮箱正确（字段：email；组内 AND）；目标70：名称正确（字段：name；组内 AND）；目标70：邮箱正确（字段：email；组内 AND）

## 题目 145（d6ca61ffbbc704a34880）

**题面：** Create a new customer account with the name "John Smith" and email "john.smith@example.com"

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:create`；new_matching_record_saved: 原选择条件匹配且本次新增的记录恰好一条。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; existing_records_unchanged: 原有实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; existing_records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 3 计分：实际新增并保存一个本任务可唯一绑定的有效对象（字段：；组内 AND）；完整姓名正确（字段：firstname, lastname；组内 AND）；邮箱正确（字段：email；组内 AND）

## 题目 146（d8597402b1c899c1eaea）

**题面：** For this local restored-page task, read the Yotpo description on the Magento Marketplace page and return its exact description text. Stay on the local page; external partner websites are outside the task.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:page_text_query`；correct_partner_description: 提交的描述与原指定伙伴的页面参考描述一致。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; correct_page: 终页路径为本题原要求路径。; records_unchanged: 原分支所比较的记录范围保持。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。; partner_still_available: 原指定伙伴的终页描述仍与初始参考相等。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; correct_page; records_unchanged; answer_schema; partner_still_available

**目前的评分准则：** 前提通过后，按固定分母 4 计分：评论及营销解决方案性质（字段：description；组内 AND）；帮助生成评论（字段：description；组内 AND）；帮助获得流量（字段：description；组内 AND）；帮助提高转化（字段：description；组内 AND）

## 题目 147（d9eedb3a01d7ba055979）

**题面：** For this local training variant, edit the existing URL rewrite in Default Store View: request path training-product-entry, target path catalog/product/view/id/1, redirect type Permanent (301). Save it.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:update`；persisted_requested_value: 原选中对象已持久保存，并整体满足 update_matches 的请求条件。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; other_records_unchanged: 原目标以外的同实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; other_records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 2 计分：目标路径正确（字段：target_path；组内 AND）；重定向类型正确（字段：redirect_type；组内 AND）

## 题目 148（dd3ea545f0d5d4ec39e7）

**题面：** Create a new customer group named "VIP Clients" with the tax class set to "Wholesale" and excluding the "Main Website".

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:create`；new_matching_record_saved: 原选择条件匹配且本次新增的记录恰好一条。; created_record_conditions: 该唯一新记录整体满足原 create_conditions。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; existing_records_unchanged: 原有实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; existing_records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 4 计分：实际新增并保存一个本任务可唯一绑定的有效对象（字段：；组内 AND）；名称正确（字段：name；组内 AND）；税类正确（字段：tax_label；组内 AND）；网站排除配置正确（字段：excluded_website_ids；组内 AND）

## 题目 149（e0d2db4c54b927dba6c4）

**题面：** List the step-by-step directions from 40.7830, -73.9650 to 40.7570, -73.9860.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_steps: 提交的 steps 满足原 record_set 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 6 计分：每条要求返回的路线指引内容和序号正确（字段：number, instruction；组内 AND）

## 题目 150（e185d8d1ac754b973390）

**题面：** Check the total distance and estimated travel time from New York City to Boston by car.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；path: /anvme/workspace/r102bf10-lab-generate-skill/experiments/train-partial-reward-20261117-v1/trace-review-v1/answer-completion-review.json; sha256: 8bce509b9b45b9e06b7bef0a47fb080d5715c3ca326a65313c447788501df5be

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 2 计分：answer_distance_km（字段：answer_distance_km；组内 AND）；answer_duration_minutes（字段：answer_duration_minutes；组内 AND）

## 题目 151（e59148d1ae21a34456e6）

**题面：** Create and save a simple product named Training Product e59148, SKU TRAIN-e59148d1ae21a34456e6, price 9.99. Keep valid defaults for unspecified settings.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:create`；new_matching_record_saved: 原选择条件匹配且本次新增的记录恰好一条。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; existing_records_unchanged: 原有实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; existing_records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 4 计分：实际新增并保存一个本任务可唯一绑定的有效对象（字段：；组内 AND）；名称正确（字段：name；组内 AND）；SKU正确（字段：sku；组内 AND）；价格正确（字段：price；组内 AND）

## 题目 152（e678830c65ec323f09db）

**题面：** View all 3 items in the cart to verify quantities before placing order

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_items: 提交的 items 满足原 record_set 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 6 计分：目标1：三个商品覆盖完整（字段：name；组内 AND）；目标1：三个商品对应数量全部正确（字段：quantity；组内 AND）；目标2：三个商品覆盖完整（字段：name；组内 AND）；目标2：三个商品对应数量全部正确（字段：quantity；组内 AND）；目标3：三个商品覆盖完整（字段：name；组内 AND）；目标3：三个商品对应数量全部正确（字段：quantity；组内 AND）

## 题目 153（e716ca170d71ab432a59）

**题面：** For this local training variant, Select order #000000002 and download all its available invoice, packing-slip and credit-memo documents as a PDF.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:pdf`；downloaded_correct_documents: 至少一个实际下载产物通过原内容及选中对象集合比较。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 3 计分：原订单的invoice文档正确（字段：invoice；组内 AND）；原订单的packing_slip文档正确（字段：packing_slip；组内 AND）；原订单的credit_memo文档正确（字段：credit_memo；组内 AND）

## 题目 154（e83b251b13a8daa1fc7a）

**题面：** Generate a geo URI for the current location

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_geo_uri: 提交的 geo_uri 满足原 string 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 2 计分：geo URI中的完整经纬度坐标对（字段：；组内 AND）；geo URI中的z缩放参数（字段：；组内 AND）

## 题目 155（e8d67ff6e22fa9ee3b67）

**题面：** List all directories in the a11y-syntax-highlighting repository.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_items: 提交的 items 满足原 record_set 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 14 计分：每个正确、不重复的要求列表成员（字段：path；组内 AND）

## 题目 156（e9c39aadd73068054997）

**题面：** Check what items are currently in your shopping cart with 3 items.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_items: 提交的 items 满足原 record_set 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 3 计分：每个正确、不重复的要求列表成员（字段：name；组内 AND）

## 题目 157（ee4d5f917fbea3c35cbe）

**题面：** Export the credit memo data as a CSV file.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:export`；downloaded_matching_csv: 至少一个实际下载产物通过原内容及选中对象集合比较。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 20 计分：退款单编号（字段：；组内 AND）；退款单创建日期（字段：；组内 AND）；关联订单编号（字段：；组内 AND）；订单创建日期（字段：；组内 AND）；账单姓名及完整账单地址（字段：；组内 AND）；退款单状态（字段：；组内 AND）；基础币种退款金额（字段：；组内 AND）；订单状态（字段：；组内 AND）；购买商店/站点（字段：；组内 AND）；完整收货地址（字段：；组内 AND）；客户完整姓名（字段：；组内 AND）；客户邮箱（字段：；组内 AND）；客户分组（字段：；组内 AND）；支付方式（字段：；组内 AND）；配送方式信息（字段：；组内 AND）；退款小计（字段：；组内 AND）；配送及手续费（字段：；组内 AND）；退款调整金额（字段：；组内 AND）；调整费用（字段：；组内 AND）；基础币种订单总额（字段：；组内 AND）

## 题目 158（f73c97fb77388ae7f772）

**题面：** Find the SKU number and manufacturer of the Mineralogie All Natural Lip Gloss, Ruby Rose.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；path: /anvme/workspace/r102bf10-lab-generate-skill/experiments/train-partial-reward-20261117-v1/trace-review-v1/answer-completion-review.json; sha256: 8bce509b9b45b9e06b7bef0a47fb080d5715c3ca326a65313c447788501df5be

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 2 计分：answer_sku（字段：answer_sku；组内 AND）；answer_manufacturer（字段：answer_manufacturer；组内 AND）

## 题目 159（f8a3e7d1108c55158a9d）

**题面：** View all customers from the United States

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:collection_query`；exact_result_set: 按原字段比较完整多重集合，包含数量、重复、遗漏和多余记录约束。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 140 计分：目标1：完整姓名正确（字段：firstname, lastname；组内 AND）；目标1：邮箱正确（字段：email；组内 AND）；目标2：完整姓名正确（字段：firstname, lastname；组内 AND）；目标2：邮箱正确（字段：email；组内 AND）；目标3：完整姓名正确（字段：firstname, lastname；组内 AND）；目标3：邮箱正确（字段：email；组内 AND）；目标4：完整姓名正确（字段：firstname, lastname；组内 AND）；目标4：邮箱正确（字段：email；组内 AND）；目标5：完整姓名正确（字段：firstname, lastname；组内 AND）；目标5：邮箱正确（字段：email；组内 AND）；目标6：完整姓名正确（字段：firstname, lastname；组内 AND）；目标6：邮箱正确（字段：email；组内 AND）；目标7：完整姓名正确（字段：firstname, lastname；组内 AND）；目标7：邮箱正确（字段：email；组内 AND）；目标8：完整姓名正确（字段：firstname, lastname；组内 AND）；目标8：邮箱正确（字段：email；组内 AND）；目标9：完整姓名正确（字段：firstname, lastname；组内 AND）；目标9：邮箱正确（字段：email；组内 AND）；目标10：完整姓名正确（字段：firstname, lastname；组内 AND）；目标10：邮箱正确（字段：email；组内 AND）；目标11：完整姓名正确（字段：firstname, lastname；组内 AND）；目标11：邮箱正确（字段：email；组内 AND）；目标12：完整姓名正确（字段：firstname, lastname；组内 AND）；目标12：邮箱正确（字段：email；组内 AND）；目标13：完整姓名正确（字段：firstname, lastname；组内 AND）；目标13：邮箱正确（字段：email；组内 AND）；目标14：完整姓名正确（字段：firstname, lastname；组内 AND）；目标14：邮箱正确（字段：email；组内 AND）；目标15：完整姓名正确（字段：firstname, lastname；组内 AND）；目标15：邮箱正确（字段：email；组内 AND）；目标16：完整姓名正确（字段：firstname, lastname；组内 AND）；目标16：邮箱正确（字段：email；组内 AND）；目标17：完整姓名正确（字段：firstname, lastname；组内 AND）；目标17：邮箱正确（字段：email；组内 AND）；目标18：完整姓名正确（字段：firstname, lastname；组内 AND）；目标18：邮箱正确（字段：email；组内 AND）；目标19：完整姓名正确（字段：firstname, lastname；组内 AND）；目标19：邮箱正确（字段：email；组内 AND）；目标20：完整姓名正确（字段：firstname, lastname；组内 AND）；目标20：邮箱正确（字段：email；组内 AND）；目标21：完整姓名正确（字段：firstname, lastname；组内 AND）；目标21：邮箱正确（字段：email；组内 AND）；目标22：完整姓名正确（字段：firstname, lastname；组内 AND）；目标22：邮箱正确（字段：email；组内 AND）；目标23：完整姓名正确（字段：firstname, lastname；组内 AND）；目标23：邮箱正确（字段：email；组内 AND）；目标24：完整姓名正确（字段：firstname, lastname；组内 AND）；目标24：邮箱正确（字段：email；组内 AND）；目标25：完整姓名正确（字段：firstname, lastname；组内 AND）；目标25：邮箱正确（字段：email；组内 AND）；目标26：完整姓名正确（字段：firstname, lastname；组内 AND）；目标26：邮箱正确（字段：email；组内 AND）；目标27：完整姓名正确（字段：firstname, lastname；组内 AND）；目标27：邮箱正确（字段：email；组内 AND）；目标28：完整姓名正确（字段：firstname, lastname；组内 AND）；目标28：邮箱正确（字段：email；组内 AND）；目标29：完整姓名正确（字段：firstname, lastname；组内 AND）；目标29：邮箱正确（字段：email；组内 AND）；目标30：完整姓名正确（字段：firstname, lastname；组内 AND）；目标30：邮箱正确（字段：email；组内 AND）；目标31：完整姓名正确（字段：firstname, lastname；组内 AND）；目标31：邮箱正确（字段：email；组内 AND）；目标32：完整姓名正确（字段：firstname, lastname；组内 AND）；目标32：邮箱正确（字段：email；组内 AND）；目标33：完整姓名正确（字段：firstname, lastname；组内 AND）；目标33：邮箱正确（字段：email；组内 AND）；目标34：完整姓名正确（字段：firstname, lastname；组内 AND）；目标34：邮箱正确（字段：email；组内 AND）；目标35：完整姓名正确（字段：firstname, lastname；组内 AND）；目标35：邮箱正确（字段：email；组内 AND）；目标36：完整姓名正确（字段：firstname, lastname；组内 AND）；目标36：邮箱正确（字段：email；组内 AND）；目标37：完整姓名正确（字段：firstname, lastname；组内 AND）；目标37：邮箱正确（字段：email；组内 AND）；目标38：完整姓名正确（字段：firstname, lastname；组内 AND）；目标38：邮箱正确（字段：email；组内 AND）；目标39：完整姓名正确（字段：firstname, lastname；组内 AND）；目标39：邮箱正确（字段：email；组内 AND）；目标40：完整姓名正确（字段：firstname, lastname；组内 AND）；目标40：邮箱正确（字段：email；组内 AND）；目标41：完整姓名正确（字段：firstname, lastname；组内 AND）；目标41：邮箱正确（字段：email；组内 AND）；目标42：完整姓名正确（字段：firstname, lastname；组内 AND）；目标42：邮箱正确（字段：email；组内 AND）；目标43：完整姓名正确（字段：firstname, lastname；组内 AND）；目标43：邮箱正确（字段：email；组内 AND）；目标44：完整姓名正确（字段：firstname, lastname；组内 AND）；目标44：邮箱正确（字段：email；组内 AND）；目标45：完整姓名正确（字段：firstname, lastname；组内 AND）；目标45：邮箱正确（字段：email；组内 AND）；目标46：完整姓名正确（字段：firstname, lastname；组内 AND）；目标46：邮箱正确（字段：email；组内 AND）；目标47：完整姓名正确（字段：firstname, lastname；组内 AND）；目标47：邮箱正确（字段：email；组内 AND）；目标48：完整姓名正确（字段：firstname, lastname；组内 AND）；目标48：邮箱正确（字段：email；组内 AND）；目标49：完整姓名正确（字段：firstname, lastname；组内 AND）；目标49：邮箱正确（字段：email；组内 AND）；目标50：完整姓名正确（字段：firstname, lastname；组内 AND）；目标50：邮箱正确（字段：email；组内 AND）；目标51：完整姓名正确（字段：firstname, lastname；组内 AND）；目标51：邮箱正确（字段：email；组内 AND）；目标52：完整姓名正确（字段：firstname, lastname；组内 AND）；目标52：邮箱正确（字段：email；组内 AND）；目标53：完整姓名正确（字段：firstname, lastname；组内 AND）；目标53：邮箱正确（字段：email；组内 AND）；目标54：完整姓名正确（字段：firstname, lastname；组内 AND）；目标54：邮箱正确（字段：email；组内 AND）；目标55：完整姓名正确（字段：firstname, lastname；组内 AND）；目标55：邮箱正确（字段：email；组内 AND）；目标56：完整姓名正确（字段：firstname, lastname；组内 AND）；目标56：邮箱正确（字段：email；组内 AND）；目标57：完整姓名正确（字段：firstname, lastname；组内 AND）；目标57：邮箱正确（字段：email；组内 AND）；目标58：完整姓名正确（字段：firstname, lastname；组内 AND）；目标58：邮箱正确（字段：email；组内 AND）；目标59：完整姓名正确（字段：firstname, lastname；组内 AND）；目标59：邮箱正确（字段：email；组内 AND）；目标60：完整姓名正确（字段：firstname, lastname；组内 AND）；目标60：邮箱正确（字段：email；组内 AND）；目标61：完整姓名正确（字段：firstname, lastname；组内 AND）；目标61：邮箱正确（字段：email；组内 AND）；目标62：完整姓名正确（字段：firstname, lastname；组内 AND）；目标62：邮箱正确（字段：email；组内 AND）；目标63：完整姓名正确（字段：firstname, lastname；组内 AND）；目标63：邮箱正确（字段：email；组内 AND）；目标64：完整姓名正确（字段：firstname, lastname；组内 AND）；目标64：邮箱正确（字段：email；组内 AND）；目标65：完整姓名正确（字段：firstname, lastname；组内 AND）；目标65：邮箱正确（字段：email；组内 AND）；目标66：完整姓名正确（字段：firstname, lastname；组内 AND）；目标66：邮箱正确（字段：email；组内 AND）；目标67：完整姓名正确（字段：firstname, lastname；组内 AND）；目标67：邮箱正确（字段：email；组内 AND）；目标68：完整姓名正确（字段：firstname, lastname；组内 AND）；目标68：邮箱正确（字段：email；组内 AND）；目标69：完整姓名正确（字段：firstname, lastname；组内 AND）；目标69：邮箱正确（字段：email；组内 AND）；目标70：完整姓名正确（字段：firstname, lastname；组内 AND）；目标70：邮箱正确（字段：email；组内 AND）

## 题目 160（fb397ea55485dc33f943）

**题面：** Create and save a new customer named Training Customer with email admin-fb397ea55485dc33f943@example.test. Keep valid defaults for unspecified optional fields.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:create`；new_matching_record_saved: 原选择条件匹配且本次新增的记录恰好一条。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; existing_records_unchanged: 原有实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; existing_records_unchanged

**目前的评分准则：** 前提通过后，按固定分母 3 计分：实际新增并保存一个本任务可唯一绑定的有效对象（字段：；组内 AND）；完整姓名正确（字段：firstname, lastname；组内 AND）；邮箱正确（字段：email；组内 AND）

## 题目 161（fbd675fc29750bd1a7ff）

**题面：** Find out who is using the a11y-syntax-highlighting themes.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_items: 提交的 items 满足原 record_set 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 前提通过后，按固定分母 7 计分：每个正确、不重复的要求列表成员（字段：name；组内 AND）
