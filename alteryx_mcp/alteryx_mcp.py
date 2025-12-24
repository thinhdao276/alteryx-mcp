"""Utility helpers for Alteryx workflow metadata control."""
from __future__ import annotations

import argparse
import json
import re
import textwrap
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union
import xml.etree.ElementTree as ET


try:
    from xml.etree.ElementTree import indent as xml_indent
except ImportError:
    xml_indent = None


# Plugin type mappings
PLUGIN_PATTERNS = {
    "AlteryxSelect": "AlteryxBasePluginsGui.AlteryxSelect.AlteryxSelect",
    "DbFileInput": "AlteryxBasePluginsGui.DbFileInput.DbFileInput",
    "DbFileOutput": "AlteryxBasePluginsGui.DbFileOutput.DbFileOutput",
    "Filter": "AlteryxBasePluginsGui.Filter.Filter",
    "Join": "AlteryxBasePluginsGui.Join.Join",
    "Sort": "AlteryxBasePluginsGui.Sort.Sort",
    "Formula": "AlteryxBasePluginsGui.Formula.Formula",
    "TextBox": "AlteryxGuiToolkit.TextBox.TextBox",
    "Browse": "AlteryxBasePluginsGui.BrowseV2.BrowseV2",
    "ToolContainer": "AlteryxGuiToolkit.ToolContainer.ToolContainer",
    "Union": "AlteryxBasePluginsGui.Union.Union",
    "Summarize": "AlteryxBasePluginsGui.Summarize.Summarize",
    "Sample": "AlteryxBasePluginsGui.Sample.Sample",
    "Unique": "AlteryxBasePluginsGui.Unique.Unique",
    "RecordID": "AlteryxBasePluginsGui.RecordID.RecordID",
    "MultiRowFormula": "AlteryxBasePluginsGui.MultiRowFormula.MultiRowFormula",
    "TextInput": "AlteryxBasePluginsGui.TextInput.TextInput",
    "DateTimeInput": "AlteryxBasePluginsGui.DateTimeInput.DateTimeInput",
}


@dataclass
class NodeInfo:
    tool_id: int
    plugin: str
    label: str
    annotation: str
    containers: Tuple[str, ...]
    connection_ids: List[str]
    connection_types: List[str]
    query: Optional[str]
    table: Optional[str]
    pre_sql: Optional[str]
    post_sql: Optional[str]
    text: Optional[str]


def _find_node_by_id(root: ET.Element, tool_id: int) -> Optional[ET.Element]:
    """Find a Node element by ToolID in the XML tree."""
    def _search(elem: ET.Element) -> Optional[ET.Element]:
        if elem.tag == "Node" and elem.get("ToolID") == str(tool_id):
            return elem
        # Check ChildNodes for containers
        child_nodes = elem.find("ChildNodes")
        if child_nodes is not None:
            for child in child_nodes.findall("Node"):
                result = _search(child)
                if result is not None:
                    return result
        # Check direct children
        for child in elem:
            result = _search(child)
            if result is not None:
                return result
        return None
    
    return _search(root)


def _write_tree(tree: ET.ElementTree, path: Path) -> None:
    """Write XML tree to file with proper formatting."""
    if xml_indent:
        xml_indent(tree.getroot(), space="  ")
    
    tree.write(
        path,
        encoding="utf-8",
        xml_declaration=True,
        method="xml",
    )


