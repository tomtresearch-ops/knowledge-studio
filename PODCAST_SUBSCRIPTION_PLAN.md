# Podcast Feed Subscription Implementation Plan

## Overview
Add podcast feed subscription functionality to Knowledge Studio, mirroring the existing YouTube channel subscription system. Users can subscribe to podcast RSS feeds, view episodes, and process them with transcription and summarization.

## Current System Analysis

### YouTube Channel System (Reference)
- **Database Tables:**
  - `channel_subscriptions` - stores subscription metadata (channel_id, channel_name, rss_url, enabled, etc.)
  - `channel_videos` - stores video metadata from RSS feeds (video_id, video_url, title, published_at, etc.)
  - `videos` - stores processed videos with transcripts and summaries

- **Key Functions:**
  - `add_subscription()` - adds subscription from channel URL/ID
  - `refresh_subscription()` - fetches new videos from RSS feed
  - `list_subscriptions()` - lists all subscriptions
  - `toggle_subscription()` - enable/disable
  - `remove_subscription()` - delete subscription

- **Processing Flow:**
  1. User subscribes to channel
  2. System parses YouTube RSS feed (Atom XML)
  3. Video metadata stored in `channel_videos`
  4. Videos processed individually (transcript + summary)
  5. Processed videos linked via `processed_video_id`

## Proposed Podcast System

### Database Schema

#### 1. `podcast_subscriptions` Table
```sql
CREATE TABLE IF NOT EXISTS podcast_subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    podcast_name TEXT NOT NULL,
    feed_url TEXT NOT NULL UNIQUE,
    description TEXT,
    website_url TEXT,
    image_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_checked TIMESTAMP,
    enabled INTEGER DEFAULT 1
)
```

#### 2. `podcast_episodes` Table
```sql
CREATE TABLE IF NOT EXISTS podcast_episodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscription_id INTEGER NOT NULL,
    episode_guid TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    description TEXT,
    audio_url TEXT NOT NULL,
    transcript_url TEXT,
    published_at TIMESTAMP,
    duration TEXT,
    processed INTEGER DEFAULT 0,
    processed_article_id INTEGER,
    FOREIGN KEY(subscription_id) REFERENCES podcast_subscriptions(id)
)
```

**Note:** `transcript_url` field stores transcript URL if found in RSS feed.

**Note:** Processed episodes will be stored in the existing `articles` table with `content_type='audio'`, linking via `processed_article_id`.

### Implementation Strategy

#### Phase 1: Core Subscription Management (Similar to YouTube)

**1.1 Create `PodcastProcessor` Class** (`podcast_processor.py`)
- Mirror structure of `YouTubeProcessor`
- Methods:
  - `init_database()` - create tables
  - `_parse_podcast_input(podcast_input)` - parse input (RSS URL, podcast name, etc.)
  - `_search_podcast_by_name(podcast_name)` - search iTunes API for podcast
  - `_fetch_podcast_metadata(feed_url)` - fetch podcast metadata from RSS feed
  - `add_subscription(podcast_input)` - subscribe to podcast (accepts name or RSS URL)
  - `refresh_subscription(subscription_id)` - fetch new episodes
  - `list_subscriptions()` - list all subscriptions
  - `toggle_subscription(subscription_id)` - enable/disable
  - `remove_subscription(subscription_id)` - delete subscription
  - `get_podcast_episodes(subscription_id, processed=None)` - list episodes

**1.2 Auto-Discovery by Name (Like YouTube Channels)**
- **iTunes Search API** (free, no authentication required)
  - Endpoint: `https://itunes.apple.com/search`
  - Parameters: `term={podcast_name}&media=podcast&limit=5`
  - Returns: podcast name, artist, feed URL, artwork, etc.
- **Search Flow:**
  1. User types podcast name (e.g., "Lex Fridman Podcast")
  2. System searches iTunes API
  3. Returns top matches for user selection (or auto-selects first match)
  4. Extracts RSS feed URL from iTunes result
  5. Subscribes to feed automatically
- **Fallback:** If iTunes search fails, try direct RSS URL parsing

