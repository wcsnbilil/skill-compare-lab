import argparse
import subprocess
from pathlib import Path

from .experiment import run_experiment
from .pack_validation import validate_pack
from .report import write_report
from .task_packs import load_task_pack


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Compare instruction-only coding skills with paired Python repair tasks."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="Run scripted fixtures offline; no model claims.")
    live = commands.add_parser("run", help="Run a live comparison using authenticated Codex CLI.")
    for command in (demo, live):
        command.add_argument("--output", type=Path, required=True, help="New output directory.")
        command.add_argument("--repeats", type=int, default=3)
        command.add_argument("--seed", type=int, default=42, help="Order seed, not a model seed.")
        command.add_argument(
            "--task", action="append", default=[], help="Task ID; repeat to select."
        )
    live.add_argument("--pack", type=Path, help="Custom task pack JSON; defaults to bundled tasks.")
    live.add_argument("--skill", type=Path, action="append", required=True)
    live.add_argument("--model", required=True, help="Explicit Codex model ID.")
    live.add_argument("--timeout", type=float, default=180, help="Seconds per model call.")
    live.add_argument(
        "--executor",
        choices=["docker", "local"],
        default="docker",
        help="Grader. local executes generated Python on this host; trusted use only.",
    )
    report = commands.add_parser("report", help="Rebuild the HTML report from local evidence.")
    report.add_argument("directory", type=Path)
    listing = commands.add_parser("tasks", help="List repair contracts without executing code.")
    listing.add_argument("--pack", type=Path)
    validation = commands.add_parser(
        "validate-pack", help="Check starter/reference outcomes offline."
    )
    validation.add_argument("pack", type=Path)
    validation.add_argument("--output", type=Path, required=True)
    validation.add_argument("--task", action="append", default=[])
    validation.add_argument(
        "--executor",
        choices=["docker", "local"],
        default="docker",
        help="local executes the pack's Python on this host; trusted use only.",
    )
    args = parser.parse_args(argv)
    try:
        if args.command == "tasks":
            for task in load_task_pack(args.pack).tasks:
                print(f"{task.id}: {task.title}\n  {task.contract}\n")
            return 0
        if args.command == "validate-pack":
            result = validate_pack(args.pack, args.output, args.executor, args.task)
            for task in result["tasks"]:
                print(
                    f"{task['id']}: {'valid' if task['valid'] else 'INVALID'} "
                    "(reference must pass; starter must fail without timing out)"
                )
            print(f"Evidence: {args.output / 'validation.json'}")
            return 0 if result["valid"] else 2
        if args.command == "report":
            path = write_report(args.directory)
            print(f"Report: {path}")
            return 0
        if args.command == "demo":
            output, status = run_experiment(
                args.output,
                repeats=args.repeats,
                seed=args.seed,
                mode="demo",
                task_ids=args.task,
            )
        else:
            print("Live run: Codex usage applies. Skills are sent to the configured model.")
            if args.executor == "local":
                print("Local grading executes model-generated Python on this host.")
            output, status = run_experiment(
                args.output,
                skills=args.skill,
                repeats=args.repeats,
                seed=args.seed,
                model=args.model,
                timeout=args.timeout,
                executor=args.executor,
                task_ids=args.task,
                pack_path=args.pack,
            )
        print(f"Experiment: {status}\nReport: {output / 'report.html'}")
        return 0 if status == "complete" else 2
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        parser.exit(2, f"skill-compare: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
