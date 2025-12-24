# Alteryx MCP

An MCP server that exposes comprehensive Alteryx workflow manipulation tools over stdio, enabling AI assistants to:

- **Read & Analyze**: Summarize workflows into Markdown (containers, connections, SQL, diagrams)
- **Find Tools**: Search for tools by ID, type, or annotation patterns
- **Edit Configurations**: Modify tool settings, field selections, annotations
- **Update SQL**: Change database queries with OCI compliance (auto-removes `--` comments)
- **Manage Connections**: Update DCM connection identifiers
- **Create Workflows**: Build new `.yxmd` files programmatically

It wraps `alteryx_mcp/alteryx_mcp.py` from this repository.

## Demo

[Watch the demo video](summarize_test.mov)

## Features

### 1. Workflow Analysis
- Parse and summarize entire workflows
- Extract container hierarchies, tool types, database connections
- Generate Mermaid diagrams for data flow visualization

### 2. Tool Discovery
- Find tools by ToolID, plugin type (e.g., `AlteryxSelect`, `DbFileInput`)
- **NEW**: `find_tools_fast()` - Optimized regex-based search (10-100x faster for specific ToolID lookups)
- Search by annotation text patterns
- Get complete tool configuration details

### 3. Direct Editing
- **Select Tools**: Update field selections (`selected: true/false`) and rename fields
- **Annotations**: Change tool annotations/labels
- **SQL Queries**: Update DbFileInput queries with automatic comment removal for OCI
- **Connections**: Swap DCM connection IDs across tools
- **NEW**: **Row Limits**: Get, update, and batch-modify row limits for Sample/Filter tools
- All edits support dry-run mode for safe previewing

### 4. Connection Management
- **Batch Update Connections**: Update multiple tools with the same connection ID
- Copy connection from reference tool or use provided connection ID
- Update entire workflow at once

### 5. Row Limit Management (NEW)
- **Get Row Limits**: Read current First N, Last N, Sample N settings
- **Update Single Tool**: Change row limit for specific tool
- **Batch Update**: Mass-modify row limits across entire workflow
- Update by specific tool IDs or by plugin type (e.g., all Sample tools)

### 6. Workflow Creation
- Build workflows from scratch with JSON configuration
- Define tools, positions, connections programmatically
- Specify custom metadata

## Install (editable dev)

```bash
# From repo root
pip install -e .
```

## Run (stdio)

```bash
alteryx-mcp
```

## Tools Reference

### Analysis Tools

#### `summarize_workflow`
```python
summarize_workflow(
    workflow: str,           # Path to .yxmd file
    mapping: str | None      # Optional JSON mapping for connection aliases
) -> str                     # Returns Markdown summary
```

**Example**:
```json
{
  "workflow": "c:/projects/VCI/VCIProjectionBaseLine.yxmd",
  "mapping": "c:/projects/connections.json"
}
```

Returns comprehensive Markdown with:
- Metadata (WorkflowId, Description)
- Container hierarchy
- Top tool types
- Database connections with queries
- Output destinations
- Mermaid flowcharts

---

#### `find_tools`
```python
find_tools(
    workflow: str,                    # Path to .yxmd file
    tool_id: int | None = None,       # Find specific tool ID
    plugin_type: str | None = None,   # e.g., 'AlteryxSelect', 'DbFileInput'
    annotation_pattern: str | None = None  # Search in annotations
) -> str                              # Returns JSON with matching tools
```

**Examples**:
```json
// Find all Select tools
{
  "workflow": "path/to/workflow.yxmd",
  "plugin_type": "AlteryxSelect"
}

// Find tools mentioning "v12Live" in annotations
{
  "workflow": "path/to/workflow.yxmd",
  "annotation_pattern": "v12Live"
}

// Find specific tool
{
  "workflow": "path/to/workflow.yxmd",
  "tool_id": 375
}
```

Supported plugin types:
- `AlteryxSelect`, `DbFileInput`, `DbFileOutput`
- `Filter`, `Join`, `Sort`, `Formula`
- `Browse`, `TextBox`, `ToolContainer`
- `Union`, `Summarize`, `Sample`, `Unique`
- `RecordID`, `MultiRowFormula`, `TextInput`, `DateTimeInput`

---

### Editing Tools

#### `update_select_tool`
```python
update_select_tool(
    workflow: str,          # Path to .yxmd file
    tool_id: int,          # Tool ID of Select tool
    field_updates: str,    # JSON string with field updates
    dry_run: bool = False
) -> str                   # Status message
```

