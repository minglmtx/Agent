# 1983 题 gate 细分准则（语义组）

> 口径：每道题 = 一组 gate（G1..Gn），每条独立判对错；分值由下游按通过条数计算，本文不掺分值。
> 一条 gate = 一个语义组；隐含前提不占 gate 分数。仅保留硬门槛，丢弃过程质量。

## 01491075d7002a532057
- **题面：** Find the SKU number for the Pre-baked Gingerbread House Kit
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【SKU】字段 sku（SKU）与参考值精确一致

## 01dbfb254303d2f08ae8
- **题面：** Search for credit memos by customer name "Veronica Costello"
- **分支：** admin_contract_rules.checks:collection_query（源：binary）
- **隐含前提（不占分）：** 终页属于原本地部署；终页未被标记为登录页/错误页；相关记录保持未变；答案格式符合 schema
  - G1 【过滤条件】搜索/过滤条件与题面一致（未放宽、未误用）
  - G2 【结果集精确】结果集完整精确：无遗漏、无多余、无重复（exact_result_set）

## 030ab9a939137f3487c0
- **题面：** Find out how many projects you have starred
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【star 项目数】字段 starred_project_count（star 项目数）与参考值精确一致

## 03d66d95ff83bd2b6c60
- **题面：** Retrieve the price of the Pre-baked Gingerbread House Kit Value Pack.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【价格】字段 price（价格）与参考值精确一致

## 04d41f77320aa450ac93
- **题面：** Configure inventory settings to enable backorders for the Eco-Friendly Water Bottle
- **分支：** admin_contract_rules.checks:update（源：binary）
- **隐含前提（不占分）：** 终页属于原本地部署；终页未被标记为登录页/错误页；目标以外的同实体记录保持未变
  - G1 【目标对象】操作对象为题面指定目标（产品/客户组/记录身份正确，非同名/新建替代）
  - G2 【目标值】目标字段最终值精确满足题面要求（persisted_requested_value / update_matches）
  - G3 【保存生效】赋值已持久保存并在保存后复查仍为目标值
  - G4 【未动无关项】目标以外的同实体记录/字段保持未变

## 05a4924068ed5d2957e5
- **题面：** See how many forks the MathJax project has
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【fork 数】字段 fork_count（fork 数）与参考值精确一致

## 05bf9124ac8251050b90
- **题面：** Apply multiple filters to find refunded credit memos for customer Veronica Costello
- **分支：** admin_contract_rules.checks:collection_query（源：binary）
- **隐含前提（不占分）：** 终页属于原本地部署；终页未被标记为登录页/错误页；相关记录保持未变；答案格式符合 schema
  - G1 【过滤条件】搜索/过滤条件与题面一致（未放宽、未误用）
  - G2 【结果集精确】结果集完整精确：无遗漏、无多余、无重复（exact_result_set）

## 06c83311b1a750c09b79
- **题面：** Find out which forum has the most submissions
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【版块名】字段 forum_name（版块名）与参考值精确一致

## 09e3cfe5f478c386a220
- **题面：** Who submitted the article titled “I built a “sentence to playlist” AI capable of turning your playlist ideas into a real playlist in a matter of seconds!”
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【作者】字段 author（作者）与参考值精确一致

## 0a8f3325b194a807f848
- **题面：** Get the number of comments on the article "Cindy Williams Dies: ‘Laverne &amp; Shirley‘ Star Who Appeared In ’American Graffiti’ &amp; ‘The Conversation’ Was 75"
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【评论数】字段 comment_count（评论数）与参考值精确一致

## 0c0195ce97a7d83dc247
- **题面：** Check who is the manufacturer of the Gingerbread House Kit.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【制造商】字段 manufacturer（制造商）与参考值精确一致

## 0c7e5b3b68c71acc9776
- **题面：** Set the tax class of Yoga Mat Pro to None and save.
- **分支：** admin_contract_rules.checks:update（源：binary）
- **隐含前提（不占分）：** 终页属于原本地部署；终页未被标记为登录页/错误页；目标以外的同实体记录保持未变
  - G1 【目标对象】操作对象为题面指定目标（产品/客户组/记录身份正确，非同名/新建替代）
  - G2 【目标值】目标字段最终值精确满足题面要求（persisted_requested_value / update_matches）
  - G3 【保存生效】赋值已持久保存并在保存后复查仍为目标值
  - G4 【未动无关项】目标以外的同实体记录/字段保持未变

## 0ccd1578f5f6ddc7b11c
- **题面：** Change the tax class of the customer group Updated General Customers to Retail Customer and save the group.
- **分支：** admin_contract_rules.checks:update（源：binary）
- **隐含前提（不占分）：** 终页属于原本地部署；终页未被标记为登录页/错误页；目标以外的同实体记录保持未变
  - G1 【目标对象】操作对象为题面指定目标（产品/客户组/记录身份正确，非同名/新建替代）
  - G2 【目标值】目标字段最终值精确满足题面要求（persisted_requested_value / update_matches）
  - G3 【保存生效】赋值已持久保存并在保存后复查仍为目标值
  - G4 【未动无关项】目标以外的同实体记录/字段保持未变

## 0d32373dbf056a7cb733
- **题面：** Retrieve the number of submissions for the television forum.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【提交数】字段 submission_count（提交数）与参考值精确一致

## 0e67c52509e468a02665
- **题面：** Find all female customers with birthdays in January
- **分支：** admin_contract_rules.checks:collection_query（源：binary）
- **隐含前提（不占分）：** 终页属于原本地部署；终页未被标记为登录页/错误页；相关记录保持未变；答案格式符合 schema
  - G1 【过滤条件】搜索/过滤条件与题面一致（未放宽、未误用）
  - G2 【结果集精确】结果集完整精确：无遗漏、无多余、无重复（exact_result_set）

## 0e7d0cf05895d7d5e746
- **题面：** What is the overall rating of the Pre-baked Gingerbread House Kit Value Pack?
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【评分】字段 rating_percent（评分）与参考值精确一致

## 0f2ae6c1ef83ad23962a
- **题面：** Set up a special price promotion for the Yoga Mat Pro
- **分支：** admin_contract_rules.checks:update（源：binary）
- **隐含前提（不占分）：** 终页属于原本地部署；终页未被标记为登录页/错误页；目标以外的同实体记录保持未变
  - G1 【目标对象】操作对象为题面指定目标（产品/客户组/记录身份正确，非同名/新建替代）
  - G2 【目标值】目标字段最终值精确满足题面要求（persisted_requested_value / update_matches）
  - G3 【保存生效】赋值已持久保存并在保存后复查仍为目标值
  - G4 【未动无关项】目标以外的同实体记录/字段保持未变

## 11e24e5efefea43a6a1e
- **题面：** Cancel the selected order. For this local training variant, the selected order is #000000301.
- **分支：** admin_contract_rules.checks:update（源：binary）
- **隐含前提（不占分）：** 终页属于原本地部署；终页未被标记为登录页/错误页；目标以外的同实体记录保持未变
  - G1 【目标对象】操作对象为题面指定目标（产品/客户组/记录身份正确，非同名/新建替代）
  - G2 【目标值】目标字段最终值精确满足题面要求（persisted_requested_value / update_matches）
  - G3 【保存生效】赋值已持久保存并在保存后复查仍为目标值
  - G4 【未动无关项】目标以外的同实体记录/字段保持未变

## 15563156f55a18d63ec0
- **题面：** Find out when the post about "Gregory Allen Howard" was submitted
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【提交日期】字段 submission_date（提交日期）与参考值精确一致

## 162eecfe220af06b700f
- **题面：** View the license type for the a11y-syntax-highlighting project.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【许可证类型】字段 license_type（许可证类型）与参考值精确一致

## 170349164ca41b627be8
- **题面：** Exclude Main Website from the Updated General Customers group, and save.
- **分支：** admin_contract_rules.checks:update（源：binary）
- **隐含前提（不占分）：** 终页属于原本地部署；终页未被标记为登录页/错误页；目标以外的同实体记录保持未变
  - G1 【目标对象】操作对象为题面指定目标（产品/客户组/记录身份正确，非同名/新建替代）
  - G2 【目标值】目标字段最终值精确满足题面要求（persisted_requested_value / update_matches）
  - G3 【保存生效】赋值已持久保存并在保存后复查仍为目标值
  - G4 【未动无关项】目标以外的同实体记录/字段保持未变

## 1743b9363cdbd904475a
- **题面：** Identify the storage size used by the a11y-syntax-highlighting project.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【存储大小】字段 storage_size（存储大小）与参考值精确一致

## 17c277148ce43e3c80e1
- **题面：** Check the price of the Pre-baked Gingerbread House Kit Value Pack.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【价格】字段 price（价格）与参考值精确一致

## 17d5e276fde02bf2afde
- **题面：** Remove the exclusion of Main Website for the Updated General Customers group, and save.
- **分支：** admin_contract_rules.checks:update（源：binary）
- **隐含前提（不占分）：** 终页属于原本地部署；终页未被标记为登录页/错误页；目标以外的同实体记录保持未变
  - G1 【目标对象】操作对象为题面指定目标（产品/客户组/记录身份正确，非同名/新建替代）
  - G2 【目标值】目标字段最终值精确满足题面要求（persisted_requested_value / update_matches）
  - G3 【保存生效】赋值已持久保存并在保存后复查仍为目标值
  - G4 【未动无关项】目标以外的同实体记录/字段保持未变

## 18b4411f46e0c135a395
- **题面：** Check when the autojump project was last updated
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【更新日期】字段 updated_date（更新日期）与参考值精确一致

## 19b39dd61c696035ce37
- **题面：** Hold the selected order. For this local training variant, the selected order is #000000301.
- **分支：** admin_contract_rules.checks:update（源：binary）
- **隐含前提（不占分）：** 终页属于原本地部署；终页未被标记为登录页/错误页；目标以外的同实体记录保持未变
  - G1 【目标对象】操作对象为题面指定目标（产品/客户组/记录身份正确，非同名/新建替代）
  - G2 【目标值】目标字段最终值精确满足题面要求（persisted_requested_value / update_matches）
  - G3 【保存生效】赋值已持久保存并在保存后复查仍为目标值
  - G4 【未动无关项】目标以外的同实体记录/字段保持未变

## 1beff0bc05a517207f6a
- **题面：** View the total number of submissions in the relationship_advice forum
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【提交数】字段 submission_count（提交数）与参考值精确一致

## 1c3c050ec5ad45313ecf
- **题面：** Find out if there are any subscribers to the movies forum
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【是否有订阅者】字段 has_subscribers（是否有订阅者）与参考值精确一致

## 1c6b231f1fb372bb206d
- **题面：** Check the price of the "Mineralogie All Natural Lip Gloss, Ruby Rose" product.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【价格】字段 price（价格）与参考值精确一致

## 20ab1fb9f2d8a7878c12
- **题面：** Identify the most recent project update date on the dashboard.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【更新日期】字段 updated_date（更新日期）与参考值精确一致

## 210e2c5cf187dea57672
- **题面：** See how many merge requests are open in the Byte Blaze / empathy-prompts project.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【打开的合并请求数】字段 open_merge_request_count（打开的合并请求数）与参考值精确一致

## 22af52ab1c27d176f62c
- **题面：** Count how many vegan products are available based on the search results
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【数量】字段 count（数量）与参考值精确一致

## 232a5983ed3010501724
- **题面：** Set the tax class of Blue T-Shirt to None and save.
- **分支：** admin_contract_rules.checks:update（源：binary）
- **隐含前提（不占分）：** 终页属于原本地部署；终页未被标记为登录页/错误页；目标以外的同实体记录保持未变
  - G1 【目标对象】操作对象为题面指定目标（产品/客户组/记录身份正确，非同名/新建替代）
  - G2 【目标值】目标字段最终值精确满足题面要求（persisted_requested_value / update_matches）
  - G3 【保存生效】赋值已持久保存并在保存后复查仍为目标值
  - G4 【未动无关项】目标以外的同实体记录/字段保持未变

## 23749feecb47697d2c74
- **题面：** On the local movies forum, find the post titled "THE DARK CRYSTAL Is Returning To Theaters In Celebration of 40th Anniversary! - Icon Vs. Icon" and report its exact title and submitting username. Use the local post metadata; opening or summarizing the external publisher article is not requested.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【标题】字段 title（标题）与参考值精确一致

## 24bbc21e497fc7e6386f
- **题面：** Retrieve the number of submissions for the memes forum.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【提交数】字段 submission_count（提交数）与参考值精确一致

## 25f8c0d4acb198c76444
- **题面：** View the status of order 000000188, whose total is $2,004.99.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【订单状态】字段 order_status（订单状态）与参考值精确一致

## 275d2224448d1c011649
- **题面：** Check when the 1.0.0 version was released
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【发布日期】字段 released_date（发布日期）与参考值精确一致

## 2802ed12abe1bb11f5a4
- **题面：** Find out who manufactures the Pre-baked Gingerbread House Kit Value Pack
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【制造商】字段 manufacturer（制造商）与参考值精确一致

## 2bf4131ca3f524bf5b2e
- **题面：** Assign the new product "Sony Headphones" to the category "Electronics".
- **分支：** admin_contract_rules.checks:update（源：binary）
- **隐含前提（不占分）：** 终页属于原本地部署；终页未被标记为登录页/错误页；目标以外的同实体记录保持未变
  - G1 【目标对象】操作对象为题面指定目标（产品/客户组/记录身份正确，非同名/新建替代）
  - G2 【目标值】目标字段最终值精确满足题面要求（persisted_requested_value / update_matches）
  - G3 【保存生效】赋值已持久保存并在保存后复查仍为目标值
  - G4 【未动无关项】目标以外的同实体记录/字段保持未变

## 2c4b678cfc6978ab9182
- **题面：** Find out when Jane Doe created her customer account For this local training variant, the target account email is jane.doe@gmail.com.
- **分支：** admin_contract_rules.checks:query（源：binary）
- **隐含前提（不占分）：** 终页属于原本地部署；终页未被标记为登录页/错误页；相关记录保持未变；答案格式符合 schema
  - G1 【创建时间】字段 created_at（创建时间）与参考值精确一致

## 2c61c04a55f42336851b
- **题面：** Find the post with the most comments on the current AskReddit page
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【标题】字段 title（标题）与参考值精确一致

## 2e1b70fe70aa84c9809d
- **题面：** Check how many issues are open for the a11yproject.com project.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【open issue 数】字段 open_issue_count（open issue 数）与参考值精确一致

## 2ebfec43e8215c9a172c
- **题面：** Find out how to contact One Stop Market customer service
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【联系表单链接】字段 contact_form_url（联系表单链接）与参考值精确一致

## 2fa6f09b1f19cd91fe9c
- **题面：** Find out when the project Byte Blaze / a11y-syntax-highlighting was last updated.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【更新日期】字段 updated_date（更新日期）与参考值精确一致

## 322038f10d4a08220ad3
- **题面：** Change the tax class of the customer group Updated General Customers to Wholesale Customer and save the group.
- **分支：** admin_contract_rules.checks:update（源：binary）
- **隐含前提（不占分）：** 终页属于原本地部署；终页未被标记为登录页/错误页；目标以外的同实体记录保持未变
  - G1 【目标对象】操作对象为题面指定目标（产品/客户组/记录身份正确，非同名/新建替代）
  - G2 【目标值】目标字段最终值精确满足题面要求（persisted_requested_value / update_matches）
  - G3 【保存生效】赋值已持久保存并在保存后复查仍为目标值
  - G4 【未动无关项】目标以外的同实体记录/字段保持未变

## 331ea9c6f7b545d516de
- **题面：** Check how many issues are open on the project thoughtbot, inc. / administrate.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【open issue 数】字段 open_issue_count（open issue 数）与参考值精确一致

## 36450a47ea9635c40045
- **题面：** Retrieve the price of the Nightfox Vulpes Handheld Digital Night Vision Goggles.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【价格】字段 price（价格）与参考值精确一致

## 3645416e63ddda135f29
- **题面：** Find the most recent customer registration date
- **分支：** admin_contract_rules.checks:query（源：binary）
- **隐含前提（不占分）：** 终页属于原本地部署；终页未被标记为登录页/错误页；相关记录保持未变；答案格式符合 schema
  - G1 【创建时间】字段 created_at（创建时间）与参考值精确一致

## 3934afdec1f314316da4
- **题面：** Check the SKU number of the Pre-baked Gingerbread House Kit Value Pack
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【SKU】字段 sku（SKU）与参考值精确一致

## 394010495e00e016fe24
- **题面：** Check the scale of the current map view
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【正确结果】返回题面要求的正确结果（值/目标与参考一致）

## 3a54d442798dc2c3ad83
- **题面：** Change the inventory quantity of the Hera Pullover Hoodie-XS-Blue to 150 units
- **分支：** admin_contract_rules.checks:update（源：binary）
- **隐含前提（不占分）：** 终页属于原本地部署；终页未被标记为登录页/错误页；目标以外的同实体记录保持未变
  - G1 【目标对象】操作对象为题面指定目标（产品/客户组/记录身份正确，非同名/新建替代）
  - G2 【目标值】目标字段最终值精确满足题面要求（persisted_requested_value / update_matches）
  - G3 【保存生效】赋值已持久保存并在保存后复查仍为目标值
  - G4 【未动无关项】目标以外的同实体记录/字段保持未变

## 3a96fe846ef551e1b692
- **题面：** Check whether gamingpro456@gmail.com is registered. Return the matching registered email as an item, or an empty items list if it is not registered.
- **分支：** admin_contract_rules.checks:collection_query（源：binary）
- **隐含前提（不占分）：** 终页属于原本地部署；终页未被标记为登录页/错误页；相关记录保持未变；答案格式符合 schema
  - G1 【过滤条件】搜索/过滤条件与题面一致（未放宽、未误用）
  - G2 【结果集精确】结果集完整精确：无遗漏、无多余、无重复（exact_result_set）

## 3b0bc1fa93e1285754a7
- **题面：** Find out when the Super-SloMo repository was last updated
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【更新日期】字段 updated_date（更新日期）与参考值精确一致

## 3b51c7012090fd5e495b
- **题面：** Check which customer group Adam Garcia belongs to For this local training variant, the target account email is adam.garcia@gmail.com.
- **分支：** admin_contract_rules.checks:query（源：binary）
- **隐含前提（不占分）：** 终页属于原本地部署；终页未被标记为登录页/错误页；相关记录保持未变；答案格式符合 schema
  - G1 【组名】字段 group_name（组名）与参考值精确一致

## 3c7b4db3d03b67efca2b
- **题面：** Check if Emma Lopez is subscribed to the newsletter.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【订阅状态】字段 subscription_status（订阅状态）与参考值精确一致

## 3d80812ae97396311085
- **题面：** Check if the main wiki page exists.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【存在性】字段 exists（存在性）与参考值精确一致

## 3e22ddce719a377a4c62
- **题面：** Search for customer details using the keyword "Veronica Costello".
- **分支：** admin_contract_rules.checks:collection_query（源：binary）
- **隐含前提（不占分）：** 终页属于原本地部署；终页未被标记为登录页/错误页；相关记录保持未变；答案格式符合 schema
  - G1 【过滤条件】搜索/过滤条件与题面一致（未放宽、未误用）
  - G2 【结果集精确】结果集完整精确：无遗漏、无多余、无重复（exact_result_set）

## 3e58d846a3d9e983aacd
- **题面：** Set the Country of Manufacture for the Yoga Mat Pro to "United States"
- **分支：** admin_contract_rules.checks:update（源：binary）
- **隐含前提（不占分）：** 终页属于原本地部署；终页未被标记为登录页/错误页；目标以外的同实体记录保持未变
  - G1 【目标对象】操作对象为题面指定目标（产品/客户组/记录身份正确，非同名/新建替代）
  - G2 【目标值】目标字段最终值精确满足题面要求（persisted_requested_value / update_matches）
  - G3 【保存生效】赋值已持久保存并在保存后复查仍为目标值
  - G4 【未动无关项】目标以外的同实体记录/字段保持未变

## 3f5222e07879c45f56d0
- **题面：** Unhold the selected order. For this local training variant, the selected order is #000000301.
- **分支：** admin_contract_rules.checks:update（源：binary）
- **隐含前提（不占分）：** 终页属于原本地部署；终页未被标记为登录页/错误页；目标以外的同实体记录保持未变
  - G1 【目标对象】操作对象为题面指定目标（产品/客户组/记录身份正确，非同名/新建替代）
  - G2 【目标值】目标字段最终值精确满足题面要求（persisted_requested_value / update_matches）
  - G3 【保存生效】赋值已持久保存并在保存后复查仍为目标值
  - G4 【未动无关项】目标以外的同实体记录/字段保持未变

## 411514c1c37d67746116
- **题面：** For this local training variant, change Adam Garcia’s first name to Adam Updated and save. For this local training variant, the target account email is adam.garcia@gmail.com.
- **分支：** admin_contract_rules.checks:update（源：binary）
- **隐含前提（不占分）：** 终页属于原本地部署；终页未被标记为登录页/错误页；目标以外的同实体记录保持未变
  - G1 【目标对象】操作对象为题面指定目标（产品/客户组/记录身份正确，非同名/新建替代）
  - G2 【目标值】目标字段最终值精确满足题面要求（persisted_requested_value / update_matches）
  - G3 【保存生效】赋值已持久保存并在保存后复查仍为目标值
  - G4 【未动无关项】目标以外的同实体记录/字段保持未变

## 41dedbdeb66536b8d8d1
- **题面：** Check the stock status of the Pre-baked Gingerbread House Kit Value Pack.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【库存状态】字段 stock_status（库存状态）与参考值精确一致

## 4247576686e176dea583
- **题面：** Find out what materials the Nightfox Vulpes Night Vision Goggles are made of.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【材质】字段 material（材质）与参考值精确一致

## 426281fcea06f8c62a26
- **题面：** Count pending to-dos related to the Byte Blaze / a11y-webring.club project.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【待办数】字段 todo_count（待办数）与参考值精确一致

## 42c114bf04c61fd15ad1
- **题面：** Retrieve the title and number of comments for the post "You win $1B but in exchange you can never use social media again, are you interested what would you do?"
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【标题】字段 title（标题）与参考值精确一致

## 45ffd6778b9d863ba9ca
- **题面：** Check the price of the Custom Jersey Style St Patricks Day T-Shirt
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【价格】字段 price（价格）与参考值精确一致

## 46202d04304eac1719ed
- **题面：** What is the submission date for the article about D.H Peligro, drummer of punk band Dead Kennedys, passing away?
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【提交日期】字段 submission_date（提交日期）与参考值精确一致

## 485486b9f7dfb1584bb6
- **题面：** For this local training task, select order #000000002 and download its existing training shipping label as a PDF. The fixed label is for simulation only and is not valid for postage. Do not purchase or generate a live carrier label.
- **分支：** admin_contract_rules.checks:pdf（源：binary）
  - G1 【下载产物】下载产物内容与选中对象集合正确匹配
  - G2 【未生成真实标签】未生成/购买真实承运标签（若题面禁止）

## 49c5b0402a3d521509dd
- **题面：** Check if the Nightfox Vulpes Night Vision Goggles are in stock.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【库存状态】字段 stock_status（库存状态）与参考值精确一致

## 4a9824d5f9d587cc9c6c
- **题面：** Set up cross-sell products for Example Product Deluxe 2023
- **分支：** admin_contract_rules.checks:links（源：binary）
  - G1 【结果精确】查询结果与参考精确一致

## 4c258f420fd1dbddf2e2
- **题面：** Count the number of stars for the Mozilla Festival project.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【star 数】字段 star_count（star 数）与参考值精确一致

## 4c44ebe0f2c8fd9f35a3
- **题面：** Update the price of the "Test Product" to $39.99
- **分支：** admin_contract_rules.checks:update（源：binary）
- **隐含前提（不占分）：** 终页属于原本地部署；终页未被标记为登录页/错误页；目标以外的同实体记录保持未变
  - G1 【目标对象】操作对象为题面指定目标（产品/客户组/记录身份正确，非同名/新建替代）
  - G2 【目标值】目标字段最终值精确满足题面要求（persisted_requested_value / update_matches）
  - G3 【保存生效】赋值已持久保存并在保存后复查仍为目标值
  - G4 【未动无关项】目标以外的同实体记录/字段保持未变

## 4fc71d425d26b849cdaa
- **题面：** Access the Advanced Pricing settings for the Blue T-Shirt and update the special price.
- **分支：** admin_contract_rules.checks:update（源：binary）
- **隐含前提（不占分）：** 终页属于原本地部署；终页未被标记为登录页/错误页；目标以外的同实体记录保持未变
  - G1 【目标对象】操作对象为题面指定目标（产品/客户组/记录身份正确，非同名/新建替代）
  - G2 【目标值】目标字段最终值精确满足题面要求（persisted_requested_value / update_matches）
  - G3 【保存生效】赋值已持久保存并在保存后复查仍为目标值
  - G4 【未动无关项】目标以外的同实体记录/字段保持未变

## 4fcb5d49a6794c46e8e8
- **题面：** Check what magnification the Nightfox Vulpes Night Vision Goggles offer.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【放大倍数】字段 magnification（放大倍数）与参考值精确一致

## 5251c3c73aebfe0cd9c6
- **题面：** List the number of stars for the project The A11Y Project / a11yproject.com.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【star 数】字段 star_count（star 数）与参考值精确一致

## 53a975104f8bf03a7d4a
- **题面：** Check what tax classes are available for customer groups.
- **分支：** admin_contract_rules.checks:collection_query（源：binary）
- **隐含前提（不占分）：** 终页属于原本地部署；终页未被标记为登录页/错误页；相关记录保持未变；答案格式符合 schema
  - G1 【过滤条件】搜索/过滤条件与题面一致（未放宽、未误用）
  - G2 【结果集精确】结果集完整精确：无遗漏、无多余、无重复（exact_result_set）

## 53c55b37cb86a07f3f21
- **题面：** Change the tax class of the customer group Updated General Customers to Wholesale Customer and save the group.
- **分支：** admin_contract_rules.checks:update（源：binary）
- **隐含前提（不占分）：** 终页属于原本地部署；终页未被标记为登录页/错误页；目标以外的同实体记录保持未变
  - G1 【目标对象】操作对象为题面指定目标（产品/客户组/记录身份正确，非同名/新建替代）
  - G2 【目标值】目标字段最终值精确满足题面要求（persisted_requested_value / update_matches）
  - G3 【保存生效】赋值已持久保存并在保存后复查仍为目标值
  - G4 【未动无关项】目标以外的同实体记录/字段保持未变

## 55d3114f967d54b51fda
- **题面：** Find the username of the person who submitted the post about Nosferatu at 100 years
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【作者】字段 author（作者）与参考值精确一致

## 55d84e6be0f0c0f44d8f
- **题面：** Find the distance scale for the current map view
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【正确结果】返回题面要求的正确结果（值/目标与参考一致）

## 56b82251a17e22440ef4
- **题面：** How many comments are there on the article about Brian May receiving a knighthood?
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【评论数】字段 comment_count（评论数）与参考值精确一致

## 582b5ef57b87b952b392
- **题面：** Find the most recent closure or merge time among currently closed or merged merge requests in byteblaze/a11y-syntax-highlighting. Return completed_at in UTC as YYYY-MM-DDTHH:MMZ, discarding seconds. Return none if neither collection contains a request.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【完成时间】字段 completed_at（完成时间）与参考值精确一致

## 58a4e4a4b7fbb2662b2d
- **题面：** Update the stock status for the Maya Tunic product. Save a native stock status different from the initial saved status; either In Stock or Out of Stock is allowed.
- **分支：** admin_contract_rules.checks:update（源：binary）
- **隐含前提（不占分）：** 终页属于原本地部署；终页未被标记为登录页/错误页；目标以外的同实体记录保持未变
  - G1 【目标对象】操作对象为题面指定目标（产品/客户组/记录身份正确，非同名/新建替代）
  - G2 【目标值】目标字段最终值精确满足题面要求（persisted_requested_value / update_matches）
  - G3 【保存生效】赋值已持久保存并在保存后复查仍为目标值
  - G4 【未动无关项】目标以外的同实体记录/字段保持未变

## 59980d9d5249b017145a
- **题面：** Find out when the gumble project was last updated
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【更新日期】字段 updated_date（更新日期）与参考值精确一致

## 5a5d552d30462f36409c
- **题面：** See how many issues across all statuses are assigned to me in the Byte Blaze / empathy-prompts project.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【数量】字段 count（数量）与参考值精确一致

## 5acb0a9a8cbbaa7e1ddd
- **题面：** View the subcategories under the "New Category Name" category
- **分支：** admin_contract_rules.checks:collection_query（源：binary）
- **隐含前提（不占分）：** 终页属于原本地部署；终页未被标记为登录页/错误页；相关记录保持未变；答案格式符合 schema
  - G1 【过滤条件】搜索/过滤条件与题面一致（未放宽、未误用）
  - G2 【结果集精确】结果集完整精确：无遗漏、无多余、无重复（exact_result_set）

## 5e356def10426fbef596
- **题面：** Set up cross-sell products for the Blue T-Shirt to increase cart value.
- **分支：** admin_contract_rules.checks:links（源：binary）
  - G1 【结果精确】查询结果与参考精确一致

## 605fa472c81c3d397dbb
- **题面：** Change the name of the Updated General Customers group to General Retail Customers
- **分支：** admin_contract_rules.checks:update（源：binary）
- **隐含前提（不占分）：** 终页属于原本地部署；终页未被标记为登录页/错误页；目标以外的同实体记录保持未变
  - G1 【目标对象】操作对象为题面指定目标（产品/客户组/记录身份正确，非同名/新建替代）
  - G2 【目标值】目标字段最终值精确满足题面要求（persisted_requested_value / update_matches）
  - G3 【保存生效】赋值已持久保存并在保存后复查仍为目标值
  - G4 【未动无关项】目标以外的同实体记录/字段保持未变

## 6096f93770d67474ee61
- **题面：** Check whether my current shopping cart qualifies for free shipping to my default saved address without changing the cart or address. Do not place an order.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【是否免运费】字段 free_shipping_available（是否免运费）与参考值精确一致

## 609abffc99ef4112c780
- **题面：** Check what routing engine is being used for the current directions.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【引擎】字段 engine（引擎）与参考值精确一致

## 61d16fff9c982ddf674f
- **题面：** Find the driving distance from New York City to Boston
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【距离】字段 distance_km（距离）与参考值精确一致

## 621e3a379562905e5595
- **题面：** For this local training variant, add Adam Garcia (adam.garcia@gmail.com), who currently has no subscriber record, to the newsletter subscribers. Use the existing customer account.
- **分支：** admin_contract_rules.checks:create（源：binary）
- **隐含前提（不占分）：** 终页属于原本地部署；终页未被标记为登录页/错误页；原有实体记录保持未变
  - G1 【目标对象】操作对象为题面指定目标（产品/客户组/记录身份正确，非同名/新建替代）
  - G2 【目标值】目标字段最终值精确满足题面要求（persisted_requested_value / update_matches）
  - G3 【保存生效】赋值已持久保存并在保存后复查仍为目标值
  - G4 【未动无关项】目标以外的同实体记录/字段保持未变

## 63148504db1e675ccf57
- **题面：** See how many issues are currently open in The A11Y Project repository
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【open issue 数】字段 open_issue_count（open issue 数）与参考值精确一致

## 673d15028cccb54d0690
- **题面：** Check which customers belong to the VIP Customers group
- **分支：** admin_contract_rules.checks:collection_query（源：binary）
- **隐含前提（不占分）：** 终页属于原本地部署；终页未被标记为登录页/错误页；相关记录保持未变；答案格式符合 schema
  - G1 【过滤条件】搜索/过滤条件与题面一致（未放宽、未误用）
  - G2 【结果集精确】结果集完整精确：无遗漏、无多余、无重复（exact_result_set）

## 67ace090b86bd67c69f0
- **题面：** Check if there are any open issues for the cloud-to-butt project
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【存在性】字段 exists（存在性）与参考值精确一致

## 6828a71bbb7c7f4f6a37
- **题面：** Check how many comments the post about "bleaching your butthole" has
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【评论数】字段 comment_count（评论数）与参考值精确一致

## 6a852616e68dfe6d2878
- **题面：** Get the quantity of NOZE Rustic Coat Rack Wall Mounted Shelf in the shopping cart.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【数量】字段 quantity（数量）与参考值精确一致

## 6d88148c5efc95914367
- **题面：** Save the currently displayed unsaved group-name change from Updated General Customers to Updated General Customers Saved.
- **分支：** admin_contract_rules.checks:update（源：binary）
- **隐含前提（不占分）：** 终页属于原本地部署；终页未被标记为登录页/错误页；目标以外的同实体记录保持未变
  - G1 【目标对象】操作对象为题面指定目标（产品/客户组/记录身份正确，非同名/新建替代）
  - G2 【目标值】目标字段最终值精确满足题面要求（persisted_requested_value / update_matches）
  - G3 【保存生效】赋值已持久保存并在保存后复查仍为目标值
  - G4 【未动无关项】目标以外的同实体记录/字段保持未变

## 6fe8b1378a01b3b210c6
- **题面：** Find the shipment with the highest total quantity on the shipments page.
- **分支：** admin_contract_rules.checks:query（源：binary）
  - G1 【结果精确】查询结果与参考精确一致

## 70306d401418877c8921
- **题面：** Identify which forum has the most subscribers
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【版块名】字段 forum_name（版块名）与参考值精确一致

## 727c233e307f925c0329
- **题面：** Check how many customer groups are available in the system
- **分支：** admin_contract_rules.checks:collection_query（源：binary）
- **隐含前提（不占分）：** 终页属于原本地部署；终页未被标记为登录页/错误页；相关记录保持未变；答案格式符合 schema
  - G1 【过滤条件】搜索/过滤条件与题面一致（未放宽、未误用）
  - G2 【结果集精确】结果集完整精确：无遗漏、无多余、无重复（exact_result_set）

## 748b3ecbeda6a6a10aa1
- **题面：** View the total cost of items in the shopping cart
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【商品小计】字段 items_subtotal（商品小计）与参考值精确一致

## 75b57e1ccf54de8f5ecb
- **题面：** Search for credit memos created in April 2023.
- **分支：** admin_contract_rules.checks:collection_query（源：binary）
- **隐含前提（不占分）：** 终页属于原本地部署；终页未被标记为登录页/错误页；相关记录保持未变；答案格式符合 schema
  - G1 【过滤条件】搜索/过滤条件与题面一致（未放宽、未误用）
  - G2 【结果集精确】结果集完整精确：无遗漏、无多余、无重复（exact_result_set）

## 77f7fe934bd24e280aa3
- **题面：** Find when the millennials-to-snake-people project was last updated
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【更新日期】字段 updated_date（更新日期）与参考值精确一致

## 78d05122d0a400a6272d
- **题面：** Check the number of items in the cart from the order summary.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【商品数】字段 item_count（商品数）与参考值精确一致

## 7a0199e38526591e656f
- **题面：** Report the name and SKU of Yoga Mat Pro.
- **分支：** admin_contract_rules.checks:query（源：binary）
  - G1 【名称】字段 name（名称）与参考值精确一致

## 7b0a04b077e4d9102163
- **题面：** Check how many starred projects I have
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【star 项目数】字段 starred_project_count（star 项目数）与参考值精确一致

## 7b224eb22f9dddeb6cf6
- **题面：** Calculate the driving distance between Utica and Albany, NY
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【距离】字段 distance_km（距离）与参考值精确一致

## 7cdb7893ed10cf4ba75a
- **题面：** Find the price of the 5x40 Night Vision Monocular Telescopes.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【价格】字段 price（价格）与参考值精确一致

## 7ed6122ce8c7f4646f43
- **题面：** View the map scale information at the current zoom level.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【正确结果】返回题面要求的正确结果（值/目标与参考一致）

## 7f1fe5a50297a970b8fe
- **题面：** Disable the Hera Pullover Hoodie-XL-Orange product
- **分支：** admin_contract_rules.checks:update（源：binary）
- **隐含前提（不占分）：** 终页属于原本地部署；终页未被标记为登录页/错误页；目标以外的同实体记录保持未变
  - G1 【目标对象】操作对象为题面指定目标（产品/客户组/记录身份正确，非同名/新建替代）
  - G2 【目标值】目标字段最终值精确满足题面要求（persisted_requested_value / update_matches）
  - G3 【保存生效】赋值已持久保存并在保存后复查仍为目标值
  - G4 【未动无关项】目标以外的同实体记录/字段保持未变

## 827c1feb3bf63a67873f
- **题面：** On the local Music forum, find the post titled "Portugal. The Man spotlights health care for Alaska Indigenous communities in new video" and report its exact title and submitting username. Use the local post metadata; opening or summarizing the external publisher article is not requested.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【标题】字段 title（标题）与参考值精确一致

## 8740532e91dbc3037815
- **题面：** Check the price of the "Posiflex MT4008 Point of Sale Tablet" product.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【价格】字段 price（价格）与参考值精确一致

## 874e41af76db85c47ce4
- **题面：** See when the joke "My grandfather warned people that the Titanic would sink" was posted
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【提交日期】字段 submission_date（提交日期）与参考值精确一致

## 89c78a04c5f2b1e693ac
- **题面：** Reset the displayed new customer group form to discard Unsaved Training Group without saving a group.
- **分支：** admin_contract_rules.checks:draft_reset（源：binary）
  - G1 【草稿重置】草稿状态重置为要求状态

## 8a66ed1a43e9687e2412
- **题面：** What is the price of the Pre-baked Gingerbread House Kit Value Pack?
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【价格】字段 price（价格）与参考值精确一致

## 8b7e1d9131362ea7a7f5
- **题面：** Find out how many comments the post about "What is the best way to remove a champagne bottle from your rectum?" has
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【评论数】字段 comment_count（评论数）与参考值精确一致

## 8c857e0111275f007585
- **题面：** Check the shipping cost for your current cart items.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【运费】字段 shipping_cost（运费）与参考值精确一致

## 8f217e01825b6f114391
- **题面：** Check the total number of merge requests across all statuses in the OpenAPI Generator project.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【合并请求总数】字段 all_merge_request_count（合并请求总数）与参考值精确一致

## 993478a7233e453bdbce
- **题面：** Check the estimated travel time for a car route from Times Square to JFK Airport
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【时长】字段 duration_minutes（时长）与参考值精确一致

## 9a9b75750d305ace38fa
- **题面：** Who submitted the article titled “Holy shit is “Tom’s Diner” by Suzanne Vega & DNA so godamn good.”
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【作者】字段 author（作者）与参考值精确一致

## 9cb0a2693df3645337ee
- **题面：** Check what payment methods are available for this purchase
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【支付方式】字段 payment_methods（支付方式）与参考值精确一致

## 9e08e0b6f78a10e5cb42
- **题面：** Calculate the walking distance between Central Park and Times Square
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【距离】字段 distance_km（距离）与参考值精确一致

## 9e246c9920d1c80ed596
- **题面：** Retrieve the number of submissions for the space forum.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【提交数】字段 submission_count（提交数）与参考值精确一致

## 9f561911da861969ad99
- **题面：** Find who assigned the pending to-do for the merge request "update or remove 404 links" in The A11Y Project / a11yproject.com.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【分配人】字段 assigned_by（分配人）与参考值精确一致

## 9fccdb70fc3f5cda6c49
- **题面：** Check the payable total for my current shopping cart, including shipping to my default saved address. Do not place the order.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【订单总额】字段 order_total（订单总额）与参考值精确一致

## a00fd4a97eb92a33c922
- **题面：** For this local training variant, associate Adam Garcia (adam.garcia@gmail.com) with Training Secondary Website using Associate to Website, and save.
- **分支：** admin_contract_rules.checks:update（源：binary）
- **隐含前提（不占分）：** 终页属于原本地部署；终页未被标记为登录页/错误页；目标以外的同实体记录保持未变
  - G1 【目标对象】操作对象为题面指定目标（产品/客户组/记录身份正确，非同名/新建替代）
  - G2 【目标值】目标字段最终值精确满足题面要求（persisted_requested_value / update_matches）
  - G3 【保存生效】赋值已持久保存并在保存后复查仍为目标值
  - G4 【未动无关项】目标以外的同实体记录/字段保持未变

## a07262b05d647d15927e
- **题面：** Check the customer rating for the ACPOTEL Night Vision Monocular.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【评分】字段 rating_percent（评分）与参考值精确一致

## a30dc8c6d713f134765f
- **题面：** View the rating percentage of the Nightfox Vulpes Handheld Digital Night Vision Goggles
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【评分】字段 rating_percent（评分）与参考值精确一致

## a5a2d922b189348cfa7f
- **题面：** Find the most active forum based on number of submissions
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【版块名】字段 forum_name（版块名）与参考值精确一致

## a748206690e0427ddd04
- **题面：** Check if the shipping method can be changed from Flat Rate - Fixed at this stage of checkout
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【是否有替代配送】字段 alternative_shipping_available（是否有替代配送）与参考值精确一致

## a8af28f0b01292514ad0
- **题面：** Find out when the "checkstyle" project was last updated
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【更新日期】字段 updated_date（更新日期）与参考值精确一致

## a94c1948e65b354ca24f
- **题面：** For this local training variant, change the URL key of New Category Name to "training-updated-category" and save.
- **分支：** admin_contract_rules.checks:update（源：binary）
- **隐含前提（不占分）：** 终页属于原本地部署；终页未被标记为登录页/错误页；目标以外的同实体记录保持未变
  - G1 【目标对象】操作对象为题面指定目标（产品/客户组/记录身份正确，非同名/新建替代）
  - G2 【目标值】目标字段最终值精确满足题面要求（persisted_requested_value / update_matches）
  - G3 【保存生效】赋值已持久保存并在保存后复查仍为目标值
  - G4 【未动无关项】目标以外的同实体记录/字段保持未变

## ad14f1ea651d3dfaa032
- **题面：** Find the current coordinates shown on the map
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【正确结果】返回题面要求的正确结果（值/目标与参考一致）

## ad26452f2969e7565c70
- **题面：** Find the estimated travel time for driving from Syracuse to Buffalo
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【时长】字段 duration_minutes（时长）与参考值精确一致

## ad3e4fb48ca4a16b8f1c
- **题面：** List the price of Lobster Cobbler Pot Pie - Gourmet Frozen Seafood Appetizers.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【价格】字段 price（价格）与参考值精确一致

## ad6b4323f8b6b17e62fd
- **题面：** Find the manufacturer of the Pre-baked Gingerbread House Kit.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【制造商】字段 manufacturer（制造商）与参考值精确一致

## ae68af8e1133e4f596dc
- **题面：** Check if you are subscribed to the newsletter.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【订阅状态】字段 subscription_status（订阅状态）与参考值精确一致

## aeda435714dad5e3f5c6
- **题面：** Retrieve the total number of issues across all statuses for The A11Y Project / a11yproject.com.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【issue 总数】字段 all_issue_count（issue 总数）与参考值精确一致

## b045428cb375aecc3613
- **题面：** Find which forum has the most submissions on this platform
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【版块名】字段 forum_name（版块名）与参考值精确一致

## b7dbf7b6ca54b76fbb97
- **题面：** Check the overall rating of the St Patricks Day T-Shirt
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【评分】字段 rating_percent（评分）与参考值精确一致

## b864f0a929e2ed01b5f3
- **题面：** Check the license type of the PureLayout project
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【许可证类型】字段 license_type（许可证类型）与参考值精确一致

## b9fc14ca759f15cd389d
- **题面：** Find the highest rated vegan product on the first page
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【商品】字段 product（商品）与参考值精确一致

## ba0e3915421dafab49c5
- **题面：** Check when the content_script.js file was last updated
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【文件更新日期】字段 file_updated_date（文件更新日期）与参考值精确一致

## bbcfeac97cd866e06f1c
- **题面：** Check how many submissions are in the AskReddit forum
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【提交数】字段 submission_count（提交数）与参考值精确一致

## bec24923c0a7ed46e025
- **题面：** Check the total travel time for driving from New York City to Boston
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【时长】字段 duration_minutes（时长）与参考值精确一致

## bec64ee0077086f0b2cb
- **题面：** Check when the question about "song describes your love life" was posted
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【提交日期】字段 submission_date（提交日期）与参考值精确一致

## bee5d9b2acdb2f66eb9c
- **题面：** Filter credit memos created between April 1, 2023 and April 30, 2023
- **分支：** admin_contract_rules.checks:collection_query（源：binary）
- **隐含前提（不占分）：** 终页属于原本地部署；终页未被标记为登录页/错误页；相关记录保持未变；答案格式符合 schema
  - G1 【过滤条件】搜索/过滤条件与题面一致（未放宽、未误用）
  - G2 【结果集精确】结果集完整精确：无遗漏、无多余、无重复（exact_result_set）

## c0d03822ad3cc182a48a
- **题面：** Find all customers who registered between March 1, 2023 and April 1, 2023
- **分支：** admin_contract_rules.checks:collection_query（源：binary）
- **隐含前提（不占分）：** 终页属于原本地部署；终页未被标记为登录页/错误页；相关记录保持未变；答案格式符合 schema
  - G1 【过滤条件】搜索/过滤条件与题面一致（未放宽、未误用）
  - G2 【结果集精确】结果集完整精确：无遗漏、无多余、无重复（exact_result_set）

## c251c8edc13bff852155
- **题面：** Change the tax class of the customer group Updated General Customers to Wholesale Customer and save the group.
- **分支：** admin_contract_rules.checks:update（源：binary）
- **隐含前提（不占分）：** 终页属于原本地部署；终页未被标记为登录页/错误页；目标以外的同实体记录保持未变
  - G1 【目标对象】操作对象为题面指定目标（产品/客户组/记录身份正确，非同名/新建替代）
  - G2 【目标值】目标字段最终值精确满足题面要求（persisted_requested_value / update_matches）
  - G3 【保存生效】赋值已持久保存并在保存后复查仍为目标值
  - G4 【未动无关项】目标以外的同实体记录/字段保持未变

## c3210e310f50c17ee5ab
- **题面：** Check the number of completed to-dos.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【已完成待办数】字段 completed_todo_count（已完成待办数）与参考值精确一致

## c334c6a3aeb526c0cc15
- **题面：** View the number of stars for the system-design-primer repository
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【star 数】字段 star_count（star 数）与参考值精确一致

## c4c457724ca5b3facc2f
- **题面：** Add a new related product to the Blue T-Shirt
- **分支：** admin_contract_rules.checks:links（源：binary）
  - G1 【结果精确】查询结果与参考精确一致

## c6ebf0496191e8d8af97
- **题面：** For this local training variant, rename New Category Name to Updated Training Category and save.
- **分支：** admin_contract_rules.checks:update（源：binary）
- **隐含前提（不占分）：** 终页属于原本地部署；终页未被标记为登录页/错误页；目标以外的同实体记录保持未变
  - G1 【目标对象】操作对象为题面指定目标（产品/客户组/记录身份正确，非同名/新建替代）
  - G2 【目标值】目标字段最终值精确满足题面要求（persisted_requested_value / update_matches）
  - G3 【保存生效】赋值已持久保存并在保存后复查仍为目标值
  - G4 【未动无关项】目标以外的同实体记录/字段保持未变

## c73f96cd937d5a5d4222
- **题面：** Find the forum with the most submissions on the current page
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【版块名】字段 forum_name（版块名）与参考值精确一致

## c7c76b2b4fc56c624da4
- **题面：** Check how many pending to-dos I have in GitLab
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【待办数】字段 pending_todo_count（待办数）与参考值精确一致

## c9d198f8cc222a1285bd
- **题面：** Find the project with the most open issues on the current page
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【项目】字段 project（项目）与参考值精确一致

## c9e49f9b5ac1dd332e59
- **题面：** Check which projects have the most open issues
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【项目】字段 projects（项目）与参考值精确一致

## c9ea69ebd9bbe0132937
- **题面：** Include the "New Category Name" category in the navigation menu
- **分支：** admin_contract_rules.checks:update（源：binary）
- **隐含前提（不占分）：** 终页属于原本地部署；终页未被标记为登录页/错误页；目标以外的同实体记录保持未变
  - G1 【目标对象】操作对象为题面指定目标（产品/客户组/记录身份正确，非同名/新建替代）
  - G2 【目标值】目标字段最终值精确满足题面要求（persisted_requested_value / update_matches）
  - G3 【保存生效】赋值已持久保存并在保存后复查仍为目标值
  - G4 【未动无关项】目标以外的同实体记录/字段保持未变

## ca05753924c09a2b379f
- **题面：** Check if there are any wiki pages available
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【存在性】字段 exists（存在性）与参考值精确一致

## ca513c352ac8683d59ba
- **题面：** Check how many issues are open in the ArduinoJson project
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【open issue 数】字段 open_issue_count（open issue 数）与参考值精确一致

## ced122c4f49dfa2d22b3
- **题面：** Check the total price of items in my shopping cart
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【商品小计】字段 items_subtotal（商品小计）与参考值精确一致

## cef94e2c64f4f23f905e
- **题面：** Check which programming language is used in the gumble project
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【声明语言】字段 declared_language（声明语言）与参考值精确一致

## cf17936dfd58f2333310
- **题面：** Look for projects with the most stars on the current page
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【项目】字段 projects（项目）与参考值精确一致

## d0e66b5ec2fd2c26f88e
- **题面：** Find out if the Intel NUC Kit NUC6i7KYK Mini PC comes with a power cord
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【是否含电源线】字段 power_cord_included（是否含电源线）与参考值精确一致

## d2920efde53b41c1a1b6
- **题面：** Add related products to the Blue T-Shirt product.
- **分支：** admin_contract_rules.checks:links（源：binary）
  - G1 【结果精确】查询结果与参考精确一致

## d2b42088c0be8bc2f160
- **题面：** Find out if user MarvelsGrantMan136 is whitelisted on the platform.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【是否在白名单】字段 whitelisted（是否在白名单）与参考值精确一致

## d344b156d8c7f1aa850a
- **题面：** Check the date when the negative review for the Gingerbread House Kit was posted.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【差评日期】字段 negative_review_date（差评日期）与参考值精确一致

## d52c0aa1fd01a13549bf
- **题面：** Add a related product to the Yoga Mat Pro listing
- **分支：** admin_contract_rules.checks:links（源：binary）
  - G1 【结果精确】查询结果与参考精确一致

## d57f5a05cc1dd5127e70
- **题面：** Retrieve the number of forks for the project "Byte Blaze / empathy-prompts".
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【fork 数】字段 fork_count（fork 数）与参考值精确一致

## d5bd865c545a1cd9a3a6
- **题面：** Find the total distance of the driving route from New York City to Boston
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【距离】字段 distance_km（距离）与参考值精确一致

## d6a29e7a354b46ccc7d5
- **题面：** Check the manufacturer of the Pre-baked Gingerbread House Kit
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【制造商】字段 manufacturer（制造商）与参考值精确一致

## d83baacc79d7fd79e8c1
- **题面：** Find the post with the most comments on the AskReddit page
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【标题】字段 title（标题）与参考值精确一致

## d87e55ef023592f031df
- **题面：** Find the oldest completed to-do item in your GitLab account.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【最早待办标题】字段 oldest_todo_title（最早待办标题）与参考值精确一致

## da0fc47b98877acabdd8
- **题面：** Modify the inventory quantity of the Blue T-Shirt.
- **分支：** admin_contract_rules.checks:update（源：binary）
- **隐含前提（不占分）：** 终页属于原本地部署；终页未被标记为登录页/错误页；目标以外的同实体记录保持未变
  - G1 【目标对象】操作对象为题面指定目标（产品/客户组/记录身份正确，非同名/新建替代）
  - G2 【目标值】目标字段最终值精确满足题面要求（persisted_requested_value / update_matches）
  - G3 【保存生效】赋值已持久保存并在保存后复查仍为目标值
  - G4 【未动无关项】目标以外的同实体记录/字段保持未变

## da2963632dabe85ed989
- **题面：** Report the displayed net score (upvotes minus downvotes) for the post “Michael Jackson’s ‘Thriller’ Returns To Billboard Top 10 After 38 Years”.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【净评分】字段 net_score（净评分）与参考值精确一致

## daa63e0184a9716e7f11
- **题面：** Locate all customers with a tax/VAT number in the system
- **分支：** admin_contract_rules.checks:collection_query（源：binary）
- **隐含前提（不占分）：** 终页属于原本地部署；终页未被标记为登录页/错误页；相关记录保持未变；答案格式符合 schema
  - G1 【过滤条件】搜索/过滤条件与题面一致（未放宽、未误用）
  - G2 【结果集精确】结果集完整精确：无遗漏、无多余、无重复（exact_result_set）

## db25b171278a7d9c4cc6
- **题面：** Find the most recent release of The A11Y Project
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【标签】字段 tag（标签）与参考值精确一致

## db3e72832768a5e92899
- **题面：** Check if dark mode is currently enabled
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【是否深色模式】字段 dark_mode（是否深色模式）与参考值精确一致

## dcc126a9d92300a10259
- **题面：** Check how many items are currently in my shopping cart
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【商品数】字段 item_count（商品数）与参考值精确一致

## dfb40a038914bcf1795b
- **题面：** View the list of VIP Customers
- **分支：** admin_contract_rules.checks:collection_query（源：binary）
- **隐含前提（不占分）：** 终页属于原本地部署；终页未被标记为登录页/错误页；相关记录保持未变；答案格式符合 schema
  - G1 【过滤条件】搜索/过滤条件与题面一致（未放宽、未误用）
  - G2 【结果集精确】结果集完整精确：无遗漏、无多余、无重复（exact_result_set）

## e0acc2846f49efa750d7
- **题面：** Retrieve the total number of issues across all statuses for Byte Blaze / accessible-html-content-patterns.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【issue 总数】字段 all_issue_count（issue 总数）与参考值精确一致

## e154d00d7844088d94d7
- **题面：** Find out which websites are excluded from the Updated General Customers group
- **分支：** admin_contract_rules.checks:query（源：binary）
- **隐含前提（不占分）：** 终页属于原本地部署；终页未被标记为登录页/错误页；相关记录保持未变；答案格式符合 schema
  - G1 【排除网站】字段 excluded_websites（排除网站）与参考值精确一致

## e1651f6e9d684024eaeb
- **题面：** Exclude Main Website from the Updated General Customers group, and save.
- **分支：** admin_contract_rules.checks:update（源：binary）
- **隐含前提（不占分）：** 终页属于原本地部署；终页未被标记为登录页/错误页；目标以外的同实体记录保持未变
  - G1 【目标对象】操作对象为题面指定目标（产品/客户组/记录身份正确，非同名/新建替代）
  - G2 【目标值】目标字段最终值精确满足题面要求（persisted_requested_value / update_matches）
  - G3 【保存生效】赋值已持久保存并在保存后复查仍为目标值
  - G4 【未动无关项】目标以外的同实体记录/字段保持未变

## e191611698289fe50395
- **题面：** View when customer Adam Garcia created his account For this local training variant, the target account email is adam.garcia@gmail.com.
- **分支：** admin_contract_rules.checks:query（源：binary）
- **隐含前提（不占分）：** 终页属于原本地部署；终页未被标记为登录页/错误页；相关记录保持未变；答案格式符合 schema
  - G1 【创建时间】字段 created_at（创建时间）与参考值精确一致

## e44dd798dd96c628fafa
- **题面：** For this local training variant, update the default billing address phone number of Jane Doe (jane.doe@gmail.com) to 555-123-4567 and save.
- **分支：** admin_contract_rules.checks:update（源：binary）
- **隐含前提（不占分）：** 终页属于原本地部署；终页未被标记为登录页/错误页；目标以外的同实体记录保持未变
  - G1 【目标对象】操作对象为题面指定目标（产品/客户组/记录身份正确，非同名/新建替代）
  - G2 【目标值】目标字段最终值精确满足题面要求（persisted_requested_value / update_matches）
  - G3 【保存生效】赋值已持久保存并在保存后复查仍为目标值
  - G4 【未动无关项】目标以外的同实体记录/字段保持未变

## e4507b6d61c7f5e585bb
- **题面：** Change Yoga Mat Pro price to 31.99 and save the product.
- **分支：** admin_contract_rules.checks:update（源：binary）
- **隐含前提（不占分）：** 终页属于原本地部署；终页未被标记为登录页/错误页；目标以外的同实体记录保持未变
  - G1 【目标对象】操作对象为题面指定目标（产品/客户组/记录身份正确，非同名/新建替代）
  - G2 【目标值】目标字段最终值精确满足题面要求（persisted_requested_value / update_matches）
  - G3 【保存生效】赋值已持久保存并在保存后复查仍为目标值
  - G4 【未动无关项】目标以外的同实体记录/字段保持未变

## e68e1f03005a83f12ade
- **题面：** Check how many issues are open in the TrafficMonitor repository
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【open issue 数】字段 open_issue_count（open issue 数）与参考值精确一致

## e99d790f732ba60e3c65
- **题面：** Count how many projects on this page have more than 10 stars
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【数量】字段 count（数量）与参考值精确一致

## ec17d35f33b53e5a1baa
- **题面：** Check how many commits have been made to the cloud-to-butt repository
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【提交次数】字段 commit_count（提交次数）与参考值精确一致

## ec7ae8996688fc3a2e08
- **题面：** Set a special price for the Example Product Deluxe 2023.
- **分支：** admin_contract_rules.checks:update（源：binary）
- **隐含前提（不占分）：** 终页属于原本地部署；终页未被标记为登录页/错误页；目标以外的同实体记录保持未变
  - G1 【目标对象】操作对象为题面指定目标（产品/客户组/记录身份正确，非同名/新建替代）
  - G2 【目标值】目标字段最终值精确满足题面要求（persisted_requested_value / update_matches）
  - G3 【保存生效】赋值已持久保存并在保存后复查仍为目标值
  - G4 【未动无关项】目标以外的同实体记录/字段保持未变

## ed517c55ec73b52a521c
- **题面：** Check how many closed issues are assigned to me across my accessible projects.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【数量】字段 count（数量）与参考值精确一致

## ed6c769c8c1b8f530584
- **题面：** Find the price of the Bushnell 743333 Boresighter.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【价格】字段 price（价格）与参考值精确一致

## ee8e562868eff0202bf8
- **题面：** Find the number of submissions in the gaming forum.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【提交数】字段 submission_count（提交数）与参考值精确一致

## efb765feca3cf117c9e3
- **题面：** View when my account was registered
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【注册日期】字段 registration_date（注册日期）与参考值精确一致

## f339a1b31f983a1b6cdb
- **题面：** Find the current map coordinates
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【正确结果】返回题面要求的正确结果（值/目标与参考一致）

## f412f90491545b946b32
- **题面：** Remove an existing up-sell product from the Blue T-Shirt
- **分支：** admin_contract_rules.checks:links（源：binary）
  - G1 【结果精确】查询结果与参考精确一致

## f8fe2dec74b77ea9c172
- **题面：** Identify the oldest pending to-do in my list and report its title.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【最早待办标题】字段 oldest_todo_title（最早待办标题）与参考值精确一致

## fbe617235425d7ebe689
- **题面：** Find the price of the "Maryia Men 3D Creative Printed Graphic T Shirts Casual Short Sleeve Crewneck Muscle Tees Personality Realistic Suit".
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【价格】字段 price（价格）与参考值精确一致

## fedf71fe5f3cf9866519
- **题面：** Find the number of submissions in the Music forum.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
- **隐含前提（不占分）：** 页面有效可用；查询未改动目标记录；答案格式符合 schema
  - G1 【提交数】字段 submission_count（提交数）与参考值精确一致

## 00073fc0e98637fac697
- **题面：** Go to the Merge requests page for the a11y-syntax-highlighting repository.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/a11y-syntax-highlighting/-/merge_requests
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Merge requests · Byte Blaze / a11y-syntax-highlighting · GitLab$

## 0072070662f4e7996848
- **题面：** Check out the TrafficMonitor project.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /zhongyang219/TrafficMonitor
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^TrafficMonitor$

## 0387fdd1bf583a5885f4
- **题面：** Navigate to the Byte Blaze / a11y-syntax-highlighting project page.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/a11y-syntax-highlighting/-/tree/main
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:Files\ ·\ main\ ·\ Byte\ Blaze\ /\ a11y\-syntax\-highlighting\ ·\ GitLab|Byte\ Blaze\ /\ a11y\-syntax\-highlighting\ ·\ GitLab)$

## 045d55acdf88f915e141
- **题面：** Navigate to the New project creation page.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /projects/new
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Create new project$

## 05b6980cb7daa00b7b96
- **题面：** Navigate to the Deployments section of the a11y-syntax-highlighting project.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/a11y-syntax-highlighting/-/environments
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Environments\ ·\ Byte\ Blaze\ /\ a11y\-syntax\-highlighting\ ·\ GitLab$

## 06d23dbbc954ea0eb0a1
- **题面：** Choose "Just me" for who will be using this group.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /groups/new#create-group-pane
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^New Group · GitLab$

## 07a3cfdf9b180d079ed7
- **题面：** Navigate to the project page for Byte Blaze / empathy-prompts.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/empathy-prompts
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Empathy Prompts$

## 0926bda7e9de9306bd1d
- **题面：** Navigate to your personal projects page
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Projects · Dashboard · GitLab$

## 0aa2590caf2eff45521d
- **题面：** View the images directory in the repository.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/a11y-syntax-highlighting/-/tree/main/images
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^images\ ·\ main\ ·\ Byte\ Blaze\ /\ a11y\-syntax\-highlighting\ ·\ GitLab$

## 0b84a338d6a53e5da8e5
- **题面：** Navigate to the Issues page from the create new group page.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /dashboard/issues
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Issues$

## 0035032b51075f0ecf6f
- **题面：** View the details of the Plus Size Lingerie item in my cart
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /plus-size-lingerie-for-women-sexy-for-sex-naughty-eyelash-lace-bodysuit-naughty-mesh-one-piece-teddy-bodysuit-outfits.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:Plus\ Size\ Lingerie\ for\ Women\ Sexy\ for\ Sex\ Naughty\ Eyelash\ Lace\ Bodysuit\ Naughty\ Mesh\ One\ Piece\ Teddy\ Bodysuit\ Outfits)$

## 083ff9b8eba023e4ff5a
- **题面：** Open the Video Games category listing page.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /video-games.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Video\ Games$

## 0a64917e7a4ac0700d59
- **题面：** Go to the Computers & Accessories section
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /electronics/computers-accessories.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Computers & Accessories(?: Items .*)?$

## 0b607d62e6782eb64262
- **题面：** Browse the Electronics category to find electronic devices and accessories.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /electronics.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Electronics$

## 0f0676833d04cef8cf07
- **题面：** Navigate to the Clothing, Shoes & Jewelry category to shop for apparel, footwear, and accessories.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /clothing-shoes-jewelry.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Clothing,\ Shoes\ \&\ Jewelry$

## 0f54611a24e7a90599d5
- **题面：** Navigate to the home page
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^One Stop Market$

## 1094c53c2034431c453d
- **题面：** Navigate to the product detail page for the V8 +Energy drink to view more information.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /v8-energy-healthy-energy-drink-natural-energy-from-tea-pomegranate-blueberry-8-fl-oz-can-12-count-pack-of-1.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:V8\ \+Energy\ Healthy\ Energy\ Drink,\ Natural\ Energy\ from\ Tea,\ Pomegranate\ Blueberry,\ 8\ FL\ Oz\ Can,\ 12\ Count\ \(Pack\ of\ 1\)|V8\ \+Energy,\ Healthy\ Energy\ Drink,\ Natural\ Energy\ from\ Tea,\ Pomegranate\ Blueberry,\ 8\ Fl\ Oz\ Can\ \(pack\ of\ 6\)|V8\ \+Energy,\ Healthy\ Energy\ Drink,\ Steady\ Energy\ from\ Black\ and\ Green\ Tea,\ Pomegranate\ Blueberry,\ 8\ Ounce\ Can\ ,Pack\ of\ 24)$

## 10c66031ab9dc871e7dc
- **题面：** View My Wish List
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /wishlist/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^My Wish List$

## 12aa53b20b84f0fb1cb4
- **题面：** View the reviews of the Nightfox Vulpes Handheld Digital Night Vision Goggles.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /nightfox-vulpes-handheld-digital-night-vision-goggles-integrated-laser-rangefinder-full-high-definition-fhd-1080p-sensor-records-video-audio-220yd-range-6x-magnification-hunting-security.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Nightfox\ Vulpes\ Handheld\ Digital\ Night\ Vision\ Goggles\ \|\ Integrated\ Laser\ Rangefinder\ \|\ Full\ High\ Definition\ FHD\ 1080p\ Sensor\ \|\ Records\ Video\ \+\ Audio\ \|\ 220yd\ Range,\ 6x\ Magnification\ \|\ Hunting,\ Security$

## 134973b622eb29eb2918
- **题面：** Navigate to your wish list to view saved items you want to purchase later.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /wishlist/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^My Wish List$

## 0189de83adbd18ca5109
- **题面：** Open the local Communities page to view its Local Chapters and Other Groups directory. External group websites or contact are not required.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /communities
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Communities$

## 058c211ed6572633b8e3
- **题面：** Get driving directions from Boston to New York City.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /directions?engine=fossgis_osrm_car&route=42.3554334%2C-71.060511%3B40.7127281%2C-74.0060152
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Directions$

## 07c4afe9a10c12f2c391
- **题面：** Find directions between Central Park, New York and Times Square, New York.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /directions?engine=fossgis_osrm_car&route=40.7827725%2C-73.9653627406542%3B40.75701215%2C-73.98597092538824
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Directions$

## 0849b046d63579fc3565
- **题面：** Reverse the direction to plan a trip from Boston to New York
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /directions?engine=fossgis_osrm_car&route=42.3554334%2C-71.060511%3B40.7127281%2C-74.0060152
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Directions$

## 0870827f06e8ef841cf6
- **题面：** Find driving directions from Syracuse to Rochester, NY
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /directions?engine=fossgis_osrm_car&route=43.0481221%2C-76.1474244%3B43.157285%2C-77.615214
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Directions$

## 090156aa79cd713a79c8
- **题面：** Get cycling directions from Times Square, New York to Central Park, New York.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /directions?engine=fossgis_osrm_bike&route=40.75701215%2C-73.98597092538824%3B40.7827725%2C-73.9653627406542
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Directions$

## 090b981871aa01b7b46f
- **题面：** Get walking directions from 40.74800, -73.98600 to 40.75300, -73.97700
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /directions?engine=fossgis_osrm_foot&route=40.748%2C-73.986%3B40.753%2C-73.977
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Directions$

## 0afd3e67a34103f0320a
- **题面：** View the specific route from Buffalo to Rochester on the map
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /directions?engine=fossgis_osrm_car&route=42.8867166%2C-78.8783922%3B43.157285%2C-77.615214
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Directions$

## 0b42ca24c4bbb72a380c
- **题面：** Change the mode of transportation to Bicycle for the route from 40.7830, -73.9650 to 40.7570, -73.9860.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /directions?engine=fossgis_osrm_bike&route=40.783%2C-73.965%3B40.757%2C-73.986
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Directions$

## 0e969f70c08ad9d881ef
- **题面：** Navigate to the Copyright page to learn about OpenStreetMap licensing and attribution requirements.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /copyright
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Copyright\ and\ License$

## 092c1675b6169ee15242
- **题面：** Navigate to the System section.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达菜单】到达菜单 System

## 0dba3fbedd31d942e2c1
- **题面：** Navigate to the STORES section of the admin panel.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达菜单】到达菜单 Stores

## 18ac54ffeac11b177872
- **题面：** Navigate to the System section from the credit memo view page.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达菜单】到达菜单 System

## 1b6c13b5546fb3506416
- **题面：** Navigate to the MARKETING section from the Dashboard page
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达菜单】到达菜单 Marketing

## 05ff9add3cd319052583
- **题面：** View the user profile of MarvelsGrantMan136
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /user/MarvelsGrantMan136
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^MarvelsGrantMan136$

## 062cf6938a87a7fe04c2
- **题面：** View your notifications to see any new activity.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /notifications
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Notifications$

## 09c50a6b3d0ad9a2de06
- **题面：** View the discussion about "What movie trope are you a sucker for?"
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /f/movies/128428
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^What\ movie\ trope\ are\ you\ a\ sucker\ for\?$

## 0b7d10bf2e674eea1898
- **题面：** Check out the philadelphia forum.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /f/philadelphia
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:/f/)?philadelphia$

## 0e04d3aec835c1d5b7a8
- **题面：** Browse the worldnews forum
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /f/worldnews
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:/f/)?worldnews$

## 0fde74c9aa1d5d8dc9b7
- **题面：** View the relationship_advice forum.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /f/relationship_advice
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:/f/)?relationship_advice$

## 1173d3d994b7c0404a62
- **题面：** Return to the Home page
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Postmill$

## 0bbee95a15b8840fefb0
- **题面：** View the understanding-vestibular-disorders.md file to learn about accessibility considerations for users with motion sensitivity.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /a11yproject/a11yproject.com/-/blob/main/src/posts/understanding-vestibular-disorders.md
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^src/posts/understanding\-vestibular\-disorders\.md\ ·\ main\ ·\ The\ A11Y\ Project\ /\ a11yproject\.com\ ·\ GitLab$

## 0cba5837440c660e0f84
- **题面：** Filter projects by name "android"
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /explore/projects?sort=name_asc&non_archived=true&name=android
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Projects · Explore · GitLab$

## 0f8811222ada4a28521a
- **题面：** Navigate to view all branches of the cloud-to-butt project.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/cloud-to-butt/-/branches/all
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:Branches\ ·\ Byte\ Blaze\ /\ cloud\-to\-butt\ ·\ GitLab)$

## 1d6ba316e7003442b363
- **题面：** Sort projects by most stars instead of name
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /?sort=stars_desc&non_archived=true
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Projects · Dashboard · GitLab$

## 1e88d13c0af8e045722e
- **题面：** Go to the Tags page to see release versions.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /a11yproject/a11yproject.com/-/tags
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Tags.*a11yproject\.com.*GitLab$

## 1e933a96c73c403f4971
- **题面：** Visit the Issues page
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /dashboard/issues
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Issues$

## 1f81a9aa4f99df2ceb59
- **题面：** Search for Python projects in the GitLab explore page
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /explore/projects?sort=name_asc&non_archived=true&name=Python
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Projects · Explore · GitLab$

## dd5bf5833f21fac3a73b
- **题面：** Visit the Snippets page for the a11y-syntax-highlighting project.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/a11y-syntax-highlighting/-/snippets
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Snippets · Byte Blaze / a11y-syntax-highlighting · GitLab$

## 152a3ef5e349e96d3254
- **题面：** Check the commit history of the a11y-syntax-highlighting project.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/a11y-syntax-highlighting/-/commits/main
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Commits\ ·\ main\ ·\ Byte\ Blaze\ /\ a11y\-syntax\-highlighting\ ·\ GitLab$

## 16369b1c4bbe0ce37cea
- **题面：** Visit the Search page to find projects, issues, or merge requests.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /search
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Search$

## 16a8b25e2eb42d7384cf
- **题面：** Check the troubleshooting documentation for The A11Y Project.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /a11yproject/a11yproject.com/-/blob/main/TROUBLESHOOTING.md
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^TROUBLESHOOTING\.md\ ·\ main\ ·\ The\ A11Y\ Project\ /\ a11yproject\.com\ ·\ GitLab$

## 24ad31a1214a0cb41285
- **题面：** View all open merge requests for the wxpy project
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /youfou/wxpy/-/merge_requests?state=opened
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Merge requests · .+ / wxpy · GitLab$

## 2594b549f5054c75b79c
- **题面：** Explore trending projects.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /explore/projects/trending?sort=name_asc&non_archived=true
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Projects · Explore · GitLab$

## 25e8ac362210da8a5672
- **题面：** Browse the repository code in Byte Blaze / a11y-syntax-highlighting.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/a11y-syntax-highlighting/-/tree/main
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:Files\ ·\ main\ ·\ Byte\ Blaze\ /\ a11y\-syntax\-highlighting\ ·\ GitLab|Byte\ Blaze\ /\ a11y\-syntax\-highlighting\ ·\ GitLab)$

## 319fef2779eadbbba151
- **题面：** Open any merge request details page associated with a pending item in your current account's initial To-Do List. Any such target is acceptable; the route used to reach it is unrestricted. Leave the target page open and do not change the to-do items.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /a11yproject/a11yproject.com/-/merge_requests/1071
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:Add\ color\ utility\ classes|Add\ verification\ functions|feat:\ add\ WCAG\ levels|update\ or\ remove\ 404\ links)$

## 357bfc824061bf58e58b
- **题面：** Browse projects by topics.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /explore/projects/topics
  - G2 【标题/身份匹配】页面标题/目标身份匹配 Topics.*GitLab$

## 3eea162bbb47832f524d
- **题面：** Visit the repository page for the "trpc" project
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /trpc/trpc
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^trpc$

## 44018a87964ae1a7c8e0
- **题面：** Explore the highlight directory for Highlight.js themes.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/a11y-syntax-highlighting/-/tree/main/dist/highlight
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^dist/highlight(?:/[^·]+)? · main\ ·\ Byte\ Blaze\ /\ a11y\-syntax\-highlighting\ ·\ GitLab$

## 4492ebf4c3edc16dacde
- **题面：** View trending projects.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /explore/projects/trending
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Projects · Explore · GitLab$

## 46cfbead6f1968393a1e
- **题面：** Visit the project roadmap to see planned future support for editors like VS Code and Sublime Text.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/a11y-syntax-highlighting/-/blob/main/README.md#roadmap
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:README\.md\ ·\ main\ ·\ Byte\ Blaze\ /\ a11y\-syntax\-highlighting\ ·\ GitLab|Byte\ Blaze\ /\ a11y\-syntax\-highlighting\ ·\ GitLab)$

## 48ae77e5d0cc194a560f
- **题面：** Check the open issues for Byte Blaze / a11y-syntax-highlighting.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/a11y-syntax-highlighting/-/issues?state=opened
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Issues · .+ / a11y\-syntax\-highlighting · GitLab$

## 52a352b5b40b267e95cc
- **题面：** Search for and view recently updated projects
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /?sort=latest_activity_desc&non_archived=true
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Projects · Dashboard · GitLab$

## 536d80fb651c8023dcc8
- **题面：** View the split_silence.py example for audio processing
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /kkroening/ffmpeg-python/-/blob/master/examples/split_silence.py
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:examples/split_silence\.py\ ·\ master\ ·\ Karl\ Kroening\ /\ ffmpeg\-python\ ·\ GitLab)$

## 5f4efeaeb777c158e271
- **题面：** Learn about the Windows High Contrast Mode support in these themes.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/a11y-syntax-highlighting/-/blob/main/README.md#high-contrast-mode
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:README\.md\ ·\ main\ ·\ Byte\ Blaze\ /\ a11y\-syntax\-highlighting\ ·\ GitLab|Byte\ Blaze\ /\ a11y\-syntax\-highlighting\ ·\ GitLab)$

## 614d94c10e6d9e3d8db2
- **题面：** Go to the Dashboard page
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Projects · Dashboard · GitLab$

## 6f9f09ff928255b2e62c
- **题面：** Go to the previous page of projects.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /explore/projects?non_archived=true&page=2&sort=name_asc
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Projects · Explore · GitLab$

## 7a47e1659934eacaa0a4
- **题面：** View the "Better sharing solution" issue in empathy-prompts.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/empathy-prompts/-/issues/6
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Better\ sharing\ solution$

## 7a89b16cae2e6e62b76b
- **题面：** Navigate to the Issues page.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /dashboard/issues
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Issues$

## 7f9cbe175731494f9444
- **题面：** Explore the a11y-syntax-highlighting project repository.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/a11y-syntax-highlighting/-/tree/main
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:Files\ ·\ main\ ·\ Byte\ Blaze\ /\ a11y\-syntax\-highlighting\ ·\ GitLab|Byte\ Blaze\ /\ a11y\-syntax\-highlighting\ ·\ GitLab)$

## 93f07bc8d671c50fe92b
- **题面：** Navigate to view all commits in the cloud-to-butt project history.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/cloud-to-butt/-/commits/master
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Commits\ ·\ master\ ·\ Byte\ Blaze\ /\ cloud\-to\-butt\ ·\ GitLab$

## a4a9ca3b41c7b722506b
- **题面：** View the examples of complex filter graphs in the ffmpeg-python project documentation (kkroening/ffmpeg-python).
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /kkroening/ffmpeg-python/-/blob/master/README.md#complex-filter-graphs
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ffmpeg\-python.*GitLab$

## a4c7022a121c07682a0a
- **题面：** Read the TECHNOLOGY.md file to understand the technical details of the A11Y Project.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /a11yproject/a11yproject.com/-/blob/main/TECHNOLOGY.md
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^TECHNOLOGY\.md\ ·\ main\ ·\ The\ A11Y\ Project\ /\ a11yproject\.com\ ·\ GitLab$

## a81c118ee6065185645e
- **题面：** Navigate to the A11Y Project repository to view its code and contribute to accessibility improvements.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /a11yproject/a11yproject.com/-/tree/main
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:Files\ ·\ main\ ·\ The\ A11Y\ Project\ /\ a11yproject\.com\ ·\ GitLab|The\ A11Y\ Project\ /\ a11yproject\.com\ ·\ GitLab)$

## b47837db4d7877b3e08f
- **题面：** Navigate to view the README.md file for the cloud-to-butt project.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/cloud-to-butt/-/blob/master/README.md
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:README\.md\ ·\ master\ ·\ Byte\ Blaze\ /\ cloud\-to\-butt\ ·\ GitLab|Byte\ Blaze\ /\ cloud\-to\-butt\ ·\ GitLab|Files\ ·\ master\ ·\ Byte\ Blaze\ /\ cloud\-to\-butt\ ·\ GitLab)$

## b97f982f826c4311d206
- **题面：** Navigate to your user profile page.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Byte\ Blaze$

## bfb8ef140ac9aff54087
- **题面：** Access the CI/CD pipelines for the a11y-syntax-highlighting repository.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/a11y-syntax-highlighting/-/pipelines
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Pipelines.*a11y\-syntax\-highlighting.*GitLab$

## c530edb71542ead8bb41
- **题面：** Navigate to the Merge Requests page.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /dashboard/merge_requests
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Merge\ requests$

## cca2dbf5a4709cfbbcd3
- **题面：** View the repository code in a11yproject/a11yproject.com.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /a11yproject/a11yproject.com/-/tree/main
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:Files\ ·\ main\ ·\ The\ A11Y\ Project\ /\ a11yproject\.com\ ·\ GitLab|The\ A11Y\ Project\ /\ a11yproject\.com\ ·\ GitLab)$

## cd3eb64294def459855a
- **题面：** Change project sorting from name ascending to most recently updated
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /explore/projects?sort=latest_activity_desc&non_archived=true
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Projects · Explore · GitLab$

## d071c67921ce55f0bed5
- **题面：** View the administrate Rails engine project.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /thoughtbot/administrate
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^administrate$

## d35ad379f6914d06df57
- **题面：** Navigate to the src/index.njk file in a11yproject/a11yproject.com to examine the homepage template.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /a11yproject/a11yproject.com/-/blob/main/src/index.njk
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^src/index\.njk\ ·\ main\ ·\ The\ A11Y\ Project\ /\ a11yproject\.com\ ·\ GitLab$

## ddeabd1d7dcdfe3d381e
- **题面：** View the how-to-write-accessible-forms.md file to understand form accessibility requirements.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /a11yproject/a11yproject.com/-/blob/main/src/posts/how-to-write-accessible-forms.md
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^src/posts/how\-to\-write\-accessible\-forms\.md\ ·\ main\ ·\ The\ A11Y\ Project\ /\ a11yproject\.com\ ·\ GitLab$

## e946abc7791e67d006aa
- **题面：** Navigate to the Create new project page.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /projects/new
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Create new project$

## f03a70d73cbc48476487
- **题面：** Navigate to the Issues page to see all issues assigned to you.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /dashboard/issues?state=all&assignee_username=byteblaze
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Issues$

## f261d1bcd5ec0dc2e3e5
- **题面：** Visit the Analytics page to see project statistics and insights.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/a11y-syntax-highlighting/-/value_stream_analytics
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Value\ Stream\ Analytics\ ·\ Byte\ Blaze\ /\ a11y\-syntax\-highlighting\ ·\ GitLab$

## f4a511b8be6e645d348c
- **题面：** View all stargazers of the autojump project
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /wting/autojump/-/starrers
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Starrers .* / autojump .* GitLab$

## fbf6113823521546ab5d
- **题面：** View your personal projects.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /
  - G2 【标题/身份匹配】页面标题/目标身份匹配 Projects · Dashboard · GitLab$

## fce615ee838e6b7d2eba
- **题面：** Check the CI/CD pipeline status for the repository
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/a11y-syntax-highlighting/-/pipelines
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Pipelines\ ·\ Byte\ Blaze\ /\ a11y\-syntax\-highlighting\ ·\ GitLab$

## 209142457ea81e33873f
- **题面：** Change the transportation mode from Car to Bicycle for a route
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /directions?engine=fossgis_osrm_bike&route=40.75701215%2C-73.98597092538824%3B40.7827725%2C-73.9653627406542
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Directions$

## 218b9e1f3bbafdd12bfa
- **题面：** Explore the "Communities" section.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /communities
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Communities$

## 229b56c832ad5567472d
- **题面：** Change the transportation mode from car to foot for directions from Central Park to Times Square.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /directions?engine=fossgis_osrm_foot&route=40.7827725%2C-73.9653627406542%3B40.75701215%2C-73.98597092538824
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Directions$

## 28db69f8589995320fef
- **题面：** Open the Export page and leave its map-area selection form visible. This task ends at the form; downloading map data is not required.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /export#map=11/40.6976/-74.1000
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Export$

## 2b01346a650162809e75
- **题面：** Navigate to the History page to view changes made to the map.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /history
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Changesets$

## 3a763d24f0737e8ccea3
- **题面：** Reverse the direction of a planned route
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /directions?engine=fossgis_osrm_car&route=40.7827725%2C-73.9653627406542%3B40.75701215%2C-73.98597092538824
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Directions$

## 4ae3baeb404856a3aef2
- **题面：** Access the Help page for guidance on using OpenStreetMap.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /help
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Getting\ Help$

## 4b9de2854a0341c31342
- **题面：** Check the available image format options for downloading the map
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /
  - G2 【标题/身份匹配】页面标题/目标身份匹配 OpenStreetMap

## 585afafca2dfc81fca02
- **题面：** Visit the "Copyright" page to understand usage rights.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /copyright
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Copyright\ and\ License$

## 5c5b074f9a68b12fee96
- **题面：** Get cycling directions from Grand Central Station to Empire State Building
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /directions?engine=fossgis_osrm_bike&route=40.752701200000004%2C-73.97724987363358%3B40.74844205%2C-73.98565890160751
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Directions$

## 61bcd3cb83dd3588c37b
- **题面：** Change the transportation mode from car to bicycle for a route from Times Square to Central Park
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /directions?engine=fossgis_osrm_bike&route=40.75701215%2C-73.98597092538824%3B40.7827725%2C-73.9653627406542
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Directions$

## 6530ef3b4169dba120bb
- **题面：** View the history of recent changes to the map.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /history
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Changesets$

## 655046ea2fa12651193f
- **题面：** Find driving directions from Central Park, New York to Times Square, New York using the Car (OSRM) option.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /directions?engine=fossgis_osrm_car&route=40.7827725%2C-73.9653627406542%3B40.75701215%2C-73.98597092538824
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Directions$

## 662c59800bde1ba75b7b
- **题面：** Explore the different map layer options available on OpenStreetMap (Standard, CyclOSM, ÖPNVKarte, Humanitarian).
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /
  - G2 【标题/身份匹配】页面标题/目标身份匹配 OpenStreetMap

## 6aacd2dcebe49641a25b
- **题面：** Get driving directions from Times Square to Central Park in New York City
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /directions?engine=fossgis_osrm_car&route=40.75701215%2C-73.98597092538824%3B40.7827725%2C-73.9653627406542
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Directions$

## 6c59219c88807202c103
- **题面：** Navigate to the Communities page to connect with other OpenStreetMap contributors.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /communities
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Communities$

## 74429d6dfc3736f2eb19
- **题面：** Open the OpenID sign-in form so that its OpenID URL field and Login button are visible. Do not submit credentials or complete authentication.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /login
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Login$

## 7b6588603121d62aa84e
- **题面：** Navigate to the History page to view past map edits and changes.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /history
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Changesets$

## 7d75122fddc17399220e
- **题面：** Navigate to the Communities page to connect with other mappers and find local mapping groups.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /communities
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Communities$

## 803615400e70561e4a91
- **题面：** Navigate to the Copyright page to understand OpenStreetMap licensing and attribution requirements.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /copyright
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Copyright\ and\ License$

## 843be1460c9332302da5
- **题面：** Go to the export page to download map data.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /export#map=10/42.8960/-75.1080
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Export$

## 858caf1607608d5ae5a0
- **题面：** Display search results for New York City, New York, United States, with the city area shown on the map.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /search?query=New+York+City#map=7/42.896/-75.108
  - G2 【标题/身份匹配】页面标题/目标身份匹配 OpenStreetMap

## 85a7523f5745961ba8e1
- **题面：** Reverse the directions to get a route from Times Square to Central Park instead.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /directions?engine=fossgis_osrm_car&route=40.757%2C-73.986%3B40.783%2C-73.965
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Directions$

## 9eed061a64564bf7146b
- **题面：** Navigate to the Communities page to find OpenStreetMap community groups and local chapters.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /communities
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Communities$

## a0bea5b00b33a65a8be4
- **题面：** Check the history of map edits in this area
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /history#map=7/42.896/-75.108
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Changesets$

## bcad4bf877daf4d67423
- **题面：** Reverse the route direction to get directions from Central Park to Times Square
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /directions?engine=fossgis_osrm_car&route=40.7827725%2C-73.9653627406542%3B40.75701215%2C-73.98597092538824
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Directions$

## bd40ef5bbf030f7c1505
- **题面：** Visit the Communities page on OpenStreetMap.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /communities
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Communities$

## c230980afa6f0bf0342b
- **题面：** Find and display the local OpenStreetMap Communities directory. Browsing an external chapter website is outside this local task.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /communities
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Communities$

## c2cdd5fb6c2f1ededd51
- **题面：** Navigate to the Help page to find documentation and guides for using OpenStreetMap.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /help
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Getting\ Help$

## c69a04a7e1db2552e953
- **题面：** Navigate to the User Diaries page.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /diary
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Users'\ Diaries$

## cecc62133b744eca72cc
- **题面：** Navigate to the directions page to find a route between two locations.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /directions
  - G2 【标题/身份匹配】页面标题/目标身份匹配 OpenStreetMap

## d1d275dc46efc2e65476
- **题面：** Explore communities related to OpenStreetMap
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /communities
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Communities$

## d89b0048178cd11720cd
- **题面：** Navigate to the GPS Traces page to upload or browse GPS tracks.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /traces
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Public\ GPS\ Traces$

## e1006161c40c56b44309
- **题面：** View copyright information
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /copyright
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Copyright\ and\ License$

## e1b9a8faf241f6a088a8
- **题面：** Reverse the direction of the route to get directions from 40.75300, -73.97700 to 40.74800, -73.98600
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /directions?engine=fossgis_osrm_foot&route=40.753%2C-73.977%3B40.748%2C-73.986
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Directions$

## f049bdfefc158611ea45
- **题面：** Access the local OpenStreetMap Help page and display its help options. External Wiki documentation is outside this local task.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /help
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Getting\ Help$

## f31a7694a8abb9a05a0a
- **题面：** View what different map layers are available
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /
  - G2 【标题/身份匹配】页面标题/目标身份匹配 OpenStreetMap

## fa2f7c04c93ddc04dd2f
- **题面：** Navigate to the Communities page to find and connect with local OpenStreetMap groups.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /communities
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Communities$

## fbc50f6895e5eb802320
- **题面：** Navigate to the Help page to get assistance with using OpenStreetMap.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /help
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Getting\ Help$

## 13a0fabb465d848a3d9f
- **题面：** Explore Patio, Lawn & Garden products
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /catalog/category/view/id/10/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:Patio,\ Lawn\ \&\ Garden)$

## 1ad6d2c220a09d4eec48
- **题面：** View details of the NOZE Rustic Coat Rack in my recently ordered items
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /noze-rustic-coat-rack-wall-mounted-shelf-with-4-hooks-hanging-entryway-organizer-for-mug-coffee-cup-holding-solid-wooden-shelf-with-2-baskets-for-kitchen-living-room-bathroom-and-bedroom.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:NOZE\ Rustic\ Coat\ Rack\ Wall\ Mounted\ Shelf\ with\ 4\ Hooks,\ Hanging\ Entryway\ Organizer\ for\ Mug\ Coffee\ Cup,\ Holding\ Solid\ Wooden\ Shelf\ with\ 2\ Baskets\ for\ Kitchen\ Living\ Room,\ Bathroom\ and\ Bedroom)$

## 255c56b474f48d698857
- **题面：** From the shopping cart page, open the Sports & Outdoors category page.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /sports-outdoors.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Sports\ \&\ Outdoors(?: Items .*)?$

## 269774e9cad9d6a4fc70
- **题面：** Go to page 2 of Beauty & Personal Care products
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /beauty-personal-care.html?p=2
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Beauty\ \&\ Personal\ Care$

## 2a9363cecaf521d7e184
- **题面：** Navigate to the Health & Household category to shop for health products and household essentials.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /health-household.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Health\ \&\ Household$

## 2fb1cbb63aa4a4d2f7a0
- **题面：** View the Bushnell 743333 Boresighter product details.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /bushnell-743333-boresighter-with-case-arbors-black.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:Bushnell\ 743333\ Boresighter\ with\ Case\ \&\ ARbors,Black)$

## 34568cb201df021547da
- **题面：** View all your recently ordered items from your account.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /customer/account/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^My Account$

## 44abeb91aebb0043c0b0
- **题面：** Go back to the home page using breadcrumb navigation
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^One\ Stop\ Market$

## 464bd7f571d9eb04ce09
- **题面：** Browse Exercise & Fitness equipment.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /catalog/category/view/id/29/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:Exercise\ \&\ Fitness|Sports\ \&\ Outdoors)$

## 47dbbc6d000b4e84932c
- **题面：** Continue shopping and return to the homepage.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^One\ Stop\ Market$

## 5239a4f0b915fb43e36f
- **题面：** Visit the home page to browse all products.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^One Stop Market$

## 5ba99a807a9cf95280ec
- **题面：** View details of the Pre-baked Gingerbread House Kit Value Pack.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /pre-baked-gingerbread-house-kit-value-pack-17-oz-pack-of-2-total-34-oz.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Pre\-baked\ Gingerbread\ House\ Kit\ Value\ Pack,\ 17\ oz\.,\ Pack\ of\ 2,\ Total\ 34\ oz\.$

## 5c796dd22c55ca62d44e
- **题面：** View details of a product in your cart.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /plus-size-lingerie-for-women-sexy-for-sex-naughty-eyelash-lace-bodysuit-naughty-mesh-one-piece-teddy-bodysuit-outfits.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:Plus\ Size\ Lingerie\ for\ Women\ Sexy\ for\ Sex\ Naughty\ Eyelash\ Lace\ Bodysuit\ Naughty\ Mesh\ One\ Piece\ Teddy\ Bodysuit\ Outfits|Uttermost\ Volterra\ Crackled\ Taupe\-Gray\ Ceramic\ Table\ Lamp|NOZE\ Rustic\ Coat\ Rack\ Wall\ Mounted\ Shelf\ with\ 4\ Hooks,\ Hanging\ Entryway\ Organizer\ for\ Mug\ Coffee\ Cup,\ Holding\ Solid\ Wooden\ Shelf\ with\ 2\ Baskets\ for\ Kitchen\ Living\ Room,\ Bathroom\ and\ Bedroom)$

## 602bc6ede42c73e516ac
- **题面：** Explore Electronics products
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /catalog/category/view/id/11/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:Electronics)$

## 62b7701daa69787a85d6
- **题面：** Read reviews for the Crazy Sales Massage Table Carry Bag.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /crazy-sales-massage-table-carry-bag-professional-spa-table-shoulder-bag-portable-foldable-belt-adjustable-salon-bed-face-cradle-bed.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Crazy\ Sales\ Massage\ Table\ Carry\ Bag,\ Professional\ Spa\ Table\ Shoulder\ Bag\ Portable\ Foldable\ Belt\ Adjustable\ Salon\ Bed\ Face\ Cradle\ Bed$

## 6acbad9b26c6427856ce
- **题面：** Look at Bedding products
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /catalog/category/view/id/35/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:Bedding|Home\ \&\ Kitchen)$

## 6be6d37e350eb2bc36e7
- **题面：** View the Privacy and Cookie Policy page to learn about how the site handles your data.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /privacy-policy-cookie-restriction-mode
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Privacy and Cookie Policy$

## 74c98564d1e35bf6dec4
- **题面：** Go to the Beauty & Personal Care category.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /beauty-personal-care.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Beauty\ \&\ Personal\ Care(?: Items .*)?$

## 78756f29fb9e71590a06
- **题面：** Go to your account page to manage your personal information
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /customer/account/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^My Account$

## 7c4352d8e52492a93e9b
- **题面：** Navigate to the Advanced Search page to search for specific products with filters.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /catalogsearch/advanced/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Advanced Search$

## 7ccd70cd9214b15c0a35
- **题面：** Navigate to the My Account page
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /customer/account/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^My Account$

## 7f76ec7678c1f7660c91
- **题面：** Browse products in the Beauty & Personal Care category
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /beauty-personal-care.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Beauty\ \&\ Personal\ Care$

## 8886097798330a2b52ad
- **题面：** Browse the Grocery & Gourmet Food category
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /grocery-gourmet-food.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Grocery\ \&\ Gourmet\ Food(?: Items .*)?$

## 8aa88113542d93e86d9d
- **题面：** Go to Advanced Search to search for specific outdoor equipment.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /catalogsearch/advanced/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Advanced Search$

## 9f25892f02f29db5ec94
- **题面：** Navigate to the Clothing, Shoes & Jewelry category page to explore more products on sale.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /clothing-shoes-jewelry.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Clothing,\ Shoes\ \&\ Jewelry$

## b8474380646f2fce807c
- **题面：** Navigate to page 2 of Home & Kitchen products to see more items.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /home-kitchen.html?p=2
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Home\ \&\ Kitchen$

## b87ba988ad238b0acc93
- **题面：** Explore Hair Care products for hair treatments and styling.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /catalog/category/view/id/19/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:Beauty\ \&\ Personal\ Care|Hair\ Care)$

## ba50fac977c6e53d4929
- **题面：** View all customer reviews for the Nightfox Vulpes Night Vision Goggles.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /nightfox-vulpes-handheld-digital-night-vision-goggles-integrated-laser-rangefinder-full-high-definition-fhd-1080p-sensor-records-video-audio-220yd-range-6x-magnification-hunting-security.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Nightfox\ Vulpes\ Handheld\ Digital\ Night\ Vision\ Goggles\ \|\ Integrated\ Laser\ Rangefinder\ \|\ Full\ High\ Definition\ FHD\ 1080p\ Sensor\ \|\ Records\ Video\ \+\ Audio\ \|\ 220yd\ Range,\ 6x\ Magnification\ \|\ Hunting,\ Security$

## bd49de7c4477fe8104f6
- **题面：** Get detailed information about the "Power of Positivity" Eye Shadow Palette.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /power-of-positivity-eye-shadow-palette-gluten-free-vegan-cruelty-free.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:'Power\ of\ Positivity'\ Eye\ Shadow\ Palette\ \|\ Gluten\ Free\ \|\ Vegan\ \|\ Cruelty\ Free)$

## c0e6e10cd6ba5aec5ffe
- **题面：** Go to the Advanced Search page.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /catalogsearch/advanced/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Advanced Search$

## c2555416de619bc829ac
- **题面：** Browse to page 2 of the Beauty & Personal Care products
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /beauty-personal-care.html?p=2
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Beauty\ \&\ Personal\ Care$

## c358dd6529a01a140edf
- **题面：** Browse Tools & Accessories in Beauty category
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /catalog/category/view/id/20/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:Beauty\ \&\ Personal\ Care|Tools\ \&\ Accessories)$

## c39966933178cd8c3756
- **题面：** View my order details for order #000000187
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /sales/order/view/order_id/187/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Order # 000000187$

## cd607128c0a32223b604
- **题面：** Go to My Account page
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /customer/account/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^My Account$

## cf4999bde780275b58cb
- **题面：** View details of the Intel NUC Kit Mini PC
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /intel-nuc-kit-nuc6i7kyk-mini-pc-no-power-cord.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:Intel\ NUC\ Kit\ NUC6i7KYK\ Mini\ PC\-no\ Power\ Cord)$

## d9dee57aa1e361c911d1
- **题面：** View my product reviews
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /review/customer/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^My Product Reviews$

## db147dc6bede0ae35635
- **题面：** Go to the List of cookies we collect section.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /privacy-policy-cookie-restriction-mode#list
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Privacy and Cookie Policy$

## e497369511069de0d3cd
- **题面：** View details for 5x40 Night Vision Monocular Telescopes Multifunctional IR Digital Night Vision Telescope Camera with Video Recorder Camouflage Infrared Camera Hunting Night Vision Monocular Device.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /5x40-night-vision-monocular-telescopes-multifunctional-ir-digital-night-vision-telescope-camera-with-video-recorder-camouflage-infrared-camera-hunting-night-vision-monocular-device.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:5x40\ Night\ Vision\ Monocular\ Telescopes\ Multifunctional\ IR\ Digital\ Night\ Vision\ Telescope\ Camera\ with\ Video\ Recorder\ Camouflage\ Infrared\ Camera\ Hunting\ Night\ Vision\ Monocular\ Device)$

## e63887a2e5fee9b8851b
- **题面：** Shop for items in the Clothing, Shoes & Jewelry category.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /clothing-shoes-jewelry.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Clothing,\ Shoes\ \&\ Jewelry$

## e916b770cf6c9961fb69
- **题面：** Navigate to the Hunting & Fishing category in Sports & Outdoors.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /catalog/category/view/id/25/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:Hunting\ \&\ Fishing|Sports\ \&\ Outdoors)$

## eb659eedcb65a365df65
- **题面：** Browse Sports & Outdoors products
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /sports-outdoors.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Sports\ \&\ Outdoors(?: Items .*)?$

## edfe76ffbd372ca622ae
- **题面：** Read reviews for Nightfox Vulpes Handheld Digital Night Vision Goggles.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /nightfox-vulpes-handheld-digital-night-vision-goggles-integrated-laser-rangefinder-full-high-definition-fhd-1080p-sensor-records-video-audio-220yd-range-6x-magnification-hunting-security.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Nightfox\ Vulpes\ Handheld\ Digital\ Night\ Vision\ Goggles\ \|\ Integrated\ Laser\ Rangefinder\ \|\ Full\ High\ Definition\ FHD\ 1080p\ Sensor\ \|\ Records\ Video\ \+\ Audio\ \|\ 220yd\ Range,\ 6x\ Magnification\ \|\ Hunting,\ Security$

## ee04c15561b881b0bf46
- **题面：** View the "Power of Positivity" Eye Shadow Palette product details
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /power-of-positivity-eye-shadow-palette-gluten-free-vegan-cruelty-free.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:'Power\ of\ Positivity'\ Eye\ Shadow\ Palette\ \|\ Gluten\ Free\ \|\ Vegan\ \|\ Cruelty\ Free)$

## f07d85b36aa89cf41e5b
- **题面：** Go to the product page of "Bushnell 743333 Boresighter with Case & ARbors,Black".
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /bushnell-743333-boresighter-with-case-arbors-black.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Bushnell\ 743333\ Boresighter\ with\ Case\ \&\ ARbors,Black$

## f792d5b646924f60298a
- **题面：** Check your recently ordered items
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /customer/account/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^My Account$

## fadb8e6b2ed3664b20d6
- **题面：** View Contact Us page.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /contact/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Contact Us$

## fdd86ebe9fbff3977476
- **题面：** Visit Newsletter Subscriptions page.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /newsletter/manage/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Newsletter Subscription$

## 18972d3400c722a4ffea
- **题面：** Go to the memes forum page to view its content.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /f/memes
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:/f/)?memes$

## 1b7cc1a2a3bded53a92c
- **题面：** Navigate to the Forums page.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /forums
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^List of forums$

## 27c63bcda6ea5f513130
- **题面：** Navigate to the movies forum to discuss films, movie news, and cinema.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /f/movies
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:/f/)?movies$

## 2ab43456dd85145f8cc8
- **题面：** Explore the memes forum
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /f/memes
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:/f/)?memes$

## 3112149ed88814016dc3
- **题面：** Explore the science forum for scientific discussions.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /f/science
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:/f/)?science$

## 351cef41c763fe65bb86
- **题面：** Navigate to the page for creating a new wiki page.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /wiki/_create
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Create new page$

## 377df3ac94c013710664
- **题面：** Browse forums in alphabetical order.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /forums/all
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^All forums$

## 3d8eadee8a7a9377df5e
- **题面：** Sort forums by title.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /forums/by_title
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:All forums|List of forums)$

## 3e26458bd2eb43f20c5b
- **题面：** Browse the memes forum for humorous content.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /f/memes
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:/f/)?memes$

## 44b4afbbc9b99c36e9bb
- **题面：** Navigate to the joke page titled "My girlfriend left me because of my abandonment issues..."
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /f/Jokes/119862
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^My\ girlfriend\ left\ me\ because\ of\ my\ abandonment\ issues\.\.\.$

## 45a739d64fcb5d5d3833
- **题面：** Check your hidden forums.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /user/MarvelsGrantMan136/hidden_forums
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Hidden\ forums$

## 47bdbdea898616e0cc46
- **题面：** Go to the forums page.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /forums
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^List of forums$

## 49aa91c52b9c981c098f
- **题面：** Sort the forum list alphabetically by forum name
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /forums/all
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:All forums|List of forums)$

## 4af9ec625c89f92a8b85
- **题面：** Navigate to the food forum.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /f/food
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:/f/)?food$

## 5b52a8165650a66e8f37
- **题面：** Go back to the forums.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /forums
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^List of forums$

## 5d450bf7b0ba022de554
- **题面：** Change the view of forums from submissions to alphabetical
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /forums/all
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:All forums|List of forums)$

## 5dd565a907f19bcd45b5
- **题面：** Go back to the home page from the submission form
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Postmill$

## 60ff346de5439a79316a
- **题面：** Navigate to the homepage.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Postmill$

## 65cd35447dd878098c31
- **题面：** Go to page 2 of the forums list
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /forums/by_submissions/2
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^List of forums$

## 66126f96f8512e54a1c2
- **题面：** Sort posts in the movies forum by Most commented over all time to find the most discussed topics.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /f/movies/most_commented?t=all
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^/f/movies$

## 69c434d3c2127b3def0a
- **题面：** Browse forums by tags.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /tags
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Tags$

## 69d7c430e7b5c9272eb5
- **题面：** Navigate to the All pages section of the wiki.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /wiki/_all
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^All pages$

## 765eb522fe286cb0a66d
- **题面：** View the user profile of SashaGreatest.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /user/SashaGreatest
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^SashaGreatest$

## 810a12011686f67f627a
- **题面：** Sort the forums by creation date to see the newest forums first.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /forums/by_creation_date
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:All forums|List of forums)$

## 878413977cd9a814b942
- **题面：** Go to the LifeProTips forum
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /f/LifeProTips
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:/f/)?LifeProTips$

## 8bf1a6bbcea8351cd55b
- **题面：** View forums sorted alphabetically.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /forums/all
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^All forums$

## 8dbb7a62694a33a430cf
- **题面：** Go to the pics forum page to view its content.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /f/pics
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:/f/)?pics$

## 92f69c08511f177fb5b3
- **题面：** Explore the moderation log for the Music forum.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /f/Music/moderation_log
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Showing\ moderation\ log\ for\ /f/Music$

## 933db784845321b7cf50
- **题面：** Check recent changes in the Wiki.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /wiki/_recent
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Recent changes$

## 9d63ee81b6bbf16f0386
- **题面：** Navigate to the Create new page section to start creating a new wiki page.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /wiki/_create
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Create new page$

## 9df7d3935a696be1049a
- **题面：** Go to the second page of forum listings
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /forums/by_submissions/2
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^List of forums$

## a8d2697ced77921baa92
- **题面：** Browse forums in alphabetical order
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /forums/all
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^All forums$

## af31dc799e51ccad402c
- **题面：** Navigate to the Forums page to explore community discussions.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /forums
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^List of forums$

## b3bd93fe9fa6eb441da5
- **题面：** Search for posts about machine learning
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /search?q=machine+learning
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Search$

## b4f0486d4418ae0bca40
- **题面：** Navigate to page 2 of the forums list.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /forums/by_submissions/2
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^List of forums$

## bb07fa576f83587a108f
- **题面：** Use the native plain-text search for "upcoming movie releases" and display its local results. This is a literal search; no external release calendar is required.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /search?q=upcoming+movie+releases
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Search$

## bb3cdfd32d3103c63645
- **题面：** Go to the news forum.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /f/news
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:/f/)?news$

## be949364ea9b3305b0fd
- **题面：** View a user profile.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /user/MarvelsGrantMan136
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^.+$

## ca5a11acef0c0662cafb
- **题面：** Check your block list.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /user/MarvelsGrantMan136/block_list
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Block list$

## d2849c468c9d7f79fc4c
- **题面：** Navigate to the relationship_advice forum
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /f/relationship_advice
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:/f/)?relationship_advice$

## d62097dc3f906d29763c
- **题面：** Clear the current search and search for "skin care products"
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /search?q=skin+care+products
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Search$

## d79c8e87b72c40aadfa5
- **题面：** Navigate to the movies forum.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /f/movies
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:/f/)?movies$

## deea459bf06ce5b27eb7
- **题面：** View your user profile
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /user/MarvelsGrantMan136
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^MarvelsGrantMan136$

## e642e4b7d549e51f63fb
- **题面：** Check recent changes in the Wiki
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /wiki/_recent
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Recent changes$

## e9867fbfbd0d5464fd39
- **题面：** View all wiki pages
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /wiki/_all
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^All pages$

## f7188e2322661c71283f
- **题面：** View forums in Alphabetical order.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /forums/all
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:All forums|List of forums)$

## f8ad6d31e9aeed13d548
- **题面：** Navigate to the Alphabetical view to see forums listed in alphabetical order.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /forums/all
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^All forums$

## f94fd0a85e1d2b24568c
- **题面：** Open the Submit page to create a new post
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /submit
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Create submission$

## f9d2a2c865817e89de70
- **题面：** Visit the gaming forum to see gaming-related discussions
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /f/gaming
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:/f/)?gaming$

## ff1288a318ead65fce2e
- **题面：** Access the homepage.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Postmill$

## 1f55e7d6982e23b0ace1
- **题面：** Navigate to the SYSTEM section of the admin panel.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达菜单】到达菜单 System

## 2a2a147a398f0b25f455
- **题面：** Navigate to the Customers section to manage customer accounts, groups, and segments.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达菜单】到达菜单 Customers

## 365168956a85f49b0695
- **题面：** Navigate to the Content section in the Magento admin panel.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达菜单】到达菜单 Content

## 4c9fb5d9afb995d13098
- **题面：** Navigate to the Catalog section from the credit memo view
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达菜单】到达菜单 Catalog

## 4d965044bc6a00b01638
- **题面：** Navigate to the Marketing section to manage promotions.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达菜单】到达菜单 Marketing

## 512eed77abee4b8ed8b6
- **题面：** Navigate to the Stores section to manage configuration, payment methods, taxes, and shipping settings.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达菜单】到达菜单 Stores

## 60826839b32ee9905dc0
- **题面：** View Reports.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达菜单】到达菜单 Reports

## 62ff49cb0c1dc47264cb
- **题面：** Navigate to the Reports section in Magento Admin.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达菜单】到达菜单 Reports

## 63a6e7044e415bed00d6
- **题面：** Navigate to the Sales section from the credit memo view.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达菜单】到达菜单 Sales

## 68d169e13d19a5c305b5
- **题面：** Navigate to the Sales section to manage orders, invoices, and shipments.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达菜单】到达菜单 Sales

## 7cab57f1d5d8ccb86777
- **题面：** Navigate to the Catalog section to manage products and categories.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达菜单】到达菜单 Catalog

## 90c5c245601840fdfb50
- **题面：** Go to the Sales section.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达菜单】到达菜单 Sales

## 99f7e4b784cfdec12cb4
- **题面：** Navigate to the Sales section.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达菜单】到达菜单 Sales

## 9f87eaf8772bea881d3e
- **题面：** Check the MARKETING section for promotional activities.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达菜单】到达菜单 Marketing

## ba2aad0bc3217100b5cb
- **题面：** Enter the System section from the Customers page.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达菜单】到达菜单 System

## c087db2325986747c17f
- **题面：** Navigate to the Sales section in the Magento Admin panel.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达菜单】到达菜单 Sales

## d11cf9048e5fb0540986
- **题面：** Navigate to the SALES section of the Magento Admin panel.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达菜单】到达菜单 Sales

## e8ffde6fb3307d42d939
- **题面：** Navigate to the Content section from the credit memo view page.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达菜单】到达菜单 Content

## 3d11daa68b8c93f5858e
- **题面：** View details of the Plus Size Lingerie item in my cart
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /plus-size-lingerie-for-women-sexy-for-sex-naughty-eyelash-lace-bodysuit-naughty-mesh-one-piece-teddy-bodysuit-outfits.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:Plus\ Size\ Lingerie\ for\ Women\ Sexy\ for\ Sex\ Naughty\ Eyelash\ Lace\ Bodysuit\ Naughty\ Mesh\ One\ Piece\ Teddy\ Bodysuit\ Outfits)$

## b4045013dcdbe0e6f5f9
- **题面：** Navigate to the reviews section for the Pre-baked Gingerbread House Kit Value Pack.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /pre-baked-gingerbread-house-kit-value-pack-17-oz-pack-of-2-total-34-oz.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Pre\-baked\ Gingerbread\ House\ Kit\ Value\ Pack,\ 17\ oz\.,\ Pack\ of\ 2,\ Total\ 34\ oz\.$

## 505e04c5eb5201102f65
- **题面：** Shop for Home & Kitchen products.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /home-kitchen.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Home\ \&\ Kitchen$

## 440a8b1af94cf76ed2bf
- **题面：** View merged merge requests assigned to your account.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /dashboard/merge_requests?state=merged&assignee_username=byteblaze
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Merge requests$

## 9819a41cd3b66bded28f
- **题面：** View issue #105 about Python 2.7 compatibility in youfou/wxpy.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /youfou/wxpy/-/issues/105
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^python2\.7\ FileNotFoundError$

## b1dc035ba13c6766daea
- **题面：** From the current Explore projects page, open your personal Projects dashboard home showing your projects. Leave that dashboard home open, rather than the Starred projects collection.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /
  - G2 【标题/身份匹配】页面标题/目标身份匹配 Projects · Dashboard · GitLab$

## bf43becccb2cb0f30d70
- **题面：** View all merge requests assigned to your account regardless of status.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /dashboard/merge_requests?state=all&assignee_username=byteblaze
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Merge requests$

## eb79e47b111e0d6f19e0
- **题面：** View open issues for checkstyle/checkstyle.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /checkstyle/checkstyle/-/issues?state=opened
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Issues · .+ / checkstyle · GitLab$

## 54066c2710d43c3a8205
- **题面：** Display the local About OpenStreetMap page. Completion means that the local introduction page is open.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /about
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^OpenStreetMap\ provides\ map\ data\ for\ thousands\ of\ websites,\ mobile\ apps,\ and\ hardware\ devices$

## 81ef7b160b5471ddc8a1
- **题面：** Open the Stores navigation menu.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达菜单】到达菜单 Stores

## bcc1737bbc829c7dcdfe
- **题面：** Open the Stores navigation menu.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达菜单】到达菜单 Stores

## 05680da53589ba4a7c39
- **题面：** Navigate to the Meta organization page.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /facebook

## 26258107ff993d1b71d7
- **题面：** Set up a GitLab group for personal use with "Just me" selected as the user
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【用户范围】用户范围选择为 "Just me"（仅本人）
  - G2 【保存生效】新建/添加已持久保存生效

## 286d4ac488bdcd446ffc
- **题面：** Set up a new GitLab group with internal visibility that can only be seen by logged-in users
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【可见性】可见性为 Internal
  - G2 【保存生效】新建/添加已持久保存生效

## 35c44498db3696d519d2
- **题面：** Create a top-level internal GitLab group with the custom URL path "local-training-internal-group".
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【可见性】可见性为 Internal
  - G2 【层级】群组层级为 top-level
  - G3 【路径】群组自定义 URL 路径为 "local-training-internal-group"
  - G4 【保存生效】新建/添加已持久保存生效

## 8c9eba264b7695102806
- **题面：** Learn about Keycloak test development
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /keycloak/keycloak/-/blob/main/docs/tests-development.md

## 290638fcb182c6960f48
- **题面：** Navigate to the Edit page on OpenStreetMap.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /edit
  - G2 【标题/身份匹配】页面标题/目标身份匹配 OpenStreetMap

## 325c3e9af6cf020c8d7f
- **题面：** View GPS traces uploaded by users
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /traces
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:Public\ GPS\ Traces|Public\ GPS\ Traces\ from\ LocalBenchmarkMapper|Viewing\ Trace\ local\-fixture\-park\-walk\.gpx|Viewing\ Trace\ local\-fixture\-riverside\-walk\.gpx)$

## 5ffe7246e3cf8cfd922f
- **题面：** Navigate to the upload page to add a new GPS trace to OpenStreetMap.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /traces/new
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Upload GPS Trace$

## 9d2a902babb8a46d7af8
- **题面：** View all GPS traces in the system.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /traces
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Public\ GPS\ Traces$

## d633bb692c21fc64b3d2
- **题面：** Check user-contributed GPS traces
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /traces
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:Public\ GPS\ Traces|Public\ GPS\ Traces\ from\ LocalBenchmarkMapper|Viewing\ Trace\ local\-fixture\-park\-walk\.gpx|Viewing\ Trace\ local\-fixture\-riverside\-walk\.gpx)$

## dde1229f74de8eaff67e
- **题面：** Browse user diaries to see contributors' experiences
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /diary
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:Users'\ Diaries|LocalBenchmarkMapper's\ Diary)$

## 50bdd7670ad731020527
- **题面：** Access User Diaries to read contributions.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /diary
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:Users'\ Diaries|LocalBenchmarkMapper's\ Diary)$

## 6586691f6d521f734fb0
- **题面：** Go to User Diaries to read about mapping activities from the community.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /diary
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:Users'\ Diaries|LocalBenchmarkMapper's\ Diary)$

## 7903acb30399bd5c8e05
- **题面：** View GPS traces from the GPS Traces page.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /traces
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:Public\ GPS\ Traces|Public\ GPS\ Traces\ from\ LocalBenchmarkMapper|Viewing\ Trace\ local\-fixture\-park\-walk\.gpx|Viewing\ Trace\ local\-fixture\-riverside\-walk\.gpx)$

## 80e2c362bab0c0442d21
- **题面：** Navigate to the OpenStreetMap homepage to view and explore maps
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】最终路径匹配目标 /
  - G2 【标题/身份匹配】页面标题/目标身份匹配 OpenStreetMap

## 023a2fa510545850eb60
- **题面：** Navigate to the DASHBOARD section of the admin panel.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】到达目标路径 /admin/dashboard/

## 0f020cbe715ac4a4d3ee
- **题面：** View and manage the Newsletter Queue for scheduled newsletters.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】到达目标路径 /newsletter/queue/

## 0fb31150596e043a7b65
- **题面：** Access the Transactions page to view payment processing history.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】到达目标路径 /sales/transactions/

## 1504f933385d5875e433
- **题面：** Navigate to create a new order.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】到达目标路径 /sales/order_create/

## 1f384c086d7233075fd8
- **题面：** Manage Billing Agreements.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】到达目标路径 /paypal/billing_agreement/

## 210145e7cb201110773f
- **题面：** Review the Login as Customer Log to see customer impersonation history
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】到达目标路径 /loginascustomer_log/log/index/

## 219d5b7acca30aefac53
- **题面：** Go to the Invoices section to manage store invoices
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】到达目标路径 /sales/invoice/

## 317565140066c12a9fd1
- **题面：** Go to the Widgets section to manage dynamic content elements
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】到达目标路径 /admin/widget_instance/

## 55845d3547aea21f1201
- **题面：** Navigate to the Billing Agreements page from the credit memo view
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】到达目标路径 /paypal/billing_agreement/

## 5d4873df89f5e36118a2
- **题面：** Navigate to the Notifications page to check system messages in the Magento Admin panel.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】到达目标路径 /admin/notification/

## 60075b8f15e63a1dc247
- **题面：** Go to the Categories section to organize the product catalog structure.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】到达目标路径 /catalog/category/

## 63913433d3077454369f
- **题面：** Check transaction history in the Transactions section
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】到达目标路径 /sales/transactions/

## 66a8efa568e2eec512cb
- **题面：** Check billing agreements with payment processors
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】到达目标路径 /paypal/billing_agreement/

## 73b9d165f08c9d60698f
- **题面：** View and manage Orders.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】到达目标路径 /sales/order/

## 81c82aa9b0a3609817b8
- **题面：** Go to the Categories management page
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】到达目标路径 /catalog/category/

## 85fdcdfa1a439c09c824
- **题面：** Navigate to the All Customers page to view and manage customer accounts.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】到达目标路径 /customer/index/

## 93942ab445a0cf91d79e
- **题面：** Go to the Categories section to organize the product catalog
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】到达目标路径 /catalog/category/

## a64a27ddf43d3a630c48
- **题面：** View Search Terms
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】到达目标路径 /search/term/index/

## a89ded491febf7ffc3d3
- **题面：** Open the Configuration page under Stores.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】到达目标路径 /admin/system_config/edit/

## aacb0cf0ec9097d39768
- **题面：** Click the "Create New Order" button to initiate a new sales order.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】到达目标路径 /sales/order_create/

## b651665d4200ca9ebc50
- **题面：** Manage customer groups in the Customer Groups section
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】到达目标路径 /customer/group/

## c3c17bbe2a53f17dd65e
- **题面：** Navigate to the Orders page to view all customer orders
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】到达目标路径 /sales/order/

## c40a2de539a9df0228a8
- **题面：** View the Design Schedule for planned theme changes.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】到达目标路径 /admin/system_design/

## c918aa067d6ff2e8dcbf
- **题面：** Go to the Invoices section to manage billing documents.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】到达目标路径 /sales/invoice/

## c9acc533c08f3ef98eb2
- **题面：** Navigate to the Products page to manage store products and inventory.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】到达目标路径 /catalog/product/

## d7c3acc1e325e037b235
- **题面：** Open the native Order Count Report in Customers reports. No numerical answer or date-range customization is required for this local training variant.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】到达目标路径 /reports/report_customer/orders/

## dd96d116c1dbb641e13a
- **题面：** Navigate to the Customer Groups page to manage customer categories and tax classes.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】到达目标路径 /customer/group/

## e6f68ee329b1294b8a3f
- **题面：** Navigate to the notifications page to check system alerts.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】到达目标路径 /admin/notification/

## ef161ad432f390ac315c
- **题面：** View Product Reviews report.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】到达目标路径 /reports/report_review/product/

## fd8855036a41db3107f3
- **题面：** Access the Media Gallery to manage website images and media files
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：binary）
  - G1 【到达目标路径】到达目标路径 /media_gallery/media/index/

## 00de3e4838fad62957df
- **题面：** How many reviews does the "Custom Jersey Style St Patrick's Day T Shirts" product have and what is its rating?
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【评论数】评论数与参考精确一致
  - G2 【评分】评分与参考精确一致

## 01aeb9ebc09ef6d46c3d
- **题面：** For this local training variant, Select shipments #000000001 and #000000002, and download their packing slips together as a PDF.
- **分支：** admin_contract_rules.checks:pdf（源：non-binary）
  - G1 【每个指定运单的完整装箱单】每个指定运单的完整装箱单与参考精确一致

## 02623a13789d0ba87796
- **题面：** Find my default billing address information
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【完整姓名正确】完整姓名正确与参考精确一致
  - G2 【电话正确】电话正确与参考精确一致
  - G3 【完整地址】完整地址各字段（street, city, region, postal_code, country_code）与参考精确一致

## 043df48c57af4a1b4de8
- **题面：** For this local training variant, create a product attribute with label Training Color, attribute code training_color and Text Field input type. Save it without changing the existing color attribute.
- **分支：** admin_contract_rules.checks:create（源：non-binary）
  - G1 【实际新增并保存一个本任务可唯一绑定的有效对象】实际新增并保存一个本任务可唯一绑定的有效对象，与题面要求精确一致
  - G2 【属性代码正确】属性代码正确与参考精确一致
  - G3 【属性标签正确】属性标签正确与参考精确一致
  - G4 【输入类型正确】输入类型正确与参考精确一致

## 05adaa3aae957f2c3dc0
- **题面：** Check the shipping method and cost for my order
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【配送方式】配送方式与参考精确一致
  - G2 【运费】运费与参考精确一致

## 05c4cabeb5f7296af901
- **题面：** For this local training variant, select order #000000002 and download its packing slip PDF.
- **分支：** admin_contract_rules.checks:pdf（源：non-binary）
  - G1 【订单日期】订单日期，与题面要求精确一致
  - G2 【账单和收货对象及完整地址】账单和收货对象及完整地址，与题面要求精确一致
  - G3 【支付方式、配送方式及运费】支付方式、配送方式及运费，与题面要求精确一致
  - G4 【商品名称、SKU、数量及规格】商品名称、SKU、数量及规格，与题面要求精确一致

## 06d6dd1b987d04ba2032
- **题面：** Create and save a new customer named Training Customer with email admin-06d6dd1b987d04ba2032@example.test and customer group Wholesale Customers. Keep valid defaults for unspecified optional fields.
- **分支：** admin_contract_rules.checks:create（源：non-binary）
  - G1 【实际新增并保存一个本任务可唯一绑定的有效对象】实际新增并保存一个本任务可唯一绑定的有效对象，与题面要求精确一致
  - G2 【完整姓名正确】完整姓名正确与参考精确一致
  - G3 【邮箱正确】邮箱正确与参考精确一致
  - G4 【客户组正确】客户组正确与参考精确一致

## 0adfc625f5e41270cf99
- **题面：** Create a new customer account for John Smith with email johnsmith@example.com
- **分支：** admin_contract_rules.checks:create（源：non-binary）
  - G1 【实际新增并保存一个本任务可唯一绑定的有效对象】实际新增并保存一个本任务可唯一绑定的有效对象，与题面要求精确一致
  - G2 【完整姓名正确】完整姓名正确与参考精确一致
  - G3 【邮箱正确】邮箱正确与参考精确一致

## 0b88605b2114cefbb677
- **题面：** Export the list of customers to a CSV file
- **分支：** admin_contract_rules.checks:export（源：non-binary）
  - G1 【名称正确】名称正确与参考精确一致
  - G2 【邮箱正确】邮箱正确与参考精确一致

## 0d50993fbdf6d32994bb
- **题面：** Verify the shipping address details for Emma Lopez.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【每条原地址行的完整正文和行号对应正确】每条原地址行的完整正文和行号对应正确与参考精确一致

## 0f1aa3a36555035eb8c0
- **题面：** Set Blue T-Shirt visibility to Catalog, Search and save.
- **分支：** admin_contract_rules.checks:update（源：non-binary）
  - G1 【保存的商品可见性包含Catalog】保存的商品可见性包含Catalog，与题面要求精确一致
  - G2 【保存的商品可见性包含Search】保存的商品可见性包含Search，与题面要求精确一致

## 10cdae7af1322acbc6a3
- **题面：** For this local training variant, the following are supplied training product facts. Set the Sony Headphones Description to exactly the text inside the quotation marks, excluding the quotation marks: "Sony Headphones feature a lightweight adjustable headband and wired stereo playback. Specifications: 3.5 mm wired connection; no wireless connectivity.". Save the change.
- **分支：** admin_contract_rules.checks:update（源：non-binary）
  - G1 【轻便可调头带】轻便可调头带与参考精确一致

## 1317a2b60d5f27b6f640
- **题面：** Find out what categories are available under Sports & Outdoors
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【每个正确、不重复的要求列表成员】每个正确、不重复的要求列表成员与参考精确一致

## 13914fd7d1bf94533456
- **题面：** Find out what technologies are used in The A11Y Project website.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【每个正确、不重复的要求列表成员】每个正确、不重复的要求列表成员与参考精确一致

## 158bf9a1de57867a2ac4
- **题面：** Find the default billing address for Emma Lopez.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【电话正确】电话正确与参考精确一致
  - G2 【完整地址】完整地址各字段（street, city, region, postal_code, country_code）与参考精确一致

## 1820a8409805e0f44e63
- **题面：** Find repositories with MIT License on the current page
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【每个正确、不重复的要求列表成员】每个正确、不重复的要求列表成员与参考精确一致

## 1a50d30e5d14712ec9d0
- **题面：** For this local training variant, retrieve the default billing phone number and ZIP code of Jane Doe (jane.doe@gmail.com). The initial snapshot places this existing customer in VIP Customers.
- **分支：** admin_contract_rules.checks:query（源：non-binary）
  - G1 【电话】电话与参考精确一致
  - G2 【完整地址】完整地址各字段（postcode）与参考精确一致

## 1af036a267a8429d2fc9
- **题面：** Search for customers living in New York state
- **分支：** admin_contract_rules.checks:collection_query（源：non-binary）
  - G1 【完整姓名正确】完整姓名正确与参考精确一致
  - G2 【邮箱正确】邮箱正确与参考精确一致

## 1b482d1d92765f6cb6d9
- **题面：** Retrieve the latest commit message for the a11yproject.com repository.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【提交说明中的变更动作Update】提交说明中的变更动作Update，与题面要求精确一致
  - G2 【提交说明中的完整受影响文件名】提交说明中的完整受影响文件名，与题面要求精确一致

## 1bfe6203aa85e3af13c0
- **题面：** For this local training variant, Subscribe these customers to the newsletter: adam.garcia@gmail.com, alex.martin@gmail.com.
- **分支：** admin_contract_rules.checks:bulk_update（源：non-binary）
  - G1 【每位指定客户的请求修改已保存且生效】每位指定客户的请求修改已保存且生效与参考精确一致

## 1d095aa28f753677a069
- **题面：** Explore available data sources for downloading OpenStreetMap data.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【名称正确】名称正确与参考精确一致
  - G2 【描述正确】描述正确与参考精确一致

## 1d838691d0e90160f0c6
- **题面：** Check which customer groups are available for new customer creation
- **分支：** admin_contract_rules.checks:collection_query（源：non-binary）
  - G1 【每个正确的目标记录/列表成员】每个正确的目标记录/列表成员与参考精确一致

## 237e143cb3de228b8d84
- **题面：** Check what markdown formatting options are available for post creation
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【要求的格式功能覆盖完整】要求的格式功能覆盖完整与参考精确一致
  - G2 【各功能对应语法正确】各功能对应语法正确与参考精确一致

## 23b872112e21eec243e8
- **题面：** Report the five most recently placed orders, including order number, customer name, and grand total. Break timestamp ties by ascending internal order ID.
- **分支：** admin_contract_rules.checks:collection_query（源：non-binary）
  - G1 【目标集合覆盖完整且记录编号正确】目标集合覆盖完整且记录编号正确与参考精确一致
  - G2 【客户姓名正确】客户姓名正确与参考精确一致
  - G3 【总额正确】总额正确与参考精确一致

## 2642eb4f6e622c2ff448
- **题面：** Check the total distance and estimated travel time for the current route
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【距离】距离与参考精确一致
  - G2 【时长】时长与参考精确一致

## 2808ca675a8231d9c01d
- **题面：** Export the current customer data to a file.
- **分支：** admin_contract_rules.checks:export（源：non-binary）
  - G1 【名称正确】名称正确与参考精确一致
  - G2 【邮箱正确】邮箱正确与参考精确一致

## 294e440ada4fcc494444
- **题面：** Find all products with less than 100 units in stock
- **分支：** admin_contract_rules.checks:collection_query（源：non-binary）
  - G1 【目标集合覆盖完整且SKU正确】目标集合覆盖完整且SKU正确与参考精确一致
  - G2 【名称正确】名称正确与参考精确一致
  - G3 【数量正确】数量正确与参考精确一致

## 2cf60b2bee0001aff88b
- **题面：** Create and save a new customer named Training Customer with email admin-2cf60b2bee0001aff88b@example.test. Keep valid defaults for unspecified optional fields.
- **分支：** admin_contract_rules.checks:create（源：non-binary）
  - G1 【实际新增并保存一个本任务可唯一绑定的有效对象】实际新增并保存一个本任务可唯一绑定的有效对象，与题面要求精确一致
  - G2 【完整姓名正确】完整姓名正确与参考精确一致
  - G3 【邮箱正确】邮箱正确与参考精确一致

## 2d4229b6bc703e398bf4
- **题面：** For this local training variant, Unsubscribe all customers whose default billing address state is Florida from the newsletter.
- **分支：** admin_contract_rules.checks:bulk_update（源：non-binary）
  - G1 【每位指定客户的请求修改已保存且生效】每位指定客户的请求修改已保存且生效与参考精确一致

## 2e437c6ebc27184225c5
- **题面：** Review existing CMS pages and their content status
- **分支：** admin_contract_rules.checks:collection_query（源：non-binary）
  - G1 【标题正确】标题正确与参考精确一致
  - G2 【启用状态正确】启用状态正确与参考精确一致

## 2ebb8e234b090307f6ac
- **题面：** Export credit memo data to a CSV file.
- **分支：** admin_contract_rules.checks:export（源：non-binary）
  - G1 【退款单编号】退款单编号，与题面要求精确一致
  - G2 【退款单创建日期】退款单创建日期，与题面要求精确一致
  - G3 【关联订单编号】关联订单编号，与题面要求精确一致
  - G4 【订单创建日期】订单创建日期，与题面要求精确一致
  - G5 【账单姓名及完整账单地址】账单姓名及完整账单地址，与题面要求精确一致
  - G6 【退款单状态】退款单状态，与题面要求精确一致
  - G7 【基础币种退款金额】基础币种退款金额，与题面要求精确一致
  - G8 【订单状态】订单状态，与题面要求精确一致
  - G9 【购买商店/站点】购买商店/站点，与题面要求精确一致
  - G10 【完整收货地址】完整收货地址，与题面要求精确一致
  - G11 【客户完整姓名】客户完整姓名，与题面要求精确一致
  - G12 【客户邮箱】客户邮箱，与题面要求精确一致
  - G13 【客户分组】客户分组，与题面要求精确一致
  - G14 【支付方式】支付方式，与题面要求精确一致
  - G15 【配送方式信息】配送方式信息，与题面要求精确一致
  - G16 【退款小计】退款小计，与题面要求精确一致
  - G17 【配送及手续费】配送及手续费，与题面要求精确一致
  - G18 【退款调整金额】退款调整金额，与题面要求精确一致
  - G19 【调整费用】调整费用，与题面要求精确一致
  - G20 【基础币种订单总额】基础币种订单总额，与题面要求精确一致

## 3023c4dedd7221a00b2c
- **题面：** Create and save a simple product named Training Product 3023c4, SKU TRAIN-3023c4dedd7221a00b2c, price 9.99. Keep valid defaults for unspecified settings.
- **分支：** admin_contract_rules.checks:create（源：non-binary）
  - G1 【实际新增并保存一个本任务可唯一绑定的有效对象】实际新增并保存一个本任务可唯一绑定的有效对象，与题面要求精确一致
  - G2 【名称正确】名称正确与参考精确一致
  - G3 【SKU正确】SKU正确与参考精确一致
  - G4 【价格正确】价格正确与参考精确一致

## 31630bd2bca463862944
- **题面：** Retrieve the project description for cloud-to-butt.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【Chrome扩展这一软件类型】Chrome扩展这一软件类型与参考精确一致

## 32f1684e1634c615f215
- **题面：** View all available color options for the St Patricks Day T-Shirt
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【每个正确、不重复的要求列表成员】每个正确、不重复的要求列表成员与参考精确一致

## 365c8f7271b76bca1522
- **题面：** View the turn-by-turn directions for the current route
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【每条要求返回的路线指引内容和序号正确】每条要求返回的路线指引内容和序号正确与参考精确一致

## 366af9836afa8987f721
- **题面：** Export the list of orders to a CSV file.
- **分支：** admin_contract_rules.checks:export（源：non-binary）
  - G1 【记录编号正确】记录编号正确与参考精确一致
  - G2 【总额正确】总额正确与参考精确一致

## 39289e43a355500e8c35
- **题面：** Report the five search terms with the highest number of uses, including each query text and its number of uses. Include all ties at the cutoff only if they fit within the first five records ordered by query ID.
- **分支：** admin_contract_rules.checks:collection_query（源：non-binary）
  - G1 【搜索词正确】搜索词正确与参考精确一致
  - G2 【使用次数正确】使用次数正确与参考精确一致

## 3a321611e2d35a0bd239
- **题面：** Read and report the project description for The A11Y Project / a11yproject.com.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【社区推动的项目性质】社区推动的项目性质与参考精确一致

## 3d44ea22ddda30c59630
- **题面：** Compare the prices of night vision devices on this page.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【名称正确】名称正确与参考精确一致
  - G2 【价格正确】价格正确与参考精确一致

## 40d3da9f6369adbe5def
- **题面：** For this local training variant, update the email template named "Training Existing Email". Save subject "Updated customer information" and body exactly "Please review your account information in our training store.".
- **分支：** admin_contract_rules.checks:update（源：non-binary）
  - G1 【主题正确】主题正确与参考精确一致
  - G2 【正文正确】正文正确与参考精确一致

## 40fbee5ad66e332b21a4
- **题面：** List all items currently in the shopping cart.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【每个正确、不重复的要求列表成员】每个正确、不重复的要求列表成员与参考精确一致

## 41b2004f1c9ede24b496
- **题面：** View the available shipping methods for my order
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【承运商与配送方式的完整组合】承运商与配送方式的完整组合与参考精确一致
  - G2 【各配送方式的对应费用正确】各配送方式的对应费用正确与参考精确一致

## 44a8860ebdd452352176
- **题面：** Get the rating and number of reviews for the Pre-baked Gingerbread House Kit Value Pack.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【评分】评分与参考精确一致
  - G2 【评论数】评论数与参考精确一致

## 44e44103a11d8563d0e1
- **题面：** For this local training variant, reference date is September 30, 2026. Save Test Product special price 19.99 from October 5 through October 11, 2026.
- **分支：** admin_contract_rules.checks:update（源：non-binary）
  - G1 【促销价格正确】促销价格正确与参考精确一致
  - G2 【促销开始日期正确】促销开始日期正确与参考精确一致
  - G3 【促销结束日期正确】促销结束日期正确与参考精确一致

## 45121a4e0f96f3cfecd2
- **题面：** Find all forums that start with the letter B
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【每个正确、不重复的要求列表成员】每个正确、不重复的要求列表成员与参考精确一致

## 4610743cece3a992dce5
- **题面：** Find all orders placed by Adam Garcia
- **分支：** admin_contract_rules.checks:collection_query（源：non-binary）
  - G1 【每个正确的目标记录/列表成员】每个正确的目标记录/列表成员与参考精确一致

## 4669e83f3f415914e5aa
- **题面：** Create a customer group named "VIP Customers" and exclude the "Main Website" from this group.
- **分支：** admin_contract_rules.checks:create（源：non-binary）
  - G1 【实际新增并保存一个本任务可唯一绑定的有效对象】实际新增并保存一个本任务可唯一绑定的有效对象，与题面要求精确一致
  - G2 【名称正确】名称正确与参考精确一致
  - G3 【网站排除配置正确】网站排除配置正确与参考精确一致

## 46c0329e4f0e6684aa4e
- **题面：** Discover which websites or projects are currently using the a11y-syntax-highlighting themes
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【每个正确、不重复的要求列表成员】每个正确、不重复的要求列表成员与参考精确一致

## 48f12d69e2ac92bbc655
- **题面：** Export all order data from the Magento Admin panel.
- **分支：** admin_contract_rules.checks:export（源：non-binary）
  - G1 【记录编号正确】记录编号正确与参考精确一致
  - G2 【总额正确】总额正确与参考精确一致

## 4b5dc32a78f627e9c01a
- **题面：** Share the current map view using a short link
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【短链接所编码的完整地图中心，经纬度同时正确】短链接所编码的完整地图中心，经纬度同时正确，与题面要求精确一致
  - G2 【同一短链接编码的缩放级别】同一短链接编码的缩放级别，与题面要求精确一致

## 4e31cc1527b413e6648e
- **题面：** List all OpenStreetMap Local Chapters.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【每个正确、不重复的要求列表成员】每个正确、不重复的要求列表成员与参考精确一致

## 4ec7495e3a9efa099bea
- **题面：** For this local training variant, save category ID 2 meta title as "Training Store Catalog" and meta description as "Browse the Training Store product catalog."
- **分支：** admin_contract_rules.checks:update（源：non-binary）
  - G1 【元标题正确】元标题正确与参考精确一致
  - G2 【元描述正确】元描述正确与参考精确一致

## 502148f62db1683b9bba
- **题面：** Export the current order data to a CSV file on the Magento Admin page.
- **分支：** admin_contract_rules.checks:export（源：non-binary）
  - G1 【记录编号正确】记录编号正确与参考精确一致
  - G2 【总额正确】总额正确与参考精确一致

## 50bb0903de04753ac2ac
- **题面：** Retrieve the step-by-step directions from 40.7900, -73.9600 to 40.6530, -73.9500.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【每条要求返回的路线指引内容和序号正确】每条要求返回的路线指引内容和序号正确与参考精确一致

## 50d1a73742dfe3e4ee1b
- **题面：** Check what formatting options are available for the submission body
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【要求的格式功能覆盖完整】要求的格式功能覆盖完整与参考精确一致
  - G2 【各功能对应语法正确】各功能对应语法正确与参考精确一致

## 550fd5ae26b1f06f5fd8
- **题面：** For this local training variant, the following are supplied training product facts. Set the Premium Leather Wallet Description to exactly the text inside the quotation marks, excluding the quotation marks: "Premium Leather Wallet: leather exterior, six card slots and one banknote compartment. Dimensions: 11 cm wide, 9 cm high and 2 cm deep.". Save the change.
- **分支：** admin_contract_rules.checks:update（源：non-binary）
  - G1 【皮革外部材质】皮革外部材质与参考精确一致

## 5786c998736d427970a6
- **题面：** Check the shipping address for the credit memo.
- **分支：** admin_contract_rules.checks:query（源：non-binary）
  - G1 【名 + 姓】名 + 姓与参考精确一致
  - G2 【街道地址】街道地址与参考精确一致
  - G3 【城市 + 州/地区 + 邮编 + 国家】城市 + 州/地区 + 邮编 + 国家与参考精确一致

## 586f3f8ccec8d42e4142
- **题面：** For this local training variant, create the email template named "Training Customer Update". Save subject "Your store update" and body exactly "Thank you for shopping at our training store.".
- **分支：** admin_contract_rules.checks:create（源：non-binary）
  - G1 【实际新增并保存一个本任务可唯一绑定的有效对象】实际新增并保存一个本任务可唯一绑定的有效对象，与题面要求精确一致
  - G2 【模板名称正确】模板名称正确与参考精确一致
  - G3 【主题正确】主题正确与参考精确一致
  - G4 【正文正确】正文正确与参考精确一致

## 5f6e00767032bff7429e
- **题面：** Describe how users can control their personal information.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【表单中的营销用途拒绝方式】表单中的营销用途拒绝方式与参考精确一致

## 6092ffb2a3014d7b5e02
- **题面：** Create and save a new customer named Training Customer with email admin-6092ffb2a3014d7b5e02@example.test and taxvat TRAINING-VAT-100. Keep valid defaults for unspecified optional fields.
- **分支：** admin_contract_rules.checks:create（源：non-binary）
  - G1 【实际新增并保存一个本任务可唯一绑定的有效对象】实际新增并保存一个本任务可唯一绑定的有效对象，与题面要求精确一致
  - G2 【完整姓名正确】完整姓名正确与参考精确一致
  - G3 【邮箱正确】邮箱正确与参考精确一致
  - G4 【税号正确】税号正确与参考精确一致

## 60f67c44bf1f5c01fa32
- **题面：** For this local restored-page task, read the dotmailer description on the Magento Marketplace page and return its exact description text. Stay on the local page; external partner websites are outside the task.
- **分支：** admin_contract_rules.checks:page_text_query（源：non-binary）
  - G1 【以邮件为核心的多渠道营销平台】以邮件为核心的多渠道营销平台与参考精确一致

## 620d3e05fa1c9ef6e951
- **题面：** Find projects that use the MIT license on the Explore page. Consider all non-archived projects accessible to the current account, across the complete project directory.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【每个正确、不重复的要求列表成员】每个正确、不重复的要求列表成员与参考精确一致

## 647cc7d981b85811507e
- **题面：** For this local training variant, Assign these five customers to VIP Customers: adam.garcia@gmail.com, alex.martin@gmail.com, alexander.thomas@hotmail.com, amanda.kim@gmail.com, anna.nguyen@yahoo.com.
- **分支：** admin_contract_rules.checks:bulk_update（源：non-binary）
  - G1 【每位指定客户的请求修改已保存且生效】每位指定客户的请求修改已保存且生效与参考精确一致

## 6539ca3a65bcebbf51e2
- **题面：** Edit the unsent newsletter with subject Training queued update. Save its body as The local training promotion starts on December 1, 2026. Keep it unsent; do not schedule or send it.
- **分支：** admin_contract_rules.checks:update（源：non-binary）
  - G1 【保存正文中的活动与开始语义：The local training promotion starts】保存正文中的活动与开始语义：The local training promotion starts，与题面要求精确一致
  - G2 【同一正文中的完整开始日期：December 1, 2026】同一正文中的完整开始日期：December 1, 2026，与题面要求精确一致

## 67f0d4e2c0b41fc6ccef
- **题面：** List all projects starred by the user.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【每个正确、不重复的要求列表成员】每个正确、不重复的要求列表成员与参考精确一致

## 690ff879812bbe4d14e5
- **题面：** Find all customers whose gender is Female and report their names and email addresses.
- **分支：** admin_contract_rules.checks:collection_query（源：non-binary）
  - G1 【目标集合覆盖完整且完整姓名正确】目标集合覆盖完整且完整姓名正确与参考精确一致
  - G2 【邮箱正确】邮箱正确与参考精确一致

## 6b630bcc794fbd170809
- **题面：** For this local training variant, create a custom URL rewrite in Default Store View: request path training-old-category, target path catalog/category/view/id/2, redirect type Permanent (301). Save it.
- **分支：** admin_contract_rules.checks:create（源：non-binary）
  - G1 【实际新增并保存一个本任务可唯一绑定的有效对象】实际新增并保存一个本任务可唯一绑定的有效对象，与题面要求精确一致
  - G2 【请求路径正确】请求路径正确与参考精确一致
  - G3 【目标路径正确】目标路径正确与参考精确一致
  - G4 【重定向类型正确】重定向类型正确与参考精确一致

## 6c8942d0a681b4fd513f
- **题面：** Explore alternative data download options for large areas.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【名称正确】名称正确与参考精确一致
  - G2 【描述正确】描述正确与参考精确一致

## 6ccae42e426d87785b76
- **题面：** Check what price ranges are available for Sports & Outdoors items
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【每个正确、不重复的要求列表成员】每个正确、不重复的要求列表成员与参考精确一致

## 6d9d8bc43ae2c1b8ef1a
- **题面：** For this local training variant, create and save a CMS block for later homepage use with identifier training_home_welcome, title Training Home Welcome, and body Welcome to the training store. Assign it to All Store Views. Publishing or inserting the block into a homepage is outside this task.
- **分支：** admin_contract_rules.checks:create（源：non-binary）
  - G1 【实际新增并保存一个本任务可唯一绑定的有效对象】实际新增并保存一个本任务可唯一绑定的有效对象，与题面要求精确一致
  - G2 【标识符正确】标识符正确与参考精确一致
  - G3 【标题正确】标题正确与参考精确一致
  - G4 【正文正确】正文正确与参考精确一致
  - G5 【分配到All Store Views】分配到All Store Views与参考精确一致

## 6eb3af9dd0b4842ac443
- **题面：** Compare the number of open issues between different projects
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【项目1的完整身份】项目1的完整身份与参考精确一致
  - G2 【项目1的未关闭issue数】项目1的未关闭issue数与参考精确一致

## 71a327bcbaf0135b6c69
- **题面：** Check what product was refunded in order #000000002
- **分支：** admin_contract_rules.checks:collection_query（源：non-binary）
  - G1 【目标集合覆盖完整且名称正确】目标集合覆盖完整且名称正确与参考精确一致
  - G2 【SKU正确】SKU正确与参考精确一致
  - G3 【数量正确】数量正确与参考精确一致

## 727b8a237690197b467e
- **题面：** For this local training variant, save Gaming Laptop meta title as "Gaming Laptop | Training Store" and meta description as "Explore the Gaming Laptop in the Training Store catalog."
- **分支：** admin_contract_rules.checks:update（源：non-binary）
  - G1 【元标题正确】元标题正确与参考精确一致
  - G2 【元描述正确】元描述正确与参考精确一致

## 79399fd63d733a51a9d7
- **题面：** Send the order email for order #000000002 to that order's customer through the local store. Completion means the new matching message is recorded by this training environment's local mail capture; delivery to an external inbox is not required. Leave the order unchanged.
- **分支：** admin_contract_rules.checks:mail（源：non-binary）
  - G1 【实际发送到指定订单客户的邮箱】实际发送到指定订单客户的邮箱与参考精确一致
  - G2 【同一邮件包含指定订单的原要求内容标识】同一邮件包含指定订单的原要求内容标识与参考精确一致

## 7b1058619b6bdffb1663
- **题面：** Create and save a simple product named Training Product 7b1058, SKU TRAIN-7b1058619b6bdffb1663, price 9.99. Keep valid defaults for unspecified settings.
- **分支：** admin_contract_rules.checks:create（源：non-binary）
  - G1 【实际新增并保存一个本任务可唯一绑定的有效对象】实际新增并保存一个本任务可唯一绑定的有效对象，与题面要求精确一致
  - G2 【名称正确】名称正确与参考精确一致
  - G3 【SKU正确】SKU正确与参考精确一致
  - G4 【价格正确】价格正确与参考精确一致

## 7b4161eaac57c41ed83d
- **题面：** Export the customer data as a CSV file.
- **分支：** admin_contract_rules.checks:export（源：non-binary）
  - G1 【名称正确】名称正确与参考精确一致
  - G2 【邮箱正确】邮箱正确与参考精确一致

## 7cf15a94c97d28cbe0f7
- **题面：** Create a new customer group named "VIP Customers" with Retail Customer tax class.
- **分支：** admin_contract_rules.checks:create（源：non-binary）
  - G1 【实际新增并保存一个本任务可唯一绑定的有效对象】实际新增并保存一个本任务可唯一绑定的有效对象，与题面要求精确一致
  - G2 【名称正确】名称正确与参考精确一致
  - G3 【税类正确】税类正确与参考精确一致

## 7d0076c89c2e731e77c8
- **题面：** For this local training variant, override the default USD currency symbol with US$ and save Currency Symbols.
- **分支：** admin_contract_rules.checks:update（源：non-binary）
  - G1 【默认作用域明确持久覆盖USD符号】默认作用域明确持久覆盖USD符号，与题面要求精确一致
  - G2 【同一作用域USD最终有效符号为US$】同一作用域USD最终有效符号为US$，与题面要求精确一致

## 7edbc4e6cbc6ddcc50cf
- **题面：** Find out what transportation modes are available for directions on OpenStreetMap.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【每个正确、不重复的要求列表成员】每个正确、不重复的要求列表成员与参考精确一致

## 8502336fbff28609722e
- **题面：** View the shipping details for order #000000001.
- **分支：** admin_contract_rules.checks:query（源：non-binary）
  - G1 【名 + 姓】名 + 姓与参考精确一致
  - G2 【街道地址】街道地址与参考精确一致
  - G3 【城市 + 州/地区 + 邮编 + 国家】城市 + 州/地区 + 邮编 + 国家与参考精确一致

## 85dadbc00c3440ad28a7
- **题面：** Create and save a new customer named Training Customer with email admin-85dadbc00c3440ad28a7@example.test. Keep valid defaults for unspecified optional fields.
- **分支：** admin_contract_rules.checks:create（源：non-binary）
  - G1 【实际新增并保存一个本任务可唯一绑定的有效对象】实际新增并保存一个本任务可唯一绑定的有效对象，与题面要求精确一致
  - G2 【完整姓名正确】完整姓名正确与参考精确一致
  - G3 【邮箱正确】邮箱正确与参考精确一致

## 87efc09382467a521c3b
- **题面：** Export the credit memo data as an Excel XML file.
- **分支：** admin_contract_rules.checks:export（源：non-binary）
  - G1 【退款单编号】退款单编号，与题面要求精确一致
  - G2 【退款单创建日期】退款单创建日期，与题面要求精确一致
  - G3 【关联订单编号】关联订单编号，与题面要求精确一致
  - G4 【订单创建日期】订单创建日期，与题面要求精确一致
  - G5 【账单姓名及完整账单地址】账单姓名及完整账单地址，与题面要求精确一致
  - G6 【退款单状态】退款单状态，与题面要求精确一致
  - G7 【基础币种退款金额】基础币种退款金额，与题面要求精确一致
  - G8 【订单状态】订单状态，与题面要求精确一致
  - G9 【购买商店/站点】购买商店/站点，与题面要求精确一致
  - G10 【完整收货地址】完整收货地址，与题面要求精确一致
  - G11 【客户完整姓名】客户完整姓名，与题面要求精确一致
  - G12 【客户邮箱】客户邮箱，与题面要求精确一致
  - G13 【客户分组】客户分组，与题面要求精确一致
  - G14 【支付方式】支付方式，与题面要求精确一致
  - G15 【配送方式信息】配送方式信息，与题面要求精确一致
  - G16 【退款小计】退款小计，与题面要求精确一致
  - G17 【配送及手续费】配送及手续费，与题面要求精确一致
  - G18 【退款调整金额】退款调整金额，与题面要求精确一致
  - G19 【调整费用】调整费用，与题面要求精确一致
  - G20 【基础币种订单总额】基础币种订单总额，与题面要求精确一致

## 8a587b258e1b2f7912a3
- **题面：** List all projects visible on the GitLab Explore page.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【每个正确、不重复的要求列表成员】每个正确、不重复的要求列表成员与参考精确一致

## 8a9442c36c0705cc4857
- **题面：** Generate a short link for sharing the current map location
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【短链接所编码的完整地图中心，经纬度同时正确】短链接所编码的完整地图中心，经纬度同时正确，与题面要求精确一致
  - G2 【同一短链接编码的缩放级别】同一短链接编码的缩放级别，与题面要求精确一致

## 8f5196ffd60a7f7dee3c
- **题面：** Verify if the order total of $365.42 is calculated correctly from the subtotal and shipping costs
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【商品小计】商品小计与参考精确一致
  - G2 【运费】运费与参考精确一致
  - G3 【订单总额 + 总额正确性】订单总额 + 总额正确性与参考精确一致

## 90171eca733558b91be8
- **题面：** For this local training variant, select order #000000002 and download its invoice PDF.
- **分支：** admin_contract_rules.checks:pdf（源：non-binary）
  - G1 【订单日期】订单日期，与题面要求精确一致
  - G2 【账单和收货对象及完整地址】账单和收货对象及完整地址，与题面要求精确一致
  - G3 【支付方式、配送方式及运费】支付方式、配送方式及运费，与题面要求精确一致
  - G4 【商品名称、SKU、数量及规格】商品名称、SKU、数量及规格，与题面要求精确一致
  - G5 【小计、税费、运费与总计】小计、税费、运费与总计，与题面要求精确一致

## 92aee5530a26d63ee39e
- **题面：** Find sports equipment under $100 on the Sports & Outdoors page.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【指出一个确实低于阈值的商品】指出一个确实低于阈值的商品与参考精确一致
  - G2 【该商品价格正确】该商品价格正确与参考精确一致

## 95ee0e2712ebe1df0764
- **题面：** Generate a list of customers who have confirmed their email address
- **分支：** admin_contract_rules.checks:collection_query（源：non-binary）
  - G1 【完整姓名正确】完整姓名正确与参考精确一致
  - G2 【邮箱正确】邮箱正确与参考精确一致

## 967848101ec725a2e28f
- **题面：** Find the license type for the project Karl Kroening / ffmpeg-python.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【项目许可证家族Apache】项目许可证家族Apache与参考精确一致

## 9ac8c191d8e0026c7a39
- **题面：** For this local training variant, reference date is September 30, 2026. Set Blue T-Shirt as new from September 30 through October 30, 2026 and save.
- **分支：** admin_contract_rules.checks:update（源：non-binary）
  - G1 【新品开始日期正确】新品开始日期正确与参考精确一致
  - G2 【新品结束日期正确】新品结束日期正确与参考精确一致

## 9cc731fdb292beb61a5e
- **题面：** For this local training variant, create Training Customer with email training.customer@example.test on Main Website and send the welcome email from Default Store View. Email delivery is captured in the isolated local mailbox.
- **分支：** admin_contract_rules.checks:create（源：non-binary）
  - G1 【实际新增并保存唯一可绑定的客户】实际新增并保存唯一可绑定的客户，与题面要求精确一致
  - G2 【新客户完整姓名正确】新客户完整姓名正确与参考精确一致
  - G3 【新客户邮箱正确】新客户邮箱正确与参考精确一致
  - G4 【请求的Main Website归属正确】请求的Main Website归属正确与参考精确一致
  - G5 【实际发送的欢迎邮件收件人正确】实际发送的欢迎邮件收件人正确与参考精确一致
  - G6 【同一封邮件的称呼及欢迎内容完整】同一封邮件的称呼及欢迎内容完整与参考精确一致

## 9e5f8a4ab82a3ef3d219
- **题面：** Find all customers located in Texas
- **分支：** admin_contract_rules.checks:collection_query（源：non-binary）
  - G1 【完整姓名正确】完整姓名正确与参考精确一致
  - G2 【邮箱正确】邮箱正确与参考精确一致

## 9f1a9b9ca85961ed9cdc
- **题面：** View the email addresses of all customers
- **分支：** admin_contract_rules.checks:collection_query（源：non-binary）
  - G1 【每个正确的目标记录/列表成员】每个正确的目标记录/列表成员与参考精确一致

## 9f2e3f4d60b9e2df2df2
- **题面：** Identify all customers from the United States with phone numbers in the 212 area code
- **分支：** admin_contract_rules.checks:collection_query（源：non-binary）
  - G1 【完整姓名正确】完整姓名正确与参考精确一致
  - G2 【邮箱正确】邮箱正确与参考精确一致

## 9f53f858718b01fac2eb
- **题面：** Provide details for the project yjlou / 2019-nCov including its description and number of stars.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【所使用的数据来源：Google Maps Timeline】所使用的数据来源：Google Maps Timeline与参考精确一致
  - G2 【项目星数】项目星数与参考精确一致

## a03f13a35cdfa2855e7d
- **题面：** Export the list of shipments using the Export button.
- **分支：** admin_contract_rules.checks:export（源：non-binary）
  - G1 【产物中每条正确的要求记录】产物中每条正确的要求记录与参考精确一致

## a15b1eb0903aef00a975
- **题面：** List the files present in the cloud-to-butt repository.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【每个正确、不重复的要求列表成员】每个正确、不重复的要求列表成员与参考精确一致

## a1b510d8e8901e742f78
- **题面：** Check what alternative download sources are available for OpenStreetMap data.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【名称正确】名称正确与参考精确一致
  - G2 【描述正确】描述正确与参考精确一致

## a3b7eedd09ab8fbc3bae
- **题面：** Check the shipping address for order #000000002
- **分支：** admin_contract_rules.checks:query（源：non-binary）
  - G1 【名 + 姓】名 + 姓与参考精确一致
  - G2 【街道地址】街道地址与参考精确一致
  - G3 【城市 + 州/地区 + 邮编 + 国家】城市 + 州/地区 + 邮编 + 国家与参考精确一致

## a4bd8f38e37459668308
- **题面：** For this local training variant, create a custom URL rewrite in Default Store View: request path training-catalog-entry, target path catalog/category/view/id/2, redirect type Permanent (301). Save it.
- **分支：** admin_contract_rules.checks:create（源：non-binary）
  - G1 【实际新增并保存一个本任务可唯一绑定的有效对象】实际新增并保存一个本任务可唯一绑定的有效对象，与题面要求精确一致
  - G2 【请求路径正确】请求路径正确与参考精确一致
  - G3 【目标路径正确】目标路径正确与参考精确一致
  - G4 【重定向类型正确】重定向类型正确与参考精确一致

## a67ffb7494750efde4d3
- **题面：** Find all products that have "Hoodie" in the name
- **分支：** admin_contract_rules.checks:collection_query（源：non-binary）
  - G1 【SKU正确】SKU正确与参考精确一致
  - G2 【名称正确】名称正确与参考精确一致

## a68151f38ec0ea3dd185
- **题面：** View all projects with the MIT license. Consider all non-archived projects accessible to the current account, across the complete project directory.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【每个正确、不重复的要求列表成员】每个正确、不重复的要求列表成员与参考精确一致

## a7e1ea92dd0e6d344bfe
- **题面：** Compare the estimated travel times between driving and cycling from New York City to Boston
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【驾车时长】驾车时长与参考精确一致
  - G2 【骑行时长】骑行时长与参考精确一致

## a98e4da9e07e8b372c7d
- **题面：** Provide details about the Pre-baked Gingerbread House Kit Value Pack.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【SKU】SKU与参考精确一致
  - G2 【价格】价格与参考精确一致
  - G3 【制造商】制造商与参考精确一致

## aa3f32f9b51bb452536c
- **题面：** List all items in the shopping cart with their quantities and prices.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【所有应有商品完整且无多余项】所有应有商品完整且无多余项与参考精确一致
  - G2 【各商品对应数量全部正确】各商品对应数量全部正确与参考精确一致
  - G3 【各商品对应单价全部正确】各商品对应单价全部正确与参考精确一致

## afacd2e2ed0b749f7af1
- **题面：** For this local training variant, create and save a subcategory named Training Subcategory directly under New Category Name.
- **分支：** admin_contract_rules.checks:create（源：non-binary）
  - G1 【实际新增并保存一个本任务可唯一绑定的有效对象】实际新增并保存一个本任务可唯一绑定的有效对象，与题面要求精确一致
  - G2 【名称正确】名称正确与参考精确一致
  - G3 【父分类归属正确】父分类归属正确与参考精确一致

## b0583d36f1dda1d88ac8
- **题面：** Find projects that use the MIT license. Consider all non-archived projects accessible to the current account, across the complete project directory.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【每个正确、不重复的要求列表成员】每个正确、不重复的要求列表成员与参考精确一致

## b22941cc28e820b8bc0c
- **题面：** Create and save a new customer named Training Customer with email admin-b22941cc28e820b8bc0c@example.test and taxvat TRAINING-VAT-101. Keep valid defaults for unspecified optional fields.
- **分支：** admin_contract_rules.checks:create（源：non-binary）
  - G1 【实际新增并保存一个本任务可唯一绑定的有效对象】实际新增并保存一个本任务可唯一绑定的有效对象，与题面要求精确一致
  - G2 【完整姓名正确】完整姓名正确与参考精确一致
  - G3 【邮箱正确】邮箱正确与参考精确一致
  - G4 【税号正确】税号正确与参考精确一致

## b3db05d3ef6a3075e584
- **题面：** Verify the selected shipping address for my current shopping cart. Do not place an order.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【每条原地址行的完整正文和行号对应正确】每条原地址行的完整正文和行号对应正确与参考精确一致

## b4f2a38f0daad2fcf5a6
- **题面：** Check the shipping address for shipment #000000001.
- **分支：** admin_contract_rules.checks:query（源：non-binary）
  - G1 【名 + 姓】名 + 姓与参考精确一致
  - G2 【街道地址】街道地址与参考精确一致
  - G3 【城市 + 州/地区 + 邮编 + 国家】城市 + 州/地区 + 邮编 + 国家与参考精确一致

## b67dfdb5d15dbb4d199f
- **题面：** For this local training variant, create the newsletter template named "Training Holiday Promotion". Save subject "Training holiday offer" and body exactly "Training offer: ten percent off selected products from December 1 through December 7, 2026.". Use sender name Training Store and sender email store@example.test. Do not send or queue the newsletter.
- **分支：** admin_contract_rules.checks:create（源：non-binary）
  - G1 【实际新增并保存一个本任务可唯一绑定的有效对象】实际新增并保存一个本任务可唯一绑定的有效对象，与题面要求精确一致
  - G2 【模板名称正确】模板名称正确与参考精确一致
  - G3 【主题正确】主题正确与参考精确一致
  - G4 【正文正确】正文正确与参考精确一致
  - G5 【发件人名称正确】发件人名称正确与参考精确一致
  - G6 【发件人邮箱正确】发件人邮箱正确与参考精确一致

## b7cc5c99dd61d8e99c2c
- **题面：** Find out what types of personal information the website collects from users.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【每个正确、不重复的要求列表成员】每个正确、不重复的要求列表成员与参考精确一致

## b827e4e29d1845d4c43a
- **题面：** Check what transportation options are available for getting directions in OpenStreetMap
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【每个正确、不重复的要求列表成员】每个正确、不重复的要求列表成员与参考精确一致

## b82e145d0549d511622d
- **题面：** Create and save a new customer named Training Customer with email admin-b82e145d0549d511622d@example.test and customer group VIP Customers. Keep valid defaults for unspecified optional fields.
- **分支：** admin_contract_rules.checks:create（源：non-binary）
  - G1 【实际新增并保存一个本任务可唯一绑定的有效对象】实际新增并保存一个本任务可唯一绑定的有效对象，与题面要求精确一致
  - G2 【完整姓名正确】完整姓名正确与参考精确一致
  - G3 【邮箱正确】邮箱正确与参考精确一致
  - G4 【客户组正确】客户组正确与参考精确一致

## b8a621852314fabd2c90
- **题面：** List all customers with the ZIP code 75201.
- **分支：** admin_contract_rules.checks:collection_query（源：non-binary）
  - G1 【完整姓名正确】完整姓名正确与参考精确一致
  - G2 【邮箱正确】邮箱正确与参考精确一致

## b920ab04dc686ce6354f
- **题面：** View details about the refunded Minerva LumaTech™ V-Tee product
- **分支：** admin_contract_rules.checks:collection_query（源：non-binary）
  - G1 【SKU正确】SKU正确与参考精确一致
  - G2 【数量正确】数量正确与参考精确一致
  - G3 【价格正确】价格正确与参考精确一致

## b9915bc8913e7309cc99
- **题面：** Check what items are currently in your shopping cart.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【每个正确、不重复的要求列表成员】每个正确、不重复的要求列表成员与参考精确一致

## ba7427f96bfdd45c6df3
- **题面：** View the contents of your shopping cart with 3 items
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【每个正确、不重复的要求列表成员】每个正确、不重复的要求列表成员与参考精确一致

## bb087733414d726c2d50
- **题面：** For this local training variant, save Blue T-Shirt meta title as "Blue T-Shirt | Training Store" and meta description as "Browse the Blue T-Shirt in the Training Store catalog."
- **分支：** admin_contract_rules.checks:update（源：non-binary）
  - G1 【元标题正确】元标题正确与参考精确一致
  - G2 【元描述正确】元描述正确与参考精确一致

## bb4c6fa4b51a5a33afce
- **题面：** See how many reviews the Wildgame Innovations Trail Camera has.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【至少一个匹配相机型号的完整显示名称】至少一个匹配相机型号的完整显示名称，与题面要求精确一致
  - G2 【与该型号对应的评论数】与该型号对应的评论数，与题面要求精确一致

## bbdb63236829567f8199
- **题面：** Check which country and state Adam Garcia is from For this local training variant, the target account email is adam.garcia@gmail.com.
- **分支：** admin_contract_rules.checks:query（源：non-binary）
  - G1 【完整地址】完整地址各字段（country_id, region）与参考精确一致

## bced6b870e718e5c4722
- **题面：** For this local restored-page task, read the Vertex description on the Magento Marketplace page and return its exact description text. Stay on the local page; external partner websites are outside the task.
- **分支：** admin_contract_rules.checks:page_text_query（源：non-binary）
  - G1 【税务技术解决方案业务】税务技术解决方案业务与参考精确一致

## be7cead538c9af903316
- **题面：** For this local training variant, save Maya Tunic meta title as "Maya Tunic | Training Store" and meta description as "Browse the Maya Tunic in the Training Store catalog.".
- **分支：** admin_contract_rules.checks:update（源：non-binary）
  - G1 【元标题正确】元标题正确与参考精确一致
  - G2 【元描述正确】元描述正确与参考精确一致

## bf53b767cb6680af3e02
- **题面：** Find out what programming libraries are supported by the a11y-syntax-highlighting project.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【每个正确、不重复的要求列表成员】每个正确、不重复的要求列表成员与参考精确一致

## bf7fb901e64a6b200e93
- **题面：** List the names of all immediate subdirectories in src on the main branch of The A11Y Project (a11yproject/a11yproject.com).
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【每个正确、不重复的要求列表成员】每个正确、不重复的要求列表成员与参考精确一致

## bfb19f582147d0013e80
- **题面：** Find out what Markdown formatting options are available for creating wiki pages
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【要求的格式功能覆盖完整】要求的格式功能覆盖完整与参考精确一致
  - G2 【各功能对应语法正确】各功能对应语法正确与参考精确一致

## c0bcd7963046f155b1aa
- **题面：** Create and save a new customer named Training Customer with email admin-c0bcd7963046f155b1aa@example.test and customer group VIP Customers, date of birth 1990-01-15, gender Male. Keep valid defaults for unspecified optional fields.
- **分支：** admin_contract_rules.checks:create（源：non-binary）
  - G1 【实际新增并保存一个本任务可唯一绑定的有效对象】实际新增并保存一个本任务可唯一绑定的有效对象，与题面要求精确一致
  - G2 【完整姓名正确】完整姓名正确与参考精确一致
  - G3 【邮箱正确】邮箱正确与参考精确一致
  - G4 【客户组正确】客户组正确与参考精确一致
  - G5 【出生日期正确】出生日期正确与参考精确一致
  - G6 【性别正确】性别正确与参考精确一致

## c2d9e62db8793636a7a2
- **题面：** Report all recorded search terms, including each term, its number of uses, and its number of search results.
- **分支：** admin_contract_rules.checks:collection_query（源：non-binary）
  - G1 【目标集合覆盖完整且搜索词正确】目标集合覆盖完整且搜索词正确与参考精确一致
  - G2 【使用次数正确】使用次数正确与参考精确一致
  - G3 【结果数量正确】结果数量正确与参考精确一致

## c2fcbc0f3dd3445dd358
- **题面：** Report the five most recently placed orders, including order number, customer name, and grand total. Break timestamp ties by ascending internal order ID.
- **分支：** admin_contract_rules.checks:collection_query（源：non-binary）
  - G1 【目标集合覆盖完整且记录编号正确】目标集合覆盖完整且记录编号正确与参考精确一致
  - G2 【客户姓名正确】客户姓名正确与参考精确一致
  - G3 【总额正确】总额正确与参考精确一致

## c4d2f4fa20e3debaf7da
- **题面：** Check which material types are available for the St Patricks Day T-Shirt
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【每个正确、不重复的要求列表成员】每个正确、不重复的要求列表成员与参考精确一致

## cb1f6d37c80c1c966d0c
- **题面：** Retrieve the distance and estimated time for the route from 40.7830, -73.9650 to 40.7570, -73.9860.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【距离】距离与参考精确一致
  - G2 【时长】时长与参考精确一致

## cc2fff7007c02443f285
- **题面：** Create and save a simple product named Training Product cc2fff, SKU TRAIN-cc2fff7007c02443f285, price 9.99. Keep valid defaults for unspecified settings.
- **分支：** admin_contract_rules.checks:create（源：non-binary）
  - G1 【实际新增并保存一个本任务可唯一绑定的有效对象】实际新增并保存一个本任务可唯一绑定的有效对象，与题面要求精确一致
  - G2 【名称正确】名称正确与参考精确一致
  - G3 【SKU正确】SKU正确与参考精确一致
  - G4 【价格正确】价格正确与参考精确一致

## cc749c4fb809e8c6fb7f
- **题面：** View all projects with the Apache License 2.0. Consider all non-archived projects accessible to the current account, across the complete project directory.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【每个正确、不重复的要求列表成员】每个正确、不重复的要求列表成员与参考精确一致

## ce00fc4dc07e7d61dd52
- **题面：** For this local training variant, enable Allow Gift Message for Blue T-Shirt, overriding the default setting, and save.
- **分支：** admin_contract_rules.checks:update（源：non-binary）
  - G1 【本商品明确持久覆盖默认礼品留言设置】本商品明确持久覆盖默认礼品留言设置，与题面要求精确一致
  - G2 【本商品最终有效的Allow Gift Message为启用】本商品最终有效的Allow Gift Message为启用，与题面要求精确一致

## cef4af3fccbffcd9e2b5
- **题面：** Read and report the project description for zerosoul / chinese-colors.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【描述的具体主题：Chinese traditional color】描述的具体主题：Chinese traditional color，与题面要求精确一致
  - G2 【描述的用途与形式：cheatsheet online】描述的用途与形式：cheatsheet online，与题面要求精确一致

## d03c2b089580e79d83f0
- **题面：** List customers whose Account Created in field is Default Store View, including their names and email addresses.
- **分支：** admin_contract_rules.checks:collection_query（源：non-binary）
  - G1 【完整姓名正确】完整姓名正确与参考精确一致
  - G2 【邮箱正确】邮箱正确与参考精确一致

## d0b831ec16b5e174fbd5
- **题面：** Share the current map location using a geo URI.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【geo URI中的完整经纬度坐标对】geo URI中的完整经纬度坐标对，与题面要求精确一致
  - G2 【geo URI中的z缩放参数】geo URI中的z缩放参数，与题面要求精确一致

## d1463ce7357f4c066d3a
- **题面：** Add a new product named "Sony Headphones" with SKU "SH123" and a price of $199.99.
- **分支：** admin_contract_rules.checks:create（源：non-binary）
  - G1 【实际新增并保存一个本任务可唯一绑定的有效对象】实际新增并保存一个本任务可唯一绑定的有效对象，与题面要求精确一致
  - G2 【名称正确】名称正确与参考精确一致
  - G3 【SKU正确】SKU正确与参考精确一致
  - G4 【价格正确】价格正确与参考精确一致

## d3157acb785a0c07897a
- **题面：** Determine what fields are required when creating a new wiki page
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【每个正确、不重复的要求列表成员】每个正确、不重复的要求列表成员与参考精确一致

## d3ff3426f3fdcea375d4
- **题面：** For this local training variant, create and save a subcategory named Training Organized Products directly under Default Category.
- **分支：** admin_contract_rules.checks:create（源：non-binary）
  - G1 【实际新增并保存一个本任务可唯一绑定的有效对象】实际新增并保存一个本任务可唯一绑定的有效对象，与题面要求精确一致
  - G2 【名称正确】名称正确与参考精确一致
  - G3 【父分类归属正确】父分类归属正确与参考精确一致

## d4498e55f4e12af7500a
- **题面：** Export the order data as a CSV file.
- **分支：** admin_contract_rules.checks:export（源：non-binary）
  - G1 【记录编号正确】记录编号正确与参考精确一致
  - G2 【总额正确】总额正确与参考精确一致

## d555e57bbc134c2d89c5
- **题面：** Create a customer group named VIP Customers, exclude Main Website, and save the group.
- **分支：** admin_contract_rules.checks:create（源：non-binary）
  - G1 【实际新增并保存一个本任务可唯一绑定的有效对象】实际新增并保存一个本任务可唯一绑定的有效对象，与题面要求精确一致
  - G2 【名称正确】名称正确与参考精确一致
  - G3 【网站排除配置正确】网站排除配置正确与参考精确一致

## d5625da1a9cdb07f180b
- **题面：** Create and save a simple product named Training Product d5625d, SKU TRAIN-d5625da1a9cdb07f180b, price 9.99, stock quantity 100. Keep valid defaults for unspecified settings.
- **分支：** admin_contract_rules.checks:create（源：non-binary）
  - G1 【实际新增并保存一个本任务可唯一绑定的有效对象】实际新增并保存一个本任务可唯一绑定的有效对象，与题面要求精确一致
  - G2 【名称正确】名称正确与参考精确一致
  - G3 【SKU正确】SKU正确与参考精确一致
  - G4 【价格正确】价格正确与参考精确一致
  - G5 【数量正确】数量正确与参考精确一致

## d6c9a19fbbadca1e0548
- **题面：** Export customer data to CSV
- **分支：** admin_contract_rules.checks:export（源：non-binary）
  - G1 【名称正确】名称正确与参考精确一致
  - G2 【邮箱正确】邮箱正确与参考精确一致

## d6ca61ffbbc704a34880
- **题面：** Create a new customer account with the name "John Smith" and email "john.smith@example.com"
- **分支：** admin_contract_rules.checks:create（源：non-binary）
  - G1 【实际新增并保存一个本任务可唯一绑定的有效对象】实际新增并保存一个本任务可唯一绑定的有效对象，与题面要求精确一致
  - G2 【完整姓名正确】完整姓名正确与参考精确一致
  - G3 【邮箱正确】邮箱正确与参考精确一致

## d8597402b1c899c1eaea
- **题面：** For this local restored-page task, read the Yotpo description on the Magento Marketplace page and return its exact description text. Stay on the local page; external partner websites are outside the task.
- **分支：** admin_contract_rules.checks:page_text_query（源：non-binary）
  - G1 【评论及营销解决方案性质】评论及营销解决方案性质与参考精确一致

## d9eedb3a01d7ba055979
- **题面：** For this local training variant, edit the existing URL rewrite in Default Store View: request path training-product-entry, target path catalog/product/view/id/1, redirect type Permanent (301). Save it.
- **分支：** admin_contract_rules.checks:update（源：non-binary）
  - G1 【目标路径正确】目标路径正确与参考精确一致
  - G2 【重定向类型正确】重定向类型正确与参考精确一致

## dd3ea545f0d5d4ec39e7
- **题面：** Create a new customer group named "VIP Clients" with the tax class set to "Wholesale" and excluding the "Main Website".
- **分支：** admin_contract_rules.checks:create（源：non-binary）
  - G1 【实际新增并保存一个本任务可唯一绑定的有效对象】实际新增并保存一个本任务可唯一绑定的有效对象，与题面要求精确一致
  - G2 【名称正确】名称正确与参考精确一致
  - G3 【税类正确】税类正确与参考精确一致
  - G4 【网站排除配置正确】网站排除配置正确与参考精确一致

## e0d2db4c54b927dba6c4
- **题面：** List the step-by-step directions from 40.7830, -73.9650 to 40.7570, -73.9860.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【每条要求返回的路线指引内容和序号正确】每条要求返回的路线指引内容和序号正确与参考精确一致

## e185d8d1ac754b973390
- **题面：** Check the total distance and estimated travel time from New York City to Boston by car.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【距离】距离与参考精确一致
  - G2 【时长】时长与参考精确一致

## e59148d1ae21a34456e6
- **题面：** Create and save a simple product named Training Product e59148, SKU TRAIN-e59148d1ae21a34456e6, price 9.99. Keep valid defaults for unspecified settings.
- **分支：** admin_contract_rules.checks:create（源：non-binary）
  - G1 【实际新增并保存一个本任务可唯一绑定的有效对象】实际新增并保存一个本任务可唯一绑定的有效对象，与题面要求精确一致
  - G2 【名称正确】名称正确与参考精确一致
  - G3 【SKU正确】SKU正确与参考精确一致
  - G4 【价格正确】价格正确与参考精确一致

## e678830c65ec323f09db
- **题面：** View all 3 items in the cart to verify quantities before placing order
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【三个商品覆盖完整】三个商品覆盖完整与参考精确一致
  - G2 【三个商品对应数量全部正确】三个商品对应数量全部正确与参考精确一致

## e716ca170d71ab432a59
- **题面：** For this local training variant, Select order #000000002 and download all its available invoice, packing-slip and credit-memo documents as a PDF.
- **分支：** admin_contract_rules.checks:pdf（源：non-binary）
  - G1 【原订单的invoice文档正确】原订单的invoice文档正确与参考精确一致
  - G2 【原订单的packing_slip文档正确】原订单的packing_slip文档正确与参考精确一致
  - G3 【原订单的credit_memo文档正确】原订单的credit_memo文档正确与参考精确一致

## e83b251b13a8daa1fc7a
- **题面：** Generate a geo URI for the current location
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【geo URI中的完整经纬度坐标对】geo URI中的完整经纬度坐标对，与题面要求精确一致
  - G2 【geo URI中的z缩放参数】geo URI中的z缩放参数，与题面要求精确一致

## e8d67ff6e22fa9ee3b67
- **题面：** List all directories in the a11y-syntax-highlighting repository.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【每个正确、不重复的要求列表成员】每个正确、不重复的要求列表成员与参考精确一致

## e9c39aadd73068054997
- **题面：** Check what items are currently in your shopping cart with 3 items.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【每个正确、不重复的要求列表成员】每个正确、不重复的要求列表成员与参考精确一致

## ee4d5f917fbea3c35cbe
- **题面：** Export the credit memo data as a CSV file.
- **分支：** admin_contract_rules.checks:export（源：non-binary）
  - G1 【退款单编号】退款单编号，与题面要求精确一致
  - G2 【退款单创建日期】退款单创建日期，与题面要求精确一致
  - G3 【关联订单编号】关联订单编号，与题面要求精确一致
  - G4 【订单创建日期】订单创建日期，与题面要求精确一致
  - G5 【账单姓名及完整账单地址】账单姓名及完整账单地址，与题面要求精确一致
  - G6 【退款单状态】退款单状态，与题面要求精确一致
  - G7 【基础币种退款金额】基础币种退款金额，与题面要求精确一致
  - G8 【订单状态】订单状态，与题面要求精确一致
  - G9 【购买商店/站点】购买商店/站点，与题面要求精确一致
  - G10 【完整收货地址】完整收货地址，与题面要求精确一致
  - G11 【客户完整姓名】客户完整姓名，与题面要求精确一致
  - G12 【客户邮箱】客户邮箱，与题面要求精确一致
  - G13 【客户分组】客户分组，与题面要求精确一致
  - G14 【支付方式】支付方式，与题面要求精确一致
  - G15 【配送方式信息】配送方式信息，与题面要求精确一致
  - G16 【退款小计】退款小计，与题面要求精确一致
  - G17 【配送及手续费】配送及手续费，与题面要求精确一致
  - G18 【退款调整金额】退款调整金额，与题面要求精确一致
  - G19 【调整费用】调整费用，与题面要求精确一致
  - G20 【基础币种订单总额】基础币种订单总额，与题面要求精确一致

## f73c97fb77388ae7f772
- **题面：** Find the SKU number and manufacturer of the Mineralogie All Natural Lip Gloss, Ruby Rose.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【SKU】SKU与参考精确一致
  - G2 【制造商】制造商与参考精确一致

## f8a3e7d1108c55158a9d
- **题面：** View all customers from the United States
- **分支：** admin_contract_rules.checks:collection_query（源：non-binary）
  - G1 【完整姓名正确】完整姓名正确与参考精确一致
  - G2 【邮箱正确】邮箱正确与参考精确一致

## fb397ea55485dc33f943
- **题面：** Create and save a new customer named Training Customer with email admin-fb397ea55485dc33f943@example.test. Keep valid defaults for unspecified optional fields.
- **分支：** admin_contract_rules.checks:create（源：non-binary）
  - G1 【实际新增并保存一个本任务可唯一绑定的有效对象】实际新增并保存一个本任务可唯一绑定的有效对象，与题面要求精确一致
  - G2 【完整姓名正确】完整姓名正确与参考精确一致
  - G3 【邮箱正确】邮箱正确与参考精确一致

## fbd675fc29750bd1a7ff
- **题面：** Find out who is using the a11y-syntax-highlighting themes.
- **分支：** site_query_rules.evaluate_query:ordinary_query（源：non-binary）
  - G1 【每个正确、不重复的要求列表成员】每个正确、不重复的要求列表成员与参考精确一致

## 00bf826e805106ec7728
- **题面：** Go to the System section to manage technical settings and integrations.
- **分支：** admin-menu-navigation-v1（源：remaining）
  - G1 【到达菜单】到达菜单 System

## 03b855df929a3c25b729
- **题面：** Go to the Catalog section to manage products.
- **分支：** admin-menu-navigation-v1（源：remaining）
  - G1 【到达菜单】到达菜单 Catalog

## 10dab2b2e59bb4192b59
- **题面：** View the CATALOG to manage product listings.
- **分支：** admin-menu-navigation-v1（源：remaining）
  - G1 【到达菜单】到达菜单 Catalog

## 145c72daa596e2b75a18
- **题面：** Navigate to the Content section in Magento Admin.
- **分支：** admin-menu-navigation-v1（源：remaining）
  - G1 【到达菜单】到达菜单 Content

## 169044048fa27c8b0201
- **题面：** Explore the Marketing section by clicking the MARKETING link.
- **分支：** admin-menu-navigation-v1（源：remaining）
  - G1 【到达菜单】到达菜单 Marketing

## 1953953709068c8a0849
- **题面：** Navigate to the Customers section to manage customer accounts and groups.
- **分支：** admin-menu-navigation-v1（源：remaining）
  - G1 【到达菜单】到达菜单 Customers

## 0745b20464a47dc9e5cd
- **题面：** Navigate to the comments section of the post "What’s the first thing you’re gonna do when 2023 starts?"
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /f/AskReddit/51906
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^What’s\ the\ first\ thing\ you’re\ gonna\ do\ when\ 2023\ starts\?$

## 10fccbde17ee149a7845
- **题面：** Check your user profile information
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /user/MarvelsGrantMan136
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^MarvelsGrantMan136$

## 0a710b27885258ed9db0
- **题面：** Navigate to the Tags page.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /tags
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Tags$

## 10161aa90f212f604445
- **题面：** Navigate to the dist directory to view distribution files.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/a11y-syntax-highlighting/-/tree/main/dist
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^dist\ ·\ main\ ·\ Byte\ Blaze\ /\ a11y\-syntax\-highlighting\ ·\ GitLab$

## 11ad462b2d3142dd99bf
- **题面：** Navigate to the Dashboard page.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /
  - G2 【标题/身份匹配】页面标题/目标身份匹配 Projects · Dashboard · GitLab$

## 13263ef7073ce0c863da
- **题面：** Go to the starred projects page
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /dashboard/projects/starred
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Projects$

## 19a46046f5ee9f558580
- **题面：** Visit the Help section to get GitLab documentation.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /help
  - G2 【标题/身份匹配】页面标题/目标身份匹配 GitLab

## 19ea57fe21b01a0e1267
- **题面：** Go to issue details for " HOWTO: Ajax with ARIA-LIVE"
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /a11yproject/a11yproject.com/-/issues/1533
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^\[Post\]\ HOWTO:\ Ajax\ with\ ARIA\-LIVE$

## 1a5f6a1a46a3a7c0f9b7
- **题面：** Navigate to the ffmpeg-python project page to learn about Python bindings for FFmpeg
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /kkroening/ffmpeg-python
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^ffmpeg\-python$

## 1a78ad9ef8791872142b
- **题面：** Read the README.md file to learn about the a11y-syntax-highlighting project.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/a11y-syntax-highlighting/-/blob/main/README.md
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:README\.md\ ·\ main\ ·\ Byte\ Blaze\ /\ a11y\-syntax\-highlighting\ ·\ GitLab|Byte\ Blaze\ /\ a11y\-syntax\-highlighting\ ·\ GitLab|Files\ ·\ main\ ·\ Byte\ Blaze\ /\ a11y\-syntax\-highlighting\ ·\ GitLab)$

## 1c6a4293eb7f56278fb2
- **题面：** Go to the New project page.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /projects/new
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Create new project$

## 205e7b43c67600f73ebd
- **题面：** Filter projects by visibility (public, internal, or private)
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 projects
  - G2 【过滤条件】按「visibility」过滤
  - G3 【保存生效】修改已持久保存生效

## 2060c9e7f562b5d1296d
- **题面：** Navigate to the Analytics page to view project statistics.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/a11y-syntax-highlighting/-/value_stream_analytics
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Value\ Stream\ Analytics\ ·\ Byte\ Blaze\ /\ a11y\-syntax\-highlighting\ ·\ GitLab$

## 21f48179dba34b88fa97
- **题面：** Browse project topics
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 227af4375424e42f9faf
- **题面：** Navigate to the Topics page to explore by topics.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /explore/projects/topics
  - G2 【标题/身份匹配】页面标题/目标身份匹配 Topics.*GitLab$

## 23051fae1c90a480b1df
- **题面：** View the commit history for this repository.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/a11y-syntax-highlighting/-/commits/main
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Commits\ ·\ main\ ·\ Byte\ Blaze\ /\ a11y\-syntax\-highlighting\ ·\ GitLab$

## 23fa3a260bccc01661f0
- **题面：** Open any merge request details page associated with a pending item in your current account's initial To-Do List. Any such target is acceptable; the route used to reach it is unrestricted. Leave the target page open and do not change the to-do items.
- **分支：** （源：remaining）
  - G1 【变更字段】变更 to-do items
  - G2 【保存生效】修改已持久保存生效

## 2600ebd67d0765275022
- **题面：** Go to your To-Do List
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /dashboard/todos
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^To-[Dd]o List(?: \u00b7| \|)

## 284dca162ad7c7d81e62
- **题面：** Go to the Primer/design repository
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /primer/design
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^design$

## 29c9bfd3a39861db9c2e
- **题面：** Go to the spotlight directory to see featured content.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /a11yproject/a11yproject.com/-/tree/main/src/spotlight
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^src/spotlight\ ·\ main\ ·\ The\ A11Y\ Project\ /\ a11yproject\.com\ ·\ GitLab$

## 2cc1d3936bce652d2804
- **题面：** Find the post about accessibility and SEO.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 2eecd376ddbc85b5e47c
- **题面：** Navigate to the _includes directory to see template parts.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /a11yproject/a11yproject.com/-/tree/main/src/_includes
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^src/_includes\ ·\ main\ ·\ The\ A11Y\ Project\ /\ a11yproject\.com\ ·\ GitLab$

## 30215fa2678b14d7fca1
- **题面：** Change the visibility level of the group to "Internal".
- **分支：** （源：remaining）
  - G1 【可见性级别】可见性级别 改为 "Internal"
  - G2 【可见性】可见性为 Internal
  - G3 【保存生效】修改已持久保存生效

## 31ecd98cbf1972305388
- **题面：** Navigate to the Issues section of the a11yproject.com GitLab project.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /a11yproject/a11yproject.com/-/issues
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Issues.*a11yproject\.com.*GitLab$

## 3354e1ff7c8a4a9a7bcb
- **题面：** View trending projects
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /explore/projects/trending
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Projects · Explore · GitLab$

## 3547aa40eedd9ab22742
- **题面：** Learn about screen reader compatibility by reading the NVDA guide.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /a11yproject/a11yproject.com/-/blob/main/src/posts/getting-started-with-nvda.md
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^src/posts/getting\-started\-with\-nvda\.md\ ·\ main\ ·\ The\ A11Y\ Project\ /\ a11yproject\.com\ ·\ GitLab$

## 378434308ca76d88ff26
- **题面：** Look at the merge requests for Media-Smart / vedaseg.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /Media-Smart/vedaseg/-/merge_requests
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Merge requests.*vedaseg.*GitLab$

## 384bc6cefb198137cce7
- **题面：** Navigate to the Issues dashboard.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /dashboard/issues
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Issues$

## 3af2675fd79c6b46c449
- **题面：** Visit the CI/CD pipelines section for the a11yproject.com project.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /a11yproject/a11yproject.com/-/pipelines
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Pipelines.*a11yproject\.com.*GitLab$

## 3c57e5ec519fd302f8bc
- **题面：** Explore trending projects on GitLab
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /explore/projects/trending?sort=name_asc&non_archived=true
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Projects · Explore · GitLab$

## 3c9d320d404a4fef43c7
- **题面：** Visit the Trending projects section on the GitLab Explore page.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /explore/projects/trending
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Projects · Explore · GitLab$

## 3cb2fcab17927d5af00a
- **题面：** View the stargazers of the js-stack-from-scratch project
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /verekia/js-stack-from-scratch/-/starrers
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Starrers\ ·\ Verekia\ /\ js\-stack\-from\-scratch\ ·\ GitLab$

## 3da6f64557544f8db993
- **题面：** Navigate to the Explore page to discover and browse public projects on GitLab.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /explore
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Projects · Explore · GitLab$

## 3dd015af9890a1224d6d
- **题面：** Check open merge requests assigned to you.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /dashboard/merge_requests?state=opened&assignee_username=byteblaze
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Merge requests$

## 3fa9fa2688f4121d53a6
- **题面：** Go to the Create new project page.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /projects/new
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Create new project$

## 3ff8caef991ecc064b20
- **题面：** Open any project overview associated with a pending item in your current account's initial To-Do List. Any such target is acceptable; the route used to reach it is unrestricted. Leave the target page open and do not change the to-do items.
- **分支：** （源：remaining）
  - G1 【变更字段】变更 to-do items
  - G2 【保存生效】修改已持久保存生效

## 4080b2751591120b1231
- **题面：** Navigate to the Subgroups documentation page.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /help/user/group/subgroups/index
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Subgroups\ \(FREE\)$

## 454ae98449d7d635b7e2
- **题面：** Browse projects by topics
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 47e98b24288104e7ad54
- **题面：** View the commit history to see recent changes to Byte Blaze / a11y-syntax-highlighting.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/a11y-syntax-highlighting/-/commits/main
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Commits\ ·\ main\ ·\ Byte\ Blaze\ /\ a11y\-syntax\-highlighting\ ·\ GitLab$

## 47ee264e253604a020aa
- **题面：** Navigate to the CI/CD section to view build pipelines and automation for the cloud-to-butt project.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/cloud-to-butt/-/pipelines
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Pipelines.*cloud\-to\-butt.*GitLab$

## 49468279e69c9e6d358f
- **题面：** View your to-do list.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /dashboard/todos
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^To-[Dd]o List(?: \u00b7| \|)

## 4b99b29bc85517a44409
- **题面：** Navigate to the Merge Requests dashboard.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /dashboard/merge_requests
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Merge\ requests$

## 4f7177707ad796a92a5d
- **题面：** Use the search filter to find projects by the name "Hotel_Project".
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 to find projects
  - G2 【名称】名称为 "Hotel_Project"
  - G3 【过滤条件】按「the name "Hotel_Project"」过滤
  - G4 【保存生效】修改已持久保存生效

## 50a7f3d242ac554d1178
- **题面：** Navigate to the alt-text article to learn about writing effective image descriptions.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /a11yproject/a11yproject.com/-/blob/main/src/posts/alt-text.md
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^src/posts/alt\-text\.md\ ·\ main\ ·\ The\ A11Y\ Project\ /\ a11yproject\.com\ ·\ GitLab$

## 510377e4a3a06b903e82
- **题面：** Navigate to the posts directory to view accessibility articles and blog posts.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /a11yproject/a11yproject.com/-/tree/main/src/posts
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^src/posts\ ·\ main\ ·\ The\ A11Y\ Project\ /\ a11yproject\.com\ ·\ GitLab$

## 527877aa6f7a4fe84c6f
- **题面：** Navigate to the content_script.js file to view its code
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/cloud-to-butt/-/blob/master/Source/content_script.js
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Source/content_script\.js\ ·\ master\ ·\ Byte\ Blaze\ /\ cloud\-to\-butt\ ·\ GitLab$

## 560f5247ec4378501301
- **题面：** View the js directory to see the JavaScript files.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /a11yproject/a11yproject.com/-/tree/main/src/js
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^src/js\ ·\ main\ ·\ The\ A11Y\ Project\ /\ a11yproject\.com\ ·\ GitLab$

## 56f69d5850829a9c50db
- **题面：** Go to your Issues page.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /dashboard/issues
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Issues$

## 5887ebc01467f200f663
- **题面：** Check the test directory to see what test files are available.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/a11y-syntax-highlighting/-/tree/main/test
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^test\ ·\ main\ ·\ Byte\ Blaze\ /\ a11y\-syntax\-highlighting\ ·\ GitLab$

## 58ea87f56824a3bfdad2
- **题面：** Find the roadmap information to see what editor support is planned
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 58f9d472c5a289fffbe6
- **题面：** View the commit history for the a11y-syntax-highlighting repository.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/a11y-syntax-highlighting/-/commits/main
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Commits\ ·\ main\ ·\ Byte\ Blaze\ /\ a11y\-syntax\-highlighting\ ·\ GitLab$

## 599c986f1ae302fac6f5
- **题面：** Read the article on creating valid and accessible links.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /a11yproject/a11yproject.com/-/blob/main/src/posts/creating-valid-and-accessible-links.md
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^src/posts/creating\-valid\-and\-accessible\-links\.md\ ·\ main\ ·\ The\ A11Y\ Project\ /\ a11yproject\.com\ ·\ GitLab$

## 59e53024dfab3e19aab6
- **题面：** View the Packages and Registries for the a11yproject.com GitLab project.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /a11yproject/a11yproject.com/-/packages
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Package\ Registry\ ·\ The\ A11Y\ Project\ /\ a11yproject\.com\ ·\ GitLab$

## 59eea7489e10e73a380b
- **题面：** Check the milestones to see the project roadmap
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/a11y-syntax-highlighting/-/milestones
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Milestones\ ·\ Byte\ Blaze\ /\ a11y\-syntax\-highlighting\ ·\ GitLab$

## 5a01974a79efcd087c21
- **题面：** Check the roadmap to see what editor support is planned for future releases.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/a11y-syntax-highlighting/-/blob/main/README.md#roadmap
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:README\.md\ ·\ main\ ·\ Byte\ Blaze\ /\ a11y\-syntax\-highlighting\ ·\ GitLab|Byte\ Blaze\ /\ a11y\-syntax\-highlighting\ ·\ GitLab)$

## 5a8051ca55436a834c36
- **题面：** Navigate to the dist directory to see the distribution files.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/a11y-syntax-highlighting/-/tree/main/dist
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^dist\ ·\ main\ ·\ Byte\ Blaze\ /\ a11y\-syntax\-highlighting\ ·\ GitLab$

## 5b3aacf53f052cb8f8e2
- **题面：** Navigate to the Topics page to browse projects organized by subject matter and categories.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /explore/projects/topics
  - G2 【标题/身份匹配】页面标题/目标身份匹配 Topics.*GitLab$

## 5efed56d2e35175ebafb
- **题面：** Read the README file in Byte Blaze / a11y-syntax-highlighting.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/a11y-syntax-highlighting/-/blob/main/README.md
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:README\.md\ ·\ main\ ·\ Byte\ Blaze\ /\ a11y\-syntax\-highlighting\ ·\ GitLab|Byte\ Blaze\ /\ a11y\-syntax\-highlighting\ ·\ GitLab|Files\ ·\ main\ ·\ Byte\ Blaze\ /\ a11y\-syntax\-highlighting\ ·\ GitLab)$

## 61dafb9f8ba9f945c6ea
- **题面：** View DynamoRIO tools
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /DynamoRIO/dynamorio/-/tree/master/tools
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:tools\ ·\ master\ ·\ DynamoRIO\ /\ dynamorio\ ·\ GitLab)$

## 6361727e57c1a9d7d094
- **题面：** View project Milestones to track issue deadlines and releases.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/a11y-syntax-highlighting/-/milestones
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Milestones\ ·\ Byte\ Blaze\ /\ a11y\-syntax\-highlighting\ ·\ GitLab$

## 63caf4a99454115864d4
- **题面：** Navigate to the Source directory to view the extension code
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/cloud-to-butt/-/tree/master/Source
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Source\ ·\ master\ ·\ Byte\ Blaze\ /\ cloud\-to\-butt\ ·\ GitLab$

## 64adb0e70ffa9348ab18
- **题面：** Navigate to the Web IDE for byteblaze/cloud-to-butt to edit code in the browser.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /-/ide/project/byteblaze/cloud-to-butt/edit/master/-/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^IDE · GitLab$

## 67b268325d0dd256b62c
- **题面：** Visit the Help page.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /help
  - G2 【标题/身份匹配】页面标题/目标身份匹配 GitLab

## 6808a7ebd871e892e053
- **题面：** Go to the "To-Do List" page.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /dashboard/todos
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^To-Do List .* GitLab$

## 69b8005bb80061065a1a
- **题面：** View the CI/CD page for the a11yproject.com repository.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /a11yproject/a11yproject.com/-/pipelines
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Pipelines.*a11yproject\.com.*GitLab$

## 6e2a8a4c0854b373814a
- **题面：** Go to the Byte Blaze / empathy-prompts project page
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/empathy-prompts
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^empathy\-prompts$

## 71d06a0475b267d82cc7
- **题面：** Navigate to the issues page of the ffmpeg-python project
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /kkroening/ffmpeg-python/-/issues
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Issues.*ffmpeg\-python.*GitLab$

## 728a582d5775de4ada63
- **题面：** Navigate to the help page for subgroups.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /help/user/group/subgroups/index
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Subgroups\ \(FREE\)$

## 732cedf79d3ffa3b1edf
- **题面：** Filter projects by typing "accessibility" in the search box.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 projects
  - G2 【过滤条件】按「typing "accessibility" in the search box」过滤
  - G3 【保存生效】修改已持久保存生效

## 73f5f6fcf223e58fcf3c
- **题面：** Navigate to the create-react-app project page.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /facebook/create-react-app
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^create\-react\-app$

## 74ef779eaaec39836af3
- **题面：** Navigate to the documentation on public access.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /help/user/public_access
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Project\ and\ group\ visibility\ \(FREE\)$

## 75eee6cca8a276a251cb
- **题面：** Navigate to the manifest.json file to view its configuration
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/cloud-to-butt/-/blob/master/Source/manifest.json
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Source/manifest\.json\ ·\ master\ ·\ Byte\ Blaze\ /\ cloud\-to\-butt\ ·\ GitLab$

## 760eb8cd3ac744840e8f
- **题面：** Navigate to the GitLab Dashboard to see an overview of your activity and projects.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Projects · Dashboard · GitLab$

## 76d29f31677312930097
- **题面：** Navigate to the images directory to view project images.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/a11y-syntax-highlighting/-/tree/main/images
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^images\ ·\ main\ ·\ Byte\ Blaze\ /\ a11y\-syntax\-highlighting\ ·\ GitLab$

## 7766f3082fed732fec98
- **题面：** View the Infrastructure section to see the projects clusters.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /a11yproject/a11yproject.com/-/clusters
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Kubernetes\ Clusters\ ·\ The\ A11Y\ Project\ /\ a11yproject\.com\ ·\ GitLab$

## 7acf1922d7013c643a42
- **题面：** Navigate to the Issue Boards to view issues in a kanban-style layout.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/a11y-syntax-highlighting/-/boards
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Development$

## 7bf0c03ca9f02fd663c4
- **题面：** Go to your personal projects
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Projects · Dashboard · GitLab$

## 7df7bf6efa09a714b940
- **题面：** Read about text resizing in iOS and Android for mobile accessibility.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /a11yproject/a11yproject.com/-/blob/main/src/posts/text-resizing-in-ios-and-android.md
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^src/posts/text\-resizing\-in\-ios\-and\-android\.md\ ·\ main\ ·\ The\ A11Y\ Project\ /\ a11yproject\.com\ ·\ GitLab$

## 7ec4ff72cfcd6fd85da9
- **题面：** Navigate to the GitLab Help page.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /help
  - G2 【标题/身份匹配】页面标题/目标身份匹配 GitLab

## 7f9ebb86965938bf863c
- **题面：** Visit the Help section to find documentation and assistance.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /help
  - G2 【标题/身份匹配】页面标题/目标身份匹配 GitLab

## 7fd908db508252cc6413
- **题面：** Learn about visual impairment from the dedicated article.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /a11yproject/a11yproject.com/-/blob/main/src/posts/understanding-visual-impairment.md
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^src/posts/understanding\-visual\-impairment\.md\ ·\ main\ ·\ The\ A11Y\ Project\ /\ a11yproject\.com\ ·\ GitLab$

## 81c83cbd4824c3422c6e
- **题面：** Go to the Deployments section to manage environments.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/a11y-syntax-highlighting/-/environments
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Environments\ ·\ Byte\ Blaze\ /\ a11y\-syntax\-highlighting\ ·\ GitLab$

## 852d6c81afda3aa02b07
- **题面：** View the figma directory for Figma design files.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/a11y-syntax-highlighting/-/tree/main/dist/figma
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^dist/figma\ ·\ main\ ·\ Byte\ Blaze\ /\ a11y\-syntax\-highlighting\ ·\ GitLab$

## 8555306127fdf278cb61
- **题面：** Go to the Merge requests page to check pending merge requests.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/a11y-syntax-highlighting/-/merge_requests?state=opened
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Merge requests · .+ / a11y\-syntax\-highlighting · GitLab$

## 858737aaec7a7dfcea69
- **题面：** Explore the Bootstrap JavaScript source code in the js directory.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /twbs/bootstrap/-/tree/main/js
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^js(?:/[^·]+)? · main\ ·\ Bootstrap\ /\ bootstrap\ ·\ GitLab$

## 85cfb6b3851e8a5de381
- **题面：** View your user profile page
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Byte\ Blaze$

## 85dd692efc691723c822
- **题面：** Open Bootstrap in the Web IDE.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /-/ide/project/twbs/bootstrap/edit/main/-/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^IDE · GitLab$

## 8769f14073b67ebf83ab
- **题面：** Navigate to the Most stars projects view
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /explore/projects?sort=stars_desc&non_archived=true
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Projects · Explore · GitLab$

## 8846a901ba5b5c11ec99
- **题面：** View the releases of create-react-app.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /facebook/create-react-app/-/releases
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Releases\ ·\ Meta\ /\ create\-react\-app\ ·\ GitLab$

## 8867b7b2306064d37e36
- **题面：** Navigate to the Issues section of the a11y-syntax-highlighting project.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/a11y-syntax-highlighting/-/issues
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Issues.*a11y\-syntax\-highlighting.*GitLab$

## 898c262d2af6785c903a
- **题面：** Browse your starred projects.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 8bc8a0871c634880551b
- **题面：** Navigate to the Source folder to view the extension source code.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/cloud-to-butt/-/tree/master/Source
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Source\ ·\ master\ ·\ Byte\ Blaze\ /\ cloud\-to\-butt\ ·\ GitLab$

## 8d5d1e123d108634397d
- **题面：** Specify that the group will be used for "I want to store my code".
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /groups/new#create-group-pane
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^New Group · GitLab$

## 8e54e4419db08cbaf348
- **题面：** Open the To-Do List page.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /dashboard/todos
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^To-Do List .* GitLab$

## 8e60871fef6b7af30e95
- **题面：** Navigate to the Infrastructure section of the a11y-syntax-highlighting project.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/a11y-syntax-highlighting/-/clusters
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Kubernetes\ Clusters\ ·\ Byte\ Blaze\ /\ a11y\-syntax\-highlighting\ ·\ GitLab$

## 8ee8de2faeb09f073951
- **题面：** View the "Tm Theme Editor" issue.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/a11y-syntax-highlighting/-/issues/1
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Tm\ Theme\ Editor$

## 8f98b0cf5c6d9f7bc282
- **题面：** Visit your user profile page.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Byte\ Blaze$

## 901143c73e0bf0671bb7
- **题面：** Sort projects by most stars
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 projects
  - G2 【排序】按 most stars 排序
  - G3 【保存生效】修改已持久保存生效

## 90840962e2dd90b6a053
- **题面：** Browse the Wiki section to view or create documentation for the project.
- **分支：** （源：remaining）
  - G1 【目标对象】新建/添加的对象与题面要求一致
  - G2 【保存生效】新建/添加已持久保存生效

## 90862afbcf7377862beb
- **题面：** Navigate to the Projects Dashboard.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Projects · Dashboard · GitLab$

## 915bed341e272fb34902
- **题面：** View the Web IDE for create-react-app.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /-/ide/project/facebook/create-react-app/edit/main/-/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^IDE · GitLab$

## 9416c842991ee495a30e
- **题面：** Navigate to the GitLab Dashboard home page.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /
  - G2 【标题/身份匹配】页面标题/目标身份匹配 Projects · Dashboard · GitLab$

## 9468796f768e996f2f95
- **题面：** View recent commits on the a11y-syntax-highlighting project.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/a11y-syntax-highlighting/-/commits/main
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Commits\ ·\ main\ ·\ Byte\ Blaze\ /\ a11y\-syntax\-highlighting\ ·\ GitLab$

## 95e718d10389dac82570
- **题面：** Go to your personal dashboard from the explore page
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Projects · Dashboard · GitLab$

## 9a381be41f64639016dd
- **题面：** Find projects with the most stars on GitLab
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 9dd3e006f24c63035625
- **题面：** Filter projects by visibility.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 projects
  - G2 【过滤条件】按「visibility」过滤
  - G3 【保存生效】修改已持久保存生效

## 9e243614712a60a8106a
- **题面：** View the a11y-syntax-highlighting project
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/a11y-syntax-highlighting
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^a11y\-syntax\-highlighting$

## a1255fefd53b48d563fe
- **题面：** Explore the Security & Compliance section to view security configuration options.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/a11y-syntax-highlighting/-/security/configuration
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Security\ Configuration\ ·\ Byte\ Blaze\ /\ a11y\-syntax\-highlighting\ ·\ GitLab$

## a1557304a1f649f8ad24
- **题面：** Navigate to the "Yours" tab to see your own projects
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Projects · Dashboard · GitLab$

## a472a8aa2733bcdb728b
- **题面：** View your profile page
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Byte\ Blaze$

## a5ecb8b97b12aef25a4b
- **题面：** View projects with the most stars.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /?sort=stars_desc&non_archived=true
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Projects · Dashboard · GitLab$

## a62ff500120b73023b43
- **题面：** Navigate to the Snippets page of the a11yproject.com repository.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /a11yproject/a11yproject.com/-/snippets
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Snippets.*a11yproject\.com.*GitLab$

## a87b63bb6a1c6adaa58d
- **题面：** View the Starred projects
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /dashboard/projects/starred
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Projects$

## a89c520b5fc750909f14
- **题面：** View your user profile page.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Byte\ Blaze$

## a97a93a77911d5ac61e2
- **题面：** Check the 10 pending merge requests for the A11Y Project.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /a11yproject/a11yproject.com/-/merge_requests?state=opened
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Merge requests · .+ / a11yproject\.com · GitLab$

## ae3f6ae1b09225814b05
- **题面：** Navigate to the Issues section of the a11y-syntax-highlighting repository.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/a11y-syntax-highlighting/-/issues
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Issues.*a11y\-syntax\-highlighting.*GitLab$

## b021b5e2c1ef77dc791a
- **题面：** Read the README file in Byte Blaze / a11y-syntax-highlighting.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/a11y-syntax-highlighting/-/blob/main/README.md
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:README\.md\ ·\ main\ ·\ Byte\ Blaze\ /\ a11y\-syntax\-highlighting\ ·\ GitLab|Byte\ Blaze\ /\ a11y\-syntax\-highlighting\ ·\ GitLab|Files\ ·\ main\ ·\ Byte\ Blaze\ /\ a11y\-syntax\-highlighting\ ·\ GitLab)$

## b04e1de8abf6ed90b265
- **题面：** Go to the Trending projects page
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /explore/projects/trending
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Projects · Explore · GitLab$

## b0cc2311480a18a2964a
- **题面：** View the details of the project William Ting / autojump.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /wting/autojump
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^autojump$

## b46f5a6ca9cead3d4f3d
- **题面：** Find out how to quit the local development server for The A11Y Project (a11yproject/a11yproject.com).
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## b4b0b75d50616e9f5884
- **题面：** View the DynamoRIO repository files
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /DynamoRIO/dynamorio/-/tree/master
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:Files\ ·\ master\ ·\ DynamoRIO\ /\ dynamorio\ ·\ GitLab|DynamoRIO\ /\ dynamorio\ ·\ GitLab)$

## b50aed2c8db375999852
- **题面：** Navigate to the package.json file to check the project dependencies and version information.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/a11y-syntax-highlighting/-/blob/main/package.json
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^package\.json\ ·\ main\ ·\ Byte\ Blaze\ /\ a11y\-syntax\-highlighting\ ·\ GitLab$

## b59b36d57ab4f49a9b38
- **题面：** Explore the packages directory of create-react-app.
- **分支：** （源：remaining）
  - G1 【目标对象】新建/添加的对象与题面要求一致
  - G2 【保存生效】新建/添加已持久保存生效

## b62a371ec1f0fd2c65ae
- **题面：** Explore trending projects instead of viewing all projects
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /explore/projects/trending?sort=name_asc&non_archived=true
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Projects · Explore · GitLab$

## b6560714356b242cece4
- **题面：** Navigate to the Keycloak project page
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /keycloak/keycloak
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^keycloak$

## b72270bbc00e65e78f9d
- **题面：** Navigate to the examples directory of ffmpeg-python to see usage examples
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /kkroening/ffmpeg-python/-/tree/master/examples
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^examples\ ·\ master\ ·\ Karl\ Kroening\ /\ ffmpeg\-python\ ·\ GitLab$

## ba163f10b633d3d563ac
- **题面：** Change the visibility filter from "Any" to "Public"
- **分支：** （源：remaining）
  - G1 【可见性筛选】可见性筛选 从 "Any" 改为 "Public"
  - G2 【保存生效】修改已持久保存生效

## bcb3ae7f5d488e4fc74e
- **题面：** Go to the Issues dashboard
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /dashboard/issues
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Issues$

## bd4472d5d3b4aeb32cea
- **题面：** Go to the prism directory to access Prism.js syntax highlighting themes.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/a11y-syntax-highlighting/-/tree/main/dist/prism
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^dist/prism\ ·\ main\ ·\ Byte\ Blaze\ /\ a11y\-syntax\-highlighting\ ·\ GitLab$

## c0973d623816b8755969
- **题面：** Navigate to the project page for Matt Harvey / five-video-classification-methods.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /harvitronix/five-video-classification-methods
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^five\-video\-classification\-methods$

## c1520cf4b0dff2768c10
- **题面：** Check the merge requests for the "create-react-app" project to see what changes are pending
- **分支：** （源：remaining）
  - G1 【目标对象】新建/添加的对象与题面要求一致
  - G2 【保存生效】新建/添加已持久保存生效

## c20494dcbe34a8f5a15d
- **题面：** Go to the CI/CD pipeline page to check build status.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/a11y-syntax-highlighting/-/pipelines
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Pipelines\ ·\ Byte\ Blaze\ /\ a11y\-syntax\-highlighting\ ·\ GitLab$

## c62b3c78afcb86b9aa90
- **题面：** Browse the src/resources directory in a11yproject/a11yproject.com to view accessibility resources.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## c6fcf13f7bf68c7eeaa8
- **题面：** Navigate to the article about ChatGPT as a cognitive accessibility assistive technology for TBI survivors.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /a11yproject/a11yproject.com/-/blob/main/src/posts/the-power-of-chatgpt-as-a-cognitive-accessibility-assistive-technology-for-traumatic-brain-injury-survivors.md
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^src/posts/the\-power\-of\-chatgpt\-as\-a\-cognitive\-accessibility\-assistive\-technology\-for\-traumatic\-brain\-injury\-survivors\.md\ ·\ main\ ·\ The\ A11Y\ Project\ /\ a11yproject\.com\ ·\ GitLab$

## c93d4e8f0d4025960385
- **题面：** Check the images directory to see visual examples of the themes.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/a11y-syntax-highlighting/-/tree/main/images
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^images\ ·\ main\ ·\ Byte\ Blaze\ /\ a11y\-syntax\-highlighting\ ·\ GitLab$

## cb8c0cfa83e96f568177
- **题面：** Navigate to the Commits page for the a11yproject.com repository.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /a11yproject/a11yproject.com/-/commits/main
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Commits\ ·\ main\ ·\ The\ A11Y\ Project\ /\ a11yproject\.com\ ·\ GitLab$

## cf0bd006450130707ad7
- **题面：** Navigate to the Create blank project page.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /projects/new#blank_project
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^New Project · GitLab$

## cf358579e66f4fb65142
- **题面：** Read the article about accessibility overlays.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /a11yproject/a11yproject.com/-/blob/main/src/posts/should-i-use-an-accessibility-overlay.md
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^src/posts/should\-i\-use\-an\-accessibility\-overlay\.md\ ·\ main\ ·\ The\ A11Y\ Project\ /\ a11yproject\.com\ ·\ GitLab$

## cf403699eae10ee20fbf
- **题面：** Check the project's CI/CD pipeline status.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /a11yproject/a11yproject.com/-/pipelines
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Pipelines\ ·\ The\ A11Y\ Project\ /\ a11yproject\.com\ ·\ GitLab$

## d49a2612b7547f2258b7
- **题面：** Browse project topics.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## d5a2bd7102dc26e4025a
- **题面：** Navigate to your personal dashboard
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /
  - G2 【标题/身份匹配】页面标题/目标身份匹配 Projects · Dashboard · GitLab$

## d60c623429daf82c23c2
- **题面：** Navigate to the Files page for a11y-syntax-highlighting.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/a11y-syntax-highlighting/-/tree/main
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:Files\ ·\ main\ ·\ Byte\ Blaze\ /\ a11y\-syntax\-highlighting\ ·\ GitLab)$

## d61bd48e81c74a963888
- **题面：** Sort projects by most stars instead of by name
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 projects
  - G2 【排序】按 most stars instead of by name 排序
  - G3 【保存生效】修改已持久保存生效

## d9f0cea66cae6707a274
- **题面：** Navigate to the Merge Requests section to view pending code changes for the cloud-to-butt project.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/cloud-to-butt/-/merge_requests?state=opened
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Merge requests · .+ / cloud\-to\-butt · GitLab$

## d9f72bbcc2277ea05ea0
- **题面：** View the MathJax project repository
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /mathjax/MathJax
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^MathJax$

## dac3a4f5b8f4fb6f46a1
- **题面：** Find projects related to bootstrap
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## dc3a35048980924eeddc
- **题面：** Open the Web IDE for a11yproject/a11yproject.com to edit accessibility content files.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /-/ide/project/a11yproject/a11yproject.com/edit/main/-/src/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^IDE · GitLab$

## dcfcfc714b82c979b2b7
- **题面：** Check the "resources.njk" file to see what accessibility resources are available.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /a11yproject/a11yproject.com/-/blob/main/src/resources.njk
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^src/resources\.njk\ ·\ main\ ·\ The\ A11Y\ Project\ /\ a11yproject\.com\ ·\ GitLab$

## ddf92d858f412f919b5c
- **题面：** Navigate to the Dashboard page
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /
  - G2 【标题/身份匹配】页面标题/目标身份匹配 Projects · Dashboard · GitLab$

## dee13320e98e40b2d2b3
- **题面：** Go to the dashboard to see your own projects
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /
  - G2 【标题/身份匹配】页面标题/目标身份匹配 Projects · Dashboard · GitLab$

## df5d3885ccff3b9afa51
- **题面：** Find issues labeled with "help wanted" in The A11Y Project repository
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## df894d3c63aec34c9d4b
- **题面：** View the article about color contrast to ensure accessible design.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /a11yproject/a11yproject.com/-/blob/main/src/posts/what-is-color-contrast.md
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^src/posts/what\-is\-color\-contrast\.md\ ·\ main\ ·\ The\ A11Y\ Project\ /\ a11yproject\.com\ ·\ GitLab$

## dff263bae21ba3bcf85e
- **题面：** Navigate to the Groups documentation page.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /help/user/group/index
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Groups\ \(FREE\)$

## e04b3a85f0f672baddbe
- **题面：** Check out Starred projects.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /dashboard/projects/starred
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Projects$

## e0f647ff0c84d4931459
- **题面：** Go to the dist directory to access distribution files.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/a11y-syntax-highlighting/-/tree/main/dist
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^dist\ ·\ main\ ·\ Byte\ Blaze\ /\ a11y\-syntax\-highlighting\ ·\ GitLab$

## e24355d4a0c398088a33
- **题面：** Go to the Help page.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /help
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Help · GitLab$

## e42f60025d8f01e6aa9e
- **题面：** View all your to-do items from the navigation menu
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /dashboard/todos
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^To-[Dd]o List(?: ·| \|)

## e5b0ca2d7f838ca0f30b
- **题面：** Navigate to The A11Y Project / a11yproject.com repository to view its code and contribute to the project.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /a11yproject/a11yproject.com/-/tree/main
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:Files\ ·\ main\ ·\ The\ A11Y\ Project\ /\ a11yproject\.com\ ·\ GitLab|The\ A11Y\ Project\ /\ a11yproject\.com\ ·\ GitLab)$

## e686829fc87c3067c1e3
- **题面：** Check your To-Do List to see pending tasks.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /dashboard/todos
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^To-[Dd]o List(?: ·| \|)

## ece3e556710b7e78c6e3
- **题面：** Visit the Analytics section to view project statistics and metrics.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /a11yproject/a11yproject.com/-/value_stream_analytics
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Value\ Stream\ Analytics\ ·\ The\ A11Y\ Project\ /\ a11yproject\.com\ ·\ GitLab$

## efb917a8ca73df1d30f8
- **题面：** Navigate to the src directory to view the source code files of the A11Y Project website.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /a11yproject/a11yproject.com/-/tree/main/src
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^src\ ·\ main\ ·\ The\ A11Y\ Project\ /\ a11yproject\.com\ ·\ GitLab$

## f2bf678c424bd20b3f48
- **题面：** Sort the projects by the latest updated date.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 projects
  - G2 【排序】按 the latest updated date 排序
  - G3 【保存生效】修改已持久保存生效

## f4a26d03fafc52d9d384
- **题面：** Navigate to the DynamoRIO project page
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /DynamoRIO/dynamorio
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^dynamorio$

## f4c18bb3b643fbfccbf6
- **题面：** View the Topics page for projects
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /explore/projects/topics
  - G2 【标题/身份匹配】页面标题/目标身份匹配 Topics.*GitLab$

## f6a131e5e95ceb191a7b
- **题面：** View all open merge requests for the a11yproject.com repository.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /a11yproject/a11yproject.com/-/merge_requests?state=opened
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Merge requests · .+ / a11yproject\.com · GitLab$

## f9010c6ffc865e4dcaff
- **题面：** View the list of all pending to-dos.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /dashboard/todos
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^To-[Dd]o List(?: ·| \|)

## f9184b91bc1afda0a62f
- **题面：** Navigate to the dist directory to view distribution files for different platforms.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/a11y-syntax-highlighting/-/tree/main/dist
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^dist\ ·\ main\ ·\ Byte\ Blaze\ /\ a11y\-syntax\-highlighting\ ·\ GitLab$

## f96a4bf6867ab89d8712
- **题面：** Navigate to the Groups dashboard page.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /dashboard/groups
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Groups$

## fe984f40428cd4ae9a21
- **题面：** Check the issues for the Eugen / tutorials project.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /eugenp/tutorials/-/issues
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Issues.*tutorials.*GitLab$

## ffd41f148a65999bf5c1
- **题面：** Check the src/css directory in a11yproject/a11yproject.com to review the project styles.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /a11yproject/a11yproject.com/-/tree/main/src/css
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^src/css\ ·\ main\ ·\ The\ A11Y\ Project\ /\ a11yproject\.com\ ·\ GitLab$

## 1146455b11c091160db0
- **题面：** Navigate to the User Diaries page to explore user-generated content.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /diary
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Users'\ Diaries$

## 1206a605e174647d60b7
- **题面：** View the loaded map-edit history for the area centered at latitude 42.896, longitude -75.108, at map zoom level 7. The native history list must finish loading for that geographic view; an empty list is acceptable.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /history#map=7/42.896/-75.108
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Changesets$

## 125732d3658ab4daee02
- **题面：** Navigate to the Copyright page to learn about the licensing of OpenStreetMap data.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /copyright
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Copyright\ and\ License$

## 152a4fb5ab907c0bb3bd
- **题面：** Navigate to the GPS Traces page to view and manage public GPS trace uploads.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /traces
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Public\ GPS\ Traces$

## 17f7bae0d2e1ede409aa
- **题面：** Get driving directions from New York City to Buffalo
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /directions?engine=fossgis_osrm_car&route=40.7127281%2C-74.0060152%3B42.8867166%2C-78.8783922
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Directions$

## 1c4b6dfbf0baeddd0a11
- **题面：** Visit the GPS Traces page to see user-uploaded GPS data.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /traces
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Public\ GPS\ Traces$

## 1d869d7aeb19f892c1fd
- **题面：** View the map history.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /history
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Changesets$

## 20a1eabbba54974e8549
- **题面：** Explore OpenStreetMap communities around the world
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /communities
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Communities$

## 2247955f168079d2f416
- **题面：** Go to the Export page to download map data
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /export#map=7/42.896/-76.476
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Export$

## 26b05ad8b662075818e0
- **题面：** Navigate to the map history page.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /history
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Changesets$

## 2839e82dcf1d04ce3405
- **题面：** Explore the Help section on OpenStreetMap.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /help
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Getting\ Help$

## 2ae71309cbaee28068be
- **题面：** Change the transportation mode from Car to Bicycle for the route from Upper Manhattan to Brooklyn.
- **分支：** （源：remaining）
  - G1 【交通方式】交通方式 从 "Car" 改为 "Bicycle"
  - G2 【保存生效】修改已持久保存生效

## 2b6697453212b22684b7
- **题面：** Find driving directions from New York City to Boston
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 2cd738b9022714136a08
- **题面：** Navigate to GPS Traces to view and upload GPS tracks.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /traces
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Public\ GPS\ Traces$

## 2d60238fe7e05488e7dc
- **题面：** View the turn-by-turn directions for driving from Central Park to Times Square.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /directions?engine=fossgis_osrm_car&route=40.7827725%2C-73.9653627406542%3B40.75701215%2C-73.98597092538824
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Directions$

## 332ab0c60fb956324d6b
- **题面：** Get walking directions from Times Square to Central Park.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /directions?engine=fossgis_osrm_foot&route=40.75701215%2C-73.98597092538824%3B40.7827725%2C-73.9653627406542
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Directions$

## 335e2b71cc94e5424c47
- **题面：** Visit the User Diaries page to explore community diaries.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /diary
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Users'\ Diaries$

## 375587bae31aeb91b358
- **题面：** Reverse the start and end points of your planned route
- **分支：** （源：remaining）
  - G1 【反转】反转 start and end points of your planned route
  - G2 【保存生效】修改已持久保存生效

## 38b80741a9c1db10863a
- **题面：** Change the image format from PNG to JPEG when downloading the map
- **分支：** （源：remaining）
  - G1 【图片格式】图片格式 从 "PNG" 改为 "JPEG"
  - G2 【保存生效】修改已持久保存生效

## 3ae056a94b5aa2489496
- **题面：** Access GPS traces
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /traces
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Public\ GPS\ Traces$

## 3d47015e3739a81781e9
- **题面：** Visit the Export page to download map data.
- **分支：** （源：remaining）
  - G1 【导出成功】导出成功：目标为 page to download map data

## 403c8f4eef512e1fc9f6
- **题面：** Find directions from Times Square to Brooklyn Bridge.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 419826e580e630c45e9a
- **题面：** Navigate to the sign-up page.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /user/new
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Sign Up$

## 47070077b58a50577da2
- **题面：** View information about New York State.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /relation/61320
  - G2 【标题/身份匹配】页面标题/目标身份匹配 OpenStreetMap

## 4853369b6ffe4cb3a1b6
- **题面：** Change the transportation mode from car to bicycle for the New York City to Boston route
- **分支：** （源：remaining）
  - G1 【交通方式】交通方式 从 "car" 改为 "bicycle"
  - G2 【保存生效】新建/添加已持久保存生效

## 4b0f1bbfc2d5212ed230
- **题面：** View OpenStreetMap copyright information.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /copyright
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Copyright\ and\ License$

## 4c1acec2d1077bf99b98
- **题面：** Navigate to the About page to learn more about OpenStreetMap and how it works.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /about
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^OpenStreetMap\ provides\ map\ data\ for\ thousands\ of\ websites,\ mobile\ apps,\ and\ hardware\ devices$

## 4e0ee20a20468999dbdd
- **题面：** Change the transportation mode from walking to driving for directions between 40.74800, -73.98600 and 40.75300, -73.97700
- **分支：** （源：remaining）
  - G1 【交通方式】交通方式 从 "walking" 改为 "driving"
  - G2 【保存生效】修改已持久保存生效

## 4f79336bf1b3f44b0bba
- **题面：** Visit the About page to learn more about OpenStreetMap.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /about
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^OpenStreetMap\ provides\ map\ data\ for\ thousands\ of\ websites,\ mobile\ apps,\ and\ hardware\ devices$

## 518f2c7a3ad50473ed54
- **题面：** View user diaries page.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /diary
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Users'\ Diaries$

## 52a348d197af6b172b3a
- **题面：** Check what map layers are available for viewing New York City
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /
  - G2 【标题/身份匹配】页面标题/目标身份匹配 OpenStreetMap

## 56157a8c8a5da7cca552
- **题面：** Navigate to the Help page on OpenStreetMap.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /help
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Getting\ Help$

## 57f5f6ebff56ba347091
- **题面：** Navigate to the Log In page to access your OpenStreetMap account
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /login
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Login$

## 5a05a81eb743468584a8
- **题面：** Calculate bicycle directions from Battery Park to Chinatown
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /directions?engine=fossgis_osrm_bike&route=40.703030749999996%2C-74.01578792289277%3B40.7164913%2C-73.9962504
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Directions$

## 60203c8b12395c0dfda0
- **题面：** Navigate to the GPS Traces page to view recent GPS trace uploads.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /traces
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Public\ GPS\ Traces$

## 6116481dc1f646968a99
- **题面：** Access all public GPS traces.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /traces
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Public\ GPS\ Traces$

## 627b8cdd111a780bff97
- **题面：** Navigate to the Log In page to access your OpenStreetMap account.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /login
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Login$

## 62f63c2cbfe7ec9e8575
- **题面：** Navigate to the Export page to download map data for offline use or other applications.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /export#map=7/42.896/-75.108
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Export$

## 63bdcd0914e09c7a5dfe
- **题面：** Navigate to the login page to sign in to your OpenStreetMap account.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /login
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Login$

## 65e78b91a377e73a3591
- **题面：** Navigate to the Help page to find guidance on using OpenStreetMap.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /help
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Getting\ Help$

## 6a355747c135f6adcf2b
- **题面：** Reverse the direction of your current route
- **分支：** （源：remaining）
  - G1 【反转】反转 direction of your current route
  - G2 【保存生效】修改已持久保存生效

## 6de79f8d7cb07a5f862f
- **题面：** Check what map layers are available for viewing.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /
  - G2 【标题/身份匹配】页面标题/目标身份匹配 OpenStreetMap

## 6e27e10e6049cee4f85d
- **题面：** Navigate to the communities page.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /communities
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Communities$

## 6fe7e3e9ec16b2f7dc0e
- **题面：** Check out the User Diaries section on OpenStreetMap.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /diary
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Users'\ Diaries$

## 71099c255a288120463c
- **题面：** Find help documentation for using OpenStreetMap
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 72a50b127b7f10d616de
- **题面：** Find directions from Times Square to Central Park in New York City
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 72fed1657cdc776e256b
- **题面：** Visit the Copyright page of OpenStreetMap.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /copyright
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Copyright\ and\ License$

## 75e650efe8eade8a4c7e
- **题面：** Find bicycle routes from Battery Park to the Brooklyn Bridge.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 75ef11e2ffecd43e9ebe
- **题面：** Search for the location of Syracuse University on the map.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 7611787b61784db89c56
- **题面：** View the map history to see recent changes.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /history
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Changesets$

## 796aedea524106e85764
- **题面：** Navigate to the Communities page on OpenStreetMap.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /communities
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Communities$

## 876dfbc29d739c619985
- **题面：** Find New York City on the map
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 87a988cb58f97e6daa11
- **题面：** Access the help pages
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /help
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Getting\ Help$

## 891a1ca187bffd53f84b
- **题面：** Navigate to the History page to view changes.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /history
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Changesets$

## 8a4c19948ede33275bad
- **题面：** Find the location of the City of New York, New York, United States on the map.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 8cfa16597c7e6c7c6ba2
- **题面：** Check GPS Traces on OpenStreetMap.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /traces
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Public\ GPS\ Traces$

## 8d24f1548027c0099afa
- **题面：** Enter "Empire State Building" as the starting point for directions
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /directions
  - G2 【标题/身份匹配】页面标题/目标身份匹配 OpenStreetMap

## 927e9e578112cd1b38b9
- **题面：** Navigate to the Help page to find OpenStreetMap resources and support
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /help
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Getting\ Help$

## 95155cf17818f58e8de1
- **题面：** Visit the Help page of OpenStreetMap.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /help
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Getting\ Help$

## 95fc15b080365667cbf1
- **题面：** Open the layers menu to explore map layers.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /
  - G2 【标题/身份匹配】页面标题/目标身份匹配 OpenStreetMap

## 97ee5a6311e5609b6bb0
- **题面：** View turn-by-turn directions for driving from New York City to Boston
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /directions?engine=fossgis_osrm_car&route=40.7127281%2C-74.0060152%3B42.3554334%2C-71.060511
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Directions$

## 990fa9ad1f82d2020cf4
- **题面：** Navigate to the Communities page to find community resources.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /communities
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Communities$

## 9c0dc55a93608d8dcd85
- **题面：** Navigate to the History page to view map edit history
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /history
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Changesets$

## 9c6bc09e1b0e980f8711
- **题面：** Visit the History page of OpenStreetMap.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /history
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Changesets$

## 9cdf144944f9b48f827d
- **题面：** View the turn-by-turn directions from Times Square to Central Park.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /directions?engine=fossgis_osrm_car&route=40.75701215%2C-73.98597092538824%3B40.7827725%2C-73.9653627406542
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Directions$

## 9cf6173b1aef7102f868
- **题面：** View copyright information for OpenStreetMap data
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /copyright
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Copyright\ and\ License$

## a17999bae382ce36ae2e
- **题面：** Navigate to the Copyright page to review usage terms.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /copyright
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Copyright\ and\ License$

## a2616ab4773e68085681
- **题面：** Change transportation mode for directions
- **分支：** （源：remaining）
  - G1 【变更字段】变更 transportation mode
  - G2 【保存生效】修改已持久保存生效

## a768923edd69b0f4e012
- **题面：** Explore Communities.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /communities
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Communities$

## ab164fc0f7c94acc73ae
- **题面：** Reverse the directions to show the route from Boston to New York City
- **分支：** （源：remaining）
  - G1 【反转】反转 directions to show the route
  - G2 【保存生效】新建/添加已持久保存生效

## ab91d8ac4a692f9a12bc
- **题面：** Navigate to the GPS Traces page to view or upload GPS tracks
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /traces
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Public\ GPS\ Traces$

## ac350bf768c4f363d703
- **题面：** View the detailed turn-by-turn directions for driving from New York City to Boston.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /directions?engine=fossgis_osrm_car&route=40.7127281%2C-74.0060152%3B42.3554334%2C-71.060511
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Directions$

## afe62847a90f86ae7221
- **题面：** Navigate to the Help page to find documentation and guidance on using OpenStreetMap.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /help
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Getting\ Help$

## b129a38e1f5b6e147357
- **题面：** Learn more about OpenStreetMap by visiting the About page
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /about
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^OpenStreetMap\ provides\ map\ data\ for\ thousands\ of\ websites,\ mobile\ apps,\ and\ hardware\ devices$

## b2580ad162a3aac41a4a
- **题面：** View the Copyright and License page for usage information
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /copyright
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Copyright\ and\ License$

## b37c546145d583238253
- **题面：** View GPS Traces
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /traces
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Public\ GPS\ Traces$

## b5610ad28e5c883a1283
- **题面：** View the history of changes made to the current map area.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /history#map=7/42.896/-75.108
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Changesets$

## b74dd7e54f3bd1877d88
- **题面：** Retrieve directions from 40.7570, -73.9860 to 40.7830, -73.9650.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /directions?engine=fossgis_osrm_car&route=40.757%2C-73.986%3B40.783%2C-73.965
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Directions$

## b75f1090bfbfccbda00a
- **题面：** Open the About page to view the information about OpenStreetMap and its mission. Leave that page open; a written summary is not required.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /about
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^OpenStreetMap\ provides\ map\ data\ for\ thousands\ of\ websites,\ mobile\ apps,\ and\ hardware\ devices$

## b87c2f01c9d593ea6c2e
- **题面：** Get driving directions from Times Square to Central Park
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /directions?engine=fossgis_osrm_car&route=40.75701215%2C-73.98597092538824%3B40.7827725%2C-73.9653627406542
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Directions$

## bda9d6ba4ed577e3043e
- **题面：** Check GPS Traces.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /traces
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Public\ GPS\ Traces$

## c0537305ebe53ca2c8fe
- **题面：** View the History page.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /history
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Changesets$

## c1cb8e0c06819d3c64c3
- **题面：** Visit the Help page for OpenStreetMap assistance.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /help
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Getting\ Help$

## c4d9cbaedc996c198539
- **题面：** View the history of map edits and changes.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /history
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Changesets$

## c5045fb59f02b7e8e776
- **题面：** Change the transportation mode to Bicycle for directions from Times Square, New York to Central Park, New York.
- **分支：** （源：remaining）
  - G1 【交通方式】交通方式 改为 "Bicycle"
  - G2 【保存生效】新建/添加已持久保存生效

## c57ca5acec017c6d0b80
- **题面：** View the turn-by-turn directions for driving from New York City to Boston
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /directions?engine=fossgis_osrm_car&route=40.7127281%2C-74.0060152%3B42.3554334%2C-71.060511
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Directions$

## c8fc3a4a90c6e7887bfb
- **题面：** View the map of Lower Manhattan in New York City
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /search?query=Lower+Manhattan%2C+New+York#map=7/42.896/-75.108
  - G2 【标题/身份匹配】页面标题/目标身份匹配 OpenStreetMap

## c9fde185c811f7d75985
- **题面：** Search for New York City on the map
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## cd2c2283fa8faf019beb
- **题面：** Review the Copyright and License information
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /copyright
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Copyright\ and\ License$

## cd8482b9004bc691462c
- **题面：** Get walking directions from Empire State Building to Grand Central Station
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /directions?engine=fossgis_osrm_foot&route=40.74844205%2C-73.98565890160751%3B40.752701200000004%2C-73.97724987363358
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Directions$

## cda227cb00c37fb530b7
- **题面：** Find the password recovery page if you forgot your password
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## cf7327f2ac74d5bf59c7
- **题面：** Find the location of the Empire State Building.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## cf89b4d2d14bdba49cdf
- **题面：** Navigate to the login page.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /login
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Login$

## d0239a40f99dbcdd4eb4
- **题面：** Visit the Communities page to learn about OpenStreetMap communities.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /communities
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Communities$

## d551aed5a825950ae0a4
- **题面：** Visit the About page to understand more about OpenStreetMap and its mission.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /about
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^OpenStreetMap\ provides\ map\ data\ for\ thousands\ of\ websites,\ mobile\ apps,\ and\ hardware\ devices$

## d664b45d475e9aed68c5
- **题面：** Calculate walking directions from Empire State Building to Grand Central Station
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /directions?engine=fossgis_osrm_foot&route=40.74844205%2C-73.98565890160751%3B40.752701200000004%2C-73.97724987363358
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Directions$

## dd7101637466a581eb7f
- **题面：** Navigate to the directions page to get driving directions between two locations.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /directions
  - G2 【标题/身份匹配】页面标题/目标身份匹配 OpenStreetMap

## df00c7d7e2aa973cb398
- **题面：** Enter Chicago as the starting point for directions
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /directions
  - G2 【标题/身份匹配】页面标题/目标身份匹配 OpenStreetMap

## dff54d59d0408f850bc1
- **题面：** View the step-by-step walking instructions from Times Square to Central Park
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /directions?engine=fossgis_osrm_foot&route=40.75701215%2C-73.98597092538824%3B40.7827725%2C-73.9653627406542
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Directions$

## e538c1e8f1d219467791
- **题面：** Visit the OpenStreetMap Communities page to learn about local chapters and community groups
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /communities
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Communities$

## e63a2acf5af471d0e22a
- **题面：** Calculate bicycle route from Brooklyn Bridge to Hudson River Park
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /directions?engine=fossgis_osrm_bike&route=40.705216050000004%2C-73.99575931949556%3B40.71951575%2C-74.01281170139342
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Directions$

## ec43f648fa3c065455a6
- **题面：** View the History of map changes
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /history
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Changesets$

## ed6b1fa7d2bc72e6e086
- **题面：** Navigate to view all GPS traces.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /traces
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Public\ GPS\ Traces$

## eecb7b3837b34a864e11
- **题面：** Display the local Communities directory with its Local Chapters and Other Groups sections. The task ends at this local directory; no contact with other mappers is required.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /communities
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Communities$

## f18d4e349ce46285ef6d
- **题面：** Find directions from New York City to Boston using the map.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## f2a128709c8ee76b9b34
- **题面：** Get walking directions from Ithaca to Cornell University
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /directions?engine=fossgis_osrm_foot&route=42.4396039%2C-76.4968019%3B42.4529076%2C-76.48008423030923
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Directions$

## f624c5d271349f15d8cc
- **题面：** Get help with using OpenStreetMap
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /help
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Getting\ Help$

## f6424e7970f29cf8c4b6
- **题面：** Navigate to the "Find directions between two points" feature.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /directions
  - G2 【标题/身份匹配】页面标题/目标身份匹配 OpenStreetMap

## f9e8b9166755a8e6195c
- **题面：** Access map layers settings
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /
  - G2 【标题/身份匹配】页面标题/目标身份匹配 OpenStreetMap

## fc9afa15a918a64d56b0
- **题面：** Reverse the directions for the route from 40.7830, -73.9650 to 40.7570, -73.9860.
- **分支：** （源：remaining）
  - G1 【反转】反转 directions for the route
  - G2 【保存生效】修改已持久保存生效

## fdba5c41e32189d28b38
- **题面：** Navigate to view detailed information about New York City.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /relation/175905
  - G2 【标题/身份匹配】页面标题/目标身份匹配 OpenStreetMap

## feaaa70986880d89a2b1
- **题面：** Navigate to the sign-up page to create a new user account.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /user/new
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Sign Up$

## feb76a089ef575ba2290
- **题面：** Navigate to the User Diaries page to read or write blog posts about mapping activities.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /diary
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Users'\ Diaries$

## 171c2a622c8254444b2d
- **题面：** Check out the Footwear section in Sports & Outdoors category.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /catalog/category/view/id/153/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:Fan\ Shop|Footwear|Sports\ \&\ Outdoors)$

## 1b33725b7a34dc0e6647
- **题面：** View the details of the Uttermost Volterra Crackled Taupe-Gray Ceramic Table Lamp in my cart
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /uttermost-volterra-crackled-taupe-gray-ceramic-table-lamp.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:Uttermost\ Volterra\ Crackled\ Taupe\-Gray\ Ceramic\ Table\ Lamp)$

## 1b5ae46def0984fbad90
- **题面：** Navigate to My Account page
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /customer/account/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^My Account$

## 1ddfd3262a0cb9633c1f
- **题面：** Navigate to the homepage by clicking the store logo.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^One\ Stop\ Market$

## 20a9d05cb8472913c526
- **题面：** Browse Clothing, Shoes & Jewelry section
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 29f9418c0635097d9ebb
- **题面：** View details for the Pre-baked Gingerbread House Kit.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /pre-baked-gingerbread-house-kit-value-pack-17-oz-pack-of-2-total-34-oz.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Pre\-baked\ Gingerbread\ House\ Kit\ Value\ Pack,\ 17\ oz\.,\ Pack\ of\ 2,\ Total\ 34\ oz\.$

## 2af51cb8f88a8e30a8ea
- **题面：** Go to page 2 of Sports & Outdoors products.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /sports-outdoors.html?p=2
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Sports\ \&\ Outdoors$

## 2c578fb73f030f3051c9
- **题面：** View Sports & Outdoors products
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /sports-outdoors.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Sports\ \&\ Outdoors(?: Items .*)?$

## 2f5273f55bc91406ac64
- **题面：** Navigate to the Add Your Review section for the Nightfox Vulpes Handheld Digital Night Vision Goggles.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /nightfox-vulpes-handheld-digital-night-vision-goggles-integrated-laser-rangefinder-full-high-definition-fhd-1080p-sensor-records-video-audio-220yd-range-6x-magnification-hunting-security.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Nightfox\ Vulpes\ Handheld\ Digital\ Night\ Vision\ Goggles\ \|\ Integrated\ Laser\ Rangefinder\ \|\ Full\ High\ Definition\ FHD\ 1080p\ Sensor\ \|\ Records\ Video\ \+\ Audio\ \|\ 220yd\ Range,\ 6x\ Magnification\ \|\ Hunting,\ Security$

## 3279630bdac6762c0e80
- **题面：** View details of an item in your cart.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /plus-size-lingerie-for-women-sexy-for-sex-naughty-eyelash-lace-bodysuit-naughty-mesh-one-piece-teddy-bodysuit-outfits.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:Plus\ Size\ Lingerie\ for\ Women\ Sexy\ for\ Sex\ Naughty\ Eyelash\ Lace\ Bodysuit\ Naughty\ Mesh\ One\ Piece\ Teddy\ Bodysuit\ Outfits|Uttermost\ Volterra\ Crackled\ Taupe\-Gray\ Ceramic\ Table\ Lamp|NOZE\ Rustic\ Coat\ Rack\ Wall\ Mounted\ Shelf\ with\ 4\ Hooks,\ Hanging\ Entryway\ Organizer\ for\ Mug\ Coffee\ Cup,\ Holding\ Solid\ Wooden\ Shelf\ with\ 2\ Baskets\ for\ Kitchen\ Living\ Room,\ Bathroom\ and\ Bedroom)$

## 3471163bbf9ffae90bd6
- **题面：** From the shopping cart page, open My Account.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /customer/account/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^My Account$

## 34ee7f4eb530b45150d7
- **题面：** Browse Computers & Accessories in the Electronics category
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 350b6731f04826f9c150
- **题面：** Navigate to your wish list to see saved items.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /wishlist/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^My Wish List$

## 3a09a847c16c7a460f51
- **题面：** Go to the My Wish List page.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /wishlist/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^My Wish List$

## 3fa4cc7e698f78de016e
- **题面：** Go to the home page.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^One Stop Market$

## 407c66458bea9334bb45
- **题面：** Return to homepage
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^One Stop Market$

## 43d4e8115ed9a46cbdf5
- **题面：** Browse Home Audio electronics products
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 44a5f6fe89bad66146a5
- **题面：** Go to My Wish List to see saved items I want to purchase later.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /wishlist/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^My Wish List$

## 461efec0d1b9b6aa13b3
- **题面：** Check out the Fan Shop category to find sports team merchandise.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /catalog/category/view/id/30/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:Fan\ Shop|Sports\ \&\ Outdoors)$

## 462e172d650a6a327384
- **题面：** Navigate to the homepage
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^One Stop Market$

## 47018a36e8e9ada2e1f6
- **题面：** View the Privacy and Cookie Policy page.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /privacy-policy-cookie-restriction-mode
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Privacy and Cookie Policy$

## 47818cdbf9860904749a
- **题面：** View all product images of the Pre-baked Gingerbread House Kit Value Pack
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /pre-baked-gingerbread-house-kit-value-pack-17-oz-pack-of-2-total-34-oz.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Pre\-baked\ Gingerbread\ House\ Kit\ Value\ Pack,\ 17\ oz\.,\ Pack\ of\ 2,\ Total\ 34\ oz\.$

## 481d4ba0c15fdbe61b5f
- **题面：** View details of the Uttermost Volterra Table Lamp in my cart
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /uttermost-volterra-crackled-taupe-gray-ceramic-table-lamp.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:Uttermost\ Volterra\ Crackled\ Taupe\-Gray\ Ceramic\ Table\ Lamp)$

## 485301523758df7e924a
- **题面：** Explore Fragrance section to find perfumes and colognes.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /catalog/category/view/id/21/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:Beauty\ \&\ Personal\ Care|Fragrance)$

## 4d256d0e203249002c5d
- **题面：** Open the Grocery & Gourmet Food category listing page.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /grocery-gourmet-food.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Grocery\ \&\ Gourmet\ Food$

## 4d9b34a7c42cfaf6eee8
- **题面：** Browse Computers & Accessories
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 4dc2fba06826c43c2081
- **题面：** Find Cell Phones & Accessories.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 515b0e8965d5353c0488
- **题面：** Navigate to the DkRgVNY Lace Bodysuit product page to view details and purchase options.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /dkrgvny-lingerie-sheer-lace-mini-babydoll-teddy-sexy-sleepwear-backless-bodysuit-babydoll-underwear-perspective-bodysuit.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:DkRgVNY\ Lingerie\ Sheer\ Lace\ Mini\ Babydoll\ Teddy\ Sexy\ Sleepwear\ Backless\ Bodysuit\ Babydoll\ Underwear\ Perspective\ Bodysuit|DkRgVNY\ Lace\ Spcling\ Lingerie\ Womens\ Sexy\ Hollow\ Out\ Underwear\ Bodysuit\ One\ Piece\ Snap\ Crotch\ Clubwear\ Teddy\ Bodysuit|DkRgVNY\ Women\ One\ Piece\ Lingerie\ Sexy\ Lace\ Bodysuit\ Deep\ V\ Teddy\ Lace\ Babydoll\ Boudoir\ Outfits\ Tops\ Jumpsuit\ Mini\ Tops|DkRgVNY\ Women\ Sexy\ Lingerie\ Lace\ Bodysuit\ Floral\ One\ Piece\ Exotic\ Naughty\ Plunging\ Boudoir\ Mini\ Outfits\ Pajamas\ Jumpsuit|DkRgVNY\ Women's\ One\ Piece\ Teddy\ Plunging\ Lace\ Bodysuit\ Elegant\ Honeymoon\ Lingerie\ Boudoir\ Outfits\ Tops\ Underwear\ Bodysuit|DkRgVNY\ Women\ Sexy\ Lingerie\ Cut\ Out\ Lace\ Bodysuit\ Strappy\ Deep\ V\ Teddy\ One\ Piece\ Naughty\ Bodysuit\ Nightwear\ Mini\ Babydoll|DkRgVNY\ Lingerie\ for\ Women\ Lace\ Teddy\ Bodysuit\ Naughty\ Sexy\ One\ Piece\ Deep\ V\ Lingerie,Lingerie\ Deep\ V\ Bodysuit\ Underwear\ Tops)$

## 5434dd76921747d23f19
- **题面：** Navigate to the Indoor Pet Camera product page.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /indoor-pet-camera-hd-1080p-no-wifi-security-camera-with-night-vision-no-built-in-baterry.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:Indoor\ Pet\ Camera,\ HD\ 1080P\ No\ WiFi\ Security\ Camera\ with\ Night\ Vision\-No\ Built\-in\ Baterry)$

## 55849c39acd62e0ba53c
- **题面：** Read customer reviews for the St Patricks Day T-Shirt
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /custom-jersey-style-st-patrick-s-day-t-shirts-saint-pattys-tee-irish-outfits.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Custom\ Jersey\ Style\ St\ Patrick's\ Day\ T\ Shirts\ \-\ Saint\ Pattys\ Tee\ \&\ Irish\ Outfits$

## 577734fce9bc8d0ccc0a
- **题面：** View your wish list.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /wishlist/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^My Wish List$

## 5e4e4bdfddf5c970b189
- **题面：** Go to the wishlist to view saved items.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /wishlist/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^My Wish List$

## 5f1e7a9e4abf805bf696
- **题面：** Browse Health & Household products
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 5f915e052d4a79991319
- **题面：** Check your wish list items.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /wishlist/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^My Wish List$

## 6165f8b9814811d8268d
- **题面：** View popular search terms to discover trending products.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /search/term/popular/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Popular Search Terms$

## 61e931757c267354df6e
- **题面：** Navigate to the Beauty & Personal Care category page to explore more products on sale.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /beauty-personal-care.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Beauty\ \&\ Personal\ Care$

## 6332b11635191f369588
- **题面：** View the product details tab for the Gingerbread House Kit
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /pre-baked-gingerbread-house-kit-value-pack-17-oz-pack-of-2-total-34-oz.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Pre\-baked\ Gingerbread\ House\ Kit\ Value\ Pack,\ 17\ oz\.,\ Pack\ of\ 2,\ Total\ 34\ oz\.$

## 66e55986c14ac65764ce
- **题面：** Browse the Electronics category for additional products
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 66e6a9acf3a473bf7e1a
- **题面：** Navigate to the homepage/main store page to start browsing from the beginning.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^One Stop Market$

## 69f1edb6f1af25accf6e
- **题面：** Go to My Wish List.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /wishlist/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^My Wish List$

## 6b0e7963de55871f722e
- **题面：** View Office Products category
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /office-products.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Office\ Products$

## 6ef9cae520ca410ae9bc
- **题面：** Visit the My Wish List page.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /wishlist/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^My Wish List$

## 7281659d6bc7b5693147
- **题面：** View the advanced search options from the shopping cart
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /catalogsearch/advanced/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Advanced Search$

## 73098cd105cad57dae36
- **题面：** Navigate to the homepage from checkout.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^One Stop Market$

## 74c0786bd3b90d0d43dc
- **题面：** Explore Cell Phones & Accessories products.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /catalog/category/view/id/12/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:Cell\ Phones\ \&\ Accessories)$

## 7d589e130821a8d5d6d4
- **题面：** Navigate to My Account page to view account settings and order history.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /customer/account/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^My Account$

## 801e4bd6c7e89a258185
- **题面：** View the Clothing subcategory in Sports & Outdoors.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /catalog/category/view/id/148/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:Clothing|Fan\ Shop|Sports\ \&\ Outdoors)$

## 812b02d0eefaf7f0096d
- **题面：** Navigate to the Advanced Search page to search for specific products using detailed criteria.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /catalogsearch/advanced/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Advanced Search$

## 878a9089634436ffb19c
- **题面：** Navigate to your account page to manage your personal information and orders.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /customer/account/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^My Account$

## 8b9dcf2f0f865e8c75d4
- **题面：** Browse Sports & Outdoors products.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 8dc3e1e6ce058c19389d
- **题面：** View the previous product image of the Pre-baked Gingerbread House Kit Value Pack
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /pre-baked-gingerbread-house-kit-value-pack-17-oz-pack-of-2-total-34-oz.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Pre\-baked\ Gingerbread\ House\ Kit\ Value\ Pack,\ 17\ oz\.,\ Pack\ of\ 2,\ Total\ 34\ oz\.$

## 8fff38c628082c80b23f
- **题面：** Navigate to the One Stop Market homepage.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^One Stop Market$

## 974d6949277c3e8d3576
- **题面：** Look for products in Home & Kitchen department.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 9af0eaafc0ef7af9b148
- **题面：** Navigate to the Beauty & Personal Care category from the shopping cart
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /beauty-personal-care.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Beauty\ \&\ Personal\ Care$

## 9d6df92133d7b96b2a34
- **题面：** Navigate to newsletter subscription settings
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /newsletter/manage/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Newsletter Subscription$

## a176133f5abe1666f0fc
- **题面：** View my account information
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /customer/account/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:My Account|Edit Account Information)$

## a18d1a580833c52ff7ba
- **题面：** Visit Address Book page.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /customer/address/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Address Book$

## a43a425395d6382d7b74
- **题面：** Navigate to the Advanced Search page to search for specific products.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /catalogsearch/advanced/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Advanced Search$

## a4dd965e3cd5be9680e8
- **题面：** Navigate to page 2 of Beauty & Personal Care products.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /beauty-personal-care.html?p=2
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Beauty\ \&\ Personal\ Care$

## a9464b0455b864b0d783
- **题面：** View details of order #000000187 and its status.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /sales/order/view/order_id/187/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Order # 000000187$

## a9ca6ac6a5daefe0f7db
- **题面：** Browse Beauty & Personal Care category.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## b24ffca0d3cd2ffd149a
- **题面：** Look at the reviews for the Orange Vanilla Caffeine-free Fruit Infusion tea.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /elmwood-inn-fine-teas-orange-vanilla-caffeine-free-fruit-infusion-16-ounce-pouch.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Elmwood\ Inn\ Fine\ Teas,\ Orange\ Vanilla\ Caffeine\-free\ Fruit\ Infusion,\ 16\-Ounce\ Pouch$

## b2d4e74ce1741466327c
- **题面：** Go to My Account page to view your account information.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /customer/account/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^My Account$

## b7b15a656b0e8d3e24e3
- **题面：** View details of order #000000187.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /sales/order/view/order_id/187/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Order # 000000187$

## b84c4c6420878baa3931
- **题面：** Go to Electronics section.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /electronics.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Electronics(?: Items .*)?$

## c1602ada9ddbed90235d
- **题面：** Look at the Body Glide Original Anti-Chafe Balm product.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /body-glide-original-anti-chafe-balm.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Body\ Glide\ Original\ Anti\-Chafe\ Balm$

## c23cb28a60659f46bc77
- **题面：** Navigate to My Account page to view your account information.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /customer/account/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^My Account$

## c2eff5ae8662187e0b2a
- **题面：** Return to Beauty & Personal Care category
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /beauty-personal-care.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Beauty\ \&\ Personal\ Care$

## c8c083231e99c08e5f7f
- **题面：** Read the reviews for the Pre-baked Gingerbread House Kit Value Pack.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /pre-baked-gingerbread-house-kit-value-pack-17-oz-pack-of-2-total-34-oz.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Pre\-baked\ Gingerbread\ House\ Kit\ Value\ Pack,\ 17\ oz\.,\ Pack\ of\ 2,\ Total\ 34\ oz\.$

## cc37ba9f712476e10ef4
- **题面：** Go to the product details page for the Mineralogie All Natural Lip Gloss
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /mineralogie-all-natural-lip-gloss-ruby-rose.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:Mineralogie\ All\ Natural\ Lip\ Gloss,\ Ruby\ Rose)$

## cd6d93e84b7fc055ac72
- **题面：** Browse Electronics products
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## cdbd54848ef12b7c0726
- **题面：** Navigate to page 3 of the Sports & Outdoors product listings
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /sports-outdoors.html?p=3
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Sports\ \&\ Outdoors$

## cf80cb6a7585ba670c6a
- **题面：** Navigate to page 2 of the Sports & Outdoors products to see more items.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /sports-outdoors.html?p=2
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Sports\ \&\ Outdoors$

## d54d5750944475dd180a
- **题面：** Browse Home & Kitchen category.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## d5fa1b3e20f88b8a6ac5
- **题面：** Navigate to the Beauty & Personal Care category to browse products.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /beauty-personal-care.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Beauty\ \&\ Personal\ Care$

## d6c65fb8216c165efc2f
- **题面：** Access the Advanced Search page.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /catalogsearch/advanced/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Advanced Search$

## def5a8a8224a04c5bec1
- **题面：** Navigate to the home page.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^One Stop Market$

## df8c914ad7671aa86765
- **题面：** Browse the Clothing, Shoes & Jewelry category to find related products.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## e6d0bbea65f280a05648
- **题面：** Go to your Address Book to manage your addresses.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /customer/address/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Address Book$

## e808e84fe194e8a32e04
- **题面：** Go to My Account page from the shopping cart
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /customer/account/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^My Account$

## eac903852b392451728c
- **题面：** Browse the Grocery & Gourmet Food category.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## f04b05f7a589dac2188f
- **题面：** Navigate to the Cell Phones & Accessories department.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /cell-phones-accessories.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Cell\ Phones\ \&\ Accessories$

## fab2bd5e88ee58c1a5a9
- **题面：** Navigate to the Tools & Home Improvement category to shop for tools, building materials, and home improvement products.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /tools-home-improvement.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Tools\ \&\ Home\ Improvement$

## fbd3d1f67648847518c0
- **题面：** Look at Video Games products.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /video-games.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Video\ Games$

## fc13a90e4e4484e02749
- **题面：** Navigate to the Privacy and Cookie Policy page.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /privacy-policy-cookie-restriction-mode
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Privacy and Cookie Policy$

## 18aa8a7f592bcd5ed85c
- **题面：** View your user profile.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /user/MarvelsGrantMan136
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^MarvelsGrantMan136$

## 1c76ffbf7c2c21dfb1d8
- **题面：** View a specific question post about removing a champagne bottle.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /f/AskReddit/51931
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^What\ is\ the\ best\ way\ to\ remove\ a\ champagne\ bottle\ from\ your\ rectum\?$

## 1efa32d68cab5814d6b0
- **题面：** Sort jokes by a different criterion than "Hot"
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 jokes
  - G2 【排序】按 a different criterion than "Hot" 排序
  - G3 【保存生效】修改已持久保存生效

## 229c0fa130e0890a276a
- **题面：** In the movies forum, filter the post list to one of these time periods: past day, week, month or year. Choose either Top or Most commented, and finish on the filtered list, including a genuine empty historical window.
- **分支：** （源：remaining）
  - G1 【时间过滤】帖子列表时间维度过滤为「过去一天/周/月/年」之一
  - G2 【排序方式】排序方式选择 Top 或 Most commented 之一
  - G3 【保存生效】修改已持久保存生效

## 2325723778d803c9a28f
- **题面：** Visit the movies forum to discuss films and movie news.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /f/movies
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:/f/)?movies$

## 23e15c651b74ab3f272c
- **题面：** View all wiki pages.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /wiki/_all
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^All pages$

## 2465863a805f34100ac8
- **题面：** Navigate to the worldnews forum page.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /f/worldnews
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:/f/)?worldnews$

## 25eaadd47f783419d6db
- **题面：** Visit the AskReddit forum
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /f/AskReddit
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:/f/)?AskReddit$

## 267a20812a9df64221b2
- **题面：** Browse the worldnews forum.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 294d0c402cb756bc019e
- **题面：** View your block list to manage blocked users
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /user/MarvelsGrantMan136/block_list
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Block list$

## 2ccb5b6f3e5e5e80299f
- **题面：** Check out the post "Men of Reddit, when a guy says "i like you because you give me attention" what does that mean?"
- **分支：** （源：remaining）
  - G1 【发布成功】发布成功：目标为 Men of Reddit, when a guy says i like you because you give me attention what does that mean?

## 3427dbd548ef790a48c7
- **题面：** Navigate to page 2 of the forums list sorted by submission count.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /forums/by_submissions/2
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^List of forums$

## 34374d79b45775ea7c2d
- **题面：** Navigate to the Home page of the site.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Postmill$

## 34d4528ba89a556fda89
- **题面：** Access your user account menu.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /user/MarvelsGrantMan136/account
  - G2 【标题/身份匹配】页面标题/目标身份匹配 .+

## 365a48116e402e489892
- **题面：** Sort AskReddit posts by Top over all time to see the highest-rated questions.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 AskReddit posts
  - G2 【排序】按 Top over all time to see the highest-rated questions 排序
  - G3 【保存生效】修改已持久保存生效

## 36f1bfae4c2ef16776ec
- **题面：** Access the moderation log to view recent moderation actions
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /f/movies/moderation_log
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Showing\ moderation\ log\ for\ /f/movies$

## 37a8c5d647ffc910d0b6
- **题面：** Go to the forums section
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /forums
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^List of forums$

## 37ea605874541abbac0b
- **题面：** Navigate to the Moderation log to review moderation activities in the Music forum.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /f/Music/moderation_log
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Showing\ moderation\ log\ for\ /f/Music$

## 38cd077af0b6c6a0fe95
- **题面：** Navigate to the comments section of the post titled "What the pandemic ruined more than we actually realise?"
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /f/AskReddit/95895
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^What\ the\ pandemic\ ruined\ more\ than\ we\ actually\ realise\?$

## 3d1a8bbb6c68a0dbc031
- **题面：** Go to the second page of forums
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /forums/by_submissions/2
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^List of forums$

## 3ec030ff7197a003a1be
- **题面：** Navigate to the All pages section to view all available wiki pages.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /wiki/_all
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^All pages$

## 3fde171a62227f5eaa57
- **题面：** Check your block list
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /user/MarvelsGrantMan136/block_list
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Block list$

## 438304c081cfc0b01dd1
- **题面：** Check the user profile page for MarvelsGrantMan136
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /user/MarvelsGrantMan136
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^MarvelsGrantMan136$

## 43fc1ffb0c7c1f8d193e
- **题面：** Go to the Forums section.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /forums
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^List of forums$

## 44132647e3dd0d0dc8c6
- **题面：** Access your account settings.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /user/MarvelsGrantMan136/account
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Editing user MarvelsGrantMan136$

## 48fd9b47cb15aaeb9d60
- **题面：** View comments on the joke titled "This man went out with the boys, and told his wife that he would be home by midnight."
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /f/Jokes/77340
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^This\ man\ went\ out\ with\ the\ boys,\ and\ told\ his\ wife\ that\ he\ would\ be\ home\ by\ midnight\.$

## 4c27ea6febe7d46c0700
- **题面：** Open the account editing page for your signed-in user, where username and account credentials are managed.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /user/MarvelsGrantMan136/account
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Editing user MarvelsGrantMan136$

## 4d213166261fe210d0fd
- **题面：** Change the view to see forums alphabetically
- **分支：** （源：remaining）
  - G1 【视图】视图 改为 "see forums alphabetically"
  - G2 【保存生效】修改已持久保存生效

## 4fc1cb94fcb774c5ceaa
- **题面：** Navigate to the joke page titled "This man went out with the boys, and told his wife that he would be home by midnight."
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /f/Jokes/77340
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^This\ man\ went\ out\ with\ the\ boys,\ and\ told\ his\ wife\ that\ he\ would\ be\ home\ by\ midnight\.$

## 517a1d5654a0ae5cb747
- **题面：** Go to the technology forum to see discussions about tech topics
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /f/technology
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:/f/)?technology$

## 52e41ee8412e922f2f6b
- **题面：** Check the latest posts in the worldnews forum
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /f/worldnews/new
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^/f/worldnews$

## 5565fd48d8c496835c1a
- **题面：** Read the article "TIFU by forgetting about a zucchini"
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /f/tifu/71164
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^TIFU\ by\ forgetting\ about\ a\ zucchini$

## 55f976462768aa640945
- **题面：** Jump to main content.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /f/Music#main
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Music$

## 568fa749374cebd2611d
- **题面：** Navigate to the Comments page.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /comments
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Recent comments$

## 571b3338b5f17814040a
- **题面：** View all comments on the Brian May knighthood post
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /f/Music/56626
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Brian\ May\ gets\ a\ knighthood\ in\ New\ Year\ Honours\ list$

## 582d7f9e00e571a2cd52
- **题面：** Navigate to the EarthPorn forum.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /f/EarthPorn
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:/f/)?EarthPorn$

## 5859db2a3bef62b69745
- **题面：** Navigate to the Forums section
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /forums
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^List of forums$

## 58768d67f83dd6383ed8
- **题面：** Navigate to the Showerthoughts forum.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /f/Showerthoughts
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:/f/)?Showerthoughts$

## 5aebbf7acf798b777496
- **题面：** Navigate to the MachineLearning forum.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /f/MachineLearning
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:/f/)?MachineLearning$

## 60746e43f4540740e757
- **题面：** Visit the technology forum to see tech news and discussions.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /f/technology
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:/f/)?technology$

## 61a446eea4bdcca926b1
- **题面：** Open the account editing page to view your username and account information.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /user/MarvelsGrantMan136/account
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Editing user MarvelsGrantMan136$

## 635be29045ebfd085a16
- **题面：** Navigate to the wallstreetbets forum.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /f/wallstreetbets
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:/f/)?wallstreetbets$

## 63941a33906094215f2f
- **题面：** View all Wiki pages.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /wiki/_all
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^All pages$

## 64037a6f7b2e11fdbf10
- **题面：** Change the search query from "bleaching your butthole" to "natural skin treatments"
- **分支：** （源：remaining）
  - G1 【搜索词】搜索词 从 "bleaching your butthole" 改为 "natural skin treatments"
  - G2 【保存生效】修改已持久保存生效

## 663c281ca7684f83b2b9
- **题面：** View all forum tags
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /tags
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Tags$

## 67e58447dd39c0dba955
- **题面：** See forums listed alphabetically
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /forums/all
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^All forums$

## 6a1db90c2843f5f608e9
- **题面：** Navigate to the worldnews forum to read global news and discussions.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /f/worldnews
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:/f/)?worldnews$

## 6a8fce928e301e664ece
- **题面：** Read the post titled "I was missing for 10 years"
- **分支：** （源：remaining）
  - G1 【发布成功】发布成功：目标为 titled I was missing for 10 years

## 6b7253e29b40ef4b9d3a
- **题面：** Use the native plain-text search for "Oscar nominations" and display its local results.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /search?q=Oscar+nominations
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Search$

## 6bad9c2ed084fb827789
- **题面：** View all comments on the movies forum
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /f/movies/comments
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:/f/)?movies$

## 6cb18016ab0360491f58
- **题面：** Access your user profile.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /user/MarvelsGrantMan136
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^MarvelsGrantMan136$

## 71cf4f69d20cedfd6162
- **题面：** View the user profile of VampiricBanghole
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /user/VampiricBanghole
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^VampiricBanghole$

## 7228a97deafdccb751d9
- **题面：** View the article "Why bleaching your butthole isn’t called changing your ring tone?"
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /f/AskReddit/10224
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Why\ bleaching\ your\ butthole\ isn’t\ called\ changing\ your\ ring\ tone\?$

## 7251156894b24b1927d0
- **题面：** View all forum tags.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /tags
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Tags$

## 726212b372d61cc5fb45
- **题面：** Browse the list of forums.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 747e72b5bd5c850802bf
- **题面：** Navigate to the relationship_advice forum to browse relationship questions and advice.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /f/relationship_advice
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:/f/)?relationship_advice$

## 78b20e58044c548dfb1c
- **题面：** Access your user preferences
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /user/MarvelsGrantMan136/preferences
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Editing user settings for MarvelsGrantMan136$

## 79774b7e32937adb6009
- **题面：** Navigate to the forums page to see a list of all available forums
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /forums
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^List of forums$

## 7c718f65720b61345821
- **题面：** Visit the user profile of "SashaGreatest"
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /user/SashaGreatest
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^SashaGreatest$

## 7dee7d50a5af953f3ca4
- **题面：** Sort forums by creation date
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 forums
  - G2 【排序】按 creation date 排序
  - G3 【保存生效】修改已持久保存生效

## 80d87f5952bc0afcd641
- **题面：** View all comments in the Music forum.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /f/Music/comments
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:/f/)?Music$

## 81048e1ff52a58ebfe6c
- **题面：** Change the sorting order of jokes from "Hot" to "New"
- **分支：** （源：remaining）
  - G1 【排序方式】排序方式 从 "Hot" 改为 "New"
  - G2 【保存生效】新建/添加已持久保存生效

## 84db70f85f00d339d268
- **题面：** View formatting help for commenting
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /f/MachineLearning/1
  - G2 【标题/身份匹配】页面标题/目标身份匹配 .+

## 854da5fb6c6f024720b1
- **题面：** Look for recent changes to the wiki.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 87241b6e6a073027952b
- **题面：** View a user profile
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /user/MarvelsGrantMan136
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^.+$

## 872d9354e3c5464dd115
- **题面：** Explore the technology forum.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /f/technology
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:/f/)?technology$

## 87afc465b401290077ad
- **题面：** View all forums sorted alphabetically
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /forums/all
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^All forums$

## 87bc67a33e51c266ff63
- **题面：** Visit the personalfinance forum for financial advice.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /f/personalfinance
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:/f/)?personalfinance$

## 8a8ea9f9a610aba36b31
- **题面：** Search for posts about Marvel movies
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 8ae050efc97e8ba86f86
- **题面：** Navigate to the comments section of the article "Who will win the Oscar for FILM EDITING?"
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /f/movies/86029
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Who\ will\ win\ the\ Oscar\ for\ FILM\ EDITING\?$

## 8e8616735c0e5f9a66cf
- **题面：** Visit the profile page of user MarvelsGrantMan136
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /user/MarvelsGrantMan136
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^MarvelsGrantMan136$

## 919d84d23c37d1cbe994
- **题面：** Check notifications
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /notifications
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Notifications$

## 93acfe9f76536523cbdf
- **题面：** Open the technology forum and view its local discussions.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /f/technology
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:/f/)?technology$

## 94e6547d60107e63dc03
- **题面：** Use the native plain-text search for "Spider-Man" and display its local results.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /search?q=Spider-Man
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Search$

## 9741073bcfb958f4c0ee
- **题面：** Navigate to the movies forum page.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /f/movies
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:/f/)?movies$

## 9ad3b254066be9cdd4e6
- **题面：** Go to the Forums page.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /forums
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^List of forums$

## 9c25793cd478774f5b14
- **题面：** Check recent changes in the wiki
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /wiki/_recent
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Recent changes$

## a6c9cf46a6efe0b8d2a6
- **题面：** Navigate to the Forums page from the error page.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /forums
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^List of forums$

## a9383e351917a0c4ace5
- **题面：** Go to page 2 of the forums list.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /forums/by_submissions/2
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^List of forums$

## ab0c1545d48be651904d
- **题面：** View the description of the AskReddit forum.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /forums
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^List of forums$

## ab2cf311d9fe9f0655af
- **题面：** View all pages from the error page.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /wiki/_all
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^All pages$

## ab91b18e370da65a55fe
- **题面：** View recent comments in the AskReddit forum
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /f/AskReddit/comments
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:/f/)?AskReddit$

## b0c68eca144dee37ce50
- **题面：** Check the Trash section.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /user/MarvelsGrantMan136/trash
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Trash$

## b5748005ffb8adb6a8c9
- **题面：** Navigate to the profile of the user "GetFreeCash" who submitted an article.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /user/GetFreeCash
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^GetFreeCash$

## b5c249cae353cad485fd
- **题面：** Navigate to your user profile page.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /user/MarvelsGrantMan136
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^MarvelsGrantMan136$

## b64f7b157f7361e9e8e8
- **题面：** View all Comments.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /comments
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Recent comments$

## b9886828906b22afac66
- **题面：** Jump to sidebar for forum information
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /#sidebar
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Postmill$

## b9ba9fe75dc6012c01f5
- **题面：** Check the top posts of all time in AskReddit
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /f/AskReddit/top?t=all
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^/f/AskReddit$

## bde358526d23b11ee3cd
- **题面：** View forums in alphabetical order.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /forums/all
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:All forums|List of forums)$

## be47263515096d2ee6db
- **题面：** Go to the news forum
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /f/news/?
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^news$

## bfc2093a7ce0d76b6d07
- **题面：** Navigate to the Recent changes section to see the latest edits on the wiki.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /wiki/_recent
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Recent changes$

## bff48edd021335866d51
- **题面：** Switch from URL submission to Image submission
- **分支：** （源：remaining）
  - G1 【from URL submission】from URL submission 改为 "Image submission"
  - G2 【切换】from URL submission 切换为 Image submission
  - G3 【保存生效】修改已持久保存生效

## c15839e0443decac1632
- **题面：** Check the latest posts in the worldnews forum.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /f/worldnews/new
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^/f/worldnews$

## c2dd2fee7f296c44b5c9
- **题面：** Navigate to the comments section for the article "Who will win the Oscar for FILM EDITING?"
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /f/movies/86029
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Who\ will\ win\ the\ Oscar\ for\ FILM\ EDITING\?$

## c307c1eaba7f0c2b58b3
- **题面：** View forums sorted alphabetically
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /forums/all
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^All forums$

## c4dc0bbc56a84198f522
- **题面：** Sort posts in the Music forum by newest first
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 posts in the Music forum
  - G2 【排序】按 newest first 排序
  - G3 【保存生效】修改已持久保存生效

## cb4eb207c4e1da2a2e2e
- **题面：** Sort the forums list by creation date
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 forums list
  - G2 【排序】按 creation date 排序
  - G3 【保存生效】修改已持久保存生效

## cb8117d34fbb8ebb3d96
- **题面：** Open the forum directory and change its default submissions ordering to Name, Title, Creation date or All forums. Finish on the corresponding directory list, rather than changing the sort of posts within a forum.
- **分支：** （源：remaining）
  - G1 【ing】ing 改为 "Name"
  - G2 【保存生效】修改已持久保存生效

## cc241dc8a47af71af83a
- **题面：** Open the complete alphabetical forum directory titled "All forums" so the available forums can be browsed.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /forums/all
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^All forums$

## cc4a002f4e870c92c341
- **题面：** Sort posts by different criteria
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 posts
  - G2 【排序】按 different criteria 排序
  - G3 【保存生效】修改已持久保存生效

## d204f38cbc8c514a48ef
- **题面：** Browse the relationship_advice forum
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## d60d57e683333045b0d2
- **题面：** Go to the books forum page to view its content.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /f/books
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:/f/)?books$

## dba7630218411d96d923
- **题面：** Go to the page for creating a new wiki entry
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /wiki/_create
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Create new page$

## decb4f3ad708d61b9e88
- **题面：** Check the Notifications page from the error page.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /notifications
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Notifications$

## df8b6938ec993aad2b4f
- **题面：** Navigate to the Jokes forum page.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /f/Jokes
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:/f/)?Jokes$

## e114e9967b1812b20a56
- **题面：** Visit the dataisbeautiful forum.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /f/dataisbeautiful
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:/f/)?dataisbeautiful$

## e2aa1fcf5dbc7d712c76
- **题面：** View all your notifications
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /notifications
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Notifications$

## e630b31845ff31f4fab9
- **题面：** Go to the Home page from the error page.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Featured forums$

## e9f516133a7da97e16df
- **题面：** Change the sorting of posts from Hot to another available option
- **分支：** （源：remaining）
  - G1 【排序】排序 从 "Hot" 改为 "another available option"
  - G2 【保存生效】修改已持久保存生效

## ebfacfc47eb95c7db026
- **题面：** Change the search query to find posts about "favorite love songs"
- **分支：** （源：remaining）
  - G1 【变更字段】变更 search query
  - G2 【保存生效】修改已持久保存生效

## ec82c9b5b6195e35f503
- **题面：** View a list of all Wiki pages.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /wiki/_all
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^All pages$

## ed6e2e7f6c0f54f3943c
- **题面：** Use the native plain-text search for "movie release news" and display its local results. This is a literal search; no external release calendar is required.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /search?q=movie+release+news
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Search$

## f2d589c72d6aa6765894
- **题面：** Check recent changes in the wiki.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /wiki/_recent
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Recent changes$

## f54cbdef6b0a6dd7887c
- **题面：** Go to the user profile page
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /user/MarvelsGrantMan136
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^MarvelsGrantMan136$

## f5c28378088f474db906
- **题面：** Visit the relationship_advice forum.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /f/relationship_advice
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:/f/)?relationship_advice$

## 1c254208ceb069ce36a4
- **题面：** Navigate to the Content section in the Magento Admin panel.
- **分支：** admin-menu-navigation-v1（源：remaining）
  - G1 【到达菜单】到达菜单 Content

## 1ec879497cc27da8c7ad
- **题面：** Navigate to the System section to manage system settings and tools.
- **分支：** admin-menu-navigation-v1（源：remaining）
  - G1 【到达菜单】到达菜单 System

## 278d330bef113a98383a
- **题面：** Navigate to the Reports section in the Magento Admin panel.
- **分支：** admin-menu-navigation-v1（源：remaining）
  - G1 【到达菜单】到达菜单 Reports

## 2982fb2a0ac2960982f9
- **题面：** Access the Content management area.
- **分支：** admin-menu-navigation-v1（源：remaining）
  - G1 【到达菜单】到达菜单 Content

## 2b2abba6597e0b3fb046
- **题面：** Navigate to the Reports section to view sales, product, customer, and other performance reports.
- **分支：** admin-menu-navigation-v1（源：remaining）
  - G1 【到达菜单】到达菜单 Reports

## 2de1fbd22b0c73adefca
- **题面：** Explore the REPORTS section to generate sales reports.
- **分支：** admin-menu-navigation-v1（源：remaining）
  - G1 【到达菜单】到达菜单 Reports

## 3f244c7033ccb11e109c
- **题面：** Navigate to the SALES section to view and manage orders.
- **分支：** admin-menu-navigation-v1（源：remaining）
  - G1 【到达菜单】到达菜单 Sales

## 42496b0648b483bf9292
- **题面：** Visit the CUSTOMERS section to manage customer accounts.
- **分支：** admin-menu-navigation-v1（源：remaining）
  - G1 【到达菜单】到达菜单 Customers

## 430cb13cd5f4a56a9f51
- **题面：** Navigate to the System section to manage user accounts, permissions, tools, and other system configurations.
- **分支：** admin-menu-navigation-v1（源：remaining）
  - G1 【到达菜单】到达菜单 System

## 4856cb4b53f010aae886
- **题面：** Go to the Content section to manage pages, blocks, and design elements.
- **分支：** admin-menu-navigation-v1（源：remaining）
  - G1 【到达菜单】到达菜单 Content

## 6b4524780a0110ab076a
- **题面：** Access the Marketing section to set up a new promotion.
- **分支：** admin-menu-navigation-v1（源：remaining）
  - G1 【到达菜单】到达菜单 Marketing

## 6cd44e2cee53ff6a43b6
- **题面：** Navigate to the SALES section to explore sales-related options and tasks.
- **分支：** admin-menu-navigation-v1（源：remaining）
  - G1 【到达菜单】到达菜单 Sales

## 6fce1855d4eec8c536a8
- **题面：** Access the Marketing section.
- **分支：** admin-menu-navigation-v1（源：remaining）
  - G1 【到达菜单】到达菜单 Marketing

## 700b6e3f667ebde8c550
- **题面：** Navigate to the Marketing section from the Products catalog
- **分支：** admin-menu-navigation-v1（源：remaining）
  - G1 【到达菜单】到达菜单 Marketing

## 70496ff42a425184ffc7
- **题面：** Go to the Content section to manage website content.
- **分支：** admin-menu-navigation-v1（源：remaining）
  - G1 【到达菜单】到达菜单 Content

## 73a5c14e7701fc356e91
- **题面：** Navigate to the Marketing section to manage promotions, email campaigns, and SEO tools.
- **分支：** admin-menu-navigation-v1（源：remaining）
  - G1 【到达菜单】到达菜单 Marketing

## 74f8b920114259b94896
- **题面：** Navigate to the Sales section in the Magento admin panel.
- **分支：** admin-menu-navigation-v1（源：remaining）
  - G1 【到达菜单】到达菜单 Sales

## 76a979f1a1b11ac0cf06
- **题面：** Navigate to the Content section to manage pages, blocks, widgets, and design configuration.
- **分支：** admin-menu-navigation-v1（源：remaining）
  - G1 【到达菜单】到达菜单 Content

## 7b7ab8a5769301a8f1a7
- **题面：** Navigate to the CATALOG section in the main menu
- **分支：** admin-menu-navigation-v1（源：remaining）
  - G1 【到达菜单】到达菜单 Catalog

## 7bbe2f6b835917324ef4
- **题面：** Navigate to the Customers section in the Magento admin panel.
- **分支：** admin-menu-navigation-v1（源：remaining）
  - G1 【到达菜单】到达菜单 Customers

## 7e8844763b3172fdcd46
- **题面：** Navigate to the Marketing section in Magento Admin.
- **分支：** admin-menu-navigation-v1（源：remaining）
  - G1 【到达菜单】到达菜单 Marketing

## 80f5bc182419b35e92c1
- **题面：** Navigate to the Content section.
- **分支：** admin-menu-navigation-v1（源：remaining）
  - G1 【到达菜单】到达菜单 Content

## 88ec47730a5c5200355a
- **题面：** Go to the SALES section to manage orders and transactions.
- **分支：** admin-menu-navigation-v1（源：remaining）
  - G1 【到达菜单】到达菜单 Sales

## 89e677cd62cf857d5e54
- **题面：** Navigate to the CONTENT section of the admin panel.
- **分支：** admin-menu-navigation-v1（源：remaining）
  - G1 【到达菜单】到达菜单 Content

## 8a6c28d43495a98f9186
- **题面：** Navigate to the Reports section to view sales, product, customer, and marketing analytics.
- **分支：** admin-menu-navigation-v1（源：remaining）
  - G1 【到达菜单】到达菜单 Reports

## 957470b89867c0f2729d
- **题面：** Navigate to the Customers section from the credit memo view
- **分支：** admin-menu-navigation-v1（源：remaining）
  - G1 【到达菜单】到达菜单 Customers

## 9800563dd15191ee6e97
- **题面：** Navigate to the Marketing section in the Magento Admin panel.
- **分支：** admin-menu-navigation-v1（源：remaining）
  - G1 【到达菜单】到达菜单 Marketing

## 9940847a6c20de0bb589
- **题面：** Go to the Customers section to manage customer accounts.
- **分支：** admin-menu-navigation-v1（源：remaining）
  - G1 【到达菜单】到达菜单 Customers

## a802d8cb23d923690f3a
- **题面：** Navigate to the Customers section.
- **分支：** admin-menu-navigation-v1（源：remaining）
  - G1 【到达菜单】到达菜单 Customers

## a9efe95583c776e41db9
- **题面：** Navigate to the Content section to manage website pages and design.
- **分支：** admin-menu-navigation-v1（源：remaining）
  - G1 【到达菜单】到达菜单 Content

## aa9e34f0cf53554f71fe
- **题面：** Navigate to the Stores section from the credit memo view page.
- **分支：** admin-menu-navigation-v1（源：remaining）
  - G1 【到达菜单】到达菜单 Stores

## abbc5a0a7b7b0cf5ac9d
- **题面：** Navigate to the Catalog section in Magento Admin.
- **分支：** admin-menu-navigation-v1（源：remaining）
  - G1 【到达菜单】到达菜单 Catalog

## b1889681ff140f6a7cea
- **题面：** Navigate to the Content section from the Credit Memos page
- **分支：** admin-menu-navigation-v1（源：remaining）
  - G1 【到达菜单】到达菜单 Content

## b2f3b7bf1708c9745fc6
- **题面：** Navigate to the Reports section to view sales, products, customers, and other store statistics.
- **分支：** admin-menu-navigation-v1（源：remaining）
  - G1 【到达菜单】到达菜单 Reports

## b8e38d943e9cead2d746
- **题面：** Navigate to the System section to manage system settings, tools, and integrations.
- **分支：** admin-menu-navigation-v1（源：remaining）
  - G1 【到达菜单】到达菜单 System

## bb12df55c673624a6bbb
- **题面：** Navigate to the Customers section to view and manage customer accounts and groups.
- **分支：** admin-menu-navigation-v1（源：remaining）
  - G1 【到达菜单】到达菜单 Customers

## c922aebe8cd65499eb36
- **题面：** Navigate to the Content section to manage pages, blocks and design elements.
- **分支：** admin-menu-navigation-v1（源：remaining）
  - G1 【到达菜单】到达菜单 Content

## d763c6df926460ccdeff
- **题面：** Navigate to the Catalog section to manage products.
- **分支：** admin-menu-navigation-v1（源：remaining）
  - G1 【到达菜单】到达菜单 Catalog

## dab9c5cc8cadf40fc49c
- **题面：** Navigate to the Stores section to manage store settings, configuration, taxes, and attributes.
- **分支：** admin-menu-navigation-v1（源：remaining）
  - G1 【到达菜单】到达菜单 Stores

## dc49946387e69036956b
- **题面：** Navigate to the Catalog section to manage products, categories, and inventory.
- **分支：** admin-menu-navigation-v1（源：remaining）
  - G1 【到达菜单】到达菜单 Catalog

## dd60eda0900f680794fa
- **题面：** Navigate to the System section
- **分支：** admin-menu-navigation-v1（源：remaining）
  - G1 【到达菜单】到达菜单 System

## df927f0b0fdd00135371
- **题面：** Navigate to the Marketing section to manage promotions, email campaigns, and SEO settings.
- **分支：** admin-menu-navigation-v1（源：remaining）
  - G1 【到达菜单】到达菜单 Marketing

## e2abade92f0afefd5feb
- **题面：** Go to the Sales section from the customer management page
- **分支：** admin-menu-navigation-v1（源：remaining）
  - G1 【到达菜单】到达菜单 Sales

## f08cb855551c230d93b1
- **题面：** Navigate to the CATALOG section in the Magento Admin.
- **分支：** admin-menu-navigation-v1（源：remaining）
  - G1 【到达菜单】到达菜单 Catalog

## f1745bc4d7f3a8da7dfe
- **题面：** Navigate to the System section to manage configurations, tools, and technical settings.
- **分支：** admin-menu-navigation-v1（源：remaining）
  - G1 【到达菜单】到达菜单 System

## f1b7c517063556614eb2
- **题面：** Navigate to the Sales section of the admin panel.
- **分支：** admin-menu-navigation-v1（源：remaining）
  - G1 【到达菜单】到达菜单 Sales

## 26317ba82b6b5d0e5eff
- **题面：** View the user profile of Dirty_Quesadilla
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /user/Dirty_Quesadilla/?
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Dirty_Quesadilla$

## 6d7cc867b7b35c4e0636
- **题面：** Open the gaming forum and leave its post listing displayed.
- **分支：** （源：remaining）
  - G1 【退出成功】退出成功：目标为 listing displayed

## 3fdb12ef66fc0ca43df1
- **题面：** Find and visit the Contact Us page.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 61045be2bcc1dd3f5cc8
- **题面：** Check the reviews for the gingerbread house kit.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /pre-baked-gingerbread-house-kit-value-pack-17-oz-pack-of-2-total-34-oz.html
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Pre\-baked\ Gingerbread\ House\ Kit\ Value\ Pack,\ 17\ oz\.,\ Pack\ of\ 2,\ Total\ 34\ oz\.$

## 63fb082124e3da14006c
- **题面：** Navigate to the My Cart page.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /checkout/cart/
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Shopping Cart$

## 1a8685ffac6b4a9bb495
- **题面：** View all issues assigned to your account regardless of status.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /dashboard/issues?state=all&assignee_username=byteblaze
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Issues$

## 1fe4ac6f4f34718009db
- **题面：** View open merge requests assigned to your account.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /dashboard/merge_requests?state=opened&assignee_username=byteblaze
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Merge requests$

## 2cd83864ac81db870307
- **题面：** View open issues assigned to your account.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /dashboard/issues?state=opened&assignee_username=byteblaze
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Issues$

## 2f8a3eb0684cdfc17a98
- **题面：** View closed issues assigned to your account.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /dashboard/issues?state=closed&assignee_username=byteblaze
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Issues$

## 3bd859d8c49a0df60fd2
- **题面：** View open issues assigned to your account.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /dashboard/issues?state=opened&assignee_username=byteblaze
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Issues$

## 4242f902d5b3062ca219
- **题面：** View open issues for byteblaze/a11y-syntax-highlighting.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/a11y-syntax-highlighting/-/issues?state=opened
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Issues · .+ / a11y\-syntax\-highlighting · GitLab$

## 4faad258a26eff9bff53
- **题面：** View open merge requests for byteblaze/a11y-syntax-highlighting.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/a11y-syntax-highlighting/-/merge_requests?state=opened
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Merge requests · .+ / a11y\-syntax\-highlighting · GitLab$

## 551c35907022fc515a15
- **题面：** View open merge requests for bblanchon/ArduinoJson.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /bblanchon/ArduinoJson/-/merge_requests?state=opened
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Merge requests · .+ / ArduinoJson · GitLab$

## 56cd92bd5452d6e323fe
- **题面：** View open merge requests for byteblaze/a11y-syntax-highlighting.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/a11y-syntax-highlighting/-/merge_requests?state=opened
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Merge requests · .+ / a11y\-syntax\-highlighting · GitLab$

## 65e12e498849f332da2e
- **题面：** View open merge requests assigned to your account.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /dashboard/merge_requests?state=opened&assignee_username=byteblaze
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Merge requests$

## 7c3eaa2994d0002f978a
- **题面：** Read the README.md file in byteblaze/a11y-syntax-highlighting.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/a11y-syntax-highlighting/-/blob/main/README.md
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:README\.md\ ·\ main\ ·\ Byte\ Blaze\ /\ a11y\-syntax\-highlighting\ ·\ GitLab|Byte\ Blaze\ /\ a11y\-syntax\-highlighting\ ·\ GitLab|Files\ ·\ main\ ·\ Byte\ Blaze\ /\ a11y\-syntax\-highlighting\ ·\ GitLab)$

## 80c6bba38a281712c2d3
- **题面：** View open issues for byteblaze/a11y-syntax-highlighting.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/a11y-syntax-highlighting/-/issues?state=opened
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Issues · .+ / a11y\-syntax\-highlighting · GitLab$

## aba1b3d49d6ea9841005
- **题面：** View open issues for byteblaze/millennials-to-snake-people.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/millennials-to-snake-people/-/issues?state=opened
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Issues · .+ / millennials\-to\-snake\-people · GitLab$

## bca5783e4849e9696b42
- **题面：** View the repository files of a11yproject/a11yproject.com.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /a11yproject/a11yproject.com/-/tree/main
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:Files\ ·\ main\ ·\ The\ A11Y\ Project\ /\ a11yproject\.com\ ·\ GitLab|The\ A11Y\ Project\ /\ a11yproject\.com\ ·\ GitLab)$

## cdf19e75d607ef4b5200
- **题面：** View open merge requests assigned to your account.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /dashboard/merge_requests?state=opened&assignee_username=byteblaze
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Merge requests$

## dfc521eb1fcc7e152b2f
- **题面：** View open issues assigned to your account.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /dashboard/issues?state=opened&assignee_username=byteblaze
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Issues$

## e1ef2095d68edbd1a702
- **题面：** View the repository files of a11yproject/a11yproject.com.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /a11yproject/a11yproject.com/-/tree/main
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:Files\ ·\ main\ ·\ The\ A11Y\ Project\ /\ a11yproject\.com\ ·\ GitLab|The\ A11Y\ Project\ /\ a11yproject\.com\ ·\ GitLab)$

## f17ae0c5a086652ecb5b
- **题面：** View closed issues assigned to your account.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /dashboard/issues?state=closed&assignee_username=byteblaze
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Issues$

## 2117cabad5712d8d165c
- **题面：** Open the local About OpenStreetMap page to display the site's introduction. An external website or written explanation is not required.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /about
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^OpenStreetMap\ provides\ map\ data\ for\ thousands\ of\ websites,\ mobile\ apps,\ and\ hardware\ devices$

## 227f0ce76530eca31eeb
- **题面：** Navigate to the local Communities page and display its local chapter and group directory. Contacting a group outside this website is outside this local task.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /communities
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Communities$

## 7442ae72bc2576957ca4
- **题面：** Open the local OpenStreetMap Help page to view the available help options. External help websites are outside this local task.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /help
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Getting\ Help$

## a2beeffbafa9f81ac969
- **题面：** Sort posts in the movies forum by Top over all time to see the highest-rated content.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 posts in the movies forum
  - G2 【排序】按 Top over all time to see the highest-rated content 排序
  - G3 【保存生效】修改已持久保存生效

## 00ec483c04c854f0376a
- **题面：** Create a GitLab group for learning Git basics with Private visibility.
- **分支：** （源：remaining）
  - G1 【可见性】可见性为 Private
  - G2 【保存生效】新建/添加已持久保存生效

## 08401838cbeaadbb22b0
- **题面：** View the logo of the cloud-to-butt Chrome extension
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/cloud-to-butt/-/blob/master/logo.png

## b45c2140f3e8557e1708
- **题面：** Create a new top-level group with the name "My Project Team".
- **分支：** （源：remaining）
  - G1 【名称】名称为 "My Project Team"
  - G2 【层级】群组层级为 top-level
  - G3 【保存生效】新建/添加已持久保存生效

## e4d658cfba6588f6a386
- **题面：** Create a new private GitLab group named "Development Team" for company use
- **分支：** （源：remaining）
  - G1 【名称】名称为 "Development Team"
  - G2 【可见性】可见性为 Private
  - G3 【保存生效】新建/添加已持久保存生效

## f205b50137926a04a0e3
- **题面：** Create a new group for organizing related projects.
- **分支：** （源：remaining）
  - G1 【目标对象】新建/添加的对象与题面要求一致
  - G2 【保存生效】新建/添加已持久保存生效

## 4459816dc17d846f297d
- **题面：** Navigate to the Customers tab in the dashboard.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【到达标签页】到达 dashboard 标签页 Customers

## 5e4a6434b08e48fe572c
- **题面：** Navigate to the Most Viewed Products tab to see which products are getting the most attention from customers.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【到达标签页】到达 dashboard 标签页 Most Viewed Products

## 69eef476c51ec81fd201
- **题面：** Navigate to the New Customers tab to view recently registered customers.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【到达标签页】到达 dashboard 标签页 New Customers

## 782e2873352ae8bddf8c
- **题面：** Configure the customer grid to display only Name, Email and Phone columns
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【列配置】网格列配置为 Name, Email, Phone
  - G2 【网格操作】网格执行操作 columns

## a9d35deaf9c4dd97dd4c
- **题面：** Change the number of customer groups displayed per page
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【网格操作】网格执行操作 page_size

## ac5ad85b4fd490181515
- **题面：** Change the number of shipments displayed per page to 50.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【网格操作】网格执行操作 page_size

## bd21a893f65fa01c2b0b
- **题面：** Customize the customer table to show only Name, Email, and Phone columns
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【列配置】网格列配置为 Name, Email, Phone
  - G2 【网格操作】网格执行操作 columns

## ee47d8e33c516fe98079
- **题面：** Remove existing images from the Blue T-Shirt product.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【目标对象】目标对象身份为 name=Blue T-Shirt
  - G2 【媒体操作】执行媒体操作 移除全部图片 且文件系统状态精确

## f39cb84616b8fd2ef4bb
- **题面：** Configure which columns are displayed in the shipments grid.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【网格操作】网格执行操作 changed_columns

## 11f2436395f683033acc
- **题面：** Read recent user diary entries about mapping activities.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /diary
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:Users'\ Diaries|LocalBenchmarkMapper's\ Diary)$

## 34198da8a76861167d82
- **题面：** Go to the Edit page to modify maps
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /edit
  - G2 【标题/身份匹配】页面标题/目标身份匹配 OpenStreetMap

## 3cc71bbbd62246248704
- **题面：** Navigate to the map editing page
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /edit
  - G2 【标题/身份匹配】页面标题/目标身份匹配 OpenStreetMap

## 4612d0321fa9e902766c
- **题面：** Browse all GPS traces uploaded by users.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 4f42e80436442c244537
- **题面：** Navigate to the Edit page to edit maps
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /edit
  - G2 【标题/身份匹配】页面标题/目标身份匹配 OpenStreetMap

## 5227fea2f6abda87e166
- **题面：** Navigate to the map editor to make changes to OpenStreetMap data.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /edit
  - G2 【标题/身份匹配】页面标题/目标身份匹配 OpenStreetMap

## 63a7f2bf7049157f2f94
- **题面：** Read user diaries to see what other mappers are doing
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /diary
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:Users'\ Diaries|LocalBenchmarkMapper's\ Diary)$

## 68b524062bce0bc76c3f
- **题面：** Browse GPS traces uploaded by OpenStreetMap users.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 8716fc0afccd0b53b932
- **题面：** View GPS traces from the diary page
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /traces
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:Public\ GPS\ Traces|Public\ GPS\ Traces\ from\ LocalBenchmarkMapper|Viewing\ Trace\ local\-fixture\-park\-walk\.gpx|Viewing\ Trace\ local\-fixture\-riverside\-walk\.gpx)$

## 97283c44de5672db8b98
- **题面：** Read User Diaries
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /diary
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:Users'\ Diaries|LocalBenchmarkMapper's\ Diary)$

## 9aa2dbd9daedc8943d3f
- **题面：** Go to the map editor
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /edit
  - G2 【标题/身份匹配】页面标题/目标身份匹配 OpenStreetMap

## a908db27f917f2eb8dae
- **题面：** Browse recent GPS trace uploads on OpenStreetMap.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## ab9220bd45634adb80b1
- **题面：** Navigate to the map editing page to edit OpenStreetMap data.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /edit
  - G2 【标题/身份匹配】页面标题/目标身份匹配 OpenStreetMap

## c685e6e37928e5548042
- **题面：** Navigate to the Edit page to modify the map
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /edit
  - G2 【标题/身份匹配】页面标题/目标身份匹配 OpenStreetMap

## e9faf1ded038f9e09624
- **题面：** Navigate to the Edit page to make changes to the map.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /edit
  - G2 【标题/身份匹配】页面标题/目标身份匹配 OpenStreetMap

## edd5d9dd9dbc3af39d3a
- **题面：** View GPS traces uploaded by other users.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /traces
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:Public\ GPS\ Traces|Public\ GPS\ Traces\ from\ LocalBenchmarkMapper|Viewing\ Trace\ local\-fixture\-park\-walk\.gpx|Viewing\ Trace\ local\-fixture\-riverside\-walk\.gpx)$

## 3192d587774b062a52dc
- **题面：** Browse GPS Traces uploaded by users.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 35896510424da46e6fbc
- **题面：** Add a comment to the credit memo for order #000000002 saying "Reviewed and approved for refund."
- **分支：** admin-single-pass-rules-v3（源：remaining）
  - G1 【评论文本】添加评论文本精确
  - G2 【保存生效】评论保存且加到正确对象

## 47c36ebf4069de79d6d3
- **题面：** View cross-sell products for the Blue T-Shirt
- **分支：** admin-single-pass-rules-v3（源：remaining）
  - G1 【到达目标路径】到达目标路径 None

## 589ffd7db76177dbaeaa
- **题面：** Change the tax class of the Blue T-Shirt to "None".
- **分支：** admin-single-pass-rules-v3（源：remaining）
  - G1 【目标对象】操作对象为题面指定目标
  - G2 【目标值】字段更新为精确值、scope 正确
  - G3 【保存生效】保存生效且未动无关字段

## 83bdf10dfe02ee8aa9fc
- **题面：** Update the price of the Blue T-Shirt to $29.99
- **分支：** admin-single-pass-rules-v3（源：remaining）
  - G1 【目标对象】操作对象为题面指定目标
  - G2 【目标值】字段更新为精确值、scope 正确
  - G3 【保存生效】保存生效且未动无关字段

## 8db58162c0790f718086
- **题面：** Navigate to the Product Reviews section for the Blue T-Shirt
- **分支：** admin-single-pass-rules-v3（源：remaining）
  - G1 【到达目标路径】到达目标路径 None

## b27df1521a689351b66b
- **题面：** Navigate to the Content section of the Blue T-Shirt product page.
- **分支：** admin-single-pass-rules-v3（源：remaining）
  - G1 【到达目标路径】到达目标路径 None

## f7f15b9942542a827638
- **题面：** Change the visibility setting of the Blue T-Shirt to "Catalog, Search"
- **分支：** admin-single-pass-rules-v3（源：remaining）
  - G1 【目标对象】操作对象为题面指定目标
  - G2 【目标值】字段更新为精确值、scope 正确
  - G3 【保存生效】保存生效且未动无关字段

## fca8f1b4c4898b3b525e
- **题面：** For this explicitly fictional training product, set the default-store Short Description of Example Product Deluxe 2023 to exactly the text inside the quotation marks (excluding the quotation marks): "Example Product Deluxe 2023 features a modular design, replaceable inserts, and a reusable case.". These supplied training facts describe a modular design, replaceable inserts and a reusable case. Save the change; leave the global-scope value and other products unchanged.
- **分支：** admin-single-pass-rules-v3（源：remaining）
  - G1 【目标对象】操作对象为题面指定目标
  - G2 【目标值】字段更新为精确值、scope 正确
  - G3 【保存生效】保存生效且未动无关字段

## 435c08cec0b551548a13
- **题面：** View users' diary entries
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /diary
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:Users'\ Diaries|LocalBenchmarkMapper's\ Diary)$

## 4ebf447289b9540df0d4
- **题面：** Return to the OpenStreetMap homepage
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /
  - G2 【标题/身份匹配】页面标题/目标身份匹配 OpenStreetMap

## 858adfb6509ecfcad97c
- **题面：** View user diaries to see updates from OpenStreetMap contributors
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /diary
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:Users'\ Diaries|LocalBenchmarkMapper's\ Diary)$

## a77217d6ceb675bb6c70
- **题面：** Navigate to the Export page for New York on OpenStreetMap.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /export
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Export$

## c95ed5254a0a0eeefa95
- **题面：** Read user diaries to see updates from the OpenStreetMap community.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /diary
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:Users'\ Diaries|LocalBenchmarkMapper's\ Diary)$

## dd0f2a5f22a031eeec2f
- **题面：** Read user diaries and experiences
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /diary
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:Users'\ Diaries|LocalBenchmarkMapper's\ Diary)$

## df44572915db95c5c12d
- **题面：** Read user diaries to see what the OpenStreetMap community is working on.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /diary
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:Users'\ Diaries|LocalBenchmarkMapper's\ Diary)$

## f9780c4ca4e7d831ff2f
- **题面：** Read User Diaries to see updates from the community.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /diary
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^(?:Users'\ Diaries|LocalBenchmarkMapper's\ Diary)$

## 6e6fdd278bd1fc7cc64f
- **题面：** View the OpenStreetMap edit page for this area
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /edit
  - G2 【标题/身份匹配】页面标题/目标身份匹配 OpenStreetMap

## f979459d965f2dab7ae4
- **题面：** Hide the Tax VAT Number column from the customer list
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【网格操作】网格执行操作 hide_column

## 01a559cd990c18bf2da1
- **题面：** Open a new submission form, enter title "Climate Change Discussion", and leave the draft unsubmitted.
- **分支：** （源：remaining）
  - G1 【标题】标题精确为 "Climate Change Discussion"
  - G2 【保存生效】新建/添加已持久保存生效

## 6636a5a379889d6b2497
- **题面：** Create a text submission in Music titled "A Song for a Calm Mood" with this exact Markdown body: "# A calm mood\n\nClair de Lune matches a calm mood through its gentle melody.\n\n- Listen to the gentle melody.\n- Notice its quiet pace.".
- **分支：** （源：remaining）
  - G1 【标题】标题精确为 "A Song for a Calm Mood"
  - G2 【正文】正文内容与题面给定文本精确一致
  - G3 【保存生效】新建/添加已持久保存生效

## 9f235f94cab42da3a2be
- **题面：** Publish one text submission in AskReddit with title "Local reference link" and exact body "Reference: https://example.com/gobrowse-training-link.". Store the body as text; no external page needs to be visited.
- **分支：** （源：remaining）
  - G1 【发布成功】发布成功：目标为 one text submission in AskReddit with title Local reference link and exact body Reference: https://example

## 01ccdfd9a75d86f713e4
- **题面：** Register a new OpenStreetMap account using the supplied local account details and confirm its registration email through the local account inbox. Completion requires the saved account to be confirmed. You do not need to open the map editor, edit the map, stay on the settings page, or remain signed in after confirmation.
- **分支：** （源：remaining）
  - G1 【目标对象】新建/添加的对象与题面要求一致
  - G2 【保存生效】新建/添加已持久保存生效

## 026ef2b9fa525aab41f2
- **题面：** Create and save a wiki page at /wiki/community-guidelines with title "Community Guidelines" and exactly this body:
- **分支：** （源：remaining）
  - G1 【路径】wiki 页面路径为 /wiki/community-guidelines
  - G2 【标题】标题精确为 "Community Guidelines"
  - G3 【正文】正文内容与题面给定文本精确一致
  - G4 【保存生效】新建/添加已持久保存生效

## 0433964c9203167f5ebf
- **题面：** Create the first wiki page for the site.
- **分支：** （源：remaining）
  - G1 【目标对象】新建/添加的对象与题面要求一致
  - G2 【保存生效】新建/添加已持久保存生效

## 091343042650fd73cdd3
- **题面：** Navigate to the My Cart page to view items and proceed to checkout.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Navigate to the My Cart page to view items and proceed to checkout.

## 0b743864dcdc445b9ddd
- **题面：** Switch the appearance to Night mode for user MarvelsGrantMan136.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 MarvelsGrantMan
  - G2 【外观】外观 改为 "Night mode"
  - G3 【切换】appearance 切换为 Night mode
  - G4 【保存生效】修改已持久保存生效

## 0cf253b647120de74989
- **题面：** Add the Pre-baked Gingerbread House Kit Value Pack to the wish list.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 Pre-baked Gingerbread House Kit Value Pack
  - G2 【目标位置】添加到 wish list
  - G3 【保存生效】新建/添加已持久保存生效

## 0eccb86b39a3f3c0dea5
- **题面：** Create and save a wiki page at /wiki/site-rules with title "Site Rules" and exactly this body:
- **分支：** （源：remaining）
  - G1 【路径】wiki 页面路径为 /wiki/site-rules
  - G2 【标题】标题精确为 "Site Rules"
  - G3 【正文】正文内容与题面给定文本精确一致
  - G4 【保存生效】新建/添加已持久保存生效

## 0f21c2d37f4c835f130f
- **题面：** Subscribe to the todayilearned forum.
- **分支：** （源：remaining）
  - G1 【订阅成功】订阅成功：目标为 todayilearned forum

## 10fc370df7e434132b2c
- **题面：** Restore the completed issue " HOWTO: Use JAWS on Windows" back to your active to-do list.
- **分支：** （源：remaining）
  - G1 【恢复成功】恢复成功：目标为 completed issue  HOWTO: Use JAWS on Windows back to your active to-do list

## 119e9fd80bd55d6a9275
- **题面：** Subscribe to the Jokes forum.
- **分支：** （源：remaining）
  - G1 【订阅成功】订阅成功：目标为 Jokes forum

## 13b8dda718ca62d1e6fb
- **题面：** Change the country to "Canada" for Emma Lopez.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 Emma Lopez
  - G2 【国家】国家 改为 "Canada"
  - G3 【保存生效】修改已持久保存生效

## 1674381bc90e3f534f87
- **题面：** Create a new wiki page with Markdown formatting for headers and bullet points
- **分支：** （源：remaining）
  - G1 【目标对象】新建/添加的对象与题面要求一致
  - G2 【保存生效】新建/添加已持久保存生效

## 17feccb82d71bee15380
- **题面：** Add Elmwood Inn Fine Teas, Orange Vanilla Caffeine-free Fruit Infusion to the comparison list.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 Elmwood Inn Fine Teas, Orange Vanilla Caffeine-free Fruit Infusion
  - G2 【目标位置】添加到 comparison list
  - G3 【保存生效】新建/添加已持久保存生效

## 190bd3c39249dd37a319
- **题面：** Update your user preferences or settings.
- **分支：** （源：remaining）
  - G1 【保存生效】修改已持久保存生效

## 19e031486c432de56501
- **题面：** Sign out of your account.
- **分支：** （源：remaining）
  - G1 【登出成功】登出成功：目标为 your account

## 1a1d015547f282c56b8e
- **题面：** Complete the purchase of all items currently in your shopping cart, creating one order.
- **分支：** （源：remaining）
  - G1 【下单】完成下单，创建订单
  - G2 【保存生效】写操作已持久保存生效

## 1b9ffd0865fdb216db57
- **题面：** Upvote the joke titled "My girlfriend left me because of my abandonment issues..."
- **分支：** （源：remaining）
  - G1 【点赞成功】点赞成功：目标为 joke titled My girlfriend left me because of my abandonment issues

## 236ce3f9719eed4df2c8
- **题面：** Create and save a wiki page at /wiki/index with title "Welcome" and exactly this body:
- **分支：** （源：remaining）
  - G1 【路径】wiki 页面路径为 /wiki/index
  - G2 【标题】标题精确为 "Welcome"
  - G3 【正文】正文内容与题面给定文本精确一致
  - G4 【保存生效】新建/添加已持久保存生效

## 24503cdddab9b77f3167
- **题面：** Subscribe to the movies forum
- **分支：** （源：remaining）
  - G1 【订阅成功】订阅成功：目标为 movies forum

## 25700998219b40e38012
- **题面：** Subscribe to the Music forum.
- **分支：** （源：remaining）
  - G1 【订阅成功】订阅成功：目标为 Music forum

## 25ce728b54b1643129d8
- **题面：** Navigate to your shopping cart to view items and proceed to checkout.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Navigate to your shopping cart to view items and proceed to checkout.

## 260fd4d0719cd3fdcabb
- **题面：** Set and save the front page default filter to Featured in the preferences for user MarvelsGrantMan136. The preference should remain Featured after reloading.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 MarvelsGrantMan
  - G2 【and save the front page default filter】and save the front page default filter 改为 "Featured"
  - G3 【保存生效】修改已持久保存生效

## 26f830ef7023dc9cebad
- **题面：** Add the Nightfox Vulpes Handheld Digital Night Vision Goggles to your compare list
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 Nightfox Vulpes Handheld Digital Night Vision Goggles
  - G2 【目标位置】添加到 compare list
  - G3 【保存生效】新建/添加已持久保存生效

## 287768be346fa3b9b264
- **题面：** Add the Uttermost Volterra Ceramic Table Lamp from recently ordered items to my cart
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 Uttermost Volterra Ceramic Table Lamp from recently ordered items
  - G2 【目标位置】添加到 cart
  - G3 【保存生效】新建/添加已持久保存生效

## 29a2b43a4d191b0bb1ee
- **题面：** Create a new branch for the a11y-syntax-highlighting project.
- **分支：** （源：remaining）
  - G1 【目标对象】新建/添加的对象与题面要求一致
  - G2 【保存生效】新建/添加已持久保存生效

## 29ecbae3ea55c55031cd
- **题面：** Add the Uttermost Volterra Crackled Taupe-Gray Ceramic Table Lamp to the cart from the Recently Ordered section.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 Uttermost Volterra Crackled Taupe-Gray Ceramic Table Lamp
  - G2 【目标位置】添加到 cart from the Recently Ordered section
  - G3 【保存生效】新建/添加已持久保存生效

## 2c96cf4ce4b66edf956f
- **题面：** Toggle dark mode on/off
- **分支：** （源：remaining）
  - G1 【切换】dark mode 在开/关之间切换
  - G2 【保存生效】修改已持久保存生效

## 2e79840ff46a12c46b95
- **题面：** Create a new issue
- **分支：** （源：remaining）
  - G1 【目标对象】新建/添加的对象与题面要求一致
  - G2 【保存生效】新建/添加已持久保存生效

## 2f24e7eb5277e22771ce
- **题面：** Disable the Enable poppers feature for user MarvelsGrantMan136.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 MarvelsGrantMan
  - G2 【停用】停用 Enable poppers feature
  - G3 【保存生效】修改已持久保存生效

## 2fba24be7aa935d09e98
- **题面：** Update your user preferences
- **分支：** （源：remaining）
  - G1 【保存生效】修改已持久保存生效

## 346554d27daebb5adee9
- **题面：** Create a new project.
- **分支：** （源：remaining）
  - G1 【目标对象】新建/添加的对象与题面要求一致
  - G2 【保存生效】新建/添加已持久保存生效

## 35074768fbbad9271b0c
- **题面：** Add the Pre-baked Gingerbread House Kit to your wish list
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 Pre-baked Gingerbread House Kit
  - G2 【目标位置】添加到 wish list
  - G3 【保存生效】新建/添加已持久保存生效

## 35fb56768f391ad7ebb9
- **题面：** Add the "Maryia Men 3D Creative Printed Graphic T Shirts Casual Short Sleeve Crewneck Muscle Tees Personality Realistic Suit" to the comparison list.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 Maryia Men 3D Creative Printed Graphic T Shirts Casual Short Sleeve Crewneck Muscle Tees Personality Realistic Suit
  - G2 【目标位置】添加到 comparison list
  - G3 【保存生效】新建/添加已持久保存生效

## 3767324f502944e66dd3
- **题面：** Downvote the article "TIFU by forgetting about a zucchini"
- **分支：** （源：remaining）
  - G1 【点踩成功】点踩成功：目标为 article TIFU by forgetting about a zucchini

## 3821fd77af965371b169
- **题面：** Add the Pibbs 512 Ez Dryer with Caster Base Sale! to the cart.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 Pibbs 512 Ez Dryer with Caster Base Sale!
  - G2 【目标位置】添加到 cart
  - G3 【保存生效】新建/添加已持久保存生效

## 433c529124cc06c2dad3
- **题面：** Subscribe to the newsletter with your email.
- **分支：** （源：remaining）
  - G1 【订阅成功】订阅成功：目标为 newsletter with your email

## 43a0778d64e6dc762204
- **题面：** Navigate to your shopping cart to view items and checkout.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Navigate to your shopping cart to view items and checkout.

## 440a0c118be897c257ac
- **题面：** Subscribe to the space forum.
- **分支：** （源：remaining）
  - G1 【订阅成功】订阅成功：目标为 space forum

## 45c845400961a8f18e66
- **题面：** Edit the Plus Size Lingerie item in your cart to change options.
- **分支：** （源：remaining）
  - G1 【变更字段】变更 options
  - G2 【保存生效】修改已持久保存生效

## 48444c99c29b4f40e01e
- **题面：** Change front page filter from "Subscribed" to "All" forums
- **分支：** （源：remaining）
  - G1 【首页筛选】首页筛选 从 "Subscribed" 改为 "All forums"
  - G2 【保存生效】修改已持久保存生效

## 4e122a29272c5d52a0f2
- **题面：** Disable showing post previews when creating content
- **分支：** （源：remaining）
  - G1 【发布成功】发布成功：目标为 previews when creating content

## 4e6a1954e68c88e5c07d
- **题面：** Downvote the joke "I gave a woman my umbrella yesterday"
- **分支：** （源：remaining）
  - G1 【点踩成功】点踩成功：目标为 joke I gave a woman my umbrella yesterday

## 572e685378b6a647663c
- **题面：** View your To-Do List which shows 5 pending items.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：View your To-Do List which shows 5 pending items.

## 5f3b1fc922d52ca9c35a
- **题面：** Change language preference to Spanish
- **分支：** （源：remaining）
  - G1 【语言偏好】语言偏好 改为 "Spanish"
  - G2 【保存生效】修改已持久保存生效

## 616ba61bec5ad15bc671
- **题面：** Move the NOZE Rustic Coat Rack to my wish list
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 NOZE Rustic Coat Rack
  - G2 【目标位置】移动到 wish list
  - G3 【保存生效】修改已持久保存生效

## 6794d03840f462593120
- **题面：** Move the NOZE Rustic Coat Rack Wall Mounted Shelf to the wishlist.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 NOZE Rustic Coat Rack Wall Mounted Shelf
  - G2 【目标位置】移动到 wishlist
  - G3 【保存生效】修改已持久保存生效

## 68265f36c43a4f58b0f7
- **题面：** Create a new project or repository.
- **分支：** （源：remaining）
  - G1 【目标对象】新建/添加的对象与题面要求一致
  - G2 【保存生效】新建/添加已持久保存生效

## 6b7ab50d1b72845a5270
- **题面：** Create and save a wiki page at /wiki/new-article with title "Latest Tech Innovations" and exactly this body:
- **分支：** （源：remaining）
  - G1 【路径】wiki 页面路径为 /wiki/new-article
  - G2 【标题】标题精确为 "Latest Tech Innovations"
  - G3 【正文】正文内容与题面给定文本精确一致
  - G4 【保存生效】新建/添加已持久保存生效

## 6c0f03afbcbc6d8ef96b
- **题面：** Create and save a wiki page at /wiki/index with title "Introduction to Python" and exactly this body:
- **分支：** （源：remaining）
  - G1 【路径】wiki 页面路径为 /wiki/index
  - G2 【标题】标题精确为 "Introduction to Python"
  - G3 【正文】正文内容与题面给定文本精确一致
  - G4 【保存生效】新建/添加已持久保存生效

## 6e4f3e0f8c42d649829b
- **题面：** Navigate to my shopping cart to review my items and proceed to checkout.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Navigate to my shopping cart to review my items and proceed to checkout.

## 6fb93d58020f82213bf1
- **题面：** Create a new page from the error page.
- **分支：** （源：remaining）
  - G1 【目标对象】新建/添加的对象与题面要求一致
  - G2 【保存生效】新建/添加已持久保存生效

## 72130d8a58430dda2e35
- **题面：** Enable "Open external links in new tab" option
- **分支：** （源：remaining）
  - G1 【启用】启用 "Open external links in new tab" option
  - G2 【保存生效】新建/添加已持久保存生效

## 72ce5f2294a8f39f8803
- **题面：** Mark all pending to-do items as done at once.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 all pending to-do items
  - G2 【状态】状态标记为 done
  - G3 【保存生效】修改已持久保存生效

## 73ec5bf7713d816f8c8d
- **题面：** Upvote or downvote the article "Michelle Yeoh to Receive Palm Springs Film Festival’s International Star Award"
- **分支：** （源：remaining）
  - G1 【点赞成功】点赞成功：目标为 or downvote the article Michelle Yeoh to Receive Palm Springs Film Festival’s International Star Award

## 780d320a0f2e394bbca9
- **题面：** Open checkout for the current cart and finish once the native shipping or payment stage is ready. Keep the current customer, cart contents, coupon and saved addresses unchanged; do not place an order.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Open checkout for the current cart and finish once the native shipping or payment stage is ready. Keep the current customer, cart contents, coupon and saved addresses unchanged; do not place an order.

## 78b4f2fb41ec8a7f9664
- **题面：** Add the Elmwood Inn Fine Teas, Orange Vanilla Caffeine-free Fruit Infusion to the cart.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 Elmwood Inn Fine Teas, Orange Vanilla Caffeine-free Fruit Infusion
  - G2 【目标位置】添加到 cart
  - G3 【保存生效】新建/添加已持久保存生效

## 7acc9730e315212d03c8
- **题面：** Upvote the article "TIFU by forgetting about a zucchini"
- **分支：** （源：remaining）
  - G1 【点赞成功】点赞成功：目标为 article TIFU by forgetting about a zucchini

## 7b77045a9659fd095c4e
- **题面：** Add the Pre-baked Gingerbread House Kit Value Pack to my wish list
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 Pre-baked Gingerbread House Kit Value Pack
  - G2 【目标位置】添加到 wish list
  - G3 【保存生效】新建/添加已持久保存生效

## 7c7d967cd9140300d497
- **题面：** Switch to dark mode
- **分支：** （源：remaining）
  - G1 【切换】切换到 dark mode
  - G2 【保存生效】修改已持久保存生效

## 7ddb7efe5d6456f895f7
- **题面：** Add the Pre-baked Gingerbread House Kit to the compare list
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 Pre-baked Gingerbread House Kit
  - G2 【目标位置】添加到 compare list
  - G3 【保存生效】新建/添加已持久保存生效

## 7ff082c612c70774969b
- **题面：** Subscribe to the LifeProTips forum.
- **分支：** （源：remaining）
  - G1 【订阅成功】订阅成功：目标为 LifeProTips forum

## 801de193509118ee95fb
- **题面：** Remove the Plus Size Lingerie item from the shopping cart
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 Plus Size Lingerie item
  - G2 【移除位置】从 shopping cart 移除
  - G3 【保存生效】修改已持久保存生效

## 80541ea9b5b31b0f6a85
- **题面：** Downvote the article about 'Tom's Diner' by Suzanne Vega.
- **分支：** （源：remaining）
  - G1 【点踩成功】点踩成功：目标为 article about Toms Diner by Suzanne Vega

## 819d74d1fc7a5568511a
- **题面：** Star the "ArduinoJson" project
- **分支：** （源：remaining）
  - G1 【星标成功】星标成功：目标为 ArduinoJson project

## 82f85c40a94438ddf5ef
- **题面：** Create and save a wiki page at /wiki/getting-started with title "Getting Started Guide" and exactly this body:
- **分支：** （源：remaining）
  - G1 【路径】wiki 页面路径为 /wiki/getting-started
  - G2 【标题】标题精确为 "Getting Started Guide"
  - G3 【正文】正文内容与题面给定文本精确一致
  - G4 【保存生效】新建/添加已持久保存生效

## 830535a81f43e9c1cdac
- **题面：** Save the new wiki page after filling in all required fields.
- **分支：** （源：remaining）
  - G1 【目标对象】新建/添加的对象与题面要求一致
  - G2 【保存生效】新建/添加已持久保存生效

## 84494cc645c974adb066
- **题面：** Open checkout for the current cart and finish once the native shipping or payment stage is ready. Keep the current customer, cart contents, coupon and saved addresses unchanged; do not place an order.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Open checkout for the current cart and finish once the native shipping or payment stage is ready. Keep the current customer, cart contents, coupon and saved addresses unchanged; do not place an order.

## 876493c893cb188fa4e7
- **题面：** Add a new issue to the a11y-syntax-highlighting project.
- **分支：** （源：remaining）
  - G1 【目标对象】新建/添加的对象与题面要求一致
  - G2 【保存生效】新建/添加已持久保存生效

## 882cafae2c499740c360
- **题面：** Add "Wedge Sandals for Women Dressy Summer, Womens Shiny Ankle Strap Platform Block Chunky High Heel Pumps Sandals for Party" to the compare list.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 Women Dressy
  - G2 【目标位置】添加到 compare list
  - G3 【保存生效】新建/添加已持久保存生效

## 89a101a3a9be8db9ee7e
- **题面：** Sort your GitLab to-do list by creation date from oldest to newest.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 your GitLab to-do list
  - G2 【排序】按 creation date 排序（oldest → newest）
  - G3 【保存生效】修改已持久保存生效

## 8a9bad19592b72927742
- **题面：** Star the a11y-syntax-highlighting repository to bookmark it for future reference.
- **分支：** （源：remaining）
  - G1 【星标成功】星标成功：目标为 a11y-syntax-highlighting repository to bookmark it

## 8c25247257def54b727c
- **题面：** Upvote the comment made by user dman2316.
- **分支：** （源：remaining）
  - G1 【点赞成功】点赞成功：目标为 comment made by user dman2316

## 8c4cbdf3e551525e138d
- **题面：** Change the street address line 1 to "202 Main St" for Emma Lopez.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 Emma Lopez
  - G2 【变更字段】变更 street address line 1
  - G3 【保存生效】修改已持久保存生效

## 8d867fb586dc6cafce4e
- **题面：** Subscribe to the funny forum to receive updates.
- **分支：** （源：remaining）
  - G1 【订阅成功】订阅成功：目标为 funny forum

## 8dc1e9b243c5cf441c09
- **题面：** Disable the Show thumbnails feature for user MarvelsGrantMan136.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 MarvelsGrantMan
  - G2 【停用】停用 Show thumbnails feature
  - G3 【保存生效】修改已持久保存生效

## 8f24a2bef415d91fe910
- **题面：** Create the missing index page for the wiki.
- **分支：** （源：remaining）
  - G1 【目标对象】新建/添加的对象与题面要求一致
  - G2 【保存生效】新建/添加已持久保存生效

## 90595012a6889c740d38
- **题面：** Filter your to-do list to only show merge request related items.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 your to-do list
  - G2 【过滤条件】仅显示满足「merge request related items」的项
  - G3 【保存生效】修改已持久保存生效

## 91bd95dca4ad6f46b718
- **题面：** View and edit my shopping cart details. Make and save at least one change to an existing cart item: change its quantity or product options, or remove it. Do not add new products or change the coupon.
- **分支：** （源：remaining）
  - G1 【变更字段】变更 to an existing cart item: change its quantity or product options
  - G2 【保存生效】新建/添加已持久保存生效

## 934ce48eda6789cb6c01
- **题面：** Subscribe to the worldnews forum
- **分支：** （源：remaining）
  - G1 【订阅成功】订阅成功：目标为 worldnews forum

## 9448ab1d6ebd865a8596
- **题面：** Disable post previews for a cleaner interface
- **分支：** （源：remaining）
  - G1 【发布成功】发布成功：目标为 previews for a cleaner interface

## 964ceb17a32e7a77f6da
- **题面：** Open the Apply Discount Code section during checkout
- **分支：** （源：remaining）
  - G1 【优惠码】应用优惠码 section
  - G2 【保存生效】修改已持久保存生效

## 985421d50a535746a6c6
- **题面：** Change front page sort order from "Hot" to "New"
- **分支：** （源：remaining）
  - G1 【首页排序】首页排序 从 "Hot" 改为 "New"
  - G2 【保存生效】新建/添加已持久保存生效

## 9a402dc1471566f4f22c
- **题面：** Mark the to-do "feat: add WCAG levels" as done.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 feat: add WCAG levels
  - G2 【状态】状态标记为 done
  - G3 【保存生效】新建/添加已持久保存生效

## 9d4fbf79ed4872b34827
- **题面：** Subscribe to the store newsletter with your email address.
- **分支：** （源：remaining）
  - G1 【订阅成功】订阅成功：目标为 store newsletter with your email address

## 9d6e230633b755152e3c
- **题面：** Create a new forum
- **分支：** （源：remaining）
  - G1 【目标对象】新建/添加的对象与题面要求一致
  - G2 【保存生效】新建/添加已持久保存生效

## 9e17e644c5326178635e
- **题面：** Filter your GitLab to-do list to only show items assigned by Byte Blaze.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 your GitLab to-do list
  - G2 【过滤条件】仅显示满足「items assigned by Byte Blaze」的项
  - G3 【保存生效】修改已持久保存生效

## a103a8bf83456ebcc07e
- **题面：** Add the Posiflex MT4008 Point of Sale Tablet to the cart.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 Posiflex MT4008 Point of Sale Tablet
  - G2 【目标位置】添加到 cart
  - G3 【保存生效】新建/添加已持久保存生效

## a1d74439291080fb3730
- **题面：** Add the SPYPOINT Link-EVO Cellular Trail Camera to your wish list.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 SPYPOINT Link-EVO Cellular Trail Camera
  - G2 【目标位置】添加到 wish list
  - G3 【保存生效】新建/添加已持久保存生效

## a20d3cc48faf9df8146d
- **题面：** Upvote the article titled \\"Spotify has some bizarre auto-generated playlists that you can only find by searching them.\\"
- **分支：** （源：remaining）
  - G1 【点赞成功】点赞成功：目标为 article titled \\Spotify has some bizarre auto-generated playlists that you can only find by searching them

## a21170d3a936a825ea62
- **题面：** Subscribe the email address of the currently signed-in account to the store newsletter.
- **分支：** （源：remaining）
  - G1 【订阅成功】订阅操作已成功执行

## a33b893d48c40a7f7da4
- **题面：** Create and save a wiki page at /wiki/community-guidelines with title "Community Guidelines" and exactly this body:
- **分支：** （源：remaining）
  - G1 【路径】wiki 页面路径为 /wiki/community-guidelines
  - G2 【标题】标题精确为 "Community Guidelines"
  - G3 【正文】正文内容与题面给定文本精确一致
  - G4 【保存生效】新建/添加已持久保存生效

## a39a5f86feb3d475a2e3
- **题面：** View and edit my full shopping cart. Make and save at least one change to an existing cart item: change its quantity or product options, or remove it. Do not add new products or change the coupon.
- **分支：** （源：remaining）
  - G1 【变更字段】变更 to an existing cart item: change its quantity or product options
  - G2 【保存生效】新建/添加已持久保存生效

## a410193d35e6ad93bbd3
- **题面：** Star the bootstrap project
- **分支：** （源：remaining）
  - G1 【星标成功】星标成功：目标为 bootstrap project

## a5de066e108da443d03a
- **题面：** Downvote the comment made by user Xacktastic.
- **分支：** （源：remaining）
  - G1 【点踩成功】点踩成功：目标为 comment made by user Xacktastic

## a637e3620deac49f9042
- **题面：** Create a new forum called TechSupport
- **分支：** （源：remaining）
  - G1 【目标对象】新建/添加的对象与题面要求一致
  - G2 【保存生效】新建/添加已持久保存生效

## a8738759435a08d82b7a
- **题面：** Change time zone to Pacific/Honolulu
- **分支：** （源：remaining）
  - G1 【时区】时区 改为 "Pacific/Honolulu"
  - G2 【保存生效】修改已持久保存生效

## a9a7f1759cf20a7b394d
- **题面：** Navigate to sign out of your account.
- **分支：** （源：remaining）
  - G1 【登出成功】登出成功：目标为 your account

## aa865454f255b63bf6b8
- **题面：** Star the cloud-to-butt project.
- **分支：** （源：remaining）
  - G1 【星标成功】星标成功：目标为 cloud-to-butt project

## aaac296a526d1d9cac0a
- **题面：** Toggle between dark mode and light mode.
- **分支：** （源：remaining）
  - G1 【切换】dark mode 模式已切换
  - G2 【保存生效】修改已持久保存生效

## aae31dacb41b5f6e2d99
- **题面：** Change the quantity of items in your shopping cart.
- **分支：** （源：remaining）
  - G1 【变更字段】变更 quantity
  - G2 【保存生效】修改已持久保存生效

## ae19fccf2b93aebb137e
- **题面：** Disable notifications for mentions
- **分支：** （源：remaining）
  - G1 【停用】停用 notifications
  - G2 【保存生效】修改已持久保存生效

## b266468b67183f2e079d
- **题面：** Fork the A11Y Project repository to your own account.
- **分支：** （源：remaining）
  - G1 【Fork成功】Fork成功：目标为 A11Y Project repository

## b47b075524c3dc613cfd
- **题面：** Hide the Jokes forum from view
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 Jokes forum
  - G2 【隐藏】隐藏 Jokes forum
  - G3 【保存生效】修改已持久保存生效

## b6c3f158bc171da68ffa
- **题面：** Update your shopping cart items. Make and save at least one change to an existing cart item: change its quantity or product options, or remove it. Do not add new products or change the coupon.
- **分支：** （源：remaining）
  - G1 【变更字段】变更 to an existing cart item: change its quantity or product options
  - G2 【保存生效】新建/添加已持久保存生效

## b7c40664f6750d27adb0
- **题面：** Upvote the joke titled "This man went out with the boys, and told his wife that he would be home by midnight."
- **分支：** （源：remaining）
  - G1 【点赞成功】点赞成功：目标为 joke titled This man went out with the boys, and told his wife that he would be home by midnight

## b7ebff2b5aff3205419d
- **题面：** Remove the NOZE Rustic Coat Rack from my shopping cart
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 NOZE Rustic Coat Rack
  - G2 【移除位置】从 shopping cart 移除
  - G3 【保存生效】修改已持久保存生效

## b8a7309ec04b073a35f6
- **题面：** View all to-do items related to issues in your GitLab account.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：View all to-do items related to issues in your GitLab account.

## ba935aa5d0dea8bb19ec
- **题面：** Navigate to the Apply Discount Code section to enter a promotional code.
- **分支：** （源：remaining）
  - G1 【优惠码】应用优惠码 section
  - G2 【保存生效】修改已持久保存生效

## bc469d901f42a142bec1
- **题面：** Create a new forum.
- **分支：** （源：remaining）
  - G1 【目标对象】新建/添加的对象与题面要求一致
  - G2 【保存生效】新建/添加已持久保存生效

## bc9b3d8163d8ef48c0bc
- **题面：** Create a new branch from the main branch
- **分支：** （源：remaining）
  - G1 【目标对象】新建/添加的对象与题面要求一致
  - G2 【保存生效】新建/添加已持久保存生效

## be7248582d84074c759d
- **题面：** Upvote or downvote the article "Oscars: \\"Naatu Naatu\\" From India’s ‘RRR’ To Be Performed During Ceremony"
- **分支：** （源：remaining）
  - G1 【点赞成功】点赞成功：目标为 or downvote the article Oscars: \\Naatu Naatu\\ From India’s ‘RRR’ To Be Performed During Ceremony

## c99e8913f1e235e9344a
- **题面：** Enable the Full width display for user MarvelsGrantMan136.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 MarvelsGrantMan
  - G2 【启用】启用 Full width display
  - G3 【保存生效】修改已持久保存生效

## c9d0f695a19d6083f656
- **题面：** Add the Sceptre E195BD-SRR 19-Inch LED TV to my wish list
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 Sceptre E195BD-SRR 19-Inch LED TV
  - G2 【目标位置】添加到 wish list
  - G3 【保存生效】新建/添加已持久保存生效

## cffb818544ff12e3822f
- **题面：** Disable private messages for user MarvelsGrantMan136.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 MarvelsGrantMan
  - G2 【停用】停用 private messages
  - G3 【保存生效】修改已持久保存生效

## d10e7208371e975eee58
- **题面：** Proceed to the Review & Payments step in the checkout process.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Proceed to the Review & Payments step in the checkout process.

## d331d0bd22404ccadb10
- **题面：** Toggle between dark mode and light mode
- **分支：** （源：remaining）
  - G1 【切换】dark mode 模式已切换
  - G2 【保存生效】修改已持久保存生效

## d4224fe483c9d08d44b4
- **题面：** Sign out from your account.
- **分支：** （源：remaining）
  - G1 【登出成功】登出操作已成功执行

## d4aefab9199bc9da69e6
- **题面：** Disable notifications for replies to your posts
- **分支：** （源：remaining）
  - G1 【停用】停用 notifications
  - G2 【保存生效】修改已持久保存生效

## d4ccb1e3e7d00b321a94
- **题面：** Navigate to the My Cart checkout page.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Navigate to the My Cart checkout page.

## d7b47909820eb98296db
- **题面：** Downvote the post titled "An unusual letter was posted into my front door this morning."
- **分支：** （源：remaining）
  - G1 【点踩成功】点踩成功：目标为 post titled An unusual letter was posted into my front door this morning

## d86e22a021e369d0bfc3
- **题面：** Add the "Power of Positivity" Eye Shadow Palette to the comparison list.
- **分支：** （源：remaining）
  - G1 【目标对象】新建/添加的对象与题面要求一致
  - G2 【保存生效】新建/添加已持久保存生效

## dd05bf5d7e29ed3f8810
- **题面：** Toggle between light and dark mode
- **分支：** （源：remaining）
  - G1 【切换】light 模式已切换
  - G2 【保存生效】修改已持久保存生效

## dd93092f20e5fcd2af32
- **题面：** Add the ACPOTEL Night Vision Monocular to your shopping cart.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 ACPOTEL Night Vision Monocular
  - G2 【目标位置】添加到 shopping cart
  - G3 【保存生效】新建/添加已持久保存生效

## e13dd61bf81912fc20ef
- **题面：** Open checkout for the current cart and finish once the native shipping or payment stage is ready. Keep the current customer, cart contents, coupon and saved addresses unchanged; do not place an order.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Open checkout for the current cart and finish once the native shipping or payment stage is ready. Keep the current customer, cart contents, coupon and saved addresses unchanged; do not place an order.

## e1c75ad898b1a0a82d9f
- **题面：** Create the main Wiki index page.
- **分支：** （源：remaining）
  - G1 【目标对象】新建/添加的对象与题面要求一致
  - G2 【保存生效】新建/添加已持久保存生效

## e2a7ac427e87c2c04291
- **题面：** Remove the Uttermost Volterra Crackled Taupe-Gray Ceramic Table Lamp from the shopping cart.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 Uttermost Volterra Crackled Taupe-Gray Ceramic Table Lamp
  - G2 【移除位置】从 shopping cart 移除
  - G3 【保存生效】修改已持久保存生效

## e3d20a86c07fe9881ad2
- **题面：** Subscribe to the tifu forum.
- **分支：** （源：remaining）
  - G1 【订阅成功】订阅成功：目标为 tifu forum

## e3fe00ee91ddcb3e5ff6
- **题面：** Create and save a wiki page at /wiki/index with title "HTML Example" and exactly this body:
- **分支：** （源：remaining）
  - G1 【路径】wiki 页面路径为 /wiki/index
  - G2 【标题】标题精确为 "HTML Example"
  - G3 【正文】正文内容与题面给定文本精确一致
  - G4 【保存生效】新建/添加已持久保存生效

## e54dafa5db4016de692a
- **题面：** Remove the Uttermost Volterra Table Lamp from my cart
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 Uttermost Volterra Table Lamp
  - G2 【移除位置】从 cart 移除
  - G3 【保存生效】修改已持久保存生效

## e8234f3597bb4919bea0
- **题面：** Add BHNDOING DIY Night Vision Scope to the wish list.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 BHNDOING DIY Night Vision Scope
  - G2 【目标位置】添加到 wish list
  - G3 【保存生效】新建/添加已持久保存生效

## e93c67192e8e54d4431c
- **题面：** Add "Mens Cotton Dress Shirts Short Sleeve Button Down Summer Casual Roll Up Beach Hawaiian Hipster Tops Classic Poplin Shirt" to the wish list.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 Mens Cotton Dress Shirts Short Sleeve Button Down Summer Casual Roll Up Beach Hawaiian Hipster Tops Classic Poplin Shirt
  - G2 【目标位置】添加到 wish list
  - G3 【保存生效】新建/添加已持久保存生效

## e94eaf34f5b356f2fb2f
- **题面：** Click the "Place Order" button to complete the purchase of the ceramic table lamp and other items
- **分支：** （源：remaining）
  - G1 【下单】完成下单，创建订单
  - G2 【保存生效】写操作已持久保存生效

## eeddf8caba328ec21c49
- **题面：** Star the project "Square / maximum-awesome".
- **分支：** （源：remaining）
  - G1 【星标成功】星标成功：目标为 project Square / maximum-awesome

## f06ebd1c33fba01c93f5
- **题面：** Fork the Super-SloMo repository
- **分支：** （源：remaining）
  - G1 【Fork成功】Fork成功：目标为 Super-SloMo repository

## f306c1714031eda5b377
- **题面：** Add the ATN DNVM-2 Digital Night Vision Monocular to your cart
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 ATN DNVM-2 Digital Night Vision Monocular
  - G2 【目标位置】添加到 cart
  - G3 【保存生效】新建/添加已持久保存生效

## f43f661f91be8223f0e9
- **题面：** Create a new issue for the autojump project
- **分支：** （源：remaining）
  - G1 【目标对象】新建/添加的对象与题面要求一致
  - G2 【保存生效】新建/添加已持久保存生效

## f56c72a352b89e085203
- **题面：** Create and save a wiki page at /wiki/index with title "Site Features" and exactly this body:
- **分支：** （源：remaining）
  - G1 【路径】wiki 页面路径为 /wiki/index
  - G2 【标题】标题精确为 "Site Features"
  - G3 【正文】正文内容与题面给定文本精确一致
  - G4 【保存生效】新建/添加已持久保存生效

## f5dafaacdfa776fa8342
- **题面：** Add both the BARSKA AB13345 Hunting Optics Binoculars and the MaxUSee Spotting Scope to your cart for comparison
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 both the BARSKA AB13345 Hunting Optics Binoculars and the MaxUSee Spotting Scope
  - G2 【目标位置】添加到 cart for comparison
  - G3 【保存生效】新建/添加已持久保存生效

## f644eca9332742cda001
- **题面：** Create a new tag for a release version.
- **分支：** （源：remaining）
  - G1 【目标对象】新建/添加的对象与题面要求一致
  - G2 【保存生效】新建/添加已持久保存生效

## f79bd8d8fabfbe62cf3e
- **题面：** Clear all items from my shopping cart
- **分支：** （源：remaining）
  - G1 【清空】清空 shopping cart 中的全部项
  - G2 【保存生效】修改已持久保存生效

## f8a40b4ea61dfc96894e
- **题面：** Open checkout for the current cart and finish once the native shipping or payment stage is ready. Keep the current customer, cart contents, coupon and saved addresses unchanged; do not place an order.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Open checkout for the current cart and finish once the native shipping or payment stage is ready. Keep the current customer, cart contents, coupon and saved addresses unchanged; do not place an order.

## fa8c9ae023cd1fad051c
- **题面：** Subscribe to the newsletter with your email address.
- **分支：** （源：remaining）
  - G1 【订阅成功】订阅成功：目标为 newsletter with your email address

## fab30915ee2c14a8b87c
- **题面：** Remove the NOZE Rustic Coat Rack Wall Mounted Shelf from the shopping cart.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 NOZE Rustic Coat Rack Wall Mounted Shelf
  - G2 【移除位置】从 shopping cart 移除
  - G3 【保存生效】修改已持久保存生效

## fb822ab7e2266785959d
- **题面：** Add the Tweezers For Succulents Duo to your shopping cart.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 Tweezers For Succulents Duo
  - G2 【目标位置】添加到 shopping cart
  - G3 【保存生效】新建/添加已持久保存生效

## ff86d25219ba6db09ffd
- **题面：** Fork the a11y-syntax-highlighting repository to create your own copy.
- **分支：** （源：remaining）
  - G1 【目标对象】新建/添加的对象与题面要求一致
  - G2 【保存生效】新建/添加已持久保存生效

## ff8df7a0f979f579db7d
- **题面：** Add "DkRgVNY Lace Spcling Lingerie Womens Sexy Hollow Out Underwear Bodysuit One Piece Snap Crotch Clubwear Teddy Bodysuit" to the cart.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 DkRgVNY Lace Spcling Lingerie Womens Sexy Hollow Out Underwear Bodysuit One Piece Snap Crotch Clubwear Teddy Bodysuit
  - G2 【目标位置】添加到 cart
  - G3 【保存生效】新建/添加已持久保存生效

## 02e8f50b98202c949ce1
- **题面：** Navigate to the Share options to share your route with others The initial driving route is Central Park (40.7830, -73.9650) to Times Square (40.7570, -73.9860). Completion means the native Share panel is visible with a usable sharing control; external delivery is not requested.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Navigate to the Share options to share your route with others The initial driving route is Central Park (40.7830, -73.9650) to Times Square (40.7570, -73.9860). Completion means the native Share panel is visible with a usable sharing control; external delivery is not requested.

## 3c6180fffd4bcea9510a
- **题面：** Return a local map link representing the center, zoom and base layer shown when this task started. Finish with a JSON object containing exactly share_link. External delivery is not required.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Return a local map link representing the center, zoom and base layer shown when this task started. Finish with a JSON object containing exactly share_link. External delivery is not required.

## 60109159641dde2b0a25
- **题面：** Return a local map link representing the center, zoom and base layer shown when this task started. Finish with a JSON object containing exactly share_link. External delivery is not required.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Return a local map link representing the center, zoom and base layer shown when this task started. Finish with a JSON object containing exactly share_link. External delivery is not required.

## 7816d8c07201aa7da548
- **题面：** Share a route with someone Share the initial driving route from Central Park (40.7830, -73.9650) to Times Square (40.7570, -73.9860) by returning a local link that reopens those endpoints and driving mode. No external recipient or delivery is required.
- **分支：** （源：remaining）
  - G1 【分享成功】分享成功：目标为 a route with someone Share the initial driving route from Central Park (40

## a75fa42523fd3e7bfba4
- **题面：** Share this route with someone else Share the initial driving route from Central Park (40.7830, -73.9650) to Times Square (40.7570, -73.9860) by returning a local link that reopens those endpoints and driving mode. No external recipient or delivery is required.
- **分支：** （源：remaining）
  - G1 【分享成功】分享成功：目标为 this route with someone else Share the initial driving route from Central Park (40

## da1bfe617760c1b52bf7
- **题面：** Return a local map link representing the center, zoom and base layer shown when this task started. Finish with a JSON object containing exactly share_link. External delivery is not required.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Return a local map link representing the center, zoom and base layer shown when this task started. Finish with a JSON object containing exactly share_link. External delivery is not required.

## f9759f4731398ee74dab
- **题面：** Share the current map view with others The declared initial map view is zoom 11 centered at latitude 40.6976, longitude -73.9799. Return a local sharing link for this view; no external delivery is required.
- **分支：** （源：remaining）
  - G1 【分享成功】分享成功：目标为 current map view with others The declared initial map view is zoom 11 centered at latitude 40

## fd7f504b628b30b3872b
- **题面：** Return a local map link representing the center, zoom and base layer shown when this task started. Finish with a JSON object containing exactly share_link. External delivery is not required.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Return a local map link representing the center, zoom and base layer shown when this task started. Finish with a JSON object containing exactly share_link. External delivery is not required.

## fda1a250d55040b53f45
- **题面：** Share the map with custom dimensions Return native map embed markup with width 800 pixels and height 600 pixels for the original map area. No external publishing is required.
- **分支：** （源：remaining）
  - G1 【分享成功】分享成功：目标为 map with custom dimensions Return native map embed markup with width 800 pixels and height 600 pixels for the original map area

## 06257dae2e82b85da2c0
- **题面：** View your profile and order history in My Account. Complete after both sections have been displayed; you may finish on either section.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：View your profile and order history in My Account. Complete after both sections have been displayed; you may finish on either section.

## 0c1acdfc4c64a7973349
- **题面：** Navigate to your shopping cart to view items.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Navigate to your shopping cart to view items.

## 0f0dac9d71a75d31e7c7
- **题面：** Explore Sports & Outdoor Recreation Accessories. Complete on this category's product list or a product belonging to this category.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Explore Sports & Outdoor Recreation Accessories. Complete on this category's product list or a product belonging to this category.

## 359661cd246edee86b0b
- **题面：** Explore Electronics products. Complete on this category's product list or a product belonging to this category.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Explore Electronics products. Complete on this category's product list or a product belonging to this category.

## 60003bea880b2c221dfe
- **题面：** Navigate to your shopping cart to see the items you have added.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Navigate to your shopping cart to see the items you have added.

## 670499b804d3504a2dcf
- **题面：** View all items in your cart
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：View all items in your cart

## 812d5057c08a63b379d5
- **题面：** Browse Beauty & Personal Care products. Complete on this category's product list or a product belonging to this category.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## cbdde79bc3ea252774e2
- **题面：** View your shopping cart
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：View your shopping cart

## e5a4555efa3a045296b7
- **题面：** Go to my shopping cart
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Go to my shopping cart

## e8505eec4ed09f0164b8
- **题面：** Go to my shopping cart to view the items I have added.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Go to my shopping cart to view the items I have added.

## f74a43d388fc44e745b8
- **题面：** View my shopping cart.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：View my shopping cart.

## 07e0b01e0939579ed9cf
- **题面：** Subscribe to the Jokes forum.
- **分支：** （源：remaining）
  - G1 【订阅成功】订阅成功：目标为 Jokes forum

## 3596b2e681128fad82e7
- **题面：** Create a text submission in AskReddit titled "A Small Helpful Habit" with this exact Markdown body: "What small daily habit improved your day?\n\n- Describe the habit.\n- Explain why it helped.".
- **分支：** （源：remaining）
  - G1 【标题】标题精确为 "A Small Helpful Habit"
  - G2 【正文】正文内容与题面给定文本精确一致
  - G3 【保存生效】新建/添加已持久保存生效

## 5718d30f35cbbc4a8a04
- **题面：** Create a forum with these exact fields: {"name": "PhotographyPractice", "title": "Photography Practice", "description": "Discuss photography equipment and techniques.", "sidebar": "Share photography advice respectfully.", "tags": ["equipment", "techniques"]}.
- **分支：** （源：remaining）
  - G1 【分享成功】分享成功：目标为 photography advice respectfully

## 5db02c00018733e52496
- **题面：** Create a text submission in AskReddit titled "Markdown Formatting Practice" with this exact Markdown body: "# Discussion\n\n- First point\n- Second point".
- **分支：** （源：remaining）
  - G1 【标题】标题精确为 "Markdown Formatting Practice"
  - G2 【正文】正文内容与题面给定文本精确一致
  - G3 【保存生效】新建/添加已持久保存生效

## 79f958b0d09e0eb0ce3b
- **题面：** Create the wiki page with these exact path, title and Markdown body fields: {"path": "index", "title": "Index", "body": "# Index\n\n## Table of contents\n\n- [Getting started](#getting-started)\n- [Topics](#topics)\n\n## Getting started\n\nRead the topics below.\n\n## Topics\n\n### Discussion\n\nShare useful information."}.
- **分支：** （源：remaining）
  - G1 【目标对象】新建/添加的对象与题面要求一致
  - G2 【保存生效】新建/添加已持久保存生效

## bbb4423f22fcd9b24b44
- **题面：** Create a forum with these exact fields: {"name": "TechnologyTipsPractice", "title": "Technology Tips Practice", "description": "Share practical technology tips.", "sidebar": "Discuss practical technology tips respectfully."}.
- **分支：** （源：remaining）
  - G1 【分享成功】分享成功：目标为 practical technology tips

## efdc03c5517f40d0b8d6
- **题面：** Open the new submission form and select the AskReddit forum; leave the form unsubmitted.
- **分支：** （源：remaining）
  - G1 【退出成功】退出操作已成功执行

## f436a53904af5a2955af
- **题面：** Open a new submission form, enter this exact Markdown body "- First discussion point\n- Second discussion point", and leave the draft unsubmitted.
- **分支：** （源：remaining）
  - G1 【退出成功】退出操作已成功执行

## 083443f4efea7cf5be64
- **题面：** Copy the project ID for a11yproject.com.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 a11yproject
  - G2 【复制】复制 a11yproject 到剪贴板
  - G3 【保存生效】修改已持久保存生效

## 8bd308b6039d0a8e3af9
- **题面：** Download DynamoRIO as a ZIP archive
- **分支：** （源：remaining）
  - G1 【下载成功】下载成功：目标为 DynamoRIO as a ZIP archive

## 8d8739509efd91e27a71
- **题面：** Download the Source directory as a ZIP file
- **分支：** （源：remaining）
  - G1 【下载成功】下载成功：目标为 Source directory as a ZIP file

## 91fbe02c5362c40a1c30
- **题面：** Copy the commit SHA of the latest commit in the a11y-syntax-highlighting repository.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 commit SHA of the latest commit in the a11y-syntax-highlighting repository
  - G2 【复制】复制 commit SHA of the latest commit in the a11y-syntax-highlighting repository 到剪贴板
  - G3 【保存生效】修改已持久保存生效

## eb0bfa978786fec1e65d
- **题面：** Download the cloud-to-butt Chrome extension file
- **分支：** （源：remaining）
  - G1 【下载成功】下载成功：目标为 cloud-to-butt Chrome extension file

## 08473184d468a5dd8d4b
- **题面：** Find the driving route with the lowest expected travel time among the routes actually offered by this local website from Chicago, Illinois to Detroit, Michigan. The current website offers one route; leave it displayed with its estimated time. This does not assert a global fastest-route optimum.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 097262fc8d581f8fb378
- **题面：** Change the size of the Plus Size Lingerie item from Large to Medium
- **分支：** （源：remaining）
  - G1 【尺寸】尺寸 从 "Large" 改为 "Medium"
  - G2 【保存生效】修改已持久保存生效

## 1759257a9bb03d9b51aa
- **题面：** Remove the NOZE Rustic Coat Rack from my cart
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 NOZE Rustic Coat Rack
  - G2 【移除位置】从 cart 移除
  - G3 【保存生效】修改已持久保存生效

## 09bb58ea559bca0a7939
- **题面：** Submit a 5-star review for Pre-baked Gingerbread House Kit Value Pack, 17 oz., Pack of 2, Total 34 oz. with exact review title "Kit quality", exact review text "This kit is well made and easy to assemble.", and reviewer nickname "Emma Lopez". Pending moderation counts as submitted; publication is not required.
- **分支：** （源：remaining）
  - G1 【提交成功】提交成功：目标为 a 5-star review for Pre-baked Gingerbread House Kit Value Pack, 17 oz

## 1edcd9d147703b909066
- **题面：** In this initialized checkout, change the shipping method from Flat Rate to Free Shipping and save the change without placing an order.
- **分支：** （源：remaining）
  - G1 【配送方式】配送方式 从 "Flat Rate" 改为 "Free Shipping"
  - G2 【保存生效】修改已持久保存生效

## 2c25f241e19cbd069320
- **题面：** Apply the local discount code SAVE10 to the initialized shopping cart and confirm the saved 10% item-subtotal discount. Do not place an order.
- **分支：** （源：remaining）
  - G1 【优惠码】应用优惠码 SAVE10
  - G2 【保存生效】修改已持久保存生效

## 3015110b47ad0871eb51
- **题面：** Apply the local discount code SAVE10 to the initialized shopping cart and confirm the saved 10% item-subtotal discount. Do not place an order.
- **分支：** （源：remaining）
  - G1 【优惠码】应用优惠码 SAVE10
  - G2 【保存生效】修改已持久保存生效

## 42f0b80e730cd23551eb
- **题面：** Submit a 5-star review for Pre-baked Gingerbread House Kit Value Pack, 17 oz., Pack of 2, Total 34 oz. with exact review title "Kit review", exact review text "This kit is well made and easy to assemble.", and reviewer nickname "Emma Lopez". Pending moderation counts as submitted; publication is not required.
- **分支：** （源：remaining）
  - G1 【提交成功】提交成功：目标为 a 5-star review for Pre-baked Gingerbread House Kit Value Pack, 17 oz

## 8237179a0d1515ab960a
- **题面：** Apply the local discount code SAVE10 to the initialized shopping cart and confirm the saved 10% item-subtotal discount. Do not place an order.
- **分支：** （源：remaining）
  - G1 【优惠码】应用优惠码 SAVE10
  - G2 【保存生效】修改已持久保存生效

## 87328c9da97417b0a3bf
- **题面：** Submit this exact message through the Contact Us form: {"name": "Emma Lopez", "email": "emma.lopez@example.test", "telephone": "6505551212", "comment": "Please provide information about customer support hours."}. This training website captures the native email locally and does not deliver it externally.
- **分支：** （源：remaining）
  - G1 【提交成功】提交成功：目标为 this exact message through the Contact Us form: {name: Emma Lopez, email: emma

## abd2919a4dd017d86396
- **题面：** In this initialized checkout, change the shipping method from Flat Rate to Free Shipping and save the change without placing an order.
- **分支：** （源：remaining）
  - G1 【配送方式】配送方式 从 "Flat Rate" 改为 "Free Shipping"
  - G2 【保存生效】修改已持久保存生效

## b13602c57124235dc250
- **题面：** In this initialized checkout, select Bank Transfer instead of Check / Money order as the current payment method. Do not place an order.
- **分支：** （源：remaining）
  - G1 【选择】选择 Bank Transfer（而非 Check / Money order）
  - G2 【保存生效】修改已持久保存生效

## be2cbaef98f6643f4518
- **题面：** In this initialized checkout, change the shipping method from Flat Rate to Free Shipping and save the change without placing an order.
- **分支：** （源：remaining）
  - G1 【配送方式】配送方式 从 "Flat Rate" 改为 "Free Shipping"
  - G2 【保存生效】修改已持久保存生效

## deba6b948e9ac76a0c77
- **题面：** The initialized cart contains one Pre-baked Gingerbread House Kit Value Pack, 17 oz., Pack of 2, Total 34 oz.. Change its saved cart quantity from 1 to 2 without changing other products.
- **分支：** （源：remaining）
  - G1 【数量】数量 从 "1" 改为 "2"
  - G2 【保存生效】修改已持久保存生效

## f713feacbafad6bf85c9
- **题面：** In this initialized checkout, save a billing address different from the existing shipping address: {"firstname": "Emma", "lastname": "Lopez", "street": "102 Training Lane", "city": "San Mateo", "country_id": "US", "region_id": 12, "region": "California", "postcode": "94010", "telephone": "6505551212"}. Keep the customer address book unchanged and do not place an order.
- **分支：** （源：remaining）
  - G1 【姓名】姓名保存为 "Emma Lopez"
  - G2 【完整地址】地址各字段保存为 street=102 Training Lane、city=San Mateo、region=California、postcode=94010、country_id=US
  - G3 【电话】电话保存为 6505551212
  - G4 【保存生效】写操作已持久保存生效

## 0ac76cae33c7c5994ac4
- **题面：** Change the map layer to Humanitarian style. Keep the initial geographic area and zoom. Finish with the requested base layer selected and its genuine local-frozen imagery fully rendered.
- **分支：** （源：remaining）
  - G1 【地图图层】地图图层 改为 "Humanitarian style"
  - G2 【保存生效】修改已持久保存生效

## 2b808470bbeb27182cf5
- **题面：** Change the map layer to view satellite imagery. Keep the initial geographic area and zoom. Finish with the requested base layer selected and its genuine local-frozen imagery fully rendered.
- **分支：** （源：remaining）
  - G1 【地图图层】地图图层 改为 "view satellite imagery"
  - G2 【保存生效】修改已持久保存生效

## 2cbe7a37b1b308699099
- **题面：** Compare Standard and ÖPNVKarte at the declared initial map area (zoom 7, latitude 42.896, longitude -75.108), allowing both to finish loading without changing the area or zoom. Select and finish on the style specifically designed for public transportation. Provider brief: Standard is the general-purpose OpenStreetMap style; ÖPNVKarte, provided by memomaps, focuses on public transportation. This task uses that documented purpose as the selection criterion; no visual ranking or written answer is required.
- **分支：** （源：remaining）
  - G1 【选择】选择「public transportation」样式
  - G2 【保存生效】修改已持久保存生效

## 4708d2d69232e0c8b69e
- **题面：** Switch to the Humanitarian map style for disaster response information Start in the declared Standard map view and finish with the requested base layer selected and its genuine local-frozen imagery rendered for the same area.
- **分支：** （源：remaining）
  - G1 【切换】切换到 Humanitarian map
  - G2 【保存生效】修改已持久保存生效

## 476a9c6b0d9bab06d4f5
- **题面：** Inspect the declared initial map area in both Standard and Humanitarian map styles. Let each style finish loading at the same initial zoom and geographic area. Finish with either Standard or Humanitarian showing that area. No ranking of which style is best or written comparison is required.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Inspect the declared initial map area in both Standard and Humanitarian map styles. Let each style finish loading at the same initial zoom and geographic area. Finish with either Standard or Humanitarian showing that area. No ranking of which style is best or written comparison is required.

## 4a5710b7b0bef4592f70
- **题面：** Inspect the displayed route in both Standard and CyclOSM map styles. Let each style finish loading at the same initial zoom and geographic area. Keep the initial route and its endpoints unchanged in both views. Finish with either Standard or CyclOSM showing that area and route. No ranking of which style is best or written comparison is required.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Inspect the displayed route in both Standard and CyclOSM map styles. Let each style finish loading at the same initial zoom and geographic area. Keep the initial route and its endpoints unchanged in both views. Finish with either Standard or CyclOSM showing that area and route. No ranking of which style is best or written comparison is required.

## 63f01a01208ec2bea610
- **题面：** Change the map style from Standard to Humanitarian Start in the declared Standard map view and finish with the requested base layer selected and its genuine local-frozen imagery rendered for the same area.
- **分支：** （源：remaining）
  - G1 【地图样式】地图样式 从 "Standard" 改为 "Humanitarian"
  - G2 【保存生效】修改已持久保存生效

## 7e05021c9b1e9a14ee29
- **题面：** Inspect the declared initial map area in both Standard and Humanitarian map styles. Let each style finish loading at the same initial zoom and geographic area. Finish with either Standard or Humanitarian showing that area. No ranking of which style is best or written comparison is required.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Inspect the declared initial map area in both Standard and Humanitarian map styles. Let each style finish loading at the same initial zoom and geographic area. Finish with either Standard or Humanitarian showing that area. No ranking of which style is best or written comparison is required.

## 9388845c80a2810d0534
- **题面：** Change the map layer to satellite view Start in the declared Standard map view and finish with the requested base layer selected and its genuine local-frozen imagery rendered for the same area.
- **分支：** （源：remaining）
  - G1 【地图图层】地图图层 改为 "satellite view"
  - G2 【保存生效】修改已持久保存生效

## 98f9b7bea82ea834ae3e
- **题面：** Change the map layers to view satellite imagery Start in the declared Standard map view and finish with the requested base layer selected and its genuine local-frozen imagery rendered for the same area.
- **分支：** （源：remaining）
  - G1 【地图图层】地图图层 改为 "view satellite imagery"
  - G2 【保存生效】修改已持久保存生效

## a0e4c50e495d7aeef857
- **题面：** Inspect the declared initial map area in both Standard and Humanitarian map styles. Let each style finish loading at the same initial zoom and geographic area. Finish with either Standard or Humanitarian showing that area. No ranking of which style is best or written comparison is required.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Inspect the declared initial map area in both Standard and Humanitarian map styles. Let each style finish loading at the same initial zoom and geographic area. Finish with either Standard or Humanitarian showing that area. No ranking of which style is best or written comparison is required.

## ae2430c3d8b894cc915d
- **题面：** Switch the map display from Standard to Humanitarian style. Start in the declared Standard map view and finish with the requested base layer selected and its genuine local-frozen imagery rendered for the same area.
- **分支：** （源：remaining）
  - G1 【map display】map display 从 "Standard" 改为 "Humanitarian style"
  - G2 【切换】map display from Standard 切换为 Humanitarian style
  - G3 【保存生效】修改已持久保存生效

## ae4bf86aec96ed2ec07f
- **题面：** Inspect the declared Central Park area in both Standard and Humanitarian map styles. Let each style finish loading at the same initial zoom and geographic area. Finish with either Standard or Humanitarian showing that area. No ranking of which style is best or written comparison is required.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Inspect the declared Central Park area in both Standard and Humanitarian map styles. Let each style finish loading at the same initial zoom and geographic area. Finish with either Standard or Humanitarian showing that area. No ranking of which style is best or written comparison is required.

## dec96aacea17816ba445
- **题面：** Inspect the declared initial map area in both Standard and Humanitarian map styles. Let each style finish loading at the same initial zoom and geographic area. Finish with either Standard or Humanitarian showing that area. No ranking of which style is best or written comparison is required.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Inspect the declared initial map area in both Standard and Humanitarian map styles. Let each style finish loading at the same initial zoom and geographic area. Finish with either Standard or Humanitarian showing that area. No ranking of which style is best or written comparison is required.

## e3fff5c627b420034e82
- **题面：** Inspect the displayed route in both Standard and Humanitarian map styles. Let each style finish loading at the same initial zoom and geographic area. Keep the initial route and its endpoints unchanged in both views. Finish with either Standard or Humanitarian showing that area and route. No ranking of which style is best or written comparison is required.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Inspect the displayed route in both Standard and Humanitarian map styles. Let each style finish loading at the same initial zoom and geographic area. Keep the initial route and its endpoints unchanged in both views. Finish with either Standard or Humanitarian showing that area and route. No ranking of which style is best or written comparison is required.

## 0c29d96781a661d80dc4
- **题面：** Identify reasons why the current map area might be too large for export. Return a JSON object with exactly these fields: {"area_square_degrees": "number", "maximum_area_square_degrees": "number", "too_large": "boolean", "reason": "string"}. Compare the current native selected/export-view rectangle with the native direct-export limit. Use reason as one of ["selected_area_exceeds_direct_export_limit", "selected_area_within_direct_export_limit"]. This reports the observed size condition, not every possible server failure.
- **分支：** （源：remaining）
  - G1 【导出成功】导出成功：目标为 limit

## 26b10b12540867cccc5e
- **题面：** Export map data for offline use.
- **分支：** （源：remaining）
  - G1 【导出成功】导出成功：目标为 map data for offline use

## 45dff43cfa783a42869f
- **题面：** Export the map data
- **分支：** （源：remaining）
  - G1 【导出成功】导出成功：目标为 map data

## 0c738aca4eb5037d0ce6
- **题面：** Use Advanced Search to find products whose Product Name contains chocolate and whose Description contains vegan.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Use Advanced Search to find products whose Product Name contains chocolate and w

## 14303620aff26b029225
- **题面：** Sort the Sports & Outdoors products by price from low to high.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 Sports & Outdoors products
  - G2 【排序】按 price 排序（low → high）
  - G3 【保存生效】修改已持久保存生效

## 2af1b776aff914589cee
- **题面：** Browse the Grocery & Gourmet Food category for vegan options
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 2c05a82cc8e19dbd9da1
- **题面：** Filter the "Sports & Outdoors" items to show only "Footwear".
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 "Sports & Outdoors" items
  - G2 【过滤条件】仅显示满足「only "Footwear"」的项
  - G3 【保存生效】修改已持久保存生效

## 3931bbaa9bebe88a385f
- **题面：** Modify the current Advanced Search to search only for products whose Description contains ergonomic.
- **分支：** （源：remaining）
  - G1 【搜索条件】搜索条件改为：products whose Description contains ergonomic
  - G2 【保存生效】修改已持久保存生效

## 3fd90ef69e41740f2443
- **题面：** Sort electronics products by price from low to high
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 electronics products
  - G2 【排序】按 price 排序（low → high）
  - G3 【保存生效】修改已持久保存生效

## 40903a6027973d27e95f
- **题面：** Open page 2 of the Sports & Outdoors product list.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Open page 2 of the Sports & Outdoors product list.

## 484de4f3df69765f825d
- **题面：** Change the Sports & Outdoors product view from grid to list format.
- **分支：** （源：remaining）
  - G1 【视图】视图 从 "grid" 改为 "list format"
  - G2 【保存生效】修改已持久保存生效

## 5b51fe3b8e85aa84a361
- **题面：** Filter products to only show Hunting & Fishing items.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 products
  - G2 【过滤条件】仅显示满足「Hunting & Fishing items」的项
  - G3 【保存生效】修改已持久保存生效

## 7909d7364767a2fa02a8
- **题面：** Change the product view from Grid to List view.
- **分支：** （源：remaining）
  - G1 【视图】视图 从 "Grid" 改为 "List view"
  - G2 【保存生效】修改已持久保存生效

## 83ca4e3534e8ac387a90
- **题面：** Filter beauty products to only show items in the $1,000-$1,999.99 price range.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 beauty products
  - G2 【过滤条件】仅显示满足「items in the $1」的项
  - G3 【保存生效】修改已持久保存生效

## 84285dceb13440dc8f26
- **题面：** Filter the current Hunting & Fishing selection in Sports & Outdoors to prices from $0.00 to $999.99, preserving the category selection.
- **分支：** （源：remaining）
  - G1 【过滤条件】价格区间 $0.00 - $999.99,
  - G2 【保存生效】修改已持久保存生效

## 871bed938bede39f4d29
- **题面：** Find products with a price range between 10 USD and 50 USD.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 89357921faf097843f53
- **题面：** Search for products with SKU "12345-SONY".
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 8bb0cd7a3126d682e7b5
- **题面：** Filter the current Fan Shop selection in Sports & Outdoors to prices from $0.00 to $99.99, preserving the category selection.
- **分支：** （源：remaining）
  - G1 【过滤条件】价格区间 $0.00 - $99.99,
  - G2 【保存生效】修改已持久保存生效

## 9436e9940fc7f8b43550
- **题面：** Use Advanced Search to find products priced between $10 and $50.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Use Advanced Search to find products priced between $10 and $50.

## 94cae98980b91364bf2b
- **题面：** Browse electric toothbrushes in the Oral Care section
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## a24399e06061c3674e62
- **题面：** Sort products by price from highest to lowest.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 products
  - G2 【排序】按 price 排序（highest → lowest）
  - G3 【保存生效】修改已持久保存生效

## a2f03f1583074d0250e8
- **题面：** Change the sort order of Beauty & Personal Care products from Position to Price.
- **分支：** （源：remaining）
  - G1 【排序方式】排序方式 从 "Position" 改为 "Price"
  - G2 【保存生效】修改已持久保存生效

## a58a1e06c7d9109cf303
- **题面：** Search for camping equipment in the Sports & Outdoors category.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## ad90068395f62cad6cb1
- **题面：** Sort all products in the current Sports & Outdoors category selection by price from lowest to highest, preserving the category filter.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 all products in the current Sports & Outdoors category selection
  - G2 【排序】按 price 排序（lowest → highest）
  - G3 【保存生效】修改已持久保存生效

## ae527f0537ce15a26471
- **题面：** Use the search bar to search for products using the keyword "night vision".
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Use the search bar to search for products using the keyword "night vision".

## b6681418ebeeaac8dfee
- **题面：** Sort the Hunting & Fishing products in Sports & Outdoors by price from low to high.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 Hunting & Fishing products in Sports & Outdoors
  - G2 【排序】按 price 排序（low → high）
  - G3 【保存生效】修改已持久保存生效

## bbd68181dd3a0c692dbe
- **题面：** Use Advanced Search to find products whose Product Name contains 'vegan'. Finish on the submitted results page, including a genuine no-results page if none match.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Use Advanced Search to find products whose Product Name contains 'vegan'. Finish on the submitted results page, including a genuine no-results page if none match.

## bc7bb947b49ee1a3d89a
- **题面：** Use Advanced Search to find products whose Description contains ergonomic.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Use Advanced Search to find products whose Description contains ergonomic.

## cf46e00e24876cce6c83
- **题面：** Use Advanced Search to find products whose Product Name contains chocolate and whose Description contains vegan.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Use Advanced Search to find products whose Product Name contains chocolate and w

## d27b47d08e651fc5766d
- **题面：** Modify the current Advanced Search to show products whose Description contains vegan and whose price is below $20.
- **分支：** （源：remaining）
  - G1 【搜索条件】搜索条件改为：products whose Description contains vegan and whose price is below $20
  - G2 【保存生效】修改已持久保存生效

## d3be4453ebbb14ec814f
- **题面：** Change the product view from grid to list view
- **分支：** （源：remaining）
  - G1 【视图】视图 从 "grid" 改为 "list view"
  - G2 【保存生效】修改已持久保存生效

## d4d6b176770f22cacbf2
- **题面：** Change the number of products displayed per page from 12 to 24
- **分支：** （源：remaining）
  - G1 【数量】数量 从 "12" 改为 "24"
  - G2 【保存生效】修改已持久保存生效

## d9155fcc1af90b181c27
- **题面：** Sort the products in the current Sports & Outdoors category selection by Price, preserving the category filter.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 products in the current Sports & Outdoors category selection
  - G2 【排序】按 Price 排序
  - G3 【保存生效】修改已持久保存生效

## d9c3031179f049062a43
- **题面：** Use the search bar to search for products using the keyword "gingerbread".
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Use the search bar to search for products using the keyword "gingerbread".

## da37272ba36449b26bca
- **题面：** Search for products with the description containing "ergonomic".
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## e153a101f71ea9df9c9f
- **题面：** Use Advanced Search to find products whose Description contains "wireless headphones noise cancellation".
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Use Advanced Search to find products whose Description contains "wireless headphones noise cancellation".

## f3aefb178925a01bb41f
- **题面：** Find products with a price range between $40 and $100.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## f72f31528a25f7b15de8
- **题面：** Sort products by price in ascending order.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 products
  - G2 【排序】按 price 排序
  - G3 【保存生效】修改已持久保存生效

## 0cc0ce1a25187584f6a9
- **题面：** In the local training environment containing the Local Training Groups / Engineering / Platform hierarchy, expand one subgroup in the native group hierarchy and leave its nested subgroups visible.
- **分支：** （源：remaining）
  - G1 【退出成功】退出操作已成功执行

## 0d0d700ce8df59462367
- **题面：** Sign up for a new OpenStreetMap account Use the supplied local account details. Confirm the actual signup message in the local inbox and establish a signed-in session for this account.
- **分支：** （源：remaining）
  - G1 【注册】完成新账户注册并建立登录会话
  - G2 【保存生效】新建/添加已持久保存生效

## 47b21c596f7f9b16e223
- **题面：** Start mapping with OpenStreetMap by creating an account. Use the supplied local account details. Confirm the actual signup message in the local inbox and establish a signed-in session for this account.
- **分支：** （源：remaining）
  - G1 【创建账号】使用提供的本地账号信息创建并提交新账号
  - G2 【确认注册】在本地收件箱确认实际注册/签到消息
  - G3 【登录会话】为该账号建立已登录会话
  - G4 【保存生效】写操作已持久保存生效

## 7f0c020b34cad614f1e7
- **题面：** Start mapping by creating a new account Use the supplied local account details. Confirm the actual signup message in the local inbox and establish a signed-in session for this account.
- **分支：** （源：remaining）
  - G1 【创建账号】使用提供的本地账号信息创建并提交新账号
  - G2 【确认注册】在本地收件箱确认实际注册/签到消息
  - G3 【登录会话】为该账号建立已登录会话
  - G4 【保存生效】新建/添加已持久保存生效

## 979e35e58dd641b01939
- **题面：** Log in to your OpenStreetMap account. Use the supplied local account details. Establish a signed-in session for the supplied existing local account.
- **分支：** （源：remaining）
  - G1 【登录会话】使用提供的本地账号信息登录 OpenStreetMap 账号并建立已登录会话
  - G2 【保存生效】写操作已持久保存生效

## cfff6e696afc843c9afd
- **题面：** Create a new OpenStreetMap account. Use the supplied local account details. Confirm the actual signup message in the local inbox and establish a signed-in session for this account.
- **分支：** （源：remaining）
  - G1 【目标对象】新建/添加的对象与题面要求一致
  - G2 【保存生效】新建/添加已持久保存生效

## d8f8c5b3d5c96b09e1cc
- **题面：** Sign up to create a new user account on OpenStreetMap. Use the supplied local account details. Confirm the actual signup message in the local inbox and establish a signed-in session for this account.
- **分支：** （源：remaining）
  - G1 【注册】完成新账户注册并建立登录会话
  - G2 【保存生效】新建/添加已持久保存生效

## e76fc0395b3c4a40f372
- **题面：** Log in to your account Use the supplied local account details. Establish a signed-in session for the supplied existing local account.
- **分支：** （源：remaining）
  - G1 【登录会话】使用提供的本地账号信息登录 OpenStreetMap 账号并建立已登录会话
  - G2 【保存生效】写操作已持久保存生效

## 0dab6f8092988efb7a3c
- **题面：** Add the supplied public Ed25519 SSH key to your local GitLab profile with the title Skill Runtime Validation Key; confirm it is saved.
- **分支：** （源：remaining）
  - G1 【目标对象】新建/添加的对象与题面要求一致
  - G2 【保存生效】新建/添加已持久保存生效

## 7f7332f49e12acdf9e3a
- **题面：** View the commit for tag 1.5.0 in BoltsFramework/Bolts-ObjC.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：View the commit for tag 1.5.0 in BoltsFramework/Bolts-ObjC.

## ea5e0993b81190cf0080
- **题面：** Add a commit to byteblaze/a11y-syntax-highlighting with the explicitly supplied file, branch, content and commit message.
- **分支：** （源：remaining）
  - G1 【目标对象】新建/添加的对象与题面要求一致
  - G2 【保存生效】新建/添加已持久保存生效

## f8a210047a35bedcadaf
- **题面：** Update your GitLab full name to Skill Runtime Validation User.
- **分支：** （源：remaining）
  - G1 【全名】全名 改为 "Skill Runtime Validation User"
  - G2 【保存生效】修改已持久保存生效

## 1058c680a43778e2f8a8
- **题面：** View the Bestsellers report for All Websites from January 8, 2022 through May 31, 2023, grouped by Year. Find Quest Lumaflex Band (SKU 24-UG01), then open its product details in the catalog, change its Price to 21.00, save, and reopen to confirm the saved price.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 All Websites
  - G2 【价格】价格 改为 "21"
  - G3 【保存生效】修改已持久保存生效

## 12153c7b4fcd5f06d500
- **题面：** View comments on "Cindy Williams Dies: ‘Laverne & Shirley‘ Star Who Appeared In ’American Graffiti’ & ‘The Conversation’ Was 75"
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：View comments on "Cindy Williams Dies: ‘Laverne & Shirley‘ Star Who Appeared In 

## 150ec2edc02a2d017f74
- **题面：** For this local training variant, search for 'relationship advice' in the relationship_advice forum and leave an observed matching post open. A global search results page alone does not complete this task.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 25af25ca0b5d78e5fa97
- **题面：** Open the comments on the Music post titled "Fame and Flashdance singer Irene Cara has died aged 63".
- **分支：** （源：remaining）
  - G1 【发布成功】发布成功：目标为 titled Fame and Flashdance singer Irene Cara has died aged 63

## 3c6c45c952fa4e4d53b2
- **题面：** List all comments made in response to the post titled '20K IRS bill and no idea how to handle'. Return all visible comments, including nested replies, as answer.comments with id, author and rendered body strings. Omit removed placeholders; whitespace differences are ignored.
- **分支：** （源：remaining）
  - G1 【发布成功】发布成功：目标为 titled 20K IRS bill and no idea how to handle

## 3d9236ba8550175169a1
- **题面：** Read the joke titled "My girlfriend left me because of my abandonment issues..."
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Read the joke titled "My girlfriend left me because of my abandonment issues..."

## 7412760746270f91e8ef
- **题面：** For this local training variant, search for 'Spotify' in the Music forum and leave an observed matching post open. A global search results page alone does not complete this task.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## b4fda4d80141e46560da
- **题面：** View comments on the article about Brian May's knighthood.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：View comments on the article about Brian May's knighthood.

## c7651b6dd9bdb7e24569
- **题面：** Navigate to the comments section of the article "Cindy Williams Dies: ‘Laverne & Shirley‘ Star Who Appeared In ’American Graffiti’ & ‘The Conversation’ Was 75"
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Navigate to the comments section of the article "Cindy Williams Dies: ‘Laverne &

## e38f12f15bfdc08dbbda
- **题面：** Read the joke "My girlfriend left me because of my abandonment issues..."
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Read the joke "My girlfriend left me because of my abandonment issues..."

## f067aea97b5722ace128
- **题面：** For this local training variant, advance once from the original Recent comments page using its More link and leave the next page open.
- **分支：** （源：remaining）
  - G1 【退出成功】退出操作已成功执行

## f3a877e064b1a535c77c
- **题面：** View all comments on the joke "A priest and a nun in a desert cabin"
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：View all comments on the joke "A priest and a nun in a desert cabin"

## f7dcbdb404153368138d
- **题面：** For this local training variant, open the direct parent of the reply identified by public permalink /f/worldnews/51145/-/comment/731559 and leave that parent comment open.
- **分支：** （源：remaining）
  - G1 【回复成功】回复成功：目标为 identified by public permalink /f/worldnews/51145/-/comment/731559 and leave that parent comment open

## 12937f145767e7e679fb
- **题面：** Show the simulated device location (latitude 40.7830, longitude -73.9650, accuracy 25 metres) on the map while retaining the initially displayed car route from Central Park to Times Square. Leave the location marker and part of that same route visible on the map. This is a local training variant with a supplied simulated location, not the original device location.
- **分支：** （源：remaining）
  - G1 【退出成功】退出操作已成功执行

## 12be1e4f468ffdfe78d9
- **题面：** Create a short link to share the route from Central Park to Times Square.
- **分支：** （源：remaining）
  - G1 【分享成功】分享成功：目标为 route from Central Park to Times Square

## 139b90645b5eb09484b8
- **题面：** List all forum names available on this local platform.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：List all forum names available on this local platform.

## bde3ee9750cca4844f82
- **题面：** In the movies forum, show the Top posts from the past year and finish on the native filtered list, including a genuine empty historical window.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：In the movies forum, show the Top posts from the past year and finish on the native filtered list, including a genuine empty historical window.

## 13a8e735f2d8b42d9a16
- **题面：** Subscribe the attempt-local client to the native Tags Atom feed for The A11Y Project (a11yproject/a11yproject.com). Keep the subscription active with at least two successful fetches persisted in this attempt. Opening the feed or copying its URL alone does not complete the task.
- **分支：** （源：remaining）
  - G1 【订阅成功】订阅操作已成功执行

## 13b14991580859199ca4
- **题面：** Download a PNG of the initially displayed driving route from Central Park (40.7830, -73.9650) to Times Square (40.7570, -73.9860), including the route line. Keep the initial map position and zoom, and use the default image-export area and scale.
- **分支：** （源：remaining）
  - G1 【下载成功】下载成功：目标为 a PNG of the initially displayed driving route from Central Park (40

## 79155a4aa91a6199bd88
- **题面：** Download a PNG of the New York City map initially shown. Keep the initial map position and zoom, and use the default image-export area and scale.
- **分支：** （源：remaining）
  - G1 【下载成功】下载成功：目标为 a PNG of the New York City map initially shown

## 7d7dfe535b3ae8650a4e
- **题面：** Read the initial image-export scale for the current Standard map. Set the image-export scale to twice that initial value and download a PNG, keeping the default export area unchanged.
- **分支：** （源：remaining）
  - G1 【导出比例】导出比例 改为 "twice that initial value"
  - G2 【保存生效】修改已持久保存生效

## 17f4635eafc9cc9b3175
- **题面：** Submit a new post in the "AskReddit" forum
- **分支：** （源：remaining）
  - G1 【提交成功】提交成功：目标为 a new post in the AskReddit forum

## 37683e689f427c0cae71
- **题面：** Submit a new post to the movies forum
- **分支：** （源：remaining）
  - G1 【提交成功】提交成功：目标为 a new post to the movies forum

## 5848a4067b142743ef04
- **题面：** Create one visible submission in Music with title "Local music reference" and the exact URL "https://www.youtube.com/watch?v=dQw4w9WgXcQ&training_source=5848a4067b142743ef04". Store the URL as data; do not open or verify the external destination.
- **分支：** （源：remaining）
  - G1 【标题】标题精确为 "Local music reference"
  - G2 【保存生效】新建/添加已持久保存生效

## 654771ab0c2f25b8a84c
- **题面：** Submit a new post to any existing forum of your choice.
- **分支：** （源：remaining）
  - G1 【提交成功】提交成功：目标为 a new post to any existing forum of your choice

## 7c80b077b56f9f3f5a0e
- **题面：** Create a submission with the URL "https://example.com" and title "Example Website Review"
- **分支：** （源：remaining）
  - G1 【标题】标题精确为 "Example Website Review"
  - G2 【保存生效】新建/添加已持久保存生效

## b05900811e468751caa1
- **题面：** Create a new post in the AskReddit forum.
- **分支：** （源：remaining）
  - G1 【发布成功】发布成功：目标为 in the AskReddit forum

## b55d47b1a195729a91a0
- **题面：** Submit a new post to a forum
- **分支：** （源：remaining）
  - G1 【提交成功】提交成功：目标为 a new post to a forum

## de4c5a6533c2184a1ecd
- **题面：** Submit new content.
- **分支：** （源：remaining）
  - G1 【提交成功】提交成功：目标为 new content

## f2e8d455b5814c280d7f
- **题面：** Submit a new post
- **分支：** （源：remaining）
  - G1 【提交成功】提交成功：目标为 a new post

## 18bb8f41188fd7da8001
- **题面：** For this local task, change the map by enabling either Map Notes or Map Data. These are the two supported overlays for this task; other base-map styles are outside its local scope. The chosen overlay must actually be active. A successfully loaded empty overlay is acceptable. The Layers panel may be open or closed when you finish.
- **分支：** （源：remaining）
  - G1 【变更字段】变更 map by enabling either Map Notes or Map Data
  - G2 【保存生效】修改已持久保存生效

## 1c5c6925760778e6bbb5
- **题面：** For this local task, change the map by enabling either Map Notes or Map Data. These are the two supported overlays for this task; other base-map styles are outside its local scope. The chosen overlay must actually be active. A successfully loaded empty overlay is acceptable. The Layers panel may be open or closed when you finish.
- **分支：** （源：remaining）
  - G1 【变更字段】变更 map by enabling either Map Notes or Map Data
  - G2 【保存生效】修改已持久保存生效

## 4791902089d0ca6ecab7
- **题面：** For this local task, change the map by enabling either Map Notes or Map Data. These are the two supported overlays for this task; other base-map styles are outside its local scope. The chosen overlay must actually be active. A successfully loaded empty overlay is acceptable. The Layers panel may be open or closed when you finish. Keep the original map area in view.
- **分支：** （源：remaining）
  - G1 【变更字段】变更 map by enabling either Map Notes or Map Data
  - G2 【保存生效】修改已持久保存生效

## 57941f7d5cbd99c5acd8
- **题面：** For this local task, change the map by enabling either Map Notes or Map Data. These are the two supported overlays for this task; other base-map styles are outside its local scope. The chosen overlay must actually be active. A successfully loaded empty overlay is acceptable. The Layers panel may be open or closed when you finish.
- **分支：** （源：remaining）
  - G1 【变更字段】变更 map by enabling either Map Notes or Map Data
  - G2 【保存生效】修改已持久保存生效

## 6791c6f3e4b6b6963094
- **题面：** For this local task, change the map by enabling either Map Notes or Map Data. These are the two supported overlays for this task; other base-map styles are outside its local scope. The chosen overlay must actually be active. A successfully loaded empty overlay is acceptable. The Layers panel may be open or closed when you finish.
- **分支：** （源：remaining）
  - G1 【变更字段】变更 map by enabling either Map Notes or Map Data
  - G2 【保存生效】修改已持久保存生效

## ef2552bf69bb38768b61
- **题面：** For this local task, change the map by enabling either Map Notes or Map Data. These are the two supported overlays for this task; other base-map styles are outside its local scope. The chosen overlay must actually be active. A successfully loaded empty overlay is acceptable. The Layers panel may be open or closed when you finish.
- **分支：** （源：remaining）
  - G1 【变更字段】变更 map by enabling either Map Notes or Map Data
  - G2 【保存生效】修改已持久保存生效

## 19f082255560da530586
- **题面：** View the native Ordered Quantity report for Fitness Tracker Pro (SKU LMTX-FITNESS-TRACKER-PRO), from January 8, 2022 through May 31, 2023, across All Websites. Report the total ordered quantity for this product over the date range. A normally completed query with zero ordered quantity is acceptable. Return a JSON answer with the single numeric field ordered_quantity.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：View the native Ordered Quantity report for Fitness Tracker Pro (SKU LMTX-FITNES

## 1af77c6d697fa92372fe
- **题面：** Filter the non-archived Explore project collection by the native accessibility topic.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 non-archived Explore project collection
  - G2 【过滤条件】按「the native accessibility topic」过滤
  - G3 【保存生效】修改已持久保存生效

## d2358c64e425307b24c9
- **题面：** Filter the non-archived Explore project collection by the native python topic.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 non-archived Explore project collection
  - G2 【过滤条件】按「the native python topic」过滤
  - G3 【保存生效】修改已持久保存生效

## 1ca5882ecd999718991f
- **题面：** Navigate to the History page for New York on OpenStreetMap. For this deterministic local training interpretation, New York means New York City according to the declared native geographic identity. Display the actually loaded native History list for that map view; a genuinely empty native list is valid. Original goals, starts, traces and scores remain unchanged and benchmark equivalence is not claimed.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Navigate to the History page for New York on OpenStreetMap. For this determinist

## 1e23d47d9fec468a69af
- **题面：** Access the user profile for MarvelsGrantMan136 to view profile details and settings.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Access the user profile for MarvelsGrantMan136 to view profile details and setti

## 4da98402a7c911b92bf5
- **题面：** View all submissions from the user GetFreeCash
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：View all submissions from the user GetFreeCash

## 7ca64f8fd24f1c44b1e0
- **题面：** Find the publicly displayed imported user identifier on your current Postmill profile.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 7f4d0c8336d1f5ca13c2
- **题面：** Sort search results by relevance
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 search results
  - G2 【排序】按 relevance 排序
  - G3 【保存生效】修改已持久保存生效

## a1571f24de03ba500122
- **题面：** Find all native forum names containing "technology" in the alphabetical forum directory.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## ad3e7b8c5db5c98fbc57
- **题面：** Access your user profile and settings.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Access your user profile and settings.

## b338a9437cf64163e2de
- **题面：** Click on your username to access account settings
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Click on your username to access account settings

## d31e7a310521d6a06bb4
- **题面：** List all native posts from nosleep among the current search results for "song describes your love life".
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：List all native posts from nosleep among the current search results for "song de

## ea715e77fdd3e9634de8
- **题面：** Find one native forum name containing "gaming" in the alphabetical forum directory.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## fe6c98831b4ff7148245
- **题面：** Find all native posts from the movies forum matching the native text search "Spider-Verse".
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 1fbea782181c1363ac1e
- **题面：** Display the store's native product comparison table containing both the JSY Foldable Bath Body Brush and the BODY Exfoliating Washcloth Mitt. A written comparison or recommendation is not required.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Display the store's native product comparison table containing both the JSY Foldable Bath Body Brush and the BODY Exfoliating Washcloth Mitt. A written comparison or recommendation is not required.

## 21482bd3a34a1ca47051
- **题面：** Compare the native car, bicycle and walking travel times from Miami, Florida to Orlando, Florida. Return JSON with car_minutes, bicycle_minutes and walking_minutes, each an integer total number of minutes converted from the corresponding displayed hours:minutes summary. Use the displayed rounded times. Observe all three routes and leave one of them displayed when answering.
- **分支：** （源：remaining）
  - G1 【退出成功】退出操作已成功执行

## 222f40ea91b82d9ee829
- **题面：** Get walking directions from New York, NY to Brooklyn. This is an explicit local training derivative with different named geography. The original goal "Get walking directions from New York, NY to Washington, DC.", all original starts and traces, and all old scores remain unchanged. It does not claim equivalence to the original geographical task or its benchmark result.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Get walking directions from New York, NY to Brooklyn. This is an explicit local training derivative with different named geography. The original goal "Get walking directions from New York, NY to Washington, DC.", all original starts and traces, and all old scores remain unchanged. It does not claim equivalence to the original geographical task or its benchmark result.

## 2c6f66ba2ced531479b3
- **题面：** Compare travel times between car and bicycle routes from Lower Manhattan to Brooklyn. This is an explicit local training derivative with different named geography. The original goal "Compare travel times between car and bicycle routes from Lower Manhattan to Upper Manhattan", all original starts and traces, and all old scores remain unchanged. It does not claim equivalence to the original geographical task or its benchmark result.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Compare travel times between car and bicycle routes from Lower Manhattan to Brooklyn. This is an explicit local training derivative with different named geography. The original goal "Compare travel times between car and bicycle routes from Lower Manhattan to Upper Manhattan", all original starts and traces, and all old scores remain unchanged. It does not claim equivalence to the original geographical task or its benchmark result.

## 3c6d47f5168b57cf1250
- **题面：** Reverse the explicitly initialized current driving directions from Brooklyn to New York, NY. The resulting route must run from New York, NY to Brooklyn, retaining car mode. This is an explicit local training derivative with different named geography. The original goal "Reverse the current directions from Washington, DC to New York, NY.", all original starts and traces, and all old scores remain unchanged. It does not claim equivalence to the original geographical task or its benchmark result.
- **分支：** （源：remaining）
  - G1 【反转】反转 explicitly initialized current driving directions
  - G2 【保存生效】新建/添加已持久保存生效

## 24334e2ab58fffd2515a
- **题面：** Starting from the GPS traces page, open the map and enable the Public GPS Traces overlay. A correctly enabled and normally loaded layer is sufficient even when no traces exist in the view. Keep the map visible; a checkbox alone or failed resource loading does not complete the task.
- **分支：** （源：remaining）
  - G1 【启用】启用 Public GPS Traces overlay
  - G2 【保存生效】修改已持久保存生效

## 26f8e95fe16198967645
- **题面：** Enable the Public GPS Traces overlay for the initial map area. Wait until recorded GPS tracks are visible, keeping the initial zoom and geographic area.
- **分支：** （源：remaining）
  - G1 【启用】启用 Public GPS Traces overlay
  - G2 【保存生效】修改已持久保存生效

## c1f18d322db1b02b3ad9
- **题面：** Enable the Public GPS Traces overlay for the initial map area. Wait until recorded GPS tracks are visible, keeping the initial zoom and geographic area.
- **分支：** （源：remaining）
  - G1 【启用】启用 Public GPS Traces overlay
  - G2 【保存生效】修改已持久保存生效

## ca7b5f868b986c10ac53
- **题面：** Enable the Public GPS Traces overlay for the initial map area. Wait until recorded GPS tracks are visible, keeping the initial zoom and geographic area.
- **分支：** （源：remaining）
  - G1 【启用】启用 Public GPS Traces overlay
  - G2 【保存生效】修改已持久保存生效

## 25b2d52fa26d1437a963
- **题面：** For this local training variant, display the native bicycle route from Rochester, New York to Syracuse, New York. This variant does not assert a global fastest-route optimum.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：For this local training variant, display the native bicycle route from Rochester, New York to Syracuse, New York. This variant does not assert a global fastest-route optimum.

## 2dd27c427c710971abff
- **题面：** Return a local link that reopens the initially displayed walking directions with the same ordered endpoints and walking mode. No external delivery is requested. Return a JSON object with exactly one string field, share_link, containing the complete local directions URL.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Return a local link that reopens the initially displayed walking directions with the same ordered endpoints and walking mode. No external delivery is requested. Return a JSON object with exactly one string field, share_link, containing the complete local directions URL.

## 35cc8f7f2a4d20c391d6
- **题面：** Change the destination of the route to Rockefeller Center. Initially the driving route runs from Central Park (40.7830, -73.9650) to Times Square (40.7570, -73.9860). Preserve the origin and driving mode while replacing the destination.
- **分支：** （源：remaining）
  - G1 【目的地】目的地 改为 "Rockefeller Center"
  - G2 【保存生效】修改已持久保存生效

## 412ffda8ee79901c387b
- **题面：** For this local training variant, find the native walking route from latitude 40.748, longitude -73.986 to latitude 40.753, longitude -73.977. Report its displayed distance as JSON with distance_value (number) and distance_unit ("m" or "km"). Equivalent conversion between metres and kilometres is accepted. A globally shortest route is not required. Leave the requested route displayed when answering.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 5f380f4afe1533d2afa7
- **题面：** Find the fastest route from Manhattan to Brooklyn by car Compare the complete alternatives returned by the local routing backend for the specified mode; choose the minimum travel time. This is a backend-relative optimum, not a global optimality claim.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 848a2bf72ed1fef896df
- **题面：** Find the numbered highways traversed by the native car route from Buffalo, New York to Rochester, New York. Return JSON with highway_refs containing the complete unique set of numbered road references used by that route and shown in its instructions. Exclude highways mentioned only as exit-sign destinations. Leave the requested route displayed when answering.
- **分支：** （源：remaining）
  - G1 【目标对象】新建/添加的对象与题面要求一致
  - G2 【保存生效】新建/添加已持久保存生效

## be0443471ca4fb25bef5
- **题面：** For this local training variant, find the numbered highways traversed by the native car route from New York City to Boston, Massachusetts. Return JSON with highway_refs containing the complete unique set of numbered road references used by that route and shown in its instructions. Exclude highways mentioned only as exit-sign destinations. Leave the requested route displayed when answering.
- **分支：** （源：remaining）
  - G1 【目标对象】新建/添加的对象与题面要求一致
  - G2 【保存生效】新建/添加已持久保存生效

## c4a65a289c86d73f8ac1
- **题面：** Find the shortest walking route from Times Square to Central Park Compare the complete alternatives returned by the local routing backend for the specified mode; choose the minimum route distance. This is a backend-relative optimum, not a global optimality claim.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## d1405a70bb34f5ce1f9b
- **题面：** For this local training variant, find the native car directions from Boston, Massachusetts to New York City, then return a local link that reopens those directions with the same ordered endpoints and car mode. No external delivery is requested. Return a JSON object with exactly one string field, share_link, containing the complete local directions URL.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## da41011ce8317ef81100
- **题面：** Show the driving route from New York City to Boston and list every distinct numbered Interstate, U.S., or state highway reference actually travelled on that route. Exclude highways named only as exit-sign destinations. Return highway_refs as a JSON array of strings.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Show the driving route from New York City to Boston and list every distinct numbered Interstate, U.S., or state highway reference actually travelled on that route. Exclude highways named only as exit-sign destinations. Return highway_refs as a JSON array of strings.

## df0823b879f1acb244a8
- **题面：** Print the complete turn-by-turn driving directions from New York City to Boston as a PDF.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Print the complete turn-by-turn driving directions from New York City to Boston as a PDF.

## 26e527b2b15f6fceef71
- **题面：** Open the native Wiki pages directory.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Open the native Wiki pages directory.

## 308ad0b8cb7d8b96b000
- **题面：** Open the Wiki All pages directory to view the list of wiki pages.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Open the Wiki All pages directory to view the list of wiki pages.

## 43e95bdc9b6777a912ab
- **题面：** View a specific post about Oscar nominations
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：View a specific post about Oscar nominations

## 5d65c9edd559c414d897
- **题面：** Open the native Wiki pages directory to view the available community pages.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Open the native Wiki pages directory to view the available community pages.

## 8676465b5f948cda1234
- **题面：** Open the native Wiki pages directory to view the available documentation pages.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Open the native Wiki pages directory to view the available documentation pages.

## 9bc0d01e22920707c86f
- **题面：** Open the Wiki All pages directory to view the list of wiki pages.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Open the Wiki All pages directory to view the list of wiki pages.

## b5e9b8165dfe29bf69ef
- **题面：** Open the Wiki All pages directory to view the list of wiki pages.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Open the Wiki All pages directory to view the list of wiki pages.

## c2a9fdd91f1129199c8c
- **题面：** Determine which user or users have submitted the most visible posts in the movies forum.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Determine which user or users have submitted the most visible posts in the movies forum.

## dc0ecc826d701c6878a5
- **题面：** Determine a forum tied for the most native search results for "bleaching your butthole", counting both post and comment results in the complete native search scope.
- **分支：** （源：remaining）
  - G1 【发布成功】发布成功：目标为 and comment results in the complete native search scope

## de8ff61707f99225b9de
- **题面：** Open the native Wiki pages directory to view the available pages.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Open the native Wiki pages directory to view the available pages.

## 2707dc9a5606556484fd
- **题面：** Clone byteblaze/a11y-syntax-highlighting from its observed native local HTTP URL into this attempt's local workspace, preserving all branches and tags with a clean checked-out repository.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 byteblaze/a11y-syntax-highlighting
  - G2 【克隆】克隆仓库 byteblaze/a11y-syntax-highlighting 到本地工作区（保留所有分支与标签）
  - G3 【保存生效】新建/添加已持久保存生效

## 3b6eaf481e19d340f6e1
- **题面：** Subscribe to your native global Dashboard issues calendar using this attempt's local calendar client, and successfully refresh the active subscription.
- **分支：** （源：remaining）
  - G1 【订阅成功】订阅成功：目标为 your native global Dashboard issues calendar using this attempts local calendar client, and successfully refresh the active subscription

## 5160caa52e98c417c23c
- **题面：** Clone the a11yproject/a11yproject.com repository into the local workspace. Completion requires a usable local Git working tree; returning a clone command is insufficient.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 a11yproject/a11yproject.com
  - G2 【克隆】克隆仓库 a11yproject/a11yproject.com 到本地工作区
  - G3 【保存生效】新建/添加已持久保存生效

## 5c26df4516e2a5a405f5
- **题面：** Subscribe in the local feed reader to open merge requests in a11yproject/a11yproject.com. The saved subscription must fetch the native feed successfully; opening or returning a URL alone is insufficient.
- **分支：** （源：remaining）
  - G1 【订阅成功】订阅操作已成功执行

## 2a9b4bf76c50cbb8a51c
- **题面：** Find out where you are on the map using Where is this? The location referent is the actual original native map center; device geolocation is not part of this local protocol.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 60b46c5edd539496a9de
- **题面：** Share a link to a map of Manhattan with someone
- **分支：** （源：remaining）
  - G1 【分享成功】分享成功：目标为 a link to a map of Manhattan with someone

## 749c6228af8e9b39790d
- **题面：** Pan the map to view a different area
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Pan the map to view a different area

## 95355b340743a003ec8c
- **题面：** Search for New York, NY and view this geographical place on the native map. This is an explicit local training derivative with different named geography. The original goal "Search for Washington DC and view it on the map.", all original starts and traces, and all old scores remain unchanged. It does not claim equivalence to the original geographical task or its benchmark result. For this local protocol, New York, NY means the geographical place described by {"names": ["New York", "New York City", "City of New York"], "state": ["New York"], "country_code": "us"}.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 9abe8b18926aa9aa6e96
- **题面：** Share the New York City map view as a geo URI
- **分支：** （源：remaining）
  - G1 【分享成功】分享成功：目标为 New York City map view as a geo URI

## 2bf72a482e22f2c8118f
- **题面：** Search for a location using the search bar.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## b426ce66fac7cab70638
- **题面：** Search for a location on OpenStreetMap using the search box.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## c4c3ed65dbc5ae07b18d
- **题面：** Share a link to this New York City map view
- **分支：** （源：remaining）
  - G1 【分享成功】分享成功：目标为 a link to this New York City map view

## 2d08c1408e0e1d7061ac
- **题面：** Create one visible submission in technology with title "Local technology reference" and the exact URL "https://techcrunch.com/2023/03/23/openai-announces-plugins-for-chatgpt/?training_source=2d08c1408e0e1d7061ac". Store the URL as data; do not open or verify the external destination.
- **分支：** （源：remaining）
  - G1 【标题】标题精确为 "Local technology reference"
  - G2 【保存生效】新建/添加已持久保存生效

## 2d9ace4d49f56609bd6a
- **题面：** Enable notifications on mentions for user MarvelsGrantMan136.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 MarvelsGrantMan
  - G2 【启用】启用 notifications on mentions
  - G3 【保存生效】修改已持久保存生效

## fd524ecb23918d90ea8c
- **题面：** Find posts related to songs that describe love life. Complete on the native matching search-results page, or by opening a matching post shown in those observed results. This training task uses the website's lexical search for "song describes your love life".
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 2feb3ccb518b1e7b160b
- **题面：** Create a forum with these exact fields: {"name": "GamersUnite", "title": "GamersUnite", "description": "Discuss video games.", "sidebar": "Discuss video games respectfully."}.
- **分支：** （源：remaining）
  - G1 【目标对象】新建/添加的对象与题面要求一致
  - G2 【保存生效】新建/添加已持久保存生效

## 30502ede94547d51e806
- **题面：** View your current location on the map
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：View your current location on the map

## 35b12298d937ee87365e
- **题面：** Change the zoom level of the map
- **分支：** （源：remaining）
  - G1 【变更字段】变更 zoom level of the map
  - G2 【保存生效】修改已持久保存生效

## 3bba7df63976545b6817
- **题面：** Show my current location on the map
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Show my current location on the map

## 3d700781c92bf2a295f6
- **题面：** Click "Show My Location" to find the current location on the map.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Click "Show My Location" to find the current location on the map.

## 4d1f5dd10e9928c68270
- **题面：** Find your current location on the map.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 4f2531fa54962c4e2925
- **题面：** Use the Show My Location feature to center the map on the user's current location.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Use the Show My Location feature to center the map on the user's current locatio

## 55d6a62becc3cdece8e2
- **题面：** Use the Show My Location button to center the map on the user's current location.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Use the Show My Location button to center the map on the user's current location

## 6320c4fde077a871f08c
- **题面：** Zoom in on the map to see more street details.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Zoom in on the map to see more street details.

## 6e964973c6fb24e47b00
- **题面：** Zoom in to get a closer view of the current map area
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Zoom in to get a closer view of the current map area

## 77d1b1546b4ceb7682ef
- **题面：** Zoom out on the map.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Zoom out on the map.

## 79e826b91a60ce20b95a
- **题面：** Show my current location on the map.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Show my current location on the map.

## 892b510e321e1c69db3d
- **题面：** Zoom in on the map view.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Zoom in on the map view.

## b4ae7a1b1fb155daccf2
- **题面：** Zoom in to get a closer view of the map
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Zoom in to get a closer view of the map

## f6a7b2874a4d4b806801
- **题面：** Use the "Zoom In" feature to get a closer view of the map.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Use the "Zoom In" feature to get a closer view of the map.

## 313888e5558df451129e
- **题面：** Inspect the installed GitLab blank-project form, then describe the process of creating a private blank project as an ordered JSON steps array using the actual native UI labels. Include checking the Project URL namespace; it may be fixed for the current account. Use one object per declared operation, with exactly operation and ui_label as string fields. Field setup operations may appear in any valid order. Describe the process without creating a project.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Inspect the installed GitLab blank-project form, then describe the process of creating a private blank project as an ordered JSON steps array using the actual native UI labels. Include checking the Project URL namespace; it may be fixed for the current account. Use one object per declared operation, with exactly operation and ui_label as string fields. Field setup operations may appear in any valid order. Describe the process without creating a project.

## 3163cfbe4a2f0114b45f
- **题面：** For this local training variant, download a PNG of the Standard map centered on the native Brooklyn, New York search result at zoom level 15, with its native object details panel open. Keep the center obtained by fitting the native object boundary. Use the full extent offered when the native Share panel opens from that view, and an export scale of 1:25000, with no route line. The downloaded image must depict that view. This specifies a local detailed view, not the entire borough.
- **分支：** （源：remaining）
  - G1 【下载成功】下载成功：目标为 panel opens from that view, and an export scale of 1:25000, with no route line

## 50e038cdc546bacdd1b0
- **题面：** For this local training variant, download a PNG of the initial walking-directions map view on the Standard map layer, using the full extent and default export scale offered when the native Share panel opens from that initial view. The initially displayed walking route may be included or omitted; if included it must be that route. Preserve the view after native route initialization, not an earlier uninitialized URL center.
- **分支：** （源：remaining）
  - G1 【下载成功】下载成功：目标为 panel opens from that initial view

## 78e26845a858ef34bdc1
- **题面：** For this local training variant, identify the native geographic object returned for the center of the initial map view. Leave that native result visible. Return a JSON object containing exactly name (the complete displayed result label), latitude and longitude (the result object coordinates, in decimal degrees, accurate to 0.000001 degree). This identifies the center object, not the area of the entire viewport.
- **分支：** （源：remaining）
  - G1 【退出成功】退出操作已成功执行

## 983144dddd4cfc891d65
- **题面：** For this local training variant, inspect the initially displayed driving route and report all native numbered instructions whose maneuver occurs at the intersection of Broadway and West 86th Street in Manhattan, New York. Return a JSON object with exactly instructions, an ordered list of objects containing number (integer) and instruction (the complete instruction-cell text, including its displayed number and excluding the separate distance column). Return an empty list if this route has no maneuver instruction at that intersection. Keep the original route displayed; a nearby turn is not an instruction at the intersection.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：For this local training variant, inspect the initially displayed driving route and report all native numbered instructions whose maneuver occurs at the intersection of Broadway and West 86th Street in Manhattan, New York. Return a JSON object with exactly instructions, an ordered list of objects containing number (integer) and instruction (the complete instruction-cell text, including its displayed number and excluding the separate distance column). Return an empty list if this route has no maneuver instruction at that intersection. Keep the original route displayed; a nearby turn is not an instruction at the intersection.

## cb231ede0a39966a8e72
- **题面：** For this local training variant, show a map view centered inside Manhattan, New York, at zoom level 17 on the Standard map layer. The visible map must have loaded. This checks a detailed local view, not coverage of the entire borough.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：For this local training variant, show a map view centered inside Manhattan, New York, at zoom level 17 on the Standard map layer. The visible map must have loaded. This checks a detailed local view, not coverage of the entire borough.

## 3344a251f4a5c00fc936
- **题面：** Set the Eugen / tutorials project notification level to Watch and save it. Actual external email delivery is outside this local task.
- **分支：** （源：remaining）
  - G1 【通知级别】通知级别 改为 "Watch"
  - G2 【保存生效】修改已持久保存生效

## 55dba75bfc3c800b5fa3
- **题面：** Upload the provided local-training-upload.txt fixture to the default branch of byteblaze/a11y-syntax-highlighting, preserving its filename and bytes, and commit it.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 provided local-training-upload.txt fixture
  - G2 【上传】上传 provided local-training-upload.txt fixture 到 default branch of byteblaze/a11y-syntax-highlighting
  - G3 【保存生效】新建/添加已持久保存生效

## 5fbcf6276c5efe5c9c89
- **题面：** Change byteblaze/a11y-syntax-highlighting project visibility to Private and save it.
- **分支：** （源：remaining）
  - G1 【可见性】可见性为 Private
  - G2 【保存生效】修改已持久保存生效

## b328e1258a7e8ca6b262
- **题面：** Create local-training-directory in the default branch of byteblaze/a11y-syntax-highlighting, containing an empty .gitkeep file, and commit it.
- **分支：** （源：remaining）
  - G1 【目标对象】新建/添加的对象与题面要求一致
  - G2 【保存生效】新建/添加已持久保存生效

## cbcb6695f0797d376657
- **题面：** In byteblaze/cloud-to-butt on its default branch, replace every case-sensitive literal butt with rear in content_script.js and commit the change, leaving all other files unchanged.
- **分支：** （源：remaining）
  - G1 【替换】将 case-sensitive literal butt 替换为 rear
  - G2 【保存生效】修改已持久保存生效

## 35984f23d32598fe54dd
- **题面：** On the local test map, sign in with email local-map-editor@example.test and password LocalMapEditor-2026!. Edit node 666, Hell's Kitchen in New York (40.7644228, -73.9923918). Set its note tag to "Local training map review completed". Save the edit and reopen the same node to confirm the note is saved. Keep its other tags and position unchanged.
- **分支：** （源：remaining）
  - G1 【note tag】note tag 改为 "Local training map review completed"
  - G2 【保存生效】新建/添加已持久保存生效

## 365ab69eff6f3f588608
- **题面：** Submit a new post.
- **分支：** （源：remaining）
  - G1 【提交成功】提交成功：目标为 a new post

## 3b09aec673d3fa39e691
- **题面：** Navigate to the Wiki page
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Navigate to the Wiki page

## 40201e06fff3f37ffd8e
- **题面：** Search local posts for site rules; finish on the matching results or a matching post opened from those results.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 40cd6ea96d1b834eddfc
- **题面：** Browse user diary entries related to New York City. This local test website contains explicitly synthetic New York City and Boston diary entries. Display a New York City entry in the diary list or its detail page.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## cb16efd063fc41a3f9d5
- **题面：** Subscribe to the OpenStreetMap public GPS traces RSS feed in the provided local reader and reopen the reader to confirm the saved subscription. The local reader is available at /__lab_local__/reader. A valid feed with no entries is acceptable; future delivery is not required.
- **分支：** （源：remaining）
  - G1 【订阅成功】订阅成功：目标为 OpenStreetMap public GPS traces RSS feed in the provided local reader and reopen the reader to confirm the saved subscription

## f4e78317c35308b7e404
- **题面：** Log in using the supplied existing local test account training-mapper-v183@example.test (display name Training Mapper V183), password TrainingMapper-LocalOnly-2026. Create and save a diary entry titled "Training mapping diary v183" with body "Today I explored the public map and learned how to inspect map features. This is a local training diary entry.". Reopen it and verify its author, title and body.
- **分支：** （源：remaining）
  - G1 【重新打开成功】重新打开成功：目标为 it and verify its author, title and body

## 4342bb4781ecf250ddc5
- **题面：** Sign out of the current account, then sign in with the supplied different active seeded account. Both sign-out and actual second-account authentication are required.
- **分支：** （源：remaining）
  - G1 【登出成功】登出成功：目标为 the current account, then sign in with the supplied different active seeded account

## 46942c22ff0d5b115b3f
- **题面：** Subscribe the current task account to the Music forum RSS updates in the deterministic local RSS client; confirm the saved subscription and its initial feed receipt.
- **分支：** （源：remaining）
  - G1 【订阅成功】订阅操作已成功执行

## 84e24b8091debb890843
- **题面：** Open the local movies discussion post titled "Who will win the Oscar for FILM EDITING?" and finish on that post. External polls are outside this task.
- **分支：** （源：remaining）
  - G1 【发布成功】发布成功：目标为 titled Who will win the Oscar for FILM EDITING? and finish on that post

## b0574531e2fea15edb44
- **题面：** Search the local posts and comments for "Nosferatu Robert Eggers remake" and finish on the native results page, including a genuine empty result set. Do not query external movie sites.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## f36fe82d6f84b000e8e2
- **题面：** Search the local Wiki page titles and bodies for "guide" and finish on the complete Wiki results page, including a genuine empty result set.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 4a0ecbc7a6eade52d711
- **题面：** Read the dark-mode support announcement in src/announcements/dark-mode-support.md on the main branch of the a11yproject/a11yproject.com repository.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /a11yproject/a11yproject.com/-/blob/main/src/announcements/dark-mode-support.md

## 6acd8cce13dbbe3f27d1
- **题面：** View all public projects in the GitLab instance
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /explore
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Projects · Explore · GitLab$

## 74435bed863fe2349c03
- **题面：** Check Issue #1 in the a11y-syntax-highlighting project.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/a11y-syntax-highlighting/-/issues/1
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Tm\ Theme\ Editor$

## 929196f0dee835334fef
- **题面：** Navigate to the Bootstrap project repository.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /twbs/bootstrap
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^bootstrap$

## 4df3d8c744ae3dfcd677
- **题面：** Find directions between two locations on the map.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 5e14b1ec816996910464
- **题面：** Reverse the direction of your planned route from Manhattan to Brooklyn
- **分支：** （源：remaining）
  - G1 【反转】反转 direction of your planned route
  - G2 【保存生效】修改已持久保存生效

## 954063137200c0af2656
- **题面：** Set New York, NY as the destination in the native direction-search To field. This explicit local training derivative preserves the destination-field operation and its complete native named-place existence check. It replaces the original destination with the publicly named New York, NY. The original goal "Set Miami as the destination for your journey", all original starts and traces, and all old scores remain unchanged. It does not claim equivalence to the original destination task. Route completion is not required.
- **分支：** （源：remaining）
  - G1 【目标对象】新建/添加的对象与题面要求一致
  - G2 【保存生效】新建/添加已持久保存生效

## 9d336e827a8427042062
- **题面：** Find directions between two points
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## ad6bc5ac97e88c745ee5
- **题面：** Get driving directions from Manhattan to Brooklyn.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Get driving directions from Manhattan to Brooklyn.

## ae08c270853d3ed2d361
- **题面：** Enter custom coordinates for a starting point and destination to get specific directions between those exact points.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Enter custom coordinates for a starting point and destination to get specific di

## af40bb0f257951e66f0d
- **题面：** Reverse the direction to get directions from Rochester to Buffalo
- **分支：** （源：remaining）
  - G1 【反转】反转 direction
  - G2 【保存生效】修改已持久保存生效

## b82dcc8454fc561f50cd
- **题面：** Input a custom location in the "To" field for direction search.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Input a custom location in the "To" field for direction search.

## c4b2026fb964179f11b8
- **题面：** Get driving directions from New York City to Boston. Identify all numbered segments tied for the largest distance displayed in the turn-by-turn list. Compare displayed metres and kilometres in common units.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Get driving directions from New York City to Boston. Identify all numbered segments tied for the largest distance displayed in the turn-by-turn list. Compare displayed metres and kilometres in common units.

## ca7f085d2b110016afc9
- **题面：** Retrieve and display walking directions from 10, West 33rd Street, Manhattan Community Board 5, Manhattan, New York County, City of New York, New York, 10001, United States (node 2709306542; 40.7480451, -73.9859788) to Grand Central Terminal, East 46th Street, Manhattan Community Board 5, Manhattan, New York County, City of New York, New York, 10017, United States (relation 11171793; 40.75517605, -73.97523148658365). These are the local native text resolver outputs for "40.74800, -73.98600" and "40.75300, -73.97700". This explicit training derivative uses those resolved object identities and coordinates; it does not assert equivalence to the original exact numeric-coordinate route.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Retrieve and display walking directions from 10, West 33rd Street, Manhattan Community Board 5, Manhattan, New York County, City of New York, New York, 10001, United States (node 2709306542; 40.7480451, -73.9859788) to Grand Central Terminal, East 46th Street, Manhattan Community Board 5, Manhattan, New York County, City of New York, New York, 10017, United States (relation 11171793; 40.75517605, -73.97523148658365). These are the local native text resolver outputs for "40.74800, -73.98600" and "40.75300, -73.97700". This explicit training derivative uses those resolved object identities and coordinates; it does not assert equivalence to the original exact numeric-coordinate route.

## cd9a826663fedf99b95c
- **题面：** Change the starting point of the route to Times Square, New York
- **分支：** （源：remaining）
  - G1 【起点】起点 改为 "Times Square"
  - G2 【保存生效】新建/添加已持久保存生效

## e7cc97607702e3c068f0
- **题面：** Find directions between two specific points on OpenStreetMap.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## e90e52433bd62066d5fe
- **题面：** Get directions between two points
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Get directions between two points

## fda3687e418b2e77a927
- **题面：** Examine the specific route shown on the map for traveling between New York City and Boston.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Examine the specific route shown on the map for traveling between New York City 

## 51af550413fbb12ff585
- **题面：** Navigate to a user profile from a post
- **分支：** （源：remaining）
  - G1 【发布成功】发布操作已成功执行

## 51de100442d8125c782a
- **题面：** Download a complete OpenStreetMap XML file for an area you select that contains the original starting map center.
- **分支：** （源：remaining）
  - G1 【下载成功】下载成功：目标为 a complete OpenStreetMap XML file for an area you select that contains the original starting map center

## 5548fb9da73c6f241a46
- **题面：** Change the map style from Standard to Humanitarian, then download a complete OpenStreetMap XML data file for an area you select.
- **分支：** （源：remaining）
  - G1 【地图样式】地图样式 从 "Standard" 改为 "Humanitarian"
  - G2 【保存生效】修改已持久保存生效

## 55a2c894bcb4fb84a0d1
- **题面：** Using the supplied native GitLab group export file, import its group metadata into a new private top-level group named "Imported Training Group" at path "lab-import-target" on this website. Preserve the exported description, labels, milestones and group membership. This export contains no projects or repositories; no external server access is required.
- **分支：** （源：remaining）
  - G1 【导出成功】导出成功：目标为 file, import its group metadata into a new private top-level group named Imported Training Group at path lab-import-target on this website

## 56fc1f536d2c9ba5a7ac
- **题面：** Find the fastest walking route from Empire State Building to Brooklyn Bridge Compare the complete alternatives returned by the local routing backend for the specified mode; choose the minimum travel time. This is a backend-relative optimum, not a global optimality claim.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 583161da69051b897f1f
- **题面：** Search the non-archived Explore project collection for GitHub in project names, paths, or descriptions.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## acff3f4c8cd98c58ff73
- **题面：** Navigate to the Byte Blaze / empathy-prompts repository to access inclusive design principles and resources.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Navigate to the Byte Blaze / empathy-prompts repository to access inclusive desi

## b71aadd64cd9b00a7129
- **题面：** Check the Activity page to see recent updates across your projects.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Check the Activity page to see recent updates across your projects.

## de15d6de02024f3619ac
- **题面：** View project storage usage and quotas information.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：View project storage usage and quotas information.

## df856638e15fb10861d3
- **题面：** View your starred projects.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：View your starred projects.

## e4aa16561f614640191c
- **题面：** Search for merge requests mentioning Bootstrap project
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 596b65ea28455970fb10
- **题面：** For this local training variant, open the native Explore directory of all non-archived projects accessible to your account. You may inspect a project listed in that directory; completion requires leaving the directory, or a listed project overview or repository page, open. Do not modify site records.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：For this local training variant, open the native Explore directory of all non-archived projects accessible to your account. You may inspect a project listed in that directory; completion requires leaving the directory, or a listed project overview or repository page, open. Do not modify site records.

## 7ea45493b5a607c0f9df
- **题面：** Go to your user profile page to manage account settings.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /\-/profile/?
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Edit Profile .*GitLab$

## 852be48b6721d3b17600
- **题面：** For this local training variant, open the native Explore directory of public non-archived projects. You may inspect a project listed in that directory; completion requires leaving the directory, or a listed project overview or repository page, open. Do not modify site records.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：For this local training variant, open the native Explore directory of public non-archived projects. You may inspect a project listed in that directory; completion requires leaving the directory, or a listed project overview or repository page, open. Do not modify site records.

## 999eff3cbc3641769521
- **题面：** Go to the Starred projects section on the GitLab Explore page.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /explore/projects/starred/?
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Projects .*Explore .*GitLab$

## f1ff8d817214cc662de0
- **题面：** Access the Bootstrap project wiki.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /twbs/bootstrap/\-/wikis/home/?
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Wiki .*Bootstrap / bootstrap .*GitLab$

## 5bdfde236d2459249233
- **题面：** Change the map layer style Change to an actual supported local map overlay, Map Notes or Map Data, while retaining the complete original native car route. Native Notes may be genuinely empty; opening the catalog, checked controls alone, remote providers, warnings or incomplete response bodies do not complete this local interpretation. Original goals, starts, traces and scores remain unchanged; benchmark equivalence is not claimed.
- **分支：** （源：remaining）
  - G1 【map layer style Change】map layer style Change 改为 "an actual supported local map overlay"
  - G2 【保存生效】修改已持久保存生效

## 5d6d2407a33586ba8780
- **题面：** View all products marked Out of Stock in the catalog inventory, across the full catalog. Leave the complete matching product list displayed and do not change any products or inventory.
- **分支：** （源：remaining）
  - G1 【变更字段】变更 any products or inventory
  - G2 【保存生效】修改已持久保存生效

## 9da79908372d345bd8cb
- **题面：** Set the Logo Image for Default Store View in Design Configuration to the provided training-logo-9da79908.png and save the configuration. Keep other design settings and existing media unchanged.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 Default Store
  - G2 【Logo Image for Default Store View in Design Configuration】Logo Image for Default Store View in Design Configuration 改为 "the provided training-logo-9da79908"
  - G3 【保存生效】修改已持久保存生效

## c4ab9bc0417f13b6bae7
- **题面：** Upload the provided training-banner-c4ab9bc0.png banner image to the wysiwyg/mens folder in Media Gallery. Keep all existing media files and other catalog content unchanged.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 provided training-banner-c4ab9bc0.png banner image
  - G2 【上传】上传 provided training-banner-c4ab9bc0.png banner image 到 wysiwyg/mens folder in Media Gallery
  - G3 【保存生效】新建/添加已持久保存生效

## 63e71191537ae6ae0053
- **题面：** View the local a11yproject/a11yproject.com resources source, src/resources.njk, and locate its Screen readers and Screen reader help entries. This training task checks the local source material, not the content of external linked websites.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：View the local a11yproject/a11yproject.com resources source, src/resources.njk, and locate its Screen readers and Screen reader help entries. This training task checks the local source material, not the content of external linked websites.

## 72acd537c3f7f0f541e8
- **题面：** Open one local announcement source document in src/announcements of a11yproject/a11yproject.com.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Open one local announcement source document in src/announcements of a11yproject/a11yproject.com.

## 8f895ff3fc7981f5135d
- **题面：** Open the local contribution instructions in the a11yproject/a11yproject.com repository.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Open the local contribution instructions in the a11yproject/a11yproject.com repository.

## 98d35ac5ff30a57a3473
- **题面：** Open the local Code of Conduct source document src/code-of-conduct.njk in a11yproject/a11yproject.com.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Open the local Code of Conduct source document src/code-of-conduct.njk in a11yproject/a11yproject.com.

## fd7ce2fd29097ac8678d
- **题面：** Open one local featured-accessibility profile document from src/spotlight in a11yproject/a11yproject.com.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Open one local featured-accessibility profile document from src/spotlight in a11yproject/a11yproject.com.

## 66acba7fc3a47aa78208
- **题面：** Create a simple product named Atomic coffee maker - training catalog item, SKU TRAINING-COFFEE-ATOMIC-001, price 29.99 in the local training catalog. Use Page Builder to create its Description with the bold heading "Atomic coffee maker", bullet points ["Product type: coffee maker.", "Design: Giordano Robbiati."], and the supplied local image atomic-coffee-maker.jpg. Save the product without changing other catalog items. These identity and price values are training fixtures, not a real sale offer.
- **分支：** admin-material-creation-v1（源：remaining）
  - G1 【产品身份】创建产品身份正确
  - G2 【产品字段】价格/描述/图片等字段正确
  - G3 【未动其他】未改变其他商品

## 680a097ada00b0af5f17
- **题面：** In the provided local catalog snapshot, for Maya Tunic (SKU WT07), add Antonia Racer Tank (WT08) as a related product, Gwyn Endurance Tee (WS01) as an up-sell, and Joust Duffle Bag (24-MB01) as a cross-sell. Keep all existing associations, make no other product changes, and save.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 Maya Tunic
  - G2 【保存生效】新建/添加已持久保存生效

## 6f727a98850974eacdbd
- **题面：** Reorder items from your completed order #000000180.
- **分支：** （源：remaining）
  - G1 【重新下单】从订单 #000000180 重新下单
  - G2 【保存生效】修改已持久保存生效

## ff12429c3d973f57a483
- **题面：** Filter electronics products by price range $0-$100
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 electronics products
  - G2 【过滤条件】按「price range $0-$100」过滤
  - G3 【保存生效】修改已持久保存生效

## 729a968268eec62c50ca
- **题面：** Open the local Installation instructions for the cloud-to-butt Chrome extension in the byteblaze/cloud-to-butt repository and leave those instructions displayed. Installing the extension is not required.
- **分支：** （源：remaining）
  - G1 【退出成功】退出操作已成功执行

## aba33f959b5bc3c451a1
- **题面：** Open the local Updating the website instructions in the a11yproject/a11yproject.com repository and leave that section displayed. Do not deploy or change the website.
- **分支：** （源：remaining）
  - G1 【变更字段】变更 website
  - G2 【保存生效】修改已持久保存生效

## 741896107a1f2301d290
- **题面：** Find the driving route with the lowest expected travel time among the routes actually offered by this local website from Los Angeles, California to San Diego, California. The current website offers one route; leave it displayed with its estimated time. This does not assert a global fastest-route optimum.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 7b1ffdcc9288a0ea41a1
- **题面：** Check the monitoring dashboards for create-react-app. In this local training environment, the Metrics dashboard of facebook/create-react-app is enabled for project readers. Open the native Metrics page; no live metric values are required.
- **分支：** （源：remaining）
  - G1 【目标对象】新建/添加的对象与题面要求一致
  - G2 【保存生效】新建/添加已持久保存生效

## bf2ac2c8c2f0a3ecc319
- **题面：** View the latest locally shipped GitLab release cards in the native What's new drawer. Latest means this frozen installation's native release catalogue, not current Internet releases.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：View the latest locally shipped GitLab release cards in the native What's new drawer. Latest means this frozen installation's native release catalogue, not current Internet releases.

## d124cba3c48937ab4761
- **题面：** Export all merge requests in the current project as a CSV file.
- **分支：** （源：remaining）
  - G1 【导出成功】导出成功：目标为 all merge requests in the current project as a CSV file

## ef09dcd8d81c4fd76907
- **题面：** Create Skill Runtime Template Project using the supplied, independently qualified native local repository template and confirm the populated repository is saved.
- **分支：** （源：remaining）
  - G1 【目标对象】新建/添加的对象与题面要求一致
  - G2 【保存生效】新建/添加已持久保存生效

## 7f5e33d812204a528b3d
- **题面：** Create a configurable product named LMTX Training Tee with parent SKU LMTX-CONFIG-TEE. Use sizes S and M and colors Black and Blue, with all four size/color combinations. Use price 29.99, weight 0.5 lb and quantity 1 for each variant. Allow the native automatically generated variant names and SKUs. Save and reopen the product to verify its type, options and four associated variants.
- **分支：** （源：remaining）
  - G1 【重新打开成功】重新打开成功：目标为 product to verify its type, options and four associated variants

## 89f45e0f5bc0e1e473c5
- **题面：** Create a new order using the Create New Order button for Veronica Costello (roni_cost@example.com). Add one Fitness Tracker Pro (SKU LMTX-FITNESS-TRACKER-PRO), use her existing default billing and shipping address, Check / Money order, and Flat Rate shipping. Submit and reopen the order to confirm the customer, product and quantity. Do not send an order confirmation email.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 Veronica Costello
  - G2 【保存生效】新建/添加已持久保存生效

## 83579defd97294d34a19
- **题面：** View the coordinates of the currently selected export area. Return a JSON object with exactly these fields: {"west": "number", "south": "number", "east": "number", "north": "number"}. Select an actual rectangle through native Export and report its currently selected west/south/east/north longitude/latitude degrees. This explicit local training initialization does not assume that the original published start already had a selected rectangle and does not use viewport bounds as the selected area.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：View the coordinates of the currently selected export area. Return a JSON object

## 83f93b3087aa3c05c5dd
- **题面：** Manually select a different area for export.
- **分支：** （源：remaining）
  - G1 【导出成功】导出操作已成功执行

## 8c69b9918376f1bf4ac6
- **题面：** Zoom in on the map to enable data export.
- **分支：** （源：remaining）
  - G1 【导出成功】导出操作已成功执行

## b2baf5c23b272f00446f
- **题面：** Download a complete OpenStreetMap XML file for an area you select.
- **分支：** （源：remaining）
  - G1 【下载成功】下载成功：目标为 a complete OpenStreetMap XML file for an area you select

## 84067d885e88d9308ca9
- **题面：** Update the existing cafe point named Local Training Cafe near latitude 40.7830, longitude -73.9650. Save its name as Local Training Cafe Updated and its amenity as cafe. Keep the saved point within 100 metres of those coordinates.
- **分支：** （源：remaining）
  - G1 【名称】名称 保存为 "Local Training Cafe Updated"
  - G2 【设施类型】设施类型 保存为 "cafe"
  - G3 【保存生效】修改已持久保存生效

## cc21cc90e12f7fed8e4f
- **题面：** Add and save a new pedestrian-crossing point named Local Training Crossing within 100 metres of latitude 40.7830, longitude -73.9650. Set highway=crossing.
- **分支：** （源：remaining）
  - G1 【目标对象】新建/添加的对象与题面要求一致
  - G2 【保存生效】新建/添加已持久保存生效

## cceb1d4e9c145309f419
- **题面：** Add and save a new bakery point named Local Training Bakery within 100 metres of latitude 40.7830, longitude -73.9650. Set shop=bakery.
- **分支：** （源：remaining）
  - G1 【目标对象】新建/添加的对象与题面要求一致
  - G2 【保存生效】新建/添加已持久保存生效

## 8f9b359a1841c03dfec1
- **题面：** Subscribe in the local calendar client to the native upcoming-due-date calendar for open issues assigned to the currently signed-in user. Use the native calendar window (next month and previous two weeks). Completion requires a saved subscription and a successfully fetched valid calendar.
- **分支：** （源：remaining）
  - G1 【订阅成功】订阅操作已成功执行

## b501b2eb43fd13258b5e
- **题面：** Subscribe in the local feed reader to open issues in zhongyang219/TrafficMonitor. The saved subscription must fetch the native feed successfully; opening or returning a URL alone is insufficient.
- **分支：** （源：remaining）
  - G1 【订阅成功】订阅操作已成功执行

## c22e3ef1b633541de03f
- **题面：** Clone the amwhalen/archive-my-tweets repository into the local workspace. Completion requires a usable local Git working tree; returning a clone command is insufficient.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 amwhalen/archive-my-tweets
  - G2 【克隆】克隆仓库 amwhalen/archive-my-tweets 到本地工作区
  - G3 【保存生效】新建/添加已持久保存生效

## 96589b87f8054e909e32
- **题面：** Share the current map view using the "Share" feature.
- **分支：** （源：remaining）
  - G1 【分享成功】分享成功：目标为 current map view using the Share feature

## 986fe7a818c13d647950
- **题面：** Export the current product catalog as a CSV file. Download a newly generated native Products CSV containing the complete catalog, all store views and all available export columns. Keep product data unchanged.
- **分支：** （源：remaining）
  - G1 【导出成功】导出成功：目标为 current product catalog as a CSV file

## 9a7b1a5fd0f2ac7920e3
- **题面：** Rate the Pre-baked Gingerbread House Kit with 3 stars.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 Pre-baked Gingerbread House Kit
  - G2 【评分】评分为 3 星
  - G3 【保存生效】修改已持久保存生效

## c9825125201a7feb144e
- **题面：** Submit a 5-star review for the Nightfox Vulpes Night Vision Goggles with the title "Great for night hunting".
- **分支：** （源：remaining）
  - G1 【提交成功】提交成功：目标为 a 5-star review for the Nightfox Vulpes Night Vision Goggles with the title Great for night hunting

## 9aecbe6c890525d67975
- **题面：** Associate Wireless Bluetooth Headphones (SKU LMTX-WIRELESS-HEADPHONES) with the preconfigured Lab Audio Website, keeping its existing website associations. Save the product and reopen it to verify the website association. The website, Lab Audio Store and Lab Audio English store view already exist; creating those objects is outside this task.
- **分支：** （源：remaining）
  - G1 【重新打开成功】重新打开成功：目标为 it to verify the website association

## a73e169e685b1bcbfb7a
- **题面：** Create a new product attribute labelled Material, with attribute code lmtx_material_eco and catalog input type Text Field. Add it to Yoga Mat Pro (SKU LMTX-YOGA-MAT-PRO), set its value to Eco-friendly rubber, save the product, and reopen it to verify that value. This task uses the declared local Yoga Mat Pro fixture.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 it to Yoga Mat Pro (SKU LMTX-YOGA-MAT-PRO), set its value to Eco-friendly rubber, save the product, and reopen it
  - G2 【值】值 改为 "Eco-friendly rubber"
  - G3 【目标位置】添加到 verify that value
  - G4 【保存生效】新建/添加已持久保存生效

## 9e4bb872e2c51ee183ca
- **题面：** Create a bundle product named LMTX Fitness Audio Bundle with SKU LMTX-FITNESS-AUDIO-BUNDLE. Include Fitness Tracker Pro (SKU LMTX-FITNESS-TRACKER-PRO) and Wireless Bluetooth Headphones (SKU LMTX-WIRELESS-HEADPHONES), with default quantity 1 for each component. Keep the native dynamic price and dynamic weight defaults. Save and reopen the bundle to verify both component associations.
- **分支：** （源：remaining）
  - G1 【重新打开成功】重新打开成功：目标为 bundle to verify both component associations

## a1078549f94ed0af0411
- **题面：** Get bicycle directions from San Francisco, California to Oakland, California.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Get bicycle directions from San Francisco, California to Oakland, California.

## ac178002ab63fe121bb8
- **题面：** Download a PDF of the initial Standard map view using the default image-export area and scale.
- **分支：** （源：remaining）
  - G1 【下载成功】下载成功：目标为 a PDF of the initial Standard map view using the default image-export area and scale

## b363c4adf5ba96d3c195
- **题面：** Download a PDF showing the initial driving route from Central Park to Times Square on the Standard map, retaining the route overlay and using the default image-export area and scale.
- **分支：** （源：remaining）
  - G1 【下载成功】下载成功：目标为 a PDF showing the initial driving route from Central Park to Times Square on the Standard map, retaining the route overlay and using the default image-export area and scale

## eb7dbf2b4317d9cb583b
- **题面：** Download a PNG of the initial walking route on the Standard map, keeping its route overlay and the default image-export area and scale.
- **分支：** （源：remaining）
  - G1 【下载成功】下载成功：目标为 a PNG of the initial walking route on the Standard map, keeping its route overlay and the default image-export area and scale

## acd4566552fb8364f8ef
- **题面：** Update the inventory threshold for "Fitness Tracker Pro" to trigger low stock notifications at 10 units
- **分支：** （源：remaining）
  - G1 【写操作结果】写操作结果状态精确
  - G2 【保存生效】结果已保存

## c0b840810cad9823b1e6
- **题面：** Create a duplicate of the "Fitness Tracker Pro" product with a different SKU
- **分支：** （源：remaining）
  - G1 【写操作结果】写操作结果状态精确
  - G2 【保存生效】结果已保存

## aecc474f08b43bd57981
- **题面：** Display a bicycle route from San Francisco, California to Oakland, California.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Display a bicycle route from San Francisco, California to Oakland, California.

## b4c7ac6c9fecf70474ed
- **题面：** Check if there is a convenience store called "New York" in Manhattan For this local finite-snapshot training interpretation, inspect a native object tagged shop=convenience and name=New York whose actual native administrative address declares Manhattan and whose point lies in the independently identified Manhattan bounds. This positive existence protocol cannot infer absence from bounded or empty search results. Original goals, starts, traces and scores remain unchanged and benchmark equivalence is not claimed. Finish with a JSON object containing exactly exists (boolean) and object_path (the actual native object path inspected).
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Check if there is a convenience store called "New York" in Manhattan For this lo

## f7b5b69967228adc3616
- **题面：** View the edit history of the New York map area For this deterministic local training interpretation, New York means New York City according to the declared native geographic identity. Display the actually loaded native History list for that map view; a genuinely empty native list is valid. Original goals, starts, traces and scores remain unchanged and benchmark equivalence is not claimed.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：View the edit history of the New York map area For this deterministic local trai

## b4eecdad9946f2165795
- **题面：** Search for the Eiffel Tower in Paris, France. Leave its native search result or its object details visible. A correctly identified, successfully loaded result is sufficient; changing the base-map style, centering or zooming the map, loading every background tile, and planning a route are not required.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## b9101b71aacd51b61f6e
- **题面：** Enable the Map Data overlay to see detailed map information along the route from Central Park to Times Square.
- **分支：** （源：remaining）
  - G1 【启用】启用 Map Data overlay
  - G2 【保存生效】修改已持久保存生效

## b9b08929e91c1bfab775
- **题面：** View the complete detailed turn-by-turn driving directions from Lower Manhattan to Brooklyn. This is an explicit local training derivative with different named geography. The original goal "View the detailed turn-by-turn directions for driving from Upper Manhattan to Brooklyn.", all original starts and traces, and all old scores remain unchanged. It does not claim equivalence to the original geographical task or its benchmark result.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：View the complete detailed turn-by-turn driving directions from Lower Manhattan to Brooklyn. This is an explicit local training derivative with different named geography. The original goal "View the detailed turn-by-turn directions for driving from Upper Manhattan to Brooklyn.", all original starts and traces, and all old scores remain unchanged. It does not claim equivalence to the original geographical task or its benchmark result.

## c9e0b6ce1b0127b8165a
- **题面：** Export the current map view to use offline or in other applications.
- **分支：** （源：remaining）
  - G1 【导出成功】导出成功：目标为 current map view to use offline or in other applications

## bf928111f7eeda70ebb7
- **题面：** View product reviews for the V8 Energy drink.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：View product reviews for the V8 Energy drink.

## ca7440f2c8998084beaa
- **题面：** Submit one local content report for the specified native comment by 7SlotGrill in rva, using the supplied reason and report details. Finish on the saved content report receipt.
- **分支：** （源：remaining）
  - G1 【提交成功】提交成功：目标为 one local content report for the specified native comment by 7SlotGrill in rva, using the supplied reason and report details

## ca83744cd6665d0bf7ba
- **题面：** Log in using the supplied existing local test account training-mapper-v183@example.test (display name Training Mapper V183), password TrainingMapper-LocalOnly-2026. Upload the supplied training-hike-v183.gpx file as a private GPS trace with description "Synthetic local training hike v183". Reopen its saved trace record and verify that it belongs to your account and identifies this file. The GPX is a synthetic local test hike; map rendering or point-by-point review is not required.
- **分支：** （源：remaining）
  - G1 【重新打开成功】重新打开成功：目标为 its saved trace record and verify that it belongs to your account and identifies this file

## cfea17890aff46338228
- **题面：** Export the list of open issues as a CSV file.
- **分支：** （源：remaining）
  - G1 【导出成功】导出成功：目标为 list of open issues as a CSV file

## d235c40ec6d147df43b5
- **题面：** Reply with Thanks for sharing this song. to a visible comment on a local post opened from the native search results for song describes your love life.
- **分支：** （源：remaining）
  - G1 【回复成功】回复成功：目标为 with Thanks for sharing this song

## f73cb8c389af66bfe1c2
- **题面：** Reply with Thanks for sharing your thoughts. to a visible comment made by Nut_shells on this local platform.
- **分支：** （源：remaining）
  - G1 【回复成功】回复成功：目标为 with Thanks for sharing your thoughts

## d4bc409ee106127d9cef
- **题面：** Export a PNG map showing the complete driving route from Times Square to Central Park in New York City. Include the whole route in the exported image.
- **分支：** （源：remaining）
  - G1 【导出成功】导出成功：目标为 a PNG map showing the complete driving route from Times Square to Central Park in New York City

## d7871458d5abbfb193c3
- **题面：** Find the coordinates of Boston on the map For this local protocol, Boston means the geographical place described by {"names": ["Boston"], "state": ["Massachusetts"], "country_code": "us"}. Return a JSON object containing exactly latitude and longitude, the complete native place coordinates.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## da9f45b19b82ff5bd367
- **题面：** Inspect the saved, enabled catalog price rules and report the customer groups configured on those rules. Enabled means the rule Active setting is on. List the group names in your final answer; if no saved enabled rules have customer groups, explicitly report none. This task does not ask whether a discount is currently effective for a product, website, or date. Return your final answer as JSON with the single key customer_groups and a list of group names, for example {"customer_groups": []} for a genuinely empty result.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Inspect the saved, enabled catalog price rules and report the customer groups co

## db7973ac919efac96963
- **题面：** Manually select a different area on the map for export.
- **分支：** （源：remaining）
  - G1 【导出成功】导出操作已成功执行

## eadb904d28ab449fb575
- **题面：** Open the local movies discussion post titled "Who will win the Oscar for ACTRESS IN A SUPPORTING ROLE?" and finish on that post. External polls are outside this task.
- **分支：** （源：remaining）
  - G1 【发布成功】发布成功：目标为 titled Who will win the Oscar for ACTRESS IN A SUPPORTING ROLE? and finish on that post

## fdcf9f8c7df1bf7d7627
- **题面：** Search the local Wiki page titles and bodies for "specific content" and finish on the complete Wiki results page, including a genuine empty result set.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## f5553200250f467d3763
- **题面：** For this local training variant, select orders 000000125 and 000000300 together and update both to Processing without changing any other orders. These two supplied local orders initially have status On Hold; this initial state differs from the original task. Start from the original Transactions page.
- **分支：** （源：remaining）
  - G1 【状态】状态 改为 "Processing"
  - G2 【保存生效】修改已持久保存生效

## f8de0216fd7963aac2f9
- **题面：** Display the local formatting help that explains links to wiki pages, forums, and user profiles. Leave the relevant help visible; creating a page or writing an explanation is not required.
- **分支：** （源：remaining）
  - G1 【退出成功】退出操作已成功执行

## 14f06188c98331becd21
- **题面：** View details for shipment 000000001 by clicking the View link.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【目标记录】打开题面指定记录（increment_id=000000001）

## 177050ea8a1797a953ea
- **题面：** Visit the FIND PARTNERS & EXTENSIONS page to explore additional integrations.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【到达目标路径】到达路径 /marketplace/index/
  - G2 【标题匹配】页面标题为 Magento Marketplace

## 1c0bf161407336002171
- **题面：** Find order #000000074 in the system
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【目标记录】打开题面指定记录（increment_id=000000074）

## 1f2f394baa44fccb4cad
- **题面：** View the order details for the most recent order from John Doe
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【目标记录】打开题面指定记录（customer_firstname=John、customer_lastname=Doe）

## 2038477b06ca11f8cc96
- **题面：** View and edit Search Terms in the SEO & Search section
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【到达目标路径】到达路径 /search/term/
  - G2 【标题匹配】页面标题为 Search Terms

## 2416c44a87ae78a202b0
- **题面：** Manage Pending Reviews that need approval before publication.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【到达目标路径】到达路径 /review/product/pending/
  - G2 【标题匹配】页面标题为 Pending Reviews

## 254628e03fe9f5afe40a
- **题面：** Reload the data on the local Magento Admin Dashboard and wait for the refresh to finish. Do not open external Advanced Reporting.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【操作步骤】执行 UI 操作 Reload Data

## 27181d248c2ed67451cf
- **题面：** View details of order with ID 000000260.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【目标记录】打开题面指定记录（increment_id=000000260）

## 291f00a6864cf2f47b3b
- **题面：** View details of order ID 000000215 placed by Lucy Garcia.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【目标记录】打开题面指定记录（increment_id=000000215）

## 2aaa780d74d8ec80e460
- **题面：** View the details of shipment #000000001.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【目标记录】打开题面指定记录（increment_id=000000001）

## 2d298184d2a84a81c3de
- **题面：** Check what options are available for configuring related products and up-sells.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【目标表单】目标表单为 New Product
  - G2 【展开面板】展开面板 Related Products, Up-Sells, and Cross-Sells

## 2e0d5e481b545d006eb5
- **题面：** Find out what design customization options are available for products.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【目标表单】目标表单为 New Product
  - G2 【展开面板】展开面板 Design

## 347e7078395d31f5d956
- **题面：** Retrieve the details of order ID 000000001 placed by Veronica Costello.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【目标记录】打开题面指定记录（increment_id=000000001）

## 363200aa291cf6e60c34
- **题面：** Retrieve the details of order ID 000000074.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【目标记录】打开题面指定记录（increment_id=000000074）

## 36dae9d540f0783d5241
- **题面：** Navigate to the admin account settings to manage your user information and preferences.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【到达目标路径】到达路径 /admin/system_account/
  - G2 【标题匹配】页面标题为 My Account

## 375ad2e06bf13f338ef6
- **题面：** Find customer Adam Garcia and open the account details. For this local training variant, the target account email is adam.garcia@gmail.com.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【目标记录】打开题面指定记录（email=adam.garcia@gmail.com、firstname=Adam、lastname=Garcia）

## 3d4457325afe8f91d530
- **题面：** View details of order ID 000000006.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【目标记录】打开题面指定记录（increment_id=000000006）

## 3e62c110ad19ec0f26a9
- **题面：** Access the Search Engine Optimization settings for the Yoga Mat Pro
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【目标对象】目标对象身份为 name=Yoga Mat Pro
  - G2 【展开面板】展开面板 Search Engine Optimization

## 40b5703362f69dcf2769
- **题面：** Manage search terms to improve site search functionality.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【到达目标路径】到达路径 /search/term/
  - G2 【标题匹配】页面标题为 Search Terms

## 48b472dc7ddc79b9c280
- **题面：** Open the details of order #000000002.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【目标记录】打开题面指定记录（increment_id=000000002）

## 4cdcd6e8f67a6b50c471
- **题面：** Navigate to the associated order details page from the credit memo view.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【目标记录】打开题面指定记录（increment_id=000000002）

## 4d970be093df3ecedb43
- **题面：** Go to the Add Product page to create a new product
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【到达目标路径】到达路径 /catalog/product/new/set/4/type/simple/
  - G2 【标题匹配】页面标题为 New Product

## 4e3cd4fb6e1a9faf4ae5
- **题面：** Navigate to the Add Product page to create a new product.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【到达目标路径】到达路径 /catalog/product/new/set/4/type/simple/
  - G2 【标题匹配】页面标题为 New Product

## 55031e51fe71e1884f97
- **题面：** Navigate to the Customizable Options section to set up product customization choices for customers.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【目标表单】目标表单为 New Product
  - G2 【展开面板】展开面板 Customizable Options

## 569902f77d2fc9220640
- **题面：** View the details of the Updated General Customers group
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【目标记录】打开题面指定记录（name=Updated General Customers）

## 59f10f648e07a8599c10
- **题面：** Open the Account Information section of the new customer form and view its required name and email fields. Do not create a customer.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【到达目标路径】到达路径 /customer/index/new/
  - G2 【标题匹配】页面标题为 New Customer

## 5d069a986272c2c463ca
- **题面：** Search for an order using the keyword '000000002'.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【目标记录】打开题面指定记录（increment_id=000000002）

## 6349db43411d84c10b34
- **题面：** View details of order ID 000000296 placed by Lily Potter.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【目标记录】打开题面指定记录（increment_id=000000296）

## 63844c9cde42853554e9
- **题面：** Check the Product Reviews section for Example Product Deluxe 2023
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【目标对象】目标对象身份为 name=Example Product Deluxe 2023
  - G2 【展开面板】展开面板 Product Reviews

## 6a77d804880c9dd593ca
- **题面：** Navigate to the Account Activity page to monitor login history and security events in the Magento Admin panel.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【到达目标路径】到达路径 /security/session/activity/
  - G2 【标题匹配】页面标题为 Account Activity

## 6de6f3be5631c3154fa9
- **题面：** Navigate to the Search Engine Optimization section to configure SEO settings
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【目标对象】目标对象身份为 name=Blue T-Shirt
  - G2 【展开面板】展开面板 Search Engine Optimization

## 6ea31b8a6b1c57f74d78
- **题面：** Navigate to the Marketplace to find partners and extensions for your store.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【到达目标路径】到达路径 /marketplace/index/
  - G2 【标题匹配】页面标题为 Magento Marketplace

## 70acff4f3314529e00e4
- **题面：** View the current details of the Yoga Mat Pro product.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【目标记录】打开题面指定记录（name=Yoga Mat Pro）

## 73b7ff954d5a0403a027
- **题面：** Check which customers are currently online in the Now Online section
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【到达目标路径】到达路径 /customer/online/
  - G2 【标题匹配】页面标题为 Customers Now Online

## 766c107f2c4a20999ec7
- **题面：** Open the Email Templates management list. This navigation task does not require editing or sending a template.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【到达目标路径】到达路径 /admin/email_template/
  - G2 【标题匹配】页面标题为 Email Templates

## 7e7b743d668a8fbf10d6
- **题面：** Open the edit page for the search term Joust Bag and view its details. No saved modification is required.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【目标记录】打开题面指定记录（query_text=Joust Bag）

## 7e8f9ce1c211bf5cfc57
- **题面：** Show related products, up-sells, and cross-sells for the Blue T-Shirt.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【目标对象】目标对象身份为 name=Blue T-Shirt
  - G2 【展开面板】展开面板 Related Products, Up-Sells, and Cross-Sells

## 87e7fc781adb323845eb
- **题面：** Starting from credit memo #000000001 for order #000000002, open the shipping address edit form for that order. Do not change the address.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【操作步骤】执行 UI 操作 
  - G2 【到达路径】最终到达路径 /admin/sales/order/address/address_id/3/

## 8c52e068ace257038ee9
- **题面：** Check what customizable options can be added to a product.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【目标表单】目标表单为 New Product
  - G2 【展开面板】展开面板 Customizable Options

## 8e153454fde6cec53e07
- **题面：** Check which customers are currently online
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【到达目标路径】到达路径 /customer/online/
  - G2 【标题匹配】页面标题为 Customers Now Online

## 8e2e7558360b6eafb077
- **题面：** View details of credit memo #000000001 for customer Veronica Costello
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【目标记录】打开题面指定记录（increment_id=000000001）

## 8f0371193c9f301d3a23
- **题面：** View details of order ID 000000149 placed by Ava Brown.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【目标记录】打开题面指定记录（increment_id=000000149）

## 982797e1e68253e3357d
- **题面：** Search the Orders grid using the exact keyword "Canceled" and leave the completed search applied. This is a keyword search, not an order-status filter.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【操作步骤】执行 UI 操作 、
  - G2 【到达路径】最终到达路径 /admin/sales/order/

## 9b3f3de66823922994cb
- **题面：** Navigate to the Find Partners & Extensions page
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【到达目标路径】到达路径 /marketplace/index/
  - G2 【标题匹配】页面标题为 Magento Marketplace

## 9dfc73f6ed3e35bcac8d
- **题面：** Navigate to the Search Engine Optimization section to configure product meta title, description, and URL key for better search visibility.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【目标表单】目标表单为 New Product
  - G2 【展开面板】展开面板 Search Engine Optimization

## 9e4dffe846c3d7af5588
- **题面：** Manage URL Rewrites in the SEO & Search section
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【到达目标路径】到达路径 /admin/url_rewrite/
  - G2 【标题匹配】页面标题为 URL Rewrites

## a283f052b780de047d00
- **题面：** Navigate to the Product Reviews section for the Yoga Mat Pro
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【目标对象】目标对象身份为 name=Yoga Mat Pro
  - G2 【展开面板】展开面板 Product Reviews

## ae1dc8ac2b70c4162580
- **题面：** Navigate to the Find Partners & Extensions page.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【到达目标路径】到达路径 /marketplace/index/
  - G2 【标题匹配】页面标题为 Magento Marketplace

## afc1ae80713f5adb54f1
- **题面：** Starting with Default Store View selected, change the dashboard scope to All Store Views and wait for the dashboard to load.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【操作步骤】执行 UI 操作 、

## b148ea88e3291720b100
- **题面：** For this local training variant, use the Shipments Filters controls to apply Shipment = 000000001 and leave that filter applied.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【操作步骤】执行 UI 操作 、、Apply Filters
  - G2 【到达路径】最终到达路径 /admin/sales/shipment/

## b8e5669b95518725aeb8
- **题面：** Find a customer named Adam Garcia in the customer list For this local training variant, the target account email is adam.garcia@gmail.com.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【目标记录】打开题面指定记录（email=adam.garcia@gmail.com、firstname=Adam、lastname=Garcia）

## c6ac29c6747d728cde87
- **题面：** Navigate to the Product Attributes section to create a new product attribute for material type.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【到达目标路径】到达路径 /catalog/product_attribute/
  - G2 【标题匹配】页面标题为 Product Attributes

## d42ce8884ce7718f6c7d
- **题面：** View the scheduled design updates for the "New Category Name" category
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【目标对象】目标对象身份为 name=New Category Name
  - G2 【展开面板】展开面板 Schedule Design Update

## d5189447448bd9559f2e
- **题面：** For this local training variant, upload the provided training image admin-training-d5189447448bd9559f2e.png to Sony Headphones and save it as a product image.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【目标对象】目标对象身份为 name=Sony Headphones
  - G2 【媒体操作】执行媒体操作 upload 且文件系统状态精确

## d525e09342e6ef7b1e55
- **题面：** Check which customers are currently online by going to the Now Online page
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【到达目标路径】到达路径 /customer/online/
  - G2 【标题匹配】页面标题为 Customers Now Online

## d5cc9a3ade15173c7771
- **题面：** Navigate to the edit page for the Yoga Mat Pro product
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【目标记录】打开题面指定记录（name=Yoga Mat Pro）

## d6e4047f095397551651
- **题面：** Open the details of order #000000002.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【目标记录】打开题面指定记录（increment_id=000000002）

## daf0737fe666f1a64a7a
- **题面：** View the required fields for creating a new simple product in Magento.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【到达目标路径】到达路径 /catalog/product/new/set/4/type/simple/
  - G2 【标题匹配】页面标题为 New Product

## e002def8cda365af6e51
- **题面：** Navigate to the Images And Videos section of the Blue T-Shirt product page.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【目标对象】目标对象身份为 name=Blue T-Shirt
  - G2 【展开面板】展开面板 Images And Videos

## e1ff77db4d7f5388c86a
- **题面：** Open the edit page of Yoga Mat Pro.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【目标记录】打开题面指定记录（name=Yoga Mat Pro）

## e514bbe583bf49164ed6
- **题面：** Retrieve details of the credit memo 000000001.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【目标记录】打开题面指定记录（increment_id=000000001）

## ecb8fd8c46003d01d111
- **题面：** View details of credit memo for order #000000002
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【目标记录】打开题面指定记录（order_increment_id=000000002）

## f23fe4dd97cd71659fbe
- **题面：** View up-sell products for the Blue T-Shirt
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【目标对象】目标对象身份为 name=Blue T-Shirt
  - G2 【展开面板】展开面板 Related Products, Up-Sells, and Cross-Sells, Up-Sell Products

## f3a71fb5b99ae901657f
- **题面：** View details of order ID 000000240.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【目标记录】打开题面指定记录（increment_id=000000240）

## f6e7d7a7b8e2c5de9686
- **题面：** View the details of order 000000002.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【目标记录】打开题面指定记录（increment_id=000000002）

## f98ec9d6215909d72fdf
- **题面：** For this local training variant, open the saved grid View menu on the admin Products catalog page. Do not change the storefront layout.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【网格操作】网格执行操作 view_menu

## fafe0f88b72987584111
- **题面：** For this local training variant, upload the provided training image admin-training-fafe0f88b72987584111.png to Blue T-Shirt and save it as a product image.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【目标对象】目标对象身份为 name=Blue T-Shirt
  - G2 【媒体操作】执行媒体操作 upload 且文件系统状态精确

## fc286f56ae1f1db977e4
- **题面：** On the Products catalog grid, open the Filters panel so that its filter fields are available. No particular product or filter value is requested.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【操作步骤】执行 UI 操作 
  - G2 【到达路径】最终到达路径 /admin/catalog/product/

## fe896ed53cb133b9e2f6
- **题面：** For this local training variant, upload the provided training image admin-training-fe896ed53cb133b9e2f6.png to Premium Leather Wallet and save it as a product image.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【目标对象】目标对象身份为 name=Premium Leather Wallet
  - G2 【媒体操作】执行媒体操作 upload 且文件系统状态精确

## 022fa40c9fd37fa21286
- **题面：** Go to the Categories page to organize products into categories and manage the catalog structure.
- **分支：** admin-page-navigation-v2（源：remaining）
  - G1 【到达目标路径】到达目标路径 /catalog/category/

## 029301626f4ad1aad104
- **题面：** Navigate to the page to add a new customer to the system.
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /customer/index/new/

## 0adb752374941d613c64
- **题面：** Navigate to the Billing Agreements page to manage billing agreements.
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /paypal/billing_agreement/

## 0e2395e6e0ec9275b2c5
- **题面：** Navigate to the Invoices page to manage billing documents for orders.
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /sales/invoice/

## 1052784c7dbb6cf095d2
- **题面：** View the Orders sales report.
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /reports/report_sales/sales/

## 17e34235d6332e537ed1
- **题面：** Navigate to Catalog Price Rule to set up product discounts.
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /catalog_rule/promo_catalog/

## 196fe000070f772337aa
- **题面：** Navigate to the Dashboard page in the Magento Admin panel.
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /admin/dashboard/

## 1a2c3bd8484a1a239921
- **题面：** Retrieve the Products in Cart report.
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /reports/report_shopcart/product/

## 1d58056bb47b072d89ed
- **题面：** Navigate to the Shipments page to manage order fulfillment and track packages.
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /sales/shipment/

## 21b56472c09b5af384f8
- **题面：** View all products in the inventory
- **分支：** admin-page-unfiltered-listing-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /catalog/product/

## 287b1d0abd68d6c4faff
- **题面：** Review abandoned cart reports.
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /reports/report_shopcart/abandoned/

## 288d0528f8245033c650
- **题面：** Review all credit memos in the system
- **分支：** admin-page-unfiltered-listing-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /sales/creditmemo/

## 2b7d01f5bdac5dce2e6f
- **题面：** Navigate to the Categories page to organize product categories.
- **分支：** admin-page-navigation-v2（源：remaining）
  - G1 【到达目标路径】到达目标路径 /catalog/category/

## 2cd4730643278ebd29df
- **题面：** View and manage Billing Agreements with customers.
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /paypal/billing_agreement/

## 3079b0f26aede73ecc80
- **题面：** View Newsletter Problem Reports
- **分支：** admin-page-navigation-v2（源：remaining）
  - G1 【到达目标路径】到达目标路径 /newsletter/problem/

## 334c7b41c06d6169261f
- **题面：** Go to URL Rewrites to manage custom URLs and redirects.
- **分支：** admin-page-navigation-v2（源：remaining）
  - G1 【到达目标路径】到达目标路径 /admin/url_rewrite/index/

## 348fa1130c91b65b08d7
- **题面：** View Sales Orders reports to analyze order trends and performance.
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /reports/report_sales/sales/

## 392c54b1ebf4013351c4
- **题面：** Review credit memos for refunded orders
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /sales/creditmemo/

## 3a0a7f7a3aaa0df0cd4a
- **题面：** Navigate to the Pending Reviews page
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /review/product/pending/

## 3c0f269ae557e2d751fc
- **题面：** Access Credit Memos.
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /sales/creditmemo/

## 3d2c65086f2e7ba8dbd6
- **题面：** Monitor Low Stock reports.
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /reports/report_product/lowstock/

## 3f3122e9facc97c4287f
- **题面：** View all products in the catalog
- **分支：** admin-page-unfiltered-listing-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /catalog/product/

## 4954d9e20162ffc56b41
- **题面：** Check Pending Reviews under User Content.
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /review/product/pending/

## 4c53e93b8aa0b208c356
- **题面：** Review the Login as Customer Log to see recent customer impersonation activity.
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /loginascustomer_log/log/index/

## 4cadc71c31de16328198
- **题面：** Navigate to the notifications page to view system notifications and alerts.
- **分支：** admin-page-navigation-v2（源：remaining）
  - G1 【到达目标路径】到达目标路径 /admin/notification/

## 4d7432269a21ce48117a
- **题面：** Navigate to the Customer Groups page
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /customer/group/

## 4db52a1c141a7d06789c
- **题面：** Navigate to the Customer Order Total report to identify high-value customers.
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /reports/report_customer/totals/

## 4f47d94604aa81593d47
- **题面：** Navigate to the DASHBOARD to view the store performance metrics.
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /admin/dashboard/

## 5ab9218e384f092d6b21
- **题面：** Navigate to the Newsletter Subscribers page
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /newsletter/subscriber/

## 5ee4350e91ecd4fba38e
- **题面：** View the Login as Customer Log to see login history
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /loginascustomer_log/log/index/

## 6589713cf83f391a811d
- **题面：** Access Templates in Content Elements.
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /pagebuilder/template/

## 6ef249e4262c7a65366f
- **题面：** Navigate to All Customers page to view and manage customer accounts.
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /customer/index/

## 742eb69ffc4e476779fd
- **题面：** Navigate to the Dashboard page from the admin panel.
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /admin/dashboard/

## 770e84f69b170c3ba8c7
- **题面：** Access Widgets to add dynamic content to your store.
- **分支：** admin-page-navigation-v2（源：remaining）
  - G1 【到达目标路径】到达目标路径 /admin/widget_instance/

## 7c5fe84f24b796184e43
- **题面：** View reports on products currently in customer carts.
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /reports/report_shopcart/product/

## 81a379f0551db8dcdf05
- **题面：** Go to Blocks to manage reusable content blocks.
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /cms/block/

## 83cc5308e9d6d5c546a0
- **题面：** View payment transactions.
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /sales/transactions/

## 87ef525083f13676f985
- **题面：** Access Customer Reviews report.
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /reports/report_review/customer/

## 8e723842fabefd41edd2
- **题面：** Check Shipping reports.
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /reports/report_sales/shipping/

## 8f383823f120146a87e8
- **题面：** Navigate to the Transactions page to view and manage payment transactions.
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /sales/transactions/

## 914d0005a85ecd74dc7c
- **题面：** Review pending product reviews in the User Content section
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /review/product/pending/

## 98f11124b6774718d6c3
- **题面：** Access the Ordered Products report to track product sales performance.
- **分支：** admin-page-navigation-v2（源：remaining）
  - G1 【到达目标路径】到达目标路径 /reports/report_product/sold/

## 998cd1e1da684487cc15
- **题面：** Access the Transactions section to review payment transactions
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /sales/transactions/

## 99f2735a501514a00c60
- **题面：** Navigate to the Site Map page
- **分支：** admin-page-navigation-v2（源：remaining）
  - G1 【到达目标路径】到达目标路径 /admin/sitemap/

## 9d081b9f92bfe8923b7a
- **题面：** View all invoices in the Magento admin panel
- **分支：** admin-page-unfiltered-listing-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /sales/invoice/

## a0ab4cd75b59d31017fa
- **题面：** Navigate to the Products page to manage the product catalog.
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /catalog/product/

## a2f503b9548b6050f341
- **题面：** Access the Themes page to manage store design themes.
- **分支：** admin-page-navigation-v2（源：remaining）
  - G1 【到达目标路径】到达目标路径 /admin/system_design_theme/

## a2f7b302cadf8b9e1c2c
- **题面：** Navigate to the Dashboard from the Products page
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /admin/dashboard/

## a36f4efc37a9157949cd
- **题面：** View and manage newsletter subscribers.
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /newsletter/subscriber/

## a621fee204c3cc91b091
- **题面：** Go to the Shipments page to track and manage order shipments.
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /sales/shipment/

## af3770e756b32c5b726d
- **题面：** Go to the Customer Groups page to manage all customer groups
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /customer/group/

## b0975b785aaf2e81c1f9
- **题面：** Go back to the dashboard from the credit memo page
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /admin/dashboard/

## b667b6898eb0d4a4ff26
- **题面：** Access the Customer Groups page
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /customer/group/

## bb3a3fac9a1373a8fe52
- **题面：** Navigate to the Categories section in the Catalog menu
- **分支：** admin-page-navigation-v2（源：remaining）
  - G1 【到达目标路径】到达目标路径 /catalog/category/

## be70bc5b17446788991b
- **题面：** Navigate to the Dashboard page.
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /admin/dashboard/

## c3166d0a0c8ab825fc1f
- **题面：** Navigate to the Dashboard page in the Magento admin panel.
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /admin/dashboard/

## c5d0f5e308457fc25967
- **题面：** Visit the Credit Memos section for managing credit memos.
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /sales/creditmemo/

## caa61a4acbf4347558ac
- **题面：** Go to the Invoices page to manage billing documents
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /sales/invoice/

## d165fa1c58233af52006
- **题面：** List all newsletter problem reports.
- **分支：** admin-page-unfiltered-listing-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /newsletter/problem/

## dc7b46cdf861e834e35b
- **题面：** Access Page Templates
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /pagebuilder/template/

## dd4da374676ecf75cfb6
- **题面：** Navigate to the Orders section to view all customer orders
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /sales/order/

## e7eb1bdeeea9701f4173
- **题面：** Go to Design Configuration
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /theme/design_config/

## e9aba5949657447080e6
- **题面：** Review Credit Memos to manage customer refunds.
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /sales/creditmemo/

## f06b77b2331bb8209410
- **题面：** Navigate to the Site Map configuration page
- **分支：** admin-page-navigation-v2（源：remaining）
  - G1 【到达目标路径】到达目标路径 /admin/system_config/edit/section/sitemap/

## f1398ba03f2d29e60d67
- **题面：** Navigate to the Products section to manage store products
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /catalog/product/

## f2e0fbff3876d911b4d3
- **题面：** Navigate to the Dashboard page in Magento Admin.
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /admin/dashboard/

## f3e2449c36b23f7d6e99
- **题面：** Navigate to the Dashboard section by clicking the DASHBOARD link.
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /admin/dashboard/

## f42f69d990c4ffab9f35
- **题面：** Navigate to the Orders page to view all customer orders.
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /sales/order/

## f4a3593174d433446377
- **题面：** Go to the Design Configuration section to customize store design
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /theme/design_config/

## f4c60fbb7eda8516cbea
- **题面：** Go to the Invoices page to manage billing documents.
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /sales/invoice/

## fb1530b2f54846e6dc87
- **题面：** Navigate to Billing Agreements
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /paypal/billing_agreement/

## fc8f01c7c7e4f57875c3
- **题面：** View customer order count reports.
- **分支：** admin-page-navigation-v1（源：remaining）
  - G1 【到达目标路径】到达目标路径 /reports/report_customer/orders/

## 0f2454466bc17d1e2cc2
- **题面：** Schedule the installed Magento Blank theme for Default Store View from January 1, 2027 through January 31, 2027, and save the schedule.
- **分支：** （源：remaining）
  - G1 【写操作结果】写操作结果状态精确
  - G2 【保存生效】结果已保存

## a56c2d7739536c91fdd3
- **题面：** Create and save a search synonym group containing exactly "fitness tracker" and "activity tracker", scoped to All Websites.
- **分支：** （源：remaining）
  - G1 【写操作结果】写操作结果状态精确
  - G2 【保存生效】结果已保存

## 104066102ddb5b510b0d
- **题面：** For this local training variant, navigate to the Issues page for the Byte Blaze / a11y-syntax-highlighting project.
- **分支：** （源：remaining）
  - G1 【到达目标路径】最终路径匹配目标 /byteblaze/a11y-syntax-highlighting/-/issues
  - G2 【标题/身份匹配】页面标题/目标身份匹配 ^Issues.*a11y\-syntax\-highlighting.*GitLab$

## 2b189826938239798f93
- **题面：** Check who the contributors are to the A11Y Project.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Check who the contributors are to the A11Y Project.

## 2dde6194b86bf76d25b9
- **题面：** Search for guides on how to write accessible alt text for images.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 2e6315cc8d029eb9e78a
- **题面：** Learn how to mention subgroups in issues and merge requests
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Learn how to mention subgroups in issues and merge requests

## 6addb348032f05c09678
- **题面：** Learn about the benefits of creating subgroups in GitLab by clicking the "Learn more about subgroups" link.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Learn about the benefits of creating subgroups in GitLab by clicking the "Learn 

## 7e1ecbfe83910a7f3ae7
- **题面：** Check if there are versions of cloud-to-butt for browsers other than Chrome
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Check if there are versions of cloud-to-butt for browsers other than Chrome

## 9da3e5f38722764ba141
- **题面：** Learn what subgroups are in GitLab and how they can be used to organize projects
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Learn what subgroups are in GitLab and how they can be used to organize projects

## b6b1755abdbf3d7b075e
- **题面：** Understand the difference between Private, Internal, and Public visibility levels for groups
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Understand the difference between Private, Internal, and Public visibility level

## 393940f1369ec92cb2ad
- **题面：** Add 3 units of the Pre-baked Gingerbread House Kit Value Pack to your cart.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 3 units of the Pre-baked Gingerbread House Kit Value Pack
  - G2 【目标位置】添加到 cart
  - G3 【保存生效】新建/添加已持久保存生效

## 877e61d97322417f1aea
- **题面：** Show pending to-do items for the The A11Y Project / a11yproject.com project.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Show pending to-do items for the The A11Y Project / a11yproject.com project.

## 8c6e741fb621a721d6dd
- **题面：** Add 5 units of the Pre-baked Gingerbread House Kit Value Pack to your cart.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 5 units of the Pre-baked Gingerbread House Kit Value Pack
  - G2 【目标位置】添加到 cart
  - G3 【保存生效】新建/添加已持久保存生效

## f3a6d339f865637a3d4f
- **题面：** Add 3 units of the Nightfox Vulpes Night Vision Goggles to your cart.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 3 units of the Nightfox Vulpes Night Vision Goggles
  - G2 【目标位置】添加到 cart
  - G3 【保存生效】新建/添加已持久保存生效

## 48b09951d684bc8c340f
- **题面：** Within the native search results for "song describes your love life", view all comments on any post tied for the highest exact native upvote score.
- **分支：** （源：remaining）
  - G1 【发布成功】发布成功：目标为 tied for the highest exact native upvote score

## adc6624ca0e224f6c7e1
- **题面：** Open the Forums directory, then open the Music forum from that directory. Finish on the Music forum page without changing site content.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Open the Forums directory, then open the Music forum from that directory. Finish on the Music forum page without changing site content.

## 55102868e4425a2690aa
- **题面：** View the credit memo history for order #000000002
- **分支：** admin-single-pass-rules-v3（源：remaining）
  - G1 【到达目标路径】到达目标路径 None

## 5eddb585793c30159e97
- **题面：** For order #000000002, add an internal comment to its credit memo with the exact text "Customer reported a product quality issue; review required." Save the comment without notifying the customer and without making it visible on the storefront. Do not issue another refund.
- **分支：** admin-single-pass-rules-v3（源：remaining）
  - G1 【评论文本】添加评论文本精确
  - G2 【保存生效】评论保存且加到正确对象

## 5f532160e2e20dbecd2b
- **题面：** Search the byteblaze/a11y-syntax-highlighting repository code for #00e0e0.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 743bfc193b93200e7646
- **题面：** Search Explore projects for a11y-syntax-highlighting.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 7e361fd5175194721c57
- **题面：** Open the Wiki for byteblaze/a11y-syntax-highlighting.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Open the Wiki for byteblaze/a11y-syntax-highlighting.

## 902e0a22bf229b593e13
- **题面：** Open the package registry for byteblaze/a11y-syntax-highlighting.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Open the package registry for byteblaze/a11y-syntax-highlighting.

## 9619659b2c186e114bf3
- **题面：** Browse the snippets for a11yproject/a11yproject.com.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 988309d846af4151a40f
- **题面：** View all tags for a11yproject/a11yproject.com.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：View all tags for a11yproject/a11yproject.com.

## b8fe3245dfa606c5d034
- **题面：** Sort your Dashboard projects by Most stars.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 your Dashboard projects
  - G2 【排序】按 Most stars 排序
  - G3 【保存生效】修改已持久保存生效

## c44c57073cbf6b729bb4
- **题面：** Copy the project ID of byteblaze/a11y-syntax-highlighting to the browser clipboard.
- **分支：** （源：remaining）
  - G1 【目标对象】操作针对的正确对象为 project ID of byteblaze/a11y-syntax-highlighting
  - G2 【复制】复制 project ID of byteblaze/a11y-syntax-highlighting 到剪贴板
  - G3 【保存生效】修改已持久保存生效

## eff2d0b72895814825aa
- **题面：** Change the global Bootstrap search scope from Issues to Merge requests, preserving the query.
- **分支：** （源：remaining）
  - G1 【Bootstrap search scope】Bootstrap search scope 从 "Issues" 改为 "Merge requests"
  - G2 【保存生效】修改已持久保存生效

## 65d44f1f647a37cce37a
- **题面：** For this local training variant, set the position of Erika Running Short within New Category Name to 10 and save the category.
- **分支：** （源：remaining）
  - G1 【分类参数】分类内位置/SKU 参数精确
  - G2 【保存生效】保存到正确分类

## 7dfd7947cbf21b1561b6
- **题面：** For this local training variant, use 2023-01-01 as the reference date. Apply the Orders date filter for the previous calendar month, December 1 through December 31, 2022, in the store display timezone, and leave the filtered grid open.
- **分支：** （源：remaining）
  - G1 【操作参数】操作参数精确
  - G2 【生效】操作已生效

## b3948d69b63665617e41
- **题面：** For this local training variant, search for product SKU WSH12 within New Category Name and leave the matching category product results displayed.
- **分支：** （源：remaining）
  - G1 【分类参数】分类内位置/SKU 参数精确
  - G2 【保存生效】保存到正确分类

## c8de5316f4877a385aa2
- **题面：** For this local training variant, create a simple product named Training Design Product with SKU TRAINING-DESIGN-PRODUCT and price 10.00 USD in the default catalog scope (All Store Views), set its design layout to 1 column, and save it.
- **分支：** （源：remaining）
  - G1 【操作参数】操作参数精确
  - G2 【生效】操作已生效

## cc8e3029d44462f11c13
- **题面：** For this local training variant, the Orders grid initially has keyword "Canceled" applied. Clear that keyword filter and leave the unfiltered Orders grid loaded.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【操作步骤】执行 UI 操作 、
  - G2 【到达路径】最终到达路径 /admin/sales/order/

## d18683a46643d64bc8bd
- **题面：** For this local training task, display the native Explore project directory of all non-archived projects accessible to the signed-in account. Leave the unfiltered project directory open without modifying site records.
- **分支：** （源：remaining）
  - G1 【退出成功】退出操作已成功执行

## f6f2f898a2458ab9d5d8
- **题面：** Restore the default columns on the Customers grid. The initial local view has the Name column hidden; restore the original default column set.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【操作步骤】执行 UI 操作 、、
  - G2 【到达路径】最终到达路径 /admin/customer/index/

## 601bcd890b3a0b8a68a4
- **题面：** View the estimated travel time by car from JFK Airport to Manhattan
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：View the estimated travel time by car from JFK Airport to Manhattan

## 760027033b012a85b33a
- **题面：** Find out which streets I need to take when driving from Central Park to Times Square.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## a6e74bffdde6f6df4a89
- **题面：** Explore different routing options between Midtown and Upper East Side Manhattan
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Explore different routing options between Midtown and Upper East Side Manhattan

## 850cac391b40707d949b
- **题面：** Search for credit memo #000000001 using the search box
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【过滤条件】过滤条件为 increment_id=000000001
  - G2 【结果字段】返回字段 increment_id 精确

## dc7d73783c9bb98a03ff
- **题面：** Filter credit memos by status "Refunded"
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【过滤条件】过滤条件为 state=2
  - G2 【结果字段】返回字段 increment_id 精确

## 021fa6a7f51c13d79d86
- **题面：** Extract the comment details made by user 7SlotGrill on March 31, 2023.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Extract the comment details made by user 7SlotGrill on March 31, 2023.

## 4185b3fd3ba2b6c5d1e8
- **题面：** Find all native forum names containing "gaming" in the alphabetical forum directory.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 5f5b21a7d63174b0114b
- **题面：** Search for posts about "Spider-Man" in the movies forum
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## fd4ecd3696bcc366c215
- **题面：** Count how many search results are from the nosleep subreddit
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Count how many search results are from the nosleep subreddit

## 02aa6fe34cb30dbacf7f
- **题面：** Find information about the data sources used in OpenStreetMap
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 4a313c582e7b15114ee4
- **题面：** Find out who the contributors are to OpenStreetMap
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## fa8bcff3cfeeff04fefc
- **题面：** Find out the license terms for OpenStreetMap data.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 0497c9f116f7434bd78e
- **题面：** List all accessible non-archived projects whose native Updated date is within 2021-03-23 through 2023-03-23, inclusive in UTC.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：List all accessible non-archived projects whose native Updated date is within 2021-03-23 through 2023-03-23, inclusive in UTC.

## 37beaff20228a7119e4f
- **题面：** On the current Explore page, list the full project paths whose displayed name or description contains Python, ignoring case.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：On the current Explore page, list the full project paths whose displayed name or description contains Python, ignoring case.

## 6c7fd41381e857c6b91c
- **题面：** List all accessible non-archived projects whose native Updated date is within 2023-02-23 through 2023-03-23, inclusive in UTC.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：List all accessible non-archived projects whose native Updated date is within 2023-02-23 through 2023-03-23, inclusive in UTC.

## c3d9a78436325e0dada1
- **题面：** Report the status of the latest pipeline attached to merge request !1531 in a11yproject/a11yproject.com.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Report the status of the latest pipeline attached to merge request !1531 in a11yproject/a11yproject.com.

## cd82fbf6b56e3149e961
- **题面：** List all non-archived Explore projects with more than 20 stars. Return their full project paths.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：List all non-archived Explore projects with more than 20 stars. Return their full project paths.

## d11f656463a809915334
- **题面：** See when the "Explore less thin secondary font options" issue was last updated
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：See when the "Explore less thin secondary font options" issue was last updated

## 0b7f1d54eac2d68bb858
- **题面：** Determine the maximum area size that can be exported directly from OpenStreetMap.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Determine the maximum area size that can be exported directly from OpenStreetMap

## 277be4af3f5af765396d
- **题面：** Retrieve the bounding box coordinates for the current map view.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Retrieve the bounding box coordinates for the current map view.

## 227e6681d6fce338880e
- **题面：** Find out if there are any technology-related forums available
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 284810473d5423137bd6
- **题面：** View the current price of the Blue T-Shirt
- **分支：** admin-single-pass-rules-v3（源：remaining）
  - G1 【对象正确】返回题面指定实体
  - G2 【字段值精确】实体字段值与参考精确一致

## 5bdea638324ccae37801
- **题面：** View the SKU of the Blue T-Shirt
- **分支：** admin-single-pass-rules-v3（源：remaining）
  - G1 【对象正确】返回题面指定实体
  - G2 【字段值精确】实体字段值与参考精确一致

## 997fa3690ee26ce63c8b
- **题面：** Find the SKU number for the Yoga Mat Pro
- **分支：** admin-typed-query-v1（源：remaining）
  - G1 【记录正确】返回题面指定记录
  - G2 【字段值精确】指定字段值与参考精确一致

## ca0fa0363a5638a1c347
- **题面：** See the grand total amount for order #000000074
- **分支：** admin-typed-query-v1（源：remaining）
  - G1 【记录正确】返回题面指定记录
  - G2 【字段值精确】指定字段值与参考精确一致

## d24fc9d03c01ec50b6d3
- **题面：** Check if the Yoga Mat Pro is currently in stock
- **分支：** admin-typed-query-v1（源：remaining）
  - G1 【记录正确】返回题面指定记录
  - G2 【字段值精确】指定字段值与参考精确一致

## e5bd171b0b1550f4d11d
- **题面：** View the order status for order #000000002
- **分支：** admin-single-pass-rules-v3（源：remaining）
  - G1 【对象正确】返回题面指定实体
  - G2 【字段值精确】实体字段值与参考精确一致

## f892d8b609ce32484d7b
- **题面：** Get the price and stock status of the Blue T-Shirt.
- **分支：** admin-typed-query-v1（源：remaining）
  - G1 【记录正确】返回题面指定记录
  - G2 【字段值精确】指定字段值与参考精确一致

## 292ad3eb62765c7e6d93
- **题面：** Publish one image post titled "Beautiful Sunset at the Beach" in EarthPorn using the supplied fixed beach-sunset photograph. Confirm the native post saved the supplied image.
- **分支：** （源：remaining）
  - G1 【发布成功】发布成功：目标为 one image post titled Beautiful Sunset at the Beach in EarthPorn using the supplied fixed beach-sunset photograph

## dbab57fbe44ffe3192ec
- **题面：** Publish one image post titled "Landscape Photo" in the existing EarthPorn landscape photography forum using the supplied fixed landscape photograph. Confirm the native post saved the supplied image.
- **分支：** （源：remaining）
  - G1 【发布成功】发布成功：目标为 one image post titled Landscape Photo in the existing EarthPorn landscape photography forum using the supplied fixed landscape photograph

## 2bcee20a87bc7d2a364a
- **题面：** Find the most expensive available product across the entire Beauty & Personal Care category, using the native currently displayed final price. Return any maximum-price product, including a tie, with its exact name, SKU and price.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 6096f92056825746c39a
- **题面：** Check the complete currently available website catalogue for products whose names contain both Memory Foam and slippers and whose native final price is below the regular price. Return all matching on-sale products with their names, SKUs and prices, or an empty array when none qualify.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Check the complete currently available website catalogue for products whose names contain both Memory Foam and slippers and whose native final price is below the regular price. Return all matching on-sale products with their names, SKUs and prices, or an empty array when none qualify.

## 6c9859753d00a6ecdeb8
- **题面：** Count all currently available native website catalogue products with a native final price below their regular price. Count each product once, include the entire catalogue, and return on_sale_count as an integer.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Count all currently available native website catalogue products with a native final price below their regular price. Count each product once, include the entire catalogue, and return on_sale_count as an integer.

## ae21e102050d4eabc264
- **题面：** Find another currently available product whose name contains gingerbread, house and kit, excluding Pre-baked Gingerbread House Kit Value Pack, 17 oz., Pack of 2, Total 34 oz. Return at least one matching product with its exact name, SKU and current final price.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## bad2efa6e6e84fc81de4
- **题面：** Compare current final prices of at least two different available products whose names contain the whole word milk and at least one of vegan, almond, oat, soy or coconut. This training query uses that explicit name criterion; it does not infer dietary certification. Return their exact names, SKUs and prices.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Compare current final prices of at least two different available products whose names contain the whole word milk and at least one of vegan, almond, oat, soy or coconut. This training query uses that explicit name criterion; it does not infer dietary certification. Return their exact names, SKUs and prices.

## 40c60ae42c6e37d73c6b
- **题面：** Explore OpenStreetMap Local Chapters around the world
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Explore OpenStreetMap Local Chapters around the world

## 4edc660efd1a6b32f0e5
- **题面：** Find out more about the contributors to OpenStreetMap and the sources of their data.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## 6bf04a7d1ba5de3b970b
- **题面：** Find information about how to contribute to OpenStreetMap
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## cfa46549195e2139a434
- **题面：** Retrieve information about the OpenStreetMap community and its contributors.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Retrieve information about the OpenStreetMap community and its contributors.

## 44748c782495ad00b02f
- **题面：** Get the distance and estimated travel time for the route from 40.7570, -73.9860 to 40.7830, -73.9650.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Get the distance and estimated travel time for the route from 40.7570, -73.9860 

## 48512c07d2c18c94f3b0
- **题面：** Report the revenue, tax and shipping amounts currently displayed on the restored local dashboard, with All Store Views scope. Read the displayed dashboard figures; do not calculate a different sales period.
- **分支：** admin-declarative-contract-v3（源：remaining）
  - G1 【读取结果】读取 dashboard 展示数值与题面要求一致

## 6ab1a9d69b9bfd4885e4
- **题面：** Among currently available products whose names contain a whole word lip, lipstick, lipgloss, lipbalm or lipliner and that have approved customer reviews, find the maximum displayed percentage rating. Read an approved customer review of any product tied at that maximum and return its name, SKU, percentage rating, review title and review text. Normalize whitespace in the review title and text to single spaces.
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Among currently available products whose names contain a whole word lip, lipstick, lipgloss, lipbalm or lipliner and that have approved customer reviews, find the maximum displayed percentage rating. Read an approved customer review of any product tied at that maximum and return its name, SKU, percentage rating, review title and review text. Normalize whitespace in the review title and text to single spaces.

## 844f5158cdae0b1c86a5
- **题面：** Find the recorded estimated delivery date for your order 000000148 in its customer-visible order comments. Return estimated_delivery_date in YYYY-MM-DD format. This local training snapshot records an estimate; no live carrier estimate or actual delivery is requested.
- **分支：** （源：remaining）
  - G1 【搜索结果】搜索条件正确且结果页到达，结果集与本地真实状态一致

## ebbb24b8f7340577c0b5
- **题面：** Check the Keycloak JavaScript code
- **分支：** （源：remaining）
  - G1 【完成目标】完成题面声明的原子目标：Check the Keycloak JavaScript code
