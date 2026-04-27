#!/usr/bin/env python3
"""
MCP Server for Knowledge Studio
Exposes database queries and operations via Model Context Protocol
"""

import sqlite3
import json
import os
import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Database path - use absolute path based on script location
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_PATH = os.path.join(SCRIPT_DIR, "youtube_intelligence.db")

# Initialize MCP Server
app = Server("knowledge-studio")

def get_connection() -> sqlite3.Connection:
    """Get SQLite connection with dict row factory.
    Uses WAL mode and timeout to prevent blocking the main app."""
    # Use timeout to prevent database locks
    conn = sqlite3.connect(DATABASE_PATH, timeout=5.0)  # Shorter timeout for MCP
    conn.row_factory = sqlite3.Row
    # Enable WAL mode for better concurrent access (readers don't block writers)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA busy_timeout=5000')  # Wait max 5 seconds if locked
    return conn

def search_videos(
    query: str,
    channel_id: Optional[str] = None,
    channel_name: Optional[str] = None,
    limit: int = 20
) -> List[Dict[str, Any]]:
    """
    Search videos by text query, optionally filtered by channel.
    
    Args:
        query: Search term to match against title, channel, transcript, or summary
        channel_id: Optional channel ID to filter results
        channel_name: Optional channel name to filter results
        limit: Maximum number of results to return
    
    Returns:
        List of video dictionaries
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    search_term = f"%{query}%"
    
    # Build query with optional channel filter
    if channel_id:
        # Try channel_videos join first
        query_sql = '''
            SELECT DISTINCT v.id, v.title, v.channel, v.video_url, v.full_transcript,
                   v.ai_summary, v.processing_date, v.status, v.filename, 
                   v.confidence_score, v.tags, v.published_at, 
                   COALESCE(v.favorited, 0) as favorited
            FROM videos v
            INNER JOIN channel_videos cv ON v.id = cv.processed_video_id
            WHERE v.status = 'completed' 
            AND cv.channel_id = ?
            AND (v.title LIKE ? OR v.channel LIKE ? OR v.full_transcript LIKE ? OR v.ai_summary LIKE ?)
            ORDER BY v.processing_date DESC
            LIMIT ?
        '''
        params = (channel_id, search_term, search_term, search_term, search_term, limit)
        cursor.execute(query_sql, params)
        rows = cursor.fetchall()
        
        # Fallback to channel name if no results
        if len(rows) == 0:
            cursor.execute('SELECT channel_name FROM channel_subscriptions WHERE channel_id = ?', (channel_id,))
            sub_row = cursor.fetchone()
            if sub_row and sub_row[0]:
                channel_name = sub_row[0]
                query_sql = '''
                    SELECT id, title, channel, video_url, full_transcript,
                           ai_summary, processing_date, status, filename, 
                           confidence_score, tags, published_at,
                           COALESCE(favorited, 0) as favorited
                    FROM videos 
                    WHERE status = 'completed' 
                    AND channel = ?
                    AND (title LIKE ? OR channel LIKE ? OR full_transcript LIKE ? OR ai_summary LIKE ?)
                    ORDER BY processing_date DESC
                    LIMIT ?
                '''
                params = (channel_name, search_term, search_term, search_term, search_term, limit)
                cursor.execute(query_sql, params)
                rows = cursor.fetchall()
    elif channel_name:
        query_sql = '''
            SELECT id, title, channel, video_url, full_transcript,
                   ai_summary, processing_date, status, filename, 
                   confidence_score, tags, published_at,
                   COALESCE(favorited, 0) as favorited
            FROM videos 
            WHERE status = 'completed' 
            AND channel = ?
            AND (title LIKE ? OR channel LIKE ? OR full_transcript LIKE ? OR ai_summary LIKE ?)
            ORDER BY processing_date DESC
            LIMIT ?
        '''
        params = (channel_name, search_term, search_term, search_term, search_term, limit)
        cursor.execute(query_sql, params)
        rows = cursor.fetchall()
    else:
        query_sql = '''
            SELECT id, title, channel, video_url, full_transcript,
                   ai_summary, processing_date, status, filename, 
                   confidence_score, tags, published_at,
                   COALESCE(favorited, 0) as favorited
            FROM videos 
            WHERE status = 'completed' 
            AND (title LIKE ? OR channel LIKE ? OR full_transcript LIKE ? OR ai_summary LIKE ?)
            ORDER BY processing_date DESC
            LIMIT ?
        '''
        params = (search_term, search_term, search_term, search_term, limit)
        cursor.execute(query_sql, params)
        rows = cursor.fetchall()
    
    videos = []
    for row in rows:
        videos.append({
            'id': row['id'],
            'title': row['title'] or 'Untitled Video',
            'channel': row['channel'] or 'Unknown Channel',
            'video_url': row['video_url'],
            'has_transcript': bool(row['full_transcript']),
            'transcript_length': len(row['full_transcript']) if row['full_transcript'] else 0,
            'summary': row['ai_summary'],
            'processing_date': row['processing_date'],
            'published_at': row['published_at'],
            'status': row['status'],
            'tags': row['tags'] or '',
            'favorited': bool(row['favorited']),
            'confidence_score': row['confidence_score'] or 0
        })
    
    conn.close()
    return videos

def get_video_by_id(video_id: int) -> Optional[Dict[str, Any]]:
    """
    Get a single video by ID.
    
    Args:
        video_id: Video ID
    
    Returns:
        Video dictionary or None if not found
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, title, channel, video_url, full_transcript,
               ai_summary, processing_date, status, filename, 
               confidence_score, tags, published_at, original_publish_date,
               COALESCE(favorited, 0) as favorited, key_insights, topics
        FROM videos 
        WHERE id = ?
    ''', (video_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return None
    
    return {
        'id': row['id'],
        'title': row['title'] or 'Untitled Video',
        'channel': row['channel'] or 'Unknown Channel',
        'video_url': row['video_url'],
        'full_transcript': row['full_transcript'],
        'has_transcript': bool(row['full_transcript']),
        'transcript_length': len(row['full_transcript']) if row['full_transcript'] else 0,
        'summary': row['ai_summary'],
        'key_insights': row['key_insights'],
        'topics': row['topics'],
        'processing_date': row['processing_date'],
        'published_at': row['published_at'] or row['original_publish_date'],
        'status': row['status'],
        'tags': row['tags'] or '',
        'favorited': bool(row['favorited']),
        'confidence_score': row['confidence_score'] or 0
    }

def get_videos_by_channel(
    channel_id: Optional[str] = None,
    channel_name: Optional[str] = None,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """
    Get all videos from a specific channel.
    
    Args:
        channel_id: Channel ID to filter by
        channel_name: Channel name to filter by
        limit: Maximum number of results
    
    Returns:
        List of video dictionaries
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    if channel_id:
        query_sql = '''
            SELECT DISTINCT v.id, v.title, v.channel, v.video_url, v.full_transcript,
                   v.ai_summary, v.processing_date, v.status, v.filename, 
                   v.confidence_score, v.tags, v.published_at,
                   COALESCE(v.favorited, 0) as favorited
            FROM videos v
            INNER JOIN channel_videos cv ON v.id = cv.processed_video_id
            WHERE v.status = 'completed' 
            AND cv.channel_id = ?
            ORDER BY v.processing_date DESC
            LIMIT ?
        '''
        params = (channel_id, limit)
    elif channel_name:
        query_sql = '''
            SELECT id, title, channel, video_url, full_transcript,
                   ai_summary, processing_date, status, filename, 
                   confidence_score, tags, published_at,
                   COALESCE(favorited, 0) as favorited
            FROM videos 
            WHERE status = 'completed' 
            AND channel = ?
            ORDER BY processing_date DESC
            LIMIT ?
        '''
        params = (channel_name, limit)
    else:
        return []
    
    cursor.execute(query_sql, params)
    rows = cursor.fetchall()
    
    videos = []
    for row in rows:
        videos.append({
            'id': row['id'],
            'title': row['title'] or 'Untitled Video',
            'channel': row['channel'] or 'Unknown Channel',
            'video_url': row['video_url'],
            'has_transcript': bool(row['full_transcript']),
            'transcript_length': len(row['full_transcript']) if row['full_transcript'] else 0,
            'summary': row['ai_summary'],
            'processing_date': row['processing_date'],
            'published_at': row['published_at'],
            'status': row['status'],
            'tags': row['tags'] or '',
            'favorited': bool(row['favorited']),
            'confidence_score': row['confidence_score'] or 0
        })
    
    conn.close()
    return videos

def get_videos_by_date_range(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """
    Get videos within a date range.
    
    Args:
        start_date: Start date (YYYY-MM-DD format)
        end_date: End date (YYYY-MM-DD format)
        limit: Maximum number of results
    
    Returns:
        List of video dictionaries
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    query_sql = '''
        SELECT id, title, channel, video_url, full_transcript,
               ai_summary, processing_date, status, filename, 
               confidence_score, tags, published_at,
               COALESCE(favorited, 0) as favorited
        FROM videos 
        WHERE status = 'completed'
    '''
    params = []
    
    if start_date:
        query_sql += ' AND (published_at >= ? OR processing_date >= ?)'
        params.extend([start_date, start_date])
    
    if end_date:
        query_sql += ' AND (published_at <= ? OR processing_date <= ?)'
        params.extend([end_date, end_date])
    
    query_sql += ' ORDER BY processing_date DESC LIMIT ?'
    params.append(limit)
    
    cursor.execute(query_sql, params)
    rows = cursor.fetchall()
    
    videos = []
    for row in rows:
        videos.append({
            'id': row['id'],
            'title': row['title'] or 'Untitled Video',
            'channel': row['channel'] or 'Unknown Channel',
            'video_url': row['video_url'],
            'has_transcript': bool(row['full_transcript']),
            'transcript_length': len(row['full_transcript']) if row['full_transcript'] else 0,
            'summary': row['ai_summary'],
            'processing_date': row['processing_date'],
            'published_at': row['published_at'],
            'status': row['status'],
            'tags': row['tags'] or '',
            'favorited': bool(row['favorited']),
            'confidence_score': row['confidence_score'] or 0
        })
    
    conn.close()
    return videos

def get_all_channels() -> List[Dict[str, Any]]:
    """
    Get all subscribed channels.
    
    Returns:
        List of channel dictionaries
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, channel_id, channel_name, channel_url, 
               created_at, last_checked, enabled
        FROM channel_subscriptions
        ORDER BY channel_name
    ''')
    
    rows = cursor.fetchall()
    channels = []
    for row in rows:
        channels.append({
            'id': row['id'],
            'channel_id': row['channel_id'],
            'channel_name': row['channel_name'],
            'channel_url': row['channel_url'],
            'created_at': row['created_at'],
            'last_checked': row['last_checked'],
            'enabled': bool(row['enabled'])
        })
    
    conn.close()
    return channels

