#!/usr/bin/env python3
"""
YouTube Intelligence Background Service
Runs the file monitoring and processing in the background
"""

import os
import sys
import time
import signal
import subprocess
from datetime import datetime
from pathlib import Path
from youtube_processor import YouTubeProcessor, ScreenshotHandler
from watchdog.observers import Observer

def should_refresh_feeds():
    """Check if it's time for a scheduled feed refresh (9am, 3pm, 9pm)"""
    now = datetime.now()
    current_hour = now.hour
    current_minute = now.minute

    # Refresh at 9am, 3pm (15:00), and 9pm (21:00)
    # Trigger within first 5 minutes of each scheduled hour
    scheduled_hours = [9, 15, 21]

    if current_hour in scheduled_hours and current_minute < 5:
        return True
    return False

def should_generate_briefs():
    """Check if it's time for the nightly brief generation (9:30 PM)

    Runs at 9:30 PM to give the 9 PM feed refresh time to complete first.
    Generates all three verticals: ai_tech, health_longevity, futures_trends.
    """
    now = datetime.now()
    # 9:30-9:35 PM window — after the 9 PM feed refresh has finished
    if now.hour == 21 and 30 <= now.minute < 35:
        return True
    return False

def generate_all_briefs():
    """Generate daily briefs for all three verticals via the local API"""
    import urllib.request
    import json

    verticals = ['ai_tech', 'health_longevity', 'futures_trends']
    results = {}

    for vertical in verticals:
        try:
            print(f"📝 Generating {vertical} brief...")
            payload = json.dumps({'vertical': vertical}).encode('utf-8')
            req = urllib.request.Request(
                'http://localhost:5001/api/briefs/generate',
                data=payload,
                method='POST',
                headers={'Content-Type': 'application/json'}
            )
            with urllib.request.urlopen(req, timeout=120) as response:
                data = json.loads(response.read().decode())

            if data.get('success'):
                signal_count = data.get('brief', {}).get('signal_count', '?')
                print(f"   ✅ {vertical}: {signal_count} signals synthesized")
                results[vertical] = 'success'
            else:
                print(f"   ⚠️ {vertical}: {data.get('error', 'Unknown error')}")
                results[vertical] = 'failed'
        except urllib.error.URLError as e:
            print(f"   ⚠️ {vertical}: Could not connect to server: {e}")
            results[vertical] = 'error'
        except Exception as e:
            print(f"   ⚠️ {vertical}: {e}")
            results[vertical] = 'error'

    succeeded = sum(1 for v in results.values() if v == 'success')
    print(f"📊 Brief generation complete: {succeeded}/{len(verticals)} succeeded")
    return results

def refresh_all_feeds():
    """Refresh all subscribed feeds (YouTube, newsletters, podcasts) via the local API"""
    import urllib.request
    import json

    try:
        print("📡 Refreshing all feeds...")
        req = urllib.request.Request(
            'http://localhost:5001/api/refresh-all-feeds',
            method='POST',
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=300) as response:
            data = json.loads(response.read().decode())

        if data.get('success'):
            summary = data.get('summary', {})
            results = data.get('results', {})
            print(f"✅ Feed refresh complete:")
            print(f"   YouTube: {results.get('youtube', {}).get('refreshed', 0)} channels, {results.get('youtube', {}).get('new_videos', 0)} new videos")
            print(f"   Newsletters: {results.get('newsletters', {}).get('refreshed', 0)} feeds, {results.get('newsletters', {}).get('new_issues', 0)} new issues")
            print(f"   Podcasts: {results.get('podcasts', {}).get('refreshed', 0)} feeds, {results.get('podcasts', {}).get('new_episodes', 0)} new episodes")
            if summary.get('total_errors', 0) > 0:
                print(f"   ⚠️  {summary.get('total_errors')} errors occurred")
        else:
            print(f"⚠️ Feed refresh failed: {data.get('error', 'Unknown error')}")
    except urllib.error.URLError as e:
        print(f"⚠️ Could not connect to server for feed refresh: {e}")
    except Exception as e:
        print(f"⚠️ Error refreshing feeds: {e}")

def check_and_update_ytdlp():
    """Check if yt-dlp needs updating and update if necessary"""
    try:
        print("🔍 Checking yt-dlp version...")
        result = subprocess.run([sys.executable, '-m', 'pip', 'list', '--outdated'], 
                               capture_output=True, text=True, timeout=30)
        
        if 'yt-dlp' in result.stdout:
            print("📦 yt-dlp update available, updating...")
            update_result = subprocess.run([sys.executable, '-m', 'pip', 'install', '--upgrade', 'yt-dlp'], 
                                         capture_output=True, text=True, timeout=120)
            if update_result.returncode == 0:
                print("✅ yt-dlp updated successfully")
            else:
                print(f"❌ yt-dlp update failed: {update_result.stderr}")
        else:
            print("✅ yt-dlp is up to date")
    except Exception as e:
        print(f"⚠️ Could not check yt-dlp updates: {e}")