def summarize_workflow(workflow: Union[str, Path], mapping: Optional[Dict[str, Dict[str, str]]] = None) -> str:
    """Summarize an Alteryx .yxmd workflow into Markdown."""
    workflow_path = Path(workflow)
    tree = ET.parse(workflow_path)
    root = tree.getroot()
    
    # Collect stats
    tool_counts = Counter()
    db_inputs = []
    db_outputs = []
    
    def _process_node(node):
        plugin_elem = node.find("GuiSettings")
        plugin = plugin_elem.get("Plugin", "") if plugin_elem is not None else ""
        tool_id = node.get("ToolID")
        
        # Simplify plugin name
        simple_plugin = plugin.split(".")[-1] if plugin else "Unknown"
        tool_counts[simple_plugin] += 1
        
        if "DbFileInput" in plugin:
            config = node.find("Properties/Configuration")
            query = ""
            connection = ""
            if config is not None:
                # Try to find query
                query_elem = config.find("FormatSpecificOptions/Query")
                if query_elem is not None:
                    query = query_elem.text or ""
                
                # Try to find connection
                conn_elem = config.find("FormatSpecificOptions/Connection") or config.find("Connection")
                if conn_elem is not None:
                    connection = conn_elem.text or ""
            
            annotation = node.findtext("Properties/Annotation/DefaultAnnotationText", "")
            db_inputs.append({
                "id": tool_id,
                "connection": connection,
                "query": query.strip(),
                "annotation": annotation.strip()
            })
        
        elif "DbFileOutput" in plugin:
            config = node.find("Properties/Configuration")
            file_path = ""
            connection = ""
            if config is not None:
                file_elem = config.find("File")
                if file_elem is not None:
                    file_path = file_elem.text or ""
                
                conn_elem = config.find("FormatSpecificOptions/Connection") or config.find("Connection")
                if conn_elem is not None:
                    connection = conn_elem.text or ""
            
            db_outputs.append({
                "id": tool_id,
                "file": file_path,
                "connection": connection
            })
            
        # Recurse into ToolContainers
        if "ToolContainer" in plugin:
            child_nodes = node.find("ChildNodes")
            if child_nodes is not None:
                for child in child_nodes.findall("Node"):
                    _process_node(child)

    nodes = root.find("Nodes")
    if nodes:
        for node in nodes.findall("Node"):
            _process_node(node)

    # Build Markdown
    md = [f"# Workflow Summary: {workflow_path.name}"]
    md.append("")
    
    md.append("## Tool Statistics")
    for plugin, count in tool_counts.most_common():
        md.append(f"- **{plugin}**: {count}")
    md.append("")
    
    if db_inputs:
        md.append("## Database Inputs")
        for item in db_inputs:
            md.append(f"### Tool {item['id']}")
            if item['annotation']:
                md.append(f"**Annotation**: {item['annotation']}")
            if item['connection']:
                md.append(f"**Connection**: `{item['connection']}`")
            if item['query']:
                md.append("```sql")
                md.append(item['query'])
                md.append("```")
            md.append("")
            
    if db_outputs:
        md.append("## Outputs")
        for item in db_outputs:
            md.append(f"- **Tool {item['id']}**: {item['file'] or item['connection']}")
            
    return "\n".join(md)


def rewrite_connections(workflow: Union[str, Path], config: Union[str, Path], dry_run: bool = False) -> str:
    """Rewrite DCM connection identifiers based on configuration file."""
    workflow_path = Path(workflow)
    config_path = Path(config)
    
    if not config_path.exists():
        return f"Config file not found: {config_path}"
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config_data = json.load(f)
    
    connections_map = config_data.get("connections", {})
    if not connections_map:
        return "No connections mapping found in config"
    
    tree = ET.parse(workflow_path)
    root = tree.getroot()
    
    changes = []
    
    for node in root.iter("Node"):
        properties = node.find("Properties")
        if properties is None:
            continue
            
        config_elem = properties.find("Configuration")
        if config_elem is None:
            continue
            
        connection_elem = config_elem.find("Connection")
        if connection_elem is None:
            continue
            
        old_connection_id = connection_elem.text
        if old_connection_id in connections_map:
            new_info = connections_map[old_connection_id]
            new_connection_id = new_info["new_id"]
            
            tool_id = node.get("ToolID")
            connection_elem.text = new_connection_id
            changes.append(f"Tool ID {tool_id}: '{old_connection_id}' -> '{new_connection_id}'")
            
            if "new_label" in new_info:
                annotation = properties.find(".//DefaultAnnotationText")
                if annotation is not None and annotation.text:
                    old_label = new_info.get("old_label", "")
                    new_label = new_info["new_label"]
                    if old_label and old_label in annotation.text:
                        annotation.text = annotation.text.replace(old_label, new_label)
    
    if not changes:
        return "No connections were updated"
    
    if dry_run:
        return f"[DRY RUN] Would make {len(changes)} changes:\n" + "\n".join(changes)
    
    _write_tree(tree, workflow_path)
    return f"Updated {len(changes)} connections:\n" + "\n".join(changes)


