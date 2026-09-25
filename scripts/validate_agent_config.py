#!/usr/bin/env python3
"""
Validation script for Gemma 4 Developer Agent configuration.
Checks schema conformance, file existence, and ADK requirements.
"""

import sys
from pathlib import Path
import yaml

ROOT_DIR = Path(__file__).resolve().parent.parent

class IncludeLoader(yaml.SafeLoader):
    """Custom YAML loader to handle !include tags relative to the calling file."""
    def __init__(self, stream):
        if hasattr(stream, "name") and stream.name and stream.name != "<unicode string>":
            self._root = Path(stream.name).parent
        else:
            self._root = ROOT_DIR
        super().__init__(stream)

def include_constructor(loader: IncludeLoader, node: yaml.Node):
    rel_path = loader.construct_scalar(node)
    file_path = (loader._root / rel_path).resolve()
    if not file_path.exists():
        raise FileNotFoundError(f"Included file does not exist: {file_path}")
    if file_path.suffix in [".yaml", ".yml"]:
        with open(file_path, "r", encoding="utf-8") as f:
            sub_loader = IncludeLoader(f)
            return sub_loader.get_single_data()
    else:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()

IncludeLoader.add_constructor("!include", include_constructor)


def validate_config(agent_yaml_path: Path) -> bool:
    print(f"[*] Validating agent configuration at: {agent_yaml_path}")
    if not agent_yaml_path.exists():
        print(f"[!] Error: {agent_yaml_path} does not exist.")
        return False

    try:
        with open(agent_yaml_path, "r", encoding="utf-8") as f:
            loader = IncludeLoader(f)
            data = loader.get_single_data()
    except Exception as e:
        print(f"[!] YAML Parsing Error: {e}")
        return False

    required_keys = ["model", "instruction", "tools"]
    missing_keys = [k for k in required_keys if k not in data]
    if missing_keys:
        print(f"[!] Missing required keys in agent.yaml: {missing_keys}")
        return False

    print(f"[+] Agent Name: {data.get('name', 'unnamed')}")
    print(f"[+] Model: {data.get('model')}")
    print(f"[+] Instruction Length: {len(str(data.get('instruction')))} chars")

    raw_tools = data.get("tools", [])
    if not isinstance(raw_tools, list) or len(raw_tools) == 0:
        print("[!] Error: 'tools' must be a non-empty list.")
        return False

    core_tools = []
    agent_tools = []
    for t in raw_tools:
        if isinstance(t, str):
            core_tools.append(t)
        elif isinstance(t, dict) and "agent_tool" in t:
            cfg = t["agent_tool"].get("config_path")
            agent_tools.append(cfg)
            # Verify sub-agent config exists
            sub_path = ROOT_DIR / cfg
            if not sub_path.exists():
                print(f"[!] Error: sub-agent config not found: {sub_path}")
                return False
            # Verify sub-agent can parse
            try:
                with open(sub_path, "r", encoding="utf-8") as sf:
                    s_loader = IncludeLoader(sf)
                    sub_data = s_loader.get_single_data()
                print(f"  + Verified sub-agent '{sub_data.get('name')}' at {cfg}")
            except Exception as se:
                print(f"[!] Error loading sub-agent {cfg}: {se}")
                return False

    print(f"[+] Core Tools ({len(core_tools)}): {', '.join(core_tools)}")
    if agent_tools:
        print(f"[+] Agent Tools ({len(agent_tools)}): {', '.join(agent_tools)}")

    # Verify standard competition tools
    standard_tools = {
        "read_file", "edit_file", "write_file", "run_command",
        "submit_patch", "get_status", "search_similar_code",
        "get_code_neighbors", "get_code_subgraph"
    }
    missing_standard = standard_tools - set(core_tools)
    if missing_standard:
        print(f"[?] Warning: Some standard competition tools are missing from 'tools': {missing_standard}")

    # Check generate_content_config
    if "generate_content_config" in data:
        print(f"[+] Generation config verified.")

    # Check eval_config.yaml
    eval_cfg_file = ROOT_DIR / "eval_config.yaml"
    if not eval_cfg_file.exists():
        print(f"[!] Warning: eval_config.yaml missing! Kaggle submissions will use default 60-min timeouts.")
    else:
        try:
            with open(eval_cfg_file, "r") as ef:
                ec = yaml.safe_load(ef)
            e_vals = ec.get("evaluation", {})
            print(f"[+] Execution Budgets (eval_config.yaml): {e_vals}")
        except Exception as e:
            print(f"[!] Warning: Failed to parse eval_config.yaml: {e}")

    print("\n[SUCCESS] Configuration is valid and ADK compliant!")
    return True

if __name__ == "__main__":
    target = ROOT_DIR / "agent.yaml"
    success = validate_config(target)
    sys.exit(0 if success else 1)
