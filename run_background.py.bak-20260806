#!/usr/bin/env python3
"""
YouTube Intelligence Background Service
Runs the file monitoring and processing in the background
"""

import os
import sys
import time
import json
import signal
import subprocess
import urllib.request
from datetime import datetime
from pathlib import Path
from youtube_processor import YouTubeProcessor, ScreenshotHandler
from watchdog.observers import Observer

def notify_mattermost(channel, message):
    """Best-effort Mattermost notification. Never blocks the pipeline."""
    try:
        jarvis_path = os.path.expanduser("~/jarvis")
        if jarvis_path not in sys.path:
            sys.path.insert(0, jarvis_path)
        from tools.mattermost_client import mm
        mm.post(channel, message, username="Pipeline")
    except Exception:
        pass  # Mattermost down or unavailable — pipeline continues regardless


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
    """
    now = datetime.now()
    # 9:30-9:35 PM window — after the 9 PM feed refresh has finished
    if now.hour == 21 and 30 <= now.minute < 35:
        return True
    return False

def get_verticals_for_today():
    """Determine which verticals should generate briefs today.

    Core verticals:
    - ai_tech: daily
    - health_longevity: Tuesday and Friday
    - future_medicine: Monday and Thursday
    - futures_trends: Wednesday (once a week, PAUSED)

    Life-stage verticals (weekly, spread across the week):
    - Monday:    early_childhood, elementary, middle_school
    - Tuesday:   high_school, college, early_career
    - Wednesday: mid_career, late_career, seniors
    """
    today = datetime.now()
    day_of_week = today.weekday()  # 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, 5=Sat, 6=Sun

    verticals = ['ai_tech']  # Always daily
    verticals.append('ai_agents')  # Always daily

    if day_of_week in (1, 4):  # Tuesday, Friday
        verticals.append('health_longevity')

    if day_of_week in (0, 3):  # Monday, Thursday
        verticals.append('future_medicine')

    # futures_trends: PAUSED — editorial identity rethink in progress (turned off Feb 28)
    # if day_of_week == 2:  # Wednesday
    #     verticals.append('futures_trends')

    if day_of_week in (0, 2, 4):  # Monday, Wednesday, Friday
        verticals.append('local_ai_intel')

    # Life-stage verticals — PAUSED (editorial design incomplete, running since Feb 23 without review)
    # Uncomment when editorial quality reviewed and approved by Tom.
    # lifestage_schedule = {
    #     0: ['lifestage_early_childhood', 'lifestage_elementary', 'lifestage_middle_school'],
    #     1: ['lifestage_high_school', 'lifestage_college', 'lifestage_early_career'],
    #     2: ['lifestage_mid_career', 'lifestage_late_career', 'lifestage_seniors'],
    # }
    # verticals.extend(lifestage_schedule.get(day_of_week, []))

    return verticals

def generate_all_briefs():
    """Generate daily briefs for scheduled verticals via the local API"""
    import urllib.request
    import json

    verticals = get_verticals_for_today()
    print(f"📋 Scheduled verticals for today: {', '.join(verticals)}")
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
    print("📰 Auto-generating briefs at 9:30pm (AI&Tech daily, Health Tue/Fri, Futures Wed)")
    print("🎙️  Auto-generating podcasts at 9:45pm (core verticals, except Futures)")
    print("📧 Auto-generating newsletters at 10:00pm → Ghost drafts")
    print("🎙️  All core podcast verticals run sequentially at 9:45pm, ks_youtube at 11:15pm")
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

    # Track podcast generation (runs after briefs complete)
    last_podcast_generation_date = None

    # Track daily subscriber snapshot
    last_subscriber_snapshot_date = None

    # Track newsletter generation (runs after podcasts)
    last_newsletter_generation_date = None

    # Sequential podcast tracking — all non-KS verticals handled in single 9:45 PM block
    last_agents_podcast_date = None

    last_medicine_podcast_date = None

    # Track KS verticals (staggered at 11 PM to avoid load conflicts with main pipeline)
    last_ks_brief_date = None
    last_ks_podcast_date = None

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

            # Snapshot subscriber counts once daily (at 9 PM with the feed refresh)
            today = datetime.now().date()
            if current_hour == 21 and last_subscriber_snapshot_date != today:
                try:
                    print(f"\n📊 Daily subscriber snapshot")
                    result = processor.refresh_subscriber_counts()
                    print(f"   ✅ {result['updated']} channels snapshotted")
                    last_subscriber_snapshot_date = today
                except Exception as e:
                    print(f"   ⚠️  Subscriber snapshot error: {e}")

            # Generate nightly briefs at 9:30 PM (after 9 PM feed refresh)
            if should_generate_briefs() and last_brief_generation_date != today:
                try:
                    print(f"\n📰 Nightly brief generation ({datetime.now().strftime('%I:%M %p')})")
                    results = generate_all_briefs()
                    last_brief_generation_date = today
                    # Notify Mattermost
                    succeeded = [v for v, s in results.items() if s == 'success']
                    failed = [v for v, s in results.items() if s != 'success']
                    if succeeded:
                        notify_mattermost("producer", f"**Briefs generated:** {', '.join(succeeded)}")
                    if failed:
                        notify_mattermost("alerts", f"**Brief generation failed:** {', '.join(failed)}")
                except Exception as e:
                    print(f"⚠️  Error in brief generation: {e}")
                    notify_mattermost("alerts", f"**Brief generation error:** {e}")

            # Generate all podcast episodes sequentially at 9:45 PM
            # HARD RULE: zero concurrent TTS runs. Single loop, sequential, no staggered triggers.
            now = datetime.now()
            podcast_already_running = bool(subprocess.run(
                ["pgrep", "-f", "podcast_pipeline.py"],
                capture_output=True
            ).stdout.strip())
            if now.hour == 21 and 45 <= now.minute < 50 and last_podcast_generation_date != today and not podcast_already_running:
                try:
                    print("Podcast generation: sequential run")
                    tts_python = os.path.expanduser("~/tts-env/bin/python3")
                    pipeline_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "podcast_pipeline.py")

                    all_podcast_order = ["ai_tech", "ai_agents", "health_longevity", "future_medicine", "local_ai_intel"]
                    todays_verticals = set(get_verticals_for_today())
                    podcast_skip = {"futures_trends"}
                    podcast_verticals = [v for v in all_podcast_order if v in todays_verticals and v not in podcast_skip]

                    podcast_results = {}
                    for vertical in podcast_verticals:
                        print(f"  Generating {vertical} podcast...")
                        result = subprocess.run(
                            [tts_python, pipeline_script, vertical],
                            capture_output=True, text=True, timeout=3600
                        )
                        if result.returncode == 0:
                            print(f"  {vertical} done")
                            podcast_results[vertical] = "success"
                        else:
                            print(f"  {vertical} failed: {result.stderr[-200:]}")
                            podcast_results[vertical] = "failed"
                        print(result.stdout)

                    last_podcast_generation_date = today
                    last_agents_podcast_date = today
                    last_medicine_podcast_date = today

                    pod_ok = [v for v, s in podcast_results.items() if s == "success"]
                    pod_fail = [v for v, s in podcast_results.items() if s != "success"]
                    if pod_ok:
                        notify_mattermost("producer", f"**Podcasts generated:** {', '.join(pod_ok)}")
                    if pod_fail:
                        notify_mattermost("alerts", f"**Podcast generation failed:** {', '.join(pod_fail)}")
                except Exception as e:
                    print(f"Error in podcast generation: {e}")
                    notify_mattermost("alerts", f"**Podcast generation error:** {e}")

            # Generate newsletters at 10:00 PM (after briefs and podcasts)
            # Creates editorial newsletter from each brief and posts as Ghost draft
            if now.hour == 22 and 0 <= now.minute < 5 and last_newsletter_generation_date != today:
                try:
                    print(f"\n📧 Newsletter generation ({now.strftime('%I:%M %p')})")
                    newsletter_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "newsletter_generator.py")
                    ghost_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ghost_api.py")

                    newsletter_verticals = get_verticals_for_today()
                    nl_results = {}
                    for vertical in newsletter_verticals:
                        print(f"  📧 Generating {vertical} newsletter...")
                        result = subprocess.run(
                            [sys.executable, newsletter_script, vertical],
                            capture_output=True, text=True, timeout=120
                        )
                        if result.returncode == 0:
                            print(f"  ✅ {vertical} newsletter generated")
                            nl_results[vertical] = 'generated'
                            # Post to Ghost as draft
                            date_str = datetime.now().strftime("%Y-%m-%d")
                            json_path = os.path.join(
                                os.path.dirname(os.path.abspath(__file__)),
                                "newsletter_output",
                                f"newsletter_{vertical}_{date_str}.json"
                            )
                            if os.path.exists(json_path):
                                ghost_result = subprocess.run(
                                    [sys.executable, ghost_script, "post", json_path, vertical],
                                    capture_output=True, text=True, timeout=30
                                )
                                if ghost_result.returncode == 0:
                                    print(f"  📤 {vertical} posted to Ghost as draft")
                                    nl_results[vertical] = 'posted to Ghost'
                                else:
                                    print(f"  ⚠️  Ghost post failed: {ghost_result.stderr[-200:]}")
                                    nl_results[vertical] = 'generated (Ghost post failed)'
                        else:
                            print(f"  ⚠️  {vertical} newsletter failed: {result.stderr[-200:]}")
                            nl_results[vertical] = 'failed'
                        print(result.stdout)

                    last_newsletter_generation_date = today
                    # Notify Mattermost
                    nl_ok = [f"{v} ({s})" for v, s in nl_results.items() if 'failed' not in s]
                    nl_fail = [v for v, s in nl_results.items() if 'failed' in s]
                    if nl_ok:
                        notify_mattermost("producer", f"**Newsletters:** {', '.join(nl_ok)}")
                    if nl_fail:
                        notify_mattermost("alerts", f"**Newsletter failed:** {', '.join(nl_fail)}")
                except Exception as e:
                    print(f"⚠️  Error in newsletter generation: {e}")
                    notify_mattermost("alerts", f"**Newsletter generation error:** {e}")

            # Generate KS briefs at 11:00 PM (staggered from main pipeline)
            # Two verticals: ks_youtube (content intelligence) and ks_examiner (operations report)
            if now.hour == 23 and 0 <= now.minute < 5 and last_ks_brief_date != today:
                try:
                    print(f"\n📰 KS brief generation ({now.strftime('%I:%M %p')})")
                    ks_verticals = ['ks_youtube', 'ks_examiner']
                    ks_brief_results = {}
                    for vertical in ks_verticals:
                        try:
                            print(f"  📝 Generating {vertical} brief...")
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
                                ks_brief_results[vertical] = 'success'
                            else:
                                print(f"   ⚠️  {vertical}: {data.get('error', 'unknown error')}")
                                ks_brief_results[vertical] = 'failed'
                        except Exception as e:
                            print(f"   ⚠️  {vertical} error: {e}")
                            ks_brief_results[vertical] = 'failed'

                    last_ks_brief_date = today
                    succeeded = [v for v, s in ks_brief_results.items() if s == 'success']
                    failed = [v for v, s in ks_brief_results.items() if s != 'success']
                    if succeeded:
                        notify_mattermost("producer", f"**KS Briefs generated:** {', '.join(succeeded)}")
                    if failed:
                        notify_mattermost("alerts", f"**KS Brief generation failed:** {', '.join(failed)}")
                except Exception as e:
                    print(f"⚠️  Error in KS brief generation: {e}")
                    notify_mattermost("alerts", f"**KS brief generation error:** {e}")

            # Generate KS podcasts at 11:15 PM (staggered 15 min after briefs)
            # Only ks_youtube gets a podcast — ks_examiner is read-only operational report
            ks_podcast_already_running = bool(subprocess.run(["pgrep", "-f", "podcast_pipeline.py"], capture_output=True).stdout.strip())
            if now.hour == 23 and 15 <= now.minute < 20 and last_ks_podcast_date != today and not ks_podcast_already_running:
                try:
                    print(f"\n🎙️  KS podcast generation ({now.strftime('%I:%M %p')})")
                    tts_python = os.path.expanduser("~/tts-env/bin/python3")
                    pipeline_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "podcast_pipeline.py")
                    ks_podcast_verticals = ['ks_youtube']
                    ks_pod_results = {}
                    for vertical in ks_podcast_verticals:
                        print(f"  🎙️  Generating {vertical} podcast...")
                        result = subprocess.run(
                            [tts_python, pipeline_script, vertical],
                            capture_output=True, text=True, timeout=3600
                        )
                        if result.returncode == 0:
                            print(f"  ✅ {vertical} podcast done")
                            ks_pod_results[vertical] = 'success'
                        else:
                            print(f"  ⚠️  {vertical} podcast failed: {result.stderr[-200:]}")
                            ks_pod_results[vertical] = 'failed'
                        print(result.stdout)

                    last_ks_podcast_date = today
                    pod_ok = [v for v, s in ks_pod_results.items() if s == 'success']
                    pod_fail = [v for v, s in ks_pod_results.items() if s != 'success']
                    if pod_ok:
                        notify_mattermost("producer", f"**KS Podcasts generated:** {', '.join(pod_ok)}")
                    if pod_fail:
                        notify_mattermost("alerts", f"**KS Podcast generation failed:** {', '.join(pod_fail)}")
                except Exception as e:
                    print(f"⚠️  Error in KS podcast generation: {e}")
                    notify_mattermost("alerts", f"**KS podcast generation error:** {e}")

    except KeyboardInterrupt:
        print("\n🛑 Stopping monitoring...")
        observer.stop()
        if processor.batch_timer:
            processor.batch_timer.cancel()
    
    observer.join()
    print("✅ Background service stopped")

if __name__ == "__main__":
    main()