def get_videos_by_tag(tag: str, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Get videos filtered by tag.
    
    Args:
        tag: Tag to search for
        limit: Maximum number of results
    
    Returns:
        List of video dictionaries
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, title, channel, video_url, full_transcript,
               ai_summary, processing_date, status, filename, 
               confidence_score, tags, published_at,
               COALESCE(favorited, 0) as favorited
        FROM videos 
        WHERE status = 'completed'
        AND tags LIKE ?
        ORDER BY processing_date DESC
        LIMIT ?
    ''', (f'%{tag}%', limit))
    
    rows = cursor.fetchall()
    
    videos = []
    for row in rows:
        videos.append({
            'id': row['id'],
            'title': row['title'] or 'Untitled Video',
            'channel': row['channel'] or 'Unknown Channel',
            'video_url': row['video_url'],
            'has_transcript': bool(row['full_transcript']),
            'transcript_length': len(row['full_transcript']) if row['full_transcript'] else 0,
            'summary': row['ai_summary'],
            'processing_date': row['processing_date'],
            'published_at': row['published_at'],
            'status': row['status'],
            'tags': row['tags'] or '',
            'favorited': bool(row['favorited']),
            'confidence_score': row['confidence_score'] or 0
        })
    
    conn.close()
    return videos

def get_recent_videos(limit: int = 20) -> List[Dict[str, Any]]:
    """
    Get most recently processed videos.
    
    Args:
        limit: Maximum number of results
    
    Returns:
        List of video dictionaries
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, title, channel, video_url, full_transcript,
               ai_summary, processing_date, status, filename, 
               confidence_score, tags, published_at,
               COALESCE(favorited, 0) as favorited
        FROM videos 
        WHERE status = 'completed'
        ORDER BY processing_date DESC
        LIMIT ?
    ''', (limit,))
    
    rows = cursor.fetchall()
    
    videos = []
    for row in rows:
        videos.append({
            'id': row['id'],
            'title': row['title'] or 'Untitled Video',
            'channel': row['channel'] or 'Unknown Channel',
            'video_url': row['video_url'],
            'has_transcript': bool(row['full_transcript']),
            'transcript_length': len(row['full_transcript']) if row['full_transcript'] else 0,
            'summary': row['ai_summary'],
            'processing_date': row['processing_date'],
            'published_at': row['published_at'],
            'status': row['status'],
            'tags': row['tags'] or '',
            'favorited': bool(row['favorited']),
            'confidence_score': row['confidence_score'] or 0
        })
    
    conn.close()
    return videos

