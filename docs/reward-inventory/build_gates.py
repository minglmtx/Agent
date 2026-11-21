# -*- coding: utf-8 -*-
"""
gate 细分生成引擎 —— 从三份源清单逐题提炼「语义组 gate」。
口径（与用户确认）：
  - 每道题 = 一组 gate（G1..Gn），每条 gate 独立判对错，分值由下游 agent 按通过条数计算，本脚本不掺分值。
  - 一条 gate = 一个「语义组」：彼此语义独立、题目确实要求独立判断的才拆成独立 gate；
    天然构成一个语义整体的字段（如地址=街道+城市+州+邮编+国家）合并为一条 gate。
  - 只保留硬门槛（选对对象/做对动作/保存生效/结果精确/未动无关项），丢弃过程质量。
  - 隐含前提（page_valid / answer_schema / records_unchanged / same_local_deployment / valid_authenticated_page）
    不单独占 gate 分数，作为题目级「隐含前提」列出。

输入：docs/reward-inventory/*.md
输出：output/gates.json（机器可读）+ output/gates.md（人类可读）
"""
import re, json, os, hashlib

# 路径：以脚本自身位置为基准定位源清单与输出。
# 本脚本既可放在仓库根目录运行，也可放在 docs/reward-inventory/ 下运行。
_HERE = os.path.dirname(os.path.abspath(__file__))
if os.path.basename(_HERE) == "reward-inventory":
    # 脚本放在 docs/reward-inventory/ 下：源清单即同目录
    BASE = _HERE
    OUT = os.path.join(_HERE, "output")
else:
    # 脚本放在仓库根目录：源清单在 docs/reward-inventory/，输出在 output/
    BASE = os.path.join(_HERE, "docs", "reward-inventory")
    OUT = os.path.join(_HERE, "output")
os.makedirs(OUT, exist_ok=True)

# 隐含前提（不占 gate 分数，只做题目级说明）
IMPLICIT_PRE = {
    "page_valid": "页面有效可用",
    "answer_schema": "答案格式符合 schema",
    "requested_records_unchanged": "查询未改动目标记录",
    "records_unchanged": "相关记录保持未变",
    "other_records_unchanged": "目标以外的同实体记录保持未变",
    "existing_records_unchanged": "原有实体记录保持未变",
    "same_local_deployment": "终页属于原本地部署",
    "valid_authenticated_page": "终页未被标记为登录页/错误页",
}

def norm(s):
    return re.sub(r'\s+', ' ', s).strip()

# ---------------- 解析 binary ----------------
def parse_binary(path):
    txt = open(path, encoding="utf-8").read()
    blocks = re.split(r'\n## 题目 \d+（([0-9a-f]+)）\n', txt)
    # blocks = [head, id1, body1, id2, body2, ...]
    items = []
    for i in range(1, len(blocks), 2):
        tid = blocks[i]
        body = blocks[i+1]
        stmt = re.search(r'\*\*题面：\*\*\s*(.*)', body)
        stmt = norm(stmt.group(1)) if stmt else ""
        branch_m = re.search(r'原分支 `([^`]+)`', body)
        branch = branch_m.group(1) if branch_m else ""
        # 提取谓词段：xxx: 描述
        preds = re.findall(r'([a-z_][a-z_0-9]*):\s*([^；;。]+)', body.split('原有前提')[0])
        # 若「原有前提/限制」行里还有 answer_xxx 字段（如 answer_title），补入 preds 以便提炼 gate
        lim = re.search(r'原有前提/限制：\*\*\s*(.*)', body)
        if lim:
            for f in re.findall(r'answer_([a-z_0-9]+)', lim.group(1)):
                if f != "schema":
                    preds.append(("answer_" + f, "提交的 " + f + " 满足原比较规则"))
        # 若带内嵌 native_contract JSON，则解析之（导航类题）
        contract = {}
        jm = re.search(r'```json\n(.*?)\n```', body, re.S)
        if jm:
            try:
                contract = json.loads(jm.group(1))
            except Exception:
                contract = {}
        items.append({"task_id": tid, "statement": stmt, "branch": branch, "preds": preds,
                      "contract": contract, "src": "binary"})
    return items

# ---------------- 解析 non-binary ----------------
def parse_nonbinary(path):
    txt = open(path, encoding="utf-8").read()
    blocks = re.split(r'\n## 题目 \d+（([0-9a-f]+)）\n', txt)
    items = []
    for i in range(1, len(blocks), 2):
        tid = blocks[i]
        body = blocks[i+1]
        stmt = re.search(r'\*\*题面：\*\*\s*(.*)', body)
        stmt = norm(stmt.group(1)) if stmt else ""
        branch_m = re.search(r'原分支 `([^`]+)`', body)
        branch = branch_m.group(1) if branch_m else ""
        # 提取谓词
        preds = re.findall(r'([a-z_][a-z_0-9]*):\s*([^；;。]+)', body.split('原有前提')[0])
        # 目前评分准则里的「固定分母 N 计分」字段分组
        cur = re.search(r'目前的评分准则：\*\*\s*(.*)', body)
        cur = norm(cur.group(1)) if cur else ""
        contract = {}
        jm = re.search(r'```json\n(.*?)\n```', body, re.S)
        if jm:
            try:
                contract = json.loads(jm.group(1))
            except Exception:
                contract = {}
        items.append({"task_id": tid, "statement": stmt, "branch": branch, "preds": preds,
                      "cur_criteria": cur, "body": body, "contract": contract, "src": "non-binary"})
    return items

# ---------------- 解析 remaining ----------------
def parse_remaining(path):
    txt = open(path, encoding="utf-8").read()
    blocks = re.split(r'\n## 题目 \d+（([0-9a-f]+)）\n', txt)
    items = []
    for i in range(1, len(blocks), 2):
        tid = blocks[i]
        body = blocks[i+1]
        stmt = re.search(r'\*\*题面：\*\*\s*(.*)', body)
        stmt = norm(stmt.group(1)) if stmt else ""
        jm = re.search(r'```json\n(.*?)\n```', body, re.S)
        contract = {}
        if jm:
            try:
                contract = json.loads(jm.group(1))
            except Exception:
                contract = {}
        branch_m = re.search(r'native evaluator `([^`]+)`', body)
        branch = branch_m.group(1) if branch_m else ""
        items.append({"task_id": tid, "statement": stmt, "branch": branch, "contract": contract, "src": "remaining"})
    return items

