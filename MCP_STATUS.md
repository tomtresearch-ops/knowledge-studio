# MCP Server Status & Usage Guide

## Current Status

**MCP Server:** Not currently running (will start automatically when Claude Desktop connects)

**Configuration:** 
- File: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Server: `knowledge-studio`
- Command: `/Users/bossmdaddy/Desktop/screenshot-ai-claude rapid IT/venv_mcp/bin/python`
- Script: `knowledge_studio_mcp.py`

## How MCP Works

### Server Lifecycle
1. **Starts automatically** when Claude Desktop launches
2. **Stays running** while Claude Desktop is open (persistent connection via stdio)
3. **Stops automatically** when Claude Desktop closes
4. **No manual management needed** - Claude Desktop handles start/stop

### Database Connection Handling
- ✅ **Connections are opened per-query** (not kept open)
- ✅ **Connections are closed immediately** after each query completes
- ✅ **Uses WAL mode** for concurrent access (readers don't block writers)
- ✅ **Short timeout (5s)** so MCP queries don't block main app
- ✅ **Read-only queries** - no writes that could interfere

### Query Flow
```
Claude Desktop → MCP Server → Open DB connection → Execute query → Close connection → Return results
```

Each query:
1. Opens a fresh database connection
2. Executes the query
3. Closes the connection immediately
4. Returns results to Claude

**No persistent connections** - each query is independent.

## Interference Prevention

### ✅ Already Configured:
1. **WAL Mode** - Enables concurrent reads/writes
   - Main app can write while MCP reads
   - No blocking between operations

2. **Connection Timeouts**
   - MCP: 5 second timeout (fails fast if locked)
   - Main app: 10 second timeout (priority)

3. **Immediate Connection Closing**
   - Every MCP function closes connections after use
   - No connection pooling or persistent connections

4. **Read-Only Operations**
   - MCP only does SELECT queries
   - Never modifies data
   - Can't interfere with video processing

## Usage

### When MCP is Active:
- Claude Desktop is running
- MCP server runs in background automatically
- You can query your Knowledge Studio from Claude Desktop
- No impact on main app performance

### When MCP is Inactive:
- Claude Desktop is closed
- MCP server stops automatically
- Zero overhead when not in use

## Available MCP Tools

1. `search_videos` - Search videos by text
2. `get_video_by_id` - Get single video details
3. `get_videos_by_channel` - Get videos by channel
4. `get_recent_videos` - Get most recent videos
5. `search_by_topic` - Search by topic keyword

## Troubleshooting

### If MCP interferes with main app:
1. **Check database locks:** `lsof youtube_intelligence.db`
2. **Restart Claude Desktop** - this restarts MCP server
3. **Check logs:** Claude Desktop logs show MCP errors

### If MCP doesn't work:
1. **Check Claude Desktop config:** `~/Library/Application Support/Claude/claude_desktop_config.json`
2. **Verify Python path:** Must point to Python 3.12+ with MCP installed
3. **Check server logs:** Run MCP server directly to see errors

## Best Practices

✅ **Safe to use MCP anytime** - Won't interfere with video processing
✅ **No manual management needed** - Claude Desktop handles it
✅ **Zero overhead when not used** - Only active when Claude Desktop is open
✅ **Read-only operations** - Can't break anything

## Summary

- **MCP server:** Managed by Claude Desktop (auto-start/stop)
- **Database connections:** Opened per-query, closed immediately
- **Interference:** Prevented by WAL mode and proper connection handling
- **Usage:** Use whenever you want via Claude Desktop - no manual steps needed