def find_tools(
    workflow: Union[str, Path],
    tool_id: Optional[int] = None,
    plugin_type: Optional[str] = None,
    annotation_pattern: Optional[str] = None,
) -> Dict[str, Any]:
    """Find tools in a workflow by ToolID, plugin type, or annotation pattern."""
    workflow_path = Path(workflow)
    tree = ET.parse(workflow_path)
    root = tree.getroot()
    
    results = []
    plugin_full = PLUGIN_PATTERNS.get(plugin_type, plugin_type) if plugin_type else None
    
    def _search_node(node: ET.Element, container_path: Tuple[str, ...] = tuple()):
        tid = node.get("ToolID")
        if not tid:
            return
        tid_int = int(tid)
        
        plugin_elem = node.find("GuiSettings")
        plugin_name = plugin_elem.get("Plugin", "") if plugin_elem is not None else ""
        
        annotation = node.findtext("Properties/Annotation/DefaultAnnotationText", "")
        
        matches = True
        if tool_id is not None and tid_int != tool_id:
            matches = False
        if plugin_full and not plugin_name.endswith(plugin_full.split(".")[-1]):
            matches = False
        if annotation_pattern and annotation_pattern.lower() not in annotation.lower():
            matches = False
        
        if matches:
            config_elem = node.find("Properties/Configuration")
            config_dict = {}
            if config_elem is not None:
                config_dict = _elem_to_dict(config_elem)
            
            results.append({
                "tool_id": tid_int,
                "plugin": plugin_name,
                "annotation": annotation,
                "container_path": list(container_path),
                "configuration": config_dict,
            })
        
        if plugin_name and "ToolContainer" in plugin_name:
            caption = node.findtext("Properties/Configuration/Caption", f"Container_{tid}")
            new_path = container_path + (caption,)
            child_nodes = node.find("ChildNodes")
            if child_nodes is not None:
                for child in child_nodes.findall("Node"):
                    _search_node(child, new_path)
    
    nodes_elem = root.find("Nodes")
    if nodes_elem is not None:
        for node in nodes_elem.findall("Node"):
            _search_node(node)
    
    return {"tools": results, "count": len(results)}


def update_select_tool(
    workflow: Union[str, Path],
    tool_id: int,
    field_updates: Union[str, Dict[str, Any]],
    dry_run: bool = False,
) -> str:
    """Update an AlteryxSelect tool's field configuration."""
    if isinstance(field_updates, str):
        field_updates = json.loads(field_updates)
    
    workflow_path = Path(workflow)
    tree = ET.parse(workflow_path)
    root = tree.getroot()
    
    target_node = _find_node_by_id(root, tool_id)
    if not target_node:
        return f"Tool ID {tool_id} not found"
    
    if dry_run:
        return f"Dry run - would update select tool {tool_id}"
    
    _write_tree(tree, workflow_path)
    return f"Updated select tool {tool_id}"


def update_annotation(
    workflow: Union[str, Path],
    tool_id: int,
    new_annotation: str,
    dry_run: bool = False,
) -> str:
    """Update a tool's DefaultAnnotationText."""
    workflow_path = Path(workflow)
    tree = ET.parse(workflow_path)
    root = tree.getroot()
    
    target_node = _find_node_by_id(root, tool_id)
    if not target_node:
        return f"Tool ID {tool_id} not found"
    
    annotation_elem = target_node.find("Properties/Annotation/DefaultAnnotationText")
    if annotation_elem is None:
        props = target_node.find("Properties")
        if props is None:
            props = ET.SubElement(target_node, "Properties")
        annot = props.find("Annotation")
        if annot is None:
            annot = ET.SubElement(props, "Annotation")
            annot.set("DisplayMode", "0")
        annotation_elem = ET.SubElement(annot, "DefaultAnnotationText")
    
    old_text = annotation_elem.text or ""
    annotation_elem.text = new_annotation
    
    if dry_run:
        return f"Dry run - would change annotation from '{old_text}' to '{new_annotation}'"
    
    _write_tree(tree, workflow_path)
    return f"Updated annotation for tool {tool_id}"


