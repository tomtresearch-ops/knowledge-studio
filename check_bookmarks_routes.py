#!/usr/bin/env python3
"""Quick script to verify bookmarks routes are registered"""
import sys
sys.path.insert(0, '.')

try:
    import app
    routes = [str(rule) for rule in app.app.url_map.iter_rules()]
    bookmark_routes = [r for r in routes if 'bookmark' in r.lower()]
    
    if bookmark_routes:
        print("✅ Bookmark routes are registered:")
        for route in bookmark_routes:
            print(f"   {route}")
    else:
        print("❌ No bookmark routes found!")
        print(f"\nTotal routes: {len(routes)}")
        print("Sample routes:", routes[:10])
        
except Exception as e:
    print(f"❌ Error importing app: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

