#!/usr/bin/env python3
import sqlite3

def add_summary():
    title = input("Title: ")
    project = input("Project tag: ")
    source_url = input("Source URL (optional): ")
    print("Summary text (press Enter twice when done):")
    
    lines = []
    while True:
        line = input()
        if line == "":
            break
        lines.append(line)
    
    summary_text = "\n".join(lines)
    
    conn = sqlite3.connect('database/screenshots.db')
    cursor = conn.cursor()
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS manual_summaries (
        id INTEGER PRIMARY KEY,
        title TEXT,
        summary_text TEXT,
        project_tag TEXT,
        source_url TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    
    cursor.execute('INSERT INTO manual_summaries (title, summary_text, project_tag, source_url) VALUES (?, ?, ?, ?)',
                   (title, summary_text, project, source_url))
    
    conn.commit()
    conn.close()
    print("Summary added!")

if __name__ == "__main__":
    add_summary()