# ---------------- gate 提炼 ----------------
def field_group_name(f):
    """把 answer_xxx / 英文写操作字段 映射为人类可读中文语义名"""
    M = {
        "sku": "SKU", "price": "价格", "name": "名称", "email": "邮箱",
        "city": "城市", "region": "州/地区", "postal_code": "邮编", "postcode": "邮编",
        "country_code": "国家", "country_id": "国家", "telephone": "电话", "phone": "电话",
        "street": "街道地址", "firstname": "名", "lastname": "姓",
        "comment_count": "评论数", "rating_percent": "评分", "review_count": "评论数",
        "fork_count": "fork 数", "star_count": "star 数", "starred_project_count": "star 项目数",
        "author": "作者", "title": "标题", "username": "用户名", "forum_name": "版块名",
        "open_issue_count": "open issue 数", "all_issue_count": "issue 总数",
        "submission_count": "提交数", "submission_date": "提交日期", "updated_date": "更新日期",
        "license_type": "许可证类型", "subscription_status": "订阅状态", "stock_status": "库存状态",
        "manufacturer": "制造商", "duration_minutes": "时长", "distance_km": "距离",
        "item_count": "商品数", "items_subtotal": "商品小计", "grand_total": "总金额",
        "increment_id": "订单号", "shipping_method": "配送方式", "shipping_cost": "运费",
        "status": "状态", "exists": "存在性", "has_subscribers": "是否有订阅者",
        "free_shipping_available": "是否免运费", "alternative_shipping_available": "是否有替代配送",
        "power_cord_included": "是否含电源线", "whitelisted": "是否在白名单", "dark_mode": "是否深色模式",
        # 写操作题常见字段（change/set/update 提取的英文字段名）
        "visibility": "可见性", "visibility level": "可见性", "country": "国家",
        "transportation mode": "交通方式", "shipping method": "配送方式",
        "map layer": "地图图层", "map style": "地图样式", "map layers": "地图图层",
        "notification level": "通知级别", "image-export scale": "导出比例",
        "logo image": "Logo 图片", "amenity": "设施类型", "quantity": "数量",
        "zoom level": "缩放级别", "appearance": "外观", "theme": "主题",
        "front page filter": "首页筛选", "front page sort order": "首页排序",
        "default filter": "默认筛选", "language preference": "语言偏好",
        "time zone": "时区", "full name": "全名", "product view": "商品视图",
        "advanced search": "高级搜索", "search scope": "搜索范围",
        "sort order": "排序方式", "shipping address": "收货地址",
        "billing address": "账单地址", "payment method": "支付方式",
        "scale": "比例尺", "size": "尺寸", "value": "值", "filter": "筛选",
        "destination": "目的地", "origin": "起点", "route": "路线",
        "open merge request count": "打开的合并请求数", "all merge request count": "合并请求总数",
        "notification level": "通知级别", "visibility level": "可见性级别",
        "subtotal": "商品小计", "shipping cost": "运费", "car duration minutes": "驾车时长",
        "cycling duration minutes": "骑行时长", "duration minutes": "时长",
        "bicycle duration minutes": "骑行时长",
        "order total": "订单总额", "total correct": "总额正确性",
        # binary 普通查询的英文字段名
        "created at": "创建时间", "released date": "发布日期", "storage size": "存储大小",
        "contact form url": "联系表单链接", "material": "材质", "magnification": "放大倍数",
        "completed at": "完成时间", "engine": "引擎", "payment methods": "支付方式",
        "assigned by": "分配人", "order total": "订单总额", "product": "商品",
        "file updated date": "文件更新日期", "completed todo count": "已完成待办数",
        "pending todo count": "待办数", "project": "项目", "declared language": "声明语言",
        "negative review date": "差评日期", "net score": "净评分", "tag": "标签",
        "excluded websites": "排除网站", "commit count": "提交次数", "registration date": "注册日期",
        "oldest todo title": "最早待办标题", "projects": "项目", "search query": "搜索词",
        "advanced search": "高级搜索",
        "count": "数量", "order status": "订单状态", "group name": "组名",
        "visibility filter": "可见性筛选", "view": "视图", "todo count": "待办数",
        "image format": "图片格式", "sort order": "排序方式", "full name": "全名",
        "number": "数量", "quantity": "数量", "sorting": "排序", "sort": "排序",
        "sorting order": "排序方式", "cart quantity": "数量",
        "transportation mode": "交通方式", "bicycle": "自行车", "driving": "驾车",
        "starting point": "起点", "destination point": "终点", "search scope": "搜索范围",
        "map layer style": "地图图层样式", "map layer": "地图图层",
    }
    f = f.strip()
    fl = f.lower()
    # 归一化字典键：把下划线键也以空格形式加入，避免键混用下划线/空格导致漏翻译
    M2 = {}
    for k, v in M.items():
        M2[k] = v
        M2[k.replace("_", " ")] = v
    M = M2
    if fl in M:
        return M[fl]
    # 下划线归一化为空格再查（answer_car_duration_minutes -> car duration minutes）
    fl_space = fl.replace("_", " ")
    if fl_space in M:
        return M[fl_space]
    # 去掉 answer_ / answer 空格 前缀再查（shipping_/billing_ 保留在键里，因字段名含该限定词）
    fl2 = re.sub(r'^answer[ _]+', '', fl_space)
    if fl2 in M:
        return M[fl2]
    # 再去 shipping_/billing_ 前缀查一次（如 shipping_street -> street）
    fl3 = re.sub(r'^(shipping[ _]|billing[ _])+', '', fl2)
    if fl3 in M and fl3 != fl2:
        return M[fl3]
    # 复合字段（如 "its price" / "and its amenity"）提取核心词
    core = re.sub(r'^(the\s+|its\s+|and\s+|save\s+the\s+|set\s+the\s+)', '', fl)
    if core in M:
        return M[core]
    return f.replace("_", " ")

def make_gates_from_criteria(cur_criteria):
    """从 non-binary 的「目前评分准则」里提取语义组 gate。
    格式：语义名（字段：f1, f2；组内 AND）；语义名（字段：f3；组内 AND）...
    每个「语义名」就是一个语义组 gate。
    注意：export/collection_query 的原文按「目标N」逐条记录展开（固定分母口径），
    同一字段集合在每条记录上重复出现；本函数按「字段集合」去重，合并为一条语义组 gate。"""
    gates = []
    # 去掉「前提通过后，按固定分母 N 计分：」前缀
    body = re.sub(r'^前提通过后，按固定分母\s*\d+\s*计分[:：]\s*', '', cur_criteria)
    units = re.findall(r'([^；;（）()]+)[（(]字段[:：]([^）)]*)[）)]', body)
    seen = {}  # 用字段元组做去重键
    addr = {"street","city","region","postal_code","postcode","country_code","country_id"}
    addr_accum = []  # 地址类字段归并
    for gname, raw in units:
        gname = gname.strip()
        gname = re.sub(r'^目标\s*\d+\s*[:：]\s*', '', gname).strip()  # 去「目标N：」
        fields = [f.strip() for f in raw.split(',') if f.strip()]
        # 清理字段名里可能混入的「；组内 AND」等尾随文字
        fields = [re.sub(r'[；;]\s*组内\s*AND.*$', '', f).strip() for f in fields]
        # 去 answer_ / shipping_ / billing_ 前缀
        fields = [re.sub(r'^(answer_|shipping_|billing_)', '', f) for f in fields]
        fields = [f for f in fields if f and f not in ("schema",)]
        # 若语义名是 answer_xxx / answer xxx / 复合 answer 字段名，转为中文语义名
        if re.search(r'answer[ _]', gname, re.I):
            parts = [field_group_name(p) for p in re.split(r'\s*\+\s*', gname)]
            gname = " + ".join(parts)
        elif re.fullmatch(r'[a-z][a-z_ ]*', gname) and len(gname) < 30:
            # 纯英文语义名（单字段），尝试翻译
            translated = field_group_name(gname)
            if translated != gname.replace("_", " "):
                gname = translated
        if not fields:
            # 空字段（如「实际新增并保存有效对象」）单独一条
            key = ("__nofield__", gname)
            if key not in seen:
                seen[key] = gname
                gates.append({"group": (gname or "正确结果"), "fields": [],
                              "cond": (gname + "，与题面要求精确一致") if gname else "结果与题面要求精确一致"})
            continue
        # 地址类字段归并（去前缀后匹配）
        if set(fields) & addr:
            addr_accum.append((gname, fields))
            continue
        key = tuple(sorted(set(fields)))
        if key in seen:
            continue
        seen[key] = gname
        g = gname
        # 去掉语义名里已含的「正确」避免重复
        cond = (g + "与参考精确一致") if g else "结果与参考精确一致"
        gates.append({"group": g, "fields": fields, "cond": cond})
    # 地址字段合并为一条
    if addr_accum:
        all_fields = []
        for _, fs in addr_accum:
            for f in fs:
                if f not in all_fields:
                    all_fields.append(f)
        gates.append({"group": "完整地址", "fields": all_fields,
                      "cond": f"完整地址各字段（{', '.join(all_fields)}）与参考精确一致"})
    if not gates:
        gates = [{"group": "正确结果", "fields": [], "cond": "返回题面要求的正确结果与参考一致"}]
    return gates

def make_gates_ordinary(preds):
    """普通查询：每个 answer_ 字段一个语义组；多字段按语义合并（地址类合并）。"""
    answer_fields = []
    for name, desc in preds:
        if name.startswith("answer_") and name != "answer_schema":
            answer_fields.append(name[len("answer_"):])
    answer_fields = list(dict.fromkeys(answer_fields))  # 去重保序
    if not answer_fields:
        return [], []
    gates = []
    # 地址语义组合并：street/city/region/postal_code/postcode/country_code/country_id
    addr = ["street","city","region","postal_code","postcode","country_code","country_id"]
    addr_present = [f for f in answer_fields if f in addr]
    others = [f for f in answer_fields if f not in addr]
    if addr_present:
        gates.append({"group": "完整地址", "fields": addr_present,
                      "cond": "完整地址各字段（街道/城市/州/邮编/国家）与参考值精确一致"})
    for f in others:
        gates.append({"group": field_group_name(f), "fields": [f],
                      "cond": f"字段 {f}（{field_group_name(f)}）与参考值精确一致"})
    # 隐含前提
    implicit = []
    for name, desc in preds:
        if name in IMPLICIT_PRE:
            implicit.append(IMPLICIT_PRE[name])
    return gates, list(dict.fromkeys(implicit))

def make_gates_update(preds, statement):
    """写操作：目标对象 / 目标值 / 保存生效 / 未动无关项。"""
    gates = [
        {"group": "目标对象", "fields": [], "cond": "操作对象为题面指定目标（产品/客户组/记录身份正确，非同名/新建替代）"},
        {"group": "目标值", "fields": [], "cond": "目标字段最终值精确满足题面要求（persisted_requested_value / update_matches）"},
        {"group": "保存生效", "fields": [], "cond": "赋值已持久保存并在保存后复查仍为目标值"},
    ]
    if any(p[0] in ("other_records_unchanged","existing_records_unchanged","records_unchanged") for p in preds):
        gates.append({"group": "未动无关项", "fields": [], "cond": "目标以外的同实体记录/字段保持未变"})
    implicit = []
    for name, desc in preds:
        if name in IMPLICIT_PRE:
            implicit.append(IMPLICIT_PRE[name])
    return gates, list(dict.fromkeys(implicit))

