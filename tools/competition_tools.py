"""
Reference local implementations of the 9 competition tools
for testing and dry-running agent workflows locally.
"""

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional
import networkx as nx

class CompetitionTools:
    def __init__(self, repo_dir: Path, graph_path: Optional[Path] = None, embeddings_path: Optional[Path] = None):
        self.repo_dir = repo_dir
        self.patch_submitted = False
        self.graph = nx.MultiDiGraph()
        
        # Load real graph if available
        if graph_path and Path(graph_path).exists():
            try:
                with open(graph_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.graph = nx.node_link_graph(data, directed=True, multigraph=True)
            except Exception:
                pass

        self.embeddings_path = embeddings_path

    def read_file(self, filepath: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> str:
        """Read lines from a file in the repository (1-indexed inclusive)."""
        target = (self.repo_dir / filepath.lstrip("/")).resolve()
        if not target.is_relative_to(self.repo_dir.resolve()):
            return json.dumps({"status": "error", "error_type": "PathTraversalError", "error_message": "Access outside repository root blocked."})
        if not target.exists():
            return json.dumps({"status": "error", "error_type": "FileNotFoundError", "error_message": f"File '{filepath}' does not exist."})

        with open(target, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        total = len(lines)
        start = max(1, start_line or 1)
        end = min(total, end_line or total)
        # Cap at 150 lines
        if (end - start + 1) > 150:
            end = start + 149
            is_truncated = True
        else:
            is_truncated = False

        sliced = "".join(f"{i}: {lines[i-1]}" for i in range(start, end + 1))
        return json.dumps({
            "status": "ok",
            "filepath": filepath,
            "content": sliced,
            "start_line": start,
            "end_line": end,
            "total_lines": total,
            "is_truncated": is_truncated
        })

    def edit_file(self, filepath: str, old_string: str, new_string: str, allow_multiple: bool = False) -> str:
        """Replace exact occurrences of old_string with new_string."""
        target = (self.repo_dir / filepath.lstrip("/")).resolve()
        if not target.is_relative_to(self.repo_dir.resolve()):
            return json.dumps({"status": "error", "error_type": "PathTraversalError", "error_message": "Access outside repository root blocked."})
        if not target.exists():
            return json.dumps({"status": "error", "error_type": "FileEditError", "error_message": f"File '{filepath}' does not exist."})

        with open(target, "r", encoding="utf-8") as f:
            content = f.read()

        count = content.count(old_string)
        if count == 0:
            return json.dumps({"status": "error", "error_type": "FileEditError", "error_message": f"Target content not found in '{filepath}'."})
        if count > 1 and not allow_multiple:
            return json.dumps({"status": "error", "error_type": "FileEditError", "error_message": f"Target content appears {count} times in '{filepath}'. Must be unique."})

        new_content = content.replace(old_string, new_string, 1 if not allow_multiple else count)
        with open(target, "w", encoding="utf-8") as f:
            f.write(new_content)
        return json.dumps({"status": "ok", "filepath": filepath, "occurrences": count, "strategy": "exact"})

    def write_file(self, filepath: str, content: str) -> str:
        """Create or overwrite a file."""
        target = (self.repo_dir / filepath.lstrip("/")).resolve()
        if not target.is_relative_to(self.repo_dir.resolve()):
            return json.dumps({"status": "error", "error_type": "PathTraversalError", "error_message": "Access outside repository root blocked."})
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(content)
        return json.dumps({"status": "ok", "filepath": filepath, "size": len(content)})

    def run_command(self, command: str) -> str:
        """Execute a shell command within the repository sandbox."""
        try:
            res = subprocess.run(
                command,
                shell=True,
                cwd=str(self.repo_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=300
            )
            output = (res.stdout or "")[:5000]
            if res.returncode == 0:
                return json.dumps({"status": "ok", "stdout": output, "exit_code": 0})
            return json.dumps({
                "status": "error",
                "error_type": "CommandError",
                "error_message": f"Command failed with exit code {res.returncode}",
                "details": {"stdout": output, "exit_code": res.returncode}
            })
        except subprocess.TimeoutExpired:
            return json.dumps({"status": "error", "error_type": "TimeoutExceeded", "error_message": "Command execution timed out after 300s."})
        except Exception as e:
            return json.dumps({"status": "error", "error_type": "ExecutionError", "error_message": str(e)})

    def get_status(self) -> str:
        """Return the current git status diff and modified files (FREE)."""
        diff = subprocess.run("git diff --stat HEAD 2>/dev/null || true", shell=True, cwd=str(self.repo_dir), stdout=subprocess.PIPE, text=True).stdout
        return json.dumps({
            "tool_calls_used": 0,
            "patch_submitted": self.patch_submitted,
            "diff_summary": diff.strip()
        })

    def submit_patch(self) -> str:
        """Submit the working tree changes as the final solution (FREE)."""
        self.patch_submitted = True
        subprocess.run("git add -N . 2>/dev/null || true", shell=True, cwd=str(self.repo_dir))
        diff = subprocess.run("git diff HEAD 2>/dev/null || true", shell=True, cwd=str(self.repo_dir), stdout=subprocess.PIPE, text=True).stdout
        return json.dumps({"status": "ok", "patch_size": len(diff), "files_changed": diff.count("diff --git")})

    def search_similar_code(self, query: str, k: int = 10) -> str:
        """Query top-k symbols by name or semantic similarity."""
        matched = []
        q_lower = query.lower()
        for node in self.graph.nodes:
            if q_lower in str(node).lower():
                matched.append({"node_name": str(node), "similarity": 0.95})
                if len(matched) >= k:
                    break
        if not matched:
            matched = [{"node_name": f"{query}.handler", "similarity": 0.85}]
        return json.dumps({"status": "ok", "query": query, "results": matched, "count": len(matched)})

    def get_code_neighbors(self, node: str, edge_type: Optional[str] = None, max_neighbors: int = 50) -> str:
        """Query AST graph for neighbor nodes (callers, callees, definitions)."""
        neighbors = []
        if node in self.graph:
            for neighbor in self.graph.neighbors(node):
                neighbors.append(str(neighbor))
                if len(neighbors) >= max_neighbors:
                    break
        return json.dumps({"status": "ok", "node": node, "neighbors": neighbors, "count": len(neighbors)})

    def get_code_subgraph(self, nodes: List[str]) -> str:
        """Extract induced subgraph for a given list of nodes."""
        valid_nodes = [n for n in nodes if n in self.graph]
        if valid_nodes:
            sub = self.graph.subgraph(valid_nodes)
            edges = [{"from": str(u), "to": str(v)} for u, v in sub.edges()]
            return json.dumps({"status": "ok", "nodes": valid_nodes, "edges": edges, "node_count": len(valid_nodes), "edge_count": len(edges)})
        return json.dumps({"status": "ok", "nodes": nodes, "edges": [], "node_count": len(nodes), "edge_count": 0})
