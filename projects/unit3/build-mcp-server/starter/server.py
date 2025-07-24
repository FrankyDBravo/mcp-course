#!/usr/bin/env python3
"""
Module 1: Basic MCP Server - Starter Code
TODO: Implement tools for analyzing git changes and suggesting PR templates
"""

import json
import subprocess
from pathlib import Path

from mcp.server.fastmcp import FastMCP

# Initialize the FastMCP server
mcp = FastMCP("pr-agent")

# PR template directory (shared across all modules)
TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"


# TODO: Implement tool functions here
# Example structure for a tool:
# @mcp.tool()
# async def analyze_file_changes(base_branch: str = "main", include_diff: bool = True) -> str:
#     """Get the full diff and list of changed files in the current git repository.
#     
#     Args:
#         base_branch: Base branch to compare against (default: main)
#         include_diff: Include the full diff content (default: true)
#     """
#     # Your implementation here
#     pass

# Minimal stub implementations so the server runs
# TODO: Replace these with your actual implementations

@mcp.tool()
async def analyze_file_changes(base_branch: str = "main", include_diff: bool = True, max_diff_lines: int = 500) -> str:
    """Get the full diff and list of changed files in the current git repository.
    Args:
        base_branch: Base branch to compare against (default: main)
        include_diff: Include the full diff content (default: true)
        max_diff_lines: Maximum number of diff lines to return (default: 500)
    """
    import os
    working_directory = None
    try:
        # ---
        # Why do we check for MCP roots?
        # In some environments (e.g., Claude Code, remote agents, or when the server is not started in the repo root),
        # the process's current working directory may NOT be the root of the git repository we want to analyze.
        # MCP provides a way to get the intended root directory via session roots.
        # This ensures git commands run in the correct place, regardless of where the server process was started.
        # ---
        try:
            context = mcp.get_context()
            roots_result = await context.session.list_roots()
            # Use the first root as the working directory
            working_directory = roots_result.roots[0].uri.path
        except Exception:
            # If we can't get roots, fall back to current directory
            working_directory = os.getcwd()

        # Get changed files
        result_files = subprocess.run([
            "git", "diff", "--name-status", base_branch
        ], capture_output=True, text=True, check=True, cwd=working_directory)
        files_changed = result_files.stdout.strip().splitlines()
        files = [line.split("\t", 1)[-1] for line in files_changed if line]
        
        diff_content = None
        truncated = False
        if include_diff:
            result_diff = subprocess.run([
                "git", "diff", base_branch
            ], capture_output=True, text=True, check=True, cwd=working_directory)
            diff_lines = result_diff.stdout.splitlines()
            if len(diff_lines) > max_diff_lines:
                diff_content = "\n".join(diff_lines[:max_diff_lines])
                truncated = True
            else:
                diff_content = result_diff.stdout
        response = {
            "files_changed": files,
            "num_files_changed": len(files),
            "used_working_directory": working_directory
        }
        if include_diff:
            response["diff"] = diff_content
            response["diff_truncated"] =    
            response["diff_line_limit"] = max_diff_lines
        return json.dumps(response)
    except subprocess.CalledProcessError as e:
        return json.dumps({"error": "Failed to analyze git changes", "details": str(e)})
    except Exception as e:
        return json.dumps({"error": "Unexpected error in analyze_file_changes", "details": str(e)})


@mcp.tool()
async def get_pr_templates() -> str:
    """List available PR templates with their content."""
    try:
        templates = []
        for template_file in TEMPLATES_DIR.glob("*.md"):
            with open(template_file, "r") as f:
                content = f.read()
            templates.append({
                "filename": template_file.name,
                "name": template_file.stem,
                "content": content
            })
        return json.dumps(templates)
    except Exception as e:
        return json.dumps({"error": "Failed to read templates", "details": str(e)})


@mcp.tool()
async def suggest_template(changes_summary: str, change_type: str) -> str:
    """Let Claude analyze the changes and suggest the most appropriate PR template.
    Args:
        changes_summary: Your analysis of what the changes do
        change_type: The type of change you've identified (bug, feature, docs, refactor, test, etc.)
    """
    # Map change_type to template filename
    type_map = {
        "bug": "bug.md",
        "feature": "feature.md",
        "docs": "docs.md",
        "documentation": "docs.md",
        "refactor": "refactor.md",
        "test": "test.md",
        "performance": "performance.md",
        "security": "security.md"
    }
    template_file = type_map.get(change_type.lower())
    try:
        if template_file:
            path = TEMPLATES_DIR / template_file
            if path.exists():
                with open(path, "r") as f:
                    content = f.read()
                return json.dumps({
                    "recommended_template": template_file,
                    "template_content": content
                })
            else:
                return json.dumps({"error": f"Template '{template_file}' not found."})
        else:
            # Fallback: return all templates for manual selection
            templates = []
            for template_file in TEMPLATES_DIR.glob("*.md"):
                with open(template_file, "r") as f:
                    content = f.read()
                templates.append({
                    "filename": template_file.name,
                    "name": template_file.stem,
                    "content": content
                })
            return json.dumps({
                "error": f"Unknown change_type '{change_type}'. Returning all templates.",
                "templates": templates
            })
    except Exception as e:
        return json.dumps({"error": "Failed to suggest template", "details": str(e)})


if __name__ == "__main__":
    mcp.run()