def make_gates_collection(preds):
    gates = [
        {"group": "过滤条件", "fields": [], "cond": "搜索/过滤条件与题面一致（未放宽、未误用）"},
        {"group": "结果集精确", "fields": [], "cond": "结果集完整精确：无遗漏、无多余、无重复（exact_result_set）"},
    ]
    implicit = []
    for name, desc in preds:
        if name in IMPLICIT_PRE:
            implicit.append(IMPLICIT_PRE[name])
    return gates, list(dict.fromkeys(implicit))

# 写操作动词（用于识别 remaining 里的写操作题）
WRITE_VERBS = re.compile(
    r'\b(create|save|change|set|update|add|remove|delete|edit|modify|assign|configure|rename|move|upload|enable|disable|mark|register|open a new|associate|log in|sign in|sort|filter|toggle|switch|apply|copy|clone|reverse|clear|reorder|rate|replace|hide|select|set up)\b',
    re.I)

# 单动作动词：一个动作 + 一个目标对象，无额外可独立判错字段（A 类，保持 1 条）
SINGLE_ACTION_VERBS = re.compile(
    r'\b(subscribe|unsubscribe|upvote|downvote|sign out|sign in|star|unstar|follow|unfollow|join|leave|fork|publish|post|submit|reply|share|vote|restore|reopen|close|download|export|import)\b',
    re.I)

# 单动作动词 → 中文动作名
ACTION_CN = {
    "subscribe": "订阅", "unsubscribe": "取消订阅", "upvote": "点赞", "downvote": "点踩",
    "sign out": "登出", "sign in": "登录", "star": "星标", "unstar": "取消星标",
    "follow": "关注", "unfollow": "取消关注", "join": "加入", "leave": "退出",
    "fork": "Fork", "publish": "发布", "post": "发布", "submit": "提交", "reply": "回复",
    "share": "分享", "vote": "投票", "restore": "恢复", "reopen": "重新打开",
    "close": "关闭", "download": "下载", "export": "导出", "import": "导入",
}

def make_gates_single_action(statement):
    """A 类单动作题：一个动作 + 一个目标对象，无额外字段。
    产出 1 条 gate，语义 = 「动作成功 + 目标对象」。"""
    s = statement
    # 找出第一个命中的单动作动词
    action = None
    for m in SINGLE_ACTION_VERBS.finditer(s):
        action = m.group(1).lower()
        break
    if not action:
        return None
    cn = ACTION_CN.get(action, action)
    # 提取目标对象：动词后的目标短语
    # 常见：subscribe to the X forum / upvote the article "T" / star the X project / fork the X repository / sign out of your account
    obj = ""
    # 订阅/加入/关注：... to the <X>
    m = re.search(r'\b(?:subscribe|unsubscribe|join|follow|unfollow)\s+to\s+(?:the\s+)?(.+?)(?:\.|$)', s, re.I)
    if m:
        obj = m.group(1).strip()
    # 点赞/点踩/星标/fork：<verb> the <X>
    if not obj:
        m = re.search(r'\b(?:upvote|downvote|star|unstar|fork|publish|post|submit|reply|share|restore|reopen|close)\s+(?:the\s+)?(.+?)(?:\.|$)', s, re.I)
        if m:
            obj = m.group(1).strip()
    # 登出/登录：sign out of / sign in to
    if not obj:
        m = re.search(r'\b(?:sign out|sign in)\s+(?:of|to)\s+(.+?)(?:\.|$)', s, re.I)
        if m:
            obj = m.group(1).strip()
    # 下载/导出/导入：download/export/import <X>
    if not obj:
        m = re.search(r'\b(?:download|export|import)\s+(?:the\s+)?(.+?)(?:\.|$)', s, re.I)
        if m:
            obj = m.group(1).strip()
    # 清理对象
    if obj:
        obj = re.sub(r'[“”"\'「」]', '', obj).strip()
        # 截断尾部的介词短语（to your own account / for future reference 等）
        obj = re.sub(r'\s+(?:to\s+your\s+own\s+account|for\s+future\s+reference|to\s+receive\s+updates|from\s+the\s+Recently\s+Ordered\s+section)\s*$', '', obj, flags=re.I).strip()
    if obj:
        cond = f"{cn}成功：目标为 {obj}"
    else:
        cond = f"{cn}操作已成功执行"
    return [{"group": f"{cn}成功", "fields": [], "cond": cond}]

def clean_value(v):
    """清理字段值：去引号、截断尾随介词短语/从句残留。"""
    v = re.sub(r'[“”"\'「」]', '', v).strip()
    # 截断 "X for ..." / "X in the ..." / "X and save ..." / "X when ..." / "X to ..." 等尾随
    v = re.sub(r'\s+(?:for|in\s+the|and\s+save|and\s+download|and\s+confirm|to\s+see|to\s+display|start\s+in|Start\s+in|when|while|without|preserving|to\s+get)\s+.*$', '', v, flags=re.I).strip()
    return v

def trim_field_name(fname):
    """收缩字段名：去掉对象限定词（of X / its / your / the 等）之前的部分，
    只保留语义核心（如 "sort order of jokes" → "sort order"、"size of the X item" → "size"）。"""
    fname = fname.strip()
    # 1. 去掉 "of X" 结构（of 后面是对象描述，不是字段本身）
    m = re.search(r'\bof\s+(the\s+)?', fname, re.I)
    if m:
        # of 前面的部分才是字段（sort order / size / number），of 后是对象
        head = fname[:m.start()].strip()
        # 但 "number of items displayed per page" 里 "number" 是字段，"items displayed per page" 是说明
        # 保留 head 作为字段名
        if head:
            fname = head
    # 2. 去掉 "its saved" / "its" / "your" / "the" / "saved" / "gitlab" / "global" 前缀
    fname = re.sub(r'^(its\s+|your\s+|the\s+|saved\s+|gitlab\s+|global\s+)+', '', fname, flags=re.I).strip()
    # 3. 若含对象限定词，截取其后（取最后的语义核心）
    for marker in ("project", "group", "repository", "product", "item", "order", "account"):
        if marker in fname.lower():
            idx = fname.lower().rfind(marker)
            tail = fname[idx + len(marker):].strip()
            if tail:
                return tail.lstrip(" /-")
    return fname

