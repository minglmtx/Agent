# -*- coding: utf-8 -*-
"""
gates 数据解析器 —— 供下游 agent 消费 output/gates.json。

用途：读取 1983 题的 gate 细分结果，按「通过条数」计分（分值由调用方自行决定）。
本模块只负责「读 + 结构化访问」，不实现计分、不判断对错。

最小用法：
    from gates_loader import load_gates, gates_by_id, gates_by_src

    data = load_gates()                 # list[dict]，1983 题
    item = gates_by_id(data, "<task_id>")   # 取单题
    # item = {"task_id", "statement", "branch", "src",
    #         "gates": [{"id":"G1","group":"...","fields":[...],"cond":"..."}],
    #         "implicit_preconditions": ["..."]}

    n = len(item["gates"])              # 该题 gate 条数（= 计分的分母）
    passed = 2                          # 假设通过 2 条
    score = passed / n                  # 示例：按条数占比计分（仅供参考）
"""
import json, os

_HERE = os.path.dirname(os.path.abspath(__file__))
# gates.json 可能在同目录（脚本放在 docs/reward-inventory/ 下），
# 也可能在 output/ 子目录（脚本放在仓库根目录）。
_candidates = [
    os.path.join(_HERE, "gates.json"),
    os.path.join(_HERE, "output", "gates.json"),
]
DEFAULT_PATH = _candidates[0] if os.path.exists(_candidates[0]) else _candidates[1]


def load_gates(path=DEFAULT_PATH):
    """读取 gates.json，返回 list[dict]。"""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def gates_by_id(data, task_id):
    """按 task_id 取单题；找不到返回 None。"""
    for item in data:
        if item["task_id"] == task_id:
            return item
    return None


def gates_by_src(data, src):
    """按来源（binary / non-binary / remaining）过滤。"""
    return [item for item in data if item["src"] == src]


def gate_count(item):
    """返回某题的 gate 条数（即计分分母）。"""
    return len(item["gates"])


def score_by_passed(item, passed_count):
    """按通过条数计分（0~1，线性）。仅示例，调用方可替换为任意计分规则。

    passed_count：判定的 gate 通过条数（由调用方对每条 gate 判对错后给出）。
    返回 passed_count / 总条数；总条数为 0 时返回 None。
    """
    n = gate_count(item)
    if n == 0:
        return None
    return passed_count / n


def summary(data):
    """返回整体统计：总题数、各来源题数、gate 条数分布。"""
    from collections import Counter
    dist = Counter(gate_count(x) for x in data)
    return {
        "total": len(data),
        "by_src": dict(Counter(x["src"] for x in data)),
        "gate_count_dist": dict(sorted(dist.items())),
    }


if __name__ == "__main__":
    data = load_gates()
    print("总题数:", len(data))
    s = summary(data)
    print("来源分布:", s["by_src"])
    print("gate 条数分布:", s["gate_count_dist"])