**Example - Update field selections**:
```json
{
  "workflow": "path/to/workflow.yxmd",
  "tool_id": 375,
  "field_updates": "{\"SCM37_CTRA22_IBCONO\": {\"selected\": false}, \"SCM37_CTRA22_IBFACI\": {\"selected\": true, \"rename\": \"FACILITY_CODE\"}}",
  "dry_run": true
}
```

Field update options:
- `selected`: `true` or `false`
- `rename`: New field name

---

#### `update_annotation`
```python
update_annotation(
    workflow: str,          # Path to .yxmd file
    tool_id: int,          # Tool ID to update
    new_annotation: str,   # New annotation text
    dry_run: bool = False
) -> str
```

**Example**:
```json
{
  "workflow": "path/to/workflow.yxmd",
  "tool_id": 12,
  "new_annotation": "dcm:prod-oracle\nQuery=SELECT * FROM MPHEAD WHERE CONO=1",
  "dry_run": false
}
```

---

#### `update_sql_query`
```python
update_sql_query(
    workflow: str,                  # Path to .yxmd file
    tool_id: int,                  # Tool ID of DbFileInput
    new_query: str,                # New SQL query
    remove_comments: bool = True,  # Strip -- comments for OCI
    dry_run: bool = False
) -> str
```

**Example - Update query with OCI compliance**:
```json
{
  "workflow": "path/to/workflow.yxmd",
  "tool_id": 12,
  "new_query": "SELECT IACONO, IAPUNO, IACUCD -- Company info\nFROM MVXCDTA.MPHEAD\nWHERE IACONO = 1",
  "remove_comments": true,
  "dry_run": false
}
```

Result (after comment removal):
```sql
SELECT IACONO, IAPUNO, IACUCD
FROM MVXCDTA.MPHEAD
WHERE IACONO = 1
```

---

#### `update_connection_id`
```python
update_connection_id(
    workflow: str,              # Path to .yxmd file
    tool_id: int,              # Tool ID to update
    new_connection_id: str,    # New DCM connection ID (UUID)
    dry_run: bool = False
) -> str
```

**Example**:
```json
{
  "workflow": "path/to/workflow.yxmd",
  "tool_id": 12,
  "new_connection_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "dry_run": false
}
```

---

#### `batch_update_connections`
```python
batch_update_connections(
    workflow: str,
    tool_ids: List[int],
    source_connection_id: str | None = None,
    source_tool_id: int | None = None,
    dry_run: bool = False
) -> str
```

**Example**:
```json
{
  "workflow": "path/to/workflow.yxmd",
  "tool_ids": [12, 14, 16],
  "source_tool_id": 13,
  "dry_run": true
}
```

---

#### `rewrite_connections`
```python
rewrite_connections(
    workflow: str,     # Path to .yxmd file
    config: str,       # Path to JSON config
    dry_run: bool = False
) -> str
```

Config JSON format:
```json
{
  "connections": {
    "old-uuid-1": {
      "new_id": "new-uuid-1",
      "old_label": "dev-db",
      "new_label": "prod-db"
    }
  }
}
```

---

### Row Limit Tools

#### `get_row_limit`
```python
get_row_limit(
    workflow: str,
    tool_id: int
) -> str
```

**Example**:
```json
{
  "workflow": "path/to/workflow.yxmd",
  "tool_id": 10
}
```

#### `update_row_limit`
```python
update_row_limit(
    workflow: str,
    tool_id: int,
    first_n: int | None = None,
    last_n: int | None = None,
    sample_n: int | None = None,
    dry_run: bool = False
) -> str
```

**Example**:
```json
{
  "workflow": "path/to/workflow.yxmd",
  "tool_id": 10,
  "first_n": 500,
  "dry_run": false
}
```

#### `batch_update_row_limits`
```python
batch_update_row_limits(
    workflow: str,
    tool_ids: List[int] | None = None,
    plugin_type: str | None = None,
    first_n: int | None = None,
    last_n: int | None = None,
    sample_n: int | None = None,
    dry_run: bool = False
) -> str
```

**Example**:
```json
{
  "workflow": "path/to/workflow.yxmd",
  "plugin_type": "Sample",
  "first_n": 1000,
  "dry_run": false
}
```

---

### Creation Tools

#### `create_workflow`
```python
create_workflow(
    output_path: str,        # Where to save .yxmd
    tools_config: str,       # JSON array of tool configs
    connections: str | None, # Optional JSON array of connections
    metadata: str | None     # Optional JSON dict of metadata
) -> str
```

