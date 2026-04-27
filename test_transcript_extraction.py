#!/usr/bin/env python3
"""Test transcript extraction with youtube-transcript-api"""

import sys
from youtube_processor import YouTubeProcessor

def test_transcript(video_url: str):
    """Test transcript extraction on a single video"""
    processor = YouTubeProcessor()
    
    print(f"🧪 Testing transcript extraction for: {video_url}")
    print("-" * 60)
    
    transcript = processor.get_transcript(video_url)
    
    if transcript:
        print(f"\n✅ SUCCESS!")
        print(f"📊 Transcript length: {len(transcript)} characters")
        print(f"📝 First 500 characters:")
        print("-" * 60)
        print(transcript[:500])
        print("-" * 60)
        return True
    else:
        print(f"\n❌ FAILED: Could not extract transcript")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 test_transcript_extraction.py <youtube_url>")
        print("\nExample:")
        print("  python3 test_transcript_extraction.py 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'")
        sys.exit(1)
    
    video_url = sys.argv[1]
    success = test_transcript(video_url)
    sys.exit(0 if success else 1)

