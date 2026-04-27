# MCP Server Setup Plan for Knowledge Studio

## Overview
Set up a read-only MCP (Model Context Protocol) server to expose Knowledge Studio database queries to Claude Desktop. This will allow Claude to query your video library, search by topics, find videos by channel, and more.

## Prerequisites
- Python 3.10+ installed
- Claude Desktop application installed
- Existing Knowledge Studio database (`youtube_intelligence.db`)
- Project location: `/Users/bossmdaddy/Desktop/screenshot-ai-claude rapid IT/`

---

## Step 1: Install MCP Python SDK

```bash
# Navigate to project directory
cd "/Users/bossmdaddy/Desktop/screenshot-ai-claude rapid IT"

# Install MCP SDK using pip
pip install mcp

# Or if using uv (recommended)
curl -LsSf https://astral.sh/uv/install.sh | sh
uv add "mcp[cli]"
```

---

## Step 2: Create MCP Server File

Create `knowledge_studio_mcp.py` in the project root that:

1. **Imports required modules:**
   - MCP SDK components
   - DatabaseService from `app.py` (or creates a read-only wrapper)
   - SQLite for direct database access

2. **Wraps existing DatabaseService methods as MCP tools:**
   - `search_videos(query, channel_id=None, channel_name=None)` - Text search across videos
   - `get_video_by_id(video_id)` - Get single video details
   - `get_videos_by_channel(channel_id=None, channel_name=None, limit=50)` - Get all videos from a channel
   - `get_recent_videos(limit=20)` - Get most recently processed videos
   - `search_by_topic(topic, limit=20)` - Search videos by topics column

3. **Uses MCP tool decorators** to expose functions

---

## Step 3: Implement Helper Methods

Since `get_recent_videos` and `search_by_topic` may not exist in DatabaseService, add them:

### `get_recent_videos(limit=20)`
- Query: `SELECT ... FROM videos WHERE status = 'completed' ORDER BY processing_date DESC LIMIT ?`
- Returns: List of most recently processed videos

### `search_by_topic(topic, limit=20)`
- Query: `SELECT ... FROM videos WHERE status = 'completed' AND topics LIKE ? ORDER BY processing_date DESC LIMIT ?`
- Searches the `topics` column (TEXT field that may contain JSON or comma-separated topics)

---

## Step 4: Configure Claude Desktop

1. **Locate Claude Desktop config file:**
   - macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - Create if it doesn't exist

2. **Add MCP server configuration:**
```json
{
  "mcpServers": {
    "knowledge-studio": {
      "command": "python",
      "args": [
        "/Users/bossmdaddy/Desktop/screenshot-ai-claude rapid IT/knowledge_studio_mcp.py"
      ],
      "env": {}
    }
  }
}
```

3. **Restart Claude Desktop** to load the MCP server

---

## Step 5: Test the Connection

1. **Test MCP server directly:**
```bash
python knowledge_studio_mcp.py
```

2. **In Claude Desktop, verify:**
   - Ask Claude: "What MCP tools do you have access to?"
   - Try: "Search my Knowledge Studio for videos about AI"
   - Try: "Get recent videos from my library"

---

## Step 6: MCP Server Structure

The server should:

1. **Initialize DatabaseService** (read-only mode)
2. **Define MCP tools** with proper schemas:
   - Input parameter types (str, int, optional params)
   - Return types (list of dicts)
   - Descriptions for each tool
3. **Handle errors gracefully** (return error messages, don't crash)
4. **Use stdio transport** (MCP default for local servers)

---

## Key Functions to Expose

### 1. `search_videos`
- **Input:** `query` (str), `channel_id` (str, optional), `channel_name` (str, optional)
- **Output:** List of video dicts with: id, title, channel, video_url, summary, transcript_length, etc.
- **Description:** "Search videos by text query across title, channel, transcript, and summary. Optionally filter by channel."

### 2. `get_video_by_id`
- **Input:** `video_id` (int)
- **Output:** Single video dict with full details including transcript
- **Description:** "Get complete details for a specific video by ID."

### 3. `get_videos_by_channel`
- **Input:** `channel_id` (str, optional), `channel_name` (str, optional), `limit` (int, default 50)
- **Output:** List of video dicts from specified channel
- **Description:** "Get all videos from a specific channel. Provide either channel_id or channel_name."

### 4. `get_recent_videos`
- **Input:** `limit` (int, default 20)
- **Output:** List of most recently processed videos
- **Description:** "Get the most recently processed videos, ordered by processing date."

### 5. `search_by_topic`
- **Input:** `topic` (str), `limit` (int, default 20)
- **Output:** List of videos matching the topic
- **Description:** "Search videos by topic keyword. Searches the topics column for matches."

---

## Security Considerations

- ✅ **Read-only:** All queries are SELECT only, no writes
- ✅ **Local only:** Server runs on localhost, not exposed to network
- ✅ **No authentication needed:** Local MCP servers don't require auth
- ✅ **Error handling:** Wrap all DB operations in try/except

---

## Troubleshooting

### MCP server won't start
- Check Python path in Claude config matches your system
- Verify MCP SDK is installed: `pip show mcp`
- Check file permissions on `knowledge_studio_mcp.py`

### Claude can't see tools
- Restart Claude Desktop after config changes
- Check Claude Desktop logs for MCP errors
- Verify server starts without errors when run directly

### Database errors
- Verify `youtube_intelligence.db` exists in project root
- Check database file permissions
- Ensure SQLite3 is available: `python -c "import sqlite3"`

---

## Next Steps After Setup

1. Test each MCP tool individually
2. Create example queries for common use cases
3. Consider adding more tools:
   - `get_all_channels()` - List subscribed channels
   - `get_videos_by_date_range(start_date, end_date)` - Filter by date
   - `get_videos_by_tag(tag)` - Search by user tags
   - `get_statistics()` - Database stats

---

## File Structure

```
/Users/bossmdaddy/Desktop/screenshot-ai-claude rapid IT/
├── app.py                          # Existing Flask app with DatabaseService
├── youtube_intelligence.db         # SQLite database
├── knowledge_studio_mcp.py         # NEW: MCP server file
└── MCP_SETUP_PLAN.md              # This file
```

---

## Example MCP Tool Definition

```python
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

app = Server("knowledge-studio")

@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="search_videos",
            description="Search videos by text query across title, channel, transcript, and summary",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "channel_id": {"type": "string", "description": "Optional channel ID filter"},
                    "channel_name": {"type": "string", "description": "Optional channel name filter"}
                },
                "required": ["query"]
            }
        ),
        # ... more tools
    ]
```

---

## Resources

- MCP Documentation: https://modelcontextprotocol.io
- MCP Python SDK: https://github.com/modelcontextprotocol/python-sdk
- Claude Desktop MCP Guide: https://modelcontextprotocol.io/quickstart/desktop