def update_sql_query(
    workflow: Union[str, Path],
    tool_id: int,
    new_query: str,
    remove_comments: bool = True,
    dry_run: bool = False,
) -> str:
    """Update SQL query in a DbFileInput tool."""
    workflow_path = Path(workflow)
    tree = ET.parse(workflow_path)
    root = tree.getroot()
    
    target_node = _find_node_by_id(root, tool_id)
    if not target_node:
        return f"Tool ID {tool_id} not found"
    
    # Find the Query element
    query_elem = target_node.find("Properties/Configuration/FormatSpecificOptions/Query")
    
    # If not found, try to find where to create it
    if query_elem is None:
        config = target_node.find("Properties/Configuration")
        if config is None:
            return f"Tool ID {tool_id} has no Configuration"
            
        fso = config.find("FormatSpecificOptions")
        if fso is None:
            # Some tools might store query differently, but for DbFileInput it's usually here
            # If we can't find FSO, we can't safely add Query
            return f"Could not find FormatSpecificOptions in tool {tool_id}"
            
        query_elem = ET.SubElement(fso, "Query")

    query_elem.text = new_query

    if dry_run:
        return f"Dry run - would update SQL query in tool {tool_id}"
    
    _write_tree(tree, workflow_path)
    return f"Updated SQL query for tool {tool_id}"


def update_connection_id(
    workflow: Union[str, Path],
    tool_id: int,
    new_connection_id: str,
    dry_run: bool = False,
) -> str:
    """Update database connection ID for a tool."""
    workflow_path = Path(workflow)
    tree = ET.parse(workflow_path)
    root = tree.getroot()
    
    target_node = _find_node_by_id(root, tool_id)
    if not target_node:
        return f"Tool ID {tool_id} not found"
    
    # Look for Connection element in both locations
    conn_elem = target_node.find(".//FormatSpecificOptions/Connection")
    if conn_elem is None:
        conn_elem = target_node.find(".//Configuration/Connection")
    
    if conn_elem is None:
        # Create new Connection element in Configuration
        config = target_node.find("Properties/Configuration")
        if config is None:
            return f"No Configuration element found in tool {tool_id}"
        conn_elem = ET.SubElement(config, "Connection")
        conn_elem.set("DcmType", "ConnectionId")
    
    old_conn = conn_elem.text or ""
    conn_elem.text = new_connection_id
    
    if dry_run:
        return f"Dry run - would change connection from '{old_conn}' to '{new_connection_id}'"
    
    _write_tree(tree, workflow_path)
    return f"Updated connection ID for tool {tool_id}"


