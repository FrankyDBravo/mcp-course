#!/usr/bin/env python3
"""
Module 2: GitHub Actions Integration - STARTER CODE
Extend your PR Agent with webhook handling and MCP Prompts for CI/CD workflows.
"""

import json
import os
import subprocess
from typing import Optional
from pathlib import Path
from datetime import datetime

from mcp.server.fastmcp import FastMCP

# Initialize the FastMCP server
mcp = FastMCP("pr-agent-actions")

# PR template directory (shared between starter and solution)
TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"

# Default PR templates
DEFAULT_TEMPLATES = {
    "bug.md": "Bug Fix",
    "feature.md": "Feature",
    "docs.md": "Documentation",
    "refactor.md": "Refactor",
    "test.md": "Test",
    "performance.md": "Performance",
    "security.md": "Security"
}

# File where webhook server stores events
EVENTS_FILE = Path(__file__).parent / "github_events.json"


# Type mapping for PR templates
TYPE_MAPPING = {
    "bug": "bug.md",
    "fix": "bug.md",
    "feature": "feature.md",
    "enhancement": "feature.md",
    "docs": "docs.md",
    "documentation": "docs.md",
    "refactor": "refactor.md",
    "cleanup": "refactor.md",
    "test": "test.md",
    "testing": "test.md",
    "performance": "performance.md",
    "optimization": "performance.md",
    "security": "security.md"
}


# ===== Module 1 Tools (Already includes output limiting fix from Module 1) =====

