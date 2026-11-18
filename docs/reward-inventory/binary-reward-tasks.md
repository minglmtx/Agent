# 二值奖励题目


## 题目 1（01491075d7002a532057）

**题面：** Find the SKU number for the Pre-baked Gingerbread House Kit

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_sku: 提交的 sku 满足原 string 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 2（01dbfb254303d2f08ae8）

**题面：** Search for credit memos by customer name "Veronica Costello"

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:collection_query`；exact_result_set: 按原字段比较完整多重集合，包含数量、重复、遗漏和多余记录约束。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 3（030ab9a939137f3487c0）

**题面：** Find out how many projects you have starred

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_starred_project_count: 提交的 starred_project_count 满足原 integer 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 4（03d66d95ff83bd2b6c60）

**题面：** Retrieve the price of the Pre-baked Gingerbread House Kit Value Pack.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_price: 提交的 price 满足原 decimal 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 5（04d41f77320aa450ac93）

**题面：** Configure inventory settings to enable backorders for the Eco-Friendly Water Bottle

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:update`；persisted_requested_value: 原选中对象已持久保存，并整体满足 update_matches 的请求条件。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; other_records_unchanged: 原目标以外的同实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; other_records_unchanged

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 6（05a4924068ed5d2957e5）

**题面：** See how many forks the MathJax project has

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_fork_count: 提交的 fork_count 满足原 integer 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 7（05bf9124ac8251050b90）

**题面：** Apply multiple filters to find refunded credit memos for customer Veronica Costello

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:collection_query`；exact_result_set: 按原字段比较完整多重集合，包含数量、重复、遗漏和多余记录约束。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 8（06c83311b1a750c09b79）

**题面：** Find out which forum has the most submissions

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_forum_name: 提交的 forum_name 满足原 string_choice 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 9（09e3cfe5f478c386a220）

**题面：** Who submitted the article titled “I built a “sentence to playlist” AI capable of turning your playlist ideas into a real playlist in a matter of seconds!”

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_author: 提交的 author 满足原 string 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 10（0a8f3325b194a807f848）

**题面：** Get the number of comments on the article "Cindy Williams Dies: ‘Laverne &amp; Shirley‘ Star Who Appeared In ’American Graffiti’ &amp; ‘The Conversation’ Was 75"

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_comment_count: 提交的 comment_count 满足原 integer 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 11（0c0195ce97a7d83dc247）

**题面：** Check who is the manufacturer of the Gingerbread House Kit.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_manufacturer: 提交的 manufacturer 满足原 string 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 12（0c7e5b3b68c71acc9776）

**题面：** Set the tax class of Yoga Mat Pro to None and save.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:update`；persisted_requested_value: 原选中对象已持久保存，并整体满足 update_matches 的请求条件。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; other_records_unchanged: 原目标以外的同实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; other_records_unchanged

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 13（0ccd1578f5f6ddc7b11c）

**题面：** Change the tax class of the customer group Updated General Customers to Retail Customer and save the group.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:update`；persisted_requested_value: 原选中对象已持久保存，并整体满足 update_matches 的请求条件。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; other_records_unchanged: 原目标以外的同实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; other_records_unchanged

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 14（0d32373dbf056a7cb733）

**题面：** Retrieve the number of submissions for the television forum.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_submission_count: 提交的 submission_count 满足原 integer 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 15（0e67c52509e468a02665）

**题面：** Find all female customers with birthdays in January

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:collection_query`；exact_result_set: 按原字段比较完整多重集合，包含数量、重复、遗漏和多余记录约束。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 16（0e7d0cf05895d7d5e746）

**题面：** What is the overall rating of the Pre-baked Gingerbread House Kit Value Pack?

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_rating_percent: 提交的 rating_percent 满足原 integer 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 17（0f2ae6c1ef83ad23962a）

**题面：** Set up a special price promotion for the Yoga Mat Pro

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:update`；persisted_requested_value: 原选中对象已持久保存，并整体满足 update_matches 的请求条件。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; other_records_unchanged: 原目标以外的同实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; other_records_unchanged

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 18（11e24e5efefea43a6a1e）

**题面：** Cancel the selected order. For this local training variant, the selected order is #000000301.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:update`；persisted_requested_value: 原选中对象已持久保存，并整体满足 update_matches 的请求条件。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; other_records_unchanged: 原目标以外的同实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; other_records_unchanged

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 19（15563156f55a18d63ec0）

**题面：** Find out when the post about "Gregory Allen Howard" was submitted

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_submission_date: 提交的 submission_date 满足原 string 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 20（162eecfe220af06b700f）

**题面：** View the license type for the a11y-syntax-highlighting project.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_license_type: 提交的 license_type 满足原 string 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 21（170349164ca41b627be8）

**题面：** Exclude Main Website from the Updated General Customers group, and save.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:update`；persisted_requested_value: 原选中对象已持久保存，并整体满足 update_matches 的请求条件。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; other_records_unchanged: 原目标以外的同实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; other_records_unchanged

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 22（1743b9363cdbd904475a）

**题面：** Identify the storage size used by the a11y-syntax-highlighting project.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_storage_size: 提交的 storage_size 满足原 string 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 23（17c277148ce43e3c80e1）

**题面：** Check the price of the Pre-baked Gingerbread House Kit Value Pack.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_price: 提交的 price 满足原 decimal 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 24（17d5e276fde02bf2afde）

**题面：** Remove the exclusion of Main Website for the Updated General Customers group, and save.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:update`；persisted_requested_value: 原选中对象已持久保存，并整体满足 update_matches 的请求条件。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; other_records_unchanged: 原目标以外的同实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; other_records_unchanged

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 25（18b4411f46e0c135a395）

**题面：** Check when the autojump project was last updated

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_updated_date: 提交的 updated_date 满足原 string 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 26（19b39dd61c696035ce37）

**题面：** Hold the selected order. For this local training variant, the selected order is #000000301.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:update`；persisted_requested_value: 原选中对象已持久保存，并整体满足 update_matches 的请求条件。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; other_records_unchanged: 原目标以外的同实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; other_records_unchanged

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 27（1beff0bc05a517207f6a）

**题面：** View the total number of submissions in the relationship_advice forum

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_submission_count: 提交的 submission_count 满足原 integer 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 28（1c3c050ec5ad45313ecf）

**题面：** Find out if there are any subscribers to the movies forum

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_has_subscribers: 提交的 has_subscribers 满足原 string 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 29（1c6b231f1fb372bb206d）

**题面：** Check the price of the "Mineralogie All Natural Lip Gloss, Ruby Rose" product.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_price: 提交的 price 满足原 decimal 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 30（20ab1fb9f2d8a7878c12）

**题面：** Identify the most recent project update date on the dashboard.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_updated_date: 提交的 updated_date 满足原 string 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 31（210e2c5cf187dea57672）

**题面：** See how many merge requests are open in the Byte Blaze / empathy-prompts project.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_open_merge_request_count: 提交的 open_merge_request_count 满足原 integer 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 32（22af52ab1c27d176f62c）

**题面：** Count how many vegan products are available based on the search results

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_count: 提交的 count 满足原 integer 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 33（232a5983ed3010501724）

**题面：** Set the tax class of Blue T-Shirt to None and save.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:update`；persisted_requested_value: 原选中对象已持久保存，并整体满足 update_matches 的请求条件。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; other_records_unchanged: 原目标以外的同实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; other_records_unchanged

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 34（23749feecb47697d2c74）

**题面：** On the local movies forum, find the post titled "THE DARK CRYSTAL Is Returning To Theaters In Celebration of 40th Anniversary! - Icon Vs. Icon" and report its exact title and submitting username. Use the local post metadata; opening or summarizing the external publisher article is not requested.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；path: /anvme/workspace/r102bf10-lab-generate-skill/experiments/train-partial-reward-20261117-v1/trace-review-v1/answer-completion-review.json; sha256: 8bce509b9b45b9e06b7bef0a47fb080d5715c3ca326a65313c447788501df5be

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema; answer_title

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 35（24bbc21e497fc7e6386f）

**题面：** Retrieve the number of submissions for the memes forum.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_submission_count: 提交的 submission_count 满足原 integer 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 36（25f8c0d4acb198c76444）

**题面：** View the status of order 000000188, whose total is $2,004.99.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_order_status: 提交的 order_status 满足原 string 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 37（275d2224448d1c011649）

**题面：** Check when the 1.0.0 version was released

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_released_date: 提交的 released_date 满足原 string 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 38（2802ed12abe1bb11f5a4）

**题面：** Find out who manufactures the Pre-baked Gingerbread House Kit Value Pack

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_manufacturer: 提交的 manufacturer 满足原 string 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 39（2bf4131ca3f524bf5b2e）

**题面：** Assign the new product "Sony Headphones" to the category "Electronics".

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:update`；persisted_requested_value: 原选中对象已持久保存，并整体满足 update_matches 的请求条件。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; other_records_unchanged: 原目标以外的同实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; other_records_unchanged

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 40（2c4b678cfc6978ab9182）

**题面：** Find out when Jane Doe created her customer account For this local training variant, the target account email is jane.doe@gmail.com.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:query`；answer_created_at: 提交的单字段值与原绑定对象的参考值相符。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 41（2c61c04a55f42336851b）

**题面：** Find the post with the most comments on the current AskReddit page

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_title: 提交的 title 满足原 string_choice 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 42（2e1b70fe70aa84c9809d）

**题面：** Check how many issues are open for the a11yproject.com project.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_open_issue_count: 提交的 open_issue_count 满足原 integer 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 43（2ebfec43e8215c9a172c）

**题面：** Find out how to contact One Stop Market customer service

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_contact_form_url: 提交的 contact_form_url 满足原 local_url 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 44（2fa6f09b1f19cd91fe9c）

**题面：** Find out when the project Byte Blaze / a11y-syntax-highlighting was last updated.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_updated_date: 提交的 updated_date 满足原 string 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 45（322038f10d4a08220ad3）

**题面：** Change the tax class of the customer group Updated General Customers to Wholesale Customer and save the group.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:update`；persisted_requested_value: 原选中对象已持久保存，并整体满足 update_matches 的请求条件。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; other_records_unchanged: 原目标以外的同实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; other_records_unchanged

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 46（331ea9c6f7b545d516de）

**题面：** Check how many issues are open on the project thoughtbot, inc. / administrate.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_open_issue_count: 提交的 open_issue_count 满足原 integer 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 47（36450a47ea9635c40045）

**题面：** Retrieve the price of the Nightfox Vulpes Handheld Digital Night Vision Goggles.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_price: 提交的 price 满足原 decimal 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 48（3645416e63ddda135f29）

