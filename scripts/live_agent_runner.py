#!/usr/bin/env python3
"""
Live Autonomous Agent Runner for Gemma 4 Developer Agent competition.
Connects to an OpenAI-compatible endpoint (e.g. oMLX on Apple Silicon or vLLM)
and drives the agent using the 9 competition tools against a benchmark task.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv
load_dotenv(ROOT_DIR / ".env")
load_dotenv(Path.home() / ".env")

from openai import OpenAI
from tools.competition_tools import CompetitionTools

DATA_DIR = ROOT_DIR / "data"
SNAPSHOTS_DIR = DATA_DIR / "snapshots"
GRAPHS_DIR = DATA_DIR / "graphs"
TASKS_FILE = DATA_DIR / "tasks.jsonl"
SYSTEM_PROMPT_FILE = ROOT_DIR / "prompts" / "system.md"

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_similar_code",
            "description": "Find semantically similar functions/classes in repository AST graph. Pass a symbol or function name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Symbol, function, or class name to search for."},
                    "k": {"type": "integer", "description": "Number of top results to return.", "default": 5}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_code_neighbors",
            "description": "Inspect AST graph neighbors (callers, callees, definitions) for a symbol.",
            "parameters": {
                "type": "object",
                "properties": {
                    "node": {"type": "string", "description": "Symbol name in graph."},
                    "edge_type": {"type": "string", "description": "Optional edge filter (CALLS, IMPORTS, etc.)."}
                },
                "required": ["node"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read line-numbered contents from a workspace file (150 lines max).",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "Relative file path."},
                    "start_line": {"type": "integer", "description": "Starting line number (1-indexed)."},
                    "end_line": {"type": "integer", "description": "Ending line number (inclusive)."}
                },
                "required": ["filepath"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Replace an exact unique substring in a file with new content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "Relative file path."},
                    "old_string": {"type": "string", "description": "Exact text to replace."},
                    "new_string": {"type": "string", "description": "Replacement text."},
                    "allow_multiple": {"type": "boolean", "description": "Whether to replace multiple occurrences.", "default": False}
                },
                "required": ["filepath", "old_string", "new_string"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or completely overwrite a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "Relative file path."},
                    "content": {"type": "string", "description": "File text content."}
                },
                "required": ["filepath", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Execute a shell command inside the workspace (e.g. targeted pytest).",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to execute."}
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_status",
            "description": "Check current git status and modified files (FREE).",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "submit_patch",
            "description": "Conclude session and submit git diff patch for official evaluation (FREE).",
            "parameters": {"type": "object", "properties": {}}
        }
    }
]

def load_system_prompt() -> str:
    with open(SYSTEM_PROMPT_FILE, "r", encoding="utf-8") as f:
        return f.read()

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

def run_agent_on_task(instance_id: str, base_url: str, api_key: str, model_name: str, max_turns: int = 15):
    print("=" * 70)
    print(f"[*] Starting Live Agent Run for: {instance_id}")
    print(f"[*] Endpoint: {base_url} | Model: {model_name}")
    print("=" * 70)

    # 1. Load task
    with open(TASKS_FILE, "r", encoding="utf-8") as f:
        task = next(json.loads(line) for line in f if json.loads(line)["instance_id"] == instance_id)

    # 2. Extract snapshot into temporary workspace
    tmpdir = tempfile.mkdtemp(prefix=f"live_{instance_id}_")
    workspace = Path(tmpdir) / "workspace"
    workspace.mkdir()

    client = OpenAI(base_url=base_url, api_key=api_key)

    try:
        with tarfile.open(SNAPSHOTS_DIR / f"{instance_id}.tgz", "r:gz") as tar:
            tar.extractall(path=workspace)

        subprocess.run("git add -A && git commit -m 'baseline' -q", shell=True, cwd=workspace)
        subprocess.run("git tag baseline_tag", shell=True, cwd=workspace)
        # In Container A, test_patch is NOT applied — agent operates strictly on base_commit!

        tools = CompetitionTools(repo_dir=workspace, graph_path=GRAPHS_DIR / f"{instance_id}.json")

        system_instruction = load_system_prompt()
        # Build workspace layout matching swegemma harness (find . -maxdepth 3)
        res = subprocess.run("find . -maxdepth 3", shell=True, cwd=workspace, capture_output=True, text=True)
        raw_entries = [l for l in res.stdout.splitlines() if not any(x in l for x in [".git", "__pycache__", ".pyc"])]
        files_str = "\n".join(raw_entries[:150])

        graph_file = GRAPHS_DIR / f"{instance_id}.json"
        graph_hint = ""
        if graph_file.exists() and graph_file.stat().st_size > 100:
            graph_hint = """
