# Kaggle Submission Summary: Gemma 4 Developer Agent

**Competition:** [Google - The Gemma 4 Developer Agent](https://www.kaggle.com/competitions/gemma-4-developer-agent)  
**Submission Ref:** `56557628`  
**Submission Date:** September 25, 2026 (18:23:39 UTC / 23:53:39 IST)  
**Submission Archive:** `submission.zip`  
**Status:** `SubmissionStatus.PENDING`  

---

## 1. Executive Summary

This repository contains the complete autonomous software engineering agent configuration submitted to the **Google - The Gemma 4 Developer Agent Competition**. The agent is built on Google's Agent Development Kit (ADK) and powered by `gemma-4-31b-it-qat-w4a16-ct` running on 4x NVIDIA L4 GPUs with vLLM tensor parallelism.

The submission is specifically engineered to overcome the common failure modes observed in autonomous SWE benchmarks:
1. **Evaluation Timeouts**: Uses a calibrated 4.5-minute per-task hard governor to guarantee the 129 evaluation benchmark tasks finish within Kaggle's 12-hour evaluation ceiling.
2. **Context Looping**: Implements targeted definition lookup (`grep -n "def <name>"`) and multi-term keyword extraction instead of blind file scrolling.
3. **Patch Pollution**: Enforces strict test-file isolation so reproduction scripts never contaminate the final git diff patch.
4. **Git Safety**: Guides safe file-level rollbacks (`git checkout -- <file>`) while forbidding destructive operations (`git reset --hard`).

---

## 2. Architecture & Submission Files

The submission package (`submission.zip`) consists of a flat, highly responsive 9-tool architecture:

```text
submission.zip
├── agent.yaml                 # Root ADK agent configuration & tool bindings
├── eval_config.yaml           # Runtime budgets & execution limits
├── configs/
│   └── sampling.yaml          # Gemma 4 generation & reasoning config
├── prompts/
│   ├── system.md              # Core autonomous SWE developer instruction
│   └── analyzer.md            # Code analyzer reference prompt
└── sub_agents/
    └── code_analyzer.yaml     # Auxiliary analyzer schema
```

### Tool Suite (9 Official Competition Tools)
- `search_similar_code(query, k)`: Offline semantic code search via pre-computed embeddings.
- `get_code_neighbors(node, edge_type, max_neighbors)`: AST dependency graph traversal.
- `get_code_subgraph(nodes)`: Induced dependency subgraph extraction.
- `read_file(filepath, start_line, end_line)`: Resilient line-numbered reading with 150-line caps.
- `edit_file(filepath, old_string, new_string, allow_multiple)`: 3-tier resilient matching engine.
- `write_file(filepath, content)`: Atomic file creation / overwrite.
- `run_command(command)`: Sandboxed shell execution with 45s per-command timeout.
- `get_status()`: Un-gated status inspector for diffs and remaining budgets (FREE).
- `submit_patch()`: Un-gated evaluator submission trigger (FREE).

---

## 3. Configuration & Budget Calibration

### `eval_config.yaml`
```yaml
evaluation:
  timeout_seconds: 45      # Aggressive per-command timeout to avoid hanging scripts
  max_tool_calls: 70       # High ceiling to prevent early cutoff on complex tasks
  max_time_minutes: 4.5    # Hard safety governor: 129 tasks * 4.5m = 9.68h (under 12h limit)
  max_turns: 80            # Ample multi-turn reasoning ceiling
```

### `configs/sampling.yaml`
```yaml
temperature: 0.1           # Highly deterministic for syntax-accurate code edits
top_p: 0.95
max_output_tokens: 8192    # Accommodates large unified diffs and verbose stack traces
thinking_config:
  thinking_level: high
  thinking_budget: 2048    # Deep chain-of-thought localization before tool dispatch
  include_thoughts: true
```

---

## 4. Key Prompt Engineering Strategies (`prompts/system.md`)

- **Fast Symbol Navigation**: Directs the agent to run `grep -n "def <name>" <file>` or `grep -n "class <name>" <file>` to immediately locate line numbers instead of reading files 10 lines at a time.
- **Multi-Keyword Search**: For sparse problem statements (e.g. *"proxy isatty"*), extracts and cross-references all terms across both source and `tests/` directories.
- **Test File Protection**: Strictly prohibits creating or modifying files under `tests/`. Enforces running targeted tests via `pytest <target> -k <test>` or inline assertions via `python3 -c "..."`.
- **Targeted Git Rollbacks**: Explicitly allows `git checkout -- <file>` to undo mistaken edits on specific files while strictly barring `git reset --hard`.

---

## 5. Local Validation & Benchmark Results

Evaluated against the official competition tasks locally using `gemma-4-31B-it-MLX-4bit` on Apple Silicon:

| Benchmark Task | Repository | Turns | Result | Verification Notes |
|:---|:---|:---:|:---:|:---|
| `rich_4077` | Textualize/rich | 11 | **PASS 1.0** | Located `test_file_proxy.py`, reproduced failure, added `isatty()` to `FileProxy`, verified with pytest, called `submit_patch()`. |
| `requests_7427` | psf/requests | 20 | **PASS 1.0** | Fixed `no_proxy` domain boundary handling, reverted unintended test edits via `git checkout --`, passed all tests. |
| `requests_7433` | psf/requests | 9 | **PASS 1.0 (Fix)** | Instantly located `prepare_body` on line 574, applied exact 3-line stream detection fix, verified via inline assertions. |

---

## 6. How to Run Locally

```bash
# 1. Activate environment
source .venv/bin/activate

# 2. Validate configuration
python scripts/validate_agent_config.py

# 3. Package submission archive
python scripts/package_submission.py

# 4. Run live agent loop against a benchmark task (requires local oMLX / vLLM server)
python scripts/live_agent_runner.py --id rich_4077 --max-turns 25
```