def make_gates_write_statement(statement, contract):
    """从题面提炼写操作题的字段级 gate。
    结构 = [目标对象] + [题面列出的每个独立字段] + [保存生效]。
    只拆「题面明确列出、且彼此可独立出错」的字段；单一字段不拆。"""
    gates = []
    s = statement
    target = None
    fields = []  # (group, cond)

    # ---- 识别目标对象 ----
    # "for <Name>" / "for user <Name>" / "of <对象>"
    m = re.search(r'\bfor\s+(?:user\s+)?([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)?)', s)
    if m:
        target = m.group(1)
    # "named X" / "called X" / "titled X" 的 X 若是新建对象名，则字段而非目标

    # ---- 识别字段（按模式） ----
    # 收集 from...to 已覆盖的区间，避免 to 模式重复
    covered = []

    # A) change/set/update X (of Y) from "A" to "B"（A/B 引号可选）
    # 注意：字段名与 from 之间不能跨句号（避免把后一句的 from...to 误当成本题的字段变更），
    # 也不能含 "to"（避免 "change X to Y ... from A to B" 里把背景 from...to 误当字段变更）
    for m in re.finditer(
        r'(?:change|set|update|modify|switch)\s+(?:the\s+)?([a-z][a-z &\-\/.]*?)(?:\s+of\s+the\s+(?:group|map|product|item|route|destination|origin))?\s+from\s+["\'“]?(.+?)["\'”]?\s+to\s+["\'“]?(.+?)["\'”]?(?=\.|,|;|$|\s+while\b|\s+without\b|\s+and\s+save\b|\s+and\s+keep\b|\s+Keep\b|\s+Start\b|\s+start\b|\s+for\b)',
        s, re.I):
        # 字段名若含句号或 "to"，说明跨句/跨结构了，跳过
        if '.' in m.group(1) or ' to ' in m.group(1).lower():
            continue
        fname_raw, a, b = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
        fname = field_group_name(trim_field_name(fname_raw))
        # 值边界：截断到句内合理边界
        a = clean_value(a); b = clean_value(b)
        fields.append((fname, f'{fname} 从 "{a}" 改为 "{b}"'))
        covered.append(m.span())

    # B) change/set X to "Y"（无 from，引号可选）
    for m in re.finditer(
        r'(?:change|set|update|modify|switch)\s+(?:the\s+)?([a-z][a-z &\-\/.]*?)(?:\s+of\s+the\s+(?:group|map|product|item|route))?\s+to\s+["\'“]?(.+?)["\'”]?(?=\.|,|;|$|\s+while\b|\s+without\b|\s+and\s+save\b|\s+and\s+keep\b|\s+Keep\b|\s+for\b|\s+in\s+the\b|\s+Start\b|\s+start\b)',
        s, re.I):
        if any(a <= m.start() < b for a, b in covered):
            continue
        # 字段名若含句号，说明跨句了，跳过
        if '.' in m.group(1):
            continue
        fname_raw, val = m.group(1).strip(), m.group(2).strip()
        fname = field_group_name(trim_field_name(fname_raw))
        if fname_raw.lower() in ("both", "all", "them", "it"):  # update both to X → 状态
            fname = "状态"
        val = clean_value(val)
        # 若值以动作动词开头（search/show/find/filter/sort/display），说明这是操作描述而非值，跳过字段拆分
        if re.match(r'^(search|show|find|filter|sort|display|list|return)\b', val, re.I):
            continue
        fields.append((fname, f'{fname} 改为 "{val}"'))
        covered.append(m.span())

    # C) move X to Y
    m = re.search(r'\bmove\s+(?:the\s+)?(.+?)\s+to\s+(?:the\s+|my\s+|your\s+)?(.+?)(?=\.|,|$)', s, re.I)
    if m:
        objx = re.sub(r'[“”"\'「」]', '', m.group(1)).strip()
        loc = re.sub(r'[“”"\'「」]', '', m.group(2)).strip()
        if not target:
            target = objx
        fields.append(("目标位置", f'移动到 {loc}'))

    # D) remove X from Y
    m = re.search(r'\bremove\s+(?:the\s+)?(.+?)\s+from\s+(?:the\s+|my\s+|your\s+)?(.+?)(?=\.|,|$)', s, re.I)
    if m:
        objx = re.sub(r'[“”"\'「」]', '', m.group(1)).strip()
        loc = re.sub(r'[“”"\'「」]', '', m.group(2)).strip()
        if not target:
            target = objx
        fields.append(("移除位置", f'从 {loc} 移除'))

    # E) save X as Y / its X as Y（收紧：仅限明确 save 语境，避免误匹配 mark...as / 地名 as）
    for m in re.finditer(r'(?:save\s+(?:the\s+|its\s+)?|its\s+)([a-z][a-z ]*?)\s+as\s+["\']?([^"\'.]+?)["\']?(?=\.|,|;|$|\s+and\b|\s+with\b)', s, re.I):
        fname_raw, val = m.group(1).strip(), m.group(2).strip()
        fname = field_group_name(fname_raw)
        if fname_raw.lower() in ("name", "amenity", "title", "body", "subject", "status", "its name", "its amenity"):
            if not any(g.lower() == fname.lower() for g, _ in fields):
                fields.append((fname, f'{fname} 保存为 "{clean_value(val)}"'))

    # wiki 页面：路径 + 标题 + 正文
    wiki_path = re.search(r'at\s+(/wiki/[^\s]+)', s)
    if wiki_path:
        fields.append(("路径", f'wiki 页面路径为 {wiki_path.group(1)}'))
    title_m = re.search(r'(?:with\s+)?title\s+[「"\']([^"\']+)[」"\']|titled\s+[「"\']([^"\']+)[」"\']', s)
    if title_m:
        t = title_m.group(1) or title_m.group(2)
        fields.append(("标题", f'标题精确为 "{t}"'))
    if re.search(r'exactly this body|body\s*:', s, re.I):
        fields.append(("正文", "正文内容与题面给定文本精确一致"))

    # group：名称 / 可见性 / 层级
    named_m = re.search(r'(?:named|name)\s+[「"\']([^"\']+)[」"\']', s)
    if named_m:
        fields.append(("名称", f'名称为 "{named_m.group(1)}"'))
    vis_m = re.search(r'\b(private|internal|public)\b\s*(?:visibility|gitlab group|group)?', s, re.I)
    # 仅当「可见性」是新建/修改 group 的属性时才拆（create/set up/change ... visibility），
    # 避免误伤 "filter projects by visibility (public, ...)" 这类过滤题
    is_group_ctx = bool(re.search(r'\b(create|set\s+up|change|new)\b.*\b(group|gitlab)\b', s, re.I) or re.search(r'\bvisibility\s+to\b|\bvisibility\s+level\b', s, re.I))
    if vis_m and is_group_ctx:
        fields.append(("可见性", f'可见性为 {vis_m.group(1).capitalize()}'))
    if re.search(r'\btop[- ]level\b', s, re.I):
        fields.append(("层级", "群组层级为 top-level"))
    # group 自定义 URL path
    urlp = re.search(r'(?:custom\s+)?URL\s+path\s+[「"\']([^"\']+)[」"\']', s, re.I)
    if urlp:
        fields.append(("路径", f'群组自定义 URL 路径为 "{urlp.group(1)}"'))
    # "Just me" / "Personal" 作为用户范围（GitLab group 可见性选项）
    jm = re.search(r'["\']?(?:Just\s+me|Personal)["\']?\s+selected\s+as\s+the\s+user', s, re.I)
    if jm:
        fields.append(("用户范围", '用户范围选择为 "Just me"（仅本人）'))

    # add <product> to <list>：目标对象 = 商品
    add_m = re.search(r'add\s+(?:the\s+)?[「"\']?([^「"\']+?)[「"\']?\s+to\s+(?:the\s+)?(?:your\s+|my\s+)?([a-z ]+?)(?:\.|$)', s, re.I)
    if add_m:
        if not target:
            target = add_m.group(1).strip()
        fields.append(("目标位置", f'添加到 {add_m.group(2).strip()}'))

    # mark X as done：目标对象是 X，字段是状态
    mark_m = re.search(r'mark\s+(?:the\s+)?(?:to-do|todo|item)?\s*[「"\']?([^「"\']+?)[「"\']?\s+as\s+(done|complete)', s, re.I)
    if mark_m:
        if not target:
            target = mark_m.group(1).strip()
        fields.append(("状态", f'状态标记为 {mark_m.group(2)}'))

    # change X（无 to/from 目标值）：如 Change the quantity / zoom level / transportation mode
    # 仅当上面的 change-to / change-from 都没命中时，给「变更字段」语义
    if re.search(r'\bchange\b', s, re.I) and not any(
        g in ("排序", "过滤条件", "切换", "目标值") or g in [f[0] for f in fields if f[0] not in ("目标对象", "保存生效")]
        for g, _ in fields):
        cm = re.search(r'\bchange\s+(?:the\s+)?(.+?)(?=\.|,|;|$|\s+of\s+items\b|\s+for\b|\s+to\b)', s, re.I)
        if cm and cm.group(1).strip():
            fields.append(("变更字段", f'变更 {cm.group(1).strip()}'))

    # ---- sort/filter/toggle/switch/apply/copy/clone/reverse/clear/reorder/rate ----

    # Modify the (current) Advanced Search to search/show only ... → 拆「搜索条件」
    adv_m = re.search(r'\b(?:modify|change|update)\s+(?:the\s+)?(?:current\s+)?advanced\s+search\s+to\s+(?:search\s+only\s+for|show|search\s+for)\s+(.+?)(?=\.|$)', s, re.I)
    if adv_m:
        cond = adv_m.group(1).strip()
        fields.append(("搜索条件", f'搜索条件改为：{cond}'))

    # sort X by Y (from A to B / ascending/descending)
    for m in re.finditer(r'\bsort\s+(?:the\s+)?([^,.;]+?)\s+by\s+(.+?)(?=\.|,|;|$|\s+preserving\b|\s+in\s+ascending\b|\s+in\s+descending\b)', s, re.I):
        objx = m.group(1).strip()
        key = m.group(2).strip()
        if not target:
            target = objx
        direction = ""
        dm = re.search(r'from\s+(?:the\s+)?(.+?)\s+to\s+(?:the\s+)?(.+?)(?=\.|,|;|$)', key, re.I)
        if dm:
            key = key[:dm.start()].strip()
            direction = f'（{dm.group(1)} → {dm.group(2)}）'
        fields.append(("排序", f'按 {key} 排序{direction}'))
    # sort ... ascending/descending（无 by 结构）
    if not any(g == "排序" for g, _ in fields):
        am = re.search(r'\bsort\s+(?:the\s+)?([^,.;]+?)\s+(?:in\s+)?(ascending|descending)', s, re.I)
        if am:
            if not target:
                target = am.group(1).strip()
            fields.append(("排序", f'按 {am.group(2)} 顺序排序'))

    # filter X to only show Y / filter X by Y
    # 注意：filter by visibility (public, ...) 这类，by 后是「维度名」，应作为过滤条件而非拆可见性
    for m in re.finditer(r'\bfilter\s+(?:the\s+)?([^,.;]+?)\s+(?:to\s+only\s+show|to\s+show)\s+(.+?)(?=\.|,|;|$|\s+preserving\b)', s, re.I):
        objx = m.group(1).strip()
        cond = m.group(2).strip()
        if not target:
            target = objx
        fields.append(("过滤条件", f'仅显示满足「{cond}」的项'))
    # filter X by <维度>（无 to show 结构，by 后是维度名）
    for m in re.finditer(r'\bfilter\s+(?:the\s+)?([^,.;]+?)\s+by\s+(.+?)(?=\.|,|;|$|\s+\(|\s+preserving\b)', s, re.I):
        if any(g == "过滤条件" for g, _ in fields):
            break
        objx = m.group(1).strip()
        cond = m.group(2).strip()
        if not target:
            target = objx
        fields.append(("过滤条件", f'按「{cond}」过滤'))
    # filter X by price range $A-$B / to prices from $A to $B
    pr = re.search(r'prices?\s+(?:from\s+)?\$?([\d,\.]+)\s*(?:-|to)\s*\$?([\d,\.]+)', s, re.I)
    if pr and not any(g == "过滤条件" for g, _ in fields):
        fields.append(("过滤条件", f'价格区间 ${pr.group(1)} - ${pr.group(2)}'))

    # filter X to one of these time periods ... + Choose Top/Most commented（论坛帖子：时间维度 + 排序维度）
    fp = re.search(r'\bfilter\s+(?:the\s+)?post\s+list\s+to\s+one\s+of\s+these\s+time\s+periods\b', s, re.I)
    if fp:
        fields.append(("时间过滤", "帖子列表时间维度过滤为「过去一天/周/月/年」之一"))
    if re.search(r'\bchoose\s+either\s+(Top|Most\s+commented)\b', s, re.I):
        fields.append(("排序方式", "排序方式选择 Top 或 Most commented 之一"))

    # toggle / switch：统一成「切换」语义
    # toggle X on/off / toggle between A and B
    tg_onoff = re.search(r'\btoggle\s+(?:the\s+)?([a-z][a-z ]*?)\s+(?:on\s*/\s*off|off\s*/\s*on)', s, re.I)
    if tg_onoff:
        fields.append(("切换", f'{tg_onoff.group(1).strip()} 在开/关之间切换'))
    elif re.search(r'\btoggle\s+(?:the\s+)?([a-z][a-z ]*?)\s+(?:between\s+)?', s, re.I):
        tgm = re.search(r'\btoggle\s+(?:the\s+)?(?:between\s+)?([a-z][a-z ]*?)(?:\s+and\s+[a-z ]+)?(?=\.|,|;|$)', s, re.I)
        if tgm:
            fields.append(("切换", f'{tgm.group(1).strip()} 模式已切换'))
        elif not fields:
            fields.append(("切换", "目标模式已切换"))
    # switch X to Y（appearance to Night / display from A to B）
    sw = re.search(r'\bswitch\s+(?:the\s+)?([a-z][a-z ]*?)\s+to\s+(.+?)(?=\.|,|;|$|\s+for\b|\s+start\b|\s+in\s+the\s+declared\b)', s, re.I)
    if sw:
        fields.append(("切换", f'{sw.group(1).strip()} 切换为 {sw.group(2).strip()}'))
    # switch from A to B（submission type 等）
    sw2 = re.search(r'\bswitch\s+from\s+(.+?)\s+to\s+(.+?)(?=\.|,|;|$)', s, re.I)
    if sw2:
        fields.append(("切换", f'从 {sw2.group(1).strip()} 切换为 {sw2.group(2).strip()}'))
    # switch to X（无中间名词：Switch to dark mode / Humanitarian style）
    if not any(g == "切换" for g, _ in fields):
        sw3 = re.search(r'\bswitch\s+to\s+(?:the\s+)?(.+?)(?=\.|,|;|$|\s+for\b|\s+start\b|\s+style\b)', s, re.I)
        if sw3:
            fields.append(("切换", f'切换到 {sw3.group(1).strip()}'))

    # enable / disable X（含 overlay/notifications/feature）
    for m in re.finditer(r'\b(enable|disable)\s+(?:the\s+)?(.+?)(?=\.|,|;|$|\s+for\b|\s+to\s+see\b|\s+to\s+display\b|\s+along\b|\s+and\b)', s, re.I):
        act = "启用" if m.group(1).lower() == "enable" else "停用"
        fields.append((act, f'{act} {m.group(2).strip()}'))

    # replace A with B（case-sensitive literal 等）
    rp = re.search(r'\breplace\s+(?:every\s+)?(.+?)\s+with\s+(.+?)(?=\.|,|;|$|\s+and\b|\s+in\b|\s+leaving\b)', s, re.I)
    if rp:
        fields.append(("替换", f'将 {rp.group(1).strip()} 替换为 {rp.group(2).strip()}'))

    # complete the purchase / place order → 下单
    if re.search(r'\b(?:complete\s+the\s+purchase|place\s+(?:the\s+)?order)\b', s, re.I):
        fields.append(("下单", "完成下单，创建订单"))
    # sign up for a new account → 注册
    if re.search(r'\bsign\s+up\b', s, re.I):
        fields.append(("注册", "完成新账户注册并建立登录会话"))
    # log in to X → 登录建立会话（单动作，语义精确）
    # 优先匹配「服务名 + account」（如 OpenStreetMap account）；无服务名则用通用文案
    li = re.search(r'\blog\s+in\s+(?:to\s+)?(?:your\s+|the\s+)?(?!account\b)([A-Za-z0-9 .&+-]+?)\s+account\b', s, re.I)
    if li:
        svc = li.group(1).strip()
        svc = re.sub(r'\s+(?:Use|using|Establish|Confirm|Provide)\b.*$', '', svc, flags=re.I).strip()
        if not svc or svc.lower() in ("your", "the", "own"):
            svc = "OpenStreetMap"
        fields.append(("登录会话", f'使用提供的本地账号信息登录 {svc} 账号并建立已登录会话'))
    # Start mapping by creating a(n) new account → 创建账号 + 确认注册邮件 + 建立登录会话
    if re.search(r'\bstart\s+mapping\b.*\b(?:creating|create)\s+(?:a\s+|an\s+)?(?:new\s+)?account\b', s, re.I):
        fields.append(("创建账号", "使用提供的本地账号信息创建并提交新账号"))
        if re.search(r'\bconfirm\b.*\bsignup\s+message\b', s, re.I):
            fields.append(("确认注册", "在本地收件箱确认实际注册/签到消息"))
        fields.append(("登录会话", "为该账号建立已登录会话"))

    # apply discount code X
    ap = re.search(r'\bapply\s+(?:the\s+)?(?:local\s+)?(?:discount\s+)?code\s+["\']?([A-Za-z0-9]+)["\']?', s, re.I)
    if ap:
        fields.append(("优惠码", f'应用优惠码 {ap.group(1)}'))

    # copy X (to clipboard)
    cp = re.search(r'\bcopy\s+(?:the\s+)?(.+?)(?=\.|,|$|\s+to\s+(?:the\s+)?(?:browser\s+)?clipboard)', s, re.I)
    if cp:
        objx = cp.group(1).strip()
        # 提取 copy 目标里 "for <repo>" 的仓库作为对象，而不是整个短语
        fm = re.search(r'\bfor\s+([a-zA-Z0-9/_.-]+)', objx)
        if fm:
            objx = fm.group(1)
        if not target:
            target = objx
        fields.append(("复制", f'复制 {objx} 到剪贴板'))

    # clone repo X（preserving branches/tags）
    cl = re.search(r'\bclone\s+(?:the\s+)?([a-zA-Z0-9/_.-]+)(?:\s+repository)?', s, re.I)
    if cl:
        if not target:
            target = cl.group(1)
        extra = "（保留所有分支与标签）" if re.search(r'preserving|all branches', s, re.I) else ""
        fields.append(("克隆", f'克隆仓库 {cl.group(1)} 到本地工作区{extra}'))

    # reverse the direction / start and end points
    rv = re.search(r'\breverse\s+(?:the\s+)?(.+?)(?=\.|,|;|$|\s+from\b|\s+to\s+get\b)', s, re.I)
    if rv:
        fields.append(("反转", f'反转 {rv.group(1).strip()}'))

    # clear all items from X
    clr = re.search(r'\bclear\s+(?:all\s+)?(?:items|item)s?\s+from\s+(?:the\s+|my\s+|your\s+)?(.+?)(?=\.|,|$)', s, re.I)
    if clr:
        fields.append(("清空", f'清空 {clr.group(1).strip()} 中的全部项'))

    # reorder items from order #X
    ro = re.search(r'\breorder\s+(?:items?\s+from\s+)?(?:your\s+)?(?:completed\s+)?(?:order\s+)?#?(\d+)', s, re.I)
    if ro:
        fields.append(("重新下单", f'从订单 #{ro.group(1)} 重新下单'))

    # rate X with N stars
    rt = re.search(r'\brate\s+(?:the\s+)?(.+?)\s+with\s+(\d+)\s+stars?', s, re.I)
    if rt:
        if not target:
            target = rt.group(1).strip()
        fields.append(("评分", f'评分为 {rt.group(2)} 星'))

    # upload X to Y
    up = re.search(r'\bupload\s+(?:the\s+)?(.+?)\s+to\s+(?:the\s+)?(.+?)(?=\.|,|;|$|\s+preserving\b|\s+and\s+commit\b)', s, re.I)
    if up:
        if not target:
            target = up.group(1).strip()
        fields.append(("上传", f'上传 {up.group(1).strip()} 到 {up.group(2).strip()}'))

    # hide X（from view）
    hd = re.search(r'\bhide\s+(?:the\s+)?(.+?)(?=\.|,|;|$|\s+from\s+view\b)', s, re.I)
    if hd:
        if not target:
            target = hd.group(1).strip()
        fields.append(("隐藏", f'隐藏 {hd.group(1).strip()}'))

    # select X instead of Y（选择具体项：支付方式/地图样式等单动作 + 明确值）
    sel = re.search(r'\bselect\s+(?:the\s+)?(.+?)\s+instead\s+of\s+(.+?)(?=\.|$)', s, re.I)
    if sel:
        chosen = sel.group(1).strip()
        alt = re.sub(r'\s+as\s+the\s+(?:current\s+)?.*$', '', sel.group(2).strip())
        fields.append(("选择", f'选择 {chosen}（而非 {alt}）'))
    # select and finish on the style (specifically designed for X)（选择具体样式/项）
    if not any(g == "选择" for g, _ in fields):
        sel2 = re.search(r'\bselect\s+and\s+finish\s+on\s+the\s+style\s+(?:specifically\s+)?(?:designed\s+for\s+)?(.+?)(?=\.|$)', s, re.I)
        if sel2:
            fields.append(("选择", f'选择「{sel2.group(1).strip()}」样式'))

    # F) 账单/收货地址 JSON：{"firstname":..., "street":...} → 按地址字段拆
    addr_json = re.search(r'\{[^{}]*"(?:firstname|street|city|postcode)"[^{}]*\}', s)
    if addr_json:
        try:
            import json as _json
            ao = _json.loads(addr_json.group(0))
            name_parts = []
            for k in ("firstname", "lastname"):
                if ao.get(k):
                    name_parts.append(ao[k])
            if name_parts:
                fields.append(("姓名", f'姓名保存为 "{" ".join(name_parts)}"'))
            addr_fields = []
            for k in ("street", "city", "region", "postcode", "country_id"):
                if ao.get(k):
                    addr_fields.append(f"{k}={ao[k]}")
            if addr_fields:
                fields.append(("完整地址", "地址各字段保存为 " + "、".join(addr_fields)))
            if ao.get("telephone"):
                fields.append(("电话", f'电话保存为 {ao["telephone"]}'))
        except Exception:
            pass

    # 去重字段（同 group 保留首个）
    seen_g = set()
    dedup_fields = []
    for g, c in fields:
        if g.lower() not in seen_g:
            seen_g.add(g.lower())
            dedup_fields.append((g, c))
    fields = dedup_fields

    # ---- 组装 gate ----
    # 新建/添加类：目标对象 = 新建对象本身（无独立 target 时给「新建对象」语义）
    is_create = bool(re.search(r'\bcreate\b|\bregister\b|\bnew\b|\badd\b|\bupload\b|\bopen a new\b|\bclone\b|\bsign up\b|\bset up\b', s, re.I))
    is_change = bool(re.search(r'\bchange\b|\bset\b|\bupdate\b|\bedit\b|\bmodify\b|\bmove\b|\brename\b|\bmark\b|\benable\b|\bdisable\b|\bremove\b|\bdelete\b|\bassociate\b|\bsort\b|\bfilter\b|\btoggle\b|\bswitch\b|\bapply\b|\bcopy\b|\breverse\b|\bclear\b|\breorder\b|\brate\b|\breplace\b|\bhide\b|\bselect\b', s, re.I))

    if target:
        gates.append({"group": "目标对象", "fields": [], "cond": f"操作针对的正确对象为 {target}"})
    elif is_create and not fields:
        gates.append({"group": "目标对象", "fields": [], "cond": "新建/添加的对象与题面要求一致"})

    for g, c in fields:
        gates.append({"group": g, "fields": [], "cond": c})

    # 保存生效（写操作最后一条）
    if is_create:
        gates.append({"group": "保存生效", "fields": [], "cond": "新建/添加已持久保存生效"})
    elif is_change:
        gates.append({"group": "保存生效", "fields": [], "cond": "修改已持久保存生效"})
    else:
        gates.append({"group": "保存生效", "fields": [], "cond": "写操作已持久保存生效"})

    # 若仍为空（极端兜底）
    if not gates:
        gates = [{"group": "正确结果", "fields": [], "cond": "题面要求的写操作已正确执行并保存"}]

    return gates, []

