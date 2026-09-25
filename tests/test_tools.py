"""
Unit tests for the 9 local competition tools.
"""

import json
import tempfile
from pathlib import Path
from tools.competition_tools import CompetitionTools

def test_competition_tools_lifecycle():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        tools = CompetitionTools(repo_dir=tmp_path)

        # 1. Write file
        res = json.loads(tools.write_file("example.py", "def add(a, b):\n    return a - b\n"))
        assert res["status"] == "ok"
        assert (tmp_path / "example.py").exists()

        # 2. Read file
        read_res = json.loads(tools.read_file("example.py", 1, 2))
        assert read_res["status"] == "ok"
        assert "1: def add(a, b):" in read_res["content"]

        # 3. Edit file
        edit_res = json.loads(tools.edit_file("example.py", "return a - b", "return a + b"))
        assert edit_res["status"] == "ok"

        # 4. Verify edit
        updated = json.loads(tools.read_file("example.py", 2, 2))
        assert "return a + b" in updated["content"]

        # 5. Search similar code
        search_res = json.loads(tools.search_similar_code("def add", k=1))
        assert search_res["status"] == "ok"
        assert len(search_res["results"]) >= 1

        # 6. Subgraph tool
        sub_res = json.loads(tools.get_code_subgraph(["symbol_a", "symbol_b"]))
        assert sub_res["status"] == "ok"

        # 7. Submit patch
        sub_res = json.loads(tools.submit_patch())
        assert tools.patch_submitted is True
        assert sub_res["status"] == "ok"