**题面：** Find the most recent customer registration date

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:query`；answer_created_at: 提交的单字段值与原绑定对象的参考值相符。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 49（3934afdec1f314316da4）

**题面：** Check the SKU number of the Pre-baked Gingerbread House Kit Value Pack

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_sku: 提交的 sku 满足原 string 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 50（394010495e00e016fe24）

**题面：** Check the scale of the current map view

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；path: /anvme/workspace/r102bf10-lab-generate-skill/experiments/train-partial-reward-20261117-v1/trace-review-v1/answer-completion-review.json; sha256: 8bce509b9b45b9e06b7bef0a47fb080d5715c3ca326a65313c447788501df5be

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 51（3a54d442798dc2c3ad83）

**题面：** Change the inventory quantity of the Hera Pullover Hoodie-XS-Blue to 150 units

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:update`；persisted_requested_value: 原选中对象已持久保存，并整体满足 update_matches 的请求条件。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; other_records_unchanged: 原目标以外的同实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; other_records_unchanged

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 52（3a96fe846ef551e1b692）

**题面：** Check whether gamingpro456@gmail.com is registered. Return the matching registered email as an item, or an empty items list if it is not registered.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:collection_query`；exact_result_set: 按原字段比较完整多重集合，包含数量、重复、遗漏和多余记录约束。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 53（3b0bc1fa93e1285754a7）

**题面：** Find out when the Super-SloMo repository was last updated

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_updated_date: 提交的 updated_date 满足原 string 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 54（3b51c7012090fd5e495b）

**题面：** Check which customer group Adam Garcia belongs to For this local training variant, the target account email is adam.garcia@gmail.com.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:query`；answer_group_name: 提交的单字段值与原绑定对象的参考值相符。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 55（3c7b4db3d03b67efca2b）

**题面：** Check if Emma Lopez is subscribed to the newsletter.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_subscription_status: 提交的 subscription_status 满足原 string 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 56（3d80812ae97396311085）

**题面：** Check if the main wiki page exists.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_exists: 提交的 exists 满足原 string 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 57（3e22ddce719a377a4c62）

**题面：** Search for customer details using the keyword "Veronica Costello".

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:collection_query`；exact_result_set: 按原字段比较完整多重集合，包含数量、重复、遗漏和多余记录约束。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 58（3e58d846a3d9e983aacd）

**题面：** Set the Country of Manufacture for the Yoga Mat Pro to "United States"

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:update`；persisted_requested_value: 原选中对象已持久保存，并整体满足 update_matches 的请求条件。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; other_records_unchanged: 原目标以外的同实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; other_records_unchanged

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 59（3f5222e07879c45f56d0）

**题面：** Unhold the selected order. For this local training variant, the selected order is #000000301.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:update`；persisted_requested_value: 原选中对象已持久保存，并整体满足 update_matches 的请求条件。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; other_records_unchanged: 原目标以外的同实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; other_records_unchanged

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 60（411514c1c37d67746116）

**题面：** For this local training variant, change Adam Garcia’s first name to Adam Updated and save. For this local training variant, the target account email is adam.garcia@gmail.com.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:update`；persisted_requested_value: 原选中对象已持久保存，并整体满足 update_matches 的请求条件。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; other_records_unchanged: 原目标以外的同实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; other_records_unchanged

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 61（41dedbdeb66536b8d8d1）

**题面：** Check the stock status of the Pre-baked Gingerbread House Kit Value Pack.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_stock_status: 提交的 stock_status 满足原 string 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 62（4247576686e176dea583）

**题面：** Find out what materials the Nightfox Vulpes Night Vision Goggles are made of.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_material: 提交的 material 满足原 string 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 63（426281fcea06f8c62a26）

**题面：** Count pending to-dos related to the Byte Blaze / a11y-webring.club project.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_todo_count: 提交的 todo_count 满足原 integer 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 64（42c114bf04c61fd15ad1）

**题面：** Retrieve the title and number of comments for the post "You win $1B but in exchange you can never use social media again, are you interested what would you do?"

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；path: /anvme/workspace/r102bf10-lab-generate-skill/experiments/train-partial-reward-20261117-v1/trace-review-v1/answer-completion-review.json; sha256: 8bce509b9b45b9e06b7bef0a47fb080d5715c3ca326a65313c447788501df5be

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema; answer_title

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 65（45ffd6778b9d863ba9ca）

**题面：** Check the price of the Custom Jersey Style St Patricks Day T-Shirt

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_price: 提交的 price 满足原 decimal 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 66（46202d04304eac1719ed）

**题面：** What is the submission date for the article about D.H Peligro, drummer of punk band Dead Kennedys, passing away?

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_submission_date: 提交的 submission_date 满足原 string 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 67（485486b9f7dfb1584bb6）

**题面：** For this local training task, select order #000000002 and download its existing training shipping label as a PDF. The fixed label is for simulation only and is not valid for postage. Do not purchase or generate a live carrier label.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:pdf`；downloaded_correct_documents: 至少一个实际下载产物通过原内容及选中对象集合比较。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 68（49c5b0402a3d521509dd）

**题面：** Check if the Nightfox Vulpes Night Vision Goggles are in stock.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_stock_status: 提交的 stock_status 满足原 string 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 69（4a9824d5f9d587cc9c6c）

**题面：** Set up cross-sell products for Example Product Deluxe 2023

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:links`；requested_relationship_change: 原目标和链接类型的关系集合发生原要求的增删，并满足原集合包含约束。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; other_relationships_unchanged: 原目标或链接类型以外的关系保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; other_relationships_unchanged

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 70（4c258f420fd1dbddf2e2）

**题面：** Count the number of stars for the Mozilla Festival project.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_star_count: 提交的 star_count 满足原 integer 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 71（4c44ebe0f2c8fd9f35a3）

**题面：** Update the price of the "Test Product" to $39.99

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:update`；persisted_requested_value: 原选中对象已持久保存，并整体满足 update_matches 的请求条件。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; other_records_unchanged: 原目标以外的同实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; other_records_unchanged

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 72（4fc71d425d26b849cdaa）

**题面：** Access the Advanced Pricing settings for the Blue T-Shirt and update the special price.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:update`；persisted_requested_value: 原选中对象已持久保存，并整体满足 update_matches 的请求条件。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; other_records_unchanged: 原目标以外的同实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; other_records_unchanged

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 73（4fcb5d49a6794c46e8e8）

**题面：** Check what magnification the Nightfox Vulpes Night Vision Goggles offer.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_magnification: 提交的 magnification 满足原 decimal 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 74（5251c3c73aebfe0cd9c6）

**题面：** List the number of stars for the project The A11Y Project / a11yproject.com.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_star_count: 提交的 star_count 满足原 integer 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 75（53a975104f8bf03a7d4a）

**题面：** Check what tax classes are available for customer groups.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:collection_query`；exact_result_set: 按原字段比较完整多重集合，包含数量、重复、遗漏和多余记录约束。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 76（53c55b37cb86a07f3f21）

**题面：** Change the tax class of the customer group Updated General Customers to Wholesale Customer and save the group.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:update`；persisted_requested_value: 原选中对象已持久保存，并整体满足 update_matches 的请求条件。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; other_records_unchanged: 原目标以外的同实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; other_records_unchanged

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 77（55d3114f967d54b51fda）

**题面：** Find the username of the person who submitted the post about Nosferatu at 100 years

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_author: 提交的 author 满足原 string 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 78（55d84e6be0f0c0f44d8f）

**题面：** Find the distance scale for the current map view

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；path: /anvme/workspace/r102bf10-lab-generate-skill/experiments/train-partial-reward-20261117-v1/trace-review-v1/answer-completion-review.json; sha256: 8bce509b9b45b9e06b7bef0a47fb080d5715c3ca326a65313c447788501df5be

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 79（56b82251a17e22440ef4）

**题面：** How many comments are there on the article about Brian May receiving a knighthood?
To finish this query, output {"action": "finish", "answer": {"comment_count": 0}}. Put exactly these requested fields inside answer: comment_count. Do not return bare fields or a serialized JSON string. Return the requested field values without adding surrounding field labels or explanatory prefixes. When a field explicitly requests a UI label, preserve that observed label as its value. The <observed value> examples are placeholders; use the exact scalar types required by the public task schema. All example values, including 0, 0.0, false and [], illustrate types only; replace them with observed answers. Boolean fields must be JSON true or false, not quoted strings, numeric status codes or explanatory text. Money and numeric fields must follow the public schema; numeric strings are permitted only when that schema permits strings. Use no currency symbols or thousands separators, and no units. For string fields, preserve the requested text and any units explicitly required by the field definition. Telephone values must omit the T: or Tel: label; retain the phone number itself. Record identifiers are exact strings: preserve all leading zeros; do not convert an ID to a number. List-valued fields must be JSON arrays; use [] for no results, never an empty string, null or the word None. Read the requested values without modifying site records. Field types: comment_count=integer.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_comment_count: 提交的 comment_count 满足原 integer 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 80（582b5ef57b87b952b392）

**题面：** Find the most recent closure or merge time among currently closed or merged merge requests in byteblaze/a11y-syntax-highlighting. Return completed_at in UTC as YYYY-MM-DDTHH:MMZ, discarding seconds. Return none if neither collection contains a request.
To finish this query, output {"action": "finish", "answer": {"completed_at": "<observed value>"}}. Put exactly these requested fields inside answer: completed_at. Do not return bare fields or a serialized JSON string. Return the requested field values without adding surrounding field labels or explanatory prefixes. When a field explicitly requests a UI label, preserve that observed label as its value. The <observed value> examples are placeholders; use the exact scalar types required by the public task schema. All example values, including 0, 0.0, false and [], illustrate types only; replace them with observed answers. Boolean fields must be JSON true or false, not quoted strings, numeric status codes or explanatory text. Money and numeric fields must follow the public schema; numeric strings are permitted only when that schema permits strings. Use no currency symbols or thousands separators, and no units. For string fields, preserve the requested text and any units explicitly required by the field definition. Telephone values must omit the T: or Tel: label; retain the phone number itself. Record identifiers are exact strings: preserve all leading zeros; do not convert an ID to a number. List-valued fields must be JSON arrays; use [] for no results, never an empty string, null or the word None. Read the requested values without modifying site records. Field types: completed_at=string.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_completed_at: 提交的 completed_at 满足原 string 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 81（58a4e4a4b7fbb2662b2d）

**题面：** Update the stock status for the Maya Tunic product. Save a native stock status different from the initial saved status; either In Stock or Out of Stock is allowed.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:update`；persisted_requested_value: 原选中对象已持久保存，并整体满足 update_matches 的请求条件。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; other_records_unchanged: 原目标以外的同实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; other_records_unchanged

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 82（59980d9d5249b017145a）

**题面：** Find out when the gumble project was last updated

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_updated_date: 提交的 updated_date 满足原 string 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 83（5a5d552d30462f36409c）

**题面：** See how many issues across all statuses are assigned to me in the Byte Blaze / empathy-prompts project.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_count: 提交的 count 满足原 integer 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 84（5acb0a9a8cbbaa7e1ddd）