def make_gates_nav(contract, statement):
    """导航题：到达目标路径 + 标题/身份匹配（若 contract 有）。"""
    gates = []
    spec = contract.get("spec", {}) or {}
    completion = contract.get("completion", {}) or {}
    # 目标路径
    path = None
    if "control_target_path" in contract:
        path = contract["control_target_path"]
    elif "path_regex" in completion:
        path = completion["path_regex"]
    elif "target_path" in contract:
        path = contract["target_path"]
    if path:
        gates.append({"group": "到达目标路径", "fields": [], "cond": f"最终路径匹配目标 {path}"})
    # 标题/身份
    heading = completion.get("heading_regex") or completion.get("title_regex") or contract.get("menu_label")
    if heading:
        gates.append({"group": "标题/身份匹配", "fields": [], "cond": f"页面标题/目标身份匹配 {heading}"})
    if not gates:
        # 兜底：只有 goal_revision 或 completion_scope 时，给单一目标 gate
        goal = contract.get("goal_revision", {}).get("derived_goal", "") if isinstance(contract.get("goal_revision"), dict) else ""
        gates.append({"group": "完成目标", "fields": [], "cond": f"完成题面声明的原子目标：{goal or statement[:80]}"})
    return gates, []

def make_gates_admin_contract(contract, statement):
    """remaining 里带 spec.kind 的 admin 题。"""
    spec = contract.get("spec", {}) or {}
    kind = spec.get("kind", "")
    gates = []
    if kind in ("menu_navigation",):
        gates.append({"group": "到达菜单", "fields": [], "cond": f"到达菜单 {spec.get('menu_label') or spec.get('menu_id')}"})
    elif kind in ("page_navigation", "navigation"):
        target = spec.get("target_path") or spec.get("final_path") or contract.get("control_target_path")
        gates.append({"group": "到达目标路径", "fields": [], "cond": f"到达目标路径 {target}"})
    elif kind == "update":
        gates = [
            {"group": "目标对象", "fields": [], "cond": "操作对象为题面指定目标"},
            {"group": "目标值", "fields": [], "cond": "字段更新为精确值、scope 正确"},
            {"group": "保存生效", "fields": [], "cond": "保存生效且未动无关字段"},
        ]
    elif kind == "typed_query":
        gates = [
            {"group": "记录正确", "fields": [], "cond": "返回题面指定记录"},
            {"group": "字段值精确", "fields": [], "cond": "指定字段值与参考精确一致"},
        ]
    elif kind == "query":
        gates = [
            {"group": "对象正确", "fields": [], "cond": "返回题面指定实体"},
            {"group": "字段值精确", "fields": [], "cond": "实体字段值与参考精确一致"},
        ]
    elif kind == "comment":
        gates = [
            {"group": "评论文本", "fields": [], "cond": "添加评论文本精确"},
            {"group": "保存生效", "fields": [], "cond": "评论保存且加到正确对象"},
        ]
    elif kind == "native_mutation":
        gates = [
            {"group": "写操作结果", "fields": [], "cond": "写操作结果状态精确"},
            {"group": "保存生效", "fields": [], "cond": "结果已保存"},
        ]
    elif kind == "material_product_creation":
        gates = [
            {"group": "产品身份", "fields": [], "cond": "创建产品身份正确"},
            {"group": "产品字段", "fields": [], "cond": "价格/描述/图片等字段正确"},
            {"group": "未动其他", "fields": [], "cond": "未改变其他商品"},
        ]
    elif kind == "native_category_operation":
        gates = [
            {"group": "分类参数", "fields": [], "cond": "分类内位置/SKU 参数精确"},
            {"group": "保存生效", "fields": [], "cond": "保存到正确分类"},
        ]
    elif kind == "reviewed_admin_operation":
        gates = [
            {"group": "操作参数", "fields": [], "cond": "操作参数精确"},
            {"group": "生效", "fields": [], "cond": "操作已生效"},
        ]
    elif kind == "admin_contract":
        # admin-declarative-contract-v3，按 mode 精确拆分
        mode = spec.get("mode", "")
        match = spec.get("match", {}) or {}
        if mode == "tab":
            gates.append({"group": "到达标签页", "fields": [], "cond": f"到达 dashboard 标签页 {spec.get('tab_label')}"})
        elif mode == "page":
            tp = spec.get("target_path")
            hd = spec.get("heading")
            if tp:
                gates.append({"group": "到达目标路径", "fields": [], "cond": f"到达路径 {tp}"})
            if hd:
                gates.append({"group": "标题匹配", "fields": [], "cond": f"页面标题为 {hd}"})
            if not gates:
                gates.append({"group": "到达页面", "fields": [], "cond": "到达题面指定页面"})
        elif mode == "navigate":
            # match 里是对象身份（如 increment_id/name）
            ident = "、".join(f"{k}={v}" for k, v in match.items())
            gates.append({"group": "目标记录", "fields": [], "cond": f"打开题面指定记录（{ident}）"})
        elif mode == "panel":
            ident = "、".join(f"{k}={v}" for k, v in match.items())
            panels = spec.get("panel_labels") or []
            if ident:
                gates.append({"group": "目标对象", "fields": [], "cond": f"目标对象身份为 {ident}"})
            if panels:
                gates.append({"group": "展开面板", "fields": [], "cond": f"展开面板 {', '.join(panels)}"})
            if not gates:
                gates.append({"group": "到达面板", "fields": [], "cond": "到达题面指定面板"})
        elif mode == "form_panel":
            panels = spec.get("panel_labels") or []
            hd = spec.get("heading")
            if hd:
                gates.append({"group": "目标表单", "fields": [], "cond": f"目标表单为 {hd}"})
            if panels:
                gates.append({"group": "展开面板", "fields": [], "cond": f"展开面板 {', '.join(panels)}"})
            if not gates:
                gates.append({"group": "到达表单面板", "fields": [], "cond": "到达题面指定表单面板"})
        elif mode == "grid":
            cols = spec.get("columns") or []
            op = spec.get("operation", "")
            if cols:
                gates.append({"group": "列配置", "fields": [], "cond": f"网格列配置为 {', '.join(cols)}"})
            if op:
                gates.append({"group": "网格操作", "fields": [], "cond": f"网格执行操作 {op}"})
            if not gates:
                gates.append({"group": "网格配置", "fields": [], "cond": "完成题面要求的网格配置"})
        elif mode == "media":
            ident = "、".join(f"{k}={v}" for k, v in match.items())
            op = spec.get("operation", "")
            if ident:
                gates.append({"group": "目标对象", "fields": [], "cond": f"目标对象身份为 {ident}"})
            if op:
                opname = "移除全部图片" if op == "remove_all" else op
                gates.append({"group": "媒体操作", "fields": [], "cond": f"执行媒体操作 {opname} 且文件系统状态精确"})
            if not gates:
                gates.append({"group": "媒体操作", "fields": [], "cond": "完成题面要求的媒体操作"})
        elif mode == "collection_query":
            fields = spec.get("fields") or []
            ident = "、".join(f"{k}={v}" for k, v in match.items())
            if ident:
                gates.append({"group": "过滤条件", "fields": [], "cond": f"过滤条件为 {ident}"})
            if fields:
                gates.append({"group": "结果字段", "fields": [], "cond": f"返回字段 {', '.join(fields)} 精确"})
            if not gates:
                gates.append({"group": "结果集精确", "fields": [], "cond": "结果集精确：无遗漏、无多余"})
        elif mode == "ui_contract":
            steps = spec.get("control_steps") or []
            final_path = spec.get("required_final_path")
            goal = spec.get("derived_goal", "")
            if steps:
                stepnames = "、".join(s.get("name", "") for s in steps)
                gates.append({"group": "操作步骤", "fields": [], "cond": f"执行 UI 操作 {stepnames}"})
            if final_path:
                gates.append({"group": "到达路径", "fields": [], "cond": f"最终到达路径 {final_path}"})
            if not gates:
                gates.append({"group": "完成 UI 操作", "fields": [], "cond": goal or "完成题面要求的 UI 操作"})
        elif mode == "ui_query":
            goal = spec.get("derived_goal", "")
            gates.append({"group": "读取结果", "fields": [], "cond": f"读取 {spec.get('entity')} 展示数值与题面要求一致"})
        else:
            gates.append({"group": "完成声明操作", "fields": [], "cond": "完成 spec 声明的操作与结果状态"})
    else:
        # 兜底
        if contract.get("completion"):
            gates.append({"group": "完成目标", "fields": [], "cond": "完成 completion 声明的目标状态"})
        else:
            gates.append({"group": "完成目标", "fields": [], "cond": "完成题面声明的原子目标"})
    return gates, []

