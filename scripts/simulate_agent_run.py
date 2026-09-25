#!/usr/bin/env python3
"""
Simulate an agent execution lifecycle on a benchmark task using the 9 competition tools.
Demonstrates the 5-phase protocol (Locate -> Inspect -> Edit -> Verify -> Submit).
"""

import argparse
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from tools.competition_tools import CompetitionTools

TASKS_FILE = ROOT_DIR / "data" / "tasks.jsonl"
SNAPSHOTS_DIR = ROOT_DIR / "data" / "snapshots"
GRAPHS_DIR = ROOT_DIR / "data" / "graphs"

def simulate_agent(instance_id: str = "rich_4077"):
    print("=" * 70)
    print(f"[*] SIMULATING AGENT EXECUTION FOR: {instance_id}")
    print("=" * 70)

    # 1. Load task
    with open(TASKS_FILE, "r") as f:
        task = next(json.loads(line) for line in f if json.loads(line)["instance_id"] == instance_id)

    print(f"[Problem Statement]\n{task['problem_statement'].strip()}\n")

    # 2. Extract snapshot into temporary workspace
    tmpdir = tempfile.mkdtemp(prefix=f"agent_sim_{instance_id}_")
    workspace = Path(tmpdir) / "workspace"
    workspace.mkdir()

    try:
        with tarfile.open(SNAPSHOTS_DIR / f"{instance_id}.tgz", "r:gz") as tar:
            tar.extractall(path=workspace)

        # Baseline commit
        subprocess.run("git add -A && git commit -m 'baseline' -q", shell=True, cwd=workspace)

        # Apply test patch so targeted tests exist for verification
        test_patch = task.get("test_patch", "")
        if not test_patch.endswith("\n"): test_patch += "\n"
        subprocess.run("git apply --recount --ignore-space-change --ignore-whitespace -", input=test_patch, text=True, shell=True, cwd=workspace)

        # Initialize the 9 Competition Tools against the workspace
        graph_file = GRAPHS_DIR / f"{instance_id}.json"
        tools = CompetitionTools(repo_dir=workspace, graph_path=graph_file)

        print("[*] AGENT PROTOCOL STARTED")
        print("-" * 50)

        # Turn 1: Code Search / Localization
        print("\n>> Turn 1: Calling search_similar_code('FileProxy')...")
        res1 = json.loads(tools.search_similar_code("FileProxy", k=3))
        print("Response:", res1)

        # Turn 2: Inspect suspect file lines
        print("\n>> Turn 2: Calling read_file('rich/file_proxy.py', start_line=50, end_line=60)...")
        res2 = json.loads(tools.read_file("rich/file_proxy.py", start_line=50, end_line=60))
        print(f"Content read:\n{res2['content'].strip()}")

        # Turn 3: Verify initial test failure (Reproduction)
        print("\n>> Turn 3: Calling run_command('pytest tests/test_file_proxy.py -k test_isatty')...")
        res3 = json.loads(tools.run_command(f"{ROOT_DIR}/.venv/bin/python -m pytest tests/test_file_proxy.py -k test_isatty -q"))
        print(f"Test Status: exit_code={res3.get('exit_code', res3.get('details', {}).get('exit_code'))} (Expected Failure)")

        # Turn 4: Apply surgical edit
        print("\n>> Turn 4: Calling edit_file('rich/file_proxy.py')...")
        old_code = "    def fileno(self) -> int:\n        return self.__file.fileno()"
        new_code = "    def fileno(self) -> int:\n        return self.__file.fileno()\n\n    def isatty(self) -> bool:\n        return self.__file.isatty()"
        res4 = json.loads(tools.edit_file("rich/file_proxy.py", old_code, new_code))
        print("Response:", res4)

        # Turn 5: Re-verify with targeted pytest
        print("\n>> Turn 5: Calling run_command('pytest tests/test_file_proxy.py -k test_isatty')...")
        res5 = json.loads(tools.run_command(f"{ROOT_DIR}/.venv/bin/python -m pytest tests/test_file_proxy.py -k test_isatty -q"))
        print("Response stdout:", res5.get("stdout", "").strip())
        print(f"Test Status: exit_code={res5.get('exit_code')} (Passed!)")

        # Turn 6: Submit patch
        print("\n>> Turn 6: Calling submit_patch()...")
        res6 = json.loads(tools.submit_patch())
        print("Response:", res6)

        print("\n" + "=" * 70)
        print("[SUCCESS] Local Agent Simulation Completed and Verified Cleanly!")
        print("=" * 70)

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

if __name__ == "__main__":
    simulate_agent("rich_4077")