**题面：** View the subcategories under the "New Category Name" category

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:collection_query`；exact_result_set: 按原字段比较完整多重集合，包含数量、重复、遗漏和多余记录约束。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 85（5e356def10426fbef596）

**题面：** Set up cross-sell products for the Blue T-Shirt to increase cart value.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:links`；requested_relationship_change: 原目标和链接类型的关系集合发生原要求的增删，并满足原集合包含约束。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; other_relationships_unchanged: 原目标或链接类型以外的关系保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; other_relationships_unchanged

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 86（605fa472c81c3d397dbb）

**题面：** Change the name of the Updated General Customers group to General Retail Customers

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:update`；persisted_requested_value: 原选中对象已持久保存，并整体满足 update_matches 的请求条件。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; other_records_unchanged: 原目标以外的同实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; other_records_unchanged

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 87（6096f93770d67474ee61）

**题面：** Check whether my current shopping cart qualifies for free shipping to my default saved address without changing the cart or address. Do not place an order.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_free_shipping_available: 提交的 free_shipping_available 满足原 string 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 88（609abffc99ef4112c780）

**题面：** Check what routing engine is being used for the current directions.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_engine: 提交的 engine 满足原 string 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 89（61d16fff9c982ddf674f）

**题面：** Find the driving distance from New York City to Boston

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_distance_km: 提交的 distance_km 满足原 decimal 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 90（621e3a379562905e5595）

**题面：** For this local training variant, add Adam Garcia (adam.garcia@gmail.com), who currently has no subscriber record, to the newsletter subscribers. Use the existing customer account.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:create`；new_matching_record_saved: 原选择条件匹配且本次新增的记录恰好一条。; created_record_conditions: 该唯一新记录整体满足原 create_conditions。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; existing_records_unchanged: 原有实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; existing_records_unchanged

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 91（63148504db1e675ccf57）

**题面：** See how many issues are currently open in The A11Y Project repository

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_open_issue_count: 提交的 open_issue_count 满足原 integer 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 92（673d15028cccb54d0690）

**题面：** Check which customers belong to the VIP Customers group

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:collection_query`；exact_result_set: 按原字段比较完整多重集合，包含数量、重复、遗漏和多余记录约束。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 93（67ace090b86bd67c69f0）

**题面：** Check if there are any open issues for the cloud-to-butt project

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_exists: 提交的 exists 满足原 string 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 94（6828a71bbb7c7f4f6a37）

**题面：** Check how many comments the post about "bleaching your butthole" has

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_comment_count: 提交的 comment_count 满足原 integer 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 95（6a852616e68dfe6d2878）

**题面：** Get the quantity of NOZE Rustic Coat Rack Wall Mounted Shelf in the shopping cart.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_quantity: 提交的 quantity 满足原 integer 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 96（6d88148c5efc95914367）

**题面：** Save the currently displayed unsaved group-name change from Updated General Customers to Updated General Customers Saved.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:update`；persisted_requested_value: 原选中对象已持久保存，并整体满足 update_matches 的请求条件。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; other_records_unchanged: 原目标以外的同实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; other_records_unchanged

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 97（6fe8b1378a01b3b210c6）

**题面：** Find the shipment with the highest total quantity on the shipments page.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:query`；path: /anvme/workspace/r102bf10-lab-generate-skill/experiments/train-partial-reward-20261117-v1/trace-review-v1/answer-completion-review.json; sha256: 8bce509b9b45b9e06b7bef0a47fb080d5715c3ca326a65313c447788501df5be

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 98（70306d401418877c8921）

**题面：** Identify which forum has the most subscribers

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_forum_name: 提交的 forum_name 满足原 string_choice 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 99（727c233e307f925c0329）

**题面：** Check how many customer groups are available in the system

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:collection_query`；answer_count: 提交的数量等于原选中集合数量。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 100（748b3ecbeda6a6a10aa1）

**题面：** View the total cost of items in the shopping cart

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_items_subtotal: 提交的 items_subtotal 满足原 decimal 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 101（75b57e1ccf54de8f5ecb）

**题面：** Search for credit memos created in April 2023.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:collection_query`；exact_result_set: 按原字段比较完整多重集合，包含数量、重复、遗漏和多余记录约束。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 102（77f7fe934bd24e280aa3）

**题面：** Find when the millennials-to-snake-people project was last updated

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_updated_date: 提交的 updated_date 满足原 string 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 103（78d05122d0a400a6272d）

**题面：** Check the number of items in the cart from the order summary.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_item_count: 提交的 item_count 满足原 integer 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 104（7a0199e38526591e656f）

**题面：** Report the name and SKU of Yoga Mat Pro.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:query`；path: /anvme/workspace/r102bf10-lab-generate-skill/experiments/train-partial-reward-20261117-v1/trace-review-v1/answer-completion-review.json; sha256: 8bce509b9b45b9e06b7bef0a47fb080d5715c3ca326a65313c447788501df5be

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged; answer_schema; answer_name

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 105（7b0a04b077e4d9102163）

**题面：** Check how many starred projects I have

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_starred_project_count: 提交的 starred_project_count 满足原 integer 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 106（7b224eb22f9dddeb6cf6）

**题面：** Calculate the driving distance between Utica and Albany, NY

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_distance_km: 提交的 distance_km 满足原 decimal 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 107（7cdb7893ed10cf4ba75a）

**题面：** Find the price of the 5x40 Night Vision Monocular Telescopes.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_price: 提交的 price 满足原 decimal 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 108（7ed6122ce8c7f4646f43）

**题面：** View the map scale information at the current zoom level.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；path: /anvme/workspace/r102bf10-lab-generate-skill/experiments/train-partial-reward-20261117-v1/trace-review-v1/answer-completion-review.json; sha256: 8bce509b9b45b9e06b7bef0a47fb080d5715c3ca326a65313c447788501df5be

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 109（7f1fe5a50297a970b8fe）

**题面：** Disable the Hera Pullover Hoodie-XL-Orange product

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:update`；persisted_requested_value: 原选中对象已持久保存，并整体满足 update_matches 的请求条件。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; other_records_unchanged: 原目标以外的同实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; other_records_unchanged

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 110（827c1feb3bf63a67873f）

**题面：** On the local Music forum, find the post titled "Portugal. The Man spotlights health care for Alaska Indigenous communities in new video" and report its exact title and submitting username. Use the local post metadata; opening or summarizing the external publisher article is not requested.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；path: /anvme/workspace/r102bf10-lab-generate-skill/experiments/train-partial-reward-20261117-v1/trace-review-v1/answer-completion-review.json; sha256: 8bce509b9b45b9e06b7bef0a47fb080d5715c3ca326a65313c447788501df5be

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema; answer_title

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 111（8740532e91dbc3037815）

**题面：** Check the price of the "Posiflex MT4008 Point of Sale Tablet" product.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_price: 提交的 price 满足原 decimal 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 112（874e41af76db85c47ce4）

**题面：** See when the joke "My grandfather warned people that the Titanic would sink" was posted

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_submission_date: 提交的 submission_date 满足原 string 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 113（89c78a04c5f2b1e693ac）

**题面：** Reset the displayed new customer group form to discard Unsaved Training Group without saving a group.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:draft_reset`；form_reset: 原记录的非空表单默认字段全部恢复为原值。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; correct_form: 终页路径为原表单路径。; no_record_created: 该实体初末记录相等。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; correct_form; no_record_created

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 114（8a66ed1a43e9687e2412）

**题面：** What is the price of the Pre-baked Gingerbread House Kit Value Pack?

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_price: 提交的 price 满足原 decimal 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 115（8b7e1d9131362ea7a7f5）

**题面：** Find out how many comments the post about "What is the best way to remove a champagne bottle from your rectum?" has

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_comment_count: 提交的 comment_count 满足原 integer 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 116（8c857e0111275f007585）

**题面：** Check the shipping cost for your current cart items.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_shipping_cost: 提交的 shipping_cost 满足原 decimal 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 117（8f217e01825b6f114391）

**题面：** Check the total number of merge requests across all statuses in the OpenAPI Generator project.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_all_merge_request_count: 提交的 all_merge_request_count 满足原 integer 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 118（993478a7233e453bdbce）

**题面：** Check the estimated travel time for a car route from Times Square to JFK Airport

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_duration_minutes: 提交的 duration_minutes 满足原 integer 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 119（9a9b75750d305ace38fa）

**题面：** Who submitted the article titled “Holy shit is “Tom’s Diner” by Suzanne Vega & DNA so godamn good.”

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_author: 提交的 author 满足原 string 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 120（9cb0a2693df3645337ee）

**题面：** Check what payment methods are available for this purchase

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_payment_methods: 提交的 payment_methods 满足原 record_set 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 121（9e08e0b6f78a10e5cb42）

**题面：** Calculate the walking distance between Central Park and Times Square

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_distance_km: 提交的 distance_km 满足原 decimal 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 122（9e246c9920d1c80ed596）

**题面：** Retrieve the number of submissions for the space forum.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_submission_count: 提交的 submission_count 满足原 integer 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 123（9f561911da861969ad99）

**题面：** Find who assigned the pending to-do for the merge request "update or remove 404 links" in The A11Y Project / a11yproject.com.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_assigned_by: 提交的 assigned_by 满足原 string 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 124（9fccdb70fc3f5cda6c49）

**题面：** Check the payable total for my current shopping cart, including shipping to my default saved address. Do not place the order.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_order_total: 提交的 order_total 满足原 decimal 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 125（a00fd4a97eb92a33c922）

**题面：** For this local training variant, associate Adam Garcia (adam.garcia@gmail.com) with Training Secondary Website using Associate to Website, and save.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:update`；persisted_requested_value: 原选中对象已持久保存，并整体满足 update_matches 的请求条件。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; other_records_unchanged: 原目标以外的同实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; other_records_unchanged

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 126（a07262b05d647d15927e）

**题面：** Check the customer rating for the ACPOTEL Night Vision Monocular.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_rating_percent: 提交的 rating_percent 满足原 integer 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 127（a30dc8c6d713f134765f）

**题面：** View the rating percentage of the Nightfox Vulpes Handheld Digital Night Vision Goggles

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_rating_percent: 提交的 rating_percent 满足原 integer 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 128（a5a2d922b189348cfa7f）

**题面：** Find the most active forum based on number of submissions

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_forum_name: 提交的 forum_name 满足原 string_choice 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 129（a748206690e0427ddd04）

**题面：** Check if the shipping method can be changed from Flat Rate - Fixed at this stage of checkout

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_alternative_shipping_available: 提交的 alternative_shipping_available 满足原 string 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 130（a8af28f0b01292514ad0）

**题面：** Find out when the "checkstyle" project was last updated

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_updated_date: 提交的 updated_date 满足原 string 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 131（a94c1948e65b354ca24f）

**题面：** For this local training variant, change the URL key of New Category Name to "training-updated-category" and save.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:update`；persisted_requested_value: 原选中对象已持久保存，并整体满足 update_matches 的请求条件。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; other_records_unchanged: 原目标以外的同实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; other_records_unchanged

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 132（ad14f1ea651d3dfaa032）