def search_by_topic(topic: str, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Search videos by topic keyword.
    
    Args:
        topic: Topic keyword to search for
        limit: Maximum number of results
    
    Returns:
        List of video dictionaries
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    topic_term = f"%{topic}%"
    
    cursor.execute('''
        SELECT id, title, channel, video_url, full_transcript,
               ai_summary, processing_date, status, filename, 
               confidence_score, tags, published_at, topics,
               COALESCE(favorited, 0) as favorited
        FROM videos 
        WHERE status = 'completed'
        AND topics LIKE ?
        ORDER BY processing_date DESC
        LIMIT ?
    ''', (topic_term, limit))
    
    rows = cursor.fetchall()
    
    videos = []
    for row in rows:
        videos.append({
            'id': row['id'],
            'title': row['title'] or 'Untitled Video',
            'channel': row['channel'] or 'Unknown Channel',
            'video_url': row['video_url'],
            'has_transcript': bool(row['full_transcript']),
            'transcript_length': len(row['full_transcript']) if row['full_transcript'] else 0,
            'summary': row['ai_summary'],
            'topics': row['topics'],
            'processing_date': row['processing_date'],
            'published_at': row['published_at'],
            'status': row['status'],
            'tags': row['tags'] or '',
            'favorited': bool(row['favorited']),
            'confidence_score': row['confidence_score'] or 0
        })
    
    conn.close()
    return videos

def get_statistics() -> Dict[str, Any]:
    """
    Get database statistics.
    
    Returns:
        Dictionary with various statistics
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    stats = {}
    
    # Total videos
    cursor.execute('SELECT COUNT(*) FROM videos WHERE status = "completed"')
    stats['total_videos'] = cursor.fetchone()[0]
    
    # Videos with transcripts
    cursor.execute('SELECT COUNT(*) FROM videos WHERE status = "completed" AND full_transcript IS NOT NULL AND full_transcript != ""')
    stats['videos_with_transcripts'] = cursor.fetchone()[0]
    
    # Total channels
    cursor.execute('SELECT COUNT(*) FROM channel_subscriptions WHERE enabled = 1')
    stats['total_channels'] = cursor.fetchone()[0]
    
    # Total articles
    try:
        cursor.execute('SELECT COUNT(*) FROM articles')
        stats['total_articles'] = cursor.fetchone()[0]
    except sqlite3.OperationalError:
        stats['total_articles'] = 0
    
    # Videos by channel (top 10)
    cursor.execute('''
        SELECT channel, COUNT(*) as count
        FROM videos
        WHERE status = "completed"
        GROUP BY channel
        ORDER BY count DESC
        LIMIT 10
    ''')
    stats['top_channels'] = [{'channel': row[0], 'count': row[1]} for row in cursor.fetchall()]
    
    conn.close()
    return stats

def save_intelligence(
    intelligence_type: str,
    title: str,
    content: str,
    source_video_ids: Optional[List[int]] = None,
    tags: Optional[str] = None
) -> Dict[str, Any]:
    """
    Save a new intelligence entry (synthesis, prediction, script, or query).
    
    Args:
        intelligence_type: Type of intelligence ('synthesis', 'prediction', 'script', or 'query')
        title: Title of the intelligence entry
        content: Full content/markdown of the intelligence entry
        source_video_ids: Optional list of video IDs this intelligence is based on
        tags: Optional comma-separated tags
    
    Returns:
        Dictionary with success status and created entry or error message
    """
    # Validation
    valid_types = ['synthesis', 'prediction', 'script', 'query', 'trends', 'pattern', 'workflows', 'strategy']
    if intelligence_type not in valid_types:
        return {"success": False, "error": f"Type must be one of: {', '.join(valid_types)}"}
    
    if not title or len(title.strip()) == 0:
        return {"success": False, "error": "Title is required"}
    
    if not content or len(content.strip()) == 0:
        return {"success": False, "error": "Content is required"}
    
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # Convert source_video_ids list to comma-separated string
        source_video_ids_str = None
        if source_video_ids:
            source_video_ids_str = ','.join(str(vid) for vid in source_video_ids)
        
        cursor.execute('''
            INSERT INTO intelligence (
                type, title, content, source_video_ids, tags
            )
            VALUES (?, ?, ?, ?, ?)
        ''', (
            intelligence_type,
            title.strip(),
            content.strip(),
            source_video_ids_str,
            tags.strip() if tags else None
        ))
        
        intelligence_id = cursor.lastrowid
        conn.commit()
        
        # Fetch the created entry
        cursor.execute('''
            SELECT id, type, title, content, source_video_ids, tags, created_at, updated_at
            FROM intelligence
            WHERE id = ?
        ''', (intelligence_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return {"success": False, "error": "Failed to retrieve created entry"}
        
        # Parse source_video_ids back to list
        source_video_ids_list = []
        if row['source_video_ids']:
            try:
                source_video_ids_list = [int(vid.strip()) for vid in row['source_video_ids'].split(',') if vid.strip()]
            except (ValueError, AttributeError):
                source_video_ids_list = []
        
        result = {
            "success": True,
            "intelligence": {
                "id": row['id'],
                "type": row['type'],
                "title": row['title'],
                "content": row['content'],
                "source_video_ids": source_video_ids_list,
                "tags": row['tags'] or '',
                "created_at": row['created_at'],
                "updated_at": row['updated_at']
            }
        }
        
        return result
        
    except Exception as e:
        conn.close()
        return {"success": False, "error": str(e)}

# MCP Server Handlers

@app.list_tools()
async def list_tools() -> list[Tool]:
    """List all available MCP tools."""
    return [
        Tool(
            name="search_videos",
            description="Search videos by text query across title, channel, transcript, and summary. Optionally filter by channel.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query text"
                    },
                    "channel_id": {
                        "type": "string",
                        "description": "Optional channel ID to filter results"
                    },
                    "channel_name": {
                        "type": "string",
                        "description": "Optional channel name to filter results"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (default: 20)",
                        "default": 20
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="get_video_by_id",
            description="Get complete details for a specific video by ID, including full transcript and summary.",
            inputSchema={
                "type": "object",
                "properties": {
                    "video_id": {
                        "type": "integer",
                        "description": "Video ID"
                    }
                },
                "required": ["video_id"]
            }
        ),
        Tool(
            name="get_videos_by_channel",
            description="Get all videos from a specific channel. Provide either channel_id or channel_name.",
            inputSchema={
                "type": "object",
                "properties": {
                    "channel_id": {
                        "type": "string",
                        "description": "Channel ID to filter by"
                    },
                    "channel_name": {
                        "type": "string",
                        "description": "Channel name to filter by"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (default: 50)",
                        "default": 50
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="get_recent_videos",
            description="Get the most recently processed videos, ordered by processing date.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (default: 20)",
                        "default": 20
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="search_by_topic",
            description="Search videos by topic keyword. Searches the topics column for matches.",
            inputSchema={
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "Topic keyword to search for"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (default: 20)",
                        "default": 20
                    }
                },
                "required": ["topic"]
            }
        ),
        Tool(
            name="save_intelligence",
            description="Save intelligence to the knowledge database. Types: synthesis (cross-video analysis), prediction (forecasts), script (generated scripts), query (research queries), trends, pattern, workflows, strategy (distribution/competitive/market research).",
            inputSchema={
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "description": "Type of intelligence: 'synthesis', 'prediction', 'script', 'query', 'trends', 'pattern', 'workflows', or 'strategy' (distribution/competitive/market research)",
                        "enum": ["synthesis", "prediction", "script", "query", "trends", "pattern", "workflows", "strategy"]
                    },
                    "title": {
                        "type": "string",
                        "description": "Title of the intelligence entry"
                    },
                    "content": {
                        "type": "string",
                        "description": "Full content/markdown of the intelligence entry"
                    },
                    "source_video_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Optional list of video IDs this intelligence is based on"
                    },
                    "tags": {
                        "type": "string",
                        "description": "Optional comma-separated tags for categorization"
                    }
                },
                "required": ["type", "title", "content"]
            }
        )
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls from Claude."""
    try:
        if name == "search_videos":
            query = arguments.get("query", "")
            channel_id = arguments.get("channel_id")
            channel_name = arguments.get("channel_name")
            limit = arguments.get("limit", 20)
            
            results = search_videos(query, channel_id, channel_name, limit)
            return [TextContent(
                type="text",
                text=json.dumps(results, indent=2, default=str)
            )]
        
        elif name == "get_video_by_id":
            video_id = arguments.get("video_id")
            if video_id is None:
                return [TextContent(
                    type="text",
                    text=json.dumps({"error": "video_id is required"})
                )]
            
            result = get_video_by_id(video_id)
            if result is None:
                return [TextContent(
                    type="text",
                    text=json.dumps({"error": f"Video with ID {video_id} not found"})
                )]
            
            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2, default=str)
            )]
        
        elif name == "get_videos_by_channel":
            channel_id = arguments.get("channel_id")
            channel_name = arguments.get("channel_name")
            limit = arguments.get("limit", 50)
            
            if not channel_id and not channel_name:
                return [TextContent(
                    type="text",
                    text=json.dumps({"error": "Either channel_id or channel_name is required"})
                )]
            
            results = get_videos_by_channel(channel_id, channel_name, limit)
            return [TextContent(
                type="text",
                text=json.dumps(results, indent=2, default=str)
            )]
        
        elif name == "get_recent_videos":
            limit = arguments.get("limit", 20)
            results = get_recent_videos(limit)
            return [TextContent(
                type="text",
                text=json.dumps(results, indent=2, default=str)
            )]
        
        elif name == "search_by_topic":
            topic = arguments.get("topic")
            if not topic:
                return [TextContent(
                    type="text",
                    text=json.dumps({"error": "topic is required"})
                )]
            
            limit = arguments.get("limit", 20)
            results = search_by_topic(topic, limit)
            return [TextContent(
                type="text",
                text=json.dumps(results, indent=2, default=str)
            )]
        
        elif name == "save_intelligence":
            intelligence_type = arguments.get("type")
            title = arguments.get("title")
            content = arguments.get("content")
            source_video_ids = arguments.get("source_video_ids")
            tags = arguments.get("tags")
            
            if not intelligence_type:
                return [TextContent(
                    type="text",
                    text=json.dumps({"success": False, "error": "type is required"})
                )]
            
            if not title:
                return [TextContent(
                    type="text",
                    text=json.dumps({"success": False, "error": "title is required"})
                )]
            
            if not content:
                return [TextContent(
                    type="text",
                    text=json.dumps({"success": False, "error": "content is required"})
                )]
            
            result = save_intelligence(
                intelligence_type=intelligence_type,
                title=title,
                content=content,
                source_video_ids=source_video_ids,
                tags=tags
            )
            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2, default=str)
            )]
        
        else:
            return [TextContent(
                type="text",
                text=json.dumps({"error": f"Unknown tool: {name}"})
            )]
    
    except Exception as e:
        return [TextContent(
            type="text",
            text=json.dumps({"error": str(e)})
        )]

async def main():
    """Run the MCP server using stdio transport."""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )

if __name__ == "__main__":
    asyncio.run(main())

