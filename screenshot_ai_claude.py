#!/usr/bin/env python3
"""
Screenshot AI with Claude Vision
"""

import os
import json
import sqlite3
import base64
from datetime import datetime
from pathlib import Path
import time

from PIL import Image
import anthropic
from dotenv import load_dotenv
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Load environment variables
load_dotenv()

class ScreenshotProcessor:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.db_path = "database/screenshots.db"
        self.input_folder = "input"
        self.processed_folder = "processed"
        self.setup_database()
        
    def setup_database(self):
        """Create database and table if they don't exist"""
        os.makedirs("database", exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS screenshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                file_path TEXT NOT NULL,
                extracted_text TEXT,
                ai_analysis TEXT,
                tags TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
        print("Database setup complete")
    
    def encode_image(self, image_path):
        """Convert image to base64 for Claude API"""
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    
    def analyze_screenshot(self, image_path):
        """Send image to Claude Vision for analysis"""
        try:
            base64_image = self.encode_image(image_path)
            file_ext = Path(image_path).suffix.lower()
            media_type = f"image/jpeg" if file_ext in ['.jpg', '.jpeg'] else f"image/png"
            
            message = self.client.messages.create(
                model="claude-3-5-sonnet-20240620",
                max_tokens=1000,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": base64_image,
                                },
                            },
                            {
                                "type": "text",
                                "text": "Analyze this screenshot. Extract any text, prices, trading indicators, chart patterns, or financial data. Focus on crypto/trading content. Provide insights about what this shows."
                            }
                        ],
                    }
                ],
            )
            
            return message.content[0].text
            
        except Exception as e:
            print(f"Error analyzing image: {e}")
            return f"Error: {str(e)}"
    
    def process_image(self, image_path):
        """Process a single image"""
        print(f"Processing: {image_path}")
        analysis = self.analyze_screenshot(image_path)
        
        filename = Path(image_path).name
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO screenshots (filename, file_path, ai_analysis)
            VALUES (?, ?, ?)
        ''', (filename, str(image_path), analysis))
        
        conn.commit()
        conn.close()
        
        os.makedirs(self.processed_folder, exist_ok=True)
        processed_path = Path(self.processed_folder) / filename
        os.rename(image_path, processed_path)
        
        print(f"Completed: {filename}")
        return analysis

if __name__ == "__main__":
    processor = ScreenshotProcessor()
    
    input_path = Path("input")
    for image_file in input_path.glob("*"):
        if image_file.suffix.lower() in ['.jpg', '.jpeg', '.png', '.heic']:
            processor.process_image(str(image_file))
    
    print("Screenshot processor ready. Add images to 'input' folder to process them.")
