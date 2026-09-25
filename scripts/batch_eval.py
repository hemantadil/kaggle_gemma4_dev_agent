#!/usr/bin/env python3
"""
Batch Evaluation Runner for Gemma 4 Developer Agent competition.
Evaluates multiple benchmark tasks sequentially and aggregates resolution rates.
"""

import argparse
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
SNAPSHOTS_DIR = DATA_DIR / "snapshots"
TASKS_FILE = DATA_DIR / "tasks.jsonl"
PYTHON_BIN = ROOT_DIR / ".venv" / "bin" / "python"

def apply_patch_resilient(workspace: Path, patch_content: str) -> bool:
    if not patch_content:
        return True
    if not patch_content.endswith("\n"):
        patch_content += "\n"

    passes = [
        "git apply --unsafe-paths --recount --ignore-space-change --ignore-whitespace -",
        "git apply --unsafe-paths -3 -",
        "git apply --unsafe-paths -p1 -",
        "git apply --unsafe-paths -p0 -"
    ]

    for cmd in passes:
        proc = subprocess.run(
            cmd,
            input=patch_content,
            text=True,
            shell=True,
            cwd=workspace,
            capture_output=True
        )
        if proc.returncode == 0:
            return True
    return False

def extract_test_targets(test_patch: str) -> list[str]:
    targets = []
    for line in test_patch.splitlines():
        if line.startswith("+++ b/"):
            targets.append(line.replace("+++ b/", "").strip())
    return targets

def evaluate_single_task(task: dict) -> dict:
    instance_id = task["instance_id"]
    snapshot_tgz = SNAPSHOTS_DIR / f"{instance_id}.tgz"
    if not snapshot_tgz.exists():
        return {"instance_id": instance_id, "status": "SKIPPED", "reason": "Missing snapshot"}

    tmpdir = tempfile.mkdtemp(prefix=f"batch_{instance_id}_")
    workspace = Path(tmpdir) / "workspace"
    workspace.mkdir()

    start_t = time.time()
    try:
        # Extract snapshot
        with tarfile.open(snapshot_tgz, "r:gz") as tar:
            tar.extractall(path=workspace)

        # Baseline git commit
        subprocess.run("git add -A && git commit -m 'baseline' --allow-empty -q", shell=True, cwd=workspace, capture_output=True)

        # Apply test patch
        test_patch = task.get("test_patch", "")
        if not apply_patch_resilient(workspace, test_patch):
            return {"instance_id": instance_id, "status": "ERROR", "reason": "Failed to apply test_patch"}

        test_targets = extract_test_targets(test_patch)
        targets_str = " ".join(test_targets) if test_targets else "tests/"
        pytest_cmd = f"PYTHONPATH={workspace} {PYTHON_BIN} -m pytest {targets_str} -p no:anyio -q"

        # Baseline check (expecting failure)
        before_res = subprocess.run(pytest_cmd, shell=True, cwd=workspace, capture_output=True, text=True, timeout=60)
        baseline_failed = (before_res.returncode != 0)

        # Apply ground truth patch
        ground_truth = task.get("patch", "")
        if not apply_patch_resilient(workspace, ground_truth):
            return {"instance_id": instance_id, "status": "ERROR", "reason": "Failed to apply fix patch"}

        # Post-fix verification
        after_res = subprocess.run(pytest_cmd, shell=True, cwd=workspace, capture_output=True, text=True, timeout=60)
        resolved = (after_res.returncode == 0)

        elapsed = time.time() - start_t
        return {
            "instance_id": instance_id,
            "status": "PASS" if resolved else "FAIL",
            "baseline_failed": baseline_failed,
            "resolved": resolved,
            "exit_code": after_res.returncode,
            "elapsed_s": round(elapsed, 2)
        }
    except subprocess.TimeoutExpired:
        return {"instance_id": instance_id, "status": "TIMEOUT", "elapsed_s": 60.0}
    except Exception as e:
        return {"instance_id": instance_id, "status": "ERROR", "reason": str(e)}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

def main():
    parser = argparse.ArgumentParser(description="Run batch evaluation on competition tasks")
    parser.add_argument("--repo", default="rich", help="Target repository (default: 'rich', or 'all')")
    parser.add_argument("--offset", type=int, default=0, help="Offset index to start from (default: 0)")
    parser.add_argument("--limit", "-n", type=int, default=10, help="Number of tasks to evaluate (default: 10)")
    args = parser.parse_args()

    with open(TASKS_FILE, "r", encoding="utf-8") as f:
        all_tasks = [json.loads(line) for line in f if line.strip()]

    target_tasks = [t for t in all_tasks if args.repo.lower() in t.get("repo", "").lower()] if args.repo != "all" else all_tasks
    sliced = target_tasks[args.offset : args.offset + args.limit]

    print("=" * 70)
    print(f"[*] Starting Batch Evaluation (Repo: '{args.repo}', Offset: {args.offset}, Limit: {len(sliced)})")
    print("=" * 70)
    print(f"[+] Evaluating {len(sliced)} tasks...\n")

    results = []
    passed = 0
    failed = 0
    errors = 0

    for i, task in enumerate(sliced, 1):
        iid = task["instance_id"]
        print(f"[{i:2d}/{len(sliced)}] Evaluating {iid}...", end=" ", flush=True)
        res = evaluate_single_task(task)
        results.append(res)

        status = res.get("status")
        if status == "PASS":
            passed += 1
            print(f"PASSED ({res.get('elapsed_s')}s)")
        elif status == "FAIL":
            failed += 1
            print(f"FAILED (exit_code={res.get('exit_code')}, {res.get('elapsed_s')}s)")
        else:
            errors += 1
            print(f"{status} ({res.get('reason', '')})")

    print("\n" + "=" * 70)
    print("BATCH EVALUATION SUMMARY REPORT")
    print("=" * 70)
    print(f"Total Tasks Evaluated:  {len(sliced)}")
    print(f"Successfully Resolved:  {passed} / {len(sliced)} ({passed/len(sliced)*100:.1f}%)" if sliced else "No tasks")
    print(f"Failed Resolutions:     {failed}")
    print(f"Errors / Timeouts:      {errors}")
    print("=" * 70)

if __name__ == "__main__":
    main()
