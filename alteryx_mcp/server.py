#!/usr/bin/env python3
"""MCP server exposing Alteryx tools over stdio.

Tools:
- summarize_workflow(workflow: str, mapping: str | None)
- rewrite_connections(workflow: str, config: str, dry_run: bool = False)
- find_tools(workflow: str, tool_id: int | None, plugin_type: str | None, annotation_pattern: str | None)
- update_select_tool(workflow: str, tool_id: int, field_updates: dict, dry_run: bool = False)
- update_annotation(workflow: str, tool_id: int, new_annotation: str, dry_run: bool = False)
- update_sql_query(workflow: str, tool_id: int, new_query: str, remove_comments: bool = True, dry_run: bool = False)
- update_connection_id(workflow: str, tool_id: int, new_connection_id: str, dry_run: bool = False)
- create_workflow(output_path: str, tools_config: list, connections: list | None, metadata: dict | None)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from mcp.server.fastmcp import FastMCP

# Import from local module
from . import alteryx_mcp


mcp = FastMCP("Alteryx MCP")


@mcp.tool()
def summarize_workflow(workflow: str, mapping: Optional[str] = None) -> str:
    """Summarize an Alteryx .yxmd workflow into Markdown.

    Args:
      workflow: Path to .yxmd file
      mapping: Optional path to JSON mapping file with connection aliases
    Returns: Markdown string summary
    """
    wf_path = Path(workflow)
    map_dict = None
    if mapping:
        map_path = Path(mapping)
        if map_path.exists():
            data = json.loads(map_path.read_text(encoding="utf-8"))
            map_dict = data.get("connections", {})
    return alteryx_mcp.summarize_workflow(wf_path, map_dict)


@mcp.tool()
def rewrite_connections(
    workflow: str, config: str, dry_run: bool = False
) -> str:
    """Rewrite DCM connection IDs in a workflow based on a JSON config.

    Args:
      workflow: Path to .yxmd file
      config: Path to JSON config with `connections` mapping
      dry_run: If True, do not write changes to disk
    Returns: Status string
    """
    wf_path = Path(workflow)
    cfg_path = Path(config)
    alteryx_mcp.rewrite_connections(wf_path, cfg_path, dry_run=dry_run)
    status = "dry-run" if dry_run else "updated"
    return f"rewrite-connections: {status} {wf_path.name} using {cfg_path.name}"


@mcp.tool()
def find_tools(
    workflow: str,
    tool_id: Optional[int] = None,
    plugin_type: Optional[str] = None,
    annotation_pattern: Optional[str] = None,
) -> str:
    """Find tools in an Alteryx workflow by criteria.

    Args:
      workflow: Path to .yxmd file
      tool_id: Optional specific tool ID to find
      plugin_type: Optional plugin type (e.g., 'AlteryxSelect', 'DbFileInput')
      annotation_pattern: Optional text to search in annotations
    Returns: JSON string with matching tools
    """
    wf_path = Path(workflow)
    results = alteryx_mcp.find_tools(wf_path, tool_id, plugin_type, annotation_pattern)
    return json.dumps(results, indent=2)


@mcp.tool()
def update_select_tool(
    workflow: str,
    tool_id: int,
    field_updates: str,
    dry_run: bool = False,
) -> str:
    """Update field configurations in an AlteryxSelect tool.

    Args:
      workflow: Path to .yxmd file
      tool_id: Tool ID of the Select tool
      field_updates: JSON string mapping field names to updates, e.g.:
        '{"field_name": {"selected": true, "rename": "new_name"}}'
      dry_run: If True, don't write changes
    Returns: Status message
    """
    wf_path = Path(workflow)
    updates = json.loads(field_updates)
    return alteryx_mcp.update_select_tool(wf_path, tool_id, updates, dry_run)


@mcp.tool()
def update_annotation(
    workflow: str,
    tool_id: int,
    new_annotation: str,
    dry_run: bool = False,
) -> str:
    """Update the DefaultAnnotationText for a tool.

    Args:
      workflow: Path to .yxmd file
      tool_id: Tool ID to update
      new_annotation: New annotation text
      dry_run: If True, don't write changes
    Returns: Status message
    """
    wf_path = Path(workflow)
    return alteryx_mcp.update_annotation(wf_path, tool_id, new_annotation, dry_run)


@mcp.tool()
def update_sql_query(
    workflow: str,
    tool_id: int,
    new_query: str,
    remove_comments: bool = True,
    dry_run: bool = False,
) -> str:
    """Update SQL query in a DbFileInput tool.

    Args:
      workflow: Path to .yxmd file
      tool_id: Tool ID of the DbFileInput tool
      new_query: New SQL query text
      remove_comments: If True, remove -- comments for OCI compliance
      dry_run: If True, don't write changes
    Returns: Status message
    """
    wf_path = Path(workflow)
    return alteryx_mcp.update_sql_query(
        wf_path, tool_id, new_query, remove_comments, dry_run
    )


@mcp.tool()
def update_connection_id(
    workflow: str,
    tool_id: int,
    new_connection_id: str,
    dry_run: bool = False,
) -> str:
    """Update database connection ID for a DbFileInput/DbFileOutput tool.

    Args:
      workflow: Path to .yxmd file
      tool_id: Tool ID to update
      new_connection_id: New DCM connection ID
      dry_run: If True, don't write changes
    Returns: Status message
    """
    wf_path = Path(workflow)
    return alteryx_mcp.update_connection_id(
        wf_path, tool_id, new_connection_id, dry_run
    )


@mcp.tool()
def create_workflow(
    output_path: str,
    tools_config: str,
    connections: Optional[str] = None,
    metadata: Optional[str] = None,
) -> str:
    """Create a new Alteryx workflow from scratch.

    Args:
      output_path: Path where to save .yxmd file
      tools_config: JSON array of tool configurations, each with:
        - plugin: Tool type (e.g., 'AlteryxSelect', 'DbFileInput')
        - position: {"x": int, "y": int}
        - configuration: Dict of tool-specific config
      connections: Optional JSON array of connections:
        - origin: tool_id, destination: tool_id
      metadata: Optional JSON dict with workflow metadata
    Returns: Status message
    """
    out_path = Path(output_path)
    tools = json.loads(tools_config)
    conns = json.loads(connections) if connections else None
    meta = json.loads(metadata) if metadata else None
    return alteryx_mcp.create_workflow(out_path, tools, conns, meta)


@mcp.tool()
def batch_update_connections(
    workflow: str,
    tool_ids: List[int],
    source_connection_id: Optional[str] = None,
    source_tool_id: Optional[int] = None,
    dry_run: bool = False
) -> str:
    """Update multiple tools with the same connection ID.
    
    Args:
        workflow: Path to .yxmd file
        tool_ids: List of tool IDs to update
        source_connection_id: Connection ID to use (if provided)
        source_tool_id: Tool ID to copy connection from (if not provided)
        dry_run: If True, show changes without writing to file
        
    Returns:
        Status message
    """
    return alteryx_mcp.batch_update_connections(
        workflow, tool_ids, source_connection_id, source_tool_id, dry_run
    )


@mcp.tool()
def find_tools_fast(
    workflow: str,
    tool_id: Optional[int] = None,
    plugin_type: Optional[str] = None,
    annotation_pattern: Optional[str] = None,
) -> str:
    """Optimized find tools - much faster for specific ToolID searches.
    
    Args:
        workflow: Path to .yxmd file
        tool_id: Specific tool ID (fast search)
        plugin_type: Plugin type (e.g., 'Sample', 'DbFileInput')
        annotation_pattern: Text pattern in annotations
        
    Returns:
        JSON string with matching tools
    """
    result = alteryx_mcp.find_tools_fast(
        workflow, tool_id, plugin_type, annotation_pattern
    )
    return json.dumps(result, indent=2)


@mcp.tool()
def get_row_limit(workflow: str, tool_id: int) -> str:
    """Get row limit settings for a specific tool.
    
    Args:
        workflow: Path to .yxmd file
        tool_id: Tool ID to query
        
    Returns:
        JSON with First N, Last N, Sample N settings
    """
    result = alteryx_mcp.get_row_limit(workflow, tool_id)
    return json.dumps(result, indent=2)


@mcp.tool()
def update_row_limit(
    workflow: str,
    tool_id: int,
    first_n: Optional[int] = None,
    last_n: Optional[int] = None,
    sample_n: Optional[int] = None,
    dry_run: bool = False
) -> str:
    """Update row limit for a single tool.
    
    Args:
        workflow: Path to .yxmd file
        tool_id: Tool ID to update
        first_n: First N rows setting
        last_n: Last N rows setting
        sample_n: Sample N rows setting
        dry_run: Preview without writing
        
    Returns:
        Status message
    """
    return alteryx_mcp.update_row_limit(
        workflow, tool_id, first_n, last_n, sample_n, dry_run
    )


@mcp.tool()
def batch_update_row_limits(
    workflow: str,
    tool_ids: Optional[List[int]] = None,
    plugin_type: Optional[str] = None,
    first_n: Optional[int] = None,
    last_n: Optional[int] = None,
    sample_n: Optional[int] = None,
    dry_run: bool = False
) -> str:
    """Update row limits for multiple tools or all tools of a type.
    
    Args:
        workflow: Path to .yxmd file
        tool_ids: List of tool IDs (or use plugin_type)
        plugin_type: Update all tools of this type (e.g., 'Sample')
        first_n: First N rows setting
        last_n: Last N rows setting
        sample_n: Sample N rows setting
        dry_run: Preview without writing
        
    Returns:
        Status message with results
    """
    return alteryx_mcp.batch_update_row_limits(
        workflow, tool_ids, plugin_type, first_n, last_n, sample_n, dry_run
    )


def main() -> None:
    mcp.run()  # stdio by default


if __name__ == "__main__":
    main()