def refine_for_branch(item, gates, implicit):
    """根据 branch 做最终 gate 调整。"""
    branch = item.get("branch", "")
    if "update" in branch:
        return gates, implicit
    if "collection_query" in branch:
        return gates, implicit
    if "create" in branch:
        # create 语义：目标 + 新建记录字段正确 + 恰好一条 + 未动现有
        return [
            {"group": "新建记录", "fields": [], "cond": "新建且保存一条可唯一绑定的有效记录"},
            {"group": "记录字段", "fields": [], "cond": "新建记录的全部字段满足题面要求"},
            {"group": "未动现有", "fields": [], "cond": "原有记录保持未变"},
        ], implicit
    return gates, implicit

def build_item_gates(item):
    """返回该题的 gate 列表 + 隐含前提列表。"""
    gates, implicit = [], []
    branch = item.get("branch", "")
    if item["src"] == "binary":
        preds = item["preds"]
        # 若有内嵌 native_contract：优先 spec.kind → admin 题；否则 completion → 导航题
        contract = item.get("contract") or {}
        spec = contract.get("spec", {}) or {}
        if contract:
            if isinstance(spec, dict) and "kind" in spec:
                gates, implicit = make_gates_admin_contract(contract, item["statement"])
            elif "group_creation" in contract:
                # 创建 group 写操作：按题面字段拆（名称/可见性/层级/路径）
                gates, implicit = make_gates_write_statement(item["statement"], contract)
            elif contract.get("completion"):
                gates, implicit = make_gates_nav(contract, item["statement"])
            else:
                gates, implicit = make_gates_ordinary(preds)
            # 若仍为空，兜底
            if not gates:
                gates = [{"group": "正确结果", "fields": [], "cond": "返回题面要求的正确结果（值/目标与参考一致）"}]
            return gates, implicit
        if "ordinary_query" in branch:
            gates, implicit = make_gates_ordinary(preds)
            if not gates:
                gates = [{"group": "正确结果", "fields": [], "cond": "返回题面要求的正确结果（值/目标与参考一致）"}]
            return gates, implicit
        elif "collection_query" in branch:
            gates, implicit = make_gates_collection(preds)
        elif "update" in branch or "create" in branch:
            gates, implicit = make_gates_update(preds, item["statement"])
        elif "query" in branch or "links" in branch:
            # admin query / links：类似普通查询但谓词不同
            gates, implicit = make_gates_ordinary(preds) if any(p[0].startswith("answer_") for p in preds) else ([{"group":"结果精确","fields":[],"cond":"查询结果与参考精确一致"}], [])
        elif "pdf" in branch:
            gates = [{"group":"下载产物","fields":[],"cond":"下载产物内容与选中对象集合正确匹配"},{"group":"未生成真实标签","fields":[],"cond":"未生成/购买真实承运标签（若题面禁止）"}]
        elif "draft_reset" in branch:
            gates = [{"group":"草稿重置","fields":[],"cond":"草稿状态重置为要求状态"}]
        else:
            gates, implicit = make_gates_update(preds, item["statement"])
    elif item["src"] == "non-binary":
        contract = item.get("contract") or {}
        spec = contract.get("spec", {}) or {}
        if contract:
            if isinstance(spec, dict) and "kind" in spec:
                gates, implicit = make_gates_admin_contract(contract, item["statement"])
            elif contract.get("completion"):
                gates, implicit = make_gates_nav(contract, item["statement"])
            else:
                gates, implicit = make_gates_ordinary(item.get("preds", []))
            if not gates:
                gates = [{"group": "正确结果", "fields": [], "cond": "返回题面要求的正确结果（值/目标与参考一致）"}]
            return gates, implicit
        preds = item.get("body", "")
        # non-binary 的普通查询/create 等：优先用「目前评分准则」里的语义组（字段：xxx）
        cur = item.get("cur_criteria", "")
        if cur and ("字段：" in cur or "固定分母" in cur):
            gates = make_gates_from_criteria(cur)
            return gates, []
        # 用 body 里「判断器的判定条件」提取谓词
        pm = re.search(r'判断器的判定条件：\*\*(.*?)(?:\n|$)', preds, re.S)
        predtxt = pm.group(1) if pm else ""
        pred_pairs = re.findall(r'([a-z_][a-z_0-9]*):\s*([^；;。]+)', predtxt)
        if "ordinary_query" in branch:
            gates, implicit = make_gates_ordinary(pred_pairs)
        elif "collection_query" in branch:
            gates, implicit = make_gates_collection(pred_pairs)
        elif "create" in branch:
            gates = [
                {"group":"新建记录","fields":[],"cond":"新建且保存一条可唯一绑定的有效记录"},
                {"group":"记录字段","fields":[],"cond":"新建记录的全部字段满足题面要求"},
                {"group":"未动现有","fields":[],"cond":"原有记录保持未变"},
            ]
        elif "update" in branch:
            gates, implicit = make_gates_update(pred_pairs, item["statement"])
        elif "pdf" in branch:
            gates = [{"group":"下载产物","fields":[],"cond":"下载产物内容与选中对象集合正确匹配"}]
        elif "export" in branch:
            gates = [{"group":"导出对象","fields":[],"cond":"导出对象集合正确"},{"group":"导出完整","fields":[],"cond":"导出 CSV 内容完整无缺行缺字段"}]
        elif "bulk_update" in branch:
            gates = [{"group":"目标集合","fields":[],"cond":"目标记录集合正确"},{"group":"全部更新","fields":[],"cond":"集合内所有对象均满足更新条件"},{"group":"未动其他","fields":[],"cond":"其他记录保持未变"}]
        elif "page_text_query" in branch:
            gates = [{"group":"正确页面","fields":[],"cond":"终页路径为要求路径"},{"group":"描述正确","fields":[],"cond":"描述与参考一致"}]
        elif "mail" in branch:
            gates = [{"group":"目标订单","fields":[],"cond":"目标订单正确"},{"group":"邮件投递","fields":[],"cond":"本地捕获新邮件且收件人+订单号匹配"}]
        elif "query" in branch:
            gates, implicit = make_gates_ordinary(pred_pairs) if any(p[0].startswith("answer_") for p in pred_pairs) else ([{"group":"结果精确","fields":[],"cond":"查询结果与参考精确一致"}], [])
        else:
            gates, implicit = make_gates_update(pred_pairs, item["statement"])
    elif item["src"] == "remaining":
        contract = item.get("contract", {})
        spec = contract.get("spec", {}) or {}
        has_kind = isinstance(spec, dict) and "kind" in spec
        if has_kind:
            gates, implicit = make_gates_admin_contract(contract, item["statement"])
        else:
            # 无 spec.kind：优先判断是否写操作题（题面含写动词且 contract 非导航结构）
            # 清洗：去掉「result set」这类把 set 误当动词的短语，避免 Search 题误判
            stmt_for_verb = re.sub(r'result\s+set', '', item["statement"], flags=re.I)
            stmt_for_verb = re.sub(r'\bdata\s+set\b', '', stmt_for_verb, flags=re.I)
            is_write = bool(WRITE_VERBS.search(stmt_for_verb))
            is_single = bool(SINGLE_ACTION_VERBS.search(stmt_for_verb))
            is_search = bool(re.match(r'^\s*(?:For\s+this\s+local\s+training\s+variant,?\s*)?(?:Search|Find|Look\s+for|Browse)\b', item["statement"], re.I))
            # 「操作类」动词：即使 contract 有 completion（path_regex），题面核心也是操作而非到达
            op_verbs = re.compile(r'\b(sort|filter|toggle|switch|apply|copy|reverse|clear|reorder|rate|change|set|update)\b', re.I)
            is_op = bool(op_verbs.search(stmt_for_verb))
            # 下单/注册等明确写操作模式（complete 的形容词义需排除，故单独精准匹配）
            is_order = bool(re.search(r'\b(?:complete\s+the\s+purchase|place\s+(?:the\s+)?order|sign\s+up|create\s+an?\s+account)\b', item["statement"], re.I))
            # Start mapping by creating (a new) account：注册类写操作（creating 现在分词需单独匹配）
            is_signup = bool(re.search(r'\bstart\s+mapping\b.*\b(?:creating|create)\s+(?:a\s+|an\s+)?(?:new\s+)?account\b', item["statement"], re.I))
            # 「导航到页面」优先：题面以 Navigate/Open/Go to 开头且目标是 page/IDE 等页面，
            # 即使句中含 edit/modify 等目的状语，也按导航处理（到达目标页面）
            is_nav_page = bool(re.match(r'^\s*(?:For\s+this\s+local\s+training\s+variant,?\s*)?(?:Navigate|Open|Go\s+to|View|Access)\b', item["statement"], re.I) and re.search(r'\b(?:page|IDE|directory|section|drawer|tab|panel|screen|view)\b', item["statement"], re.I))
            if is_search and not is_write:
                # 搜索/查询类：1 条查询结果 gate
                gates = [{"group": "搜索结果", "fields": [],
                          "cond": "搜索条件正确且结果页到达，结果集与本地真实状态一致"}]
                return gates, []
            if is_nav_page and not is_op and not is_order and not is_signup:
                # 导航到页面：1 条到达目标
                gates, implicit = make_gates_nav(contract, item["statement"])
                return gates, implicit
            if is_single and not is_op and not is_order and not is_signup:
                # A 类单动作题：动作 + 对象，1 条精确 gate（操作类优先走字段拆分）
                gates = make_gates_single_action(item["statement"])
                if gates:
                    return gates, []
            if is_write or is_order or is_signup:
                # 写操作优先（含 sort/filter/reverse/switch 等操作类，即使有 completion 也按操作拆字段）
                gates, implicit = make_gates_write_statement(item["statement"], contract)
            else:
                gates, implicit = make_gates_nav(contract, item["statement"])
    return gates, implicit

