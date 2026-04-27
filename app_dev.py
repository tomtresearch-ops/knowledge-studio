#!/usr/bin/env python3
"""
Flask Development Server for YouTube Intelligence System
Hot reloading enabled for development
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import json
import os
import anthropic
from dotenv import load_dotenv
import shutil
from datetime import datetime
import threading
import time

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)

# Configuration
DATABASE_PATH = "youtube_intelligence.db"
CLAUDE_API_KEY = os.getenv("ANTHROPIC_API_KEY")

claude_client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

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
    
    # Fallback to general LLM Brief prompt
    if not prompt_template:
        general_file = "prompts/current_best/general_llm_brief.txt"
        try:
            with open(general_file, 'r', encoding='utf-8') as f:
                prompt_template = f.read()
            print(f"✅ Using fallback LLM Brief prompt: general_llm_brief.txt")
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
    
    def get_connection(self):
        return sqlite3.connect(self.db_path)
    
    def get_all_videos(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, title, channel, video_url, full_transcript, 
                   ai_summary, processing_date, status, filename, confidence_score
            FROM videos 
            WHERE status = 'completed'
            ORDER BY processing_date DESC
        ''')
        
        videos = []
        for row in cursor.fetchall():
            videos.append({
                'id': row[0],
                'title': row[1] or 'Untitled Video',
                'channel': row[2] or 'Unknown Channel',
                'video_url': row[3],
                'full_transcript': row[4],  # Include actual transcript data
                'hasTranscript': bool(row[4]),
                'transcriptLength': len(row[4]) if row[4] else 0,
                'summary': str(row[5]) if row[5] else "No summary",
                'ai_summary': row[5],  # Send full ai_summary for enhanced display
                'date': row[6] or 'Unknown date',
                'status': row[7],
                'filename': row[8],
                'confidence_score': row[9] or 0,
                'duration': 'Unknown duration'
            })
        
        conn.close()
        return videos
    
    def search_videos(self, query):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        search_term = f"%{query}%"
        cursor.execute('''
            SELECT id, title, channel, video_url, full_transcript,
                   ai_summary, processing_date, status, filename, confidence_score
            FROM videos 
            WHERE status = 'completed' 
            AND (title LIKE ? OR channel LIKE ? OR full_transcript LIKE ?)
            ORDER BY processing_date DESC
        ''', (search_term, search_term, search_term))
        
        videos = []
        for row in cursor.fetchall():
            videos.append({
                'id': row[0],
                'title': row[1] or 'Untitled Video',
                'channel': row[2] or 'Unknown Channel',
                'video_url': row[3],
                'full_transcript': row[4],  # Include actual transcript data
                'hasTranscript': bool(row[4]),
                'transcriptLength': len(row[4]) if row[4] else 0,
                'summary': str(row[5]) if row[5] else "No summary",
                'ai_summary': row[5],  # Send full ai_summary for enhanced display
                'date': row[6] or 'Unknown date',
                'status': row[7],
                'filename': row[8],
                'confidence_score': row[9] or 0,
                'duration': 'Unknown duration'
            })
        
        conn.close()
        return videos
    
    def get_video_by_id(self, video_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, title, channel, video_url, full_transcript,
                   ai_summary, processing_date, status, filename, confidence_score
            FROM videos 
            WHERE id = ?
        ''', (video_id,))
        
        row = cursor.fetchone()
        if not row:
            conn.close()
            return None
        
        video = {
            'id': row[0],
            'title': row[1] or 'Untitled Video',
            'channel': row[2] or 'Unknown Channel',
            'video_url': row[3],
            'transcript': row[4] or '',
            'ai_summary': row[5],  # Full ai_summary
            'summary_data': {'ai_summary': str(row[5]) if row[5] else ''},
            'date': row[6] or 'Unknown date',
            'status': row[7],
            'filename': row[8],
            'confidence_score': row[9] or 0
        }
        
        conn.close()
        return video

db_service = DatabaseService(DATABASE_PATH)

# Import the YouTube processor
from youtube_processor import YouTubeProcessor

# Initialize processor
processor = YouTubeProcessor()

# Ensure screenshots folder exists
SCREENSHOTS_FOLDER = "screenshots"
os.makedirs(SCREENSHOTS_FOLDER, exist_ok=True)

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
            return f.read()
    except FileNotFoundError:
        return '<h1>Library page not found</h1><p><a href="/">← Back to Capture</a></p>'

@app.route('/stats')
def stats():
    try:
        with open('stats.html', 'r') as f:
            return f.read()
    except FileNotFoundError:
        return '<h1>Stats page not found</h1><p><a href="/">← Back to Capture</a></p>'

@app.route('/debug')
def debug():
    try:
        with open('debug.html', 'r') as f:
            return f.read()
    except FileNotFoundError:
        return '<h1>Debug page not found</h1>'

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
        
        transcript = video['transcript']
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
            model="claude-3-5-sonnet-20241022",
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
        
        transcript = video['transcript']
        if not transcript:
            return jsonify({'success': False, 'error': 'No transcript available'}), 400
        
        # Detect content type for domain-specific synthesis
        content_type = processor.detect_content_type(video['title'], transcript)
        
        # Load the appropriate prompt based on content type
        prompt_file = f"prompts/current_best/{content_type}_prompt.txt"
        try:
            with open(prompt_file, 'r', encoding='utf-8') as f:
                prompt_template = f.read()
        except FileNotFoundError:
            # Fallback to general prompt
            with open("prompts/current_best/general_prompt.txt", 'r', encoding='utf-8') as f:
                prompt_template = f.read()
        
        # Format the prompt
        prompt = prompt_template.format(title=video['title'], transcript=transcript)
        
        # Generate new brief with rate limit handling
        import time
        max_retries = 3
        base_delay = 60  # Start with 60 seconds
        
        for attempt in range(max_retries):
            try:
                response = claude_client.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=4000,
                    messages=[{"role": "user", "content": prompt}]
                )
                break  # Success, exit retry loop
                
            except Exception as e:
                error_str = str(e)
                if "rate_limit_error" in error_str and attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)  # Exponential backoff
                    print(f"⏳ Rate limit hit, waiting {delay} seconds before retry {attempt + 2}/{max_retries}...")
                    time.sleep(delay)
                    continue
                else:
                    return jsonify({'success': False, 'error': f'API Error: {error_str}'}), 500
        
        # Update the database with new brief
        conn = db_service.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE videos SET ai_summary = ? WHERE id = ?",
            (response.content[0].text, video_id)
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
        
        transcript = video['transcript']
        if not transcript:
            return jsonify({'success': False, 'error': 'No transcript available'}), 400
        
        # Detect content type for domain-specific synthesis
        content_type = processor.detect_content_type(video['title'], transcript)
        
        # Get brief summary for context
        brief_summary = video.get('ai_summary', '')[:500] if video.get('ai_summary') else 'No summary available'
        
        # Load category-specific LLM Brief prompt
        llm_brief_prompt = load_llm_brief_prompt(content_type, video['title'], transcript, brief_summary)

        response = claude_client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=4000,
            messages=[{"role": "user", "content": llm_brief_prompt}]
        )
        
        return jsonify({
            'success': True,
            'brief': response.content[0].text,
            'video_id': video_id
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        data = request.get_json()
        question = data.get('question', '')
        
        if not question:
            return jsonify({'success': False, 'error': 'Question required'}), 400
        
        videos = db_service.search_videos(question)[:3]
        
        if not videos:
            return jsonify({
                'success': True,
                'response': "No relevant videos found for this question."
            })
        
        relevant_content = []
        for video in videos:
            full_video = db_service.get_video_by_id(video['id'])
            if full_video and full_video['transcript']:
                relevant_content.append(f"Video: {full_video['title']}\nContent: {full_video['transcript'][:1500]}")
        
        prompt = f"Question: {question}\n\nRelevant videos:\n{chr(10).join(relevant_content)}\n\nAnswer based on this content:"
        
        response = claude_client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )
        
        return jsonify({
            'success': True,
            'response': response.content[0].text,
            'question': question,
            'videos_searched': len(videos)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/upload', methods=['POST'])
def upload_files():
    try:
        if 'files' not in request.files:
            return jsonify({'success': False, 'error': 'No files provided'}), 400
        
        files = request.files.getlist('files')
        uploaded_files = []
        
        for file in files:
            if file.filename == '':
                continue
                
            # Save file to screenshots folder
            filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
            file_path = os.path.join(SCREENSHOTS_FOLDER, filename)
            file.save(file_path)
            uploaded_files.append(filename)
            
            print(f"📸 File uploaded: {filename}")
        
        return jsonify({
            'success': True,
            'message': f'Successfully uploaded {len(uploaded_files)} file(s)',
            'files': uploaded_files
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/videos/<int:video_id>', methods=['DELETE'])
def delete_video(video_id):
    try:
        conn = db_service.get_connection()
        cursor = conn.cursor()
        
        # Check if video exists
        cursor.execute('SELECT title FROM videos WHERE id = ?', (video_id,))
        video = cursor.fetchone()
        
        if not video:
            conn.close()
            return jsonify({'success': False, 'error': 'Video not found'}), 404
        
        # Delete the video
        cursor.execute('DELETE FROM videos WHERE id = ?', (video_id,))
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': f'Successfully deleted video: {video[0]}',
            'video_id': video_id
        })
        
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

if __name__ == '__main__':
    if not os.path.exists(DATABASE_PATH):
        print(f"⚠️  Database not found: {DATABASE_PATH}")
    else:
        print(f"✅ Database found: {DATABASE_PATH}")
    
    print("🚀 Starting YouTube Intelligence Development Server...")
    print("🔥 Hot reloading ENABLED - changes will auto-reload")
    print("📱 Open browser to: http://localhost:5002")
    print("📱 Library: http://localhost:5002/library")
    print("")
    print("💡 Edit prompts in prompts/current_best/ and HTML files to see changes instantly!")
    
    # Enable hot reloading with proper configuration
    app.run(
        debug=True,           # Enable debug mode
        host='0.0.0.0',       # Allow external connections
        port=5002,            # Different port from production
        use_reloader=True,    # Enable auto-reload
        threaded=True,        # Enable threading
        extra_files=[         # Watch these files for changes
            'interface.html',
            'library.html', 
            'stats.html',
            'debug.html',
            'prompts/current_best/'
        ]
    )
