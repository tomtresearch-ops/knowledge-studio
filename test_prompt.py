import sqlite3
from anthropic import Anthropic

# Get Mo Gawdat transcript
conn = sqlite3.connect('youtube_intelligence.db')
cursor = conn.cursor()
cursor.execute("SELECT full_transcript, title FROM videos WHERE id = 19")
result = cursor.fetchone()
transcript = result[0][:50000]  # First 50k chars
title = result[1]
conn.close()

# Load prompt
with open('prompts/youtube_summary.txt', 'r') as f:
    prompt = f.read()

# Get API key from processor
exec(open('youtube_processor.py').read())

# Test with Haiku
client = Anthropic(api_key=CLAUDE_API_KEY)
response = client.messages.create(
    model="claude-3-5-haiku-20241022",
    max_tokens=4000,
    messages=[{
        "role": "user",
        "content": prompt.replace('{title}', title).replace('{transcript}', transcript)
    }]
)

print(response.content[0].text)
