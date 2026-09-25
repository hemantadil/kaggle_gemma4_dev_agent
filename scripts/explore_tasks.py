#!/usr/bin/env python3
"""
Task Explorer utility for Gemma 4 Developer Agent competition.
Inspect and search benchmark tasks in data/tasks.jsonl.
"""

import argparse
import json
import sys
from pathlib import Path

TASKS_FILE = Path(__file__).resolve().parent.parent / "data" / "tasks.jsonl"

def load_tasks():
    if not TASKS_FILE.exists():
        print(f"[!] Error: {TASKS_FILE} not found. Please ensure tasks.jsonl is downloaded.")
        sys.exit(1)
    tasks = []
    with open(TASKS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                tasks.append(json.loads(line))
    return tasks

def show_task_detail(t):
    print("=" * 70)
    print(f"Instance ID: {t.get('instance_id')}")
    print(f"Repository:  {t.get('repo')}")
    print(f"Base Commit: {t.get('base_commit')}")
    print("=" * 70)
    print("\n--- Problem Statement ---")
    print(t.get("problem_statement", "").strip())
    
    hints = t.get("hints_text", "").strip()
    if hints:
        print("\n--- Hints ---")
        print(hints)

    patch = t.get("patch", "")
    if patch:
        print("\n--- Ground Truth Modified Files ---")
        files = [l for l in patch.splitlines() if l.startswith("+++ b/")]
        for f in files:
            print(f"  * {f.replace('+++ b/', '')}")

    test_patch = t.get("test_patch", "")
    if test_patch:
        print("\n--- Target Test Files ---")
        tfiles = [l for l in test_patch.splitlines() if l.startswith("+++ b/")]
        for tf in tfiles:
            print(f"  * {tf.replace('+++ b/', '')}")

def search_tasks(query=None, repo=None, limit=10):
    tasks = load_tasks()
    matches = []
    for t in tasks:
        if repo and repo.lower() not in t.get("repo", "").lower():
            continue
        if query:
            q = query.lower()
            ps = t.get("problem_statement", "").lower()
            iid = t.get("instance_id", "").lower()
            if q not in ps and q not in iid:
                continue
        matches.append(t)

    print(f"[*] Found {len(matches)} matching tasks (showing up to {limit}):\n")
    for i, t in enumerate(matches[:limit], 1):
        lines = t.get("problem_statement", "").strip().splitlines()
        first_line = lines[0] if lines else "No description"
        print(f"{i:2d}. [{t.get('instance_id')}] ({t.get('repo')})")
        print(f"    Title: {first_line[:80]}")
    return matches

def main():
    parser = argparse.ArgumentParser(description="Explore SWE tasks in tasks.jsonl")
    parser.add_argument("--id", help="Show full details for a specific task instance_id")
    parser.add_argument("--repo", help="Filter tasks by repository name (e.g. 'fastapi', 'rich')")
    parser.add_argument("--query", "-q", help="Search keywords in problem statement")
    parser.add_argument("--limit", "-n", type=int, default=10, help="Max results to display")
    parser.add_argument("--stats", action="store_true", help="Show dataset summary statistics")

    args = parser.parse_args()

    if args.stats:
        tasks = load_tasks()
        print(f"Total tasks: {len(tasks)}")
        from collections import Counter
        repos = Counter(t.get("repo") for t in tasks)
        for r, c in repos.most_common():
            print(f"  {r}: {c} ({c/len(tasks)*100:.1f}%)")
        return

    if args.id:
        tasks = load_tasks()
        target = next((t for t in tasks if t.get("instance_id") == args.id), None)
        if target:
            show_task_detail(target)
        else:
            print(f"[!] Task ID '{args.id}' not found.")
        return

    search_tasks(query=args.query, repo=args.repo, limit=args.limit)

if __name__ == "__main__":
    main()
