#!/usr/bin/env python3
"""
Flask Backend Server for YouTube Intelligence System
"""

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import sqlite3
import json
import os
import anthropic
from dotenv import load_dotenv
import shutil
from datetime import datetime, timedelta
import threading
import time
import re

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)

# Configuration
DATABASE_PATH = "youtube_intelligence.db"
CLAUDE_API_KEY = os.getenv("ANTHROPIC_API_KEY")

claude_client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

def generate_shortened_summary(full_summary: str, target_percentage: int) -> str:
    """
    Generate a shortened version of a summary using Claude Haiku 4.5.
    
    Args:
        full_summary: The full summary text to shorten
        target_percentage: Target length as percentage (15, 30, or 50)
    
    Returns:
        The shortened summary text
    """
    if not full_summary or len(full_summary.strip()) < 100:
        return full_summary  # Return as-is if too short to shorten meaningfully
    
    if target_percentage == 15:
        target_length = "85% shorter (15% of original length)"
    elif target_percentage == 30:
        target_length = "70% shorter (30% of original length)"
    elif target_percentage == 50:
        target_length = "50% shorter"
    else:
        target_length = f"{100 - target_percentage}% shorter ({target_percentage}% of original length)"
    
    prompt = f"""Condense this summary to approximately {target_length}.

Preserve in priority order:
- Specific metaphors, frameworks, and distinctive framings (these ARE the insight — don't genericize them)
- Concrete prescriptions with their details (activities, tools, numbers, names)
- The sharpest quotes that carry real meaning
- What makes each point different from generic advice

Cut in priority order:
- Transition phrases and connective prose
- Redundant explanations of the same point
- Background context the reader can infer
- Generic framing ("the author argues that...")

Keep it dense with meaning. Every sentence should carry specific information. Never replace a concrete insight with a generic label.

Original Summary:
{full_summary}"""

    try:
        model = "claude-haiku-4-5-20251001"
        response = claude_client.messages.create(
            model=model,
            max_tokens=4000,  # Enough for shortened summaries
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text
    except Exception as e:
        print(f"⚠️ Error generating shortened summary ({target_percentage}%): {e}")
        return full_summary  # Return original on error

def load_llm_brief_prompt(content_type, title, transcript, brief_summary):
    """Load category-specific LLM Brief prompt with fallback to general"""
    prompt_file = f"prompts/current_best/{content_type}_llm_brief.txt"
    
    # Try to load category-specific prompt
    if os.path.exists(prompt_file):
        try:
            with open(prompt_file, 'r', encoding='utf-8') as f:
                prompt_template = f.read()
            print(f"✅ Using specialized LLM Brief prompt: {content_type}_llm_brief.txt")
        except Exception as e:
            print(f"⚠️ Error loading {prompt_file}: {e}")
            prompt_template = None
    else:
        print(f"⚠️ LLM Brief prompt not found: {prompt_file}")
        prompt_template = None
    
    # Fallback to explainer LLM Brief prompt
    if not prompt_template:
        explainer_file = "prompts/current_best/explainer_llm_brief.txt"
        try:
            with open(explainer_file, 'r', encoding='utf-8') as f:
                prompt_template = f.read()
            print(f"✅ Using fallback LLM Brief prompt: explainer_llm_brief.txt")
        except Exception as e:
            print(f"❌ Error loading fallback prompt: {e}")
            # Ultimate fallback - embedded prompt
            prompt_template = """Create a comprehensive intelligence brief with this structure:

**EXECUTIVE CONTEXT (30-50 words):**
What is this? Why does it matter? What shift/trend does it represent?

**WHAT THEY DELIVERED (organized synthesis):**
Extract and organize everything they actually covered, but structure it better than they did:
- If listicle (50 use cases) → All items, categorized logically
- If predictions → Specific claims with timelines and evidence
- If tutorial → Complete process with exact steps
- If analysis → Key findings with supporting data

**INTELLIGENCE AMPLIFICATION:**
- **Competitive Context** (when relevant): Alternatives, pricing, positioning
- **What They Missed**: Additional applications/angles from domain knowledge
- **Market Implications**: What this represents in broader context
- **Forward Intelligence**: Specific developments expected in 3/6/12 months

**DECISION FRAMEWORK** (when evaluating tools/strategies):
When to use this vs alternatives for the user's projects

QUALITY BAR: User should prefer this brief to watching the video. More comprehensive, better organized, strategically useful.

Be aggressive about extraction. Be intelligent about synthesis. Be specific about everything.

**Video Title:** {title}
**Transcript:** {transcript}"""
    
    # Format the prompt with actual values
    return prompt_template.format(
        title=title,
        transcript=transcript[:120000],  # Limit to 120k chars for API
        brief_summary=brief_summary,
        content_type=content_type
    )

class DatabaseService:
    def __init__(self, db_path):
        self.db_path = db_path
        self.init_chat_tables()
        self.init_notes_table()
        self.init_highlights_table()
        self.init_intelligence_table()
        self.init_newsletter_tables()
        self.init_sparks_table()
        self.init_yt_podcast_tables()
        self.init_briefs_table()

    def get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        # Enable WAL mode for concurrent access (MCP can read while app writes)
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA busy_timeout=10000')
        return conn
    
    def init_chat_tables(self):
        """Initialize chat session and message tables"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Chat sessions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL UNIQUE,
                channel_id TEXT,
                channel_name TEXT,
                mode TEXT DEFAULT 'grounded',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Chat messages table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                message TEXT NOT NULL,
                retrieved_content_ids TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(session_id) REFERENCES chat_sessions(session_id)
            )
        ''')
        
        # Indexes
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_chat_messages_session 
            ON chat_messages(session_id, created_at)
        ''')
        
        conn.commit()
        conn.close()

    def init_notes_table(self):
        """Ensure lightweight knowledge notes table exists"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                note TEXT NOT NULL,
                video_id TEXT,
                video_title TEXT,
                summary_id TEXT,
                summary_url TEXT,
                source_url TEXT,
                channel TEXT,
                content_type TEXT,
                captured_at TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_notes_created_at ON notes(created_at DESC)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_notes_video_id ON notes(video_id)')
        conn.commit()
        conn.close()
    
    def init_highlights_table(self):
        """Ensure highlights table exists"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS highlights (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                video_id INTEGER,
                article_id INTEGER,
                content_type TEXT,
                highlighted_text TEXT NOT NULL,
                user_note TEXT,
                tags TEXT,
                context TEXT,
                source_title TEXT,
                source_url TEXT,
                channel TEXT,
                favorited INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_highlights_created_at ON highlights(created_at DESC)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_highlights_video_id ON highlights(video_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_highlights_article_id ON highlights(article_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_highlights_tags ON highlights(tags)')

        # Add favorited column if it doesn't exist (migration for existing tables)
        cursor.execute("PRAGMA table_info(highlights)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'favorited' not in columns:
            cursor.execute('ALTER TABLE highlights ADD COLUMN favorited INTEGER DEFAULT 0')

        # Create index on favorited after ensuring column exists
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_highlights_favorited ON highlights(favorited)')

        conn.commit()
        conn.close()
    
    def init_intelligence_table(self):
        """Initialize intelligence table for Claude-generated syntheses, predictions, scripts, queries, and trends"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Check if table exists and if it has the old constraint
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='intelligence'")
        table_exists = cursor.fetchone()
        
        if table_exists:
            # Check if we need to migrate (old constraint doesn't include 'trends')
            cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='intelligence'")
            table_sql = cursor.fetchone()
            table_sql_text = table_sql[0] if table_sql else ""
            
            # Check if constraint needs updating (doesn't include 'trends')
            needs_migration = False
            if "CHECK(type IN" in table_sql_text and "'trends'" not in table_sql_text:
                needs_migration = True
                print(f"🔄 Found constraint without 'trends': {table_sql_text[:200]}...")
                print(f"   Current constraint includes: {table_sql_text}")
            
            if needs_migration:
                # Need to migrate - recreate table with new constraint
                print("🔄 Migrating intelligence table to include 'trends' type...")
                # Create backup table
                cursor.execute('''
                    CREATE TABLE intelligence_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        type TEXT NOT NULL CHECK(type IN ('synthesis', 'prediction', 'script', 'query', 'trends')),
                        title TEXT NOT NULL,
                        content TEXT NOT NULL,
                        source_video_ids TEXT,
                        tags TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                # Copy data
                cursor.execute('INSERT INTO intelligence_new SELECT * FROM intelligence')
                # Drop old table
                cursor.execute('DROP TABLE intelligence')
                # Rename new table
                cursor.execute('ALTER TABLE intelligence_new RENAME TO intelligence')
                # Recreate indexes
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_intelligence_type ON intelligence(type)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_intelligence_created_at ON intelligence(created_at DESC)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_intelligence_tags ON intelligence(tags)')
                conn.commit()
                print("✅ Intelligence table migrated successfully")
            else:
                # Table exists with correct constraint or no constraint - just ensure indexes
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_intelligence_type ON intelligence(type)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_intelligence_created_at ON intelligence(created_at DESC)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_intelligence_tags ON intelligence(tags)')
                conn.commit()
        else:
            # Create new table with correct constraint
            cursor.execute('''
                CREATE TABLE intelligence (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT NOT NULL CHECK(type IN ('synthesis', 'prediction', 'script', 'query', 'trends')),
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source_video_ids TEXT,
                    tags TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_intelligence_type ON intelligence(type)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_intelligence_created_at ON intelligence(created_at DESC)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_intelligence_tags ON intelligence(tags)')
            conn.commit()
        
        conn.close()

    def init_sparks_table(self):
        """Initialize sparks/ideas table"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sparks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                status TEXT DEFAULT 'active' CHECK(status IN ('active', 'archived', 'acted_on')),
                tags TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_sparks_status ON sparks(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_sparks_created ON sparks(created_at DESC)')
        conn.commit()
        conn.close()

    def init_yt_podcast_tables(self):
        """Initialize tables for YouTube-to-Podcast feed feature"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS yt_podcast_episodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                channel TEXT,
                description TEXT,
                video_url TEXT,
                audio_filename TEXT,
                audio_size INTEGER,
                duration_seconds INTEGER,
                thumbnail_url TEXT,
                published_at TEXT,
                status TEXT DEFAULT 'pending',
                error_message TEXT,
                source TEXT DEFAULT 'pick',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (video_id) REFERENCES videos(id)
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_yt_podcast_episodes_video ON yt_podcast_episodes(video_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_yt_podcast_episodes_status ON yt_podcast_episodes(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_yt_podcast_episodes_source ON yt_podcast_episodes(source)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_yt_podcast_episodes_channel ON yt_podcast_episodes(channel)')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS yt_podcast_channel_feeds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_name TEXT NOT NULL UNIQUE,
                enabled INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.commit()
        conn.close()

    def init_newsletter_tables(self):
        """Initialize newsletter subscriptions and issues tables"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Newsletter subscriptions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS newsletter_subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                newsletter_name TEXT NOT NULL,
                feed_url TEXT,
                website_url TEXT,
                platform TEXT,
                description TEXT,
                image_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_checked TIMESTAMP,
                enabled INTEGER DEFAULT 1
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_newsletter_subs_enabled ON newsletter_subscriptions(enabled)')

        # Add ktn_email column for Kill the Newsletter integration
        try:
            cursor.execute('ALTER TABLE newsletter_subscriptions ADD COLUMN ktn_email TEXT')
        except sqlite3.OperationalError:
            pass  # Column already exists

        # Newsletter issues table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS newsletter_issues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subscription_id INTEGER NOT NULL,
                issue_guid TEXT NOT NULL UNIQUE,
                title TEXT,
                description TEXT,
                content TEXT,
                issue_url TEXT,
                published_at TIMESTAMP,
                processed INTEGER DEFAULT 0,
                processed_article_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(subscription_id) REFERENCES newsletter_subscriptions(id)
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_newsletter_issues_sub ON newsletter_issues(subscription_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_newsletter_issues_processed ON newsletter_issues(processed)')

        conn.commit()
        conn.close()

    def init_briefs_table(self):
        """Initialize daily briefs table for Briefing Room"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_briefs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vertical TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                signal_count INTEGER DEFAULT 0,
                source_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_briefs_vertical ON daily_briefs(vertical)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_briefs_created ON daily_briefs(created_at DESC)')
        conn.commit()
        conn.close()

    # Newsletter CRUD methods
    def list_newsletter_subscriptions(self):
        """List all newsletter subscriptions with issue counts"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT ns.*, COUNT(ni.id) as issue_count
            FROM newsletter_subscriptions ns
            LEFT JOIN newsletter_issues ni ON ns.id = ni.subscription_id
            GROUP BY ns.id
            ORDER BY ns.created_at DESC
        ''')
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def add_newsletter_subscription(self, newsletter_name, feed_url=None, platform=None, website_url=None, description=None, ktn_email=None):
        """Add a new newsletter subscription"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO newsletter_subscriptions (newsletter_name, feed_url, platform, website_url, description, ktn_email)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (newsletter_name, feed_url, platform, website_url, description, ktn_email))
        sub_id = cursor.lastrowid
        conn.commit()
        cursor.execute('SELECT * FROM newsletter_subscriptions WHERE id = ?', (sub_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def get_newsletter_subscription(self, subscription_id):
        """Get a single newsletter subscription"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM newsletter_subscriptions WHERE id = ?', (subscription_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def delete_newsletter_subscription(self, subscription_id):
        """Delete a newsletter subscription and its issues"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM newsletter_issues WHERE subscription_id = ?', (subscription_id,))
        cursor.execute('DELETE FROM newsletter_subscriptions WHERE id = ?', (subscription_id,))
        deleted = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return deleted

    def toggle_newsletter_subscription(self, subscription_id):
        """Toggle enabled status of a newsletter subscription"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT enabled FROM newsletter_subscriptions WHERE id = ?', (subscription_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return None
        new_status = 0 if row['enabled'] else 1
        cursor.execute('UPDATE newsletter_subscriptions SET enabled = ? WHERE id = ?', (new_status, subscription_id))
        conn.commit()
        cursor.execute('SELECT * FROM newsletter_subscriptions WHERE id = ?', (subscription_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def update_newsletter_last_checked(self, subscription_id):
        """Update last_checked timestamp"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE newsletter_subscriptions SET last_checked = CURRENT_TIMESTAMP WHERE id = ?', (subscription_id,))
        conn.commit()
        conn.close()

    def add_newsletter_issue(self, subscription_id, issue_guid, title, description=None, content=None, issue_url=None, published_at=None):
        """Add a newsletter issue"""
        # Normalize date to ISO format for proper sorting
        if published_at and not published_at.startswith('20'):
            try:
                from email.utils import parsedate_to_datetime
                published_at = parsedate_to_datetime(published_at).strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                pass
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO newsletter_issues (subscription_id, issue_guid, title, description, content, issue_url, published_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (subscription_id, issue_guid, title, description, content, issue_url, published_at))
            conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            # Issue already exists
            return None
        finally:
            conn.close()

    def get_newsletter_issues(self, subscription_id):
        """Get all issues for a newsletter subscription"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM newsletter_issues
            WHERE subscription_id = ?
            ORDER BY published_at DESC
        ''', (subscription_id,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def get_all_videos(self):
        conn = self.get_connection()
        cursor = conn.cursor()

        self._ensure_video_columns(cursor, conn)

        cursor.execute('''
            SELECT id, title, channel, video_url, full_transcript,
                   ai_summary, summary_50, summary_30, summary_15, processing_date, status, filename, confidence_score, tags, prompt_used,
                   published_at, COALESCE(favorited, 0) as favorited, original_publish_date, view_count, last_duplicate_attempt
            FROM videos
            WHERE status IN ('completed', 'error', 'failed', 'no_transcript', 'no_video_found')
            ORDER BY processing_date DESC
        ''')
        
        videos = []
        for row in cursor.fetchall():
            video = self._serialize_video_row(row)
            if video:
                videos.append(video)
        
        conn.close()
        return videos
    
    def search_videos(self, query, channel_id=None, channel_name=None):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        self._ensure_video_columns(cursor, conn)
        
        # Simple LIKE search - more permissive
        search_term = f"%{query}%"
        
        # Normalize empty strings to None
        if channel_id == '':
            channel_id = None
        if channel_name == '':
            channel_name = None
        
        print(f"🔍 Searching for: '{query}' (channel_id={channel_id}, channel_name={channel_name})")
        
        # Build query with optional channel filter
        if channel_id or channel_name:
            # If channel_id provided, try to match via channel_videos table first
            if channel_id:
                # First try: Match via channel_videos table (for videos processed through queue)
                query_sql = '''
            SELECT DISTINCT v.id, v.title, v.channel, v.video_url, v.full_transcript,
                   v.ai_summary, v.processing_date, v.status, v.filename, v.confidence_score, v.tags, v.prompt_used,
                   v.published_at, COALESCE(v.favorited, 0) as favorited, v.original_publish_date
                    FROM videos v
                    INNER JOIN channel_videos cv ON v.id = cv.processed_video_id
                    WHERE v.status = 'completed' 
                    AND cv.channel_id = ?
                    AND (v.title LIKE ? OR v.channel LIKE ? OR v.full_transcript LIKE ? OR v.ai_summary LIKE ?)
                    ORDER BY v.processing_date DESC
                    LIMIT 20
                '''
                params = (channel_id, search_term, search_term, search_term, search_term)
                cursor.execute(query_sql, params)
                rows = cursor.fetchall()
                print(f"🔍 Channel ID search (via channel_videos) returned {len(rows)} rows")
                
                # If no results, fallback to channel name match (for videos processed before subscriptions)
                if len(rows) == 0:
                    print(f"⚠️  No videos found via channel_videos join, trying channel name fallback...")
                    # Get channel name from subscriptions table
                    cursor.execute('SELECT channel_name FROM channel_subscriptions WHERE channel_id = ?', (channel_id,))
                    sub_row = cursor.fetchone()
                    if sub_row and sub_row[0]:
                        channel_name_fallback = sub_row[0]
                        query_sql = '''
                    SELECT id, title, channel, video_url, full_transcript,
                           ai_summary, processing_date, status, filename, confidence_score, tags, prompt_used,
                           published_at, COALESCE(favorited, 0) as favorited, original_publish_date
                            FROM videos 
                            WHERE status = 'completed' 
                            AND channel = ?
                            AND (title LIKE ? OR channel LIKE ? OR full_transcript LIKE ? OR ai_summary LIKE ?)
                            ORDER BY processing_date DESC
                            LIMIT 20
                        '''
                        params = (channel_name_fallback, search_term, search_term, search_term, search_term)
                        cursor.execute(query_sql, params)
                        rows = cursor.fetchall()
                        print(f"🔍 Channel name fallback returned {len(rows)} rows")
                else:
                    # Use the rows from channel_videos join
                    pass
            else:
                # Match by channel name
                query_sql = '''
                    SELECT id, title, channel, video_url, full_transcript,
                           ai_summary, processing_date, status, filename, confidence_score, tags, prompt_used,
                           published_at, COALESCE(favorited, 0) as favorited, original_publish_date
                    FROM videos 
                    WHERE status = 'completed' 
                    AND channel = ?
                    AND (title LIKE ? OR channel LIKE ? OR full_transcript LIKE ? OR ai_summary LIKE ?)
                    ORDER BY processing_date DESC
                    LIMIT 20
                '''
                params = (channel_name, search_term, search_term, search_term, search_term)
                cursor.execute(query_sql, params)
                rows = cursor.fetchall()
                print(f"🔍 Channel name search returned {len(rows)} rows")
        else:
            # No channel filter - search all content
            query_sql = '''
                    SELECT id, title, channel, video_url, full_transcript,
                           ai_summary, processing_date, status, filename, confidence_score, tags, prompt_used,
                           published_at, COALESCE(favorited, 0) as favorited, original_publish_date
                SELECT id, title, channel, video_url, full_transcript,
                       ai_summary, processing_date, status, filename, confidence_score, tags, prompt_used,
                       published_at, COALESCE(favorited, 0) as favorited, original_publish_date
                FROM videos 
                WHERE status = 'completed' 
                AND (title LIKE ? OR channel LIKE ? OR full_transcript LIKE ? OR ai_summary LIKE ?)
                ORDER BY processing_date DESC
                LIMIT 20
            '''
            params = (search_term, search_term, search_term, search_term)
            cursor.execute(query_sql, params)
            rows = cursor.fetchall()
            print(f"🔍 SQL query returned {len(rows)} rows")
        
        # Ensure rows exists
        if 'rows' not in locals():
            rows = []
        
        videos = []
        for row in rows:
            video = self._serialize_video_row(row)
            if video:
                videos.append(video)
        
        conn.close()
        return videos
    
    def create_chat_session(self, channel_id=None, channel_name=None, mode='grounded'):
        """Create a new chat session"""
        import uuid
        session_id = str(uuid.uuid4())
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO chat_sessions (session_id, channel_id, channel_name, mode)
            VALUES (?, ?, ?, ?)
        ''', (session_id, channel_id, channel_name, mode))
        conn.commit()
        conn.close()
        return session_id
    
    def get_chat_session(self, session_id):
        """Get chat session by ID"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT session_id, channel_id, channel_name, mode, created_at, last_activity
            FROM chat_sessions
            WHERE session_id = ?
        ''', (session_id,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        return {
            'session_id': row[0],
            'channel_id': row[1],
            'channel_name': row[2],
            'mode': row[3],
            'created_at': row[4],
            'last_activity': row[5]
        }
    
    def add_chat_message(self, session_id, role, message, retrieved_content_ids=None):
        """Add a message to a chat session"""
        conn = self.get_connection()
        cursor = conn.cursor()
        content_ids_json = json.dumps(retrieved_content_ids) if retrieved_content_ids else None
        cursor.execute('''
            INSERT INTO chat_messages (session_id, role, message, retrieved_content_ids)
            VALUES (?, ?, ?, ?)
        ''', (session_id, role, message, content_ids_json))
        # Update session last_activity
        cursor.execute('''
            UPDATE chat_sessions
            SET last_activity = CURRENT_TIMESTAMP
            WHERE session_id = ?
        ''', (session_id,))
        conn.commit()
        conn.close()
    
    def get_chat_history(self, session_id, limit=10):
        """Get conversation history for a session"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT role, message, created_at
            FROM chat_messages
            WHERE session_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        ''', (session_id, limit))
        messages = []
        for row in cursor.fetchall():
            messages.append({
                'role': row[0],
                'message': row[1],
                'created_at': row[2]
            })
        conn.close()
        # Return in chronological order (oldest first)
        return list(reversed(messages))

    def _serialize_video_row(self, row):
        if not row:
            return None
        keys = row.keys()
        ai_summary = row['ai_summary'] if 'ai_summary' in keys else None
        summary_50 = row['summary_50'] if 'summary_50' in keys else None
        summary_30 = row['summary_30'] if 'summary_30' in keys else None
        summary_15 = row['summary_15'] if 'summary_15' in keys else None
        processed_at = row['processing_date'] if 'processing_date' in keys else None
        published_source = row['published_at'] if 'published_at' in keys else None
        original_published = row['original_publish_date'] if 'original_publish_date' in keys else None
        published_at = original_published or published_source
        favorited_value = row['favorited'] if 'favorited' in keys else 0

        video = {
            'id': row['id'],
            'title': row['title'] or 'Untitled Video',
            'channel': row['channel'] or 'Unknown Channel',
            'video_url': row['video_url'],
            'full_transcript': row['full_transcript'],
            'hasTranscript': bool(row['full_transcript']),
            'transcriptLength': len(row['full_transcript']) if row['full_transcript'] else 0,
            'summary': str(ai_summary) if ai_summary else "No summary",
            'ai_summary': ai_summary,
            'summary_50': summary_50,
            'summary_30': summary_30,
            'summary_15': summary_15,
            'summary_data': {'ai_summary': str(ai_summary) if ai_summary else ''},
            'date': processed_at or row['processing_date'] or published_at or 'Unknown date',
            'sort_date': processed_at or row['processing_date'] or published_at or '',  # Raw timestamp for sorting
            'processed_at': processed_at or row['processing_date'],
            'published_at': published_at,
            'published_at_source': published_source,
            'original_published_at': original_published,
            'status': row['status'],
            'filename': row['filename'],
            'confidence_score': row['confidence_score'] or 0,
            'tags': row['tags'] or '',
            'prompt_used': row['prompt_used'] or 'general',
            'favorited': bool(favorited_value),
            'duration': 'Unknown duration',
            'content_type': 'video',
            'view_count': row['view_count'] if 'view_count' in keys else None,
            'last_duplicate_attempt': row['last_duplicate_attempt'] if 'last_duplicate_attempt' in keys else None
        }
        return video

    def _serialize_note_row(self, row):
        if not row:
            return None
        return {
            'id': row[0],
            'user_id': row[1],
            'note': row[2],
            'video_id': row[3],
            'video_title': row[4],
            'summary_id': row[5],
            'summary_url': row[6],
            'source_url': row[7],
            'channel': row[8],
            'content_type': row[9],
            'captured_at': row[10],
            'created_at': row[11]
        }

    def save_note(self, payload):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO notes (
                user_id, note, video_id, video_title, summary_id,
                summary_url, source_url, channel, content_type, captured_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            payload.get('user_id'),
            payload.get('note'),
            payload.get('video_id'),
            payload.get('video_title'),
            payload.get('summary_id'),
            payload.get('summary_url'),
            payload.get('source_url'),
            payload.get('channel'),
            payload.get('content_type'),
            payload.get('captured_at')
        ))
        note_id = cursor.lastrowid
        conn.commit()
        cursor.execute('''
            SELECT id, user_id, note, video_id, video_title, summary_id, summary_url,
                   source_url, channel, content_type, captured_at, created_at
            FROM notes
            WHERE id = ?
        ''', (note_id,))
        row = cursor.fetchone()
        conn.close()
        return self._serialize_note_row(row)

    def get_notes(self, limit=50, offset=0):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, user_id, note, video_id, video_title, summary_id, summary_url,
                   source_url, channel, content_type, captured_at, created_at
            FROM notes
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        ''', (limit, offset))
        rows = cursor.fetchall()
        conn.close()
        return [self._serialize_note_row(row) for row in rows]
    
    def delete_note(self, note_id):
        """Delete a note"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM notes WHERE id = ?', (note_id,))
        conn.commit()
        deleted = cursor.rowcount > 0
        conn.close()
        return deleted
    
    def save_highlight(self, payload):
        """Save a new highlight"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO highlights (
                user_id, video_id, article_id, content_type, highlighted_text,
                user_note, tags, context, source_title, source_url, channel, bookmark_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            payload.get('user_id'),
            payload.get('video_id'),
            payload.get('article_id'),
            payload.get('content_type'),
            payload.get('highlighted_text'),
            payload.get('user_note'),
            payload.get('tags'),
            payload.get('context'),
            payload.get('source_title'),
            payload.get('source_url'),
            payload.get('channel'),
            payload.get('bookmark_id')
        ))
        highlight_id = cursor.lastrowid
        conn.commit()
        cursor.execute('''
            SELECT id, user_id, video_id, article_id, content_type, highlighted_text,
                   user_note, tags, context, source_title, source_url, channel, created_at
            FROM highlights
            WHERE id = ?
        ''', (highlight_id,))
        row = cursor.fetchone()
        conn.close()
        return self._serialize_highlight_row(row)
    
    def get_highlights(self, tag=None, video_id=None, article_id=None, favorited=None, limit=100, offset=0):
        """Get highlights, optionally filtered by tag, video_id, article_id, or favorited status"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Build query based on filters
        base_select = '''
            SELECT id, user_id, video_id, article_id, content_type, highlighted_text,
                   user_note, tags, context, source_title, source_url, channel, favorited, created_at
            FROM highlights
        '''
        conditions = []
        params = []

        if video_id:
            conditions.append('video_id = ?')
            params.append(video_id)
        if article_id:
            conditions.append('article_id = ?')
            params.append(article_id)
        if tag:
            if tag == 'untagged':
                conditions.append("(tags IS NULL OR tags = '' OR tags = 'untagged')")
            else:
                conditions.append('tags LIKE ?')
                params.append(f'%{tag}%')
        if favorited is not None:
            conditions.append('favorited = ?')
            params.append(1 if favorited else 0)

        query = base_select
        if conditions:
            query += ' WHERE ' + ' AND '.join(conditions)
        query += ' ORDER BY created_at DESC LIMIT ? OFFSET ?'
        params.extend([limit, offset])

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        # Filter out None values in case serialization fails for some rows
        highlights = []
        for row in rows:
            try:
                serialized = self._serialize_highlight_row(row)
                if serialized:
                    highlights.append(serialized)
            except Exception as e:
                print(f"Error serializing highlight row (skipping): {e}")
                continue
        return highlights
    
    def update_highlight(self, highlight_id, payload):
        """Update an existing highlight"""
        conn = self.get_connection()
        cursor = conn.cursor()
        updates = []
        values = []
        for key in ['user_note', 'tags', 'favorited']:
            if key in payload:
                updates.append(f"{key} = ?")
                values.append(payload[key])
        if not updates:
            conn.close()
            return None
        values.append(highlight_id)
        cursor.execute(f'''
            UPDATE highlights
            SET {', '.join(updates)}
            WHERE id = ?
        ''', values)
        conn.commit()
        cursor.execute('''
            SELECT id, user_id, video_id, article_id, content_type, highlighted_text,
                   user_note, tags, context, source_title, source_url, channel, favorited, created_at
            FROM highlights
            WHERE id = ?
        ''', (highlight_id,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        return self._serialize_highlight_row(row)

    def toggle_highlight_favorite(self, highlight_id):
        """Toggle the favorited status of a highlight"""
        conn = self.get_connection()
        cursor = conn.cursor()
        # Get current status
        cursor.execute('SELECT favorited FROM highlights WHERE id = ?', (highlight_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return None
        current = row[0] or 0
        new_status = 0 if current else 1
        cursor.execute('UPDATE highlights SET favorited = ? WHERE id = ?', (new_status, highlight_id))
        conn.commit()
        # Return full highlight
        cursor.execute('''
            SELECT id, user_id, video_id, article_id, content_type, highlighted_text,
                   user_note, tags, context, source_title, source_url, channel, favorited, created_at
            FROM highlights
            WHERE id = ?
        ''', (highlight_id,))
        row = cursor.fetchone()
        conn.close()
        return self._serialize_highlight_row(row)

    def get_favorited_highlights_count(self):
        """Get count of favorited highlights"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM highlights WHERE favorited = 1')
        count = cursor.fetchone()[0]
        conn.close()
        return count
    
    def delete_highlight(self, highlight_id):
        """Delete a highlight"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM highlights WHERE id = ?', (highlight_id,))
        conn.commit()
        deleted = cursor.rowcount > 0
        conn.close()
        return deleted
    
    def get_highlight_tags(self):
        """Get all unique tags with counts"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT tags, COUNT(*) as count
            FROM highlights
            WHERE tags IS NOT NULL AND tags != '' AND tags != 'untagged'
            GROUP BY tags
            ORDER BY count DESC
        ''')
        rows = cursor.fetchall()
        conn.close()
        tags_with_counts = []
        for row in rows:
            tag_string = row[0] if row[0] else ''
            count = row[1]
            # Split on comma or space (supports both separators)
            for tag in re.split(r'[,\s]+', tag_string):
                tag = tag.strip()
                if tag:
                    # Check if we already have this tag
                    existing = next((t for t in tags_with_counts if t['tag'] == tag), None)
                    if existing:
                        existing['count'] += count
                    else:
                        tags_with_counts.append({'tag': tag, 'count': count})
        # Sort by count descending
        tags_with_counts.sort(key=lambda x: x['count'], reverse=True)
        return tags_with_counts

    def get_bookmarks(self, limit=100, offset=0):
        """Get bookmarks"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id,
                   user_id,
                   content_id,
                   content_type,
                   COALESCE(content_title, title, 'Untitled') as final_title,
                   COALESCE(source_url, url, '') as final_url,
                   COALESCE(channel, source, '') as final_channel,
                   COALESCE(tags, '') as tags,
                   note,
                   COALESCE(created_at, CURRENT_TIMESTAMP) as created_at
            FROM bookmarks
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        ''', (limit, offset))
        rows = cursor.fetchall()
        conn.close()
        bookmarks = []
        for row in rows:
            try:
                serialized = self._serialize_bookmark_row(row)
                if serialized:
                    bookmarks.append(serialized)
            except Exception as e:
                print(f"Error serializing bookmark row (skipping): {e}")
                continue
        return bookmarks

    def _serialize_bookmark_row(self, row):
        """Serialize a bookmark database row to dict"""
        if not row:
            return None
        try:
            created_at = row['created_at']
            if created_at:
                created_at_str = created_at if isinstance(created_at, str) else str(created_at)
            else:
                created_at_str = None

            return {
                'id': row['id'],
                'user_id': row['user_id'] if row['user_id'] else None,
                'content_id': row['content_id'] if row['content_id'] else None,
                'content_type': row['content_type'] if row['content_type'] else None,
                'content_title': str(row['final_title']).strip() if row['final_title'] else '',
                'source_url': str(row['final_url']).strip() if row['final_url'] else '',
                'channel': str(row['final_channel']).strip() if row['final_channel'] else '',
                'tags': str(row['tags']).strip() if row['tags'] else '',
                'note': str(row['note']).strip() if row['note'] else '',
                'created_at': created_at_str
            }
        except Exception as e:
            print(f"Error serializing bookmark row: {e}")
            return None

    def get_bookmark_count(self):
        """Get total count of bookmarks"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) as count FROM bookmarks')
        result = cursor.fetchone()
        count = result['count'] if hasattr(result, 'keys') else result[0] if result else 0
        conn.close()
        return count

    def get_all_tags(self):
        """Get all tags from videos, articles, and highlights (unified tag system)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        all_tags = set()

        # Get tags from videos (split on comma or space)
        cursor.execute('SELECT tags FROM videos WHERE tags IS NOT NULL AND tags != ""')
        for row in cursor.fetchall():
            if row[0]:
                for tag in re.split(r'[,\s]+', row[0]):
                    tag = tag.strip()
                    if tag:
                        all_tags.add(tag)

        # Get tags from articles (split on comma or space)
        try:
            cursor.execute('SELECT tags FROM articles WHERE tags IS NOT NULL AND tags != ""')
            for row in cursor.fetchall():
                if row[0]:
                    for tag in re.split(r'[,\s]+', row[0]):
                        tag = tag.strip()
                        if tag:
                            all_tags.add(tag)
        except sqlite3.OperationalError:
            pass  # articles table might not have tags column

        # Get tags from highlights (split on comma or space)
        cursor.execute('SELECT tags FROM highlights WHERE tags IS NOT NULL AND tags != ""')
        for row in cursor.fetchall():
            if row[0]:
                for tag in re.split(r'[,\s]+', row[0]):
                    tag = tag.strip()
                    if tag:
                        all_tags.add(tag)

        conn.close()
        return sorted(list(all_tags))
    
    def _serialize_highlight_row(self, row):
        """Serialize a highlight database row to dict"""
        if not row:
            return None
        try:
            # Safely get created_at, handling various formats
            created_at = row['created_at']
            if created_at:
                # If it's already a string, use it; otherwise convert
                if isinstance(created_at, str):
                    created_at_str = created_at
                else:
                    # Try to format datetime objects
                    created_at_str = str(created_at)
            else:
                created_at_str = None
            
            return {
                'id': row['id'],
                'user_id': row['user_id'],
                'video_id': row['video_id'],
                'article_id': row['article_id'],
                'content_type': row['content_type'],
                'highlighted_text': row['highlighted_text'] or '',
                'user_note': row['user_note'] or '',
                'tags': row['tags'] or '',
                'context': row['context'] or '',
                'source_title': row['source_title'] or '',
                'source_url': row['source_url'] or '',
                'channel': row['channel'] or '',
                'favorited': row['favorited'] if 'favorited' in row.keys() else 0,
                'created_at': created_at_str
            }
        except Exception as e:
            # Log error but return a safe dict
            print(f"Error serializing highlight row: {e}")
            print(f"Row keys: {row.keys() if hasattr(row, 'keys') else 'N/A'}")
            return {
                'id': row.get('id', 0) if hasattr(row, 'get') else (row[0] if len(row) > 0 else 0),
                'user_id': None,
                'video_id': None,
                'article_id': None,
                'content_type': None,
                'highlighted_text': '',
                'user_note': '',
                'tags': '',
                'context': '',
                'source_title': '',
                'source_url': '',
                'channel': '',
                'favorited': 0,
                'created_at': None
            }
    
    def get_video_by_id(self, video_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        self._ensure_video_columns(cursor, conn)
        
        cursor.execute('''
            SELECT id, title, channel, video_url, full_transcript,
                   ai_summary, processing_date, status, filename, confidence_score, tags, prompt_used,
                   published_at, original_publish_date, COALESCE(favorited, 0) as favorited,
                   summary_50, summary_30, summary_15
            FROM videos
            WHERE id = ?
        ''', (video_id,))
        
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        return self._serialize_video_row(row)

    def _ensure_video_columns(self, cursor, conn):
        column_defs = [
            ("tags", "TEXT DEFAULT ''"),
            ("favorited", "INTEGER DEFAULT 0"),
            ("published_at", "TEXT"),
            ("original_publish_date", "TEXT"),
            ("summary_50", "TEXT"),
            ("summary_30", "TEXT"),
            ("summary_15", "TEXT"),
            ("view_count", "INTEGER"),
            ("last_duplicate_attempt", "TEXT")
        ]
        for column_name, definition in column_defs:
            try:
                cursor.execute(f"ALTER TABLE videos ADD COLUMN {column_name} {definition}")
                conn.commit()
            except sqlite3.OperationalError:
                pass
    
    def update_video_tags(self, video_id, tags):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('UPDATE videos SET tags = ? WHERE id = ?', (tags, video_id))
        conn.commit()
        conn.close()
        
        return True
    
    # Intelligence CRUD methods
    def save_intelligence(self, payload):
        """Save a new intelligence entry"""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Validate type
            valid_types = ['synthesis', 'prediction', 'script', 'query', 'trends']
            intelligence_type = payload.get('type')
            if intelligence_type not in valid_types:
                return None
            
            # Convert source_video_ids list to comma-separated string if provided
            source_video_ids = payload.get('source_video_ids')
            if isinstance(source_video_ids, list):
                source_video_ids = ','.join(str(vid) for vid in source_video_ids)
            
            cursor.execute('''
                INSERT INTO intelligence (
                    type, title, content, source_video_ids, tags
                )
                VALUES (?, ?, ?, ?, ?)
            ''', (
                intelligence_type,
                payload.get('title'),
                payload.get('content'),
                source_video_ids,
                payload.get('tags')
            ))
            intelligence_id = cursor.lastrowid
            conn.commit()
            
            # Fetch and return the created entry
            cursor.execute('''
                SELECT id, type, title, content, source_video_ids, tags, created_at, updated_at
                FROM intelligence
                WHERE id = ?
            ''', (intelligence_id,))
            row = cursor.fetchone()
            return self._serialize_intelligence_row(row)
        except sqlite3.OperationalError as e:
            if 'locked' in str(e).lower():
                print(f"⚠️ Database locked error in save_intelligence: {e}")
                # Wait a bit and retry once
                import time
                time.sleep(0.2)
                if conn:
                    conn.close()
                conn = self.get_connection()
                cursor = conn.cursor()
                # Retry the insert
                cursor.execute('''
                    INSERT INTO intelligence (
                        type, title, content, source_video_ids, tags
                    )
                    VALUES (?, ?, ?, ?, ?)
                ''', (
                    intelligence_type,
                    payload.get('title'),
                    payload.get('content'),
                    source_video_ids,
                    payload.get('tags')
                ))
                intelligence_id = cursor.lastrowid
                conn.commit()
                cursor.execute('''
                    SELECT id, type, title, content, source_video_ids, tags, created_at, updated_at
                    FROM intelligence
                    WHERE id = ?
                ''', (intelligence_id,))
                row = cursor.fetchone()
                return self._serialize_intelligence_row(row)
            else:
                raise
        finally:
            if conn:
                conn.close()
    
    def get_intelligence(self, intelligence_type=None, limit=100, offset=0):
        """Get intelligence entries, optionally filtered by type"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        if intelligence_type:
            cursor.execute('''
                SELECT id, type, title, content, source_video_ids, tags, created_at, updated_at
                FROM intelligence
                WHERE type = ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            ''', (intelligence_type, limit, offset))
        else:
            cursor.execute('''
                SELECT id, type, title, content, source_video_ids, tags, created_at, updated_at
                FROM intelligence
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            ''', (limit, offset))
        
        rows = cursor.fetchall()
        conn.close()
        return [self._serialize_intelligence_row(row) for row in rows]
    
    def get_intelligence_by_id(self, intelligence_id):
        """Get a single intelligence entry by ID"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, type, title, content, source_video_ids, tags, created_at, updated_at
            FROM intelligence
            WHERE id = ?
        ''', (intelligence_id,))
        
        row = cursor.fetchone()
        conn.close()
        return self._serialize_intelligence_row(row)
    
    def get_intelligence_stats(self):
        """Get statistics for intelligence entries by type"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        stats = {}
        types = ['synthesis', 'prediction', 'script', 'query', 'trends']
        
        for int_type in types:
            cursor.execute('''
                SELECT COUNT(*) as count, MAX(created_at) as latest
                FROM intelligence
                WHERE type = ?
            ''', (int_type,))
            row = cursor.fetchone()
            stats[int_type] = {
                'count': row[0] if row else 0,
                'latest': row[1] if row and row[1] else None
            }
        
        conn.close()
        return stats
    
    def update_intelligence(self, intelligence_id, payload):
        """Update an existing intelligence entry"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        updates = []
        values = []
        
        for key in ['title', 'content', 'tags']:
            if key in payload:
                updates.append(f"{key} = ?")
                values.append(payload[key])
        
        if 'source_video_ids' in payload:
            source_video_ids = payload['source_video_ids']
            if isinstance(source_video_ids, list):
                source_video_ids = ','.join(str(vid) for vid in source_video_ids)
            updates.append("source_video_ids = ?")
            values.append(source_video_ids)
        
        if not updates:
            conn.close()
            return None
        
        updates.append("updated_at = CURRENT_TIMESTAMP")
        values.append(intelligence_id)
        
        cursor.execute(f'''
            UPDATE intelligence
            SET {', '.join(updates)}
            WHERE id = ?
        ''', values)
        conn.commit()
        
        cursor.execute('''
            SELECT id, type, title, content, source_video_ids, tags, created_at, updated_at
            FROM intelligence
            WHERE id = ?
        ''', (intelligence_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        return self._serialize_intelligence_row(row)
    
    def delete_intelligence(self, intelligence_id):
        """Delete an intelligence entry"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM intelligence WHERE id = ?', (intelligence_id,))
        conn.commit()
        deleted = cursor.rowcount > 0
        conn.close()
        return deleted
    
    def _serialize_intelligence_row(self, row):
        """Serialize an intelligence database row to dict"""
        if not row:
            return None
        
        # Parse source_video_ids from comma-separated string
        source_video_ids = row['source_video_ids']
        if source_video_ids:
            try:
                source_video_ids = [int(vid.strip()) for vid in source_video_ids.split(',') if vid.strip()]
            except (ValueError, AttributeError):
                source_video_ids = []
        else:
            source_video_ids = []
        
        return {
            'id': row['id'],
            'type': row['type'],
            'title': row['title'],
            'content': row['content'],
            'source_video_ids': source_video_ids,
            'tags': row['tags'] or '',
            'created_at': row['created_at'],
            'updated_at': row['updated_at']
        }

db_service = DatabaseService(DATABASE_PATH)

# Import the YouTube processor
from youtube_processor import YouTubeProcessor
from podcast_processor import PodcastProcessor

# Initialize processors
processor = YouTubeProcessor()
podcast_processor = PodcastProcessor()

# Ensure screenshots folder exists
SCREENSHOTS_FOLDER = "screenshots"
os.makedirs(SCREENSHOTS_FOLDER, exist_ok=True)

AUDIO_FOLDER = "audio_files"
os.makedirs(AUDIO_FOLDER, exist_ok=True)

AUDIO_GENERATED_FOLDER = "audio_generated"
os.makedirs(AUDIO_GENERATED_FOLDER, exist_ok=True)

PODCAST_AUDIO_FOLDER = "podcast_audio"
os.makedirs(PODCAST_AUDIO_FOLDER, exist_ok=True)

# iCloud Drive folder for auto-sync to iPhone
ICLOUD_PODCASTS_FOLDER = os.path.expanduser("~/Library/Mobile Documents/com~apple~CloudDocs/Knowledge Studio Audio")
try:
    os.makedirs(ICLOUD_PODCASTS_FOLDER, exist_ok=True)
    print(f"✅ iCloud Drive folder ready: Knowledge Studio Audio")
except Exception as e:
    print(f"⚠️  Could not create iCloud folder: {e}")
    ICLOUD_PODCASTS_FOLDER = None

@app.route('/')
def index():
    try:
        with open('interface.html', 'r') as f:
            return f.read()
    except FileNotFoundError:
        return '<h1>Interface file not found</h1><p>API running at <a href="/api/status">/api/status</a></p>'

@app.route('/library')
def library():
    try:
        with open('library.html', 'r') as f:
            content = f.read()
            # Add cache-busting headers
            from flask import Response
            response = Response(content, mimetype='text/html')
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
            return response
    except FileNotFoundError:
        return '<h1>Library page not found</h1><p><a href="/">← Back to Capture</a></p>'

@app.route('/stats')
def stats():
    try:
        with open('stats.html', 'r') as f:
            return f.read()
    except FileNotFoundError:
        return '<h1>Stats page not found</h1><p><a href="/">← Back to Capture</a></p>'

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get usage statistics and cost data"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Helper function to estimate cost based on content length
        def estimate_cost(content_length):
            """Estimate API cost based on content length (characters)
            Assumes: 4 chars per token, 20% output tokens, Haiku 4.5 pricing"""
            if not content_length or content_length == 0:
                return 0.0
            
            input_tokens = content_length / 4
            output_tokens = input_tokens * 0.20  # 20% output (typical for summaries)
            
            input_cost = (input_tokens / 1_000_000) * 1.0  # $1 per 1M tokens
            output_cost = (output_tokens / 1_000_000) * 5.0  # $5 per 1M tokens
            
            return input_cost + output_cost
        
        # Vision API cost per screenshot (rough estimate)
        VISION_API_COST = 0.002  # ~$0.002 per image for Vision API (Haiku 4.5)
        
        # Get current date ranges
        now = datetime.now()
        current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        current_year_start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        last_month_start = (current_month_start - timedelta(days=1)).replace(day=1)
        thirty_days_ago = now - timedelta(days=30)
        
        # Get videos data
        cursor.execute('''
            SELECT processing_date, full_transcript, ai_summary
            FROM videos
            WHERE status = 'completed' AND full_transcript IS NOT NULL
        ''')
        videos = cursor.fetchall()
        
        # Get articles data
        cursor.execute('''
            SELECT created_at, content, summary
            FROM articles
            WHERE content IS NOT NULL
        ''')
        articles = cursor.fetchall()
        
        # Calculate costs
        total_cost = 0.0
        month_cost = 0.0
        last_month_cost = 0.0
        year_cost = 0.0
        daily_costs = {}  # {date: cost}
        
        # Process videos
        for video_date, transcript, summary in videos:
            if not video_date:
                continue
                
            try:
                video_dt = datetime.strptime(video_date, '%Y-%m-%d %H:%M:%S') if isinstance(video_date, str) else video_date
            except:
                continue
            
            transcript_len = len(transcript) if transcript else 0
            cost = estimate_cost(transcript_len)
            # Add Vision API cost for screenshot processing (each video starts with a screenshot)
            cost += VISION_API_COST
            
            total_cost += cost
            
            if video_dt >= current_month_start:
                month_cost += cost
            if video_dt >= last_month_start and video_dt < current_month_start:
                last_month_cost += cost
            if video_dt >= current_year_start:
                year_cost += cost
            
            # Daily costs for chart
            if video_dt >= thirty_days_ago:
                date_key = video_dt.strftime('%Y-%m-%d')
                daily_costs[date_key] = daily_costs.get(date_key, 0.0) + cost
        
        # Process articles
        for article_date, content, summary in articles:
            if not article_date:
                continue
                
            try:
                article_dt = datetime.strptime(article_date, '%Y-%m-%d %H:%M:%S') if isinstance(article_date, str) else article_date
            except:
                continue
            
            content_len = len(content) if content else 0
            cost = estimate_cost(content_len)
            
            total_cost += cost
            
            if article_dt >= current_month_start:
                month_cost += cost
            if article_dt >= last_month_start and article_dt < current_month_start:
                last_month_cost += cost
            if article_dt >= current_year_start:
                year_cost += cost
            
            # Daily costs for chart
            if article_dt >= thirty_days_ago:
                date_key = article_dt.strftime('%Y-%m-%d')
                daily_costs[date_key] = daily_costs.get(date_key, 0.0) + cost
        
        # Build chart data (last 30 days)
        chart_data = []
        for i in range(30):
            date = (now - timedelta(days=29-i)).strftime('%Y-%m-%d')
            chart_data.append({
                'date': date,
                'cost': round(daily_costs.get(date, 0.0), 4)
            })
        
        # Get counts
        cursor.execute('SELECT COUNT(*) FROM videos WHERE status = "completed"')
        total_videos = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM articles')
        total_articles = cursor.fetchone()[0]
        
        # Get this week's count
        week_ago = now - timedelta(days=7)
        cursor.execute('''
            SELECT COUNT(*) FROM videos 
            WHERE status = "completed" AND processing_date >= ?
        ''', (week_ago.strftime('%Y-%m-%d'),))
        this_week_videos = cursor.fetchone()[0]
        
        # Get recent activity (last 10 items)
        recent_activity = []
        
        # Recent videos
        cursor.execute('''
            SELECT title, processing_date, full_transcript
            FROM videos
            WHERE status = "completed" AND full_transcript IS NOT NULL
            ORDER BY processing_date DESC
            LIMIT 5
        ''')
        for title, date, transcript in cursor.fetchall():
            cost = estimate_cost(len(transcript) if transcript else 0)
            recent_activity.append({
                'type': 'video',
                'title': title or 'Untitled Video',
                'date': date,
                'cost': round(cost, 4),
                'icon': '📹'
            })
        
        # Recent articles
        cursor.execute('''
            SELECT title, created_at, content
            FROM articles
            WHERE content IS NOT NULL
            ORDER BY created_at DESC
            LIMIT 5
        ''')
        for title, date, content in cursor.fetchall():
            cost = estimate_cost(len(content) if content else 0)
            recent_activity.append({
                'type': 'article',
                'title': title or 'Untitled Article',
                'date': date,
                'cost': round(cost, 4),
                'icon': '📄'
            })
        
        # Sort by date and take top 10
        recent_activity.sort(key=lambda x: x['date'] if x['date'] else '', reverse=True)
        recent_activity = recent_activity[:10]
        
        conn.close()
        
        return jsonify({
            'success': True,
            'stats': {
                'total_cost': round(total_cost, 2),
                'month_cost': round(month_cost, 2),
                'last_month_cost': round(last_month_cost, 2),
                'year_cost': round(year_cost, 2),
                'month_change': round(month_cost - last_month_cost, 2),
                'total_videos': total_videos,
                'total_articles': total_articles,
                'this_week_videos': this_week_videos,
                'chart_data': chart_data,
                'recent_activity': recent_activity,
                'models': {
                    'text_model': 'Claude Haiku 4.5',
                    'text_model_id': 'claude-haiku-4-5-20251001',
                    'vision_model': 'Claude Sonnet 4.5',
                    'vision_model_id': 'claude-3-5-sonnet-20241022'
                }
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/debug')
def debug():
    try:
        with open('debug.html', 'r') as f:
            return f.read()
    except FileNotFoundError:
        return '<h1>Debug page not found</h1>'

@app.route('/api/search-interviews', methods=['GET'])
def search_interviews():
    """Search YouTube for interviews with a specific person"""
    try:
        person_name = request.args.get('person', '').strip()
        max_results = request.args.get('max_results', type=int) or 50
        
        if not person_name:
            return jsonify({'success': False, 'error': 'Person name is required'}), 400
        
        results = processor.search_interviews_by_person(person_name, max_results=max_results)
        
        # Check if person is already subscribed
        person_subscriptions = processor.list_person_subscriptions()
        subscribed_person_names = {sub['person_name'].lower() for sub in person_subscriptions if sub.get('enabled')}
        is_subscribed = person_name.lower() in subscribed_person_names
        
        return jsonify({
            'success': True,
            'person': person_name,
            'results': results,
            'count': len(results),
            'is_subscribed': is_subscribed
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/person-subscriptions', methods=['GET'])
def list_person_subscriptions():
    """List person subscriptions."""
    try:
        subs = processor.list_person_subscriptions()
        return jsonify({'success': True, 'subscriptions': subs})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/person-subscriptions', methods=['POST'])
def add_person_subscription():
    """Add a new person subscription."""
    data = request.get_json(force=True)
    person_name = data.get('person_name', '').strip()
    if not person_name:
        return jsonify({'success': False, 'error': 'Person name is required'}), 400
    try:
        subscription = processor.add_person_subscription(person_name)
        return jsonify({'success': True, 'subscription': subscription})
    except ValueError as ve:
        return jsonify({'success': False, 'error': str(ve)}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/person-subscriptions/<int:subscription_id>', methods=['DELETE'])
def delete_person_subscription(subscription_id):
    """Delete a person subscription."""
    try:
        removed = processor.remove_person_subscription(subscription_id)
        if not removed:
            return jsonify({'success': False, 'error': 'Subscription not found'}), 404
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/person-subscriptions/<int:subscription_id>/toggle', methods=['POST'])
def toggle_person_subscription(subscription_id):
    """Enable or disable a person subscription."""
    try:
        subscription = processor.toggle_person_subscription(subscription_id)
        return jsonify({'success': True, 'subscription': subscription})
    except ValueError as ve:
        return jsonify({'success': False, 'error': str(ve)}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/person-subscriptions/<int:subscription_id>/refresh', methods=['POST'])
def refresh_person_subscription(subscription_id):
    """Refresh interviews for a person subscription."""
    max_results = None
    if request.is_json:
        payload = request.get_json(silent=True) or {}
        max_results = payload.get('max_results')
    try:
        result = processor.refresh_person_subscription(
            subscription_id,
            max_results=max_results
        )
        return jsonify({'success': True, 'result': result})
    except ValueError as ve:
        return jsonify({'success': False, 'error': str(ve)}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/person-interviews', methods=['GET'])
def list_person_interviews():
    """List person interviews with optional filters."""
    person_subscription_id = request.args.get('person_subscription_id', type=int)
    processed_param = request.args.get('processed')
    limit = request.args.get('limit', type=int) or 50
    offset = request.args.get('offset', type=int) or 0
    order = request.args.get('order', 'desc')
    
    processed = None
    if processed_param is not None:
        processed = processed_param.lower() in ('true', '1', 'yes')
    
    try:
        result = processor.get_person_interviews(
            person_subscription_id=person_subscription_id,
            processed=processed,
            limit=limit,
            offset=offset,
            order=order
        )
        return jsonify({'success': True, **result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/person-interviews/add-to-queue', methods=['POST'])
def add_person_interviews_to_queue():
    """Add person interviews to processing queue."""
    data = request.get_json(force=True)
    interview_ids = data.get('interview_ids', [])
    if not interview_ids:
        return jsonify({'success': False, 'error': 'No interview IDs provided'}), 400
    try:
        result = processor.add_person_interviews_to_queue_by_ids(interview_ids)
        return jsonify({'success': True, **result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/person-subscriptions/monitor', methods=['POST'])
def monitor_person_subscriptions():
    """Monitor enabled person subscriptions for new interviews (background task)
    
    Uses staggered checking - only checks people who are due (default: not checked in 72+ hours).
    This spreads out API calls to avoid quota exhaustion and doesn't interfere with other processing.
    """
    max_results = request.args.get('max_results', type=int) or 20
    check_interval_hours = request.args.get('check_interval_hours', type=int) or 72
    max_checks_per_run = request.args.get('max_checks_per_run', type=int)
    
    if request.is_json:
        payload = request.get_json(silent=True) or {}
        max_results = payload.get('max_results', max_results)
        check_interval_hours = payload.get('check_interval_hours', check_interval_hours)
        max_checks_per_run = payload.get('max_checks_per_run', max_checks_per_run)
    
    try:
        result = processor.monitor_person_subscriptions(
            max_results_per_person=max_results,
            check_interval_hours=check_interval_hours,
            max_checks_per_run=max_checks_per_run
        )
        return jsonify({'success': True, **result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/videos')
def get_videos():
    try:
        videos = db_service.get_all_videos()
        return jsonify({
            'success': True,
            'videos': videos,
            'count': len(videos)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/videos/search')
def search_videos():
    query = request.args.get('q', '')
    if not query:
        return jsonify({'success': False, 'error': 'Query required'}), 400
    
    try:
        videos = db_service.search_videos(query)
        return jsonify({
            'success': True,
            'videos': videos,
            'count': len(videos),
            'query': query
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/videos/<int:video_id>')
def get_video(video_id):
    try:
        video = db_service.get_video_by_id(video_id)
        if not video:
            return jsonify({'success': False, 'error': 'Video not found'}), 404
        return jsonify({'success': True, 'video': video})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/videos/<int:video_id>/analyze', methods=['POST'])
def analyze_video(video_id):
    try:
        data = request.get_json()
        analysis_type = data.get('type', 'brief')
        custom_prompt = data.get('custom_prompt', '')
        
        video = db_service.get_video_by_id(video_id)
        if not video:
            return jsonify({'success': False, 'error': 'Video not found'}), 404
        
        transcript = video.get('full_transcript') or video.get('transcript') or ''
        if not transcript:
            return jsonify({'success': False, 'error': 'No transcript'}), 400
        
        if custom_prompt:
            prompt = f"Custom analysis: {custom_prompt}\n\nVideo: {video['title']}\nTranscript: {transcript[:8000]}"
        else:
            prompts = {
                'brief': f"Create a brief analysis of this video:\n\nTitle: {video['title']}\nTranscript: {transcript[:8000]}\n\nProvide: Executive summary, core thesis, key value, bottom line.",
                'bullets': f"Create bullet points for this video:\n\nTitle: {video['title']}\nTranscript: {transcript[:8000]}\n\nExtract: frameworks, tools, processes, data points, costs, specs.",
                'frameworks': f"Extract frameworks from this video:\n\nTitle: {video['title']}\nTranscript: {transcript[:8000]}\n\nFocus on: named frameworks, methodologies, systematic approaches.",
                'technical': f"Extract technical details:\n\nTitle: {video['title']}\nTranscript: {transcript[:8000]}\n\nFocus on: settings, specs, formats, APIs, pricing, performance."
            }
            prompt = prompts.get(analysis_type, prompts['brief'])
        
        response = claude_client.messages.create(
            model="claude-haiku-4-5-20251001",  # Haiku 4.5: Sonnet-level quality at 1/3 cost
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}]
        )
        
        return jsonify({
            'success': True,
            'analysis': response.content[0].text,
            'type': analysis_type,
            'video_id': video_id
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/videos/<int:video_id>/regenerate-brief', methods=['POST'])
def regenerate_brief(video_id):
    try:
        video = db_service.get_video_by_id(video_id)
        if not video:
            return jsonify({'success': False, 'error': 'Video not found'}), 404
        
        transcript = video.get('full_transcript') or video.get('transcript') or ''
        if not transcript or len(transcript) < 5000:
            return jsonify({'success': False, 'error': 'No transcript available for this video. Only video descriptions were found, which don\'t contain the actual conversation content needed for analysis.'}), 400
        
        # Detect content type for domain-specific synthesis
        from youtube_processor import YouTubeProcessor, _parse_formatted_duration
        processor = YouTubeProcessor()
        
        # Get duration if available
        duration_str = video.get('duration')
        duration_seconds = _parse_formatted_duration(duration_str) if duration_str else None
        
        content_type = processor.detect_content_type(video['title'], transcript, duration_seconds)
        
        # Load the appropriate prompt based on content type
        prompt_file = f"prompts/current_best/{content_type}_prompt.txt"
        try:
            with open(prompt_file, 'r', encoding='utf-8') as f:
                prompt_template = f.read()
        except FileNotFoundError:
            # Fallback to explainer prompt
            with open("prompts/current_best/explainer_prompt.txt", 'r', encoding='utf-8') as f:
                prompt_template = f.read()
        
        # Format the prompt
        prompt = prompt_template.format(title=video['title'], transcript=transcript)
        
        # Generate new brief with improved overload handling
        max_retries = 3
        base_delay = 60  # Start with 60 seconds
        
        for attempt in range(max_retries):
            try:
                response = claude_client.messages.create(
                    model="claude-haiku-4-5-20251001",  # Use Haiku 4.5 for cost efficiency
                    max_tokens=8192,  # Increased to allow comprehensive summaries without truncation
                    messages=[{"role": "user", "content": prompt}],
                    timeout=300.0  # 5 minutes timeout for long requests
                )
                break  # Success, exit retry loop
                
            except Exception as e:
                error_str = str(e)
                # Check for timeout errors and retry
                if ("timeout" in error_str.lower() or "timed out" in error_str.lower() or "interrupted" in error_str.lower()) and attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)  # Exponential backoff
                    print(f"⏳ Request timeout, waiting {delay} seconds before retry {attempt + 2}/{max_retries}...")
                    time.sleep(delay)
                    continue
                # Check for rate limit errors and retry
                elif ("rate_limit_error" in error_str or "overloaded_error" in error_str or "529" in error_str) and attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)  # Exponential backoff
                    print(f"⏳ API overload/rate limit hit, waiting {delay} seconds before retry {attempt + 2}/{max_retries}...")
                    time.sleep(delay)
                    continue
                else:
                    return jsonify({'success': False, 'error': f'API Error: {error_str}'}), 500
        
        # Update the database with new brief
        conn = db_service.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE videos SET ai_summary = ?, prompt_used = ? WHERE id = ?",
            (response.content[0].text, content_type, video_id)
        )
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'brief': response.content[0].text,
            'video_id': video_id
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/videos/<int:video_id>/llm-brief', methods=['POST'])
def generate_llm_brief(video_id):
    try:
        video = db_service.get_video_by_id(video_id)
        if not video:
            return jsonify({'success': False, 'error': 'Video not found'}), 404
        
        transcript = video.get('full_transcript') or video.get('transcript') or ''
        if not transcript:
            return jsonify({'success': False, 'error': 'No transcript available'}), 400
        
        # Detect content type for domain-specific synthesis
        from youtube_processor import YouTubeProcessor, _parse_formatted_duration
        processor = YouTubeProcessor()
        
        # Get duration if available
        duration_str = video.get('duration')
        duration_seconds = _parse_formatted_duration(duration_str) if duration_str else None
        
        content_type = processor.detect_content_type(video['title'], transcript, duration_seconds)
        
        # Get brief summary for context
        brief_summary = video.get('ai_summary', '')[:500] if video.get('ai_summary') else 'No summary available'
        
        # Load category-specific LLM Brief prompt
        llm_brief_prompt = load_llm_brief_prompt(content_type, video['title'], transcript, brief_summary)

        response = claude_client.messages.create(
            model="claude-haiku-4-5-20251001",  # Haiku 4.5: Sonnet-level quality at 1/3 cost
            max_tokens=8192,  # Increased to allow comprehensive summaries without truncation
            messages=[{"role": "user", "content": llm_brief_prompt}]
        )
        
        return jsonify({
            'success': True,
            'brief': response.content[0].text,
            'video_id': video_id
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/chat/session', methods=['POST'])
def create_chat_session():
    """Create a new chat session"""
    try:
        data = request.get_json() or {}
        channel_id = data.get('channel_id')
        channel_name = data.get('channel_name')
        mode = data.get('mode', 'grounded')
        
        session_id = db_service.create_chat_session(
            channel_id=channel_id,
            channel_name=channel_name,
            mode=mode
        )
        
        session = db_service.get_chat_session(session_id)
        return jsonify({
            'success': True,
            'session': session
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/chat/session/<session_id>', methods=['GET'])
def get_chat_session(session_id):
    """Get chat session details and history"""
    try:
        session = db_service.get_chat_session(session_id)
        if not session:
            return jsonify({'success': False, 'error': 'Session not found'}), 404
        
        history = db_service.get_chat_history(session_id, limit=20)
        session['history'] = history
        
        return jsonify({
            'success': True,
            'session': session
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/chat', methods=['POST'])
def chat():
    """AI-powered chat with knowledge base - supports channel filtering and conversation history"""
    try:
        data = request.get_json()
        question = data.get('question', '')
        session_id = data.get('session_id')
        channel_id = data.get('channel_id')
        channel_name = data.get('channel_name')
        mode = data.get('mode', 'grounded')
        
        if not question:
            return jsonify({'success': False, 'error': 'Question required'}), 400
        
        # Normalize channel_id/channel_name - convert empty strings to None
        if channel_id == '':
            channel_id = None
        if channel_name == '':
            channel_name = None
        
        # Get or create session
        if session_id:
            session = db_service.get_chat_session(session_id)
            if not session:
                return jsonify({'success': False, 'error': 'Session not found'}), 404
            channel_id = session.get('channel_id') or channel_id
            channel_name = session.get('channel_name') or channel_name
            mode = session.get('mode') or mode
        else:
            # Create new session if none provided
            session_id = db_service.create_chat_session(
                channel_id=channel_id,
                channel_name=channel_name,
                mode=mode
            )
        
        # Get conversation history
        history = db_service.get_chat_history(session_id, limit=10)
        
        # Save user message
        db_service.add_chat_message(session_id, 'user', question)
        
        # First, get broader initial matches (more candidates)
        print(f"🔍 About to search: question='{question}', channel_id={channel_id}, channel_name={channel_name}")
        initial_videos = db_service.search_videos(
            question, 
            channel_id=channel_id, 
            channel_name=channel_name
        )[:10]  # Get more candidates
        print(f"🔍 Search returned {len(initial_videos)} videos")
        
        # If channel_id search returned nothing, try fallback to channel name search
        if channel_id and not initial_videos and channel_name:
            print(f"⚠️  Channel ID search returned no results, trying channel name fallback: {channel_name}")
            initial_videos = db_service.search_videos(
                question,
                channel_id=None,
                channel_name=channel_name
            )[:10]
            print(f"🔍 Channel name fallback returned {len(initial_videos)} videos")
        
        # If still nothing and channel filter is active, try channel-only search (ignore query)
        if (channel_id or channel_name) and not initial_videos:
            print(f"⚠️  Query-based search returned no results for channel, trying channel-only search (any videos from this channel)")
            # Get videos from this channel regardless of query match
            conn = sqlite3.connect(DATABASE_PATH)
            cursor = conn.cursor()
            
            if channel_id:
                # Get channel name from subscription
                cursor.execute('SELECT channel_name FROM channel_subscriptions WHERE channel_id = ?', (channel_id,))
                sub_row = cursor.fetchone()
                if sub_row and sub_row[0]:
                    channel_name_only = sub_row[0]
                else:
                    channel_name_only = channel_name
            else:
                channel_name_only = channel_name
            
            if channel_name_only:
                cursor.execute('''
                    SELECT id, title, channel, video_url, full_transcript,
                           ai_summary, processing_date, status, filename, confidence_score, tags, prompt_used,
                           published_at, COALESCE(favorited, 0) as favorited, original_publish_date
                    FROM videos 
                    WHERE status = 'completed' 
                    AND channel = ?
                    ORDER BY processing_date DESC
                    LIMIT 10
                ''', (channel_name_only,))
                fallback_rows = cursor.fetchall()
                initial_videos = []
                for row in fallback_rows:
                    initial_videos.append({
                        'id': row[0],
                        'title': row[1] or 'Untitled Video',
                        'channel': row[2] or 'Unknown Channel',
                        'video_url': row[3],
                        'full_transcript': row[4],
                        'ai_summary': row[5],
                        'summary': str(row[5]) if row[5] else "No summary",
                        'date': row[6] or 'Unknown date',
                        'status': row[7],
                        'filename': row[8],
                        'confidence_score': row[9] or 0,
                        'tags': row[10] or '',
                        'prompt_used': row[11] or 'general',
                        'favorited': bool(row[12]) if len(row) > 12 else False,
                        'duration': 'Unknown duration'
                    })
                print(f"✅ Channel-only fallback found {len(initial_videos)} videos for '{channel_name_only}'")
            
            conn.close()
        
        # Final fallback: if still nothing and channel filter is active, try without channel filter
        if (channel_id or channel_name) and not initial_videos:
            print(f"⚠️  Channel-only search also returned no results, trying without channel filter")
            initial_videos = db_service.search_videos(question)[:10]
        
        initial_articles = []
        
        # Search articles
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        search_term = f"%{question}%"
        cursor.execute('''
            SELECT id, title, url, content, summary
            FROM articles
            WHERE (title LIKE ? OR summary LIKE ? OR content LIKE ?)
            ORDER BY created_at DESC
            LIMIT 10
        ''', (search_term, search_term, search_term))
        
        for row in cursor.fetchall():
            initial_articles.append({
                'id': row[0],
                'title': row[1],
                'url': row[2],
                'content': row[3],
                'summary': row[4]
            })
        
        conn.close()
        
        # Debug logging
        print(f"🔍 Chat search: question='{question[:50]}...', channel_id={channel_id}, channel_name={channel_name}")
        print(f"📊 Found {len(initial_videos)} videos, {len(initial_articles)} articles")
        
        # Use top matches directly (skip strict relevance filtering for now)
        if initial_videos or initial_articles:
            # Use top matches directly (more permissive)
            videos = initial_videos[:5]  # Use top 5 instead of 3 for better coverage
            articles = initial_articles[:5]
            print(f"✅ Using top {len(videos)} videos and {len(articles)} articles")
        else:
            videos = []
            articles = []
            print(f"❌ No videos or articles found in initial search")
            # Fallback: if no results and no channel filter, get most recent videos
            if not channel_id and not channel_name:
                print(f"🔄 Fallback: Getting most recent videos (no search filter)")
                conn = sqlite3.connect(DATABASE_PATH)
                cursor = conn.cursor()
                cursor.execute('''
                SELECT id, title, channel, video_url, full_transcript,
                       ai_summary, processing_date, status, filename, confidence_score, tags, prompt_used,
                       published_at, COALESCE(favorited, 0) as favorited, original_publish_date
                    FROM videos 
                    WHERE status = 'completed' 
                    ORDER BY processing_date DESC
                    LIMIT 5
                ''')
                fallback_rows = cursor.fetchall()
                conn.close()
                for row in fallback_rows:
                    videos.append({
                        'id': row[0],
                        'title': row[1] or 'Untitled Video',
                        'channel': row[2] or 'Unknown Channel',
                        'video_url': row[3],
                        'full_transcript': row[4],
                        'ai_summary': row[5],
                        'summary': str(row[5]) if row[5] else "No summary",
                        'date': row[6] or 'Unknown date',
                        'status': row[7],
                        'filename': row[8],
                        'confidence_score': row[9] or 0,
                        'tags': row[10] or '',
                        'prompt_used': row[11] or 'general',
                        'favorited': bool(row[12]) if len(row) > 12 else False,
                        'duration': 'Unknown duration'
                    })
                print(f"✅ Fallback found {len(videos)} recent videos")
        
        # Collect relevant content from both sources
        relevant_content = []
        
        print(f"📝 Processing {len(videos)} videos to extract content...")
        # Add videos (use summaries instead of full transcripts for efficiency)
        for video in videos:
            video_id = video.get('id')
            video_title = video.get('title', 'Unknown')
            print(f"  Processing video ID {video_id}: '{video_title[:60]}...'")
            # Prefer summary over transcript for chat (faster, cheaper, more focused)
            summary = video.get('ai_summary') or video.get('summary')
            print(f"    Summary check: ai_summary={bool(video.get('ai_summary'))}, summary={bool(video.get('summary'))}, final={bool(summary)}")
            if summary:
                print(f"    Summary type: {type(summary)}, length: {len(str(summary))}")
            if not summary:
                # Fallback to transcript if no summary available
                if 'transcript' not in video or not video.get('transcript'):
                    full_video = db_service.get_video_by_id(video['id'])
                    transcript = full_video.get('transcript') if full_video else None
                else:
                    transcript = video.get('transcript')
                if transcript:
                    relevant_content.append(f"Video: {video.get('title', 'Unknown')}\nContent: {transcript[:2000]}")
                    print(f"  ✓ Added video '{video.get('title', 'Unknown')}' (using transcript)")
            else:
                # Use summary (preferred)
                # Handle both string and JSON summaries
                summary_text = summary
                if isinstance(summary, str) and summary.startswith('{'):
                    try:
                        import json
                        summary_json = json.loads(summary)
                        # Extract text from structured summary
                        summary_text = summary_json.get('executive_summary', '') or summary_json.get('summary', '') or str(summary_json)
                    except:
                        summary_text = summary
                
                if summary_text and len(summary_text.strip()) > 50:
                    relevant_content.append(f"Video: {video.get('title', 'Unknown')}\nContent: {summary_text[:2000]}")
                    print(f"  ✓ Added video '{video.get('title', 'Unknown')}' (using summary, {len(summary_text)} chars)")
                else:
                    print(f"  ⚠️  Summary too short for '{video.get('title', 'Unknown')}' ({len(summary_text) if summary_text else 0} chars), trying transcript...")
                    # Fallback to transcript
                    transcript = video.get('transcript') or video.get('full_transcript')
                    if not transcript:
                        full_video = db_service.get_video_by_id(video['id'])
                        transcript = full_video.get('transcript') if full_video else None
                    if transcript and len(transcript) > 100:
                        relevant_content.append(f"Video: {video.get('title', 'Unknown')}\nContent: {transcript[:2000]}")
                        print(f"  ✓ Added video '{video.get('title', 'Unknown')}' (using transcript fallback, {len(transcript)} chars)")
                    else:
                        print(f"  ❌ Skipped video '{video.get('title', 'Unknown')}' - no usable content")
        
        # Add articles (already have content/summary from search)
        for article in articles:
            # Use content if available, otherwise use summary
            content = article.get('content') or article.get('summary', '')
            if content:
                relevant_content.append(f"Article: {article.get('title', 'Unknown')}\nContent: {content[:2000]}")
        
        if not relevant_content:
            print(f"❌ No relevant content found. Videos: {len(videos)}, Articles: {len(articles)}")
            print(f"   Initial search found: {len(initial_videos)} videos, {len(initial_articles)} articles")
            return jsonify({
                'success': True,
                'response': f"No relevant content found in your knowledge base to answer this question. {'(Filtered to: ' + (channel_name or channel_id or 'All Content') + ')' if (channel_id or channel_name) else ''}",
                'question': question,
                'videos_searched': len(initial_videos),
                'articles_searched': len(initial_articles),
                'session_id': session_id
            })
        
        # Build conversation history context
        history_context = ""
        if history and len(history) > 0:
            history_text = "\n".join([
                f"{'User' if msg['role'] == 'user' else 'Assistant'}: {msg['message']}"
                for msg in history[-5:]  # Last 5 exchanges
            ])
            history_context = f"\n\nPrevious conversation:\n{history_text}\n"
        
        # Build channel context if filtering by channel
        channel_context = ""
        if channel_name:
            channel_context = f"\n\nYou are answering questions specifically about content from {channel_name}. Only use content from this creator's videos/articles."
        
        # Build mode-specific instructions
        mode_instructions = ""
        if mode == 'grounded':
            mode_instructions = "\n- Answer based ONLY on the content provided above. Do not speculate or use general knowledge."
        elif mode == 'interpolated':
            mode_instructions = "\n- Use the provided content as your primary source. You may make logical connections between excerpts, but clearly indicate when you're extrapolating (e.g., 'Based on the patterns in the content...')."
        
        # Build comprehensive prompt
        prompt = f"""You are answering questions based on the user's personal knowledge base of videos and articles.{channel_context}

Question: {question}{history_context}

Relevant content from knowledge base:
{chr(10).join(relevant_content)}

Instructions:
- Answer the question based on the content provided above{mode_instructions}
- **Only use sources that are actually relevant to the question** - ignore any that seem unrelated
- If the content doesn't contain enough information, say so honestly
- Be specific and cite sources (e.g., "According to the video about X..." or "The article on Y states...")
- If multiple sources mention the same thing, synthesize the information
- If a source doesn't clearly relate to the question, don't use it in your answer
- Be concise but comprehensive
- If you're uncertain, indicate that

Provide your answer:"""
        
        response = claude_client.messages.create(
            model="claude-haiku-4-5-20251001",  # Haiku 4.5: Sonnet-level quality at 1/3 cost
            max_tokens=3000,  # Increased for more comprehensive answers
            messages=[{"role": "user", "content": prompt}]
        )
        
        answer_text = response.content[0].text
        
        # Save assistant response
        db_service.add_chat_message(session_id, 'assistant', answer_text)
        
        return jsonify({
            'success': True,
            'response': answer_text,
            'question': question,
            'session_id': session_id,
            'videos_searched': len(videos),
            'articles_searched': len(articles),
            'sources_found': len(relevant_content),
            'channel_name': channel_name,
            'mode': mode
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/check-duplicate', methods=['POST'])
def check_duplicate():
    """Check if a screenshot contains a video that's already been processed"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'Empty filename'}), 400
        
        # Save temporarily to extract metadata
        import tempfile
        temp_dir = tempfile.mkdtemp()
        temp_path = os.path.join(temp_dir, file.filename)
        file.save(temp_path)
        
        try:
            # Extract metadata from screenshot using existing processor instance
            metadata = processor.extract_video_metadata(temp_path)
            
            if not metadata or not metadata.get('is_youtube', False):
                # Not a YouTube video, can't be duplicate
                return jsonify({
                    'success': True,
                    'is_duplicate': False,
                    'is_youtube': False
                })
            
            # Find the video URL
            video_url = processor.find_youtube_video(metadata)
            
            if not video_url:
                # Can't find video URL, can't check duplicate
                return jsonify({
                    'success': True,
                    'is_duplicate': False,
                    'is_youtube': True,
                    'video_url': None
                })
            
            # Check if video already exists in database
            conn = sqlite3.connect(DATABASE_PATH)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, title, channel, processing_date 
                FROM videos 
                WHERE video_url = ?
                ORDER BY processing_date DESC
                LIMIT 1
            ''', (video_url,))
            existing = cursor.fetchone()
            conn.close()
            
            if existing:
                return jsonify({
                    'success': True,
                    'is_duplicate': True,
                    'is_youtube': True,
                    'video_url': video_url,
                    'existing_video': {
                        'id': existing[0],
                        'title': existing[1],
                        'channel': existing[2],
                        'processing_date': existing[3]
                    },
                    'metadata': {
                        'title': metadata.get('title'),
                        'channel': metadata.get('channel')
                    }
                })
            else:
                return jsonify({
                    'success': True,
                    'is_duplicate': False,
                    'is_youtube': True,
                    'video_url': video_url,
                    'metadata': {
                        'title': metadata.get('title'),
                        'channel': metadata.get('channel')
                    }
                })
        finally:
            # Clean up temp file
            try:
                os.remove(temp_path)
                os.rmdir(temp_dir)
            except:
                pass
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/upload', methods=['POST'])
def upload_files():
    try:
        if 'files' not in request.files:
            return jsonify({'success': False, 'error': 'No files provided'}), 400
        
        files = request.files.getlist('files')
        uploaded_files = []
        processing_results = []
        
        for file in files:
            if file.filename == '':
                continue
                
            # Save file to screenshots folder
            filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
            file_path = os.path.join(SCREENSHOTS_FOLDER, filename)
            file.save(file_path)
            uploaded_files.append(filename)
            
            print(f"📸 File uploaded: {filename}")
            
            # Process the screenshot immediately
            try:
                # Extract metadata first
                metadata = processor.extract_video_metadata(file_path)
                
                if metadata and metadata.get('is_youtube', False):
                    # Find video URL
                    video_url = processor.find_youtube_video(metadata)
                    
                    if video_url:
                        # Check if already processed (unless force flag is set)
                        force_reprocess = request.form.get('force', 'false').lower() == 'true'

                        conn = sqlite3.connect(DATABASE_PATH)
                        cursor = conn.cursor()
                        cursor.execute('SELECT id FROM videos WHERE video_url = ?', (video_url,))
                        existing = cursor.fetchone()
                        conn.close()

                        if existing and not force_reprocess:
                            # Update last_duplicate_attempt timestamp on existing record
                            conn2 = sqlite3.connect(DATABASE_PATH)
                            cursor2 = conn2.cursor()
                            cursor2.execute(
                                'UPDATE videos SET last_duplicate_attempt = ? WHERE id = ?',
                                (datetime.now().isoformat(), existing[0])
                            )
                            conn2.commit()
                            conn2.close()

                            processing_results.append({
                                'filename': filename,
                                'status': 'duplicate',
                                'video_id': existing[0],
                                'message': 'Video already processed'
                            })
                        else:
                            # Add to processing queue
                            title = metadata.get('title', '')
                            channel = metadata.get('channel', '')
                            
                            queue_item = processor.add_video_to_queue(
                                video_url=video_url,
                                title=title,
                                channel_name=channel
                            )
                            
                            processing_results.append({
                                'filename': filename,
                                'status': 'queued',
                                'queue_id': queue_item['id'],
                                'video_url': video_url,
                                'message': 'Added to processing queue'
                            })
                            print(f"✅ Added {filename} to processing queue (queue ID: {queue_item['id']})")
                    else:
                        processing_results.append({
                            'filename': filename,
                            'status': 'error',
                            'message': 'Could not find video URL'
                        })
                else:
                    # Not a YouTube screenshot - try processing as article screenshot
                    print(f"📄 Not YouTube, attempting article extraction for: {filename}")
                    try:
                        article_data = processor.extract_article_text_from_image(file_path)
                        if article_data and article_data.get('text'):
                            # Process as article
                            title = article_data.get('title', f'Article from {filename}')
                            text = article_data.get('text', '')

                            # Store and process the article
                            processor.process_article_from_text(file_path, text, title)

                            processing_results.append({
                                'filename': filename,
                                'status': 'queued',
                                'content_type': 'article',
                                'message': f'Processing as article: {title[:50]}...'
                            })
                            print(f"✅ Added article screenshot to processing: {title[:50]}")
                        else:
                            processing_results.append({
                                'filename': filename,
                                'status': 'skipped',
                                'message': 'Could not extract text from screenshot'
                            })
                    except Exception as article_err:
                        print(f"❌ Article extraction failed: {article_err}")
                        processing_results.append({
                            'filename': filename,
                            'status': 'skipped',
                            'message': f'Not YouTube and article extraction failed: {str(article_err)}'
                        })
            except Exception as e:
                print(f"❌ Error processing {filename}: {e}")
                processing_results.append({
                    'filename': filename,
                    'status': 'error',
                    'message': str(e)
                })
        
        return jsonify({
            'success': True,
            'message': f'Successfully uploaded {len(uploaded_files)} file(s)',
            'files': uploaded_files,
            'processing': processing_results
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/videos/<int:video_id>/tags', methods=['PUT'])
def update_video_tags(video_id):
    try:
        data = request.get_json()
        tags = data.get('tags', '')
        
        db_service.update_video_tags(video_id, tags)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/videos/<int:video_id>/title', methods=['PUT'])
def update_video_title(video_id):
    """Update video title"""
    try:
        data = request.get_json()
        title = data.get('title', '').strip()
        
        if not title:
            return jsonify({'success': False, 'error': 'Title cannot be empty'}), 400
        
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute('UPDATE videos SET title = ? WHERE id = ?', (title, video_id))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'title': title})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/articles/<int:article_id>/title', methods=['PUT'])
def update_article_title(article_id):
    """Update article title"""
    try:
        data = request.get_json()
        title = data.get('title', '').strip()
        
        if not title:
            return jsonify({'success': False, 'error': 'Title cannot be empty'}), 400
        
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute('UPDATE articles SET title = ? WHERE id = ?', (title, article_id))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'title': title})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/videos/<int:video_id>/favorite', methods=['PUT'])
def toggle_video_favorite(video_id):
    """Toggle favorite status for a video"""
    try:
        data = request.get_json()
        favorited = data.get('favorited', False)
        
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Add favorited column if it doesn't exist
        try:
            cursor.execute('ALTER TABLE videos ADD COLUMN favorited INTEGER DEFAULT 0')
            conn.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists
        
        cursor.execute('UPDATE videos SET favorited = ? WHERE id = ?', (1 if favorited else 0, video_id))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'favorited': favorited})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/articles/<int:article_id>/favorite', methods=['PUT'])
def toggle_article_favorite(article_id):
    """Toggle favorite status for an article"""
    try:
        data = request.get_json()
        favorited = data.get('favorited', False)
        
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Add favorited column if it doesn't exist
        try:
            cursor.execute('ALTER TABLE articles ADD COLUMN favorited INTEGER DEFAULT 0')
            conn.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists
        
        cursor.execute('UPDATE articles SET favorited = ? WHERE id = ?', (1 if favorited else 0, article_id))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'favorited': favorited})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/process-article', methods=['POST'])
def process_article():
    try:
        data = request.get_json()
        url = data.get('url')

        if not url:
            return jsonify({'success': False, 'error': 'URL is required'}), 400

        # Check for recent duplicate (within last 60 seconds)
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, title FROM articles
            WHERE url = ? AND created_at > datetime('now', '-60 seconds')
            ORDER BY id DESC LIMIT 1
        ''', (url,))
        recent = cursor.fetchone()
        conn.close()

        if recent:
            return jsonify({
                'success': True,
                'article_id': recent[0],
                'title': recent[1],
                'duplicate': True,
                'message': 'Article already processed'
            })

        # Import web scraping functionality
        import requests
        from bs4 import BeautifulSoup
        
        # Fetch the article
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        # Parse the HTML
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Extract article content
        title = soup.find('title')
        title_text = title.get_text().strip() if title else "Untitled Article"
        
        # Try to find main content
        content_selectors = [
            'article', 'main', '[role="main"]', '.post-content', 
            '.article-content', '.entry-content', '.content'
        ]
        
        content_text = ""
        for selector in content_selectors:
            content = soup.select_one(selector)
            if content:
                content_text = content.get_text().strip()
                break
        
        if not content_text:
            # Fallback: get all text
            content_text = soup.get_text().strip()
        
        # Clean up the text
        content_text = ' '.join(content_text.split())
        
        if len(content_text) < 100:
            return jsonify({'success': False, 'error': 'Could not extract sufficient content from the article'}), 400
        
        # Generate concise, scannable summary prioritizing readability
        prompt = f"""Create a tight, scannable executive analysis of this article. Prioritize conciseness and quick comprehension over exhaustive detail.

## EXECUTIVE SUMMARY
**One tight paragraph** capturing the core thesis, main argument, and key takeaway. What's the essential point?

## KEY INSIGHTS
**Bullet-heavy format** - Use clear, scannable bullets (not long paragraphs). For each major insight:
- **Bold the insight/topic** followed by brief context (2-3 sentences max)
- Include specific numbers, dates, percentages when they matter
- Capture frameworks/systems but summarize components (don't break down exhaustively)
- Use quotes sparingly - only for truly significant claims

## STRUCTURED ANALYSIS
Organize into 3-5 clear sections using Roman numerals (I, II, III). For each section:
- **Lead with 1-2 short bullets** summarizing the main points
- Use sub-bullets for details, examples, or supporting evidence
- **Keep paragraphs minimal** - prefer bullets for scannability
- Extract key recommendations, predictions, or actionable items
- Don't repeat what's in Executive Summary

## CONCLUSION
**2-3 concise bullets** covering: final assessment, key implications, and what to remember.

**LENGTH TARGET**: Aim for 40-60% of the original article length. Be comprehensive but tight. Every sentence should earn its place.

**FORMAT PRIORITY**: Scannable > Exhaustive. Use bullets liberally. Break up dense paragraphs. Make it easy to quickly understand the value.

Article Title: {title_text}
Source: {url}
Article Content:
{content_text[:15000]}"""

        # Use Haiku 4.5 for all articles - Sonnet-level quality at 1/3 the cost
        model = "claude-haiku-4-5-20251001"
        print(f"Using Haiku 4.5 for article ({len(content_text)} chars)")

        try:
            response = claude_client.messages.create(
                model=model,
                max_tokens=6000,  # Much higher limit for comprehensive summaries
                messages=[{"role": "user", "content": prompt}]
            )
            
            summary = response.content[0].text
            
        except Exception as e:
            return jsonify({'success': False, 'error': f'Failed to generate summary: {str(e)}'}), 500
        
        # Generate shortened versions
        print(f"Generating shortened summaries (50%, 30%, and 15%)...")
        summary_50 = generate_shortened_summary(summary, 50)
        summary_30 = generate_shortened_summary(summary, 30)
        summary_15 = generate_shortened_summary(summary, 15)
        
        # Save to database
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Create articles table if it doesn't exist
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                content TEXT,
                summary TEXT,
                tags TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Add summary_50, summary_30, and summary_15 columns if they don't exist
        try:
            cursor.execute('ALTER TABLE articles ADD COLUMN summary_50 TEXT')
            conn.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists
        try:
            cursor.execute('ALTER TABLE articles ADD COLUMN summary_30 TEXT')
            conn.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists
        try:
            cursor.execute('ALTER TABLE articles ADD COLUMN summary_15 TEXT')
            conn.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists
        
        # Insert the article
        cursor.execute('''
            INSERT INTO articles (title, url, content, summary, summary_50, summary_30, summary_15, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (title_text, url, content_text[:10000], summary, summary_50, summary_30, summary_15, 'article'))
        
        article_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'article_id': article_id,
            'title': title_text,
            'summary': summary
        })
        
    except requests.RequestException as e:
        return jsonify({'success': False, 'error': f'Failed to fetch article: {str(e)}'}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


def extract_title_from_text(text):
    """Extract a likely title from the first few lines of pasted article text.

    Heuristic: skip short category/label lines, date lines, and bylines.
    The first substantial line (20-200 chars) that looks like a headline is the title.
    """
    import re
    lines = text.strip().split('\n')

    # Patterns to skip: dates, bylines, category labels, section headers
    date_pattern = re.compile(r'^(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d', re.IGNORECASE)
    byline_pattern = re.compile(r'^(By |Written by |Author:|Published|Updated|Edited by)', re.IGNORECASE)
    # Category labels: short, mostly uppercase with separators like · | — or ALL CAPS
    category_pattern = re.compile(r'^[A-Z\s·|—–\-&]{2,30}$')
    # Section headers with pipes: |  SECTION  |  description
    pipe_section_pattern = re.compile(r'^\|.*\|')

    for line in lines[:10]:  # Only check first 10 lines
        line = line.strip()
        if not line:
            continue
        # Skip very short lines (likely labels/categories)
        if len(line) < 20:
            continue
        # Skip category-style lines (short, mostly uppercase with separators)
        if category_pattern.match(line) and len(line) < 40:
            continue
        # Skip pipe-delimited section headers
        if pipe_section_pattern.match(line):
            continue
        # Skip date lines
        if date_pattern.match(line):
            continue
        # Skip bylines
        if byline_pattern.match(line):
            continue
        # Skip lines that are just URLs
        if line.startswith('http://') or line.startswith('https://'):
            continue
        # Skip subtitle-style lines (very short and after we've seen other lines)
        # This looks like a title — truncate if too long
        if len(line) > 200:
            line = line[:197] + '...'
        return line

    return None


@app.route('/api/process-article-text', methods=['POST'])
def process_article_text():
    try:
        data = request.get_json()
        text = data.get('text')
        title = data.get('title', 'Pasted Article')
        url = data.get('url', 'text-input')

        if not text:
            return jsonify({'success': False, 'error': 'Text is required'}), 400

        if len(text) < 100:
            return jsonify({'success': False, 'error': 'Text is too short to process'}), 400

        # Auto-extract title from pasted text if no title was provided
        if title == 'Pasted Article':
            extracted = extract_title_from_text(text)
            if extracted:
                title = extracted
                print(f"Auto-extracted title: {title}")

        # Generate concise, scannable summary prioritizing readability
        prompt = f"""Create a tight, scannable executive analysis of this article. Prioritize conciseness and quick comprehension over exhaustive detail.

## EXECUTIVE SUMMARY
**One tight paragraph** capturing the core thesis, main argument, and key takeaway. What's the essential point?

## KEY INSIGHTS
**Bullet-heavy format** - Use clear, scannable bullets (not long paragraphs). For each major insight:
- **Bold the insight/topic** followed by brief context (2-3 sentences max)
- Include specific numbers, dates, percentages when they matter
- Capture frameworks/systems but summarize components (don't break down exhaustively)
- Use quotes sparingly - only for truly significant claims

## STRUCTURED ANALYSIS
Organize into 3-5 clear sections using Roman numerals (I, II, III). For each section:
- **Lead with 1-2 short bullets** summarizing the main points
- Use sub-bullets for details, examples, or supporting evidence
- **Keep paragraphs minimal** - prefer bullets for scannability
- Extract key recommendations, predictions, or actionable items
- Don't repeat what's in Executive Summary

## CONCLUSION
**2-3 concise bullets** covering: final assessment, key implications, and what to remember.

**LENGTH TARGET**: Aim for 40-60% of the original article length. Be comprehensive but tight. Every sentence should earn its place.

**FORMAT PRIORITY**: Scannable > Exhaustive. Use bullets liberally. Break up dense paragraphs. Make it easy to quickly understand the value.

Article Title: {title}
Source: Pasted Text
Article Content:
{text[:15000]}"""

        # Use Haiku 4.5 for all articles - Sonnet-level quality at 1/3 the cost
        model = "claude-haiku-4-5-20251001"
        print(f"Using Haiku 4.5 for article ({len(text)} chars)")

        try:
            response = claude_client.messages.create(
                model=model,
                max_tokens=6000,  # Much higher limit for comprehensive summaries
                messages=[{"role": "user", "content": prompt}]
            )
            
            summary = response.content[0].text
            
        except Exception as e:
            return jsonify({'success': False, 'error': f'Failed to generate summary: {str(e)}'}), 500
        
        # Generate shortened versions
        print(f"Generating shortened summaries (50%, 30%, and 15%)...")
        summary_50 = generate_shortened_summary(summary, 50)
        summary_30 = generate_shortened_summary(summary, 30)
        summary_15 = generate_shortened_summary(summary, 15)
        
        # Save to database
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Create articles table if it doesn't exist
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                content TEXT,
                summary TEXT,
                tags TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Add summary_50, summary_30, and summary_15 columns if they don't exist
        try:
            cursor.execute('ALTER TABLE articles ADD COLUMN summary_50 TEXT')
            conn.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists
        try:
            cursor.execute('ALTER TABLE articles ADD COLUMN summary_30 TEXT')
            conn.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists
        try:
            cursor.execute('ALTER TABLE articles ADD COLUMN summary_15 TEXT')
            conn.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists
        
        # Insert the article
        cursor.execute('''
            INSERT INTO articles (title, url, content, summary, summary_50, summary_30, summary_15, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (title, url, text[:10000], summary, summary_50, summary_30, summary_15, 'article'))
        
        article_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'article_id': article_id,
            'title': title,
            'summary': summary
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/library')
def get_library():
    """Get all content: videos and articles combined"""
    try:
        # Get videos
        videos = db_service.get_all_videos()
        for video in videos:
            video['content_type'] = 'video'
        
        # Get articles
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Add favorited column if it doesn't exist
        try:
            cursor.execute('ALTER TABLE articles ADD COLUMN favorited INTEGER DEFAULT 0')
            conn.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists
        
        # Add summary_50, summary_30, and summary_15 columns if they don't exist
        try:
            cursor.execute('ALTER TABLE articles ADD COLUMN summary_50 TEXT')
            conn.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists
        try:
            cursor.execute('ALTER TABLE articles ADD COLUMN summary_30 TEXT')
            conn.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists
        try:
            cursor.execute('ALTER TABLE articles ADD COLUMN summary_15 TEXT')
            conn.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists
        
        # Get content_type column if it exists
        # Try to include summary_15, but fall back if column doesn't exist yet
        try:
            cursor.execute('''
                SELECT id, title, url, summary, summary_50, summary_30, summary_15, tags, created_at, COALESCE(favorited, 0) as favorited, COALESCE(content_type, 'article') as content_type, content
                FROM articles
                ORDER BY created_at DESC
            ''')
            has_summary_15 = True
        except sqlite3.OperationalError:
            # summary_15 column doesn't exist yet, try without it
            try:
                cursor.execute('''
                    SELECT id, title, url, summary, summary_50, summary_30, tags, created_at, COALESCE(favorited, 0) as favorited, COALESCE(content_type, 'article') as content_type, content
                    FROM articles
                    ORDER BY created_at DESC
                ''')
                has_summary_15 = False
            except sqlite3.OperationalError:
                # content_type column doesn't exist yet, use default
                cursor.execute('''
                    SELECT id, title, url, summary, summary_50, summary_30, tags, created_at, COALESCE(favorited, 0) as favorited, content
                    FROM articles
                    ORDER BY created_at DESC
                ''')
                has_summary_15 = False
        
        articles = []
        rows = cursor.fetchall()
        for row in rows:
            # Determine column indices based on whether summary_15 exists
            # With summary_15: id, title, url, summary, summary_50, summary_30, summary_15, tags, created_at, favorited, content_type, content
            # Without summary_15: id, title, url, summary, summary_50, summary_30, tags, created_at, favorited, content_type, content
            tags_idx = 7 if has_summary_15 else 6
            created_at_idx = 8 if has_summary_15 else 7
            favorited_idx = 9 if has_summary_15 else 8
            content_type_idx = 10 if has_summary_15 else 9
            content_idx = 11 if has_summary_15 else 10

            # Handle both with and without content_type
            content_type = row[content_type_idx] if len(row) > content_type_idx else 'article'
            article_id = row[0]
            
            # Check if this article is linked to a podcast episode
            episode_id = None
            queue_status = None
            queue_stage = None
            queue_progress = None
            podcast_name = None
            published_at = None
            
            if content_type == 'audio':
                cursor.execute('''
                    SELECT pe.id, pe.published_at, ps.podcast_name
                    FROM podcast_episodes pe
                    JOIN podcast_subscriptions ps ON pe.subscription_id = ps.id
                    WHERE pe.processed_article_id = ?
                    LIMIT 1
                ''', (article_id,))
                episode_row = cursor.fetchone()
                if episode_row:
                    episode_id = episode_row[0]
                    published_at = episode_row[1]  # published_at from podcast_episodes
                    podcast_name = episode_row[2]  # podcast_name from podcast_subscriptions
                    
                    # Check if episode is in the processing queue
                    cursor.execute('''
                        SELECT status, stage, progress_percent 
                        FROM podcast_processing_queue 
                        WHERE episode_id = ? AND status IN ('queued', 'processing', 'pending_retry')
                        ORDER BY queued_at DESC
                        LIMIT 1
                    ''', (episode_id,))
                    queue_row = cursor.fetchone()
                    if queue_row:
                        queue_status = queue_row[0]
                        queue_stage = queue_row[1]
                        queue_progress = queue_row[2]
            
            # Only include articles that have summaries OR are in the queue
            # Filter out articles with no summary and not in queue (failed/unprocessed)
            # Column order depends on whether summary_15 exists
            has_summary = len(row) > 3 and row[3] and row[3].strip()
            is_in_queue = queue_status is not None
            
            if not has_summary and not is_in_queue:
                # Skip articles that have no summary and aren't being processed
                continue
            
            # Format date - prefer published_at for podcasts, otherwise use created_at
            display_date = row[created_at_idx] if len(row) > created_at_idx else 'Unknown date'
            if content_type == 'audio' and published_at:
                # Format published_at date to match video format
                try:
                    from datetime import datetime
                    if isinstance(published_at, str):
                        # Parse ISO format date
                        dt = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
                        display_date = dt.strftime('%b %d, %Y')
                    else:
                        display_date = str(published_at)
                except:
                    display_date = published_at if published_at else (row[created_at_idx] if len(row) > created_at_idx else 'Unknown date')
            
            # Format date for "Processed" display (created_at)
            processed_date = row[created_at_idx] if len(row) > created_at_idx else 'Unknown date'
            try:
                from datetime import datetime
                if isinstance(processed_date, str):
                    dt = datetime.fromisoformat(processed_date.replace('Z', '+00:00'))
                    processed_date = dt.strftime('%b %d, %Y')
            except:
                pass
            
            # Get raw timestamp for sorting (prefer created_at which is always ISO format)
            raw_timestamp = row[created_at_idx] if len(row) > created_at_idx else ''

            articles.append({
                'id': article_id,
                'title': row[1] or 'Untitled Article',
                'url': row[2],
                'ai_summary': row[3] if len(row) > 3 and row[3] and row[3].strip() else None,  # Full summary (None if empty)
                'summary': row[3] if len(row) > 3 and row[3] and row[3].strip() else None,  # Also include full summary (None if empty)
                'summary_50': row[4] if len(row) > 4 and row[4] and row[4].strip() else None,
                'summary_30': row[5] if len(row) > 5 and row[5] and row[5].strip() else None,
                'summary_15': row[6] if has_summary_15 and len(row) > 6 and row[6] and row[6].strip() else None,
                'tags': row[tags_idx] if len(row) > tags_idx else '',
                'date': display_date,  # Published date for podcasts, created_at for articles
                'sort_date': raw_timestamp,  # Raw ISO timestamp for sorting
                'processed_at': processed_date,  # When it was processed
                'published_at': published_at if content_type == 'audio' else None,  # Original published date
                'favorited': bool(row[favorited_idx]) if len(row) > favorited_idx else False,
                'content_type': content_type,
                'channel': podcast_name if (content_type == 'audio' and podcast_name) else ('Newsletter' if content_type == 'newsletter' else ('Article' if content_type == 'article' else 'Audio')),
                'status': 'completed' if has_summary else queue_status or 'processing',
                'episode_id': episode_id,  # Include episode ID if linked
                'queue_status': queue_status,  # queued, processing, pending_retry, etc.
                'queue_stage': queue_stage,  # downloading_audio, transcribing, generating_summary, etc.
                'queue_progress': queue_progress,  # 0-100
                'full_transcript': row[content_idx] if len(row) > content_idx and row[content_idx] else None  # Article full text
            })
        
        conn.close()
        
        # Combine and return
        all_content = videos + articles
        # Sort by sort_date (raw timestamp), most recent first
        all_content.sort(key=lambda x: x.get('sort_date', '') or x.get('date', ''), reverse=True)
        
        return jsonify({
            'success': True,
            'content': all_content,
            'videos_count': len(videos),
            'articles_count': len(articles),
            'total_count': len(all_content)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/articles/<int:article_id>')
def get_article(article_id):
    """Get a single article by ID"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Add previous_summary column if it doesn't exist
        try:
            cursor.execute('ALTER TABLE articles ADD COLUMN previous_summary TEXT')
            conn.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists
        
        # Add summary_50, summary_30, and summary_15 columns if they don't exist
        try:
            cursor.execute('ALTER TABLE articles ADD COLUMN summary_50 TEXT')
            conn.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists
        try:
            cursor.execute('ALTER TABLE articles ADD COLUMN summary_30 TEXT')
            conn.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists
        try:
            cursor.execute('ALTER TABLE articles ADD COLUMN summary_15 TEXT')
            conn.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists
        
        # Get content_type and favorited columns if they exist
        # Try to include summary_15, but fall back if column doesn't exist yet
        try:
            cursor.execute('''
                SELECT id, title, url, content, summary, summary_50, summary_30, summary_15, tags, created_at, previous_summary,
                       COALESCE(content_type, 'article') as content_type,
                       COALESCE(favorited, 0) as favorited
                FROM articles
                WHERE id = ?
            ''', (article_id,))
            has_summary_15 = True
        except sqlite3.OperationalError:
            # summary_15 column doesn't exist yet, try without it
            try:
                cursor.execute('''
                    SELECT id, title, url, content, summary, summary_50, summary_30, tags, created_at, previous_summary,
                           COALESCE(content_type, 'article') as content_type,
                           COALESCE(favorited, 0) as favorited
                    FROM articles
                    WHERE id = ?
                ''', (article_id,))
                has_summary_15 = False
            except sqlite3.OperationalError:
                # Fallback if columns don't exist
                cursor.execute('''
                    SELECT id, title, url, content, summary, summary_50, summary_30, tags, created_at, previous_summary
                    FROM articles
                    WHERE id = ?
                ''', (article_id,))
                has_summary_15 = False
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return jsonify({'success': False, 'error': 'Article not found'}), 404
        
        # Column order depends on whether summary_15 exists
        # With summary_15: id, title, url, content, summary, summary_50, summary_30, summary_15, tags, created_at, previous_summary, content_type, favorited
        # Without summary_15: id, title, url, content, summary, summary_50, summary_30, tags, created_at, previous_summary, content_type, favorited
        tags_idx = 8 if has_summary_15 else 7
        created_at_idx = 9 if has_summary_15 else 8
        previous_summary_idx = 10 if has_summary_15 else 9
        content_type_idx = 11 if has_summary_15 else 10
        favorited_idx = 12 if has_summary_15 else 11
        
        article = {
            'id': row[0],
            'title': row[1],
            'url': row[2],
            'content': row[3],
            'summary': row[4] if len(row) > 4 else None,
            'summary_50': row[5] if len(row) > 5 and row[5] and row[5].strip() else None,
            'summary_30': row[6] if len(row) > 6 and row[6] and row[6].strip() else None,
            'summary_15': row[7] if has_summary_15 and len(row) > 7 and row[7] and row[7].strip() else None,
            'tags': row[tags_idx] if len(row) > tags_idx else '',
            'created_at': row[created_at_idx] if len(row) > created_at_idx else None,
            'previous_summary': row[previous_summary_idx] if len(row) > previous_summary_idx else None,
            'content_type': row[content_type_idx] if len(row) > content_type_idx else 'article',
            'favorited': bool(row[favorited_idx]) if len(row) > favorited_idx else False
        }
        
        # Return HTML page if requested via browser (not API call)
        if request.headers.get('Accept', '').find('text/html') != -1:
            # Render as HTML page
            html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>{article['title']} - Knowledge Studio</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0a0a1a;
            color: #e5e7eb;
            line-height: 1.8;
            padding: 40px;
            max-width: 900px;
            margin: 0 auto;
        }}
        h1 {{
            color: #8b5cf6;
            margin-bottom: 20px;
            font-size: 28px;
        }}
        .content {{
            background: rgba(255, 255, 255, 0.05);
            padding: 30px;
            border-radius: 12px;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }}
        .content h2 {{
            color: #8b5cf6;
            margin-top: 30px;
            margin-bottom: 15px;
        }}
        .content p {{
            margin-bottom: 15px;
        }}
        .content ul, .content ol {{
            margin-left: 30px;
            margin-bottom: 15px;
        }}
        .content li {{
            margin-bottom: 8px;
        }}
        .content strong {{
            color: #fbbf24;
        }}
        .meta {{
            color: #a1a1aa;
            font-size: 14px;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        }}
        a {{
            color: #8b5cf6;
            text-decoration: none;
        }}
        a:hover {{
            text-decoration: underline;
        }}
    </style>
</head>
<body>
    <h1>{article['title']}</h1>
    <div class="meta">
        {'<a href="' + article['url'] + '" target="_blank">🔗 View Source</a>' if article.get('url') and article['url'] != 'text-input' else ''}
        <span style="margin-left: 20px;">📅 {article['created_at']}</span>
    </div>
    <div class="content">
        {article['summary'].replace(chr(10), '<br>').replace('**', '<strong>').replace('**', '</strong>') if article.get('summary') else 'No summary available'}
    </div>
</body>
</html>"""
            return html_content, 200, {'Content-Type': 'text/html; charset=utf-8'}
        
        return jsonify({'success': True, 'article': article})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/notes', methods=['POST'])
def create_note():
    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return jsonify({'success': False, 'error': 'Invalid JSON payload'}), 400
    
    note_text = (data.get('note') or '').strip()
    if not note_text:
        return jsonify({'success': False, 'error': 'Note text is required'}), 400
    
    payload = {
        'user_id': data.get('userId') or data.get('user_id'),
        'note': note_text,
        'video_id': data.get('videoId') or data.get('video_id'),
        'video_title': data.get('videoTitle') or data.get('video_title'),
        'summary_id': data.get('summaryId') or data.get('summary_id'),
        'summary_url': data.get('summaryUrl') or data.get('summary_url'),
        'source_url': data.get('sourceUrl') or data.get('source_url'),
        'channel': data.get('channel'),
        'content_type': data.get('contentType') or data.get('content_type'),
        'captured_at': data.get('capturedAt') or data.get('captured_at') or datetime.utcnow().isoformat()
    }
    
    try:
        saved_note = db_service.save_note(payload)
        return jsonify({'success': True, 'note': saved_note}), 201
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/notes', methods=['GET'])
def list_notes():
    try:
        limit = int(request.args.get('limit', 50))
        offset = int(request.args.get('offset', 0))
    except ValueError:
        return jsonify({'success': False, 'error': 'limit and offset must be integers'}), 400
    
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    
    try:
        notes = db_service.get_notes(limit=limit, offset=offset)
        return jsonify({'success': True, 'notes': notes, 'count': len(notes)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/notes/<int:note_id>', methods=['DELETE'])
def delete_note(note_id):
    """Delete a note"""
    try:
        deleted = db_service.delete_note(note_id)
        if deleted:
            return jsonify({'success': True, 'message': 'Note deleted successfully'})
        else:
            return jsonify({'success': False, 'error': 'Note not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ─── Sparks / Ideas ───────────────────────────────────────────────

@app.route('/api/sparks', methods=['GET'])
def get_sparks():
    """Get all sparks, optionally filtered by status"""
    try:
        status = request.args.get('status')
        conn = db_service.get_connection()
        cursor = conn.cursor()
        if status:
            cursor.execute('SELECT * FROM sparks WHERE status = ? ORDER BY created_at DESC', (status,))
        else:
            cursor.execute('SELECT * FROM sparks ORDER BY created_at DESC')
        rows = cursor.fetchall()
        conn.close()
        sparks = [dict(r) for r in rows]
        return jsonify({'success': True, 'sparks': sparks})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/sparks', methods=['POST'])
def create_spark():
    """Create a new spark/idea"""
    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return jsonify({'success': False, 'error': 'Invalid JSON'}), 400
    content = (data.get('content') or '').strip()
    if not content:
        return jsonify({'success': False, 'error': 'Content is required'}), 400
    tags = (data.get('tags') or '').strip()
    conn = db_service.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO sparks (content, tags) VALUES (?, ?)',
        (content, tags)
    )
    conn.commit()
    spark_id = cursor.lastrowid
    cursor.execute('SELECT * FROM sparks WHERE id = ?', (spark_id,))
    spark = dict(cursor.fetchone())
    conn.close()
    return jsonify({'success': True, 'spark': spark})

@app.route('/api/sparks/<int:spark_id>', methods=['PUT'])
def update_spark(spark_id):
    """Update a spark (content, status, tags)"""
    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return jsonify({'success': False, 'error': 'Invalid JSON'}), 400
    conn = db_service.get_connection()
    cursor = conn.cursor()
    updates = []
    params = []
    if 'content' in data:
        updates.append('content = ?')
        params.append(data['content'].strip())
    if 'status' in data:
        updates.append('status = ?')
        params.append(data['status'])
    if 'tags' in data:
        updates.append('tags = ?')
        params.append(data['tags'])
    if not updates:
        conn.close()
        return jsonify({'success': False, 'error': 'Nothing to update'}), 400
    updates.append("updated_at = CURRENT_TIMESTAMP")
    params.append(spark_id)
    cursor.execute(f"UPDATE sparks SET {', '.join(updates)} WHERE id = ?", params)
    conn.commit()
    if cursor.rowcount == 0:
        conn.close()
        return jsonify({'success': False, 'error': 'Spark not found'}), 404
    cursor.execute('SELECT * FROM sparks WHERE id = ?', (spark_id,))
    spark = dict(cursor.fetchone())
    conn.close()
    return jsonify({'success': True, 'spark': spark})

@app.route('/api/sparks/<int:spark_id>', methods=['DELETE'])
def delete_spark(spark_id):
    """Delete a spark"""
    try:
        conn = db_service.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM sparks WHERE id = ?', (spark_id,))
        conn.commit()
        deleted = cursor.rowcount > 0
        conn.close()
        if deleted:
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Spark not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ─── Highlights ───────────────────────────────────────────────────

@app.route('/api/highlights', methods=['POST'])
def create_highlight():
    """Create a new highlight"""
    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return jsonify({'success': False, 'error': 'Invalid JSON payload'}), 400
    
    highlighted_text = (data.get('highlighted_text') or '').strip()
    if not highlighted_text or len(highlighted_text) < 15:
        return jsonify({'success': False, 'error': 'Highlighted text must be at least 15 characters'}), 400
    
    # Strip markdown/HTML from highlighted text
    import re
    # Remove markdown formatting
    highlighted_text = re.sub(r'\*\*([^*]+)\*\*', r'\1', highlighted_text)  # Bold
    highlighted_text = re.sub(r'\*([^*]+)\*', r'\1', highlighted_text)  # Italic
    highlighted_text = re.sub(r'#+\s*', '', highlighted_text)  # Headers
    highlighted_text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', highlighted_text)  # Links
    # Remove HTML tags
    highlighted_text = re.sub(r'<[^>]+>', '', highlighted_text)
    highlighted_text = highlighted_text.strip()
    
    if len(highlighted_text) < 15:
        return jsonify({'success': False, 'error': 'Highlighted text too short after stripping formatting'}), 400
    
    payload = {
        'user_id': data.get('user_id') or data.get('userId'),
        'video_id': data.get('video_id') or data.get('videoId'),
        'article_id': data.get('article_id') or data.get('articleId'),
        'content_type': data.get('content_type') or data.get('contentType'),
        'highlighted_text': highlighted_text,
        'user_note': (data.get('user_note') or data.get('userNote') or '').strip(),
        'tags': (data.get('tags') or '').strip(),
        'context': data.get('context') or '',
        'source_title': data.get('source_title') or data.get('sourceTitle'),
        'source_url': data.get('source_url') or data.get('sourceUrl'),
        'channel': data.get('channel')
    }
    
    try:
        saved_highlight = db_service.save_highlight(payload)
        return jsonify({'success': True, 'highlight': saved_highlight}), 201
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/highlights', methods=['GET'])
def list_highlights():
    """Get highlights, optionally filtered by tag, video_id, article_id, or favorited status"""
    try:
        tag = request.args.get('tag')
        video_id = request.args.get('video_id')
        article_id = request.args.get('article_id')
        favorited_param = request.args.get('favorited')
        limit = int(request.args.get('limit', 100))
        offset = int(request.args.get('offset', 0))
        # Convert to int if provided
        if video_id:
            video_id = int(video_id)
        if article_id:
            article_id = int(article_id)
        # Parse favorited parameter
        favorited = None
        if favorited_param is not None:
            favorited = favorited_param.lower() in ('true', '1', 'yes')
    except ValueError as e:
        return jsonify({'success': False, 'error': f'Invalid parameter: {str(e)}'}), 400

    limit = max(1, min(limit, 10000))
    offset = max(0, offset)

    try:
        highlights = db_service.get_highlights(tag=tag, video_id=video_id, article_id=article_id, favorited=favorited, limit=limit, offset=offset)
        favorited_count = db_service.get_favorited_highlights_count()
        return jsonify({'success': True, 'highlights': highlights, 'count': len(highlights), 'favorited_count': favorited_count})
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Error in list_highlights: {error_details}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/highlights/<int:highlight_id>', methods=['PUT'])
def update_highlight(highlight_id):
    """Update an existing highlight"""
    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return jsonify({'success': False, 'error': 'Invalid JSON payload'}), 400
    
    payload = {}
    if 'user_note' in data:
        payload['user_note'] = (data.get('user_note') or '').strip()
    if 'tags' in data:
        payload['tags'] = (data.get('tags') or '').strip()
    
    if not payload:
        return jsonify({'success': False, 'error': 'No fields to update'}), 400
    
    try:
        updated = db_service.update_highlight(highlight_id, payload)
        if not updated:
            return jsonify({'success': False, 'error': 'Highlight not found'}), 404
        return jsonify({'success': True, 'highlight': updated})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/highlights/<int:highlight_id>', methods=['DELETE'])
def delete_highlight(highlight_id):
    """Delete a highlight"""
    try:
        deleted = db_service.delete_highlight(highlight_id)
        if not deleted:
            return jsonify({'success': False, 'error': 'Highlight not found'}), 404
        return jsonify({'success': True, 'message': 'Highlight deleted'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/highlights/<int:highlight_id>/favorite', methods=['PUT'])
def toggle_highlight_favorite(highlight_id):
    """Toggle the favorited status of a highlight"""
    try:
        updated = db_service.toggle_highlight_favorite(highlight_id)
        if not updated:
            return jsonify({'success': False, 'error': 'Highlight not found'}), 404
        return jsonify({'success': True, 'highlight': updated, 'favorited': updated.get('favorited', 0)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/highlights/tags', methods=['GET'])
def get_highlight_tags():
    """Get all highlight tags with counts"""
    try:
        tags = db_service.get_highlight_tags()
        # Get count of untagged highlights
        untagged_highlights = db_service.get_highlights(tag='untagged', limit=1, offset=0)
        untagged_count = len([h for h in db_service.get_highlights(limit=1000) if not h.get('tags') or h.get('tags') == ''])
        if untagged_count > 0:
            tags.append({'tag': 'untagged', 'count': untagged_count})
        return jsonify({'success': True, 'tags': tags})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# Bookmarks API endpoints
@app.route('/api/bookmarks', methods=['GET'])
def list_bookmarks():
    """Get bookmarks"""
    try:
        limit = int(request.args.get('limit', 100))
        offset = int(request.args.get('offset', 0))
    except ValueError as e:
        return jsonify({'success': False, 'error': f'Invalid parameter: {str(e)}'}), 400

    limit = max(1, min(limit, 10000))
    offset = max(0, offset)

    try:
        bookmarks = db_service.get_bookmarks(limit=limit, offset=offset)
        return jsonify({'success': True, 'bookmarks': bookmarks, 'count': len(bookmarks)})
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Error in list_bookmarks: {error_details}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/bookmarks/count', methods=['GET'])
def get_bookmark_count():
    """Get total count of bookmarks"""
    try:
        count = db_service.get_bookmark_count()
        return jsonify({'success': True, 'count': count})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/bookmarks', methods=['POST'])
def add_bookmark():
    """Add a new bookmark with optional highlight (for bookmarklet)"""
    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return jsonify({'success': False, 'error': 'Invalid JSON payload'}), 400

    url = (data.get('url') or '').strip()
    title = (data.get('title') or '').strip()
    source = (data.get('source') or '').strip()  # e.g., domain name
    tags = (data.get('tags') or '').strip()
    note = (data.get('note') or '').strip()
    highlight_text = (data.get('highlight') or '').strip()

    if not url:
        return jsonify({'success': False, 'error': 'URL is required'}), 400

    try:
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Check if bookmark already exists
        cursor.execute('SELECT id FROM bookmarks WHERE url = ?', (url,))
        existing = cursor.fetchone()

        bookmark_existed = False
        if existing:
            bookmark_id = existing['id']
            bookmark_existed = True
        else:
            # Insert new bookmark
            cursor.execute('''
                INSERT INTO bookmarks (url, title, source, tags, note, source_url, content_title, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (url, title, source, tags, note, url, title, datetime.now().isoformat()))
            bookmark_id = cursor.lastrowid

        # If highlight text provided, save it
        highlight_id = None
        if highlight_text and len(highlight_text) >= 10:
            cursor.execute('''
                INSERT INTO highlights (highlighted_text, source_url, source_title, channel, bookmark_id, content_type, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (highlight_text, url, title, source, bookmark_id, 'bookmark', datetime.now().isoformat()))
            highlight_id = cursor.lastrowid

        conn.commit()
        conn.close()

        # Build response message
        if highlight_text and len(highlight_text) >= 10:
            if bookmark_existed:
                message = 'Highlight added to existing bookmark!'
            else:
                message = 'Bookmark + highlight saved!'
        else:
            if bookmark_existed:
                return jsonify({'success': False, 'error': 'Already bookmarked', 'duplicate': True, 'bookmark_id': bookmark_id}), 409
            else:
                message = 'Bookmark saved!'

        return jsonify({
            'success': True,
            'bookmark_id': bookmark_id,
            'highlight_id': highlight_id,
            'bookmark_existed': bookmark_existed,
            'message': message
        }), 201

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/bookmarks/<int:bookmark_id>', methods=['DELETE'])
def delete_bookmark(bookmark_id):
    """Delete a bookmark and its associated highlights"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()

        # Check if bookmark exists
        cursor.execute('SELECT id FROM bookmarks WHERE id = ?', (bookmark_id,))
        if not cursor.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': 'Bookmark not found'}), 404

        # Delete associated highlights first
        cursor.execute('DELETE FROM highlights WHERE bookmark_id = ?', (bookmark_id,))
        deleted_highlights = cursor.rowcount

        # Delete the bookmark
        cursor.execute('DELETE FROM bookmarks WHERE id = ?', (bookmark_id,))

        conn.commit()
        conn.close()

        return jsonify({
            'success': True,
            'message': f'Bookmark deleted (and {deleted_highlights} highlight(s))'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# Intelligence API endpoints
@app.route('/api/intelligence', methods=['POST'])
def create_intelligence():
    """Create a new intelligence entry"""
    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return jsonify({'success': False, 'error': 'Invalid JSON payload'}), 400
    
    intelligence_type = (data.get('type') or '').strip().lower()
    title = (data.get('title') or '').strip()
    content = (data.get('content') or '').strip()
    
    if not intelligence_type:
        return jsonify({'success': False, 'error': 'Type is required'}), 400
    if intelligence_type not in ['synthesis', 'prediction', 'script', 'query', 'trends']:
        return jsonify({'success': False, 'error': 'Type must be one of: synthesis, prediction, script, query, trends'}), 400
    if not title:
        return jsonify({'success': False, 'error': 'Title is required'}), 400
    if not content:
        return jsonify({'success': False, 'error': 'Content is required'}), 400
    
    payload = {
        'type': intelligence_type,
        'title': title,
        'content': content,
        'source_video_ids': data.get('source_video_ids') or [],
        'tags': (data.get('tags') or '').strip()
    }
    
    try:
        saved_intelligence = db_service.save_intelligence(payload)
        if not saved_intelligence:
            return jsonify({'success': False, 'error': 'Failed to save intelligence entry'}), 500
        return jsonify({'success': True, 'intelligence': saved_intelligence}), 201
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/intelligence', methods=['GET'])
def list_intelligence():
    """Get intelligence entries, optionally filtered by type"""
    try:
        intelligence_type = request.args.get('type')
        limit = int(request.args.get('limit', 100))
        offset = int(request.args.get('offset', 0))
    except ValueError:
        return jsonify({'success': False, 'error': 'limit and offset must be integers'}), 400
    
    limit = max(1, min(limit, 500))
    offset = max(0, offset)
    
    if intelligence_type and intelligence_type not in ['synthesis', 'prediction', 'script', 'query', 'trends']:
        return jsonify({'success': False, 'error': 'Invalid type'}), 400
    
    try:
        entries = db_service.get_intelligence(intelligence_type=intelligence_type, limit=limit, offset=offset)
        return jsonify({'success': True, 'intelligence': entries, 'count': len(entries)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/intelligence/stats', methods=['GET'])
def get_intelligence_stats():
    """Get statistics for intelligence entries by type"""
    try:
        stats = db_service.get_intelligence_stats()
        return jsonify({'success': True, 'stats': stats})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/intelligence/<int:intelligence_id>', methods=['GET'])
def get_intelligence_by_id(intelligence_id):
    """Get a single intelligence entry by ID"""
    try:
        entry = db_service.get_intelligence_by_id(intelligence_id)
        if not entry:
            return jsonify({'success': False, 'error': 'Intelligence entry not found'}), 404
        return jsonify({'success': True, 'intelligence': entry})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/intelligence/<int:intelligence_id>', methods=['PUT'])
def update_intelligence(intelligence_id):
    """Update an existing intelligence entry"""
    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return jsonify({'success': False, 'error': 'Invalid JSON payload'}), 400
    
    payload = {}
    if 'title' in data:
        payload['title'] = (data.get('title') or '').strip()
    if 'content' in data:
        payload['content'] = (data.get('content') or '').strip()
    if 'tags' in data:
        payload['tags'] = (data.get('tags') or '').strip()
    if 'source_video_ids' in data:
        payload['source_video_ids'] = data.get('source_video_ids') or []
    
    if not payload:
        return jsonify({'success': False, 'error': 'No fields to update'}), 400
    
    try:
        updated = db_service.update_intelligence(intelligence_id, payload)
        if not updated:
            return jsonify({'success': False, 'error': 'Intelligence entry not found'}), 404
        return jsonify({'success': True, 'intelligence': updated})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/intelligence/<int:intelligence_id>', methods=['DELETE'])
def delete_intelligence(intelligence_id):
    """Delete an intelligence entry"""
    try:
        deleted = db_service.delete_intelligence(intelligence_id)
        if not deleted:
            return jsonify({'success': False, 'error': 'Intelligence entry not found'}), 404
        return jsonify({'success': True, 'message': 'Intelligence entry deleted'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/tags/all', methods=['GET'])
def get_all_tags():
    """Get all tags from videos, articles, and highlights (unified)"""
    try:
        tags = db_service.get_all_tags()
        return jsonify({'success': True, 'tags': tags})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/articles/<int:article_id>/regenerate-summary', methods=['POST'])
def regenerate_article_summary(article_id):
    """Regenerate article summary with new prompt while preserving old summary"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Add previous_summary column if it doesn't exist
        try:
            cursor.execute('ALTER TABLE articles ADD COLUMN previous_summary TEXT')
            conn.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists
        
        # Get article with original content
        cursor.execute('''
            SELECT id, title, url, content, summary, tags, content_type
            FROM articles
            WHERE id = ?
        ''', (article_id,))

        row = cursor.fetchone()
        if not row:
            conn.close()
            return jsonify({'success': False, 'error': 'Article not found'}), 404

        article_id_db, title, url, content, old_summary, tags, content_type = row

        if not content:
            conn.close()
            return jsonify({'success': False, 'error': 'No original content available to regenerate from'}), 400

        is_newsletter = (content_type == 'newsletter')

        if is_newsletter:
            newsletter_name = tags or 'Newsletter'
            prompt = f"""Summarize this newsletter issue from "{newsletter_name}".

Title: {title}

Content:
{content[:40000]}

Write a dense, substantive summary that covers ALL major points in the piece — not just the first few in detail.

For each point or section, capture what's SPECIFIC and DISTINCTIVE about it in 1-2 tight sentences. Ask yourself: "Would this line make someone say 'that's interesting' or 'I've heard that before'?" If it's the latter, you've genericized it. Fix it.

Guidelines:
- COVERAGE FIRST: Hit every major argument, prescription, or framework. Don't elaborate on early points at the expense of later ones.
- Be concise but specific. "Adaptability and resilience for wave-surfing careers" beats a paragraph expanding the surfing metaphor. But it also beats "cultivate adaptability" which strips the distinctive framing.
- Keep the author's sharpest lines verbatim when they carry meaning that paraphrase would kill.
- For prescriptions: include the specific actions, not just the category. "Drama, debate club, music lessons" not "develop emotional intelligence." "Ask your child: what do you believe that few others do?" not "encourage uniqueness."
- Preserve concrete examples, named references, numbers, and timelines.
- Cut filler prose, repetition, and setup — keep only the substance underneath.
- Do NOT use generic academic framing like "the author argues" or "key insights include."

Write 500-800 words depending on how much substance the piece contains. Every sentence should carry specific information the reader couldn't guess from the headline."""
            model = "claude-haiku-4-5-20251001"
        else:
            prompt = f"""Create a tight, scannable executive analysis of this article. Prioritize conciseness and quick comprehension over exhaustive detail.

## EXECUTIVE SUMMARY
**One tight paragraph** capturing the core thesis, main argument, and key takeaway. What's the essential point?

## KEY INSIGHTS
**Bullet-heavy format** - Use clear, scannable bullets (not long paragraphs). For each major insight:
- **Bold the insight/topic** followed by brief context (2-3 sentences max)
- Include specific numbers, dates, percentages when they matter
- Capture frameworks/systems but summarize components (don't break down exhaustively)
- Use quotes sparingly - only for truly significant claims

## STRUCTURED ANALYSIS
Organize into 3-5 clear sections using Roman numerals (I, II, III). For each section:
- **Lead with 1-2 short bullets** summarizing the main points
- Use sub-bullets for details, examples, or supporting evidence
- **Keep paragraphs minimal** - prefer bullets for scannability
- Extract key recommendations, predictions, or actionable items
- Don't repeat what's in Executive Summary

## CONCLUSION
**2-3 concise bullets** covering: final assessment, key implications, and what to remember.

**LENGTH TARGET**: Aim for 40-60% of the original article length. Be comprehensive but tight. Every sentence should earn its place.

**FORMAT PRIORITY**: Scannable > Exhaustive. Use bullets liberally. Break up dense paragraphs. Make it easy to quickly understand the value.

Article Title: {title}
Source: {url if url != 'text-input' else 'Pasted Text'}
Article Content:
{content[:15000]}"""
            model = "claude-haiku-4-5-20251001"

        # Generate new summary
        print(f"Regenerating {'newsletter' if is_newsletter else 'article'} summary for: {title}")
        
        try:
            response = claude_client.messages.create(
                model=model,
                max_tokens=6000,
                messages=[{"role": "user", "content": prompt}]
            )
            
            new_summary = response.content[0].text
            
        except Exception as e:
            conn.close()
            return jsonify({'success': False, 'error': f'Failed to generate summary: {str(e)}'}), 500
        
        # Update database: save old summary to previous_summary, update summary with new one
        if is_newsletter:
            # Also regenerate shortened summaries for newsletter content
            print(f"📰 Regenerating shortened summaries...")
            summary_50 = generate_shortened_summary(new_summary, 50)
            summary_30 = generate_shortened_summary(new_summary, 30)
            summary_15 = generate_shortened_summary(new_summary, 15)
            cursor.execute('''
                UPDATE articles
                SET previous_summary = ?, summary = ?, summary_50 = ?, summary_30 = ?, summary_15 = ?
                WHERE id = ?
            ''', (old_summary, new_summary, summary_50, summary_30, summary_15, article_id))
        else:
            cursor.execute('''
                UPDATE articles
                SET previous_summary = ?, summary = ?
                WHERE id = ?
            ''', (old_summary, new_summary, article_id))

        conn.commit()
        conn.close()

        return jsonify({
            'success': True,
            'article_id': article_id,
            'new_summary': new_summary,
            'previous_summary': old_summary,
            'message': 'Summary regenerated. Previous summary preserved for comparison.'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/videos/<int:video_id>', methods=['DELETE'])
def delete_video(video_id):
    """Delete a video"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Check if video exists
        cursor.execute('SELECT id, title FROM videos WHERE id = ?', (video_id,))
        video = cursor.fetchone()
        if not video:
            conn.close()
            return jsonify({'success': False, 'error': 'Video not found'}), 404
        
        # Delete the video
        cursor.execute('DELETE FROM videos WHERE id = ?', (video_id,))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': f'Video "{video[1]}" deleted successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/articles/<int:article_id>/episode-id', methods=['GET'])
def get_episode_id_from_article(article_id):
    """Get podcast episode ID from article ID (if article is linked to a podcast episode)"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # First check if article exists and is audio type
        cursor.execute('''
            SELECT id, content_type FROM articles WHERE id = ?
        ''', (article_id,))
        article_row = cursor.fetchone()
        
        if not article_row:
            conn.close()
            return jsonify({'success': False, 'error': 'Article not found'}), 404
        
        # Check if this article is linked to a podcast episode
        cursor.execute('''
            SELECT id FROM podcast_episodes 
            WHERE processed_article_id = ?
            LIMIT 1
        ''', (article_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return jsonify({'success': True, 'episode_id': row[0]})
        else:
            # Article exists but not linked - this can happen if processing failed
            # Return a more helpful error message
            return jsonify({
                'success': False, 
                'error': 'No podcast episode found for this article. This article may have been created manually or processing failed before linking.'
            }), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/articles/<int:article_id>', methods=['DELETE'])
def delete_article(article_id):
    """Delete an article"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Check if article exists
        cursor.execute('SELECT id FROM articles WHERE id = ?', (article_id,))
        if not cursor.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': 'Article not found'}), 404
        
        # Delete the article
        cursor.execute('DELETE FROM articles WHERE id = ?', (article_id,))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Article deleted successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/status')
def status():
    try:
        videos = db_service.get_all_videos()
        return jsonify({
            'success': True,
            'status': 'running',
            'database_connected': True,
            'videos_count': len(videos),
            'claude_api': 'configured'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# Audio processing storage
audio_processing_status = {}  # {audio_id: {'status': 'processing'|'completed'|'error', 'error': None}}

@app.route('/api/process-audio', methods=['POST'])
def process_audio():
    """Upload audio file and start transcription in background"""
    try:
        if 'audio' not in request.files:
            return jsonify({'success': False, 'error': 'No audio file provided'}), 400
        
        audio_file = request.files['audio']
        if audio_file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'}), 400
        
        # Save file
        filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{audio_file.filename}"
        file_path = os.path.join(AUDIO_FOLDER, filename)
        audio_file.save(file_path)
        
        print(f"🎵 Audio file uploaded: {filename}")
        
        # Create database entry
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Ensure articles table has content_type column
        try:
            cursor.execute('ALTER TABLE articles ADD COLUMN content_type TEXT DEFAULT "article"')
            conn.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists
        
        # Insert placeholder entry
        cursor.execute('''
            INSERT INTO articles (title, url, content, summary, tags, content_type)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (audio_file.filename, file_path, '', '', 'audio', 'audio'))
        
        audio_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        # Mark as processing
        audio_processing_status[audio_id] = {'status': 'processing', 'error': None}
        
        # Start background transcription
        thread = threading.Thread(target=transcribe_audio, args=(audio_id, file_path, filename))
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'success': True,
            'audio_id': audio_id,
            'message': 'Audio uploaded. Transcription in progress...'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

def transcribe_audio(audio_id, file_path, filename):
    """Background thread: Transcribe audio with Whisper and generate summary"""
    try:
        print(f"🎤 Starting transcription for: {filename}")
        
        # Import whisper
        import whisper
        
        # Load medium model (good balance for M4 Pro)
        model = whisper.load_model("medium")
        
        # Transcribe
        print(f"⚙️  Transcribing with Whisper medium model...")
        result = model.transcribe(file_path)
        transcript = result["text"]
        
        print(f"✅ Transcription complete ({len(transcript)} characters)")
        
        # Generate summary using Claude (same prompt as articles)
        prompt = f"""Create a tight, scannable executive analysis of this audio transcript. Prioritize conciseness and quick comprehension over exhaustive detail.

## EXECUTIVE SUMMARY
**One tight paragraph** capturing the core thesis, main argument, and key takeaway. What's the essential point?

## KEY INSIGHTS
**Bullet-heavy format** - Use clear, scannable bullets (not long paragraphs). For each major insight:
- **Bold the insight/topic** followed by brief context (2-3 sentences max)
- Include specific numbers, dates, percentages when they matter
- Capture frameworks/systems but summarize components (don't break down exhaustively)
- Use quotes sparingly - only for truly significant claims

## STRUCTURED ANALYSIS
Organize into 3-5 clear sections using Roman numerals (I, II, III). For each section:
- **Lead with 1-2 short bullets** summarizing the main points
- Use sub-bullets for details, examples, or supporting evidence
- **Keep paragraphs minimal** - prefer bullets for scannability
- Extract key recommendations, predictions, or actionable items
- Don't repeat what's in Executive Summary

## CONCLUSION
**2-3 concise bullets** covering: final assessment, key implications, and what to remember.

**LENGTH TARGET**: Aim for 40-60% of the original transcript length. Be comprehensive but tight. Every sentence should earn its place.

**FORMAT PRIORITY**: Scannable > Exhaustive. Use bullets liberally. Break up dense paragraphs. Make it easy to quickly understand the value.

Audio Title: {filename}
Transcript:
{transcript[:15000]}"""
        
        print(f"🤖 Generating summary with Claude Haiku 4.5...")
        response = claude_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=6000,
            messages=[{"role": "user", "content": prompt}]
        )
        
        summary = response.content[0].text
        
        # Update database
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE articles
            SET title = ?, content = ?, summary = ?
            WHERE id = ?
        ''', (filename, transcript[:50000], summary, audio_id))
        conn.commit()
        conn.close()
        
        # Mark as completed
        audio_processing_status[audio_id] = {'status': 'completed', 'error': None}
        print(f"✅ Audio processing complete for ID: {audio_id}")
        
    except Exception as e:
        print(f"❌ Error processing audio {audio_id}: {str(e)}")
        audio_processing_status[audio_id] = {'status': 'error', 'error': str(e)}
        
        # Update database with error
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE articles
                SET summary = ?
                WHERE id = ?
            ''', (f"Error processing audio: {str(e)}", audio_id))
            conn.commit()
            conn.close()
        except:
            pass

@app.route('/api/process-audio-url', methods=['POST'])
def process_audio_url():
    """Process audio from URL (podcast, audio file, YouTube audio, etc.)"""
    try:
        data = request.get_json()
        audio_url = data.get('url')
        
        if not audio_url:
            return jsonify({'success': False, 'error': 'URL is required'}), 400
        
        print(f"🎵 Processing audio from URL: {audio_url}")
        
        # Create database entry first
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Ensure articles table has content_type column
        try:
            cursor.execute('ALTER TABLE articles ADD COLUMN content_type TEXT DEFAULT "article"')
            conn.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists
        
        # Extract title from URL (fallback to URL itself)
        try:
            from urllib.parse import urlparse
            parsed = urlparse(audio_url)
            title = parsed.path.split('/')[-1] or parsed.netloc or audio_url
        except:
            title = audio_url
        
        # Insert placeholder entry with original URL
        cursor.execute('''
            INSERT INTO articles (title, url, content, summary, tags, content_type)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (title, audio_url, '', '', 'audio', 'audio'))
        
        audio_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        # Mark as processing
        audio_processing_status[audio_id] = {'status': 'processing', 'error': None}
        
        # Start background processing
        thread = threading.Thread(target=process_audio_from_url, args=(audio_id, audio_url, title))
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'success': True,
            'audio_id': audio_id,
            'message': 'Audio URL processing started. Transcription in progress...'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

def process_audio_from_url(audio_id, audio_url, title):
    """Background thread: Download audio from URL, transcribe, and generate summary"""
    try:
        print(f"🎤 Starting audio processing from URL: {audio_url}")
        
        # Download audio using yt-dlp (same system as videos)
        import yt_dlp
        import tempfile
        
        # Create temp file for audio
        temp_dir = tempfile.mkdtemp()
        temp_audio_path = os.path.join(temp_dir, f"audio_{audio_id}.%(ext)s")
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': temp_audio_path,
            'quiet': True,
            'no_warnings': True,
            'extractaudio': True,
            'audioformat': 'mp3',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }
        
        print(f"⬇️  Downloading audio from URL...")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(audio_url, download=True)
            # Find the downloaded file
            downloaded_files = [f for f in os.listdir(temp_dir) if f.startswith(f"audio_{audio_id}")]
            if not downloaded_files:
                raise Exception("Failed to download audio file")
            downloaded_file = os.path.join(temp_dir, downloaded_files[0])
        
        print(f"✅ Audio downloaded: {downloaded_file}")
        
        # Transcribe using Whisper (same as file upload)
        import whisper
        model = whisper.load_model("medium")
        print(f"⚙️  Transcribing with Whisper medium model...")
        result = model.transcribe(downloaded_file)
        transcript = result["text"]
        
        print(f"✅ Transcription complete ({len(transcript)} characters)")
        
        # Clean up temp file
        try:
            os.unlink(downloaded_file)
            os.rmdir(temp_dir)
        except:
            pass
        
        # Generate summary using Claude (same prompt as articles)
        prompt = f"""Create a tight, scannable executive analysis of this audio transcript. Prioritize conciseness and quick comprehension over exhaustive detail.

## EXECUTIVE SUMMARY
**One tight paragraph** capturing the core thesis, main argument, and key takeaway. What's the essential point?

## KEY INSIGHTS
**Bullet-heavy format** - Use clear, scannable bullets (not long paragraphs). For each major insight:
- **Bold the insight/topic** followed by brief context (2-3 sentences max)
- Include specific numbers, dates, percentages when they matter
- Capture frameworks/systems but summarize components (don't break down exhaustively)
- Use quotes sparingly - only for truly significant claims

## STRUCTURED ANALYSIS
Organize into 3-5 clear sections using Roman numerals (I, II, III). For each section:
- **Lead with 1-2 short bullets** summarizing the main points
- Use sub-bullets for details, examples, or supporting evidence
- **Keep paragraphs minimal** - prefer bullets for scannability
- Extract key recommendations, predictions, or actionable items
- Don't repeat what's in Executive Summary

## CONCLUSION
**2-3 concise bullets** covering: final assessment, key implications, and what to remember.

**LENGTH TARGET**: Aim for 40-60% of the original transcript length. Be comprehensive but tight. Every sentence should earn its place.

**FORMAT PRIORITY**: Scannable > Exhaustive. Use bullets liberally. Break up dense paragraphs. Make it easy to quickly understand the value.

Audio Title: {title}
Source: {audio_url}
Transcript:
{transcript[:15000]}"""
        
        print(f"🤖 Generating summary with Claude Haiku 4.5...")
        response = claude_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=6000,
            messages=[{"role": "user", "content": prompt}]
        )
        
        summary = response.content[0].text
        
        # Update database with transcript, summary, and keep original URL
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE articles
            SET title = ?, content = ?, summary = ?
            WHERE id = ?
        ''', (title, transcript[:50000], summary, audio_id))
        conn.commit()
        conn.close()
        
        # Mark as completed
        audio_processing_status[audio_id] = {'status': 'completed', 'error': None}
        print(f"✅ Audio processing complete for ID: {audio_id}")
        
    except Exception as e:
        print(f"❌ Error processing audio URL {audio_id}: {str(e)}")
        audio_processing_status[audio_id] = {'status': 'error', 'error': str(e)}
        
        # Update database with error
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE articles
                SET summary = ?
                WHERE id = ?
            ''', (f"Error processing audio: {str(e)}", audio_id))
            conn.commit()
            conn.close()
        except:
            pass

@app.route('/api/audio/<int:audio_id>/status', methods=['GET'])
def get_audio_status(audio_id):
    """Get processing status for audio file"""
    if audio_id not in audio_processing_status:
        return jsonify({'status': 'not_found', 'error': 'Audio ID not found'}), 404
    
    status_info = audio_processing_status[audio_id]
    return jsonify({
        'status': status_info['status'],
        'error': status_info.get('error')
    })

@app.route('/api/generate-audio/<content_type>/<int:item_id>', methods=['POST'])
def generate_audio(content_type, item_id):
    """Generate audio from summary or full content with Claude rewrite and OpenAI TTS"""
    try:
        # Get mode and model from request
        data = request.get_json() or {}
        mode = data.get('mode', 'summary')  # 'summary' or 'full'
        tts_model = data.get('tts_model', 'tts-1')  # 'tts-1' (standard) or 'tts-1-hd' (HD)
        
        # Get OpenAI API key (will be set by user)
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            return jsonify({'success': False, 'error': 'OpenAI API key not configured. Please add OPENAI_API_KEY to your .env file'}), 400
        
        # Get content from database
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        if content_type == 'video':
            cursor.execute('''
                SELECT title, channel, ai_summary, processing_date
                FROM videos
                WHERE id = ? AND status = 'completed'
            ''', (item_id,))
            row = cursor.fetchone()
            if not row:
                conn.close()
                return jsonify({'success': False, 'error': 'Video not found'}), 404
            title, author, summary, date = row
            if not summary:
                conn.close()
                return jsonify({'success': False, 'error': 'No summary available for this video'}), 400
            full_content = None  # Videos don't have separate full content field
        elif content_type == 'article' or content_type == 'audio':
            if mode == 'full':
                cursor.execute('''
                    SELECT title, url, content, summary, created_at
                    FROM articles
                    WHERE id = ?
                ''', (item_id,))
                row = cursor.fetchone()
                if not row:
                    conn.close()
                    return jsonify({'success': False, 'error': 'Article not found'}), 404
                title, url, full_content, summary, date = row
                if not full_content:
                    conn.close()
                    return jsonify({'success': False, 'error': 'No full content available for this article'}), 400
            else:
                cursor.execute('''
                    SELECT title, url, summary, created_at
                    FROM articles
                    WHERE id = ?
                ''', (item_id,))
                row = cursor.fetchone()
                if not row:
                    conn.close()
                    return jsonify({'success': False, 'error': 'Article not found'}), 404
                title, url, summary, date = row
                full_content = None
                if not summary:
                    conn.close()
                    return jsonify({'success': False, 'error': 'No summary available for this article'}), 400
            author = url if url and url != 'text-input' else 'Pasted Article'
        else:
            conn.close()
            return jsonify({'success': False, 'error': 'Invalid content type'}), 400
        
        conn.close()
        
        # Step 1: Claude rewrite for conversational tone
        if mode == 'full' and full_content:
            print(f"🎙️  Rewriting full content for audio (word-for-word mode): {title}")
            rewrite_prompt = f"""Convert this full article content into a natural, conversational narration suitable for audio playback.

IMPORTANT: Keep the content word-for-word. Only make minimal conversational tweaks - add brief transitional phrases where helpful (like "So here's the thing" or "Here's what's interesting"), but preserve ALL the original content, all details, all information. Don't summarize, don't condense, don't skip anything. Just make it flow slightly better when spoken while keeping it essentially word-for-word.

Original Content:
{full_content[:50000]}

Provide the conversational version (keeping it word-for-word):"""
            source_text = full_content
        else:
            print(f"🎙️  Rewriting summary for audio: {title}")
            rewrite_prompt = f"""Convert this summary into a natural, conversational narration suitable for audio playback. 

Make it sound like someone explaining this to you, not reading a document. Add brief transitional phrases where helpful (like "So here's the thing" or "Here's what's interesting"). Keep all key points and structure intact - don't add fluff or change meaning. Just make it flow better when spoken.

Original Summary:
{summary[:15000]}

Provide the conversational version:"""
            source_text = summary
        
        rewrite_response = claude_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=6000,
            messages=[{"role": "user", "content": rewrite_prompt}]
        )
        
        conversational_text = rewrite_response.content[0].text
        print(f"✅ Claude rewrite complete ({len(conversational_text)} chars)")
        
        # Step 2: Generate audio with OpenAI TTS
        print(f"🔊 Generating audio with OpenAI TTS...")
        try:
            from openai import OpenAI
            import subprocess
            import tempfile
            openai_client = OpenAI(api_key=openai_api_key)
            
            # Handle long text by splitting if needed (OpenAI TTS limit is 4096 chars)
            if len(conversational_text) > 4000:
                # Split into chunks of 4000 chars
                text_chunks = []
                for i in range(0, len(conversational_text), 4000):
                    chunk = conversational_text[i:i+4000]
                    text_chunks.append(chunk)
                
                print(f"📦 Splitting into {len(text_chunks)} chunks for TTS (total: {len(conversational_text)} chars)")
                
                # Generate TTS for each chunk
                temp_audio_files = []
                for idx, chunk in enumerate(text_chunks):
                    print(f"  Generating chunk {idx + 1}/{len(text_chunks)} with {tts_model}...")
                    response = openai_client.audio.speech.create(
                        model=tts_model,
                        voice="alloy",
                        input=chunk
                    )
                    
                    # Save to temp file
                    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3')
                    with open(temp_file.name, 'wb') as f:
                        for data in response.iter_bytes():
                            f.write(data)
                    temp_audio_files.append(temp_file.name)
                
                # Combine all chunks using ffmpeg
                print(f"🔗 Combining {len(temp_audio_files)} audio chunks...")
                model_suffix = "hd" if tts_model == "tts-1-hd" else "std"
                filename = f"{item_id}_{content_type}_{model_suffix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp3"
                
                # Save to iCloud Drive if available, otherwise save locally
                if ICLOUD_PODCASTS_FOLDER and os.path.exists(ICLOUD_PODCASTS_FOLDER):
                    file_path = os.path.join(ICLOUD_PODCASTS_FOLDER, filename)
                    print(f"📱 Saving to iCloud Drive (will auto-sync to iPhone)")
                else:
                    file_path = os.path.join(AUDIO_GENERATED_FOLDER, filename)
                    print(f"💾 Saving locally (iCloud folder not available)")
                
                # Create ffmpeg concat file
                concat_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt')
                for temp_file in temp_audio_files:
                    concat_file.write(f"file '{temp_file}'\n")
                concat_file.close()
                
                # Use ffmpeg to concatenate
                try:
                    subprocess.run([
                        'ffmpeg', '-y', '-f', 'concat', '-safe', '0',
                        '-i', concat_file.name, '-c', 'copy', file_path
                    ], check=True, capture_output=True)
                    print(f"✅ Combined audio generated: {filename}")
                except (subprocess.CalledProcessError, FileNotFoundError) as e:
                    print(f"⚠️  ffmpeg not available or failed, using first chunk only: {e}")
                    # Fallback: just use first chunk
                    import shutil
                    shutil.copy(temp_audio_files[0], file_path)
                
                # Clean up temp files
                for temp_file in temp_audio_files:
                    try:
                        os.unlink(temp_file)
                    except:
                        pass
                try:
                    os.unlink(concat_file.name)
                except:
                    pass
            else:
                # Single chunk - no need to combine
                print(f"🔊 Generating audio with {tts_model}...")
                response = openai_client.audio.speech.create(
                    model=tts_model,
                    voice="alloy",  # Options: alloy, echo, fable, onyx, nova, shimmer
                    input=conversational_text
                )
                
                # Save audio file (include model in filename for easy identification)
                model_suffix = "hd" if tts_model == "tts-1-hd" else "std"
                filename = f"{item_id}_{content_type}_{model_suffix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp3"
                
                # Save to iCloud Drive if available, otherwise save locally
                if ICLOUD_PODCASTS_FOLDER and os.path.exists(ICLOUD_PODCASTS_FOLDER):
                    file_path = os.path.join(ICLOUD_PODCASTS_FOLDER, filename)
                    print(f"📱 Saving to iCloud Drive (will auto-sync to iPhone)")
                else:
                    file_path = os.path.join(AUDIO_GENERATED_FOLDER, filename)
                    print(f"💾 Saving locally (iCloud folder not available)")
                
                with open(file_path, 'wb') as f:
                    for chunk in response.iter_bytes():
                        f.write(chunk)
                
                print(f"✅ Audio generated: {filename}")
            
            # Step 3: Add ID3 metadata
            try:
                from mutagen.id3 import ID3, TIT2, TPE1, TALB, TDRC, TCON, TDES
                from mutagen.mp3 import MP3
                
                audio_file = MP3(file_path, ID3=ID3())
                
                # Add metadata
                audio_file.tags.add(TIT2(encoding=3, text=title[:100]))  # Title
                audio_file.tags.add(TPE1(encoding=3, text=str(author)[:100]))  # Artist/Author
                audio_file.tags.add(TALB(encoding=3, text="Knowledge Studio Audio"))  # Album
                audio_file.tags.add(TDES(encoding=3, text=summary[:500] if summary else ""))  # Description
                if date:
                    try:
                        date_obj = datetime.strptime(date, '%Y-%m-%d %H:%M:%S') if isinstance(date, str) else date
                        audio_file.tags.add(TDRC(encoding=3, text=str(date_obj.year)))
                    except:
                        pass
                audio_file.tags.add(TCON(encoding=3, text="Podcast"))
                
                audio_file.save()
                print(f"✅ ID3 metadata added")
            except ImportError:
                print("⚠️  mutagen not installed - skipping ID3 tags. Install with: pip install mutagen")
            except Exception as e:
                print(f"⚠️  Error adding ID3 tags: {e}")
            
            # Check if saved to iCloud
            saved_to_icloud = ICLOUD_PODCASTS_FOLDER and os.path.exists(ICLOUD_PODCASTS_FOLDER) and file_path.startswith(ICLOUD_PODCASTS_FOLDER)
            
            return jsonify({
                'success': True,
                'audio_url': f'/api/audio/download/{filename}',
                'filename': filename,
                'title': title,
                'saved_to_icloud': saved_to_icloud,
                'file_path': file_path,
                'tts_model': tts_model,
                'estimated_cost': f"${(len(conversational_text) / 1_000_000) * (15 if tts_model == 'tts-1' else 30):.2f}"
            })
            
        except ImportError:
            return jsonify({'success': False, 'error': 'OpenAI library not installed. Install with: pip install openai'}), 500
        except Exception as e:
            print(f"❌ Error generating audio: {e}")
            return jsonify({'success': False, 'error': f'Error generating audio: {str(e)}'}), 500
        
    except Exception as e:
        print(f"❌ Error in generate_audio: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/queue', methods=['GET'])
def get_processing_queue():
    """Get processing queue items and state. Optionally include recently processed items from main tables."""
    status = request.args.get('status')
    limit = request.args.get('limit', type=int)
    include_recent = request.args.get('include_recent', 'false').lower() == 'true'
    
    try:
        items = processor.get_queue_items(status=status, limit=limit)
        
        # If include_recent is true, also get recently processed items from videos/articles tables
        if include_recent:
            from datetime import datetime, timedelta
            conn = sqlite3.connect(DATABASE_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Get recent videos (last 48 hours)
            forty_eight_hours_ago = datetime.now() - timedelta(hours=48)
            cursor.execute('''
                SELECT id, title, video_url, processing_date as completed_at, 'completed' as status, NULL as queued_at, NULL as started_at
                FROM videos
                WHERE processing_date >= ?
                ORDER BY processing_date DESC
                LIMIT 20
            ''', (forty_eight_hours_ago,))
            recent_videos = cursor.fetchall()
            
            # Get recent articles (last 48 hours)
            cursor.execute('''
                SELECT id, title, url as video_url, created_at as completed_at, 'completed' as status, NULL as queued_at, NULL as started_at
                FROM articles
                WHERE created_at >= ?
                ORDER BY created_at DESC
                LIMIT 20
            ''', (forty_eight_hours_ago,))
            recent_articles = cursor.fetchall()
            
            conn.close()
            
            # Convert to dict format and add to items
            for row in recent_videos:
                item = dict(row)
                item['video_id'] = f"video_{item['id']}"
                items.append(item)
            
            for row in recent_articles:
                item = dict(row)
                item['video_id'] = f"article_{item['id']}"
                items.append(item)
        
        state = processor.get_queue_state()
        return jsonify({'success': True, 'queue': items, 'state': state})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/queue/add', methods=['POST'])
def add_to_processing_queue():
    """Add one or more videos to the processing queue."""
    try:
        data = request.get_json(force=True, silent=False) or {}
    except Exception:
        return jsonify({'success': False, 'error': 'Invalid JSON payload'}), 400
    
    videos = data.get('videos')
    if not videos:
        # Support single video payload
        video_url = data.get('video_url') or data.get('url')
        if not video_url:
            return jsonify({'success': False, 'error': 'Missing video_url or videos payload'}), 400
        videos = [data]
    
    try:
        result = processor.add_videos_to_queue(videos)
        state = processor.get_queue_state()
        return jsonify({
            'success': True,
            'added': result['added'],
            'errors': result['errors'],
            'state': state
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/queue/<int:item_id>', methods=['DELETE'])
def delete_queue_item(item_id):
    """Remove a queue item if possible."""
    try:
        removed = processor.remove_queue_item(item_id)
        if not removed:
            return jsonify({'success': False, 'error': 'Queue item not found'}), 404
        state = processor.get_queue_state()
        return jsonify({'success': True, 'state': state})
    except ValueError as ve:
        return jsonify({'success': False, 'error': str(ve)}), 409
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/queue/<int:item_id>/retry', methods=['POST'])
def retry_queue_item(item_id):
    """Requeue a failed/completed queue item."""
    try:
        item = processor.retry_queue_item(item_id)
        state = processor.get_queue_state()
        return jsonify({'success': True, 'item': item, 'state': state})
    except ValueError as ve:
        return jsonify({'success': False, 'error': str(ve)}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/queue/pause', methods=['POST'])
def pause_queue():
    """Pause the processing queue."""
    try:
        state = processor.set_queue_paused(True)
        return jsonify({'success': True, 'state': state})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/queue/resume', methods=['POST'])
def resume_queue():
    """Resume the processing queue."""
    try:
        state = processor.set_queue_paused(False)
        return jsonify({'success': True, 'state': state})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/audio/download/<filename>', methods=['GET'])
def download_audio(filename):
    """Download generated audio file"""
    try:
        # Check iCloud folder first, then local folder
        file_path = None
        if ICLOUD_PODCASTS_FOLDER and os.path.exists(ICLOUD_PODCASTS_FOLDER):
            icloud_path = os.path.join(ICLOUD_PODCASTS_FOLDER, filename)
            if os.path.exists(icloud_path):
                file_path = icloud_path
        
        if not file_path:
            file_path = os.path.join(AUDIO_GENERATED_FOLDER, filename)
        
        if not os.path.exists(file_path):
            return jsonify({'success': False, 'error': 'Audio file not found'}), 404
        
        return send_file(file_path, as_attachment=True, download_name=filename)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/subscriptions', methods=['GET'])
def list_subscriptions():
    """List channel subscriptions."""
    try:
        subs = processor.list_subscriptions()
        return jsonify({'success': True, 'subscriptions': subs})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/subscriptions', methods=['POST'])
def add_subscription():
    """Add a new channel subscription."""
    data = request.get_json(force=True)
    channel_input = data.get('channel') or data.get('channel_url') or data.get('channel_id')
    if not channel_input:
        return jsonify({'success': False, 'error': 'Missing channel information'}), 400
    try:
        subscription = processor.add_subscription(channel_input)
        return jsonify({'success': True, 'subscription': subscription})
    except ValueError as ve:
        return jsonify({'success': False, 'error': str(ve)}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/subscriptions/<int:subscription_id>', methods=['DELETE'])
def delete_subscription(subscription_id):
    """Delete a channel subscription."""
    try:
        removed = processor.remove_subscription(subscription_id)
        if not removed:
            return jsonify({'success': False, 'error': 'Subscription not found'}), 404
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/subscriptions/<int:subscription_id>/toggle', methods=['POST'])
def toggle_subscription(subscription_id):
    """Enable or disable a channel subscription."""
    try:
        subscription = processor.toggle_subscription(subscription_id)
        return jsonify({'success': True, 'subscription': subscription})
    except ValueError as ve:
        return jsonify({'success': False, 'error': str(ve)}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/subscriptions/<int:subscription_id>/refresh', methods=['POST'])
def refresh_subscription(subscription_id):
    """Refresh channel videos for a subscription."""
    max_results = None
    history_months = None
    history_max = None
    if request.is_json:
        payload = request.get_json(silent=True) or {}
        max_results = payload.get('max_results')
        history_months = payload.get('history_months')
        history_max = payload.get('history_max')
    if history_months is not None:
        try:
            history_months = int(history_months)
        except (TypeError, ValueError):
            history_months = None
    if history_max is not None:
        try:
            history_max = int(history_max)
        except (TypeError, ValueError):
            history_max = None
    try:
        result = processor.refresh_subscription(
            subscription_id,
            max_results=max_results,
            history_months=history_months,
            history_max=history_max
        )

        # Auto-add new videos to podcast if channel is podcast-enabled
        try:
            channel_name = result.get('channel_name') if isinstance(result, dict) else None
            if not channel_name:
                # Look up channel name from subscription
                sub_info = processor.get_subscription(subscription_id) if hasattr(processor, 'get_subscription') else None
                if sub_info:
                    channel_name = sub_info.get('channel_name')
            if channel_name:
                _conn = sqlite3.connect(DATABASE_PATH)
                _cur = _conn.cursor()
                _cur.execute('SELECT id FROM yt_podcast_channel_feeds WHERE channel_name = ? AND enabled = 1',
                             (channel_name,))
                if _cur.fetchone():
                    _conn.close()
                    thread = threading.Thread(target=_auto_add_channel_videos_to_podcast, args=(channel_name,))
                    thread.daemon = True
                    thread.start()
                else:
                    _conn.close()
        except Exception as podcast_err:
            print(f"⚠️  Podcast auto-add check failed: {podcast_err}")

        return jsonify({'success': True, 'result': result})
    except ValueError as ve:
        return jsonify({'success': False, 'error': str(ve)}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/subscriptions/cleanup-shorts', methods=['POST'])
def cleanup_shorts():
    """Remove all YouTube Shorts from subscribed channels."""
    try:
        result = processor.cleanup_shorts_from_subscriptions()
        return jsonify({
            'success': True,
            'removed': result.get('removed', 0),
            'checked': result.get('checked', 0),
            'shorts_found': result.get('shorts_found', 0)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# Global flag to prevent concurrent refresh-all operations
_refresh_all_in_progress = False

@app.route('/api/refresh-all-feeds', methods=['POST'])
def refresh_all_feeds():
    """Refresh all subscriptions: YouTube channels, newsletters, and podcasts."""
    global _refresh_all_in_progress

    if _refresh_all_in_progress:
        return jsonify({
            'success': False,
            'error': 'Refresh already in progress. Please wait.'
        }), 409

    _refresh_all_in_progress = True
    results = {
        'youtube': {'refreshed': 0, 'errors': 0, 'new_videos': 0},
        'newsletters': {'refreshed': 0, 'errors': 0, 'new_issues': 0},
        'podcasts': {'refreshed': 0, 'errors': 0, 'new_episodes': 0}
    }

    try:
        import time

        # Refresh YouTube subscriptions
        try:
            youtube_subs = processor.list_subscriptions()
            for sub in youtube_subs:
                try:
                    result = processor.refresh_subscription(sub['id'], max_results=20)
                    results['youtube']['refreshed'] += 1
                    results['youtube']['new_videos'] += result.get('new_videos', 0)
                    # Auto-add to podcast if channel is podcast-enabled
                    # Always check (not just when new_videos > 0) since videos might exist
                    # but not yet be in podcast feed; the auto-add function handles duplicates
                    try:
                        ch_name = sub.get('channel_name')
                        if ch_name:
                            _pconn = sqlite3.connect(DATABASE_PATH)
                            _pcur = _pconn.cursor()
                            _pcur.execute('SELECT id FROM yt_podcast_channel_feeds WHERE channel_name = ? AND enabled = 1', (ch_name,))
                            if _pcur.fetchone():
                                _pconn.close()
                                _auto_add_channel_videos_to_podcast(ch_name)
                            else:
                                _pconn.close()
                    except Exception as pe:
                        print(f"⚠️  Podcast auto-add error for {sub.get('channel_name')}: {pe}")
                    time.sleep(0.5)  # Small delay to avoid rate limiting
                except Exception as e:
                    print(f"Error refreshing YouTube sub {sub.get('channel_name')}: {e}")
                    results['youtube']['errors'] += 1
        except Exception as e:
            print(f"Error getting YouTube subscriptions: {e}")

        # Refresh newsletter subscriptions
        try:
            import feedparser
            newsletter_subs = db_service.list_newsletter_subscriptions()
            for sub in newsletter_subs:
                try:
                    feed_url = sub.get('feed_url')
                    if not feed_url:
                        continue

                    feed = feedparser.parse(feed_url)
                    new_count = 0

                    for entry in feed.entries[:50]:
                        issue_guid = entry.get('id') or entry.get('link') or entry.get('title')
                        title = entry.get('title', 'Untitled')
                        description = entry.get('summary') or entry.get('description')
                        issue_url = entry.get('link')
                        published = entry.get('published') or entry.get('updated')

                        result = db_service.add_newsletter_issue(
                            subscription_id=sub['id'],
                            issue_guid=issue_guid,
                            title=title,
                            description=description,
                            issue_url=issue_url,
                            published_at=published
                        )
                        if result:
                            new_count += 1

                    db_service.update_newsletter_last_checked(sub['id'])
                    results['newsletters']['refreshed'] += 1
                    results['newsletters']['new_issues'] += new_count
                    time.sleep(0.3)
                except Exception as e:
                    print(f"Error refreshing newsletter {sub.get('newsletter_name')}: {e}")
                    results['newsletters']['errors'] += 1
        except Exception as e:
            print(f"Error getting newsletter subscriptions: {e}")

        # Refresh podcast subscriptions
        try:
            podcast_subs = podcast_processor.list_subscriptions()
            for sub in podcast_subs:
                try:
                    result = podcast_processor.refresh_subscription(sub['id'], max_results=20)
                    results['podcasts']['refreshed'] += 1
                    results['podcasts']['new_episodes'] += result.get('new_episodes', 0)
                    time.sleep(0.3)
                except Exception as e:
                    print(f"Error refreshing podcast {sub.get('podcast_name')}: {e}")
                    results['podcasts']['errors'] += 1
        except Exception as e:
            print(f"Error getting podcast subscriptions: {e}")

        return jsonify({
            'success': True,
            'results': results,
            'summary': {
                'total_refreshed': results['youtube']['refreshed'] + results['newsletters']['refreshed'] + results['podcasts']['refreshed'],
                'total_errors': results['youtube']['errors'] + results['newsletters']['errors'] + results['podcasts']['errors'],
                'new_content': results['youtube']['new_videos'] + results['newsletters']['new_issues'] + results['podcasts']['new_episodes']
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        _refresh_all_in_progress = False

@app.route('/api/channel-videos', methods=['GET'])
def list_channel_videos():
    """List channel videos with optional filters."""
    channel_id = request.args.get('channel_id')
    processed_param = request.args.get('processed')
    search_term = request.args.get('q')
    if search_term is not None:
        search_term = search_term.strip()
        if not search_term:
            search_term = None
    processed = None
    if processed_param is not None:
        processed = processed_param.lower() in ('1', 'true', 'yes')
    limit = request.args.get('limit', default=50, type=int)
    offset = request.args.get('offset', default=0, type=int)
    order = request.args.get('order', default='desc')
    try:
        videos = processor.get_channel_videos(
            channel_id=channel_id,
            processed=processed,
            limit=limit,
            offset=offset,
            order=order,
            search_term=search_term
        )
        return jsonify({'success': True, 'data': videos})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/channel-videos/queue', methods=['POST'])
def queue_channel_videos():
    """Queue channel videos for processing."""
    data = request.get_json(force=True)
    video_ids = data.get('video_ids') or data.get('videos') or []
    if isinstance(video_ids, dict):
        video_ids = [video_ids.get('video_id')]
    if isinstance(video_ids, str):
        video_ids = [video_ids]
    if not isinstance(video_ids, list):
        return jsonify({'success': False, 'error': 'Invalid video_ids payload'}), 400
    video_ids = [vid for vid in video_ids if vid]
    if not video_ids:
        return jsonify({'success': False, 'error': 'No video IDs provided'}), 400
    try:
        result = processor.add_channel_videos_to_queue_by_ids(video_ids)
        state = processor.get_queue_state()
        return jsonify({'success': True, 'result': result, 'state': state})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# Podcast Subscription Endpoints
@app.route('/api/podcast-subscriptions', methods=['GET'])
def list_podcast_subscriptions():
    """List podcast subscriptions."""
    try:
        subs = podcast_processor.list_subscriptions()
        return jsonify({'success': True, 'subscriptions': subs})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/podcast-subscriptions', methods=['POST'])
def add_podcast_subscription():
    """Add a new podcast subscription (accepts name or RSS URL)."""
    try:
        data = request.get_json(force=True) or {}
        podcast_input = data.get('podcast') or data.get('podcast_name') or data.get('feed_url')
        if not podcast_input:
            return jsonify({'success': False, 'error': 'Missing podcast information. Please provide a podcast name or RSS feed URL.'}), 400
        
        subscription = podcast_processor.add_subscription(podcast_input)
        return jsonify({'success': True, 'subscription': subscription})
    except ValueError as ve:
        error_msg = str(ve)
        # Clean up error messages for better UX
        if 'pattern' in error_msg.lower():
            error_msg = 'Invalid RSS feed format. Please check the feed URL or try searching by podcast name instead.'
        return jsonify({'success': False, 'error': error_msg}), 400
    except Exception as e:
        error_msg = str(e)
        if 'pattern' in error_msg.lower():
            error_msg = 'Invalid RSS feed format. Please check the feed URL or try searching by podcast name instead.'
        return jsonify({'success': False, 'error': f'Error adding subscription: {error_msg}'}), 500

@app.route('/api/podcast-subscriptions/<int:subscription_id>', methods=['DELETE'])
def delete_podcast_subscription(subscription_id):
    """Delete podcast subscription."""
    try:
        removed = podcast_processor.remove_subscription(subscription_id)
        if not removed:
            return jsonify({'success': False, 'error': 'Subscription not found'}), 404
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/podcast-subscriptions/<int:subscription_id>/toggle', methods=['POST'])
def toggle_podcast_subscription(subscription_id):
    """Enable or disable podcast subscription."""
    try:
        subscription = podcast_processor.toggle_subscription(subscription_id)
        return jsonify({'success': True, 'subscription': subscription})
    except ValueError as ve:
        return jsonify({'success': False, 'error': str(ve)}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/podcast-subscriptions/<int:subscription_id>/refresh', methods=['POST'])
def refresh_podcast_subscription(subscription_id):
    """Refresh podcast episodes from RSS feed."""
    max_results = None
    if request.is_json:
        payload = request.get_json(silent=True) or {}
        max_results = payload.get('max_results')
    if max_results is not None:
        try:
            max_results = int(max_results)
        except (TypeError, ValueError):
            max_results = None
    try:
        result = podcast_processor.refresh_subscription(
            subscription_id,
            max_results=max_results
        )
        return jsonify({'success': True, 'result': result})
    except ValueError as ve:
        return jsonify({'success': False, 'error': str(ve)}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/podcast-episodes', methods=['GET'])
def list_podcast_episodes():
    """List podcast episodes with optional filters."""
    subscription_id = request.args.get('subscription_id', type=int)
    processed_param = request.args.get('processed')
    processed = None
    if processed_param is not None:
        processed = processed_param.lower() in ('1', 'true', 'yes')
    limit = request.args.get('limit', default=50, type=int)
    offset = request.args.get('offset', default=0, type=int)
    order = request.args.get('order', default='desc')
    try:
        episodes = podcast_processor.get_podcast_episodes(
            subscription_id=subscription_id,
            processed=processed,
            limit=limit,
            offset=offset,
            order=order
        )
        return jsonify({'success': True, 'data': episodes})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/podcast-episodes/<int:episode_id>/process', methods=['POST'])
def process_podcast_episode(episode_id):
    """Add podcast episode to processing queue"""
    try:
        episode = podcast_processor.get_episode(episode_id)
        if not episode:
            return jsonify({'success': False, 'error': 'Episode not found'}), 404
        
        # Allow reprocessing - if already processed, we'll create a new article entry
        is_reprocess = episode.get('processed', False)
        existing_article_id = episode.get('processed_article_id')
        
        # Check if transcript URL exists
        transcript_url = episode.get('transcript_url')
        audio_url = episode.get('audio_url')
        
        if not audio_url and not transcript_url:
            return jsonify({'success': False, 'error': 'No audio URL or transcript URL found'}), 400
        
        # Create database entry if needed
        article_id = existing_article_id
        if not article_id or is_reprocess:
            conn = sqlite3.connect(DATABASE_PATH)
            cursor = conn.cursor()
            
            # Ensure articles table has content_type column
            try:
                cursor.execute('ALTER TABLE articles ADD COLUMN content_type TEXT DEFAULT "article"')
                conn.commit()
            except sqlite3.OperationalError:
                pass
            
            # Insert placeholder entry
            title = episode.get('title', 'Untitled Episode')
            cursor.execute('''
                INSERT INTO articles (title, url, content, summary, tags, content_type)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (title, audio_url or transcript_url, '', '', 'audio', 'audio'))
            
            article_id = cursor.lastrowid
            conn.commit()
            conn.close()
        
        # Add to queue
        queue_item = podcast_processor.add_episode_to_queue(
            episode_id=episode_id,
            article_id=article_id,
            priority=1 if is_reprocess else 0,
            max_retries=3
        )
        
        message = 'Episode added to processing queue. ' + ('Using transcript.' if transcript_url else 'Will transcribe audio.')
        if is_reprocess:
            message = 'Reprocessing episode. ' + message
        
        return jsonify({
            'success': True,
            'article_id': article_id,
            'episode_id': episode_id,
            'queue_id': queue_item['id'],
            'message': message,
            'is_reprocess': is_reprocess
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

def process_podcast_episode_background(article_id, episode_id, episode, transcript_url, audio_url, title):
    """Background thread: Process podcast episode with transcript check"""
    try:
        transcript = None
        
        if transcript_url:
            # Download transcript directly
            print(f"📝 Downloading transcript from: {transcript_url}")
            try:
                import requests
                response = requests.get(transcript_url, timeout=30)
                response.raise_for_status()
                
                # Try to parse as HTML and extract text, or use as plain text
                content = response.text
                if '<html' in content.lower() or '<body' in content.lower():
                    # HTML transcript - extract text
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(content, 'html.parser')
                    transcript = soup.get_text(separator=' ', strip=True)
                else:
                    # Plain text transcript
                    transcript = content
                
                print(f"✅ Transcript downloaded ({len(transcript)} characters)")
            except Exception as e:
                print(f"⚠️  Failed to download transcript: {e}, falling back to audio transcription")
                transcript_url = None  # Fallback to audio
        
        if not transcript and audio_url:
            # Download and transcribe audio
            print(f"🎤 Processing audio from URL: {audio_url}")
            import yt_dlp
            import tempfile
            import whisper
            
            # Create temp file for audio
            temp_dir = tempfile.mkdtemp()
            temp_audio_path = os.path.join(temp_dir, f"audio_{article_id}.%(ext)s")
            
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': temp_audio_path,
                'quiet': False,  # Show progress for debugging
                'no_warnings': False,
                'extractaudio': True,
                'audioformat': 'mp3',
                'retries': 5,  # Increased retries
                'fragment_retries': 5,
                'extractor_retries': 5,
                'sleep_interval': 3,
                'max_sleep_interval': 10,
                'socket_timeout': 30,  # Add socket timeout
                'http_chunk_size': 10485760,  # 10MB chunks for large files
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            }
            
            print(f"⬇️  Downloading audio from: {audio_url}")
            downloaded_file = None
            max_retries = 5  # Increased max retries
            retry_count = 0
            
            while retry_count < max_retries:
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        # Try to validate URL first (without downloading)
                        try:
                            info = ydl.extract_info(audio_url, download=False)
                            print(f"✅ Audio source validated: {info.get('title', 'Unknown')} ({info.get('duration', 0)}s)")
                        except Exception as validate_error:
                            if retry_count < max_retries - 1:
                                print(f"⚠️  Validation failed, retrying ({retry_count + 1}/{max_retries})...")
                                retry_count += 1
                                import time
                                time.sleep(3)
                                continue
                            raise Exception(f"Audio source validation failed: {str(validate_error)}")
                        
                        # Now download with progress callback
                        print(f"⬇️  Starting download (attempt {retry_count + 1}/{max_retries})...")
                        
                        # Use a progress hook to monitor download
                        def progress_hook(d):
                            if d['status'] == 'downloading':
                                percent = d.get('_percent_str', 'N/A')
                                speed = d.get('_speed_str', 'N/A')
                                print(f"  Download progress: {percent} at {speed}")
                        
                        ydl_opts['progress_hooks'] = [progress_hook]
                        
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl_download:
                            info = ydl_download.extract_info(audio_url, download=True)
                        
                        # Wait for file to be written
                        import time
                        time.sleep(5)  # Increased wait time for large files
                        
                        downloaded_files = [f for f in os.listdir(temp_dir) if f.startswith(f"audio_{article_id}")]
                        if not downloaded_files:
                            if retry_count < max_retries - 1:
                                print(f"⚠️  No file created, retrying ({retry_count + 1}/{max_retries})...")
                                retry_count += 1
                                time.sleep(3)
                                continue
                            raise Exception("Failed to download audio file - no file was created after retries")
                        
                        downloaded_file = os.path.join(temp_dir, downloaded_files[0])
                        if not os.path.exists(downloaded_file):
                            if retry_count < max_retries - 1:
                                print(f"⚠️  File doesn't exist, retrying ({retry_count + 1}/{max_retries})...")
                                retry_count += 1
                                time.sleep(3)
                                continue
                            raise Exception(f"Downloaded file does not exist: {downloaded_file}")
                        
                        # Check file size
                        file_size = os.path.getsize(downloaded_file)
                        if file_size == 0:
                            if retry_count < max_retries - 1:
                                print(f"⚠️  Empty file, retrying ({retry_count + 1}/{max_retries})...")
                                retry_count += 1
                                time.sleep(3)
                                continue
                            raise Exception("Downloaded file is empty")
                        
                        print(f"✅ Audio downloaded successfully ({file_size / 1024 / 1024:.2f} MB)")
                        break  # Success, exit retry loop
                        
                except BrokenPipeError as e:
                    if retry_count < max_retries - 1:
                        print(f"⚠️  Broken pipe error, retrying ({retry_count + 1}/{max_retries})...")
                        retry_count += 1
                        import time
                        time.sleep(5)  # Longer wait for broken pipe
                        continue
                    raise Exception(f"Audio download interrupted (broken pipe) after {max_retries} attempts. This may be due to network issues, the audio source being unavailable, or the file being too large. Try again later or check the audio URL.")
                except OSError as e:
                    if e.errno == 32:  # Broken pipe
                        if retry_count < max_retries - 1:
                            wait_time = 5 + (retry_count * 2)  # Exponential backoff
                            print(f"⚠️  Broken pipe (OSError), retrying in {wait_time}s ({retry_count + 1}/{max_retries})...")
                            retry_count += 1
                            import time
                            time.sleep(wait_time)
                            # Clean up any partial files
                            try:
                                if downloaded_file and os.path.exists(downloaded_file):
                                    os.unlink(downloaded_file)
                            except:
                                pass
                            continue
                        raise Exception(f"Audio download interrupted (broken pipe) after {max_retries} attempts. Try again later.")
                    raise Exception(f"Audio download error: {str(e)}")
                except Exception as e:
                    error_msg = str(e)
                    if 'broken pipe' in error_msg.lower() or 'errno 32' in error_msg.lower():
                        if retry_count < max_retries - 1:
                            wait_time = 5 + (retry_count * 2)  # Exponential backoff
                            print(f"⚠️  Broken pipe detected, retrying in {wait_time}s ({retry_count + 1}/{max_retries})...")
                            retry_count += 1
                            import time
                            time.sleep(wait_time)
                            # Clean up any partial files
                            try:
                                if downloaded_file and os.path.exists(downloaded_file):
                                    os.unlink(downloaded_file)
                            except:
                                pass
                            continue
                        raise Exception(f"Audio download interrupted after {max_retries} attempts. Try again later.")
                    # For other errors, don't retry unless it's a network issue
                    if 'network' in error_msg.lower() or 'timeout' in error_msg.lower() or 'connection' in error_msg.lower():
                        if retry_count < max_retries - 1:
                            print(f"⚠️  Network error, retrying ({retry_count + 1}/{max_retries})...")
                            retry_count += 1
                            import time
                            time.sleep(5)
                            continue
                    raise Exception(f"Failed to download audio: {error_msg}")
            
            if not downloaded_file:
                raise Exception(f"Failed to download audio after {max_retries} attempts")
            
            print(f"✅ Audio downloaded, transcribing...")
            try:
                # Load Whisper model (may take a moment)
                model = whisper.load_model("medium")
                # Transcribe with error handling
                result = model.transcribe(downloaded_file)
                if not result or 'text' not in result:
                    raise Exception("Transcription returned no text")
                transcript = result["text"]
                if not transcript or len(transcript.strip()) == 0:
                    raise Exception("Transcription returned empty text")
            except BrokenPipeError as e:
                raise Exception(f"Transcription interrupted (broken pipe). This may be due to system resource issues or the audio file being corrupted. Error: {str(e)}")
            except OSError as e:
                if e.errno == 32:  # Broken pipe
                    raise Exception(f"Transcription interrupted (broken pipe). This may be due to system resource issues. Try again.")
                raise Exception(f"Transcription error: {str(e)}")
            except Exception as e:
                error_msg = str(e)
                if 'broken pipe' in error_msg.lower() or 'errno 32' in error_msg.lower():
                    raise Exception(f"Transcription interrupted. This may be due to system resource issues. Try again.")
                raise Exception(f"Failed to transcribe audio: {error_msg}")
            
            # Clean up temp file
            try:
                if os.path.exists(downloaded_file):
                    os.unlink(downloaded_file)
                if os.path.exists(temp_dir) and not os.listdir(temp_dir):
                    os.rmdir(temp_dir)
            except Exception as cleanup_error:
                print(f"⚠️  Warning: Could not clean up temp files: {cleanup_error}")
            
            print(f"✅ Transcription complete ({len(transcript)} characters)")
        
        if not transcript:
            raise Exception("Failed to get transcript or transcribe audio")
        
        # Generate summary using Claude (same prompt as articles/audio)
        prompt = f"""Create a tight, scannable executive analysis of this podcast transcript. Prioritize conciseness and quick comprehension over exhaustive detail.

## EXECUTIVE SUMMARY
**One tight paragraph** capturing the core thesis, main argument, and key takeaway. What's the essential point?

## KEY INSIGHTS
**Bullet-heavy format** - Use clear, scannable bullets (not long paragraphs). For each major insight:
- **Bold the insight/topic** followed by brief context (2-3 sentences max)
- Include specific numbers, dates, percentages when they matter
- Capture frameworks/systems but summarize components (don't break down exhaustively)
- Use quotes sparingly - only for truly significant claims

## STRUCTURED ANALYSIS
Organize into 3-5 clear sections using Roman numerals (I, II, III). For each section:
- **Lead with 1-2 short bullets** summarizing the main points
- Use sub-bullets for details, examples, or supporting evidence
- **Keep paragraphs minimal** - prefer bullets for scannability
- Extract key recommendations, predictions, or actionable items
- Don't repeat what's in Executive Summary

## CONCLUSION
**2-3 concise bullets** covering: final assessment, key implications, and what to remember.

**LENGTH TARGET**: Aim for 40-60% of the original transcript length. Be comprehensive but tight. Every sentence should earn its place.

**FORMAT PRIORITY**: Scannable > Exhaustive. Use bullets liberally. Break up dense paragraphs. Make it easy to quickly understand the value.

Podcast Episode: {title}
Transcript:
{transcript[:15000]}"""
        
        print(f"🤖 Generating summary with Claude Haiku 4.5...")
        print(f"   Transcript length: {len(transcript)} characters")
        print(f"   Prompt length: {len(prompt)} characters")
        
        try:
            response = claude_client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=6000,
                messages=[{"role": "user", "content": prompt}]
            )
            
            if not response or not response.content or len(response.content) == 0:
                raise Exception("Claude API returned empty response")
            
            summary = response.content[0].text
            
            # Validate summary before saving
            if not summary or not summary.strip():
                raise Exception("Claude returned an empty summary")
            
            print(f"✅ Summary generated ({len(summary)} characters)")
        except Exception as summary_error:
            error_msg = str(summary_error)
            print(f"❌ Summary generation failed: {error_msg}")
            # Re-raise with more context
            raise Exception(f"Failed to generate summary: {error_msg}")
        
        # Generate shortened versions
        print(f"Generating shortened summaries (50%, 30%, and 15%)...")
        summary_50 = generate_shortened_summary(summary, 50)
        summary_30 = generate_shortened_summary(summary, 30)
        summary_15 = generate_shortened_summary(summary, 15)
        
        # Update database
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Add summary_50, summary_30, and summary_15 columns if they don't exist
        try:
            cursor.execute('ALTER TABLE articles ADD COLUMN summary_50 TEXT')
            conn.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists
        try:
            cursor.execute('ALTER TABLE articles ADD COLUMN summary_30 TEXT')
            conn.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists
        try:
            cursor.execute('ALTER TABLE articles ADD COLUMN summary_15 TEXT')
            conn.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists
        
        cursor.execute('''
            UPDATE articles
            SET title = ?, content = ?, summary = ?, summary_50 = ?, summary_30 = ?, summary_15 = ?
            WHERE id = ?
        ''', (title, transcript[:50000], summary, summary_50, summary_30, summary_15, article_id))
        
        # Mark episode as processed (update even if reprocessing)
        cursor.execute('''
            UPDATE podcast_episodes
            SET processed = 1, processed_article_id = ?
            WHERE id = ?
        ''', (article_id, episode_id))
        
        conn.commit()
        conn.close()
        
        # Mark as completed
        audio_processing_status[article_id] = {'status': 'completed', 'error': None}
        print(f"✅ Podcast episode processing complete for ID: {article_id}")
        
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Error processing podcast episode {episode_id}: {error_msg}")
        print(f"   Article ID: {article_id}")
        print(f"   Full traceback:", flush=True)
        import traceback
        traceback.print_exc()
        
        audio_processing_status[article_id] = {'status': 'error', 'error': error_msg}
        
        # Update database with error message AND link the article to episode
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            cursor = conn.cursor()
            error_message = f"Error processing episode: {error_msg}"
            
            # Update article with error message
            cursor.execute('''
                UPDATE articles
                SET summary = ?
                WHERE id = ?
            ''', (error_message, article_id))
            
            # Link the article to the episode even if processing failed
            # This way users can see the error and retry
            cursor.execute('''
                UPDATE podcast_episodes
                SET processed = 1, processed_article_id = ?
                WHERE id = ?
            ''', (article_id, episode_id))
            
            conn.commit()
            conn.close()
            print(f"✅ Error saved to article {article_id} and episode {episode_id} linked")
        except Exception as db_error:
            print(f"⚠️  Failed to update database with error: {db_error}")
            import traceback
            traceback.print_exc()

def process_podcast_queue_worker():
    """Background worker that processes items from the podcast queue"""
    import time
    while True:
        try:
            # Get next item from queue
            queue_item = podcast_processor.get_next_queue_item()
            
            if not queue_item:
                # No items in queue, sleep and check again
                time.sleep(5)
                continue
            
            queue_id = queue_item['id']
            episode_id = queue_item['episode_id']
            article_id = queue_item.get('article_id')
            
            # Mark as processing
            podcast_processor.update_queue_item(
                queue_id,
                status='processing',
                stage='starting',
                progress_percent=0,
                started_at=datetime.now().isoformat()
            )
            
            # Get episode details
            episode = podcast_processor.get_episode(episode_id)
            if not episode:
                podcast_processor.update_queue_item(
                    queue_id,
                    status='failed',
                    error_message='Episode not found'
                )
                continue
            
            # Create article if needed
            if not article_id:
                conn = sqlite3.connect(DATABASE_PATH)
                cursor = conn.cursor()
                title = episode.get('title', 'Untitled Episode')
                audio_url = episode.get('audio_url') or episode.get('transcript_url', '')
                cursor.execute('''
                    INSERT INTO articles (title, url, content, summary, tags, content_type)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (title, audio_url, '', '', 'audio', 'audio'))
                article_id = cursor.lastrowid
                conn.commit()
                conn.close()
                podcast_processor.update_queue_item(queue_id, article_id=article_id)
            
            # Process the episode with progress updates
            try:
                process_podcast_episode_with_progress(
                    queue_id=queue_id,
                    article_id=article_id,
                    episode_id=episode_id,
                    episode=episode
                )
                # Mark as completed
                podcast_processor.update_queue_item(
                    queue_id,
                    status='completed',
                    stage='completed',
                    progress_percent=100,
                    completed_at=datetime.now().isoformat()
                )
            except Exception as e:
                error_msg = str(e)
                retry_count = queue_item.get('retry_count', 0) + 1
                max_retries = queue_item.get('max_retries', 3)
                
                if retry_count < max_retries:
                    # Retry later
                    podcast_processor.update_queue_item(
                        queue_id,
                        status='pending_retry',
                        error_message=error_msg,
                        retry_count=retry_count,
                        stage='failed_retrying'
                    )
                else:
                    # Max retries reached
                    podcast_processor.update_queue_item(
                        queue_id,
                        status='failed',
                        error_message=error_msg,
                        retry_count=retry_count,
                        stage='failed'
                    )
                    # Update article with error
                    conn = sqlite3.connect(DATABASE_PATH)
                    cursor = conn.cursor()
                    cursor.execute('''
                        UPDATE articles SET summary = ? WHERE id = ?
                    ''', (f"Error processing episode: {error_msg}", article_id))
                    conn.commit()
                    conn.close()
                    
        except Exception as e:
            print(f"❌ Error in podcast queue worker: {e}")
            import traceback
            traceback.print_exc()
            time.sleep(10)  # Wait before retrying

def process_podcast_episode_with_progress(queue_id, article_id, episode_id, episode):
    """Process podcast episode with progress tracking"""
    transcript_url = episode.get('transcript_url')
    audio_url = episode.get('audio_url')
    title = episode.get('title', 'Untitled Episode')
    
    transcript = None
    
    # Stage 1: Get transcript (10-30%)
    if transcript_url:
        podcast_processor.update_queue_item(queue_id, stage='downloading_transcript', progress_percent=10)
        print(f"📝 Downloading transcript from: {transcript_url}")
        try:
            import requests
            response = requests.get(transcript_url, timeout=30)
            response.raise_for_status()
            content = response.text
            if '<html' in content.lower() or '<body' in content.lower():
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(content, 'html.parser')
                transcript = soup.get_text(separator=' ', strip=True)
            else:
                transcript = content
            print(f"✅ Transcript downloaded ({len(transcript)} characters)")
            podcast_processor.update_queue_item(queue_id, stage='transcript_downloaded', progress_percent=30)
        except Exception as e:
            print(f"⚠️  Failed to download transcript: {e}, falling back to audio transcription")
            transcript_url = None
    
    # Stage 2: Download and transcribe audio (30-70%)
    if not transcript and audio_url:
        podcast_processor.update_queue_item(queue_id, stage='downloading_audio', progress_percent=30)
        print(f"🎤 Processing audio from URL: {audio_url}")
        import yt_dlp
        import tempfile
        import whisper
        
        temp_dir = tempfile.mkdtemp()
        temp_audio_path = os.path.join(temp_dir, f"audio_{article_id}.%(ext)s")
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': temp_audio_path,
            'quiet': False,
            'no_warnings': False,
            'extractaudio': True,
            'audioformat': 'mp3',
            'retries': 5,
            'fragment_retries': 5,
            'extractor_retries': 5,
            'sleep_interval': 3,
            'max_sleep_interval': 10,
            'socket_timeout': 30,
            'http_chunk_size': 10485760,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }
        
        downloaded_file = None
        max_retries = 5
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([audio_url])
                
                import time
                time.sleep(5)
                downloaded_files = [f for f in os.listdir(temp_dir) if f.startswith(f"audio_{article_id}")]
                if downloaded_files:
                    downloaded_file = os.path.join(temp_dir, downloaded_files[0])
                    if os.path.exists(downloaded_file) and os.path.getsize(downloaded_file) > 0:
                        break
                retry_count += 1
                time.sleep(3)
            except Exception as e:
                retry_count += 1
                if retry_count < max_retries:
                    time.sleep(5)
                    continue
                raise Exception(f"Failed to download audio: {str(e)}")
        
        if not downloaded_file:
            raise Exception(f"Failed to download audio after {max_retries} attempts")
        
        podcast_processor.update_queue_item(queue_id, stage='transcribing', progress_percent=50)
        print(f"✅ Audio downloaded, transcribing...")
        print(f"   File size: {os.path.getsize(downloaded_file) / 1024 / 1024:.2f} MB")
        print(f"   This may take 10-20 minutes for large files...")
        
        # Transcribe with progress updates
        try:
            model = whisper.load_model("medium")
            print(f"   Whisper model loaded, starting transcription...")
            
            # Update progress to show we're actively transcribing
            podcast_processor.update_queue_item(queue_id, stage='transcribing', progress_percent=55)
            
            result = model.transcribe(downloaded_file)
            
            if not result or 'text' not in result:
                raise Exception("Transcription returned no text")
            transcript = result["text"]
            if not transcript or len(transcript.strip()) == 0:
                raise Exception("Transcription returned empty text")
            
            print(f"✅ Transcription complete ({len(transcript)} characters)")
            podcast_processor.update_queue_item(queue_id, stage='transcription_complete', progress_percent=70)
        except Exception as transcribe_error:
            error_msg = str(transcribe_error)
            print(f"❌ Transcription failed: {error_msg}")
            # Re-raise to be caught by outer exception handler
            raise Exception(f"Transcription failed: {error_msg}")
        
        # Cleanup
        try:
            if os.path.exists(downloaded_file):
                os.unlink(downloaded_file)
            if os.path.exists(temp_dir) and not os.listdir(temp_dir):
                os.rmdir(temp_dir)
        except:
            pass
    
    if not transcript:
        raise Exception("Failed to get transcript or transcribe audio")
    
    # Stage 3: Generate summary (70-95%)
    podcast_processor.update_queue_item(queue_id, stage='generating_summary', progress_percent=70)
    prompt = f"""Create a tight, scannable executive analysis of this podcast transcript. Prioritize conciseness and quick comprehension over exhaustive detail.

## EXECUTIVE SUMMARY
**One tight paragraph** capturing the core thesis, main argument, and key takeaway. What's the essential point?

## KEY INSIGHTS
**Bullet-heavy format** - Use clear, scannable bullets (not long paragraphs). For each major insight:
- **Bold the insight/topic** followed by brief context (2-3 sentences max)
- Include specific numbers, dates, percentages when they matter
- Capture frameworks/systems but summarize components (don't break down exhaustively)
- Use quotes sparingly - only for truly significant claims

## STRUCTURED ANALYSIS
Organize into 3-5 clear sections using Roman numerals (I, II, III). For each section:
- **Lead with 1-2 short bullets** summarizing the main points
- Use sub-bullets for details, examples, or supporting evidence
- **Keep paragraphs minimal** - prefer bullets for scannability
- Extract key recommendations, predictions, or actionable items
- Don't repeat what's in Executive Summary

## CONCLUSION
**2-3 concise bullets** covering: final assessment, key implications, and what to remember.

**LENGTH TARGET**: Aim for 40-60% of the original transcript length. Be comprehensive but tight. Every sentence should earn its place.

**FORMAT PRIORITY**: Scannable > Exhaustive. Use bullets liberally. Break up dense paragraphs. Make it easy to quickly understand the value.

Podcast Episode: {title}
Transcript:
{transcript[:15000]}"""
    
    print(f"🤖 Generating summary with Claude Haiku 4.5...")
    response = claude_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=6000,
        messages=[{"role": "user", "content": prompt}]
    )
    
    if not response or not response.content or len(response.content) == 0:
        raise Exception("Claude API returned empty response")
    
    summary = response.content[0].text
    if not summary or not summary.strip():
        raise Exception("Claude returned an empty summary")
    
    print(f"✅ Summary generated ({len(summary)} characters)")
    podcast_processor.update_queue_item(queue_id, stage='summary_generated', progress_percent=95)
    
    # Stage 4: Save to database (95-100%)
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE articles
        SET title = ?, content = ?, summary = ?
        WHERE id = ?
    ''', (title, transcript[:50000], summary, article_id))
    
    cursor.execute('''
        UPDATE podcast_episodes
        SET processed = 1, processed_article_id = ?
        WHERE id = ?
    ''', (article_id, episode_id))
    
    conn.commit()
    conn.close()
    
    podcast_processor.update_queue_item(queue_id, stage='saved', progress_percent=100)
    print(f"✅ Podcast episode processing complete for ID: {article_id}")

# Newsletter subscription endpoints
@app.route('/api/newsletter-subscriptions', methods=['GET'])
def list_newsletter_subscriptions():
    """List all newsletter subscriptions"""
    try:
        subs = db_service.list_newsletter_subscriptions()
        return jsonify({'success': True, 'subscriptions': subs})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/newsletter-subscriptions', methods=['POST'])
def add_newsletter_subscription():
    """Add a new newsletter subscription (accepts name or URL)"""
    try:
        data = request.get_json(force=True) or {}
        newsletter_input = data.get('newsletter') or data.get('name') or data.get('feed_url')
        if not newsletter_input:
            return jsonify({'success': False, 'error': 'Missing newsletter name or URL'}), 400

        # Smart resolution: try to find RSS feed
        feed_url = None
        platform = None
        newsletter_name = newsletter_input
        website_url = None
        ktn_email = None

        import re
        newsletter_input = newsletter_input.strip()

        # Check if it's a URL
        if newsletter_input.startswith('http://') or newsletter_input.startswith('https://'):
            website_url = newsletter_input

            # Substack detection
            if 'substack.com' in newsletter_input:
                platform = 'Substack'
                # Extract subdomain for name
                match = re.search(r'https?://([^.]+)\.substack\.com', newsletter_input)
                if match:
                    newsletter_name = match.group(1).replace('-', ' ').title()
                # Build feed URL
                if '/feed' not in newsletter_input:
                    base = re.sub(r'(/p/.*|/archive.*|/about.*)?$', '', newsletter_input)
                    feed_url = base.rstrip('/') + '/feed'
                else:
                    feed_url = newsletter_input

            # Beehiiv detection
            elif 'beehiiv.com' in newsletter_input:
                platform = 'Beehiiv'
                match = re.search(r'https?://([^.]+)\.beehiiv\.com', newsletter_input)
                if match:
                    newsletter_name = match.group(1).replace('-', ' ').title()
                # Beehiiv feeds are usually at /feed
                if '/feed' not in newsletter_input:
                    feed_url = newsletter_input.rstrip('/') + '/feed'
                else:
                    feed_url = newsletter_input

            # Ghost platform detection
            elif '/rss/' in newsletter_input or newsletter_input.endswith('/rss'):
                platform = 'Ghost'
                feed_url = newsletter_input

            # Generic RSS feed
            elif newsletter_input.endswith('.xml') or newsletter_input.endswith('/feed') or '/rss' in newsletter_input:
                platform = 'RSS'
                feed_url = newsletter_input
            else:
                # Try to append /feed for unknown URLs
                platform = 'RSS'
                feed_url = newsletter_input.rstrip('/') + '/feed'
        else:
            # Name-based search - try common patterns
            import feedparser
            slug = re.sub(r'[^a-z0-9]+', '-', newsletter_input.lower()).strip('-')

            # Try patterns in order of likelihood
            patterns_to_try = [
                (f'https://{slug}.com/feed', f'https://{slug}.com', 'RSS'),
                (f'https://{slug}.com/feed/', f'https://{slug}.com', 'RSS'),
                (f'https://www.{slug}.com/feed', f'https://www.{slug}.com', 'RSS'),
                (f'https://{slug}.substack.com/feed', f'https://{slug}.substack.com', 'Substack'),
                (f'https://{slug}.beehiiv.com/feed', f'https://{slug}.beehiiv.com', 'Beehiiv'),
            ]

            for try_feed, try_website, try_platform in patterns_to_try:
                try:
                    test_feed = feedparser.parse(try_feed)
                    # Check if feed is valid and has entries
                    if test_feed.entries and len(test_feed.entries) > 0 and not test_feed.get('bozo'):
                        feed_url = try_feed
                        platform = try_platform
                        website_url = try_website
                        # Use feed title if available
                        if test_feed.feed.get('title'):
                            newsletter_name = test_feed.feed.get('title')
                        break
                except:
                    continue

            # If pattern matching failed, ask Claude for intelligent lookup
            if not feed_url:
                try:
                    print(f"🤖 Pattern matching failed for '{newsletter_input}', asking Claude...")
                    ai_response = claude_client.messages.create(
                        model="claude-haiku-4-5-20251001",
                        max_tokens=300,
                        messages=[{
                            "role": "user",
                            "content": f"""What is the RSS feed URL for the newsletter or blog called "{newsletter_input}"?

Reply with ONLY the RSS feed URL on a single line, nothing else. If you're not sure, make your best guess based on common patterns.

Examples of correct responses:
https://stratechery.com/feed/
https://www.platformer.news/rss/
https://seths.blog/feed/

Just the URL, no explanation."""
                        }]
                    )
                    ai_url = ai_response.content[0].text.strip()
                    # Validate it looks like a URL
                    if ai_url.startswith('http') and ('feed' in ai_url or 'rss' in ai_url or '.xml' in ai_url):
                        print(f"🤖 Claude suggested: {ai_url}")
                        # Verify the feed actually works
                        test_feed = feedparser.parse(ai_url)
                        if test_feed.entries and len(test_feed.entries) > 0:
                            feed_url = ai_url
                            platform = 'AI-discovered'
                            website_url = re.sub(r'/feed/?$|/rss/?$|/feed\.xml$', '', ai_url)
                            if test_feed.feed.get('title'):
                                newsletter_name = test_feed.feed.get('title')
                            print(f"✅ AI-discovered feed validated: {feed_url}")
                        else:
                            print(f"⚠️ Claude's suggestion didn't validate as working feed")
                except Exception as ai_error:
                    print(f"⚠️ Claude lookup failed: {ai_error}")

            # Strategy 4: Kill the Newsletter fallback
            ktn_email = None
            if not feed_url:
                try:
                    import requests
                    print(f"📧 No RSS feed found for '{newsletter_input}', creating Kill the Newsletter inbox...")
                    ktn_response = requests.post(
                        'https://kill-the-newsletter.com/feeds',
                        data={'title': newsletter_input},
                        headers={
                            'Content-Type': 'application/x-www-form-urlencoded',
                            'Accept': 'application/json',
                            'CSRF-Protection': 'true'
                        },
                        timeout=15
                    )
                    if ktn_response.status_code == 200:
                        ktn_data = ktn_response.json()
                        feed_url = ktn_data.get('feed')
                        ktn_email = ktn_data.get('email')
                        platform = 'Kill the Newsletter'
                        print(f"✅ KTN inbox created: {ktn_email} -> {feed_url}")
                    else:
                        print(f"⚠️ KTN API returned status {ktn_response.status_code}")
                except Exception as ktn_error:
                    print(f"⚠️ Kill the Newsletter fallback failed: {ktn_error}")

            # Final fallback if still no feed
            if not feed_url:
                newsletter_name = newsletter_input
                platform = 'Manual'

        # Check for duplicate
        existing = db_service.list_newsletter_subscriptions()
        for sub in existing:
            if sub.get('feed_url') == feed_url and feed_url:
                return jsonify({'success': False, 'error': f'Newsletter already subscribed: {sub.get("newsletter_name")}'}), 400

        # Add subscription
        subscription = db_service.add_newsletter_subscription(
            newsletter_name=newsletter_name,
            feed_url=feed_url,
            platform=platform,
            website_url=website_url,
            ktn_email=ktn_email
        )

        if not subscription:
            return jsonify({'success': False, 'error': 'Failed to create subscription'}), 500

        # Try to fetch initial issues if we have a feed
        if feed_url:
            try:
                import feedparser
                feed = feedparser.parse(feed_url)
                for entry in feed.entries[:50]:  # Get last 50 issues
                    issue_guid = entry.get('id') or entry.get('link') or entry.get('title')
                    title = entry.get('title', 'Untitled')
                    description = entry.get('summary') or entry.get('description')
                    issue_url = entry.get('link')
                    published = entry.get('published') or entry.get('updated')

                    db_service.add_newsletter_issue(
                        subscription_id=subscription['id'],
                        issue_guid=issue_guid,
                        title=title,
                        description=description,
                        issue_url=issue_url,
                        published_at=published
                    )
                db_service.update_newsletter_last_checked(subscription['id'])
            except Exception as feed_error:
                print(f"Warning: Could not fetch initial issues: {feed_error}")

        return jsonify({'success': True, 'subscription': subscription})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/newsletter-subscriptions/<int:subscription_id>', methods=['DELETE'])
def delete_newsletter_subscription(subscription_id):
    """Delete a newsletter subscription"""
    try:
        deleted = db_service.delete_newsletter_subscription(subscription_id)
        if not deleted:
            return jsonify({'success': False, 'error': 'Subscription not found'}), 404
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/newsletter-subscriptions/<int:subscription_id>/toggle', methods=['POST'])
def toggle_newsletter_subscription(subscription_id):
    """Toggle enabled status of a newsletter subscription"""
    try:
        subscription = db_service.toggle_newsletter_subscription(subscription_id)
        if not subscription:
            return jsonify({'success': False, 'error': 'Subscription not found'}), 404
        return jsonify({'success': True, 'subscription': subscription})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/newsletter-subscriptions/<int:subscription_id>/rename', methods=['POST'])
def rename_newsletter_subscription(subscription_id):
    """Rename a newsletter subscription"""
    try:
        data = request.get_json(force=True) or {}
        new_name = (data.get('name') or '').strip()
        if not new_name:
            return jsonify({'success': False, 'error': 'Name is required'}), 400

        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('UPDATE newsletter_subscriptions SET newsletter_name = ? WHERE id = ?', (new_name, subscription_id))
        if cursor.rowcount == 0:
            conn.close()
            return jsonify({'success': False, 'error': 'Subscription not found'}), 404
        conn.commit()
        cursor.execute('SELECT * FROM newsletter_subscriptions WHERE id = ?', (subscription_id,))
        row = cursor.fetchone()
        conn.close()
        return jsonify({'success': True, 'subscription': dict(row)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/newsletter-subscriptions/<int:subscription_id>/refresh', methods=['POST'])
def refresh_newsletter_subscription(subscription_id):
    """Refresh newsletter issues from RSS feed"""
    try:
        subscription = db_service.get_newsletter_subscription(subscription_id)
        if not subscription:
            return jsonify({'success': False, 'error': 'Subscription not found'}), 404

        feed_url = subscription.get('feed_url')
        if not feed_url:
            return jsonify({'success': False, 'error': 'No feed URL configured for this newsletter'}), 400

        import feedparser
        feed = feedparser.parse(feed_url)
        new_count = 0

        for entry in feed.entries[:100]:  # Fetch up to 100 issues on refresh
            issue_guid = entry.get('id') or entry.get('link') or entry.get('title')
            title = entry.get('title', 'Untitled')
            description = entry.get('summary') or entry.get('description')
            issue_url = entry.get('link')
            published = entry.get('published') or entry.get('updated')

            result = db_service.add_newsletter_issue(
                subscription_id=subscription_id,
                issue_guid=issue_guid,
                title=title,
                description=description,
                issue_url=issue_url,
                published_at=published
            )
            if result:
                new_count += 1

        db_service.update_newsletter_last_checked(subscription_id)

        return jsonify({'success': True, 'new_issues': new_count})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/newsletter-issues', methods=['GET'])
def list_newsletter_issues():
    """List issues for a newsletter subscription"""
    subscription_id = request.args.get('subscription_id', type=int)
    if not subscription_id:
        return jsonify({'success': False, 'error': 'subscription_id required'}), 400
    try:
        issues = db_service.get_newsletter_issues(subscription_id)
        return jsonify({'success': True, 'issues': issues})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/newsletter-issues/<int:issue_id>/process', methods=['POST'])
def process_newsletter_issue(issue_id):
    """Process a newsletter issue - fetch content, summarize, save as article"""
    try:
        # Get the issue
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM newsletter_issues WHERE id = ?', (issue_id,))
        issue = cursor.fetchone()
        if not issue:
            conn.close()
            return jsonify({'success': False, 'error': 'Issue not found'}), 404

        issue = dict(issue)
        issue_url = issue.get('issue_url')
        if not issue_url:
            conn.close()
            return jsonify({'success': False, 'error': 'No URL for this issue'}), 400

        # Fetch the content
        import requests
        from bs4 import BeautifulSoup
        print(f"📰 Fetching newsletter content from: {issue_url}")

        headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
        response = requests.get(issue_url, headers=headers, timeout=30)
        response.raise_for_status()

        # Extract text content
        soup = BeautifulSoup(response.text, 'html.parser')

        # Remove script, style, nav elements
        for tag in soup(['script', 'style', 'nav', 'header', 'footer', 'aside']):
            tag.decompose()

        # Try to find main content
        content_el = soup.find('article') or soup.find('main') or soup.find('div', class_='post-content') or soup.find('div', class_='body')
        if content_el:
            content_text = content_el.get_text(separator='\n', strip=True)
        else:
            content_text = soup.get_text(separator='\n', strip=True)

        # Truncate if too long
        if len(content_text) > 50000:
            content_text = content_text[:50000] + '...'

        if len(content_text) < 200:
            conn.close()
            return jsonify({'success': False, 'error': 'Could not extract meaningful content from the page'}), 400

        print(f"📰 Extracted {len(content_text)} characters, sending to Claude...")

        # Get newsletter name for context
        cursor.execute('SELECT newsletter_name FROM newsletter_subscriptions WHERE id = ?', (issue.get('subscription_id'),))
        sub_row = cursor.fetchone()
        newsletter_name = sub_row['newsletter_name'] if sub_row else 'Newsletter'

        # Summarize with Claude
        summary_response = claude_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2000,
            messages=[{
                "role": "user",
                "content": f"""Summarize this newsletter issue from "{newsletter_name}".

Title: {issue.get('title', 'Untitled')}

Content:
{content_text[:40000]}

Write a dense, substantive summary that covers ALL major points in the piece — not just the first few in detail.

For each point or section, capture what's SPECIFIC and DISTINCTIVE about it in 1-2 tight sentences. Ask yourself: "Would this line make someone say 'that's interesting' or 'I've heard that before'?" If it's the latter, you've genericized it. Fix it.

Guidelines:
- COVERAGE FIRST: Hit every major argument, prescription, or framework. Don't elaborate on early points at the expense of later ones.
- Be concise but specific. "Adaptability and resilience for wave-surfing careers" beats a paragraph expanding the surfing metaphor. But it also beats "cultivate adaptability" which strips the distinctive framing.
- Keep the author's sharpest lines verbatim when they carry meaning that paraphrase would kill.
- For prescriptions: include the specific actions, not just the category. "Drama, debate club, music lessons" not "develop emotional intelligence." "Ask your child: what do you believe that few others do?" not "encourage uniqueness."
- Preserve concrete examples, named references, numbers, and timelines.
- Cut filler prose, repetition, and setup — keep only the substance underneath.
- Do NOT use generic academic framing like "the author argues" or "key insights include."

Write 500-800 words depending on how much substance the piece contains. Every sentence should carry specific information the reader couldn't guess from the headline."""
            }]
        )
        summary = summary_response.content[0].text

        # Generate shortened summaries
        print(f"📰 Generating shortened summaries...")
        summary_50 = generate_shortened_summary(summary, 50)
        summary_30 = generate_shortened_summary(summary, 30)
        summary_15 = generate_shortened_summary(summary, 15)

        # Create article entry with all summary lengths
        cursor.execute('''
            INSERT INTO articles (title, url, content, summary, summary_50, summary_30, summary_15, tags, content_type, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (
            issue.get('title', 'Newsletter Issue'),
            issue_url,
            content_text[:50000],
            summary,
            summary_50,
            summary_30,
            summary_15,
            newsletter_name,
            'newsletter'
        ))
        article_id = cursor.lastrowid

        # Update issue as processed
        cursor.execute('''
            UPDATE newsletter_issues
            SET processed = 1, processed_article_id = ?
            WHERE id = ?
        ''', (article_id, issue_id))

        conn.commit()
        conn.close()

        print(f"✅ Newsletter issue processed, article ID: {article_id}")

        return jsonify({
            'success': True,
            'article_id': article_id,
            'summary_length': len(summary)
        })

    except requests.RequestException as e:
        return jsonify({'success': False, 'error': f'Failed to fetch content: {str(e)}'}), 500
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/podcast-queue', methods=['GET'])
def get_podcast_queue():
    """Get podcast processing queue items"""
    status = request.args.get('status')
    limit = request.args.get('limit', type=int)
    try:
        items = podcast_processor.get_queue_items(status=status, limit=limit)
        return jsonify({'success': True, 'queue': items})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/channels')
def channels_page():
    try:
        with open('channels.html', 'r') as f:
            return f.read()
    except FileNotFoundError:
        return '<h1>Channels page not found</h1><p><a href="/">← Back to Capture</a></p>'

@app.route('/intelligence', endpoint='intelligence_route')
def serve_intelligence_page():
    try:
        with open('intelligence.html', 'r') as f:
            return f.read()
    except FileNotFoundError:
        return '<h1>Intelligence page not found</h1><p><a href="/">← Back to Capture</a></p>'

@app.route('/briefing')
def briefing_page():
    try:
        with open('briefing.html', 'r') as f:
            return f.read()
    except FileNotFoundError:
        return '<h1>Briefing Room page not found</h1><p><a href="/">← Back to Capture</a></p>'

@app.route('/api/server-status', methods=['GET'])
def server_status():
    """Check if the server is running"""
    try:
        # Check if port 5001 is listening
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('127.0.0.1', 5001))
        sock.close()
        
        is_running = result == 0
        
        # Check if the monitoring script is running
        import subprocess
        try:
            check_result = subprocess.run(
                ['pgrep', '-f', 'start_and_keep_running.sh'],
                capture_output=True,
                timeout=2
            )
            monitoring_running = check_result.returncode == 0
        except:
            monitoring_running = False
        
        return jsonify({
            'success': True,
            'server_running': is_running,
            'monitoring_running': monitoring_running,
            'status': 'running' if is_running else 'stopped',
            'message': 'Server is running' if is_running else 'Server is stopped'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'server_running': False,
            'monitoring_running': False,
            'status': 'error',
            'error': str(e)
        }), 500

@app.route('/api/server-start', methods=['POST'])
def server_start():
    """Start the server"""
    try:
        import subprocess
        import os
        import socket
        
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'start_and_keep_running.sh')
        
        # Check if already running
        check_result = subprocess.run(
            ['pgrep', '-f', 'start_and_keep_running.sh'],
            capture_output=True,
            timeout=2
        )
        
        if check_result.returncode == 0:
            return jsonify({
                'success': True,
                'message': 'Server is already running',
                'already_running': True
            })
        
        # Start in background
        subprocess.Popen(
            ['/bin/bash', script_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        
        # Wait a moment and check
        import time
        time.sleep(3)
        
        # Verify it started
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('127.0.0.1', 5001))
        sock.close()
        
        if result == 0:
            return jsonify({
                'success': True,
                'message': 'Server started successfully',
                'server_running': True
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Server start command executed but server not responding yet',
                'server_running': False
            }), 500
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/server-stop', methods=['POST'])
def server_stop():
    """Stop the server"""
    try:
        import subprocess
        import os
        import socket
        
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'stop_server.sh')
        
        # Run stop script
        result = subprocess.run(
            ['/bin/bash', script_path],
            capture_output=True,
            timeout=10
        )
        
        # Wait a moment and verify
        import time
        time.sleep(2)
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        check_result = sock.connect_ex(('127.0.0.1', 5001))
        sock.close()
        
        if check_result != 0:
            return jsonify({
                'success': True,
                'message': 'Server stopped successfully',
                'server_running': False
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Stop command executed but server still appears to be running',
                'server_running': True
            }), 500
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/remove-duplicates', methods=['POST'])
def remove_duplicates():
    """Remove duplicate videos, keeping the one with the most complete data"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Find duplicates by video_url
        cursor.execute('''
            SELECT video_url, COUNT(*) as count, GROUP_CONCAT(id) as ids
            FROM videos
            WHERE video_url IS NOT NULL AND video_url != ''
            GROUP BY video_url
            HAVING COUNT(*) > 1
        ''')
        
        duplicates = cursor.fetchall()
        removed_count = 0
        
        for video_url, count, ids_str in duplicates:
            ids = [int(id) for id in ids_str.split(',')]
            
            # Keep the video with the most complete data (has transcript and summary)
            cursor.execute('''
                SELECT id FROM videos
                WHERE video_url = ?
                ORDER BY 
                    CASE WHEN full_transcript IS NOT NULL AND full_transcript != '' THEN 1 ELSE 0 END DESC,
                    CASE WHEN ai_summary IS NOT NULL AND ai_summary != '' THEN 1 ELSE 0 END DESC,
                    processing_date DESC
                LIMIT 1
            ''', (video_url,))
            keep_id = cursor.fetchone()[0]
            
            # Remove all others
            ids_to_remove = [id for id in ids if id != keep_id]
            if ids_to_remove:
                placeholders = ','.join(['?'] * len(ids_to_remove))
                cursor.execute(f'''
                    DELETE FROM videos
                    WHERE id IN ({placeholders})
                ''', ids_to_remove)
                removed_count += len(ids_to_remove)
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'duplicate_groups': len(duplicates),
            'removed_count': removed_count,
            'message': f'Removed {removed_count} duplicate videos, kept {len(duplicates)} originals'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/videos/<int:video_id>/reprocess-with-prompt', methods=['POST'])
def reprocess_video_with_prompt(video_id):
    """Reprocess a video with a different prompt, creating a new entry for comparison"""
    try:
        data = request.get_json() or {}
        target_prompt = data.get('prompt_type', 'interview')  # Default to interview
        
        # Get the original video
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, video_url, title, channel, full_transcript, ai_summary, prompt_used
            FROM videos
            WHERE id = ?
        ''', (video_id,))
        video = cursor.fetchone()
        conn.close()
        
        if not video:
            return jsonify({'success': False, 'error': 'Video not found'}), 404
        
        video_id, video_url, title, channel, transcript, old_summary, old_prompt = video
        
        if not transcript:
            return jsonify({'success': False, 'error': 'Video has no transcript available'}), 400
        
        if old_prompt == target_prompt:
            return jsonify({
                'success': False, 
                'error': f'Video already processed with {target_prompt} prompt'
            }), 400
        
        print(f"🔄 Reprocessing video {video_id} ({title}) with {target_prompt} prompt")
        print(f"   Original prompt: {old_prompt}")
        
        # Force the content type detection to use the target prompt
        # We'll override the detection for this specific reprocessing
        if target_prompt == 'interview':
            # Force interview prompt
            content_type = 'interview'
        elif target_prompt == 'tools_workflows':
            content_type = 'tools_workflows'
        elif target_prompt == 'explainer':
            content_type = 'explainer'
        else:
            # Let it auto-detect
            content_type = processor.detect_content_type(title, transcript[:1000])
        
        # Generate summary with the forced target prompt
        from pathlib import Path
        prompt_file = Path(f"prompts/current_best/{target_prompt}_prompt.txt")
        if not prompt_file.exists():
            prompt_file = Path("prompts/current_best/explainer_prompt.txt")
            if not prompt_file.exists():
                return jsonify({'success': False, 'error': f'Prompt file not found for {target_prompt}'}), 500
        
        with open(prompt_file, 'r') as f:
            prompt_template = f.read()
        
        # Format the prompt
        clean_transcript = processor.clean_transcript_for_summary(transcript)
        formatted_prompt = prompt_template.format(
            title=title,
            transcript=clean_transcript[:120000]
        )
        
        # Generate with forced prompt
        print(f"🤖 Generating summary with forced {target_prompt} prompt...")
        response = processor.claude_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=6000,
            messages=[{"role": "user", "content": formatted_prompt}]
        )
        summary_text = response.content[0].text
        prompt_used = target_prompt
        
        # Create a NEW video entry (don't overwrite the old one)
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Insert as new video entry with all required fields
        cursor.execute('''
            INSERT INTO videos (
                screenshot_path, filename, video_url, title, channel,
                full_transcript, ai_summary, key_insights, topics,
                confidence_score, status, prompt_used, processing_date
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (
            f"reprocessed_from_{video_id}",  # screenshot_path
            f"reprocessed_from_{video_id}",  # filename
            video_url,  # Keep same URL
            f"{title} [Reprocessed: {target_prompt}]",  # Mark as reprocessed in title
            channel or '',
            transcript,
            summary_text,
            '',  # key_insights
            '',  # topics
            1.0,  # confidence_score
            'completed',
            prompt_used
        ))
        
        new_video_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': f'Video reprocessed with {target_prompt} prompt',
            'original_video_id': video_id,
            'new_video_id': new_video_id,
            'original_prompt': old_prompt,
            'new_prompt': prompt_used
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/clear-stuck-processing', methods=['POST'])
def clear_stuck_processing():
    """Reset videos stuck in processing status"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Reset videos stuck in processing for more than 2 hours
        cursor.execute('''
            UPDATE videos
            SET status = 'pending'
            WHERE status = 'processing'
            AND processing_date < datetime('now', '-2 hours')
        ''')
        reset_count = cursor.rowcount
        
        # Also reset queue items stuck in processing
        cursor.execute('''
            UPDATE processing_queue
            SET status = 'queued', started_at = NULL
            WHERE status = 'processing'
            AND started_at < datetime('now', '-2 hours')
        ''')
        queue_reset_count = cursor.rowcount
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'videos_reset': reset_count,
            'queue_items_reset': queue_reset_count,
            'message': f'Reset {reset_count} stuck videos and {queue_reset_count} queue items'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/create-backup', methods=['POST'])
def create_backup():
    """Create a backup of the current working state"""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backups", timestamp)
        
        # Create backup directory
        os.makedirs(backup_dir, exist_ok=True)
        
        # Files to backup
        base_dir = os.path.dirname(os.path.abspath(__file__))
        files_to_backup = [
            "app.py",
            "youtube_processor.py", 
            "library.html",
            "channels.html",
            "debug.html",
            "interface.html",
            "stats.html",
            "youtube_intelligence.db"
        ]
        
        copied_files = []
        missing_files = []
        
        # Copy files
        for file in files_to_backup:
            src_path = os.path.join(base_dir, file)
            if os.path.exists(src_path):
                shutil.copy2(src_path, backup_dir)
                copied_files.append(file)
            else:
                missing_files.append(file)
        
        # Copy prompts directory
        prompts_src = os.path.join(base_dir, "prompts")
        if os.path.exists(prompts_src):
            prompts_dst = os.path.join(backup_dir, "prompts")
            shutil.copytree(prompts_src, prompts_dst, dirs_exist_ok=True)
            copied_files.append("prompts/")
        
        # Create backup info
        info_file = os.path.join(backup_dir, "BACKUP_INFO.txt")
        backup_dir_escaped = backup_dir.replace('\\', '/')  # Normalize path separators
        with open(info_file, 'w') as f:
            f.write(f"""BACKUP INFORMATION
===================

Backup Created: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
Backup Directory: {backup_dir_escaped}

FEATURES WORKING:
=================

1. Summary Length Buttons on Tiles
   - Each tile now has "Full", "50%", and "30%" buttons (when available)
   - Buttons open document view directly with the selected summary length
   - No in-document switching needed - cleaner approach

2. Word Count Display
   - Word count now appears next to ID number on tiles
   - Shows word count for the 100% (full) summary
   - Only displays for items with summaries (not processing)

3. Document View Improvements
   - viewAsDocument function accepts summaryLength parameter (100, 50, or 30)
   - Document view shows which summary length is being viewed
   - Links to switch to other summary versions if available

4. Menu Bar Updates
   - "Channels" now appears before "Intelligence" in menu bar
   - "Back to Capture" changed to just "Capture"

5. Summary Generation
   - Videos and articles automatically generate 50% and 30% summaries
   - Summaries stored in database (summary_50, summary_30 columns)
   - Generated using Claude Haiku 4.5 for cost efficiency

FILES BACKED UP:
================
""")
            for file in copied_files:
                f.write(f"  ✓ {file}\n")
            if missing_files:
                f.write("\nMISSING FILES:\n")
                for file in missing_files:
                    f.write(f"  ✗ {file}\n")
        
        # Count total items in database
        total_items = 0
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM videos")
            video_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM articles")
            article_count = cursor.fetchone()[0]
            total_items = video_count + article_count
            conn.close()
        except:
            pass
        
        return jsonify({
            'success': True,
            'backup_dir': backup_dir_escaped,
            'copied_files': copied_files,
            'missing_files': missing_files,
            'total_items': total_items
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

###############################################################################
# YouTube-to-Podcast Feed Feature
###############################################################################

import queue as queue_module
import socket as _socket
_yt_podcast_extraction_queue = queue_module.Queue()

def _get_local_hostname():
    """Get the .local hostname for LAN access (e.g. Js-MacBook-Pro.local)."""
    try:
        import subprocess
        result = subprocess.run(['scutil', '--get', 'LocalHostName'],
                                capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip() + '.local'
    except Exception:
        pass
    return _socket.gethostname()

_LOCAL_HOSTNAME = _get_local_hostname()

def _get_podcast_host_url():
    """Get the host URL using the .local hostname for LAN/phone access."""
    return f'http://{_LOCAL_HOSTNAME}:5001/'


def _get_video_thumbnail(video_id):
    """Get thumbnail URL for a video from videos or channel_videos table."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        # Try channel_videos first (has thumbnail_url)
        cursor.execute('SELECT video_url FROM videos WHERE id = ?', (video_id,))
        row = cursor.fetchone()
        if row and row['video_url']:
            yt_url = row['video_url']
            # Extract YouTube video ID from URL
            import re
            match = re.search(r'(?:v=|youtu\.be/)([a-zA-Z0-9_-]{11})', yt_url)
            if match:
                yt_vid = match.group(1)
                conn.close()
                return f'https://img.youtube.com/vi/{yt_vid}/hqdefault.jpg'
        conn.close()
    except Exception as e:
        print(f"Error getting thumbnail: {e}")
    return None


def extract_podcast_audio(episode_id, video_url):
    """Background function to extract audio from a YouTube video for podcast feed."""
    import yt_dlp
    import time as _time

    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # Update status to extracting
        cursor.execute('UPDATE yt_podcast_episodes SET status = ? WHERE id = ?', ('extracting', episode_id))
        conn.commit()

        timestamp = int(_time.time())
        # Get video_id (our DB id) for filename
        cursor.execute('SELECT video_id FROM yt_podcast_episodes WHERE id = ?', (episode_id,))
        row = cursor.fetchone()
        db_video_id = row['video_id'] if row else episode_id
        audio_filename = f"podcast_{db_video_id}_{timestamp}.mp3"
        output_path = os.path.join(PODCAST_AUDIO_FOLDER, audio_filename)
        output_template = os.path.join(PODCAST_AUDIO_FOLDER, f"podcast_{db_video_id}_{timestamp}.%(ext)s")

        # Find ffmpeg location
        ffmpeg_loc = None
        for p in ['/opt/homebrew/bin', '/usr/local/bin', '/usr/bin']:
            if os.path.exists(os.path.join(p, 'ffmpeg')):
                ffmpeg_loc = p
                break

        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': output_template,
            'quiet': False,
            'no_warnings': False,
            'retries': 5,
            'fragment_retries': 5,
            'extractor_retries': 5,
            'sleep_interval': 3,
            'max_sleep_interval': 10,
            'socket_timeout': 30,
            'referer': 'https://www.youtube.com/',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }
        if ffmpeg_loc:
            ydl_opts['ffmpeg_location'] = ffmpeg_loc

        print(f"🎧 Extracting podcast audio for episode {episode_id}: {video_url}")

        # Try multiple client types - android first (most reliable), then others shuffled
        import random
        other_clients = ['tv', 'ios', 'web']
        random.shuffle(other_clients)
        client_types = ['android'] + other_clients
        info = None
        last_error = None

        for client_type in client_types:
            try:
                opts = dict(ydl_opts)
                opts['extractor_args'] = {
                    'youtube': {
                        'player_client': [client_type],
                        'skip': ['dash', 'hls'],
                        'player_skip': ['webpage', 'configs'],
                    }
                }
                _time.sleep(random.uniform(1, 3))
                print(f"  Trying client type: {client_type}")
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(video_url, download=True)
                if info:
                    break
            except Exception as e:
                last_error = e
                print(f"  Client {client_type} failed: {e}")
                continue

        if not info:
            raise last_error or Exception("All client types failed")

        duration_seconds = info.get('duration', 0)

        # Wait for ffmpeg post-processing
        _time.sleep(3)

        # Find the output MP3 file
        mp3_path = os.path.join(PODCAST_AUDIO_FOLDER, audio_filename)
        if not os.path.exists(mp3_path):
            # Look for any file with our prefix
            prefix = f"podcast_{db_video_id}_{timestamp}"
            for f in os.listdir(PODCAST_AUDIO_FOLDER):
                if f.startswith(prefix) and f.endswith('.mp3'):
                    audio_filename = f
                    mp3_path = os.path.join(PODCAST_AUDIO_FOLDER, f)
                    break

        if not os.path.exists(mp3_path):
            raise Exception(f"MP3 file not created at {mp3_path}")

        audio_size = os.path.getsize(mp3_path)

        # Get thumbnail
        cursor.execute('SELECT video_id FROM yt_podcast_episodes WHERE id = ?', (episode_id,))
        ep_row = cursor.fetchone()
        thumbnail_url = _get_video_thumbnail(ep_row['video_id']) if ep_row else None

        # Update episode as ready
        cursor.execute('''
            UPDATE yt_podcast_episodes
            SET status = 'ready', audio_filename = ?, audio_size = ?,
                duration_seconds = ?, thumbnail_url = COALESCE(thumbnail_url, ?)
            WHERE id = ?
        ''', (audio_filename, audio_size, duration_seconds, thumbnail_url, episode_id))
        conn.commit()

        print(f"✅ Podcast audio ready: {audio_filename} ({audio_size / 1024 / 1024:.1f} MB, {duration_seconds}s)")

    except Exception as e:
        print(f"❌ Podcast audio extraction failed for episode {episode_id}: {e}")
        cursor.execute('''
            UPDATE yt_podcast_episodes SET status = 'error', error_message = ? WHERE id = ?
        ''', (str(e)[:500], episode_id))
        conn.commit()
    finally:
        conn.close()


def yt_podcast_extraction_worker():
    """Background worker that processes YouTube podcast audio extraction jobs."""
    import time as _time
    while True:
        try:
            episode_id, video_url = _yt_podcast_extraction_queue.get(timeout=5)
            extract_podcast_audio(episode_id, video_url)
            _yt_podcast_extraction_queue.task_done()
        except queue_module.Empty:
            continue
        except Exception as e:
            print(f"❌ Podcast extraction worker error: {e}")
            import traceback
            traceback.print_exc()


def _queue_podcast_extraction(episode_id, video_url):
    """Add an extraction job to the queue."""
    _yt_podcast_extraction_queue.put((episode_id, video_url))


def _reload_pending_podcast_episodes():
    """Reload any pending/extracting podcast episodes into the queue on startup."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    try:
        # Reset any stuck 'extracting' episodes back to pending
        cursor.execute("UPDATE yt_podcast_episodes SET status = 'pending' WHERE status = 'extracting'")
        conn.commit()

        # Load all pending episodes into the queue
        cursor.execute('''
            SELECT id, video_url FROM yt_podcast_episodes
            WHERE status = 'pending' AND video_url IS NOT NULL
            ORDER BY created_at ASC
        ''')
        pending = cursor.fetchall()

        for ep in pending:
            _yt_podcast_extraction_queue.put((ep['id'], ep['video_url']))

        if pending:
            print(f"🎧 Reloaded {len(pending)} pending podcast episodes into extraction queue")
    except Exception as e:
        print(f"⚠️ Error reloading pending podcast episodes: {e}")
    finally:
        conn.close()


def _auto_add_channel_videos_to_podcast(channel_name):
    """Auto-add videos from a channel to the podcast feed (last 30 days).
    Pulls directly from channel_videos — no processing required."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    try:
        # Pull from channel_videos (all videos, processed or not)
        cursor.execute('''
            SELECT cv.video_url, cv.title, cv.channel_name, cv.description,
                   cv.published_at, cv.thumbnail_url, cv.processed_video_id
            FROM channel_videos cv
            WHERE cv.channel_name = ?
              AND cv.video_url IS NOT NULL
              AND cv.published_at >= date('now', '-30 days')
            ORDER BY cv.published_at DESC
        ''', (channel_name,))
        videos = cursor.fetchall()

        queued = 0
        for v in videos:
            # Skip if already a podcast episode (check by video_url)
            cursor.execute('SELECT id FROM yt_podcast_episodes WHERE video_url = ?', (v['video_url'],))
            if cursor.fetchone():
                continue

            video_id = v['processed_video_id'] or 0
            thumbnail_url = v['thumbnail_url']
            if not thumbnail_url:
                # Build from YouTube URL
                import re
                match = re.search(r'(?:v=|youtu\.be/)([a-zA-Z0-9_-]{11})', v['video_url'] or '')
                if match:
                    thumbnail_url = f'https://img.youtube.com/vi/{match.group(1)}/hqdefault.jpg'

            cursor.execute('''
                INSERT INTO yt_podcast_episodes (video_id, title, channel, description, video_url,
                    thumbnail_url, published_at, status, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', 'channel')
            ''', (video_id, v['title'], v['channel_name'], (v['description'] or '')[:500],
                  v['video_url'], thumbnail_url, v['published_at']))
            ep_id = cursor.lastrowid
            conn.commit()
            _queue_podcast_extraction(ep_id, v['video_url'])
            queued += 1

        print(f"🎧 Auto-added {queued} videos from '{channel_name}' to podcast feed")
        return queued
    finally:
        conn.close()


def _format_rfc2822(dt_str):
    """Convert an ISO date string to RFC 2822 format for RSS."""
    from email.utils import format_datetime as _format_dt
    from datetime import timezone
    try:
        if not dt_str:
            return ''
        dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return _format_dt(dt)
    except Exception:
        return ''


def _format_duration_hhmmss(seconds):
    """Convert seconds to HH:MM:SS for iTunes duration tag."""
    if not seconds:
        return '00:00:00'
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def _xml_escape(text):
    """Escape special characters for XML."""
    if not text:
        return ''
    import html
    return html.escape(str(text), quote=True)


def _generate_podcast_rss(title, description, episodes, feed_url, host_url, image_url=None):
    """Generate Apple Podcasts-compatible RSS XML."""
    escaped_title = _xml_escape(title)
    escaped_desc = _xml_escape(description)
    escaped_feed = _xml_escape(feed_url)
    escaped_host = _xml_escape(host_url)
    img_tag = ''
    if image_url:
        escaped_img = _xml_escape(image_url)
        img_tag = f'<itunes:image href="{escaped_img}"/>'

    items_xml = ''
    for ep in episodes:
        ep_title = _xml_escape(ep['title'])
        ep_desc = _xml_escape(ep.get('description') or ep.get('title') or '')
        ep_filename = _xml_escape(ep.get('audio_filename') or '')
        ep_size = ep.get('audio_size') or 0
        ep_duration = _format_duration_hhmmss(ep.get('duration_seconds'))
        ep_pub = _format_rfc2822(ep.get('published_at') or ep.get('created_at'))
        ep_id = ep.get('id', 0)
        ep_thumb = _xml_escape(ep.get('thumbnail_url') or '')
        audio_url = f"{host_url}podcast-audio/{ep_filename}"

        ep_img = f'<itunes:image href="{ep_thumb}"/>' if ep_thumb else ''

        items_xml += f'''
    <item>
      <title>{ep_title}</title>
      <description>{ep_desc}</description>
      <enclosure url="{audio_url}" length="{ep_size}" type="audio/mpeg"/>
      <guid isPermaLink="false">ks-podcast-{ep_id}</guid>
      <pubDate>{ep_pub}</pubDate>
      <itunes:duration>{ep_duration}</itunes:duration>
      <itunes:summary>{ep_desc}</itunes:summary>
      {ep_img}
    </item>'''

    rss = f'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
     xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{escaped_title}</title>
    <link>{escaped_host}</link>
    <description>{escaped_desc}</description>
    <language>en-us</language>
    <atom:link href="{escaped_feed}" rel="self" type="application/rss+xml"/>
    <itunes:author>{escaped_title}</itunes:author>
    <itunes:summary>{escaped_desc}</itunes:summary>
    <itunes:explicit>false</itunes:explicit>
    <itunes:category text="Technology"/>
    {img_tag}
{items_xml}
  </channel>
</rss>'''
    return rss


# --- YouTube Podcast Endpoints ---

@app.route('/api/yt-podcast/add/<int:video_id>', methods=['POST'])
def yt_podcast_add(video_id):
    """Add a video to the podcast picks feed."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Check video exists
        cursor.execute('SELECT id, title, channel, video_url, ai_summary, published_at FROM videos WHERE id = ?', (video_id,))
        video = cursor.fetchone()
        if not video:
            conn.close()
            return jsonify({'success': False, 'error': 'Video not found'}), 404

        if not video['video_url']:
            conn.close()
            return jsonify({'success': False, 'error': 'Video has no URL'}), 400

        # Check if already a podcast episode
        cursor.execute('SELECT id, status FROM yt_podcast_episodes WHERE video_id = ?', (video_id,))
        existing = cursor.fetchone()
        if existing:
            conn.close()
            return jsonify({
                'success': True,
                'already_exists': True,
                'episode_id': existing['id'],
                'status': existing['status']
            })

        thumbnail_url = _get_video_thumbnail(video_id)

        # Determine source - if channel has an enabled feed, use 'channel'
        source = 'pick'
        if video['channel']:
            cursor.execute('SELECT id FROM yt_podcast_channel_feeds WHERE channel_name = ? AND enabled = 1',
                           (video['channel'],))
            if cursor.fetchone():
                source = 'channel'

        cursor.execute('''
            INSERT INTO yt_podcast_episodes (video_id, title, channel, description, video_url,
                thumbnail_url, published_at, status, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
        ''', (video_id, video['title'], video['channel'],
              (video['ai_summary'] or '')[:500], video['video_url'],
              thumbnail_url, video['published_at'], source))
        episode_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Queue extraction
        _queue_podcast_extraction(episode_id, video['video_url'])

        return jsonify({
            'success': True,
            'episode_id': episode_id,
            'status': 'pending',
            'message': 'Audio extraction queued'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/yt-podcast/status/<int:video_id>', methods=['GET'])
def yt_podcast_status(video_id):
    """Check if a video is already a podcast episode and its status."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT id, status, source FROM yt_podcast_episodes WHERE video_id = ?', (video_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return jsonify({'success': True, 'is_podcast': True, 'episode_id': row['id'],
                            'status': row['status'], 'source': row['source']})
        return jsonify({'success': True, 'is_podcast': False})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/yt-podcast/channel/<path:channel_name>/enable', methods=['POST'])
def yt_podcast_channel_enable(channel_name):
    """Enable a YouTube channel as a podcast feed."""
    try:
        from urllib.parse import quote as url_quote
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Insert or re-enable
        cursor.execute('''
            INSERT INTO yt_podcast_channel_feeds (channel_name, enabled)
            VALUES (?, 1)
            ON CONFLICT(channel_name) DO UPDATE SET enabled = 1
        ''', (channel_name,))
        conn.commit()
        conn.close()

        # Auto-add existing videos (last 30 days) in background
        thread = threading.Thread(target=_auto_add_channel_videos_to_podcast, args=(channel_name,))
        thread.daemon = True
        thread.start()

        feed_url = f'{_get_podcast_host_url()}podcast/channel/{url_quote(channel_name, safe="")}/feed.xml'
        return jsonify({
            'success': True,
            'channel_name': channel_name,
            'feed_url': feed_url,
            'message': f'Podcast feed enabled for {channel_name}. Existing videos from last 30 days are being queued.'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/yt-podcast/channel/<path:channel_name>/disable', methods=['DELETE'])
def yt_podcast_channel_disable(channel_name):
    """Disable a YouTube channel podcast feed."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute('UPDATE yt_podcast_channel_feeds SET enabled = 0 WHERE channel_name = ?', (channel_name,))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': f'Podcast feed disabled for {channel_name}'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/podcast/channel/<path:channel_name>/feed.xml', methods=['GET'])
def yt_podcast_channel_feed(channel_name):
    """Serve RSS feed for a YouTube channel's podcast episodes."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Get ready episodes for this channel
        cursor.execute('''
            SELECT * FROM yt_podcast_episodes
            WHERE channel = ? AND status = 'ready'
            ORDER BY published_at DESC
        ''', (channel_name,))
        episodes = [dict(row) for row in cursor.fetchall()]
        conn.close()

        host_url = _get_podcast_host_url()
        from urllib.parse import quote as url_quote
        feed_url = f"{host_url}podcast/channel/{url_quote(channel_name, safe='')}/feed.xml"

        # Try to get a thumbnail from the first episode
        image_url = None
        for ep in episodes:
            if ep.get('thumbnail_url'):
                image_url = ep['thumbnail_url']
                break

        rss = _generate_podcast_rss(
            title=channel_name,
            description=f"YouTube audio feed for {channel_name} via Knowledge Studio",
            episodes=episodes,
            feed_url=feed_url,
            host_url=host_url,
            image_url=image_url
        )

        from flask import Response
        return Response(rss, mimetype='application/rss+xml',
                        headers={'Cache-Control': 'no-cache, max-age=0'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/podcast/picks/feed.xml', methods=['GET'])
def yt_podcast_picks_feed():
    """Serve RSS feed for individual podcast picks."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('''
            SELECT * FROM yt_podcast_episodes
            WHERE source = 'pick' AND status = 'ready'
            ORDER BY created_at DESC
        ''')
        episodes = [dict(row) for row in cursor.fetchall()]
        conn.close()

        host_url = _get_podcast_host_url()
        feed_url = f"{host_url}podcast/picks/feed.xml"

        image_url = None
        for ep in episodes:
            if ep.get('thumbnail_url'):
                image_url = ep['thumbnail_url']
                break

        rss = _generate_podcast_rss(
            title="Knowledge Studio Picks",
            description="Hand-picked YouTube audio via Knowledge Studio",
            episodes=episodes,
            feed_url=feed_url,
            host_url=host_url,
            image_url=image_url
        )

        from flask import Response
        return Response(rss, mimetype='application/rss+xml',
                        headers={'Cache-Control': 'no-cache, max-age=0'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/podcast-audio/<path:filename>', methods=['GET'])
def yt_podcast_serve_audio(filename):
    """Serve podcast MP3 audio files."""
    try:
        file_path = os.path.join(PODCAST_AUDIO_FOLDER, filename)
        if not os.path.exists(file_path):
            return jsonify({'success': False, 'error': 'Audio file not found'}), 404
        return send_file(file_path, mimetype='audio/mpeg')
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/yt-podcast/episodes', methods=['GET'])
def yt_podcast_list_episodes():
    """List all YouTube podcast episodes with status."""
    try:
        source = request.args.get('source')
        channel = request.args.get('channel')

        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        query = 'SELECT * FROM yt_podcast_episodes WHERE 1=1'
        params = []
        if source:
            query += ' AND source = ?'
            params.append(source)
        if channel:
            query += ' AND channel = ?'
            params.append(channel)
        query += ' ORDER BY created_at DESC'

        cursor.execute(query, params)
        episodes = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return jsonify({'success': True, 'episodes': episodes, 'count': len(episodes)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/yt-podcast/remove/<int:episode_id>', methods=['DELETE'])
def yt_podcast_remove(episode_id):
    """Remove a podcast episode and its audio file."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('SELECT audio_filename FROM yt_podcast_episodes WHERE id = ?', (episode_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return jsonify({'success': False, 'error': 'Episode not found'}), 404

        # Delete audio file if it exists
        if row['audio_filename']:
            audio_path = os.path.join(PODCAST_AUDIO_FOLDER, row['audio_filename'])
            if os.path.exists(audio_path):
                os.remove(audio_path)

        cursor.execute('DELETE FROM yt_podcast_episodes WHERE id = ?', (episode_id,))
        conn.commit()
        conn.close()

        return jsonify({'success': True, 'message': 'Episode removed'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/yt-podcast/feeds', methods=['GET'])
def yt_podcast_list_feeds():
    """List all enabled channel feeds and the picks feed with URLs and episode counts."""
    try:
        from urllib.parse import quote as url_quote
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        host_url = _get_podcast_host_url()

        feeds = []

        # Picks feed
        cursor.execute("SELECT COUNT(*) as cnt FROM yt_podcast_episodes WHERE source = 'pick' AND status = 'ready'")
        picks_count = cursor.fetchone()['cnt']
        cursor.execute("SELECT COUNT(*) as cnt FROM yt_podcast_episodes WHERE source = 'pick'")
        picks_total = cursor.fetchone()['cnt']
        feeds.append({
            'name': 'Knowledge Studio Picks',
            'type': 'picks',
            'feed_url': f'{host_url}podcast/picks/feed.xml',
            'ready_episodes': picks_count,
            'total_episodes': picks_total
        })

        # Channel feeds
        cursor.execute('SELECT * FROM yt_podcast_channel_feeds WHERE enabled = 1 ORDER BY channel_name')
        channel_feeds = cursor.fetchall()
        for cf in channel_feeds:
            ch_name = cf['channel_name']
            cursor.execute(
                "SELECT COUNT(*) as cnt FROM yt_podcast_episodes WHERE channel = ? AND source = 'channel' AND status = 'ready'",
                (ch_name,))
            ready = cursor.fetchone()['cnt']
            cursor.execute(
                "SELECT COUNT(*) as cnt FROM yt_podcast_episodes WHERE channel = ? AND source = 'channel'",
                (ch_name,))
            total = cursor.fetchone()['cnt']
            feeds.append({
                'name': ch_name,
                'type': 'channel',
                'feed_url': f"{host_url}podcast/channel/{url_quote(ch_name, safe='')}/feed.xml",
                'ready_episodes': ready,
                'total_episodes': total
            })

        conn.close()

        # Storage info
        total_size = 0
        if os.path.exists(PODCAST_AUDIO_FOLDER):
            for f in os.listdir(PODCAST_AUDIO_FOLDER):
                fp = os.path.join(PODCAST_AUDIO_FOLDER, f)
                if os.path.isfile(fp):
                    total_size += os.path.getsize(fp)

        return jsonify({
            'success': True,
            'feeds': feeds,
            'storage_bytes': total_size,
            'storage_mb': round(total_size / 1024 / 1024, 1)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/yt-podcast/channel-status/<path:channel_name>', methods=['GET'])
def yt_podcast_channel_status(channel_name):
    """Check if a channel is enabled as a podcast feed."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM yt_podcast_channel_feeds WHERE channel_name = ? AND enabled = 1', (channel_name,))
        row = cursor.fetchone()
        conn.close()
        if row:
            from urllib.parse import quote as url_quote
            return jsonify({
                'success': True,
                'enabled': True,
                'feed_url': f'{_get_podcast_host_url()}podcast/channel/{url_quote(channel_name, safe="")}/feed.xml'
            })
        return jsonify({'success': True, 'enabled': False})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/yt-podcast/retry/<int:episode_id>', methods=['POST'])
def yt_podcast_retry(episode_id):
    """Retry extraction for a failed episode."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT id, video_url, status FROM yt_podcast_episodes WHERE id = ?', (episode_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return jsonify({'success': False, 'error': 'Episode not found'}), 404
        if row['status'] not in ('error', 'pending'):
            conn.close()
            return jsonify({'success': False, 'error': f"Episode status is '{row['status']}', not retryable"}), 400

        cursor.execute('UPDATE yt_podcast_episodes SET status = ?, error_message = NULL WHERE id = ?',
                        ('pending', episode_id))
        conn.commit()
        conn.close()

        _queue_podcast_extraction(episode_id, row['video_url'])
        return jsonify({'success': True, 'message': 'Extraction re-queued'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ========== BRIEFING ROOM API ==========

@app.route('/api/briefs', methods=['GET'])
def get_briefs():
    """Get all daily briefs, newest first"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT id, vertical, title, content, signal_count, source_count, created_at FROM daily_briefs ORDER BY created_at DESC')
        rows = cursor.fetchall()
        conn.close()
        briefs = []
        for row in rows:
            briefs.append({
                'id': row[0],
                'vertical': row[1],
                'title': row[2],
                'content': row[3],
                'signal_count': row[4] or 0,
                'source_count': row[5] or 0,
                'created_at': row[6],
            })
        return jsonify({'success': True, 'briefs': briefs})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/briefs/<int:brief_id>', methods=['GET'])
def get_brief(brief_id):
    """Get a single brief by ID"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT id, vertical, title, content, signal_count, source_count, created_at FROM daily_briefs WHERE id = ?', (brief_id,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return jsonify({'success': False, 'error': 'Brief not found'}), 404
        return jsonify({'success': True, 'brief': {
            'id': row[0],
            'vertical': row[1],
            'title': row[2],
            'content': row[3],
            'signal_count': row[4] or 0,
            'source_count': row[5] or 0,
            'created_at': row[6],
        }})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/briefs/generate', methods=['POST'])
def generate_brief_api():
    """Generate a new daily brief and save to database"""
    try:
        data = request.get_json() or {}
        vertical = data.get('vertical', 'ai_tech')

        # Route to correct pipeline based on vertical
        import sys
        import importlib

        if vertical == 'health_longevity':
            brief_dir = os.path.join(os.path.dirname(__file__), 'health_longevity_brief')
        elif vertical == 'futures_trends':
            brief_dir = os.path.join(os.path.dirname(__file__), 'futures_trends_brief')
        else:
            brief_dir = os.path.join(os.path.dirname(__file__), 'daily_brief')

        sys.path.insert(0, brief_dir)
        # Force reimport in case both verticals run in same process
        if 'collectors' in sys.modules:
            del sys.modules['collectors']
        if 'synthesizer' in sys.modules:
            del sys.modules['synthesizer']
        from collectors import collect_all
        from synthesizer import synthesize_brief

        # Collect signals (wider window for futures — twice-weekly cadence)
        hours = 96 if vertical == 'futures_trends' else 24
        collected = collect_all(
            vertical=vertical,
            hours_back=hours,
            db_path=DATABASE_PATH,
            youtube_api_key=os.environ.get('YOUTUBE_API_KEY', ''),
        )

        # Synthesize
        brief_text = synthesize_brief(collected, vertical=vertical)

        # Extract title from first heading or generate one
        title_line = brief_text.split('\n')[0] if brief_text else ''
        title = title_line.replace('#', '').strip() or f"Daily Brief — {vertical}"

        source_counts = {k: len(v) for k, v in collected.get('sources', {}).items()}
        total_signals = sum(source_counts.values())

        # Save to database
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO daily_briefs (vertical, title, content, signal_count, source_count)
            VALUES (?, ?, ?, ?, ?)
        ''', (vertical, title, brief_text, total_signals, len(source_counts)))
        brief_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return jsonify({
            'success': True,
            'brief': {
                'id': brief_id,
                'vertical': vertical,
                'title': title,
                'signal_count': total_signals,
                'source_count': len(source_counts),
            }
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/briefs/<int:brief_id>', methods=['DELETE'])
def delete_brief(brief_id):
    """Delete a brief"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM daily_briefs WHERE id = ?', (brief_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/briefs/import', methods=['POST'])
def import_brief():
    """Import a brief from markdown text (for importing existing file-based briefs)"""
    try:
        data = request.get_json()
        if not data or 'content' not in data:
            return jsonify({'success': False, 'error': 'content required'}), 400

        vertical = data.get('vertical', 'ai_tech')
        content = data['content']
        title = data.get('title', '')
        signal_count = data.get('signal_count', 0)
        source_count = data.get('source_count', 0)

        if not title:
            title_line = content.split('\n')[0] if content else ''
            title = title_line.replace('#', '').strip() or f"Imported Brief — {vertical}"

        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO daily_briefs (vertical, title, content, signal_count, source_count)
            VALUES (?, ?, ?, ?, ?)
        ''', (vertical, title, content, signal_count, source_count))
        brief_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return jsonify({'success': True, 'brief_id': brief_id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == '__main__':
    if not os.path.exists(DATABASE_PATH):
        print(f"⚠️  Database not found: {DATABASE_PATH}")
    else:
        print(f"✅ Database found: {DATABASE_PATH}")

    print("🚀 Starting YouTube Intelligence Web Server...")
    print("📱 Open browser to: http://localhost:5000")

    # Start podcast queue worker thread
    podcast_queue_thread = threading.Thread(target=process_podcast_queue_worker)
    podcast_queue_thread.daemon = True
    podcast_queue_thread.start()
    print("✅ Podcast queue worker started")

    # Start YouTube podcast audio extraction worker
    _reload_pending_podcast_episodes()  # Reload any pending episodes from DB
    yt_podcast_thread = threading.Thread(target=yt_podcast_extraction_worker)
    yt_podcast_thread.daemon = True
    yt_podcast_thread.start()
    print("✅ YouTube podcast extraction worker started")

    app.run(debug=False, host='0.0.0.0', port=5001, use_reloader=False)
