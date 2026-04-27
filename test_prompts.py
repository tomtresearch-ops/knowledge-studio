#!/usr/bin/env python3
"""
Prompt Testing Tool for YouTube Intelligence System
Test new prompts on already processed videos without reprocessing
"""

import sqlite3
import os
import anthropic
from dotenv import load_dotenv
import json
from datetime import datetime

# Load environment variables
load_dotenv()

class PromptTester:
    def __init__(self):
        self.db_path = "youtube_intelligence.db"
        self.claude_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        
    def get_test_videos(self, limit=3):
        """Get completed videos for testing"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, title, channel, full_transcript, ai_summary
            FROM videos 
            WHERE status = 'completed' AND full_transcript IS NOT NULL
            ORDER BY processing_date DESC
            LIMIT ?
        ''', (limit,))
        
        videos = []
        for row in cursor.fetchall():
            videos.append({
                'id': row[0],
                'title': row[1],
                'channel': row[2],
                'transcript': row[3],
                'current_summary': row[4]
            })
        
        conn.close()
        return videos
    
    def load_prompt(self, prompt_path):
        """Load a prompt file"""
        try:
            with open(prompt_path, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            print(f"❌ Prompt file not found: {prompt_path}")
            return None
    
    def test_prompt_on_video(self, prompt_template, video, max_tokens=2000):
        """Test a prompt on a specific video"""
        try:
            # Format the prompt with video data
            formatted_prompt = prompt_template.format(
                title=video['title'],
                transcript=video['transcript'][:80000],  # Limit for API
                brief_summary=video['current_summary'][:500] if video['current_summary'] else 'No summary'
            )
            
            # Call Claude API
            response = self.claude_client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": formatted_prompt}]
            )
            
            return {
                'success': True,
                'output': response.content[0].text,
                'video_id': video['id'],
                'video_title': video['title']
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'video_id': video['id'],
                'video_title': video['title']
            }
    
    def compare_prompts(self, prompt_paths, test_videos=None):
        """Compare multiple prompts on the same videos"""
        if test_videos is None:
            test_videos = self.get_test_videos(limit=2)
        
        results = {}
        
        for prompt_path in prompt_paths:
            print(f"\n🧪 Testing prompt: {prompt_path}")
            prompt_template = self.load_prompt(prompt_path)
            
            if not prompt_template:
                continue
                
            prompt_results = []
            
            for video in test_videos:
                print(f"  📹 Testing on: {video['title'][:50]}...")
                result = self.test_prompt_on_video(prompt_template, video)
                prompt_results.append(result)
                
                if result['success']:
                    print(f"    ✅ Success")
                else:
                    print(f"    ❌ Error: {result['error']}")
            
            results[prompt_path] = prompt_results
        
        return results
    
    def save_test_results(self, results, filename=None):
        """Save test results to file"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"prompt_test_results_{timestamp}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"💾 Test results saved to: {filename}")
        return filename

def main():
    tester = PromptTester()
    
    print("🧪 YouTube Intelligence Prompt Tester")
    print("=" * 50)
    
    # Get available prompts
    prompt_dir = "prompts/current_best"
    available_prompts = []
    
    if os.path.exists(prompt_dir):
        for file in os.listdir(prompt_dir):
            if file.endswith('.txt'):
                available_prompts.append(os.path.join(prompt_dir, file))
    
    print(f"📁 Found {len(available_prompts)} prompts:")
    for i, prompt in enumerate(available_prompts, 1):
        print(f"  {i}. {prompt}")
    
    # Test prompts
    if available_prompts:
        print(f"\n🔬 Testing prompts on recent videos...")
        results = tester.compare_prompts(available_prompts)
        
        # Save results
        results_file = tester.save_test_results(results)
        
        print(f"\n📊 Test completed! Check {results_file} for detailed results.")
        
        # Show quick summary
        for prompt_path, prompt_results in results.items():
            success_count = sum(1 for r in prompt_results if r['success'])
            total_count = len(prompt_results)
            print(f"  {prompt_path}: {success_count}/{total_count} successful")
    else:
        print("❌ No prompts found in prompts/current_best/")

if __name__ == "__main__":
    main()















