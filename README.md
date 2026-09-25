# Google - The Gemma 4 Developer Agent Starter Kit

A modular, production-ready scaffold for participating in the **[Google - The Gemma 4 Developer Agent Competition](https://www.kaggle.com/competitions/gemma-4-developer-agent/overview)** hosted on Kaggle.

---

## 📁 Repository Structure

```text
.
├── agent.yaml                 # Required root ADK agent configuration
├── configs/
│   └── sampling.yaml          # Generation & decoding hyper-parameters
├── prompts/
│   └── system.md              # Battle-tested SWE system prompt & execution protocol
├── tools/
│   ├── __init__.py
│   └── competition_tools.py   # Reference implementation of the 8 competition tools
├── scripts/
│   ├── validate_agent_config.py   # Validates ADK schema and file references
│   ├── package_submission.py      # Packages & verifies submission.zip
│   └── download_kaggle_data.py    # Kaggle API downloader for datasets & wheels
├── tests/
│   ├── __init__.py
│   └── test_tools.py          # Unit tests for the local tooling suite
├── requirements.txt           # Python dependencies
└── submission.zip             # Generated submission archive ready for upload
```

---

## 🚀 Quickstart

### 1. Set Up Environment
Activate the pre-configured virtual environment or create one:
```bash
# If using existing virtualenv:
source .venv/bin/activate

# Or install dependencies:
pip install -r requirements.txt
```

### 2. Validate Agent Configuration
Before submitting, verify that `agent.yaml`, referenced prompts, and tool configurations are compliant:
```bash
python scripts/validate_agent_config.py
```

### 3. Build `submission.zip`
Package your agent files into the required Kaggle submission format:
```bash
python scripts/package_submission.py
```
This automatically validates the structure and ensures `agent.yaml` is positioned strictly at the root of `submission.zip`.

---

## 📥 Downloading Competition Data & Wheels

1. Ensure your Kaggle API key is configured at `~/.kaggle/kaggle.json` or exported in your environment:
   ```bash
   export KAGGLE_USERNAME="your_username"
   export KAGGLE_KEY="your_api_key"
   ```
2. Accept the competition rules on the Kaggle competition page.
3. Run the download helper:
   ```bash
   # List available competition files
   python scripts/download_kaggle_data.py

   # Download all files into data/
   AUTO_DOWNLOAD=true python scripts/download_kaggle_data.py
   ```

---

## 🧪 Testing Tools Locally

Run the unit tests to verify tool behavior and file manipulation logic:
```bash
PYTHONPATH=. pytest tests/
```

---

## 💡 Competition Strategies & Best Practices

1. **Flat Tool Integration:** Direct tool calling on the root agent has demonstrated significantly higher reliability than multi-layer sub-agent routing for Gemma 4.
2. **Deterministic Decoding:** Keep `temperature` low (0.05 – 0.1) and provide at least 2048 tokens of `thinking_budget` so chain-of-thought localization finishes cleanly before tool emission.
3. **AST & Embedding Utilization:** Leverage `search_similar_code` and `get_code_neighbors` to avoid wasting context tokens reading entire files.
4. **Surgical Edits:** Restrict edits to 1–10 lines around the root cause. Large file rewrites often cause syntax breakages or regression errors.
5. **Pre-Submission Verification:** Always trigger `run_command` with the test suite (`pytest`) before calling `submit_patch()`.
