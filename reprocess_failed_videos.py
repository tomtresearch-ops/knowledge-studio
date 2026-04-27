#!/usr/bin/env python3
"""
Reprocess videos that failed with summary generation errors
"""

import sqlite3
from youtube_processor import YouTubeProcessor

def reprocess_failed_videos():
    """Reprocess videos that have summary generation errors"""
    processor = YouTubeProcessor()
    
    # Connect to database
    conn = sqlite3.connect(processor.db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Find videos with summary generation errors
    cursor.execute('''
        SELECT id, title, video_url, full_transcript, ai_summary
        FROM videos 
        WHERE ai_summary LIKE '%Summary generation error%'
        AND full_transcript IS NOT NULL
        AND full_transcript != ''
        ORDER BY id DESC
        LIMIT 10
    ''')
    
    failed_videos = cursor.fetchall()
    conn.close()
    
    if not failed_videos:
        print("No failed videos found to reprocess")
        return
    
    print(f"Found {len(failed_videos)} videos with errors to reprocess...\n")
    
    for video in failed_videos:
        video_id = video['id']
        title = video['title']
        transcript = video['full_transcript']
        
        print(f"Reprocessing: {title}")
        print(f"  Video ID: {video_id}")
        print(f"  Transcript length: {len(transcript)} characters")
        
        try:
            # Generate new summary
            summary, prompt_used = processor.generate_summary(transcript, title)
            
            # Check if it succeeded (not an error message)
            if summary and not summary.startswith("Summary generation error"):
                # Update database with new summary
                conn = sqlite3.connect(processor.db_path)
                cursor = conn.cursor()
                
                cursor.execute('''
                    UPDATE videos 
                    SET ai_summary = ?, prompt_used = ?
                    WHERE id = ?
                ''', (summary, prompt_used, video_id))
                
                conn.commit()
                conn.close()
                
                print(f"  ✅ Successfully reprocessed!")
            else:
                print(f"  ❌ Still failed: {summary[:100] if summary else 'No summary'}")
                
        except Exception as e:
            print(f"  ❌ Error during reprocessing: {e}")
        
        print()
    
    print("✅ Reprocessing complete!")

if __name__ == "__main__":
    reprocess_failed_videos()



