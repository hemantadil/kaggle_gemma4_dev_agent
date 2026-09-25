#!/usr/bin/env python3
"""
Local Evaluation Runner for Gemma 4 Developer Agent competition.
Simulates the two-phase evaluation lifecycle on local snapshots and tests.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
SNAPSHOTS_DIR = DATA_DIR / "snapshots"
GRAPHS_DIR = DATA_DIR / "graphs"
TASKS_FILE = DATA_DIR / "tasks.jsonl"
PYTHON_BIN = ROOT_DIR / ".venv" / "bin" / "python"

def load_task(instance_id: str) -> dict:
    if not TASKS_FILE.exists():
        print(f"[!] Error: {TASKS_FILE} not found.")
        sys.exit(1)
    with open(TASKS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            t = json.loads(line)
            if t.get("instance_id") == instance_id:
                return t
    print(f"[!] Error: Task '{instance_id}' not found in tasks.jsonl")
    sys.exit(1)

def apply_patch_resilient(workspace: Path, patch_content: str) -> bool:
    """Applies patch using resilient fallback passes conforming to official harness."""
    if not patch_content:
        return True
    if not patch_content.endswith("\n"):
        patch_content += "\n"

    passes = [
        "git apply --unsafe-paths --recount --ignore-space-change --ignore-whitespace -",
        "git apply --unsafe-paths -3 -",
        "git apply --unsafe-paths -p1 -",
        "git apply --unsafe-paths -p0 -",
        "patch -p1 --batch --forward -l -"
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
    """Finds test files modified by test_patch."""
    targets = []
    for line in test_patch.splitlines():
        if line.startswith("+++ b/"):
            targets.append(line.replace("+++ b/", "").strip())
    return targets

def run_evaluation(instance_id: str, patch_file: Path = None, use_ground_truth: bool = False, keep_workspace: bool = False) -> bool:
    print("=" * 70)
    print(f"[*] Starting Local Evaluation for: {instance_id}")
    print("=" * 70)

    task = load_task(instance_id)
    repo = task.get("repo")
    problem = task.get("problem_statement", "").strip()
    test_patch = task.get("test_patch", "")
    ground_truth_patch = task.get("patch", "")

    snapshot_tgz = SNAPSHOTS_DIR / f"{instance_id}.tgz"
    if not snapshot_tgz.exists():
        print(f"[!] Snapshot archive missing: {snapshot_tgz}")
        return False

    print(f"[+] Repository: {repo}")
    print(f"[+] Base Commit: {task.get('base_commit')}")
    print(f"[+] Problem: {problem.splitlines()[0] if problem else ''}")

    # Determine patch to test
    if patch_file and patch_file.exists():
        print(f"[+] Testing patch from file: {patch_file}")
        with open(patch_file, "r", encoding="utf-8") as f:
            candidate_patch = f.read()
    elif use_ground_truth:
        print("[+] Testing ground-truth solution patch...")
        candidate_patch = ground_truth_patch
    else:
        print("[+] Testing baseline (no fix applied)...")
        candidate_patch = ""

    # Setup isolated evaluation workspace
    work_base = ROOT_DIR / "eval_workspaces" if keep_workspace else Path(tempfile.mkdtemp())
    workspace = work_base / instance_id
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True, exist_ok=True)

    try:
        # Step 1: Extract repository snapshot
        print(f"\n[*] Phase 1: Extracting repository snapshot to {workspace.name}...")
        with tarfile.open(snapshot_tgz, "r:gz") as tar:
            tar.extractall(path=workspace)

        # Baseline git commit
        subprocess.run("git add -A && git commit -m 'baseline' --allow-empty -q", shell=True, cwd=workspace, capture_output=True)

        # Step 2: Apply test patch
        print("[*] Phase 2: Applying verification test patch...")
        if not apply_patch_resilient(workspace, test_patch):
            print("[!] Error: Failed to apply verification test_patch.")
            return False

        # Identify test command
        test_targets = extract_test_targets(test_patch)
        print(f"[+] Target Test Files: {', '.join(test_targets)}")
        targets_str = " ".join(test_targets) if test_targets else "tests/"
        pytest_cmd = f"PYTHONPATH={workspace} {PYTHON_BIN} -m pytest {targets_str} -p no:anyio -q"

        # Step 3: Run tests BEFORE candidate fix (Should Fail)
        print("\n[*] Phase 3: Running baseline verification test (expecting failure)...")
        before_res = subprocess.run(pytest_cmd, shell=True, cwd=workspace, capture_output=True, text=True)
        baseline_failed = before_res.returncode != 0
        if baseline_failed:
            print(f"[+] Baseline test confirmed FAILING (exit code: {before_res.returncode}). Issue reproduced!")
        else:
            print(f"[?] Notice: Baseline test already passed (exit code: 0).")

        # Step 4: Apply candidate patch
        if candidate_patch:
            print("\n[*] Phase 4: Applying candidate fix patch...")
            applied = apply_patch_resilient(workspace, candidate_patch)
            if not applied:
                print("[!] FAILED: Candidate patch could not be applied cleanly.")
                return False
            print("[+] Candidate patch applied successfully.")
        else:
            print("\n[*] Phase 4: No patch applied (baseline test only).")

        # Step 5: Re-run tests AFTER fix (Should Pass)
        print("\n[*] Phase 5: Running post-fix verification test...")
        after_res = subprocess.run(pytest_cmd, shell=True, cwd=workspace, capture_output=True, text=True)
        passed = (after_res.returncode == 0)

        print("\n" + "=" * 70)
        print("EVALUATION RESULT SUMMARY")
        print("=" * 70)
        print(f"Task ID:          {instance_id}")
        print(f"Baseline Fails:   {'YES' if baseline_failed else 'NO'}")
        print(f"Post-Fix Passes:  {'YES' if passed else 'NO'}")
        print(f"Exit Code:        {after_res.returncode}")
        if passed:
            print("\n>>> [RESOLVED: TRUE] Score: 1.0 (Task successfully resolved!) <<<")
        else:
            print("\n>>> [RESOLVED: FALSE] Score: 0.0 (Tests did not pass) <<<")
            print("\nTest Output:")
            for l in after_res.stdout.splitlines()[-10:]:
                print("  ", l)

        return passed

    finally:
        if not keep_workspace and work_base.exists():
            shutil.rmtree(work_base, ignore_errors=True)

def main():
    parser = argparse.ArgumentParser(description="Evaluate a task locally using snapshots and test patches")
    parser.add_argument("--id", default="rich_4077", help="Task instance_id to evaluate (e.g. 'rich_4077')")
    parser.add_argument("--ground-truth", action="store_true", help="Apply the ground-truth patch to verify 100% pass")
    parser.add_argument("--patch", type=Path, help="Path to a custom patch file to test")
    parser.add_argument("--keep", action="store_true", help="Keep extracted workspace in eval_workspaces/ for inspection")

    args = parser.parse_args()
    success = run_evaluation(
        instance_id=args.id,
        patch_file=args.patch,
        use_ground_truth=args.ground_truth,
        keep_workspace=args.keep
    )
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