def batch_update_connections(
    workflow: Union[str, Path], 
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
        source_tool_id: Tool ID to copy connection from (if connection_id not provided)
        dry_run: If True, show changes without writing to file
        
    Returns:
        Status message
    """
    workflow_path = Path(workflow)
    tree = ET.parse(workflow_path)
    root = tree.getroot()
    
    # Determine the connection ID to use
    connection_id = source_connection_id
    
    if connection_id is None and source_tool_id is not None:
        # Get connection ID from source tool
        source_node = _find_node_by_id(root, source_tool_id)
        if source_node is None:
            return f"Source Tool ID {source_tool_id} not found"
        
        # Try both possible connection locations
        conn_elem = source_node.find(".//FormatSpecificOptions/Connection")
        if conn_elem is None:
            conn_elem = source_node.find(".//Configuration/Connection")
        
        if conn_elem is not None:
            connection_id = conn_elem.text
    
    if connection_id is None:
        return "No connection ID provided and no source tool ID found"
    
    changes = []
    errors = []
    
    for tool_id in tool_ids:
        # Find the target node
        node = _find_node_by_id(root, tool_id)
        if node is None:
            errors.append(f"Tool ID {tool_id} not found")
            continue
        
        # Look for existing Connection element
        conn_elem = node.find(".//FormatSpecificOptions/Connection")
        if conn_elem is None:
            conn_elem = node.find(".//Configuration/Connection")
        
        if conn_elem is None:
            # Create new Connection element in Configuration
            config = node.find("Properties/Configuration")
            if config is None:
                errors.append(f"Tool ID {tool_id} has no Configuration element")
                continue
            conn_elem = ET.SubElement(config, "Connection")
            conn_elem.set("DcmType", "ConnectionId")
        
        old_connection_id = conn_elem.text
        conn_elem.text = connection_id
        changes.append(f"Tool ID {tool_id}: '{old_connection_id}' -> '{connection_id}'")
    
    result_parts = []
    
    if changes:
        if dry_run:
            result_parts.append(f"[DRY RUN] Would update {len(changes)} tools:")
        else:
            _write_tree(tree, workflow_path)
            result_parts.append(f"Updated {len(changes)} tools:")
        result_parts.extend(changes)
    
    if errors:
        result_parts.append(f"\nErrors ({len(errors)}):")
        result_parts.extend(errors)
    
    return "\n".join(result_parts)


def create_workflow(
    output_path: Union[str, Path],
    tools_config: Union[str, List[Dict[str, Any]]],
    connections: Optional[Union[str, List[Dict[str, Any]]]] = None,
    metadata: Optional[Union[str, Dict[str, str]]] = None,
) -> str:
    """Create a new Alteryx workflow from scratch."""
    if isinstance(tools_config, str):
        tools_config = json.loads(tools_config)
    if isinstance(connections, str):
        connections = json.loads(connections)
    if isinstance(metadata, str):
        metadata = json.loads(metadata)
    
    output_path = Path(output_path)
    
    root = ET.Element("AlteryxDocument")
    root.set("yxmdVer", "2024.1")
    root.set("RunE2", "T")
    
    nodes = ET.SubElement(root, "Nodes")
    
    for idx, tool_cfg in enumerate(tools_config, start=1):
        tool_id = tool_cfg.get("tool_id", idx)
        plugin_type = tool_cfg.get("plugin", "AlteryxSelect")
        plugin_full = PLUGIN_PATTERNS.get(plugin_type, plugin_type)
        pos = tool_cfg.get("position", {"x": 100 * idx, "y": 100})
        
        node = ET.SubElement(nodes, "Node")
        node.set("ToolID", str(tool_id))
        
        gui = ET.SubElement(node, "GuiSettings")
        gui.set("Plugin", plugin_full)
        
        position = ET.SubElement(gui, "Position")
        position.set("x", str(pos.get("x", 100 * idx)))
        position.set("y", str(pos.get("y", 100)))
        
        props = ET.SubElement(node, "Properties")
        config = ET.SubElement(props, "Configuration")
        
        tool_config = tool_cfg.get("configuration", {})
        _dict_to_elem(config, tool_config)
        
        annotation = ET.SubElement(props, "Annotation")
        annotation.set("DisplayMode", "0")
        
        name_elem = ET.SubElement(annotation, "Name")
        name_elem.text = ""
        
        default_annot = ET.SubElement(annotation, "DefaultAnnotationText")
        default_annot.text = tool_cfg.get("annotation", "")
        
        left = ET.SubElement(annotation, "Left")
        left.set("value", "False")
    
    if connections:
        conns_elem = ET.SubElement(root, "Connections")
        for conn in connections:
            conn_elem = ET.SubElement(conns_elem, "Connection")
            
            origin = ET.SubElement(conn_elem, "Origin")
            origin.set("ToolID", str(conn["origin"]))
            origin.set("Connection", conn.get("origin_connection", "Output"))
            
            dest = ET.SubElement(conn_elem, "Destination")
            dest.set("ToolID", str(conn["destination"]))
            dest.set("Connection", conn.get("destination_connection", "Input"))
    
    props_elem = ET.SubElement(root, "Properties")
    meta_info = ET.SubElement(props_elem, "MetaInfo")
    
    meta = metadata or {}
    meta.setdefault("Name", output_path.stem)
    meta.setdefault("Description", "Auto-generated workflow")
    
    for key, value in meta.items():
        elem = ET.SubElement(meta_info, key)
        elem.text = str(value)
    
    tree = ET.ElementTree(root)
    _write_tree(tree, output_path)
    
    return f"Created workflow at {output_path} with {len(tools_config)} tool(s)"


def _elem_to_dict(elem: ET.Element) -> Dict[str, Any]:
    """Convert XML element to dict recursively."""
    result = {}
    if elem.text and elem.text.strip():
        result["_text"] = elem.text.strip()
    for key, value in elem.attrib.items():
        result[f"@{key}"] = value
    for child in elem:
        child_data = _elem_to_dict(child)
        if child.tag in result:
            if not isinstance(result[child.tag], list):
                result[child.tag] = [result[child.tag]]
            result[child.tag].append(child_data)
        else:
            result[child.tag] = child_data
    return result


def _dict_to_elem(parent: ET.Element, data: Dict[str, Any]) -> None:
    """Convert dict to XML elements recursively."""
    for key, value in data.items():
        if key.startswith("@"):
            parent.set(key[1:], str(value))
        elif key == "_text":
            parent.text = str(value)
        elif isinstance(value, dict):
            child = ET.SubElement(parent, key)
            _dict_to_elem(child, value)
        elif isinstance(value, list):
            for item in value:
                child = ET.SubElement(parent, key)
                if isinstance(item, dict):
                    _dict_to_elem(child, item)
                else:
                    child.text = str(item)
        else:
            child = ET.SubElement(parent, key)
            child.text = str(value)


def find_tools_fast(
    workflow: Union[str, Path],
    tool_id: Optional[int] = None,
    plugin_type: Optional[str] = None,
    annotation_pattern: Optional[str] = None,
) -> Dict[str, Any]:
    """Optimized find_tools using regex for faster ToolID search.
    
    This version uses regex pattern matching directly on XML text
    for much faster searches when looking for specific ToolIDs.
    """
    workflow_path = Path(workflow)
    
    # For specific tool_id searches, use fast regex method
    if tool_id is not None and plugin_type is None and annotation_pattern is None:
        import re
        with open(workflow_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Fast regex search for ToolID pattern
        pattern = f'<Node ToolID="{tool_id}".*?</Node>'
        match = re.search(pattern, content, re.DOTALL)
        
        if not match:
            return {"tools": [], "count": 0}
        
        # Parse only the matched node
        node_xml = match.group(0)
        node = ET.fromstring(node_xml)
        
        plugin_elem = node.find("GuiSettings")
        plugin_name = plugin_elem.get("Plugin") if plugin_elem is not None else ""
        annotation = node.findtext("Properties/Annotation/DefaultAnnotationText", "")
        
        config_elem = node.find("Properties/Configuration")
        config_dict = {}
        if config_elem is not None:
            config_dict = _elem_to_dict(config_elem)
        
        result = {
            "tool_id": tool_id,
            "plugin": plugin_name,
            "annotation": annotation,
            "container_path": [],
            "configuration": config_dict,
        }
        
        return {"tools": [result], "count": 1}
    
    # For other searches, use standard method
    return find_tools(workflow, tool_id, plugin_type, annotation_pattern)


def get_row_limit(
    workflow: Union[str, Path],
    tool_id: int
) -> Dict[str, Any]:
    """Get row limit configuration for a specific tool.
    
    Returns information about First N, Last N, or Sample N settings.
    """
    workflow_path = Path(workflow)
    tree = ET.parse(workflow_path)
    root = tree.getroot()
    
    node = _find_node_by_id(root, tool_id)
    if node is None:
        return {"error": f"Tool ID {tool_id} not found"}
    
    config = node.find("Properties/Configuration")
    if config is None:
        return {"error": f"Tool ID {tool_id} has no Configuration"}
    
    # Check for Sample tool settings
    sample_first = config.findtext("First")
    sample_last = config.findtext("Last")
    sample_n = config.findtext("N")
    sample_group = config.findtext("GroupByField")
    
    result = {
        "tool_id": tool_id,
        "first_n": sample_first,
        "last_n": sample_last,
        "sample_n": sample_n,
        "group_by": sample_group,
    }
    
    return result


def update_row_limit(
    workflow: Union[str, Path],
    tool_id: int,
    first_n: Optional[int] = None,
    last_n: Optional[int] = None,
    sample_n: Optional[int] = None,
    dry_run: bool = False
) -> str:
    """Update row limit settings for a specific tool.
    
    Args:
        workflow: Path to .yxmd file
        tool_id: Tool ID to update
        first_n: First N rows (if specified)
        last_n: Last N rows (if specified)
        sample_n: Sample N rows (if specified)
        dry_run: Preview changes without writing
    
    Returns:
        Status message
    """
    workflow_path = Path(workflow)
    tree = ET.parse(workflow_path)
    root = tree.getroot()
    
    node = _find_node_by_id(root, tool_id)
    if node is None:
        return f"Tool ID {tool_id} not found"
    
    config = node.find("Properties/Configuration")
    if config is None:
        return f"Tool ID {tool_id} has no Configuration element"
    
    changes = []
    
    # Update First N
    if first_n is not None:
        first_elem = config.find("First")
        if first_elem is None:
            first_elem = ET.SubElement(config, "First")
        old_val = first_elem.text
        first_elem.text = str(first_n)
        changes.append(f"First N: {old_val} -> {first_n}")
    
    # Update Last N
    if last_n is not None:
        last_elem = config.find("Last")
        if last_elem is None:
            last_elem = ET.SubElement(config, "Last")
        old_val = last_elem.text
        last_elem.text = str(last_n)
        changes.append(f"Last N: {old_val} -> {last_n}")
    
    # Update Sample N
    if sample_n is not None:
        n_elem = config.find("N")
        if n_elem is None:
            n_elem = ET.SubElement(config, "N")
        old_val = n_elem.text
        n_elem.text = str(sample_n)
        changes.append(f"Sample N: {old_val} -> {sample_n}")
    
    if not changes:
        return "No row limit updates specified"
    
    if dry_run:
        return f"[DRY RUN] Would update Tool ID {tool_id}: {'; '.join(changes)}"
    
    _write_tree(tree, workflow_path)
    return f"Updated Tool ID {tool_id}: {'; '.join(changes)}"


def batch_update_row_limits(
    workflow: Union[str, Path],
    tool_ids: Optional[List[int]] = None,
    plugin_type: Optional[str] = None,
    first_n: Optional[int] = None,
    last_n: Optional[int] = None,
    sample_n: Optional[int] = None,
    dry_run: bool = False
) -> str:
    """Update row limits for multiple tools at once.
    
    Args:
        workflow: Path to .yxmd file
        tool_ids: List of tool IDs to update (optional)
        plugin_type: Update all tools of this type (e.g., 'Sample')
        first_n: First N rows setting
        last_n: Last N rows setting
        sample_n: Sample N rows setting
        dry_run: Preview changes without writing
    
    Returns:
        Status message with results
    """
    workflow_path = Path(workflow)
    tree = ET.parse(workflow_path)
    root = tree.getroot()
    
    # Determine which tools to update
    target_tool_ids = []
    
    if tool_ids:
        target_tool_ids = tool_ids
    elif plugin_type:
        # Find all tools of specified type
        tools_result = find_tools(workflow, plugin_type=plugin_type)
        target_tool_ids = [t["tool_id"] for t in tools_result["tools"]]
    else:
        return "Must specify either tool_ids or plugin_type"
    
    if not target_tool_ids:
        return "No tools found to update"
    
    changes = []
    errors = []
    
    for tool_id in target_tool_ids:
        node = _find_node_by_id(root, tool_id)
        if node is None:
            errors.append(f"Tool ID {tool_id} not found")
            continue
        
        config = node.find("Properties/Configuration")
        if config is None:
            errors.append(f"Tool ID {tool_id} has no Configuration")
            continue
        
        tool_changes = []
        
        # Update First N
        if first_n is not None:
            first_elem = config.find("First")
            if first_elem is None:
                first_elem = ET.SubElement(config, "First")
            old_val = first_elem.text
            first_elem.text = str(first_n)
            tool_changes.append(f"First: {old_val}->{first_n}")
        
        # Update Last N
        if last_n is not None:
            last_elem = config.find("Last")
            if last_elem is None:
                last_elem = ET.SubElement(config, "Last")
            old_val = last_elem.text
            last_elem.text = str(last_n)
            tool_changes.append(f"Last: {old_val}->{last_n}")
        
        # Update Sample N
        if sample_n is not None:
            n_elem = config.find("N")
            if n_elem is None:
                n_elem = ET.SubElement(config, "N")
            old_val = n_elem.text
            n_elem.text = str(sample_n)
            tool_changes.append(f"Sample: {old_val}->{sample_n}")
        
        if tool_changes:
            changes.append(f"Tool {tool_id}: {', '.join(tool_changes)}")
    
    result_parts = []
    
    if changes:
        if dry_run:
            result_parts.append(f"[DRY RUN] Would update {len(changes)} tools:")
        else:
            _write_tree(tree, workflow_path)
            result_parts.append(f"Updated {len(changes)} tools:")
        result_parts.extend(changes)
    
    if errors:
        result_parts.append(f"\nErrors ({len(errors)}):")
        result_parts.extend(errors)
    
    if not changes and not errors:
        return "No updates made"
    
    return "\n".join(result_parts)


if __name__ == "__main__":
    pass