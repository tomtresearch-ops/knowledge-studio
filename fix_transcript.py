#!/usr/bin/env python3
"""
Fix transcript cleaning for existing videos in the database
"""

import sqlite3
import json
import re

def clean_transcript_for_summary(transcript: str) -> str:
    """Aggressively clean transcript to reduce size and improve quality"""
    
    # First, check if this is raw JSON subtitle data and extract text
    if transcript.strip().startswith('{'):
        try:
            data = json.loads(transcript)
            text_parts = []
            
            # Extract text from YouTube's subtitle format
            if 'events' in data:
                for event in data['events']:
                    if 'segs' in event:
                        for seg in event['segs']:
                            if 'utf8' in seg:
                                text_parts.append(seg['utf8'])
            
            # Join all text parts
            clean_text = ''.join(text_parts)
            print(f"📝 Extracted text from JSON: {len(transcript)} -> {len(clean_text)} characters")
            
        except json.JSONDecodeError:
            # If not JSON, treat as regular text
            clean_text = transcript
    else:
        # Regular text processing
        clean_text = transcript
    
    # Gentle cleaning to preserve content quality
    # Remove timestamps and formatting
    clean_text = re.sub(r'\d{1,2}:\d{2}:\d{2}\.\d{3} --> \d{1,2}:\d{2}:\d{2}\.\d{3}', '', clean_text)
    clean_text = re.sub(r'\d{1,2}:\d{2}:\d{2} --> \d{1,2}:\d{2}:\d{2}', '', clean_text)
    clean_text = re.sub(r'\d{1,2}:\d{2}', '', clean_text)
    clean_text = re.sub(r'^\d+$', '', clean_text, flags=re.MULTILINE)
    
    # Remove HTML tags and formatting
    clean_text = re.sub(r'<[^>]+>', '', clean_text)
    clean_text = re.sub(r'\[.*?\]', '', clean_text)  # Remove [music], [applause], etc.
    clean_text = re.sub(r'\(.*?\)', '', clean_text)  # Remove (laughs), (applause), etc.
    
    # Remove control characters
    clean_text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', clean_text)
    
    # Normalize whitespace but preserve sentence structure
    clean_text = re.sub(r'\s+', ' ', clean_text)
    
    # Don't remove repeated words or escape characters - preserve content
    
    return clean_text.strip()

def fix_video_transcript(video_id):
    """Fix transcript for a specific video"""
    conn = sqlite3.connect('youtube_intelligence_dev.db')
    cursor = conn.cursor()
    
    # Get the video
    cursor.execute('SELECT id, title, full_transcript FROM videos WHERE id = ?', (video_id,))
    video = cursor.fetchone()
    
    if not video:
        print(f"Video {video_id} not found")
        return
    
    video_id, title, transcript = video
    print(f"\n🔧 Fixing transcript for: {title}")
    print(f"📊 Original length: {len(transcript)} characters")
    
    # Clean the transcript
    cleaned_transcript = clean_transcript_for_summary(transcript)
    print(f"📊 Cleaned length: {len(cleaned_transcript)} characters")
    print(f"📉 Reduction: {len(transcript) - len(cleaned_transcript)} characters ({((len(transcript) - len(cleaned_transcript)) / len(transcript) * 100):.1f}%)")
    
    # Update the database
    cursor.execute('UPDATE videos SET full_transcript = ? WHERE id = ?', (cleaned_transcript, video_id))
    conn.commit()
    conn.close()
    
    print(f"✅ Updated transcript for video {video_id}")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        video_id = int(sys.argv[1])
        fix_video_transcript(video_id)
    else:
        print("Usage: python fix_transcript.py <video_id>")
        print("Example: python fix_transcript.py 55")
