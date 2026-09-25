#!/usr/bin/env python3
"""
Helper script to download competition data and resources for the
Kaggle Gemma 4 Developer Agent competition.
"""

import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
COMPETITION_SLUG = "gemma-4-developer-agent"

def download_data():
    try:
        from kaggle.api.kaggle_api_extended import KaggleApi
        api = KaggleApi()
        api.authenticate()
        username = api.get_config_value("username") or "authorized user"
        print(f"[+] Kaggle API authenticated successfully as: {username}")
    except Exception as e:
        print(f"[!] Authentication failed: {e}")
        print("\nPlease ensure your Kaggle token is installed or set KAGGLE_USERNAME & KAGGLE_KEY.")
        sys.exit(1)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[*] Fetching competition files list for: {COMPETITION_SLUG}...")
    try:
        files = api.competition_list_files(COMPETITION_SLUG)
        print(f"[+] Found {len(files)} items in competition dataset:")

        # Summary of file types
        prefixes = {}
        for f in files:
            p = f.name.split("/")[0] if "/" in f.name else "<root>"
            prefixes[p] = prefixes.get(p, 0) + 1

        print("\nSummary by category:")
        for prefix, count in prefixes.items():
            print(f"  - {prefix}: {count} files")

        print("\nNotable files:")
        for f in files:
            if "/" not in f.name or any(k in f.name.lower() for k in ["wheel", "task", "sample", "start", "docker", "graph"]):
                print(f"  * {f.name} ({f.size} bytes)")

        confirm = os.environ.get("AUTO_DOWNLOAD", "false").lower() == "true"
        if not confirm:
            print("\nTo download all files to data/, run:")
            print(f"  AUTO_DOWNLOAD=true .venv/bin/python scripts/download_kaggle_data.py")
            return

        print(f"\n[*] Downloading competition files to {DATA_DIR}...")
        api.competition_download_files(COMPETITION_SLUG, path=str(DATA_DIR))
        print(f"[SUCCESS] Download completed in {DATA_DIR}")

    except Exception as e:
        print(f"[!] Error fetching files: {e}")
        print("\nNote: Make sure you have accepted the competition rules on Kaggle:")
        print(f"https://www.kaggle.com/competitions/{COMPETITION_SLUG}")
        sys.exit(1)

if __name__ == "__main__":
    download_data()