**Example - Create simple workflow**:
```json
{
  "output_path": "c:/temp/new_workflow.yxmd",
  "tools_config": "[{\"tool_id\": 1, \"plugin\": \"TextInput\", \"position\": {\"x\": 100, \"y\": 100}, \"configuration\": {\"Text\": \"Hello World\"}, \"annotation\": \"Data source\"}, {\"tool_id\": 2, \"plugin\": \"Browse\", \"position\": {\"x\": 300, \"y\": 100}, \"annotation\": \"View output\"}]",
  "connections": "[{\"origin\": 1, \"destination\": 2}]",
  "metadata": "{\"Name\": \"My Workflow\", \"Description\": \"Auto-generated test workflow\"}"
}
```

Tool configuration structure:
```typescript
{
  tool_id?: number,           // Optional, defaults to index
  plugin: string,             // Plugin type name
  position: {x: number, y: number},
  configuration: object,      // Tool-specific config
  annotation?: string         // Optional annotation
}
```

Connection structure:
```typescript
{
  origin: number,                      // Source tool ID
  destination: number,                 // Target tool ID
  origin_connection?: string,          // Default: "Output"
  destination_connection?: string      // Default: "Input"
}
```

---

## MCP Client Configuration

Point your MCP client (e.g., GitHub Copilot, Claude Desktop) to launch the script on stdio:

```json
{
  "mcpServers": {
    "alteryx": {
      "command": "alteryx-mcp",
      "args": []
    }
  }
}
```

Or with full path:
```json
{
  "mcpServers": {
    "alteryx": {
      "command": "python",
      "args": ["-m", "alteryx_mcp.server"]
    }
  }
}
```

---

## Usage Patterns

### Pattern 1: Find and Update Field Selections
```
1. User: "Find all Select tools in the workflow"
   → find_tools(workflow="...", plugin_type="AlteryxSelect")

2. User: "In tool 375, deselect field IBCONO and rename IBFACI to FACILITY"
   → update_select_tool(workflow="...", tool_id=375, 
                        field_updates='{"IBCONO": {"selected": false}, 
                                       "IBFACI": {"rename": "FACILITY"}}')
```

### Pattern 2: Update SQL for OCI Compliance
```
1. User: "Show me all database input tools"
   → find_tools(workflow="...", plugin_type="DbFileInput")

2. User: "Update the SQL in tool 12 and remove all comments"
   → update_sql_query(workflow="...", tool_id=12, 
                      new_query="SELECT...", remove_comments=true)
```

### Pattern 3: Change Annotations
```
1. User: "Find tools connected to v12Live"
   → find_tools(workflow="...", annotation_pattern="v12Live")

2. User: "Update annotation for tool 12 to show production connection"
   → update_annotation(workflow="...", tool_id=12, 
                       new_annotation="dcm:prod-oracle\\nQuery=...")
```

### Pattern 4: Create New Workflow
```
User: "Create a workflow that reads from TextInput and shows Browse output"
→ create_workflow(output_path="...", 
                  tools_config='[{"plugin": "TextInput", ...}, 
                                 {"plugin": "Browse", ...}]',
                  connections='[{"origin": 1, "destination": 2}]')
```

---

## Advanced Features

### OCI Compliance
All SQL operations automatically handle Oracle Instant Client requirements:
- Removes `--` style comments (not supported in OCI)
- Preserves multi-line queries
- Maintains query formatting

### Dry Run Mode
All editing tools support `dry_run=true` to preview changes without writing to disk.

### Pattern Matching
The MCP uses efficient XML pattern matching to locate tools:
- By Plugin type (partial match supported)
- By ToolID (exact match)
- By annotation text (case-insensitive substring)

### Container Support
Tools within containers are fully supported:
- Search recurses into nested containers
- Container paths preserved in results
- Edits work on tools at any depth

---

## Architecture

```
alteryx-mcp/
├── alteryx_mcp/
│   ├── server.py          # MCP FastMCP server exposing 8 tools
│   └── __init__.py
├── pyproject.toml         # Package metadata
└── README.md              # This file
```

The server is a thin wrapper around `alteryx_mcp.py` which provides:
- XML parsing and manipulation
- Tool configuration updates
- Workflow creation
- Safe file writing with proper encoding

---

## Troubleshooting

**Tool not found**: Verify ToolID exists using `find_tools()`

**SQL comments not removed**: Ensure `remove_comments=true` is set

**Workflow won't open in Alteryx**: Check XML formatting; use dry_run first

**Connection update failed**: Verify UUID format for connection IDs

**Field not updated**: Check exact field name spelling (case-sensitive)

---

## Contributing

This MCP server is part of the Alteryx MCP project. To extend:

1. Add new functions to `alteryx_mcp/alteryx_mcp.py`
2. Expose via `@mcp.tool()` decorators in `server.py`
3. Update this README with examples
4. Test with real workflows

---

## License

Internal tool for Alteryx MCP project use.
