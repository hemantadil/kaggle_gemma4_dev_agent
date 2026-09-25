#!/usr/bin/env python3
"""
Packaging script for Kaggle Gemma 4 Developer Agent competition.
Packages agent.yaml, eval_config.yaml, prompts/, configs/, and optional adapters/ into submission.zip.
"""

import sys
import zipfile
from pathlib import Path
from validate_agent_config import validate_config

ROOT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_ZIP = ROOT_DIR / "submission.zip"

INCLUDED_ITEMS = [
    "agent.yaml",
    "eval_config.yaml",
    "prompts",
    "configs",
    "sub_agents",
    "adapters",
    "lora"
]

def build_submission():
    print("[*] Step 1: Validating agent configuration before packaging...")
    if not validate_config(ROOT_DIR / "agent.yaml"):
        print("[!] Validation failed. Aborting submission build.")
        sys.exit(1)

    print(f"\n[*] Step 2: Creating submission archive at {OUTPUT_ZIP}...")
    if OUTPUT_ZIP.exists():
        OUTPUT_ZIP.unlink()

    included_count = 0
    with zipfile.ZipFile(OUTPUT_ZIP, "w", zipfile.ZIP_DEFLATED) as zipf:
        for item_name in INCLUDED_ITEMS:
            item_path = ROOT_DIR / item_name
            if not item_path.exists():
                if item_name in ("adapters", "lora", "sub_agents"):
                    # optional folders
                    continue
                print(f"[!] Warning: Expected item '{item_name}' does not exist.")
                continue

            if item_path.is_file():
                arcname = item_path.name
                zipf.write(item_path, arcname=arcname)
                print(f"  + Added file: {arcname}")
                included_count += 1
            elif item_path.is_dir():
                for sub_path in item_path.rglob("*"):
                    if sub_path.is_file() and not sub_path.name.startswith("."):
                        arcname = str(sub_path.relative_to(ROOT_DIR))
                        zipf.write(sub_path, arcname=arcname)
                        print(f"  + Added file: {arcname}")
                        included_count += 1

    print(f"\n[*] Step 3: Verifying archive integrity...")
    with zipfile.ZipFile(OUTPUT_ZIP, "r") as zipf:
        namelist = zipf.namelist()
        if "agent.yaml" not in namelist:
            print("[!] FATAL: agent.yaml is NOT at the root of submission.zip!")
            sys.exit(1)
        if "eval_config.yaml" not in namelist:
            print("[!] FATAL: eval_config.yaml is NOT in submission.zip!")
            sys.exit(1)
        
        file_size_mb = OUTPUT_ZIP.stat().st_size / (1024 * 1024)
        print(f"[+] Total files in archive: {len(namelist)}")
        print(f"[+] Key root files: agent.yaml, eval_config.yaml")
        print(f"[+] Archive size: {file_size_mb:.2f} MB")
        print("\n[SUCCESS] submission.zip created successfully and verified!")
        print(f"Ready to submit '{OUTPUT_ZIP.name}' on Kaggle.")

if __name__ == "__main__":
    build_submission()
