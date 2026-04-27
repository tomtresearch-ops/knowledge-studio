# MCP Toggle Guide - Enable/Disable Without Closing Claude Desktop

## Quick Toggle

**Double-click:** `TOGGLE_MCP.command` to toggle MCP on/off

## Command Line Usage

```bash
# Check current status
./toggle_mcp.sh status

# Enable MCP
./toggle_mcp.sh on

# Disable MCP  
./toggle_mcp.sh off

# Toggle (switch current state)
./toggle_mcp.sh toggle
```

## How It Works

1. **Modifies Claude Desktop config** - Adds/removes MCP server entry
2. **Kills MCP process** - Stops current connection
3. **Claude Desktop auto-reconnects** - When enabled, Claude will restart MCP automatically
4. **No restart needed** - Claude Desktop detects config changes and reconnects

## When to Use

**Disable MCP when:**
- You want zero database overhead
- Troubleshooting database issues
- Maximum performance for video processing

**Enable MCP when:**
- You want to query Knowledge Studio from Claude Desktop
- You need to search your video library
- You want to use MCP tools

## Status Check

Run `./toggle_mcp.sh status` to see current state:
- ✅ **ENABLED** - MCP is active and available
- ❌ **DISABLED** - MCP is inactive, zero overhead

## Notes

- **No Claude Desktop restart needed** - Config changes are detected automatically
- **Backup created** - Original config saved to `.backup` file
- **Safe to toggle anytime** - Won't break anything








