#!/usr/bin/env python3
"""
Quick Prompt Testing - Interactive tool for testing prompts on existing videos
"""

import sqlite3
import os
import anthropic
from dotenv import load_dotenv

load_dotenv()

def get_videos():
    """Get completed videos for testing"""
    conn = sqlite3.connect("youtube_intelligence.db")
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, title, channel, full_transcript
        FROM videos 
        WHERE status = 'completed' AND full_transcript IS NOT NULL
        ORDER BY processing_date DESC
        LIMIT 10
    ''')
    
    videos = []
    for row in cursor.fetchall():
        videos.append({
            'id': row[0],
            'title': row[1],
            'channel': row[2],
            'transcript': row[3]
        })
    
    conn.close()
    return videos

def test_prompt_on_video(prompt_text, video):
    """Test a prompt on a specific video"""
    claude_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    
    # Format the prompt
    formatted_prompt = prompt_text.format(
        title=video['title'],
        transcript=video['transcript'][:60000]  # Limit for API
    )
    
    try:
        response = claude_client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=2000,
            messages=[{"role": "user", "content": formatted_prompt}]
        )
        return response.content[0].text
    except Exception as e:
        return f"Error: {e}"

def main():
    print("🧪 Quick Prompt Tester")
    print("=" * 30)
    
    # Get videos
    videos = get_videos()
    print(f"📹 Found {len(videos)} videos for testing")
    
    for i, video in enumerate(videos[:5], 1):
        print(f"{i}. {video['title'][:60]}...")
    
    # Get video selection
    try:
        choice = int(input(f"\nSelect video (1-{min(5, len(videos))}): ")) - 1
        selected_video = videos[choice]
        print(f"\n📹 Selected: {selected_video['title']}")
    except (ValueError, IndexError):
        print("❌ Invalid selection")
        return
    
    # Get prompt
    print("\n📝 Enter your prompt (use {title} and {transcript} as placeholders):")
    print("(Or type 'file:filename.txt' to load from file)")
    
    prompt_input = input("Prompt: ").strip()
    
    if prompt_input.startswith('file:'):
        # Load from file
        filename = prompt_input[5:].strip()
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                prompt_text = f.read()
            print(f"✅ Loaded prompt from {filename}")
        except FileNotFoundError:
            print(f"❌ File not found: {filename}")
            return
    else:
        prompt_text = prompt_input
    
    # Test the prompt
    print(f"\n🔬 Testing prompt on video...")
    print("=" * 50)
    
    result = test_prompt_on_video(prompt_text, selected_video)
    
    print("📊 RESULT:")
    print("=" * 50)
    print(result)
    print("=" * 50)
    
    # Ask if they want to save the result
    save = input("\n💾 Save this result to file? (y/n): ").lower().strip()
    if save == 'y':
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"test_result_{timestamp}.txt"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"Video: {selected_video['title']}\n")
            f.write(f"Prompt: {prompt_text}\n")
            f.write(f"Result:\n{result}\n")
        print(f"💾 Saved to {filename}")

if __name__ == "__main__":
    from datetime import datetime
    main()















