"""Shared single-task workflow: prompts and transitions only, no execution or I/O.

Read original checkpoints first; report the earliest missing/invalid stage.
--resources describes the ORIGINAL attempt, not a replacement experiment.
--basis is an agent-reported evidence/contract reference, never verified here.
All groups share this version. Original manifests remain the source of truth.
"""

import argparse
import json

VERSION = "1"
GUIDE = "docs/migration/five-site-preactor-execution-20261103-v1/EXECUTION-GUIDE.md#shared-task-workflow"
PROMPTS = {
    "prepare": "来源/准备：收原回执并更新checkpoint，优先合法可接续旧题；核本题差异、来源消费接口、当前资格、预算及恢复责任。过程监听须在相关动作前接通。",
    "initialize": "初始化：消费适用冻结产物；核当前owner/claim、现场初态、唯一公开观察和baseline。新现场只补必要事实，缺接线先补接口，不默认重建前缀。",
    "actor": "Actor：核原请求/动作账本与完整执行、保存及收尾预算。区分未派发、派发未知、返回已保存和后处理待补；已有返回优先补核，不重发已完成或未知动作。",
    "review": "判定/复核：消费原执行和过程证据，分别完成原语义判定与独立复核；有效业务失败可接受，工程错误、缺证据和unknown不冒充有效失败。",
    "cleanup": "恢复关闭：沿原资源身份分别核Reset、物理终止、资源/请求账本及最终登记；已证明物理关闭只补允许的登记，不重复动作。",
}
STAGES = tuple(PROMPTS)
RESULTS = (
    "show", "done", "reused", "not_applicable", "evidence_gap", "interface_gap",
    "failed", "unknown", "interrupted", "waiting", "blocked", "business_failure",
    "close", "outer_flow",
)
RESOURCES = ("none", "live", "cleanup_due", "unknown", "closed")
ADVANCING = {"done", "reused", "not_applicable", "business_failure", "close"}
INTERRUPTIONS = {
    "evidence_gap", "interface_gap", "failed", "unknown", "interrupted",
    "blocked", "outer_flow",
}
BRANCHES = {
    "evidence_gap": ("supplement", "核缺口与已有覆盖；优先补核/补登记。必要时用冻结代码、输入及可恢复状态做最小补充实验；材料不足先确定最少需重新产生什么及合法入口，不就地放弃。新证据独立归属，随后返回原阶段复核。"),
    "interface_gap": ("repair", "产物存在但消费者不能使用时，先补现有接口及受影响检查，不隐式重跑生产者。通过后冻结，刷新安装与本次提交差异。"),
    "failed": ("repair", "保留首错、清理错及部分产物，定位当前阶段和受影响接口；只做最小修复及检查。通过后冻结，重新核资格；必要协调按有限修复批次安排，不逐题或逐修复重跑整链。"),
    "unknown": ("reconcile", "沿原身份只读核原回执、请求/动作、claim与费用占用；不重发、不清账、不换ID绕过。查明后重新分类，仍未知则保留阻断。"),
    "interrupted": ("reconcile", "取消/超时先核实际派发、动作和部分产物，不自动重试；未启动替换也须证明无副作用并确认原终态，再建唯一后继。"),
    "waiting": ("wait", "保留阶段及冻结输入，按原调度协议核实际作业、进展与期限并及时收回执。等待时推进无冲突工作；新故障改报failed/unknown，不只轮询。"),
    "blocked": ("paused", "保存具体阻断、可复用产物、最小下一动作及解除条件；不把缺口记录当闭环。固定代表题不默认换题，其他就绪成员按原范围推进。"),
    "outer_flow": ("delegate", "Generator/Teacher轮次、导出及训练交回已有外层流程；其中单题执行可用本流程，不改变外层轮次、授权与训练门。"),
}
BOUNDARY = (
    "agent核原合同、证据与实际入口后执行；所有操作沿原授权及Slurm规则。"
    "已验适用前序直接消费；工程基线不授予旧实例续跑权，动态权限每门核。"
    "共用准备/检查按组复用，成员只补差异和真实结果；当前回执及收尾优先。"
    "原包更新当前阶段、证据适用性和下一提交差异，不复制完整输出或另建账本。"
)


def advance(stage, result="show", resources="unknown", basis=""):
    """Deterministic routing of reported facts, not validation of task evidence."""
    if stage not in PROMPTS or result not in RESULTS or resources not in RESOURCES:
        raise ValueError("未知阶段、结果或资源状态；流程未推进")
    if result in ADVANCING and (not isinstance(basis, str) or not basis.strip()):
        raise ValueError("推进/跳过/收口须提供原证据或合同定位 --basis；脚本不核其真实性")
    if result == "business_failure" and stage != "review":
        raise ValueError("有效业务失败须先到判定/独立复核阶段确认")
    if result == "close" and stage != "cleanup":
        raise ValueError("只能在恢复关闭后，核整题出口再报告close")

    next_stage = stage
    action = "inspect"
    directive = "先核原回执与适用性，再选择当前阶段的最小合法动作；合同明确不适用才报告not_applicable。"
    if resources == "cleanup_due" or (
        resources == "live" and (result in INTERRUPTIONS or stage == "cleanup")
    ):
        action = "cleanup_first"
        directive = "立即沿原owner做有界取证与收尾，保留首错和全部清理错。不要等待分析结束；处理后核原checkpoint，保留本阶段及原问题，不能因收尾完成改报本阶段done。"
    elif resources == "unknown":
        action = "inspect_resources"
        directive = "先核原attempt的资源、owner及收尾责任；如需收尾立即沿原入口处理。目录消失或作业终态不等于安全恢复，不以新实例代替原资源证明。"
    elif result == "close":
        if resources not in ("none", "closed"):
            raise ValueError("存在未关闭资源，不能报告整题收口")
        action = "reported_closed"
        directive = "仅登记agent报告的整题出口：结果性质明确、适用复核和原资源收尾齐备。更新原清单及下一提交差异；本组全部题目收口才释放接力名额，候补组仍须刷新当前资格。"
    elif result in ADVANCING:
        if stage == "cleanup":
            action = "reconcile_exit"
            directive = "本阶段完成不等于整题完成。核原清单全部适用出口及业务结果；尚有缺口回最早缺失/失效阶段，齐备才报告close。工程补证不回填旧run历史事实。"
        else:
            next_stage = STAGES[STAGES.index(stage) + 1]
            action = "next"
            directive = "登记原阶段证据及适用性，消费冻结输出进入下一阶段；复用不写成本轮重做。仅工程验收通过不自动推进原题业务状态。"
    elif result in BRANCHES:
        action, directive = BRANCHES[result]
    return {
        "workflow": "task-progress", "version": VERSION,
        "reported_stage": stage, "reported_result": result,
        "reported_resources": resources, "reported_basis": basis,
        "next_stage": next_stage, "action": action,
        "prompt": PROMPTS[next_stage] if action in ("inspect", "next") else directive,
        "directive": directive,
        "boundary": BOUNDARY, "guide": GUIDE,
        "evidence_verified": False, "runtime_authority": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True, choices=STAGES)
    parser.add_argument("--result", default="show", choices=RESULTS)
    parser.add_argument("--resources", default="unknown", choices=RESOURCES,
                        help="原attempt：无资源/live/待收尾/未确认/收尾全部已证实")
    parser.add_argument("--basis", default="", help="原包证据或合同定位；不读取该引用")
    args = parser.parse_args()
    try:
        report = advance(args.stage, args.result, args.resources, args.basis)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