def main():
    binary = parse_binary(os.path.join(BASE, "binary-reward-tasks.md"))
    nonbin = parse_nonbinary(os.path.join(BASE, "non-binary-reward-tasks.md"))
    remaining = parse_remaining(os.path.join(BASE, "remaining-training-tasks.md"))
    print(f"解析：binary={len(binary)} non-binary={len(nonbin)} remaining={len(remaining)}")

    all_items = binary + nonbin + remaining
    result = []
    for item in all_items:
        gates, implicit = build_item_gates(item)
        result.append({
            "task_id": item["task_id"],
            "statement": item["statement"],
            "branch": item.get("branch", ""),
            "src": item["src"],
            "gates": [{"id": f"G{i+1}", "group": g["group"], "fields": g["fields"], "cond": g["cond"]}
                      for i, g in enumerate(gates)],
            "implicit_preconditions": implicit,
        })

    # 统计
    import collections
    c = collections.Counter(len(r["gates"]) for r in result)
    print("gate 条数分布：", dict(sorted(c.items())))

    # 写 JSON
    with open(os.path.join(OUT, "gates.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print("已写 output/gates.json，共", len(result), "题")

    # 写 markdown
    md_lines = ["# 1983 题 gate 细分准则（语义组）", ""]
    md_lines.append("> 口径：每道题 = 一组 gate（G1..Gn），每条独立判对错；分值由下游按通过条数计算，本文不掺分值。")
    md_lines.append("> 一条 gate = 一个语义组；隐含前提不占 gate 分数。仅保留硬门槛，丢弃过程质量。")
    md_lines.append("")
    for r in result:
        md_lines.append(f"## {r['task_id']}")
        md_lines.append(f"- **题面：** {r['statement']}")
        md_lines.append(f"- **分支：** {r['branch']}（源：{r['src']}）")
        if r["implicit_preconditions"]:
            md_lines.append(f"- **隐含前提（不占分）：** " + "；".join(r["implicit_preconditions"]))
        for g in r["gates"]:
            md_lines.append(f"  - {g['id']} 【{g['group']}】{g['cond']}")
        md_lines.append("")
    with open(os.path.join(OUT, "gates.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))
    print("已写 output/gates.md")

if __name__ == "__main__":
    main()