def signal_handler(sig, frame):
    print('\n🛑 Shutting down background service...')
    sys.exit(0)

def main():
    """Run the background processing service"""
    print("🚀 Starting YouTube Intelligence Background Service...")
    
    # Check and update yt-dlp on startup
    check_and_update_ytdlp()
    
    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create watch folder if it doesn't exist
    watch_folder = "screenshots"
    if not os.path.exists(watch_folder):
        os.makedirs(watch_folder)
        print(f"📁 Created watch folder: {watch_folder}")
    
    # Initialize processor
    processor = YouTubeProcessor()
    
    # Set up file monitoring
    event_handler = ScreenshotHandler(processor)
    observer = Observer()
    observer.schedule(event_handler, watch_folder, recursive=False)
    
    print(f"👀 Monitoring folder: {os.path.abspath(watch_folder)}")
    print("📱 Drop screenshots into the folder to process them")
    print("🔍 Use the web interface at http://localhost:5001 to view results")
    print("📡 Auto-refreshing feeds at 9am, 3pm, and 9pm")
    print("📰 Auto-generating daily briefs at 9:30pm (all verticals)")
    print("\nPress Ctrl+C to stop monitoring...\n")
    
    observer.start()
    
    # Track time for periodic updates
    last_update_check = time.time()
    update_check_interval = 24 * 60 * 60  # Check for updates every 24 hours
    
    # Track time for person subscription monitoring
    last_person_check = time.time()
    person_check_interval = 6 * 60 * 60  # Run check cycle every 6 hours (but only checks people who are due)

    # Track scheduled feed refresh (9am, 3pm, 9pm)
    last_feed_refresh_hour = None  # Track which hour we last refreshed to avoid duplicates

    # Track nightly brief generation (9:30 PM)
    last_brief_generation_date = None  # Track date to avoid duplicate generation

    try:
        while True:
            time.sleep(1)
            current_time = time.time()
            
            # Check for yt-dlp updates every 24 hours
            if current_time - last_update_check > update_check_interval:
                print("\n🔄 Periodic update check...")
                check_and_update_ytdlp()
                last_update_check = current_time
            
            # Check person subscriptions (staggered - only checks people due for check)
            # This runs every 6 hours, but only checks people who haven't been checked in 72+ hours
            # Runs in background, won't interfere with screenshot processing or queue processing
            if current_time - last_person_check > person_check_interval:
                try:
                    print("\n🔍 Checking person subscriptions (staggered schedule, 72h interval)...")
                    result = processor.monitor_person_subscriptions(
                        max_results_per_person=20,
                        check_interval_hours=72,  # Only check people not checked in 72+ hours (3 days)
                        max_checks_per_run=2  # Max 2 people per run to keep it lightweight
                    )
                    if result.get('checked', 0) > 0:
                        print(f"✅ Person subscription check: {result.get('checked')} checked, {result.get('skipped')} skipped, {result.get('new_interviews', 0)} new interviews found")
                    elif result.get('skipped', 0) > 0:
                        print(f"⏭️  Person subscription check: All {result.get('skipped')} subscriptions checked recently, skipping")
                except Exception as e:
                    print(f"⚠️  Error in person subscription monitoring: {e}")
                last_person_check = current_time

            # Refresh all feeds at scheduled times (9am, 3pm, 9pm)
            current_hour = datetime.now().hour
            if should_refresh_feeds() and last_feed_refresh_hour != current_hour:
                try:
                    print(f"\n⏰ Scheduled feed refresh ({datetime.now().strftime('%I:%M %p')})")
                    refresh_all_feeds()
                    last_feed_refresh_hour = current_hour
                except Exception as e:
                    print(f"⚠️  Error in feed refresh: {e}")

            # Generate nightly briefs at 9:30 PM (after 9 PM feed refresh)
            today = datetime.now().date()
            if should_generate_briefs() and last_brief_generation_date != today:
                try:
                    print(f"\n📰 Nightly brief generation ({datetime.now().strftime('%I:%M %p')})")
                    generate_all_briefs()
                    last_brief_generation_date = today
                except Exception as e:
                    print(f"⚠️  Error in brief generation: {e}")
    except KeyboardInterrupt:
        print("\n🛑 Stopping monitoring...")
        observer.stop()
        if processor.batch_timer:
            processor.batch_timer.cancel()
    
    observer.join()
    print("✅ Background service stopped")

if __name__ == "__main__":
    main()
