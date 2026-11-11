"""Shared preparation prompts and transitions; no task execution or stored state.

Agent supplies the stage/result from the original package and records the outcome
there. This script neither verifies that evidence nor grants execution authority.
All groups share this version; changing groups does not require a new version.
"""

import argparse
import json

VERSION = "1"
GUIDE = (
    "docs/migration/five-site-preactor-execution-20261103-v1/"
    "EXECUTION-GUIDE.md#next-group-preparation"
)
STEPS = (
    ("scope", "核范围：仅选一个候补组，核原包、合同、版本、消费者及冻结边界；明确产物、资源和有界耗时。"),
    ("reuse", "核复用：沿原回执确认适用项，只列实际差异及受影响范围，不重做未变共用检查。"),
    ("wire", "有限接线：只补配置、参数、schema和调用方；新能力、跨模块重构、长开发或连续修复报blocked。"),
    ("check", "安装与检查：沿已有入口做隔离增量安装、短Slurm受影响检查，核实际加载与合同消费；已验适用项直接复用。"),
    ("freeze", "冻结交接：沿原包记录版本、证据引用、实际完成范围和缺口，准备提交配置及恢复方案；不另建状态账本。"),
    ("ready", "准备流程结束，等待接力；任一持有组全部题目收口后，由agent沿原入口重新核差异、动态权限和初态。"),
)
PROMPTS = dict(STEPS)
STAGES = tuple(PROMPTS)
RESULTS = ("show", "done", "reused", "failed", "blocked", "priority")
BOUNDARY = (
    "当前组结果、故障及收尾优先；准备不挤占主线资源。"
    "不领取执行claim、不创建或占用真实业务实例、不初始化网站、不调用模型，"
    "不运行有真实副作用的prepare-only。具体操作由agent沿已有入口执行。"
)


def advance(stage, result):
    """Return one transition from agent-reported facts; never perform the work."""
    if stage not in PROMPTS or result not in RESULTS:
        raise ValueError("未知步骤或结果；流程未推进")
    if stage == "ready" and result != "show":
        raise ValueError("准备流程已结束；没有业务启动步骤")
    next_stage = stage
    directive = "执行当前步骤；完成或复用须由agent核原证据，再报告结果。"
    status = "step"
    if result in ("done", "reused"):
        next_stage = STAGES[STAGES.index(stage) + 1]
    elif result == "failed":
        status = "paused"
        directive = "保留原失败，诊断当前阶段及受影响接口；不自动重试，不重跑未变前序。超出有限修复范围则报blocked。"
    elif result == "blocked":
        status = "paused"
        directive = "保存已完成产物和具体缺口，停止扩展；留到正式接手或条件改变后再核。"
    elif result == "priority":
        status = "paused"
        directive = "暂停候补准备，先收当前组结果、处理故障或收尾；重新核实后再继续本步骤。"
    if next_stage == "ready":
        status = "waiting_for_handover"
        directive = "停止候补准备；本输出不授权真实业务执行。"
    return {
        "workflow_version": VERSION,
        "reported_stage": stage,
        "reported_result": result,
        "next_stage": next_stage,
        "status": status,
        "prompt": PROMPTS[next_stage],
        "directive": directive,
        "boundary": BOUNDARY,
        "guide": GUIDE,
        "evidence_verified": False,
        "runtime_authority": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True, choices=STAGES)
    parser.add_argument("--result", default="show", choices=RESULTS)
    args = parser.parse_args()
    try:
        report = advance(args.stage, args.result)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