**题面：** Find the current coordinates shown on the map

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；path: /anvme/workspace/r102bf10-lab-generate-skill/experiments/train-partial-reward-20261117-v1/trace-review-v1/answer-completion-review.json; sha256: 8bce509b9b45b9e06b7bef0a47fb080d5715c3ca326a65313c447788501df5be

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 133（ad26452f2969e7565c70）

**题面：** Find the estimated travel time for driving from Syracuse to Buffalo

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_duration_minutes: 提交的 duration_minutes 满足原 integer 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 134（ad3e4fb48ca4a16b8f1c）

**题面：** List the price of Lobster Cobbler Pot Pie - Gourmet Frozen Seafood Appetizers.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_price: 提交的 price 满足原 decimal 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 135（ad6b4323f8b6b17e62fd）

**题面：** Find the manufacturer of the Pre-baked Gingerbread House Kit.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_manufacturer: 提交的 manufacturer 满足原 string 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 136（ae68af8e1133e4f596dc）

**题面：** Check if you are subscribed to the newsletter.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_subscription_status: 提交的 subscription_status 满足原 string 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 137（aeda435714dad5e3f5c6）

**题面：** Retrieve the total number of issues across all statuses for The A11Y Project / a11yproject.com.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_all_issue_count: 提交的 all_issue_count 满足原 integer 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 138（b045428cb375aecc3613）

**题面：** Find which forum has the most submissions on this platform

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_forum_name: 提交的 forum_name 满足原 string_choice 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 139（b7dbf7b6ca54b76fbb97）

**题面：** Check the overall rating of the St Patricks Day T-Shirt

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_rating_percent: 提交的 rating_percent 满足原 integer 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 140（b864f0a929e2ed01b5f3）

**题面：** Check the license type of the PureLayout project

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_license_type: 提交的 license_type 满足原 string 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 141（b9fc14ca759f15cd389d）

**题面：** Find the highest rated vegan product on the first page

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_product: 提交的 product 满足原 string_choice 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 142（ba0e3915421dafab49c5）

**题面：** Check when the content_script.js file was last updated

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_file_updated_date: 提交的 file_updated_date 满足原 string 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 143（bbcfeac97cd866e06f1c）

**题面：** Check how many submissions are in the AskReddit forum

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_submission_count: 提交的 submission_count 满足原 integer 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 144（bec24923c0a7ed46e025）

**题面：** Check the total travel time for driving from New York City to Boston

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_duration_minutes: 提交的 duration_minutes 满足原 integer 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 145（bec64ee0077086f0b2cb）

**题面：** Check when the question about "song describes your love life" was posted

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_submission_date: 提交的 submission_date 满足原 string 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 146（bee5d9b2acdb2f66eb9c）

**题面：** Filter credit memos created between April 1, 2023 and April 30, 2023

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:collection_query`；exact_result_set: 按原字段比较完整多重集合，包含数量、重复、遗漏和多余记录约束。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 147（c0d03822ad3cc182a48a）

**题面：** Find all customers who registered between March 1, 2023 and April 1, 2023

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:collection_query`；exact_result_set: 按原字段比较完整多重集合，包含数量、重复、遗漏和多余记录约束。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 148（c251c8edc13bff852155）

**题面：** Change the tax class of the customer group Updated General Customers to Wholesale Customer and save the group.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:update`；persisted_requested_value: 原选中对象已持久保存，并整体满足 update_matches 的请求条件。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; other_records_unchanged: 原目标以外的同实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; other_records_unchanged

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 149（c3210e310f50c17ee5ab）

**题面：** Check the number of completed to-dos.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_completed_todo_count: 提交的 completed_todo_count 满足原 integer 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 150（c334c6a3aeb526c0cc15）

**题面：** View the number of stars for the system-design-primer repository

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_star_count: 提交的 star_count 满足原 integer 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 151（c4c457724ca5b3facc2f）

**题面：** Add a new related product to the Blue T-Shirt

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:links`；requested_relationship_change: 原目标和链接类型的关系集合发生原要求的增删，并满足原集合包含约束。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; other_relationships_unchanged: 原目标或链接类型以外的关系保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; other_relationships_unchanged

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 152（c6ebf0496191e8d8af97）

**题面：** For this local training variant, rename New Category Name to Updated Training Category and save.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:update`；persisted_requested_value: 原选中对象已持久保存，并整体满足 update_matches 的请求条件。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; other_records_unchanged: 原目标以外的同实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; other_records_unchanged

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 153（c73f96cd937d5a5d4222）

**题面：** Find the forum with the most submissions on the current page

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_forum_name: 提交的 forum_name 满足原 string_choice 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 154（c7c76b2b4fc56c624da4）

**题面：** Check how many pending to-dos I have in GitLab

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_pending_todo_count: 提交的 pending_todo_count 满足原 integer 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 155（c9d198f8cc222a1285bd）

**题面：** Find the project with the most open issues on the current page

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_project: 提交的 project 满足原 string_choice 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 156（c9e49f9b5ac1dd332e59）

**题面：** Check which projects have the most open issues

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_projects: 提交的 projects 满足原 record_set 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 157（c9ea69ebd9bbe0132937）

**题面：** Include the "New Category Name" category in the navigation menu

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:update`；persisted_requested_value: 原选中对象已持久保存，并整体满足 update_matches 的请求条件。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; other_records_unchanged: 原目标以外的同实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; other_records_unchanged

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 158（ca05753924c09a2b379f）

**题面：** Check if there are any wiki pages available

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_exists: 提交的 exists 满足原 string 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 159（ca513c352ac8683d59ba）

**题面：** Check how many issues are open in the ArduinoJson project

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_open_issue_count: 提交的 open_issue_count 满足原 integer 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 160（ced122c4f49dfa2d22b3）

**题面：** Check the total price of items in my shopping cart

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_items_subtotal: 提交的 items_subtotal 满足原 decimal 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 161（cef94e2c64f4f23f905e）

**题面：** Check which programming language is used in the gumble project

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_declared_language: 提交的 declared_language 满足原 string 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 162（cf17936dfd58f2333310）

**题面：** Look for projects with the most stars on the current page

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_projects: 提交的 projects 满足原 record_set 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 163（d0e66b5ec2fd2c26f88e）

**题面：** Find out if the Intel NUC Kit NUC6i7KYK Mini PC comes with a power cord

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_power_cord_included: 提交的 power_cord_included 满足原 string 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 164（d2920efde53b41c1a1b6）

**题面：** Add related products to the Blue T-Shirt product.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:links`；requested_relationship_change: 原目标和链接类型的关系集合发生原要求的增删，并满足原集合包含约束。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; other_relationships_unchanged: 原目标或链接类型以外的关系保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; other_relationships_unchanged

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 165（d2b42088c0be8bc2f160）

**题面：** Find out if user MarvelsGrantMan136 is whitelisted on the platform.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_whitelisted: 提交的 whitelisted 满足原 string 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 166（d344b156d8c7f1aa850a）

**题面：** Check the date when the negative review for the Gingerbread House Kit was posted.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_negative_review_date: 提交的 negative_review_date 满足原 string 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 167（d52c0aa1fd01a13549bf）

**题面：** Add a related product to the Yoga Mat Pro listing

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:links`；requested_relationship_change: 原目标和链接类型的关系集合发生原要求的增删，并满足原集合包含约束。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; other_relationships_unchanged: 原目标或链接类型以外的关系保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; other_relationships_unchanged

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 168（d57f5a05cc1dd5127e70）

**题面：** Retrieve the number of forks for the project "Byte Blaze / empathy-prompts".

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_fork_count: 提交的 fork_count 满足原 integer 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 169（d5bd865c545a1cd9a3a6）

**题面：** Find the total distance of the driving route from New York City to Boston

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_distance_km: 提交的 distance_km 满足原 decimal 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 170（d6a29e7a354b46ccc7d5）

**题面：** Check the manufacturer of the Pre-baked Gingerbread House Kit

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_manufacturer: 提交的 manufacturer 满足原 string 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 171（d83baacc79d7fd79e8c1）

**题面：** Find the post with the most comments on the AskReddit page
To finish this query, output {"action": "finish", "answer": {"title": "<observed value>"}}. Put exactly these requested fields inside answer: title. Do not return bare fields or a serialized JSON string. Return the requested field values without adding surrounding field labels or explanatory prefixes. When a field explicitly requests a UI label, preserve that observed label as its value. The <observed value> examples are placeholders; use the exact scalar types required by the public task schema. All example values, including 0, 0.0, false and [], illustrate types only; replace them with observed answers. Boolean fields must be JSON true or false, not quoted strings, numeric status codes or explanatory text. Money and numeric fields must follow the public schema; numeric strings are permitted only when that schema permits strings. Use no currency symbols or thousands separators, and no units. For string fields, preserve the requested text and any units explicitly required by the field definition. Telephone values must omit the T: or Tel: label; retain the phone number itself. Record identifiers are exact strings: preserve all leading zeros; do not convert an ID to a number. List-valued fields must be JSON arrays; use [] for no results, never an empty string, null or the word None. Read the requested values without modifying site records. Field types: title=string. Field meanings: {"title": "Exact title of one post with the largest comment count among the posts on the initial AskReddit page."}. If several items tie for the requested maximum, return any one tied item as a single string.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_title: 提交的 title 满足原 string_choice 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 172（d87e55ef023592f031df）

**题面：** Find the oldest completed to-do item in your GitLab account.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_oldest_todo_title: 提交的 oldest_todo_title 满足原 string_choice 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 173（da0fc47b98877acabdd8）

**题面：** Modify the inventory quantity of the Blue T-Shirt.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:update`；persisted_requested_value: 原选中对象已持久保存，并整体满足 update_matches 的请求条件。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; other_records_unchanged: 原目标以外的同实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; other_records_unchanged

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 174（da2963632dabe85ed989）

**题面：** Report the displayed net score (upvotes minus downvotes) for the post “Michael Jackson’s ‘Thriller’ Returns To Billboard Top 10 After 38 Years”.
To finish this query, output {"action": "finish", "answer": {"net_score": 0}}. Put exactly these requested fields inside answer: net_score. Do not return bare fields or a serialized JSON string. Return the requested field values without adding surrounding field labels or explanatory prefixes. When a field explicitly requests a UI label, preserve that observed label as its value. The <observed value> examples are placeholders; use the exact scalar types required by the public task schema. All example values, including 0, 0.0, false and [], illustrate types only; replace them with observed answers. Boolean fields must be JSON true or false, not quoted strings, numeric status codes or explanatory text. Money and numeric fields must follow the public schema; numeric strings are permitted only when that schema permits strings. Use no currency symbols or thousands separators, and no units. For string fields, preserve the requested text and any units explicitly required by the field definition. Telephone values must omit the T: or Tel: label; retain the phone number itself. Record identifiers are exact strings: preserve all leading zeros; do not convert an ID to a number. List-valued fields must be JSON arrays; use [] for no results, never an empty string, null or the word None. Read the requested values without modifying site records. Field types: net_score=integer.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_net_score: 提交的 net_score 满足原 integer 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 175（daa63e0184a9716e7f11）

**题面：** Locate all customers with a tax/VAT number in the system

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:collection_query`；exact_result_set: 按原字段比较完整多重集合，包含数量、重复、遗漏和多余记录约束。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 176（db25b171278a7d9c4cc6）

