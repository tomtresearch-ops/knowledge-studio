#!/usr/bin/env python3
import sqlite3

def search_screenshots(query):
    conn = sqlite3.connect("database/screenshots.db")
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT filename, ai_analysis, timestamp 
        FROM screenshots 
        WHERE ai_analysis LIKE ? OR filename LIKE ?
    """, (f"%{query}%", f"%{query}%"))
    
    results = cursor.fetchall()
    conn.close()
    
    for filename, analysis, timestamp in results:
        print(f"\n--- {filename} ({timestamp}) ---")
        print(analysis[:200] + "..." if len(analysis) > 200 else analysis)

if __name__ == "__main__":
    query = input("Search for: ")
    search_screenshots(query)
