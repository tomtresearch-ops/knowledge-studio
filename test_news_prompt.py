#!/usr/bin/env python3

import sqlite3
import os
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

def test_news_prompt():
    # Get the Mo Gawdat video
    conn = sqlite3.connect('youtube_intelligence.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, title, full_transcript FROM videos WHERE title LIKE "%Mo Gawdat%" ORDER BY processing_date DESC LIMIT 1')
    video = cursor.fetchone()
    conn.close()

    if not video:
        print('No Mo Gawdat video found')
        return

    video_id, title, transcript = video
    print(f'Processing: {title}')
    
    # Read the news prompt
    with open('prompts/current_best/news_prompt.txt', 'r') as f:
        news_prompt = f.read()
    
    # Replace placeholders
    custom_prompt = news_prompt.replace('{title}', title).replace('{transcript}', transcript)
    
    print('\nGenerating summary using news prompt with Haiku 4.5...')
    
    # Initialize Claude client
    claude_client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
    
    # Generate the summary
    response = claude_client.messages.create(
        model='claude-haiku-4-5-20251001',
        max_tokens=4000,
        messages=[{'role': 'user', 'content': custom_prompt}]
    )
    
    summary = response.content[0].text
    
    print('\n✅ Summary generated successfully!')
    print(f'Summary length: {len(summary)} characters')
    print('\nFirst 500 characters preview:')
    print(summary[:500] + '...')
    
    # Save this as a test summary for comparison
    with open('test_news_prompt_summary.txt', 'w') as f:
        f.write(summary)
    
    print('\n📁 Test summary saved to: test_news_prompt_summary.txt')
    print('\nYou can now compare this with the current interview prompt version!')

if __name__ == "__main__":
    test_news_prompt()