**题面：** Find the most recent release of The A11Y Project

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_tag: 提交的 tag 满足原 string_choice 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 177（db3e72832768a5e92899）

**题面：** Check if dark mode is currently enabled

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_dark_mode: 提交的 dark_mode 满足原 string 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 178（dcc126a9d92300a10259）

**题面：** Check how many items are currently in my shopping cart

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_item_count: 提交的 item_count 满足原 integer 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 179（dfb40a038914bcf1795b）

**题面：** View the list of VIP Customers

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:collection_query`；exact_result_set: 按原字段比较完整多重集合，包含数量、重复、遗漏和多余记录约束。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 180（e0acc2846f49efa750d7）

**题面：** Retrieve the total number of issues across all statuses for Byte Blaze / accessible-html-content-patterns.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_all_issue_count: 提交的 all_issue_count 满足原 integer 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 181（e154d00d7844088d94d7）

**题面：** Find out which websites are excluded from the Updated General Customers group

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:query`；answer_excluded_websites: 提交的单字段值与原绑定对象的参考值相符。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 182（e1651f6e9d684024eaeb）

**题面：** Exclude Main Website from the Updated General Customers group, and save.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:update`；persisted_requested_value: 原选中对象已持久保存，并整体满足 update_matches 的请求条件。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; other_records_unchanged: 原目标以外的同实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; other_records_unchanged

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 183（e191611698289fe50395）

**题面：** View when customer Adam Garcia created his account For this local training variant, the target account email is adam.garcia@gmail.com.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:query`；answer_created_at: 提交的单字段值与原绑定对象的参考值相符。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; records_unchanged: 原分支所比较的记录范围保持。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 184（e44dd798dd96c628fafa）

**题面：** For this local training variant, update the default billing address phone number of Jane Doe (jane.doe@gmail.com) to 555-123-4567 and save.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:update`；persisted_requested_value: 原选中对象已持久保存，并整体满足 update_matches 的请求条件。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; other_records_unchanged: 原目标以外的同实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; other_records_unchanged

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 185（e4507b6d61c7f5e585bb）

**题面：** Change Yoga Mat Pro price to 31.99 and save the product.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:update`；persisted_requested_value: 原选中对象已持久保存，并整体满足 update_matches 的请求条件。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; other_records_unchanged: 原目标以外的同实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; other_records_unchanged

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 186（e68e1f03005a83f12ade）

**题面：** Check how many issues are open in the TrafficMonitor repository

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_open_issue_count: 提交的 open_issue_count 满足原 integer 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 187（e99d790f732ba60e3c65）

**题面：** Count how many projects on this page have more than 10 stars

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_count: 提交的 count 满足原 integer 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 188（ec17d35f33b53e5a1baa）

**题面：** Check how many commits have been made to the cloud-to-butt repository

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_commit_count: 提交的 commit_count 满足原 integer 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 189（ec7ae8996688fc3a2e08）