## Code Intelligence Tools
This repository has pre-built code graph and embedding data. Use these tools for fast, targeted navigation:
- `search_similar_code(query)`: Find semantically similar functions/classes by keyword.
- `get_code_neighbors(node)`: Find callers, callees, and definitions related to a symbol."""

        initial_user_prompt = f"""You are evaluating a software engineering task for repository {task.get('repo')}.

Problem Statement:
{task.get('problem_statement')}

Hints:
{task.get('hints_text', 'None')}
{graph_hint}

## Workspace Structure (Key Implementation Files):
{files_str}

Please investigate, locate the bug, apply the fix with edit_file, verify with targeted test, and call submit_patch()."""

        messages = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": initial_user_prompt}
        ]

        patch_submitted = False
        recent_tool_sigs = []

        for turn in range(1, max_turns + 1):
            print(f"\n--- Turn {turn}/{max_turns} ---")
            response = client.chat.completions.create(
                model=model_name,
                messages=messages,
                tools=TOOL_DEFINITIONS,
                tool_choice="auto",
                temperature=0.1,
                max_tokens=16384
            )

            choice = response.choices[0]
            message = choice.message
            messages.append(message)

            if message.content:
                print(f"[Agent Thought/Text]:\n{message.content.strip()}\n")

            if not message.tool_calls:
                print("[!] Agent returned no tool calls.")
                if patch_submitted:
                    print("[+] Session concluded after patch submission.")
                    break
                messages.append({"role": "user", "content": "Please continue by calling tools to investigate and resolve the issue, or call submit_patch when done."})
                continue

            for tool_call in message.tool_calls:
                fn_name = tool_call.function.name
                raw_args = tool_call.function.arguments or "{}"
                try:
                    args = json.loads(raw_args)
                except Exception:
                    args = {}

                current_sig = f"{fn_name}:{raw_args}"
                print(f"[Tool Call]: {fn_name}({args})")
                
                # Check duplicate or cyclic loop on commands
                if current_sig in recent_tool_sigs[-3:] and fn_name == "run_command":
                    result = json.dumps({
                        "status": "error",
                        "error_type": "DuplicateCallError",
                        "error_message": f"Duplicate call to '{fn_name}' detected. You have already executed this command and observed the result. Do NOT repeat it. Apply your code fix to the target file now using edit_file."
                    })
                # Execute tool
                elif fn_name == "read_file":
                    result = tools.read_file(args.get("filepath", ""), args.get("start_line"), args.get("end_line"))
                elif fn_name == "edit_file":
                    result = tools.edit_file(args.get("filepath", ""), args.get("old_string", ""), args.get("new_string", ""), allow_multiple=args.get("allow_multiple", False))
                elif fn_name == "write_file":
                    result = tools.write_file(args.get("filepath", ""), args.get("content", ""))
                elif fn_name == "run_command":
                    cmd = args.get("command", "")
                    wrapped_cmd = f"PATH={ROOT_DIR}/.venv/bin:$PATH PYTHONPATH={workspace}:$PYTHONPATH {cmd}"
                    result = tools.run_command(wrapped_cmd)
                elif fn_name == "search_similar_code":
                    result = tools.search_similar_code(args.get("query", ""), args.get("k", 5))
                elif fn_name == "get_code_neighbors":
                    result = tools.get_code_neighbors(args.get("node", ""), args.get("edge_type"))
                elif fn_name == "get_status":
                    result = tools.get_status()
                elif fn_name == "submit_patch":
                    result = tools.submit_patch()
                    patch_submitted = True
                else:
                    result = json.dumps({"status": "error", "error_message": f"Unknown tool '{fn_name}'"})

                print(f"[Tool Response]: {result[:200]}...")
                recent_tool_sigs.append(current_sig)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result
                })

            if patch_submitted:
                print("\n[+] submit_patch() was executed! Concluding agent turns.")
                break

        # Verification (Container B Simulation)
        print("\n" + "=" * 70)
        print("[*] Running Verification on Generated Patch (Container B Simulation)...")
        print("=" * 70)
        subprocess.run("git add -N . 2>/dev/null || true", shell=True, cwd=workspace)
        diff_res = subprocess.run("git diff baseline_tag", shell=True, cwd=workspace, capture_output=True, text=True)
        agent_patch = diff_res.stdout
        print(f"Generated Git Diff Size: {len(agent_patch)} chars")
        if not agent_patch.strip():
            print("[!] Warning: Agent did not generate any changes in the repository.")
        else:
            print("--- Agent Patch Preview ---")
            print(agent_patch[:1000] + ("\n... [truncated]" if len(agent_patch) > 1000 else ""))
            print("---------------------------")

        # Apply ground truth test_patch
        test_patch = task.get("test_patch", "")
        if test_patch:
            print("[+] Applying official benchmark test patch...")
            applied = apply_patch_resilient(workspace, test_patch)
            if not applied:
                print("[!] Warning: Could not cleanly apply test_patch to workspace.")
            else:
                print("[+] test_patch applied cleanly.")

        # Run pytest on target test files
        test_targets = extract_test_targets(test_patch)
        targets_str = " ".join(test_targets) if test_targets else "tests/"
        pytest_cmd = f"PATH={ROOT_DIR}/.venv/bin:$PATH PYTHONPATH={workspace}:$PYTHONPATH pytest {targets_str} -p no:anyio -q"
        print(f"[+] Executing pytest: {pytest_cmd}")
        test_run = subprocess.run(pytest_cmd, shell=True, cwd=workspace, capture_output=True, text=True)

        if test_run.returncode == 0:
            print(f"\n>>> [TASK RESOLVED: PASS] Score: 1.0! All tests passed! <<<")
            return True
        else:
            print(f"\n>>> [TASK UNRESOLVED: FAIL] Exit code: {test_run.returncode} <<<")
            print("Failure snippet:\n", test_run.stdout[-800:] if test_run.stdout else test_run.stderr[-800:])
            return False

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

def main():
    parser = argparse.ArgumentParser(description="Run live autonomous agent against competition task")
    parser.add_argument("--id", default="rich_4077", help="Task instance_id to solve")
    default_base_url = os.environ.get("OPENROUTER_BASE_URL") or os.environ.get("OMLX_BASE_URL", "http://127.0.0.1:8000/v1")
    default_api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OMLX_API_KEY", "omlx")
    default_model = os.environ.get("OPENROUTER_MODEL") or os.environ.get("OMLX_MODEL", "google/gemma-4-31b-it")

    parser.add_argument("--base-url", default=default_base_url, help="OpenAI-compatible base URL")
    parser.add_argument("--api-key", default=default_api_key, help="API key")
    parser.add_argument("--model", default=default_model, help="Model name")
    parser.add_argument("--max-turns", type=int, default=20, help="Max interaction turns")

    args = parser.parse_args()
    run_agent_on_task(
        instance_id=args.id,
        base_url=args.base_url,
        api_key=args.api_key,
        model_name=args.model,
        max_turns=args.max_turns
    )

if __name__ == "__main__":
    main()
