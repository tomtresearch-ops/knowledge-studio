#!/usr/bin/env python3
"""
Flask Backend Server for YouTube Intelligence System
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
                   ai_summary, processing_date, status, filename
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
                'url': row[3],
                'hasTranscript': bool(row[4]),
                'transcriptLength': len(row[4]) if row[4] else 0,
                'summary': str(row[5])[:200] if row[5] else "No summary",
                'date': row[6] or 'Unknown date',
                'status': row[7],
                'filename': row[8],
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
                   ai_summary, processing_date, status, filename
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
                'url': row[3],
                'hasTranscript': bool(row[4]),
                'transcriptLength': len(row[4]) if row[4] else 0,
                'summary': str(row[5])[:200] if row[5] else "No summary",
                'date': row[6] or 'Unknown date',
                'status': row[7],
                'filename': row[8],
                'duration': 'Unknown duration'
            })
        
        conn.close()
        return videos
    
    def get_video_by_id(self, video_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, title, channel, video_url, full_transcript,
                   ai_summary, processing_date, status, filename
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
            'url': row[3],
            'transcript': row[4] or '',
            'summary_data': {'ai_summary': str(row[5]) if row[5] else ''},
            'date': row[6] or 'Unknown date',
            'status': row[7],
            'filename': row[8]
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
            model="claude-3-5-sonnet-20240620",
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
            model="claude-3-5-sonnet-20240620",
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
    
    print("🚀 Starting YouTube Intelligence Web Server...")
    print("📱 Open browser to: http://localhost:5000")
    
    app.run(debug=True, host='0.0.0.0', port=5001)