**题面：** Set a special price for the Example Product Deluxe 2023.

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:update`；persisted_requested_value: 原选中对象已持久保存，并整体满足 update_matches 的请求条件。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; other_records_unchanged: 原目标以外的同实体记录保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; other_records_unchanged

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 190（ed517c55ec73b52a521c）

**题面：** Check how many closed issues are assigned to me across my accessible projects.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_count: 提交的 count 满足原 integer 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 191（ed6c769c8c1b8f530584）

**题面：** Find the price of the Bushnell 743333 Boresighter.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_price: 提交的 price 满足原 decimal 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 192（ee8e562868eff0202bf8）

**题面：** Find the number of submissions in the gaming forum.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_submission_count: 提交的 submission_count 满足原 integer 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 193（efb765feca3cf117c9e3）

**题面：** View when my account was registered

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_registration_date: 提交的 registration_date 满足原 string 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 194（f339a1b31f983a1b6cdb）

**题面：** Find the current map coordinates

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；path: /anvme/workspace/r102bf10-lab-generate-skill/experiments/train-partial-reward-20261117-v1/trace-review-v1/answer-completion-review.json; sha256: 8bce509b9b45b9e06b7bef0a47fb080d5715c3ca326a65313c447788501df5be

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 195（f412f90491545b946b32）

**题面：** Remove an existing up-sell product from the Blue T-Shirt

**判断器的判定条件：** 原分支 `admin_contract_rules.checks:links`；requested_relationship_change: 原目标和链接类型的关系集合发生原要求的增删，并满足原集合包含约束。; same_local_deployment: 终页 netloc 等于原本地部署。; valid_authenticated_page: 原终页未被标记登录页或页面错误。; other_relationships_unchanged: 原目标或链接类型以外的关系保持。

**原有前提/限制：** same_local_deployment; valid_authenticated_page; other_relationships_unchanged

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 196（f8fe2dec74b77ea9c172）

**题面：** Identify the oldest pending to-do in my list and report its title.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_oldest_todo_title: 提交的 oldest_todo_title 满足原 string_choice 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 197（fbe617235425d7ebe689）

**题面：** Find the price of the "Maryia Men 3D Creative Printed Graphic T Shirts Casual Short Sleeve Crewneck Muscle Tees Personality Realistic Suit".

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_price: 提交的 price 满足原 decimal 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 198（fedf71fe5f3cf9866519）

**题面：** Find the number of submissions in the Music forum.

**判断器的判定条件：** 原分支 `site_query_rules.evaluate_query:ordinary_query`；answer_submission_count: 提交的 submission_count 满足原 integer 比较规则。; page_valid: 原查询页面健康与可用性检查，不等于目标对象定位正确。; requested_records_unchanged: 本题原初末查询参考完整相等，不覆盖全部网站状态。; answer_schema: 提交答案满足原字段集合和适用行结构；不为漏答放宽。

**原有前提/限制：** page_valid; requested_records_unchanged; answer_schema

**目前的评分准则：** 二值：所有原有可用前提/限制和原判定条件满足记 1，否则记 0；证据不足或 unknown 保持 null，不转失败。

## 题目 199（00073fc0e98637fac697）

**题面：** Go to the Merge requests page for the a11y-syntax-highlighting repository.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 200（0072070662f4e7996848）

**题面：** Check out the TrafficMonitor project.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 201（0387fdd1bf583a5885f4）

**题面：** Navigate to the Byte Blaze / a11y-syntax-highlighting project page.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 202（045d55acdf88f915e141）

**题面：** Navigate to the New project creation page.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 203（05b6980cb7daa00b7b96）

**题面：** Navigate to the Deployments section of the a11y-syntax-highlighting project.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 204（06d23dbbc954ea0eb0a1）

**题面：** Choose "Just me" for who will be using this group.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 205（07a3cfdf9b180d079ed7）

**题面：** Navigate to the project page for Byte Blaze / empathy-prompts.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 206（0926bda7e9de9306bd1d）

**题面：** Navigate to your personal projects page

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 207（0aa2590caf2eff45521d）

**题面：** View the images directory in the repository.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 208（0b84a338d6a53e5da8e5）

**题面：** Navigate to the Issues page from the create new group page.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 209（0035032b51075f0ecf6f）

**题面：** View the details of the Plus Size Lingerie item in my cart

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 210（083ff9b8eba023e4ff5a）

**题面：** Open the Video Games category listing page.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 211（0a64917e7a4ac0700d59）

**题面：** Go to the Computers & Accessories section

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 212（0b607d62e6782eb64262）

**题面：** Browse the Electronics category to find electronic devices and accessories.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 213（0f0676833d04cef8cf07）

**题面：** Navigate to the Clothing, Shoes & Jewelry category to shop for apparel, footwear, and accessories.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 214（0f54611a24e7a90599d5）

**题面：** Navigate to the home page

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 215（1094c53c2034431c453d）

**题面：** Navigate to the product detail page for the V8 +Energy drink to view more information.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 216（10c66031ab9dc871e7dc）

**题面：** View My Wish List

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 217（12aa53b20b84f0fb1cb4）

**题面：** View the reviews of the Nightfox Vulpes Handheld Digital Night Vision Goggles.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 218（134973b622eb29eb2918）

**题面：** Navigate to your wish list to view saved items you want to purchase later.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 219（0189de83adbd18ca5109）

**题面：** Open the local Communities page to view its Local Chapters and Other Groups directory. External group websites or contact are not required.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 220（058c211ed6572633b8e3）

**题面：** Get driving directions from Boston to New York City.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 221（07c4afe9a10c12f2c391）

**题面：** Find directions between Central Park, New York and Times Square, New York.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 222（0849b046d63579fc3565）

**题面：** Reverse the direction to plan a trip from Boston to New York
Initial state: the displayed driving route runs from New York City to Boston.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 223（0870827f06e8ef841cf6）

**题面：** Find driving directions from Syracuse to Rochester, NY

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 224（090156aa79cd713a79c8）

**题面：** Get cycling directions from Times Square, New York to Central Park, New York.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 225（090b981871aa01b7b46f）

**题面：** Get walking directions from 40.74800, -73.98600 to 40.75300, -73.97700

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 226（0afd3e67a34103f0320a）

**题面：** View the specific route from Buffalo to Rochester on the map

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 227（0b42ca24c4bbb72a380c）

**题面：** Change the mode of transportation to Bicycle for the route from 40.7830, -73.9650 to 40.7570, -73.9860.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 228（0e969f70c08ad9d881ef）

**题面：** Navigate to the Copyright page to learn about OpenStreetMap licensing and attribution requirements.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 229（092c1675b6169ee15242）

**题面：** Navigate to the System section.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 230（0dba3fbedd31d942e2c1）

**题面：** Navigate to the STORES section of the admin panel.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 231（18ac54ffeac11b177872）

**题面：** Navigate to the System section from the credit memo view page.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 232（1b6c13b5546fb3506416）

**题面：** Navigate to the MARKETING section from the Dashboard page

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 233（05ff9add3cd319052583）

**题面：** View the user profile of MarvelsGrantMan136

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 234（062cf6938a87a7fe04c2）

**题面：** View your notifications to see any new activity.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 235（09c50a6b3d0ad9a2de06）

**题面：** View the discussion about "What movie trope are you a sucker for?"

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 236（0b7d10bf2e674eea1898）

**题面：** Check out the philadelphia forum.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 237（0e04d3aec835c1d5b7a8）

**题面：** Browse the worldnews forum

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 238（0fde74c9aa1d5d8dc9b7）

**题面：** View the relationship_advice forum.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 239（1173d3d994b7c0404a62）

**题面：** Return to the Home page

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 240（0bbee95a15b8840fefb0）

**题面：** View the understanding-vestibular-disorders.md file to learn about accessibility considerations for users with motion sensitivity.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 241（0cba5837440c660e0f84）

**题面：** Filter projects by name "android"

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 242（0f8811222ada4a28521a）

**题面：** Navigate to view all branches of the cloud-to-butt project.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 243（1d6ba316e7003442b363）

**题面：** Sort projects by most stars instead of name

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 244（1e88d13c0af8e045722e）

**题面：** Go to the Tags page to see release versions.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 245（1e933a96c73c403f4971）

**题面：** Visit the Issues page

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 246（1f81a9aa4f99df2ceb59）

**题面：** Search for Python projects in the GitLab explore page

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 247（dd5bf5833f21fac3a73b）

**题面：** Visit the Snippets page for the a11y-syntax-highlighting project.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 248（152a3ef5e349e96d3254）

**题面：** Check the commit history of the a11y-syntax-highlighting project.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 249（16369b1c4bbe0ce37cea）

**题面：** Visit the Search page to find projects, issues, or merge requests.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 250（16a8b25e2eb42d7384cf）

**题面：** Check the troubleshooting documentation for The A11Y Project.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 251（24ad31a1214a0cb41285）

**题面：** View all open merge requests for the wxpy project

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 252（2594b549f5054c75b79c）

**题面：** Explore trending projects.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 253（25e8ac362210da8a5672）

**题面：** Browse the repository code in Byte Blaze / a11y-syntax-highlighting.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 254（319fef2779eadbbba151）

**题面：** Open any merge request details page associated with a pending item in your current account's initial To-Do List. Any such target is acceptable; the route used to reach it is unrestricted. Leave the target page open and do not change the to-do items.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 255（357bfc824061bf58e58b）

**题面：** Browse projects by topics.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 256（3eea162bbb47832f524d）

**题面：** Visit the repository page for the "trpc" project

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 257（44018a87964ae1a7c8e0）

**题面：** Explore the highlight directory for Highlight.js themes.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 258（4492ebf4c3edc16dacde）

**题面：** View trending projects.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 259（46cfbead6f1968393a1e）

**题面：** Visit the project roadmap to see planned future support for editors like VS Code and Sublime Text.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 260（48ae77e5d0cc194a560f）

**题面：** Check the open issues for Byte Blaze / a11y-syntax-highlighting.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 261（52a352b5b40b267e95cc）

**题面：** Search for and view recently updated projects

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 262（536d80fb651c8023dcc8）

**题面：** View the split_silence.py example for audio processing

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 263（5f4efeaeb777c158e271）

**题面：** Learn about the Windows High Contrast Mode support in these themes.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 264（614d94c10e6d9e3d8db2）

**题面：** Go to the Dashboard page

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 265（6f9f09ff928255b2e62c）

**题面：** Go to the previous page of projects.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 266（7a47e1659934eacaa0a4）

**题面：** View the "Better sharing solution" issue in empathy-prompts.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 267（7a89b16cae2e6e62b76b）

**题面：** Navigate to the Issues page.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 268（7f9cbe175731494f9444）

**题面：** Explore the a11y-syntax-highlighting project repository.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 269（93f07bc8d671c50fe92b）

**题面：** Navigate to view all commits in the cloud-to-butt project history.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 270（a4a9ca3b41c7b722506b）

**题面：** View the examples of complex filter graphs in the ffmpeg-python project documentation (kkroening/ffmpeg-python).

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 271（a4c7022a121c07682a0a）

**题面：** Read the TECHNOLOGY.md file to understand the technical details of the A11Y Project.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 272（a81c118ee6065185645e）

**题面：** Navigate to the A11Y Project repository to view its code and contribute to accessibility improvements.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 273（b47837db4d7877b3e08f）

**题面：** Navigate to view the README.md file for the cloud-to-butt project.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 274（b97f982f826c4311d206）

**题面：** Navigate to your user profile page.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 275（bfb8ef140ac9aff54087）

**题面：** Access the CI/CD pipelines for the a11y-syntax-highlighting repository.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 276（c530edb71542ead8bb41）

**题面：** Navigate to the Merge Requests page.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 277（cca2dbf5a4709cfbbcd3）

**题面：** View the repository code in a11yproject/a11yproject.com.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 278（cd3eb64294def459855a）

**题面：** Change project sorting from name ascending to most recently updated

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 279（d071c67921ce55f0bed5）

**题面：** View the administrate Rails engine project.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 280（d35ad379f6914d06df57）

**题面：** Navigate to the src/index.njk file in a11yproject/a11yproject.com to examine the homepage template.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 281（ddeabd1d7dcdfe3d381e）

**题面：** View the how-to-write-accessible-forms.md file to understand form accessibility requirements.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 282（e946abc7791e67d006aa）

**题面：** Navigate to the Create new project page.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 283（f03a70d73cbc48476487）

**题面：** Navigate to the Issues page to see all issues assigned to you.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 284（f261d1bcd5ec0dc2e3e5）

**题面：** Visit the Analytics page to see project statistics and insights.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 285（f4a511b8be6e645d348c）

**题面：** View all stargazers of the autojump project

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 286（fbf6113823521546ab5d）

**题面：** View your personal projects.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 287（fce615ee838e6b7d2eba）

**题面：** Check the CI/CD pipeline status for the repository

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 288（209142457ea81e33873f）

**题面：** Change the transportation mode from Car to Bicycle for a route
Initial state: the displayed driving route runs from Times Square, New York to Central Park, New York.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 289（218b9e1f3bbafdd12bfa）

**题面：** Explore the "Communities" section.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 290（229b56c832ad5567472d）

**题面：** Change the transportation mode from car to foot for directions from Central Park to Times Square.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 291（28db69f8589995320fef）

**题面：** Open the Export page and leave its map-area selection form visible. This task ends at the form; downloading map data is not required.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 292（2b01346a650162809e75）

**题面：** Navigate to the History page to view changes made to the map.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 293（3a763d24f0737e8ccea3）

**题面：** Reverse the direction of a planned route
Initial state: the displayed driving route runs from Times Square, New York to Central Park, New York.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 294（4ae3baeb404856a3aef2）

**题面：** Access the Help page for guidance on using OpenStreetMap.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 295（4b9de2854a0341c31342）

**题面：** Check the available image format options for downloading the map

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 296（585afafca2dfc81fca02）

**题面：** Visit the "Copyright" page to understand usage rights.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 297（5c5b074f9a68b12fee96）

**题面：** Get cycling directions from Grand Central Station to Empire State Building

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 298（61bcd3cb83dd3588c37b）

**题面：** Change the transportation mode from car to bicycle for a route from Times Square to Central Park

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 299（6530ef3b4169dba120bb）

**题面：** View the history of recent changes to the map.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 300（655046ea2fa12651193f）

**题面：** Find driving directions from Central Park, New York to Times Square, New York using the Car (OSRM) option.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 301（662c59800bde1ba75b7b）

**题面：** Explore the different map layer options available on OpenStreetMap (Standard, CyclOSM, ÖPNVKarte, Humanitarian).

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 302（6aacd2dcebe49641a25b）

**题面：** Get driving directions from Times Square to Central Park in New York City

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 303（6c59219c88807202c103）

**题面：** Navigate to the Communities page to connect with other OpenStreetMap contributors.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 304（74429d6dfc3736f2eb19）

**题面：** Open the OpenID sign-in form so that its OpenID URL field and Login button are visible. Do not submit credentials or complete authentication.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 305（7b6588603121d62aa84e）

**题面：** Navigate to the History page to view past map edits and changes.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 306（7d75122fddc17399220e）

**题面：** Navigate to the Communities page to connect with other mappers and find local mapping groups.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 307（803615400e70561e4a91）

**题面：** Navigate to the Copyright page to understand OpenStreetMap licensing and attribution requirements.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 308（843be1460c9332302da5）

**题面：** Go to the export page to download map data.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 309（858caf1607608d5ae5a0）

**题面：** Display search results for New York City, New York, United States, with the city area shown on the map.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 310（85a7523f5745961ba8e1）

**题面：** Reverse the directions to get a route from Times Square to Central Park instead.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 311（9eed061a64564bf7146b）

**题面：** Navigate to the Communities page to find OpenStreetMap community groups and local chapters.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 312（a0bea5b00b33a65a8be4）

**题面：** Check the history of map edits in this area

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 313（bcad4bf877daf4d67423）

**题面：** Reverse the route direction to get directions from Central Park to Times Square
Initial state: the displayed driving route runs from Times Square, New York to Central Park, New York.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 314（bd40ef5bbf030f7c1505）

**题面：** Visit the Communities page on OpenStreetMap.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 315（c230980afa6f0bf0342b）

**题面：** Find and display the local OpenStreetMap Communities directory. Browsing an external chapter website is outside this local task.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 316（c2cdd5fb6c2f1ededd51）

**题面：** Navigate to the Help page to find documentation and guides for using OpenStreetMap.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 317（c69a04a7e1db2552e953）

**题面：** Navigate to the User Diaries page.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 318（cecc62133b744eca72cc）

**题面：** Navigate to the directions page to find a route between two locations.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 319（d1d275dc46efc2e65476）

**题面：** Explore communities related to OpenStreetMap

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 320（d89b0048178cd11720cd）

**题面：** Navigate to the GPS Traces page to upload or browse GPS tracks.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 321（e1006161c40c56b44309）

**题面：** View copyright information

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 322（e1b9a8faf241f6a088a8）

**题面：** Reverse the direction of the route to get directions from 40.75300, -73.97700 to 40.74800, -73.98600

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 323（f049bdfefc158611ea45）

**题面：** Access the local OpenStreetMap Help page and display its help options. External Wiki documentation is outside this local task.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 324（f31a7694a8abb9a05a0a）

**题面：** View what different map layers are available

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 325（fa2f7c04c93ddc04dd2f）

**题面：** Navigate to the Communities page to find and connect with local OpenStreetMap groups.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 326（fbc50f6895e5eb802320）

**题面：** Navigate to the Help page to get assistance with using OpenStreetMap.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 327（13a0fabb465d848a3d9f）

**题面：** Explore Patio, Lawn & Garden products

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 328（1ad6d2c220a09d4eec48）

**题面：** View details of the NOZE Rustic Coat Rack in my recently ordered items

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 329（255c56b474f48d698857）

**题面：** From the shopping cart page, open the Sports & Outdoors category page.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 330（269774e9cad9d6a4fc70）

**题面：** Go to page 2 of Beauty & Personal Care products

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 331（2a9363cecaf521d7e184）

**题面：** Navigate to the Health & Household category to shop for health products and household essentials.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 332（2fb1cbb63aa4a4d2f7a0）

**题面：** View the Bushnell 743333 Boresighter product details.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 333（34568cb201df021547da）

**题面：** View all your recently ordered items from your account.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 334（44abeb91aebb0043c0b0）

**题面：** Go back to the home page using breadcrumb navigation

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 335（464bd7f571d9eb04ce09）

**题面：** Browse Exercise & Fitness equipment.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 336（47dbbc6d000b4e84932c）

**题面：** Continue shopping and return to the homepage.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 337（5239a4f0b915fb43e36f）

**题面：** Visit the home page to browse all products.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 338（5ba99a807a9cf95280ec）

**题面：** View details of the Pre-baked Gingerbread House Kit Value Pack.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 339（5c796dd22c55ca62d44e）

**题面：** View details of a product in your cart.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 340（602bc6ede42c73e516ac）

**题面：** Explore Electronics products

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 341（62b7701daa69787a85d6）

**题面：** Read reviews for the Crazy Sales Massage Table Carry Bag.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 342（6acbad9b26c6427856ce）

**题面：** Look at Bedding products

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 343（6be6d37e350eb2bc36e7）

**题面：** View the Privacy and Cookie Policy page to learn about how the site handles your data.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 344（74c98564d1e35bf6dec4）

**题面：** Go to the Beauty & Personal Care category.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 345（78756f29fb9e71590a06）

**题面：** Go to your account page to manage your personal information

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 346（7c4352d8e52492a93e9b）

**题面：** Navigate to the Advanced Search page to search for specific products with filters.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 347（7ccd70cd9214b15c0a35）

**题面：** Navigate to the My Account page

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 348（7f76ec7678c1f7660c91）

**题面：** Browse products in the Beauty & Personal Care category

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 349（8886097798330a2b52ad）

**题面：** Browse the Grocery & Gourmet Food category

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 350（8aa88113542d93e86d9d）

**题面：** Go to Advanced Search to search for specific outdoor equipment.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 351（9f25892f02f29db5ec94）

**题面：** Navigate to the Clothing, Shoes & Jewelry category page to explore more products on sale.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 352（b8474380646f2fce807c）

**题面：** Navigate to page 2 of Home & Kitchen products to see more items.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 353（b87ba988ad238b0acc93）

**题面：** Explore Hair Care products for hair treatments and styling.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 354（ba50fac977c6e53d4929）

**题面：** View all customer reviews for the Nightfox Vulpes Night Vision Goggles.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 355（bd49de7c4477fe8104f6）

**题面：** Get detailed information about the "Power of Positivity" Eye Shadow Palette.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 356（c0e6e10cd6ba5aec5ffe）

**题面：** Go to the Advanced Search page.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 357（c2555416de619bc829ac）

**题面：** Browse to page 2 of the Beauty & Personal Care products

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 358（c358dd6529a01a140edf）

**题面：** Browse Tools & Accessories in Beauty category

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 359（c39966933178cd8c3756）

**题面：** View my order details for order #000000187

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 360（cd607128c0a32223b604）

**题面：** Go to My Account page

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 361（cf4999bde780275b58cb）

**题面：** View details of the Intel NUC Kit Mini PC

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 362（d9dee57aa1e361c911d1）

**题面：** View my product reviews

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 363（db147dc6bede0ae35635）

**题面：** Go to the List of cookies we collect section.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 364（e497369511069de0d3cd）

**题面：** View details for 5x40 Night Vision Monocular Telescopes Multifunctional IR Digital Night Vision Telescope Camera with Video Recorder Camouflage Infrared Camera Hunting Night Vision Monocular Device.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 365（e63887a2e5fee9b8851b）

**题面：** Shop for items in the Clothing, Shoes & Jewelry category.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 366（e916b770cf6c9961fb69）

**题面：** Navigate to the Hunting & Fishing category in Sports & Outdoors.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 367（eb659eedcb65a365df65）

**题面：** Browse Sports & Outdoors products

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 368（edfe76ffbd372ca622ae）

**题面：** Read reviews for Nightfox Vulpes Handheld Digital Night Vision Goggles.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 369（ee04c15561b881b0bf46）

**题面：** View the "Power of Positivity" Eye Shadow Palette product details

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 370（f07d85b36aa89cf41e5b）

**题面：** Go to the product page of "Bushnell 743333 Boresighter with Case & ARbors,Black".

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 371（f792d5b646924f60298a）

**题面：** Check your recently ordered items

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 372（fadb8e6b2ed3664b20d6）

**题面：** View Contact Us page.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 373（fdd86ebe9fbff3977476）

**题面：** Visit Newsletter Subscriptions page.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 374（18972d3400c722a4ffea）

**题面：** Go to the memes forum page to view its content.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 375（1b7cc1a2a3bded53a92c）

**题面：** Navigate to the Forums page.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 376（27c63bcda6ea5f513130）

**题面：** Navigate to the movies forum to discuss films, movie news, and cinema.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 377（2ab43456dd85145f8cc8）

**题面：** Explore the memes forum

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 378（3112149ed88814016dc3）

**题面：** Explore the science forum for scientific discussions.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 379（351cef41c763fe65bb86）

**题面：** Navigate to the page for creating a new wiki page.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 380（377df3ac94c013710664）

**题面：** Browse forums in alphabetical order.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 381（3d8eadee8a7a9377df5e）

**题面：** Sort forums by title.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 382（3e26458bd2eb43f20c5b）

**题面：** Browse the memes forum for humorous content.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 383（44b4afbbc9b99c36e9bb）

**题面：** Navigate to the joke page titled "My girlfriend left me because of my abandonment issues..."

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 384（45a739d64fcb5d5d3833）

**题面：** Check your hidden forums.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 385（47bdbdea898616e0cc46）

**题面：** Go to the forums page.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 386（49aa91c52b9c981c098f）

**题面：** Sort the forum list alphabetically by forum name

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 387（4af9ec625c89f92a8b85）

**题面：** Navigate to the food forum.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 388（5b52a8165650a66e8f37）

**题面：** Go back to the forums.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 389（5d450bf7b0ba022de554）

**题面：** Change the view of forums from submissions to alphabetical

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 390（5dd565a907f19bcd45b5）

**题面：** Go back to the home page from the submission form

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 391（60ff346de5439a79316a）

**题面：** Navigate to the homepage.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 392（65cd35447dd878098c31）

**题面：** Go to page 2 of the forums list

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 393（66126f96f8512e54a1c2）

**题面：** Sort posts in the movies forum by Most commented over all time to find the most discussed topics.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 394（69c434d3c2127b3def0a）

**题面：** Browse forums by tags.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 395（69d7c430e7b5c9272eb5）

**题面：** Navigate to the All pages section of the wiki.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 396（765eb522fe286cb0a66d）

**题面：** View the user profile of SashaGreatest.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 397（810a12011686f67f627a）

**题面：** Sort the forums by creation date to see the newest forums first.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 398（878413977cd9a814b942）

**题面：** Go to the LifeProTips forum

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 399（8bf1a6bbcea8351cd55b）

**题面：** View forums sorted alphabetically.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 400（8dbb7a62694a33a430cf）

**题面：** Go to the pics forum page to view its content.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 401（92f69c08511f177fb5b3）

**题面：** Explore the moderation log for the Music forum.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 402（933db784845321b7cf50）

**题面：** Check recent changes in the Wiki.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 403（9d63ee81b6bbf16f0386）

**题面：** Navigate to the Create new page section to start creating a new wiki page.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 404（9df7d3935a696be1049a）

**题面：** Go to the second page of forum listings

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 405（a8d2697ced77921baa92）

**题面：** Browse forums in alphabetical order

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 406（af31dc799e51ccad402c）

**题面：** Navigate to the Forums page to explore community discussions.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 407（b3bd93fe9fa6eb441da5）

**题面：** Search for posts about machine learning

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 408（b4f0486d4418ae0bca40）

**题面：** Navigate to page 2 of the forums list.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 409（bb07fa576f83587a108f）

**题面：** Use the native plain-text search for "upcoming movie releases" and display its local results. This is a literal search; no external release calendar is required.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 410（bb3cdfd32d3103c63645）

**题面：** Go to the news forum.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 411（be949364ea9b3305b0fd）

**题面：** View a user profile.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 412（ca5a11acef0c0662cafb）

**题面：** Check your block list.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 413（d2849c468c9d7f79fc4c）

**题面：** Navigate to the relationship_advice forum

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 414（d62097dc3f906d29763c）

**题面：** Clear the current search and search for "skin care products"

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 415（d79c8e87b72c40aadfa5）

**题面：** Navigate to the movies forum.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 416（deea459bf06ce5b27eb7）

**题面：** View your user profile

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 417（e642e4b7d549e51f63fb）

**题面：** Check recent changes in the Wiki

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 418（e9867fbfbd0d5464fd39）

**题面：** View all wiki pages

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 419（f7188e2322661c71283f）

**题面：** View forums in Alphabetical order.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 420（f8ad6d31e9aeed13d548）

**题面：** Navigate to the Alphabetical view to see forums listed in alphabetical order.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 421（f94fd0a85e1d2b24568c）

**题面：** Open the Submit page to create a new post

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 422（f9d2a2c865817e89de70）

**题面：** Visit the gaming forum to see gaming-related discussions

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 423（ff1288a318ead65fce2e）

**题面：** Access the homepage.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 424（1f55e7d6982e23b0ace1）

**题面：** Navigate to the SYSTEM section of the admin panel.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 425（2a2a147a398f0b25f455）

**题面：** Navigate to the Customers section to manage customer accounts, groups, and segments.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 426（365168956a85f49b0695）

**题面：** Navigate to the Content section in the Magento admin panel.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 427（4c9fb5d9afb995d13098）

**题面：** Navigate to the Catalog section from the credit memo view

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 428（4d965044bc6a00b01638）

**题面：** Navigate to the Marketing section to manage promotions.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 429（512eed77abee4b8ed8b6）

**题面：** Navigate to the Stores section to manage configuration, payment methods, taxes, and shipping settings.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 430（60826839b32ee9905dc0）

**题面：** View Reports.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 431（62ff49cb0c1dc47264cb）

**题面：** Navigate to the Reports section in Magento Admin.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 432（63a6e7044e415bed00d6）

**题面：** Navigate to the Sales section from the credit memo view.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 433（68d169e13d19a5c305b5）

**题面：** Navigate to the Sales section to manage orders, invoices, and shipments.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 434（7cab57f1d5d8ccb86777）

**题面：** Navigate to the Catalog section to manage products and categories.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 435（90c5c245601840fdfb50）

**题面：** Go to the Sales section.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 436（99f7e4b784cfdec12cb4）

**题面：** Navigate to the Sales section.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 437（9f87eaf8772bea881d3e）

**题面：** Check the MARKETING section for promotional activities.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 438（ba2aad0bc3217100b5cb）

**题面：** Enter the System section from the Customers page.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 439（c087db2325986747c17f）

**题面：** Navigate to the Sales section in the Magento Admin panel.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 440（d11cf9048e5fb0540986）

**题面：** Navigate to the SALES section of the Magento Admin panel.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 441（e8ffde6fb3307d42d939）

**题面：** Navigate to the Content section from the credit memo view page.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 442（3d11daa68b8c93f5858e）

**题面：** View details of the Plus Size Lingerie item in my cart

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 443（b4045013dcdbe0e6f5f9）

**题面：** Navigate to the reviews section for the Pre-baked Gingerbread House Kit Value Pack.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 444（505e04c5eb5201102f65）

**题面：** Shop for Home & Kitchen products.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 445（440a8b1af94cf76ed2bf）

**题面：** View merged merge requests assigned to your account.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 446（9819a41cd3b66bded28f）

**题面：** View issue #105 about Python 2.7 compatibility in youfou/wxpy.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 447（b1dc035ba13c6766daea）

**题面：** From the current Explore projects page, open your personal Projects dashboard home showing your projects. Leave that dashboard home open, rather than the Starred projects collection.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 448（bf43becccb2cb0f30d70）

**题面：** View all merge requests assigned to your account regardless of status.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 449（eb79e47b111e0d6f19e0）

**题面：** View open issues for checkstyle/checkstyle.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 450（54066c2710d43c3a8205）

**题面：** Display the local About OpenStreetMap page. Completion means that the local introduction page is open.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 451（81ef7b160b5471ddc8a1）

**题面：** Open the Stores navigation menu.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 452（bcc1737bbc829c7dcdfe）

**题面：** Open the Stores navigation menu.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 453（05680da53589ba4a7c39）

**题面：** Navigate to the Meta organization page.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 454（26258107ff993d1b71d7）

**题面：** Set up a GitLab group for personal use with "Just me" selected as the user

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 455（286d4ac488bdcd446ffc）

**题面：** Set up a new GitLab group with internal visibility that can only be seen by logged-in users

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 456（35c44498db3696d519d2）

**题面：** Create a top-level internal GitLab group with the custom URL path "local-training-internal-group".

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 457（8c9eba264b7695102806）

**题面：** Learn about Keycloak test development

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 458（290638fcb182c6960f48）

**题面：** Navigate to the Edit page on OpenStreetMap.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 459（325c3e9af6cf020c8d7f）

**题面：** View GPS traces uploaded by users

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 460（5ffe7246e3cf8cfd922f）

**题面：** Navigate to the upload page to add a new GPS trace to OpenStreetMap.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 461（9d2a902babb8a46d7af8）

**题面：** View all GPS traces in the system.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 462（d633bb692c21fc64b3d2）

**题面：** Check user-contributed GPS traces

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 463（dde1229f74de8eaff67e）

**题面：** Browse user diaries to see contributors' experiences

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 464（50bdd7670ad731020527）

**题面：** Access User Diaries to read contributions.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 465（6586691f6d521f734fb0）

**题面：** Go to User Diaries to read about mapping activities from the community.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 466（7903acb30399bd5c8e05）

**题面：** View GPS traces from the GPS Traces page.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 467（80e2c362bab0c0442d21）

**题面：** Navigate to the OpenStreetMap homepage to view and explore maps

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 468（023a2fa510545850eb60）

**题面：** Navigate to the DASHBOARD section of the admin panel.
Local completion requirement: Finish on the Dashboard management page itself, with its heading visible. A different subpage or an open global menu alone is not sufficient.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 469（0f020cbe715ac4a4d3ee）

**题面：** View and manage the Newsletter Queue for scheduled newsletters.
Local completion requirement: Finish on the Newsletter Queue management page itself, with its heading visible. A different subpage or an open global menu alone is not sufficient.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 470（0fb31150596e043a7b65）

**题面：** Access the Transactions page to view payment processing history.
Local completion requirement: Finish on the Transactions management page itself, with its heading visible. A different subpage or an open global menu alone is not sufficient.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 471（1504f933385d5875e433）

**题面：** Navigate to create a new order.
Local completion requirement: Finish on the New Order management page itself, with its heading visible. A different subpage or an open global menu alone is not sufficient.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 472（1f384c086d7233075fd8）

**题面：** Manage Billing Agreements.
Local completion requirement: Finish on the Billing Agreements management page itself, with its heading visible. A different subpage or an open global menu alone is not sufficient.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 473（210145e7cb201110773f）

**题面：** Review the Login as Customer Log to see customer impersonation history
Local completion requirement: Finish on the Login as Customer Log management page itself, with its heading visible. A different subpage or an open global menu alone is not sufficient.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 474（219d5b7acca30aefac53）

**题面：** Go to the Invoices section to manage store invoices
Local completion requirement: Finish on the Invoices management page itself, with its heading visible. A different subpage or an open global menu alone is not sufficient.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 475（317565140066c12a9fd1）

**题面：** Go to the Widgets section to manage dynamic content elements
Local completion requirement: Finish on the Widgets management page itself, with its heading visible. A different subpage or an open global menu alone is not sufficient.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 476（55845d3547aea21f1201）

**题面：** Navigate to the Billing Agreements page from the credit memo view
Local completion requirement: Finish on the Billing Agreements management page itself, with its heading visible. A different subpage or an open global menu alone is not sufficient.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 477（5d4873df89f5e36118a2）

**题面：** Navigate to the Notifications page to check system messages in the Magento Admin panel.
Local completion requirement: Finish on the Notifications management page itself, with its heading visible. A different subpage or an open global menu alone is not sufficient.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 478（60075b8f15e63a1dc247）

**题面：** Go to the Categories section to organize the product catalog structure.
Local completion requirement: Finish on the Categories management page itself, with its heading visible. A different subpage or an open global menu alone is not sufficient.For Categories, finish in the existing-category management view, with an existing category selected; do not finish on a new-category form.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 479（63913433d3077454369f）

**题面：** Check transaction history in the Transactions section
Local completion requirement: Finish on the Transactions management page itself, with its heading visible. A different subpage or an open global menu alone is not sufficient.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 480（66a8efa568e2eec512cb）

**题面：** Check billing agreements with payment processors
Local completion requirement: Finish on the Billing Agreements management page itself, with its heading visible. A different subpage or an open global menu alone is not sufficient.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 481（73b9d165f08c9d60698f）

**题面：** View and manage Orders.
Local completion requirement: Finish on the Orders management page itself, with its heading visible. A different subpage or an open global menu alone is not sufficient.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 482（81c82aa9b0a3609817b8）

**题面：** Go to the Categories management page
Local completion requirement: Finish on the Categories management page itself, with its heading visible. A different subpage or an open global menu alone is not sufficient.For Categories, finish in the existing-category management view, with an existing category selected; do not finish on a new-category form.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 483（85fdcdfa1a439c09c824）

**题面：** Navigate to the All Customers page to view and manage customer accounts.
Local completion requirement: Finish on the All Customers management page itself, with its heading visible. A different subpage or an open global menu alone is not sufficient.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 484（93942ab445a0cf91d79e）

**题面：** Go to the Categories section to organize the product catalog
Local completion requirement: Finish on the Categories management page itself, with its heading visible. A different subpage or an open global menu alone is not sufficient.For Categories, finish in the existing-category management view, with an existing category selected; do not finish on a new-category form.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 485（a64a27ddf43d3a630c48）

**题面：** View Search Terms
Local completion requirement: Finish on the Search Terms management page itself, with its heading visible. A different subpage or an open global menu alone is not sufficient.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 486（a89ded491febf7ffc3d3）

**题面：** Open the Configuration page under Stores.
Local completion requirement: Finish on the Configuration management page itself, with its heading visible. A different subpage or an open global menu alone is not sufficient.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 487（aacb0cf0ec9097d39768）

**题面：** Click the "Create New Order" button to initiate a new sales order.
Local completion requirement: Finish on the New Order management page itself, with its heading visible. A different subpage or an open global menu alone is not sufficient.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 488（b651665d4200ca9ebc50）

**题面：** Manage customer groups in the Customer Groups section
Local completion requirement: Finish on the Customer Groups management page itself, with its heading visible. A different subpage or an open global menu alone is not sufficient.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 489（c3c17bbe2a53f17dd65e）

**题面：** Navigate to the Orders page to view all customer orders
Local completion requirement: Finish on the Orders management page itself, with its heading visible. A different subpage or an open global menu alone is not sufficient.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 490（c40a2de539a9df0228a8）

**题面：** View the Design Schedule for planned theme changes.
Local completion requirement: Finish on the Design Schedule management page itself, with its heading visible. A different subpage or an open global menu alone is not sufficient.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 491（c918aa067d6ff2e8dcbf）

**题面：** Go to the Invoices section to manage billing documents.
Local completion requirement: Finish on the Invoices management page itself, with its heading visible. A different subpage or an open global menu alone is not sufficient.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 492（c9acc533c08f3ef98eb2）

**题面：** Navigate to the Products page to manage store products and inventory.
Local completion requirement: Finish on the Products management page itself, with its heading visible. A different subpage or an open global menu alone is not sufficient.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 493（d7c3acc1e325e037b235）

**题面：** Open the native Order Count Report in Customers reports. No numerical answer or date-range customization is required for this local training variant.
Local completion requirement: Finish on the Order Count Report management page itself, with its heading visible. A different subpage or an open global menu alone is not sufficient.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 494（dd96d116c1dbb641e13a）

**题面：** Navigate to the Customer Groups page to manage customer categories and tax classes.
Local completion requirement: Finish on the Customer Groups management page itself, with its heading visible. A different subpage or an open global menu alone is not sufficient.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 495（e6f68ee329b1294b8a3f）

**题面：** Navigate to the notifications page to check system alerts.
Local completion requirement: Finish on the Notifications management page itself, with its heading visible. A different subpage or an open global menu alone is not sufficient.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 496（ef161ad432f390ac315c）

**题面：** View Product Reviews report.
Local completion requirement: Finish on the Product Reviews Report management page itself, with its heading visible. A different subpage or an open global menu alone is not sufficient.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。

## 题目 497（fd8855036a41db3107f3）

**题面：** Access the Media Gallery to manage website images and media files
Local completion requirement: Finish on the Media Gallery management page itself, with its heading visible. A different subpage or an open global menu alone is not sufficient.

**判断器的判定条件：** 原分支 `未记录`；原判定器完整业务条件见 native_contract

**原有前提/限制：** 原 contract 中的有效性、schema 与保持条件。

**目前的评分准则：** 二值：满足原判定器全部业务条件记 1，否则记 0；原有有效性/身份/保持条件作为前提；证据不足或 unknown 保持 null。
