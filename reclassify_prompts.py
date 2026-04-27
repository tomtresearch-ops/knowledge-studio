#!/usr/bin/env python3
"""
Bulk reclassification script - updates prompt_used field for existing videos
without regenerating summaries
"""

import sqlite3
from youtube_processor import YouTubeProcessor

def reclassify_all_videos():
    """Scan all videos and update their prompt_used field based on content detection"""
    
    processor = YouTubeProcessor()
    conn = sqlite3.connect('youtube_intelligence.db')
    cursor = conn.cursor()
    
    # Get all completed videos
    cursor.execute('''
        SELECT id, title, full_transcript 
        FROM videos 
        WHERE status = 'completed' AND full_transcript IS NOT NULL
    ''')
    
    videos = cursor.fetchall()
    total = len(videos)
    
    print(f"🔍 Found {total} videos to reclassify...")
    print()
    
    updated = 0
    for i, (video_id, title, transcript) in enumerate(videos, 1):
        # Detect content type using the same logic as processing
        content_type = processor.detect_content_type(title, transcript)
        
        # Update the prompt_used field
        cursor.execute('''
            UPDATE videos 
            SET prompt_used = ? 
            WHERE id = ?
        ''', (content_type, video_id))
        
        updated += 1
        print(f"[{i}/{total}] ID {video_id}: {title[:60]}... → {content_type}")
    
    conn.commit()
    conn.close()
    
    print()
    print(f"✅ Successfully reclassified {updated} videos!")
    print()
    
    # Show distribution
    conn = sqlite3.connect('youtube_intelligence.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT prompt_used, COUNT(*) as count 
        FROM videos 
        WHERE status = 'completed'
        GROUP BY prompt_used 
        ORDER BY count DESC
    ''')
    
    print("📊 Distribution by prompt type:")
    for prompt_type, count in cursor.fetchall():
        print(f"   {prompt_type}: {count} videos")
    
    conn.close()

if __name__ == "__main__":
    reclassify_all_videos()