@mcp.tool()
async def analyze_file_changes(
    base_branch: str = "main",
    include_diff: bool = True,
    max_diff_lines: int = 500
) -> str:
    """Get the full diff and list of changed files in the current git repository.
    
    Args:
        base_branch: Base branch to compare against (default: main)
        include_diff: Include the full diff content (default: true)
        max_diff_lines: Maximum number of diff lines to include (default: 500)
    """
    try:
        # Get list of changed files
        files_result = subprocess.run(
            ["git", "diff", "--name-status", f"{base_branch}...HEAD"],
            capture_output=True,
            text=True,
            check=True
        )
        
        # Get diff statistics
        stat_result = subprocess.run(
            ["git", "diff", "--stat", f"{base_branch}...HEAD"],
            capture_output=True,
            text=True
        )
        
        # Get the actual diff if requested
        diff_content = ""
        truncated = False
        if include_diff:
            diff_result = subprocess.run(
                ["git", "diff", f"{base_branch}...HEAD"],
                capture_output=True,
                text=True
            )
            diff_lines = diff_result.stdout.split('\n')
            
            # Check if we need to truncate (learned from Module 1)
            if len(diff_lines) > max_diff_lines:
                diff_content = '\n'.join(diff_lines[:max_diff_lines])
                diff_content += f"\n\n... Output truncated. Showing {max_diff_lines} of {len(diff_lines)} lines ..."
                diff_content += "\n... Use max_diff_lines parameter to see more ..."
                truncated = True
            else:
                diff_content = diff_result.stdout
        
        # Get commit messages for context
        commits_result = subprocess.run(
            ["git", "log", "--oneline", f"{base_branch}..HEAD"],
            capture_output=True,
            text=True
        )
        
        analysis = {
            "base_branch": base_branch,
            "files_changed": files_result.stdout,
            "statistics": stat_result.stdout,
            "commits": commits_result.stdout,
            "diff": diff_content if include_diff else "Diff not included (set include_diff=true to see full diff)",
            "truncated": truncated,
            "total_diff_lines": len(diff_lines) if include_diff else 0
        }
        
        return json.dumps(analysis, indent=2)
        
    except subprocess.CalledProcessError as e:
        return json.dumps({"error": f"Git error: {e.stderr}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def get_pr_templates() -> str:
    """List available PR templates with their content."""
    templates = [
        {
            "filename": filename,
            "type": template_type,
            "content": (TEMPLATES_DIR / filename).read_text()
        }
        for filename, template_type in DEFAULT_TEMPLATES.items()
    ]
    
    return json.dumps(templates, indent=2)


@mcp.tool()
async def suggest_template(changes_summary: str, change_type: str) -> str:
    """Let Claude analyze the changes and suggest the most appropriate PR template.
    
    Args:
        changes_summary: Your analysis of what the changes do
        change_type: The type of change you've identified (bug, feature, docs, refactor, test, etc.)
    """
    
    # Get available templates
    templates_response = await get_pr_templates()
    templates = json.loads(templates_response)
    
    # Find matching template
    template_file = TYPE_MAPPING.get(change_type.lower(), "feature.md")
    selected_template = next(
        (t for t in templates if t["filename"] == template_file),
        templates[0]  # Default to first template if no match
    )
    
    suggestion = {
        "recommended_template": selected_template,
        "reasoning": f"Based on your analysis: '{changes_summary}', this appears to be a {change_type} change.",
        "template_content": selected_template["content"],
        "usage_hint": "Claude can help you fill out this template based on the specific changes in your PR."
    }
    
    return json.dumps(suggestion, indent=2)


# ===== Module 2: New GitHub Actions Tools =====

@mcp.tool()
async def get_recent_actions_events(limit: int = 10) -> str:
    """Get recent GitHub Actions events received via webhook.
    
    Args:
        limit: Maximum number of events to return (default: 10)
    """
    try:
        if not EVENTS_FILE.exists():
            return json.dumps([])
        with open(EVENTS_FILE, "r") as f:
            events = json.load(f)
        # Return the most recent events (assuming events are in chronological order)
        return json.dumps(events[-limit:])
    except Exception as e:
        return json.dumps({"error": f"Failed to read events: {str(e)}"})


@mcp.tool()
async def get_workflow_status(workflow_name: Optional[str] = None) -> str:
    """Get the current status of GitHub Actions workflows.
    
    Args:
        workflow_name: Optional specific workflow name to filter by
    """
    try:
        if not EVENTS_FILE.exists():
            return json.dumps([])
        with open(EVENTS_FILE, "r") as f:
            events = json.load(f)
        # Filter for workflow_run events
        workflow_events = [e for e in events if e.get("event") == "workflow_run"]
        # Optionally filter by workflow name
        if workflow_name:
            workflow_events = [e for e in workflow_events if e.get("workflow_name") == workflow_name]
        # Group by workflow name and get the latest status for each
        latest_status = {}
        for event in workflow_events:
            name = event.get("workflow_name", "unknown")
            run_id = event.get("run_id")
            status = event.get("status")
            conclusion = event.get("conclusion")
            updated_at = event.get("updated_at")
            # Use updated_at or run_id as a tiebreaker for latest
            key = (name,)
            if key not in latest_status or (
                updated_at and latest_status[key].get("updated_at", "") < updated_at
            ):
                latest_status[key] = {
                    "workflow_name": name,
                    "run_id": run_id,
                    "status": status,
                    "conclusion": conclusion,
                    "updated_at": updated_at
                }
        # Return as a list
        return json.dumps(list(latest_status.values()))
    except Exception as e:
        return json.dumps({"error": f"Failed to get workflow status: {str(e)}"})


# ===== Module 2: MCP Prompts =====

@mcp.prompt()
async def analyze_ci_results():
    """Analyze recent CI/CD results and provide insights."""
    # This prompt guides Claude to:
    # 1. Use get_recent_actions_events() to fetch the latest CI/CD events.
    # 2. Use get_workflow_status() to summarize the status of all workflows.
    # 3. Analyze the results for trends, failures, or patterns.
    # 4. Provide actionable insights or recommendations for the team.
    return (
        "You are a CI/CD analyst.\n"
        "- Call get_recent_actions_events() to fetch the latest GitHub Actions events.\n"
        "- Call get_workflow_status() to get the current status of all workflows.\n"
        "- Summarize the overall health of the CI/CD pipeline.\n"
        "- Highlight any recurring failures, slow jobs, or bottlenecks.\n"
        "- Suggest improvements or next steps for the team.\n"
        "- Present your analysis in a clear, actionable format."
    )

@mcp.prompt()
async def create_deployment_summary():
    """Generate a deployment summary for team communication."""
    # This prompt guides Claude to:
    # 1. Summarize the latest deployment, including what was deployed and its impact.
    # 2. Highlight key changes, new features, and resolved issues.
    # 3. Present the summary in a team-friendly, non-technical format.
    return (
        "You are responsible for communicating deployment updates to the team.\n"
        "- Summarize the most recent deployment, including the main features, bug fixes, and improvements.\n"
        "- Highlight any important changes or impacts for users.\n"
        "- Use information from recent PRs and CI/CD results if available.\n"
        "- Write in a clear, concise, and friendly tone suitable for all team members.\n"
        "- Include a section for next steps or follow-up actions if needed."
    )

@mcp.prompt()
async def generate_pr_status_report():
    """Generate a comprehensive PR status report including CI/CD results."""
    # This prompt guides Claude to:
    # 1. Combine code change analysis (from analyze_file_changes) with CI/CD status (from get_workflow_status).
    # 2. Present a unified report for a pull request.
    # 3. Highlight any issues, blockers, or required actions.
    return (
        "You are generating a PR status report for reviewers and stakeholders.\n"
        "- Use analyze_file_changes() to summarize the code changes in the PR.\n"
        "- Use get_workflow_status() to report on the CI/CD status for this PR.\n"
        "- Combine both code and CI/CD information into a single, easy-to-read report.\n"
        "- Highlight any issues, failed checks, or required actions before merging.\n"
        "- Make the report actionable and clear for both technical and non-technical readers."
    )

@mcp.prompt()
async def troubleshoot_workflow_failure():
    """Help troubleshoot a failing GitHub Actions workflow."""
    # This prompt guides Claude to:
    # 1. Systematically analyze failed workflow runs.
    # 2. Identify root causes and suggest debugging steps.
    # 3. Present findings in a step-by-step troubleshooting format.
    return (
        "You are a CI/CD troubleshooting assistant.\n"
        "- Use get_workflow_status() to identify any failed workflows.\n"
        "- For each failure, analyze the error messages, logs, and recent changes.\n"
        "- Suggest possible root causes and step-by-step debugging actions.\n"
        "- Recommend next steps for the developer or DevOps team.\n"
        "- Present your findings in a clear, systematic troubleshooting format."
    )


if __name__ == "__main__":
    print("Starting PR Agent MCP server...")
    print("NOTE: Run webhook_server.py in a separate terminal to receive GitHub events")
    mcp.run()