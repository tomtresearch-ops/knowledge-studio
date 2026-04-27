#!/usr/bin/env python3
"""
Podcast Feed Subscription Processor
Mirrors YouTube channel subscription system for podcasts
"""

import sqlite3
import requests
import feedparser
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse, parse_qs
from datetime import datetime
import os

DATABASE_PATH = "youtube_intelligence.db"

class PodcastProcessor:
    def __init__(self, db_path: str = DATABASE_PATH):
        self.db_path = db_path
        self.init_database()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get SQLite connection with dict row factory."""
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        # Enable WAL mode for concurrent access
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA busy_timeout=5000')
        return conn
    
    def _dict_from_row(self, row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
        """Convert SQLite Row to dict."""
        if row is None:
            return None
        return dict(row)
    
    def init_database(self):
        """Initialize database tables for podcast subscriptions"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Podcast subscriptions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS podcast_subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                podcast_name TEXT NOT NULL,
                feed_url TEXT NOT NULL UNIQUE,
                description TEXT,
                website_url TEXT,
                image_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_checked TIMESTAMP,
                enabled INTEGER DEFAULT 1
            )
        ''')
        
        # Podcast episodes table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS podcast_episodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subscription_id INTEGER NOT NULL,
                episode_guid TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                description TEXT,
                audio_url TEXT NOT NULL,
                transcript_url TEXT,
                published_at TIMESTAMP,
                duration TEXT,
                processed INTEGER DEFAULT 0,
                processed_article_id INTEGER,
                FOREIGN KEY(subscription_id) REFERENCES podcast_subscriptions(id)
            )
        ''')
        
        # Create indexes
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_podcast_episodes_subscription
            ON podcast_episodes(subscription_id, published_at DESC)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_podcast_episodes_processed
            ON podcast_episodes(processed)
        ''')
        
        # Podcast processing queue table (similar to video processing_queue)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS podcast_processing_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                episode_id INTEGER NOT NULL,
                article_id INTEGER,
                status TEXT DEFAULT 'queued',
                stage TEXT DEFAULT 'queued',
                progress_percent INTEGER DEFAULT 0,
                error_message TEXT,
                retry_count INTEGER DEFAULT 0,
                max_retries INTEGER DEFAULT 3,
                priority INTEGER DEFAULT 0,
                queued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                FOREIGN KEY(episode_id) REFERENCES podcast_episodes(id)
            )
        ''')
        
        # Create indexes for queue
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_podcast_queue_status
            ON podcast_processing_queue(status, priority DESC, queued_at ASC)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_podcast_queue_episode
            ON podcast_processing_queue(episode_id)
        ''')
        
        conn.commit()
        conn.close()
    
    def _parse_podcast_input(self, podcast_input: str) -> Dict[str, Optional[str]]:
        """Parse podcast input (RSS URL or podcast name)"""
        value = (podcast_input or '').strip()
        if not value:
            raise ValueError("Podcast input cannot be empty.")
        
        parsed = urlparse(value) if value.startswith(('http://', 'https://')) else None
        
        if parsed:
            # It's a URL - treat as RSS feed URL
            return {
                "feed_url": value,
                "search_query": None,
                "input_value": value
            }
        else:
            # It's a name - search for it
            return {
                "feed_url": None,
                "search_query": value,
                "input_value": value
            }
    
    def _search_podcast_by_name(self, podcast_name: str) -> List[Dict[str, Any]]:
        """Search iTunes API for podcast by name"""
        try:
            url = "https://itunes.apple.com/search"
            params = {
                'term': podcast_name,
                'media': 'podcast',
                'limit': 5
            }
            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
            
            results = []
            for item in data.get('results', []):
                feed_url = item.get('feedUrl')
                # Only include results with valid feed URLs
                if feed_url and feed_url.startswith(('http://', 'https://')):
                    results.append({
                        'podcast_name': item.get('collectionName'),
                        'artist': item.get('artistName'),
                        'feed_url': feed_url,
                        'artwork_url': item.get('artworkUrl600'),
                        'description': item.get('description', ''),
                        'genre': item.get('primaryGenreName', '')
                    })
            return results
        except requests.RequestException as e:
            raise ValueError(f"Failed to search iTunes API: {str(e)}")
        except Exception as e:
            raise ValueError(f"Error searching for podcast: {str(e)}")
    
    def _fetch_podcast_metadata(self, feed_url: str) -> Dict[str, Any]:
        """Fetch podcast metadata from RSS feed"""
        try:
            # Validate URL format
            if not feed_url.startswith(('http://', 'https://')):
                raise ValueError(f"Invalid feed URL format: {feed_url}")
            
            # Parse feed with error handling
            try:
                feed = feedparser.parse(feed_url)
            except Exception as parse_error:
                error_msg = str(parse_error)
                if 'pattern' in error_msg.lower() or 'expected' in error_msg.lower() or 'match' in error_msg.lower():
                    raise ValueError(f"Invalid RSS feed format. The feed URL '{feed_url}' may not be a valid RSS feed. Try searching by podcast name instead, or verify the RSS feed URL is correct.")
                raise ValueError(f"Error parsing RSS feed: {error_msg}")
            
            # Check for feedparser parsing errors
            if feed.bozo:
                bozo_exception = feed.bozo_exception
                if bozo_exception:
                    error_msg = str(bozo_exception)
                    # Handle common feedparser errors
                    if isinstance(bozo_exception, Exception):
                        error_type = type(bozo_exception).__name__
                        if 'pattern' in error_msg.lower() or 'expected' in error_msg.lower() or 'match' in error_msg.lower():
                            raise ValueError(f"Invalid RSS feed format. The feed URL '{feed_url}' appears to be malformed or not a valid RSS feed. Try searching by podcast name instead.")
                        raise ValueError(f"RSS feed parsing error ({error_type}): {error_msg}")
                    else:
                        if 'pattern' in error_msg.lower() or 'expected' in error_msg.lower() or 'match' in error_msg.lower():
                            raise ValueError(f"Invalid RSS feed format. The feed URL '{feed_url}' may not be a valid RSS feed. Try searching by podcast name instead.")
                        raise ValueError(f"RSS feed error: {error_msg}")
            
            if not feed.entries:
                raise ValueError("RSS feed contains no episodes. The feed may be empty or invalid.")
            
            # Extract podcast metadata
            feed_info = feed.feed
            
            return {
                'podcast_name': feed_info.get('title', 'Unknown Podcast'),
                'description': feed_info.get('description', ''),
                'website_url': feed_info.get('link', ''),
                'image_url': feed_info.get('image', {}).get('href', '') if hasattr(feed_info, 'image') else ''
            }
        except ValueError:
            # Re-raise ValueError as-is
            raise
        except Exception as e:
            error_msg = str(e)
            if 'pattern' in error_msg.lower() or 'expected' in error_msg.lower() or 'match' in error_msg.lower():
                raise ValueError(f"Invalid RSS feed format. Please check the feed URL '{feed_url}' or try searching by podcast name instead.")
            raise ValueError(f"Failed to fetch podcast metadata: {error_msg}")
    
    def _extract_transcript_url(self, entry) -> Optional[str]:
        """Extract transcript URL from RSS feed entry"""
        # Check podcast:transcript namespace (Podcast Namespace)
        if hasattr(entry, 'podcast_transcript'):
            transcript = entry.podcast_transcript
            if isinstance(transcript, list) and len(transcript) > 0:
                return transcript[0].get('url')
            elif isinstance(transcript, dict):
                return transcript.get('url')
        
        # Check itunes:transcript
        if hasattr(entry, 'itunes_transcript'):
            return entry.itunes_transcript
        
        # Check link rel="transcript" (Atom links)
        if hasattr(entry, 'links'):
            for link in entry.links:
                if link.get('rel') == 'transcript':
                    return link.get('href')
        
        # Check for transcript in custom fields
        if hasattr(entry, 'transcript'):
            transcript = entry.transcript
            if isinstance(transcript, str):
                return transcript
            elif isinstance(transcript, dict):
                return transcript.get('url') or transcript.get('href')
        
        return None
    
    def add_subscription(self, podcast_input: str) -> Dict[str, Any]:
        """Add podcast subscription (accepts name or RSS URL)"""
        parsed = self._parse_podcast_input(podcast_input)
        
        feed_url = parsed.get('feed_url')
        search_query = parsed.get('search_query')
        
        # If no feed URL, search iTunes
        if not feed_url and search_query:
            try:
                search_results = self._search_podcast_by_name(search_query)
                if not search_results:
                    raise ValueError(f"No podcasts found for '{search_query}'. Try searching with a different name or provide the RSS feed URL directly.")
                
                # Use first result (could be enhanced to show user selection)
                selected = search_results[0]
                feed_url = selected.get('feed_url')
                if not feed_url:
                    raise ValueError(f"Podcast '{selected.get('podcast_name', search_query)}' found but no RSS feed URL available. Try providing the RSS feed URL directly.")
            except ValueError:
                # Re-raise ValueError as-is
                raise
            except Exception as e:
                raise ValueError(f"Error searching for podcast '{search_query}': {str(e)}")
        
        if not feed_url:
            raise ValueError("Could not determine RSS feed URL")
        
        # Fetch podcast metadata
        metadata = self._fetch_podcast_metadata(feed_url)
        
        # Store subscription
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                '''
                INSERT INTO podcast_subscriptions (
                    podcast_name, feed_url, description, website_url, image_url, enabled
                ) VALUES (?, ?, ?, ?, ?, 1)
                ON CONFLICT(feed_url) DO UPDATE SET
                    podcast_name = excluded.podcast_name,
                    description = excluded.description,
                    website_url = excluded.website_url,
                    image_url = excluded.image_url,
                    enabled = 1
                ''',
                (
                    metadata['podcast_name'],
                    feed_url,
                    metadata['description'],
                    metadata['website_url'],
                    metadata['image_url']
                )
            )
            conn.commit()
            cursor.execute('SELECT * FROM podcast_subscriptions WHERE feed_url = ?', (feed_url,))
            subscription = self._dict_from_row(cursor.fetchone())
        finally:
            conn.close()
        
        # Optionally refresh episodes immediately
        if subscription:
            try:
                self.refresh_subscription(subscription['id'], max_results=50)
            except Exception as e:
                print(f"⚠️  Could not refresh subscription immediately: {e}")
        
        return subscription
    
    def refresh_subscription(self, subscription_id: int, max_results: Optional[int] = None) -> Dict[str, Any]:
        """Refresh podcast episodes from RSS feed"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM podcast_subscriptions WHERE id = ?', (subscription_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            raise ValueError("Subscription not found.")
        
        subscription = self._dict_from_row(row)
        feed_url = subscription.get('feed_url')
        
        if not feed_url:
            raise ValueError("Feed URL not found for subscription")
        
        try:
            # Validate URL format
            if not feed_url.startswith(('http://', 'https://')):
                raise ValueError(f"Invalid feed URL format: {feed_url}")
            
            # Parse feed with error handling
            try:
                feed = feedparser.parse(feed_url)
            except Exception as parse_error:
                error_msg = str(parse_error)
                if 'pattern' in error_msg.lower() or 'expected' in error_msg.lower() or 'match' in error_msg.lower():
                    raise ValueError(f"Invalid RSS feed format. The feed URL '{feed_url}' may not be a valid RSS feed.")
                raise ValueError(f"Error parsing RSS feed: {error_msg}")
            
            # Check for feedparser parsing errors
            if feed.bozo:
                bozo_exception = feed.bozo_exception
                if bozo_exception:
                    error_msg = str(bozo_exception)
                    if isinstance(bozo_exception, Exception):
                        error_type = type(bozo_exception).__name__
                        if 'pattern' in error_msg.lower() or 'expected' in error_msg.lower() or 'match' in error_msg.lower():
                            raise ValueError(f"Invalid RSS feed format. The feed URL '{feed_url}' appears to be malformed or not a valid RSS feed.")
                        raise ValueError(f"RSS feed parsing error ({error_type}): {error_msg}")
                    else:
                        if 'pattern' in error_msg.lower() or 'expected' in error_msg.lower() or 'match' in error_msg.lower():
                            raise ValueError(f"Invalid RSS feed format. The feed URL '{feed_url}' may not be a valid RSS feed.")
                        raise ValueError(f"RSS feed error: {error_msg}")
        except ValueError:
            # Re-raise ValueError as-is
            raise
        except Exception as e:
            error_msg = str(e)
            if 'pattern' in error_msg.lower() or 'expected' in error_msg.lower() or 'match' in error_msg.lower():
                raise ValueError(f"Invalid RSS feed format. Please check the feed URL '{feed_url}'.")
            raise ValueError(f"Failed to fetch RSS feed: {error_msg}")
        
        entries = feed.entries
        if max_results:
            entries = entries[:max_results]
        
        conn = self._get_connection()
        cursor = conn.cursor()
        new_episodes = 0
        updated_episodes = 0
        
        try:
            for entry in entries:
                # Extract episode data
                episode_guid = entry.get('id') or entry.get('link', '')
                title = entry.get('title', 'Untitled Episode')
                description = entry.get('description', '')
                
                # Find audio URL
                audio_url = None
                if hasattr(entry, 'enclosures'):
                    for enclosure in entry.enclosures:
                        if enclosure.get('type', '').startswith('audio'):
                            audio_url = enclosure.get('href')
                            break
                
                # Fallback: check links
                if not audio_url and hasattr(entry, 'links'):
                    for link in entry.links:
                        if link.get('type', '').startswith('audio'):
                            audio_url = link.get('href')
                            break
                
                if not audio_url:
                    continue  # Skip episodes without audio URL
                
                # Extract transcript URL
                transcript_url = self._extract_transcript_url(entry)
                
                # Parse published date
                published_at = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    published_at = datetime(*entry.published_parsed[:6]).isoformat()
                elif hasattr(entry, 'published'):
                    published_at = entry.published
                
                # Extract duration if available
                duration = None
                if hasattr(entry, 'itunes_duration'):
                    duration = entry.itunes_duration
                
                # Insert or update episode
                cursor.execute(
                    '''
                    INSERT INTO podcast_episodes (
                        subscription_id, episode_guid, title, description,
                        audio_url, transcript_url, published_at, duration
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(episode_guid) DO UPDATE SET
                        title = excluded.title,
                        description = excluded.description,
                        audio_url = excluded.audio_url,
                        transcript_url = excluded.transcript_url,
                        published_at = excluded.published_at,
                        duration = excluded.duration
                    ''',
                    (
                        subscription_id,
                        episode_guid,
                        title,
                        description,
                        audio_url,
                        transcript_url,
                        published_at,
                        duration
                    )
                )
                
                if cursor.rowcount == 1:
                    new_episodes += 1
                else:
                    updated_episodes += 1
            
            cursor.execute(
                'UPDATE podcast_subscriptions SET last_checked = CURRENT_TIMESTAMP WHERE id = ?',
                (subscription_id,)
            )
            conn.commit()
        finally:
            conn.close()
        
        return {
            "subscription": subscription,
            "inserted": new_episodes,
            "updated": updated_episodes,
            "total_entries": len(entries)
        }
    
    def list_subscriptions(self) -> List[Dict[str, Any]]:
        """List all podcast subscriptions"""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                SELECT ps.*, COUNT(pe.id) as episode_count
                FROM podcast_subscriptions ps
                LEFT JOIN podcast_episodes pe ON pe.subscription_id = ps.id
                GROUP BY ps.id
                ORDER BY ps.enabled DESC, ps.podcast_name COLLATE NOCASE ASC
            ''')
            rows = cursor.fetchall()
            return [self._dict_from_row(row) for row in rows]
        finally:
            conn.close()
    
    def remove_subscription(self, subscription_id: int) -> bool:
        """Remove podcast subscription"""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('DELETE FROM podcast_subscriptions WHERE id = ?', (subscription_id,))
            cursor.execute('DELETE FROM podcast_episodes WHERE subscription_id = ?', (subscription_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
    
    def toggle_subscription(self, subscription_id: int) -> Dict[str, Any]:
        """Enable or disable podcast subscription"""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT enabled FROM podcast_subscriptions WHERE id = ?', (subscription_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError("Subscription not found.")
            new_value = 0 if row['enabled'] else 1
            cursor.execute(
                'UPDATE podcast_subscriptions SET enabled = ? WHERE id = ?',
                (new_value, subscription_id)
            )
            conn.commit()
            cursor.execute('SELECT * FROM podcast_subscriptions WHERE id = ?', (subscription_id,))
            return self._dict_from_row(cursor.fetchone())
        finally:
            conn.close()
    
    def get_podcast_episodes(
        self,
        subscription_id: Optional[int] = None,
        processed: Optional[bool] = None,
        limit: int = 50,
        offset: int = 0,
        order: str = 'desc'
    ) -> Dict[str, Any]:
        """Get podcast episodes"""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            order_clause = 'published_at DESC' if order.lower() == 'desc' else 'published_at ASC'
            query = '''
                SELECT pe.*, ps.podcast_name AS subscription_name
                FROM podcast_episodes pe
                LEFT JOIN podcast_subscriptions ps ON ps.id = pe.subscription_id
                WHERE 1=1
            '''
            params: List[Any] = []
            
            if subscription_id:
                query += ' AND pe.subscription_id = ?'
                params.append(subscription_id)
            
            if processed is not None:
                query += ' AND pe.processed = ?'
                params.append(1 if processed else 0)
            
            query += f' ORDER BY pe.{order_clause} LIMIT ? OFFSET ?'
            params.extend([limit, offset])
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            episodes = [self._dict_from_row(row) for row in rows]
            
            # Get total count
            count_query = '''
                SELECT COUNT(*) FROM podcast_episodes pe WHERE 1=1
            '''
            count_params = []
            if subscription_id:
                count_query += ' AND pe.subscription_id = ?'
                count_params.append(subscription_id)
            if processed is not None:
                count_query += ' AND pe.processed = ?'
                count_params.append(1 if processed else 0)
            
            cursor.execute(count_query, count_params)
            total = cursor.fetchone()[0]
            
            return {
                'episodes': episodes,
                'total': total,
                'limit': limit,
                'offset': offset
            }
        finally:
            conn.close()
    
    def get_episode(self, episode_id: int) -> Optional[Dict[str, Any]]:
        """Get a single episode by ID"""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                SELECT pe.*, ps.podcast_name AS subscription_name
                FROM podcast_episodes pe
                LEFT JOIN podcast_subscriptions ps ON ps.id = pe.subscription_id
                WHERE pe.id = ?
            ''', (episode_id,))
            row = cursor.fetchone()
            return self._dict_from_row(row)
        finally:
            conn.close()
    
    def add_episode_to_queue(self, episode_id: int, article_id: Optional[int] = None, priority: int = 0, max_retries: int = 3) -> Dict[str, Any]:
        """Add an episode to the processing queue"""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            # Check if already in queue
            cursor.execute('''
                SELECT * FROM podcast_processing_queue
                WHERE episode_id = ? AND status IN ('queued', 'processing')
            ''', (episode_id,))
            existing = cursor.fetchone()
            if existing:
                return self._dict_from_row(existing)
            
            # Add to queue
            cursor.execute('''
                INSERT INTO podcast_processing_queue 
                (episode_id, article_id, status, stage, progress_percent, priority, max_retries)
                VALUES (?, ?, 'queued', 'queued', 0, ?, ?)
            ''', (episode_id, article_id, priority, max_retries))
            queue_id = cursor.lastrowid
            conn.commit()
            
            cursor.execute('SELECT * FROM podcast_processing_queue WHERE id = ?', (queue_id,))
            return self._dict_from_row(cursor.fetchone())
        finally:
            conn.close()
    
    def get_queue_items(self, status: Optional[str] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get queue items with optional status filter"""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            query = '''
                SELECT q.*, pe.title, pe.audio_url, pe.transcript_url, ps.podcast_name
                FROM podcast_processing_queue q
                JOIN podcast_episodes pe ON q.episode_id = pe.id
                JOIN podcast_subscriptions ps ON pe.subscription_id = ps.id
                WHERE (? IS NULL OR q.status = ?)
                ORDER BY
                    CASE q.status
                        WHEN 'processing' THEN 0
                        WHEN 'queued' THEN 1
                        WHEN 'pending_retry' THEN 2
                        ELSE 3
                    END,
                    q.priority DESC,
                    q.queued_at ASC
            '''
            params = [status, status]
            if limit:
                query += ' LIMIT ?'
                params.append(limit)
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [self._dict_from_row(row) for row in rows]
        finally:
            conn.close()
    
    def update_queue_item(self, queue_id: int, **kwargs) -> bool:
        """Update a queue item"""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            updates = []
            params = []
            for key, value in kwargs.items():
                updates.append(f"{key} = ?")
                params.append(value)
            if not updates:
                return False
            params.append(queue_id)
            cursor.execute(f'''
                UPDATE podcast_processing_queue
                SET {', '.join(updates)}
                WHERE id = ?
            ''', params)
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
    
    def get_next_queue_item(self) -> Optional[Dict[str, Any]]:
        """Get the next item to process from the queue"""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                SELECT * FROM podcast_processing_queue
                WHERE status IN ('queued', 'pending_retry')
                ORDER BY priority DESC, queued_at ASC
                LIMIT 1
            ''')
            return self._dict_from_row(cursor.fetchone())
        finally:
            conn.close()

