from __future__ import annotations
import argparse
import json
from pathlib import Path
from .config import load_settings, WEB_DOMAINS
from .llm import create_chat_backend
from .schemas import SkillBank, TrajectoryRecord
from .skill_builder import build_raw_candidates, prepare_skill_inputs
from .postprocess import postprocess_skill_bank

DEFAULT_CONFIG = Path(__file__).parents[2] / "configs/default.yaml"


def build_parser():
    p = argparse.ArgumentParser(
        prog="lab-generate-skill",
        description="Go-Browse-WA preparation, browser inference and skill bank",
    )
    sub = p.add_subparsers(dest="command", required=True)
    for name, help in [
        (
            "preprocess",
            "Select at most two Go-Browse trajectories per task and quality-filter",
        ),
        (
            "infer-offline",
            "Predict actions on recorded observations; does not execute or evaluate them",
        ),
        ("collect", "Run live BrowserGym tasks from an explicit JSONL task manifest"),
        ("build", "Extract one skill per selected trajectory"),
        ("postprocess", "Validate, embed and deduplicate skills"),
        ("workflow", "Extract skills and postprocess"),
        ("audit-trajectories", "Check browser trajectory integrity"),
        ("check-official", "Check actual WebArena task website prerequisites"),
    ]:
        q = sub.add_parser(name, help=help)
        q.add_argument("--config", default=str(DEFAULT_CONFIG))
        q.add_argument("--domains", nargs="+", choices=WEB_DOMAINS)
        if name == "check-official":
            q.add_argument("--task-id", type=int, action="append", dest="task_ids")
            q.add_argument("--output", type=Path)
        if name == "preprocess":
            q.add_argument("--overwrite", action="store_true")
        if name in {"build", "workflow", "infer-offline", "collect"}:
            q.add_argument("--limit", type=int)
        if name == "build":
            q.add_argument("--dry-run", action="store_true")
        if name in {"infer-offline", "collect"}:
            q.add_argument("--model")
            q.add_argument("--output", type=Path)
        if name == "infer-offline":
            q.add_argument("--steps-per-trace", type=int, default=1)
        if name == "collect":
            q.add_argument("--tasks", required=True)
            q.add_argument("--rollout-index", type=int, default=0)
        if name in {"postprocess", "workflow"}:
            q.add_argument(
                "--embedding-backend",
                choices=[
                    "local_hidden_state",
                    "sentence_transformers",
                    "openai",
                    "tfidf",
                ],
            )
            q.add_argument("--embedding-model")
        if name == "audit-trajectories":
            q.add_argument("--input", action="append", dest="inputs")
            q.add_argument("--output")
    q = sub.add_parser("schema")
    q.add_argument("name", choices=["trajectory", "skill_bank", "browser_task"])
    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "schema":
        from .gobrowse_runtime import BrowserTask

        print(
            json.dumps(
                {
                    "trajectory": TrajectoryRecord,
                    "skill_bank": SkillBank,
                    "browser_task": BrowserTask,
                }[args.name].model_json_schema(),
                indent=2,
            )
        )
        return
    settings = load_settings(args.config)
    if args.domains:
        settings.collection.domains = args.domains
    if getattr(args, "limit", None) is not None and args.limit < 1:
        parser.error("--limit must be positive")
    if getattr(args, "embedding_backend", None):
        settings.embedding.backend = args.embedding_backend
    if getattr(args, "embedding_model", None):
        settings.embedding.model = args.embedding_model
    if args.command == "check-official":
        from .official_check import check_official

        result = check_official(
            args.task_ids or [157],
            settings.paths.project_root.parent.parent
            / "paper_repos/WebArena/config_files/test.raw.json",
            args.output,
        )
    elif args.command == "preprocess":
        from .gobrowse_data import preprocess_gobrowse

        result = preprocess_gobrowse(settings, overwrite=args.overwrite)
    elif args.command in {"infer-offline", "collect"}:
        from .gobrowse_runtime import infer_recorded, load_browser_tasks
        from .collector import collect_trajectories

        if args.command == "collect":
            load_browser_tasks(args.tasks)  # Validate before any model loading.
        if args.model:
            settings.actor.model = args.model
        backend = create_chat_backend(settings, role="actor")
        try:
            if args.command == "infer-offline":
                result = infer_recorded(
                    settings,
                    backend,
                    limit=args.limit or 1,
                    steps_per_trace=args.steps_per_trace,
                    output=args.output,
                )
            else:
                result = collect_trajectories(
                    settings,
                    backend,
                    tasks_path=args.tasks,
                    output_path=args.output,
                    limit=args.limit,
                    rollout_index=args.rollout_index,
                )
        finally:
            backend.close()
    elif args.command == "audit-trajectories":
        from .trajectory_audit import audit_trajectories

        result = audit_trajectories(
            args.inputs or [settings.paths.trajectories_dir], output_path=args.output
        )
    elif args.command == "build" and args.dry_run:
        selected, tasks = prepare_skill_inputs(settings, limit=args.limit)
        result = {
            "dry_run": True,
            "tasks": len(tasks),
            "selected_trajectories": len(selected),
            "paired_tasks": sum(t["paired"] for t in tasks),
            "unpaired_tasks": sum(not t["paired"] for t in tasks),
            "fallback_tasks": sum(t["same_outcome_fallback"] for t in tasks),
        }
    elif args.command == "postprocess":
        result = postprocess_skill_bank(settings)
    else:
        backend = create_chat_backend(settings, role="skill_extractor")
        try:
            result = build_raw_candidates(settings, backend, limit=args.limit)
        finally:
            backend.close()
        if args.command == "workflow":
            result = {
                "generation": result,
                "postprocessing": postprocess_skill_bank(settings),
            }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.command == "check-official" and not result["ready_for_browser_attempt"]:
        raise SystemExit(2)
    if result.get("runtime_errors", 0):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