**1.3 RSS Feed Parsing**
- Use standard RSS/Atom parser (Python's `feedparser` library)
- Extract:
  - Podcast metadata (title, description, image, website)
  - Episode metadata (title, description, GUID, published date, audio URL)
  - **Transcript URLs** (check for existing transcripts in feed)
- Store episodes in `podcast_episodes` table

**1.3 API Endpoints** (`app.py`)
```python
@app.route('/api/podcast-subscriptions', methods=['GET'])
@app.route('/api/podcast-subscriptions', methods=['POST'])
@app.route('/api/podcast-subscriptions/<int:subscription_id>', methods=['DELETE'])
@app.route('/api/podcast-subscriptions/<int:subscription_id>/toggle', methods=['POST'])
@app.route('/api/podcast-subscriptions/<int:subscription_id>/refresh', methods=['POST'])
@app.route('/api/podcast-subscriptions/<int:subscription_id>/episodes', methods=['GET'])
```

#### Phase 2: Episode Processing (Reuse Existing Audio System)

**2.1 Process Episode Endpoint**
- Create `/api/podcast-episodes/<int:episode_id>/process`
- **Transcript Detection Flow:**
  1. Check if episode has `transcript_url` in database (from RSS feed)
  2. If transcript URL exists:
     - Download transcript directly from URL
     - Skip audio download and Whisper transcription
     - Generate summary with Claude using transcript
  3. If no transcript URL:
     - Download audio using `yt-dlp` (supports many podcast platforms)
     - Transcribe with Whisper
     - Generate summary with Claude
- Stores in `articles` table with `content_type='audio'`
- Updates `podcast_episodes.processed = 1` and `processed_article_id`

**2.2 Transcript Detection in RSS Feed**
- Parse RSS feed for transcript links:
  - `<podcast:transcript>` tag (Podcast Namespace)
  - `<itunes:transcript>` tag (iTunes extension)
  - `<link rel="transcript">` in episode entry
  - Custom transcript fields in feed
- Store transcript URL in `podcast_episodes.transcript_url`
- Priority: Use transcript if available, fallback to audio transcription

**2.2 Integration Points**
- Use existing `process_audio_from_url()` function
- Use existing `transcribe_audio()` background processing
- Store in `articles` table (already supports audio)

#### Phase 3: UI Integration

**3.1 Subscriptions Page**
- Add "Podcasts" tab to subscriptions interface
- List subscriptions with enable/disable toggle
- "Refresh" button to fetch new episodes
- **"Add Podcast" form:**
  - Single input field (like YouTube channel input)
  - Accepts: podcast name OR RSS feed URL
  - Auto-searches iTunes API if name provided
  - Shows search results for user selection (optional)
  - Automatically subscribes to selected podcast

**3.2 Episodes View**
- Show episodes per subscription
- Display: title, published date, duration, processed status
- **Transcript indicator:** Show "📝 Transcript Available" badge if transcript URL found
- "Process" button for unprocessed episodes
- Link to processed episode in library

**3.3 Library Integration**
- Processed podcast episodes appear in library (already works via `articles` table)
- Filter by `content_type='audio'`
- Show podcast name in "channel" field

### Key Design Decisions

1. **Reuse Existing Audio Processing**
   - Podcast episodes are just audio URLs
   - Use same transcription and summarization pipeline
   - Store in `articles` table (already supports audio)

2. **RSS Feed Parsing**
   - Use `feedparser` library (standard, handles RSS/Atom)
   - More reliable than custom XML parsing
   - Handles various podcast feed formats

3. **Audio Download**
   - Use `yt-dlp` (already installed)
   - Supports many podcast platforms (Spotify, Apple Podcasts, direct RSS)
   - Same system as YouTube audio extraction

4. **Database Design**
   - Mirror YouTube subscription structure
   - Separate `podcast_episodes` table (like `channel_videos`)
   - Link to `articles` via `processed_article_id` (like `processed_video_id`)

5. **Processing Model**
   - Manual processing (user clicks "Process" on episode)
   - Same as YouTube videos (not automatic)
   - Background processing with status polling

### Implementation Steps

1. **Create `podcast_processor.py`**
   - Copy structure from `youtube_processor.py`
   - Adapt RSS parsing for podcasts
   - Implement subscription management

2. **Add Database Tables**
   - Add to `DatabaseService.init_database()` or `PodcastProcessor.init_database()`

3. **Add API Endpoints**
   - Mirror YouTube subscription endpoints
   - Add episode processing endpoint

4. **Add UI Components**
   - Podcast subscriptions tab
   - Episodes list view
   - Process episode button

5. **Testing**
   - Test with various podcast RSS feeds
   - Verify audio download and transcription
   - Test subscription refresh

### Advantages of This Approach

1. **Consistency** - Mirrors existing YouTube system (same UX pattern)
2. **Auto-Discovery** - Search by name, no need to find RSS URLs manually
3. **Smart Transcript Detection** - Uses existing transcripts when available (faster, cheaper)
4. **Reusability** - Leverages existing audio processing
5. **Simplicity** - Minimal new code, mostly adaptation
6. **Flexibility** - Works with any RSS podcast feed
7. **Integration** - Processed episodes appear in library automatically

### Potential Challenges

1. **RSS Feed Variations** - Different podcast platforms use different formats
   - **Solution:** Use `feedparser` library (handles variations)

2. **Audio URL Formats** - Some feeds use redirects or special URLs
   - **Solution:** `yt-dlp` handles most formats

3. **Large Episodes** - Podcasts can be hours long
   - **Solution:** Existing Whisper transcription handles long audio
   - **Better:** Use transcripts when available (much faster)

4. **Feed Updates** - Need to check for new episodes periodically
   - **Solution:** Manual refresh (like YouTube) or add scheduled refresh

5. **iTunes API Rate Limits** - Free API has rate limits
   - **Solution:** Cache search results, fallback to direct RSS URL

6. **Transcript Format Variations** - Transcripts may be in different formats (HTML, plain text, JSON)
   - **Solution:** Parse common formats, extract text content

### Implementation Details

#### iTunes Search API Integration
```python
def _search_podcast_by_name(self, podcast_name: str) -> List[Dict]:
    """Search iTunes API for podcast by name"""
    import requests
    url = "https://itunes.apple.com/search"
    params = {
        'term': podcast_name,
        'media': 'podcast',
        'limit': 5
    }
    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()
    data = response.json()
    
    results = []
    for item in data.get('results', []):
        results.append({
            'podcast_name': item.get('collectionName'),
            'artist': item.get('artistName'),
            'feed_url': item.get('feedUrl'),  # RSS feed URL
            'artwork_url': item.get('artworkUrl600'),
            'description': item.get('description', ''),
            'genre': item.get('primaryGenreName', '')
        })
    return results
```

#### Transcript Detection in RSS Feed
```python
def _extract_transcript_url(self, entry) -> Optional[str]:
    """Extract transcript URL from RSS feed entry"""
    # Check podcast:transcript namespace
    transcript_nodes = entry.findall('podcast:transcript', namespaces)
    if transcript_nodes:
        return transcript_nodes[0].get('url')
    
    # Check itunes:transcript
    itunes_transcript = entry.find('itunes:transcript', namespaces)
    if itunes_transcript is not None:
        return itunes_transcript.text
    
    # Check link rel="transcript"
    links = entry.findall('atom:link', namespaces)
    for link in links:
        if link.get('rel') == 'transcript':
            return link.get('href')
    
    return None
```

#### Process Episode with Transcript Check
```python
def process_episode(self, episode_id: int):
    """Process episode, using transcript if available"""
    episode = self.get_episode(episode_id)
    
    if episode.get('transcript_url'):
        # Download and use existing transcript
        transcript = self._download_transcript(episode['transcript_url'])
        # Generate summary directly
        summary = self._generate_summary(transcript, episode['title'])
    else:
        # Download audio and transcribe
        audio_file = self._download_audio(episode['audio_url'])
        transcript = self._transcribe_audio(audio_file)
        summary = self._generate_summary(transcript, episode['title'])
    
    # Store in articles table
    article_id = self._save_to_articles(episode, transcript, summary)
    self._mark_episode_processed(episode_id, article_id)
```

### Next Steps

1. ✅ Review and approve this plan
2. Create `podcast_processor.py` with:
   - iTunes search integration
   - RSS feed parsing with transcript detection
   - Subscription management
3. Add database tables (including `transcript_url` field)
4. Implement API endpoints
5. Add UI components (podcast name search)
6. Test with real podcast feeds (with and without transcripts)

