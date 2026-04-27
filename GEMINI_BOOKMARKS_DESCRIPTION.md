# Application Overview & Sidebar System Description

## Application Overview

This is a **Knowledge Management System** built with Flask (Python backend) and vanilla JavaScript (frontend). The core purpose is to capture, process, and organize transcript-based content into a searchable knowledge library.

### Core Architecture

**Backend (Flask/Python):**
- SQLite database storing all content and metadata
- RESTful API endpoints for CRUD operations
- Content processing pipeline that extracts transcripts and generates AI summaries
- Database service layer (`DatabaseService` class) handling all data operations

**Frontend (Vanilla JavaScript/HTML):**
- Single-page application (`library.html`) with dynamic content rendering
- No frameworks - pure JavaScript DOM manipulation
- Modal-based UI for detailed views and interactions
- Real-time updates via API calls

### Content Flow

1. **Ingestion**: Transcripts are processed and stored in the database
2. **Processing**: AI generates structured summaries from transcripts
3. **Storage**: Content stored in `videos` and `articles` tables (unified as "items")
4. **Display**: Library view shows all items as cards with summaries
5. **Interaction**: Users can highlight text, take notes, favorite items, and chat with their knowledge base

### Main Features

- **Library View**: Grid/list view of all processed content with search and filtering
- **AI Summaries**: Structured summaries generated from transcripts using category-specific prompts
- **Chat Interface**: Query the knowledge base using RAG (Retrieval Augmented Generation)
- **Highlights System**: Users can highlight text from summaries and add notes
- **Notes System**: Quick capture notes linked to specific content items
- **Favorites**: Mark important items for quick access
- **Tagging**: Organize content with custom tags
- **Document View**: Clean, focused view of individual summaries in a popup window

---

## Sidebar System Architecture

The sidebar is a **persistent left panel** in the library view that provides quick access to key features and aggregated data. It's divided into multiple collapsible sections.

### Sidebar Structure

The sidebar (`<aside class="sidebar">`) contains several sections, each with distinct functionality:

#### 1. **Chat with Knowledge Base Section**
- Channel selector dropdown (filters chat to specific content sources)
- Mode toggle (Grounded vs Interpolated chat modes)
- Input field for asking questions
- Chat container that displays conversation history
- **Behavior**: Opens inline chat interface, no modal

#### 2. **Maintenance Section** (Collapsible)
- Collapsible section with maintenance tools
- "Remove All Duplicates" button
- "Clear Stuck Processing" button
- **Behavior**: Toggles open/closed on click

#### 3. **Highlights Section** (Clickable)
- Displays total highlight count: `Highlights (<span id="highlight-count">0</span>)`
- **Behavior**: Clicking opens a modal (`showHighlightsModal()`)
- **API Endpoint**: `GET /api/highlights` with optional tag filter
- **Modal Features**:
  - Shows all highlights or filtered by tag
  - Each highlight displays: quoted text, optional user note, source metadata, date
  - Actions per highlight: Edit, Delete, View source
  - Export button to copy all highlights as Markdown
  - Tag-based filtering within modal

#### 4. **Notes Section** (Clickable)
- Displays total note count: `Notes (<span id="note-count">0</span>)`
- **Behavior**: Clicking opens a modal (`showNotesModal()`)
- **API Endpoint**: `GET /api/notes` with optional source_type filter
- **Modal Features**:
  - Shows all notes or filtered by source type (video/article/kindle)
  - Each note displays: note text, linked content title, channel, date, content type
  - Actions per note: Delete, View source, View summary
  - Source type filter dropdown
  - Notes sorted chronologically (most recent first)

#### 5. **Favorites Section** (Clickable)
- Toggle button to filter library view to show only favorited items
- **Behavior**: Clicking toggles a filter state that affects main content area
- Updates library view dynamically (no modal)

#### 6. **Recent Processing Section** (Collapsible)
- Shows count of recent processing items
- Collapsible section with:
  - "View Queue" button
  - "Retry Failed" button
  - List of recent processing items with status
- **Behavior**: Toggles open/closed, shows processing queue status

#### 7. **Knowledge Stats Section**
- Displays statistics:
  - Total Items count
  - This Week count
  - Average Confidence score
- **Behavior**: Static display, no interaction

### Sidebar Interaction Patterns

**Clickable Sections** (Highlights, Notes, Favorites):
- Title is clickable (`onclick` handler)
- Opens modal or toggles filter state
- Counts update dynamically via API calls

**Collapsible Sections** (Maintenance, Recent Processing):
- Title has `collapsible` class
- Content div has `collapsed` class initially
- Toggle function shows/hides content
- Uses CSS classes for animation

**Count Updates**:
- Counts are fetched via API and updated in sidebar
- Functions like `loadHighlightCategories()` update counts
- Counts reflect current database state

### Modal System

When sidebar sections open modals, they follow this pattern:

1. **Create Modal Element**: `document.createElement('div')` with `analysis-modal` class
2. **Modal Structure**:
   - Overlay div (closes modal on click)
   - Modal content div (stops propagation)
   - Header with title and close button
   - Body with content (list of items)
   - Footer with actions (if needed)

3. **Global Functions**: Modal-specific functions attached to `window` object:
   - `closeHighlightsModal()`, `closeNotesModal()`
   - Action functions like `deleteHighlight()`, `editHighlight()`
   - Export functions

4. **API Integration**: Modals fetch data via `fetch()` calls to Flask endpoints
5. **Dynamic Rendering**: Content rendered as HTML strings using `.map()` and template literals
6. **Event Handling**: Inline `onclick` handlers in generated HTML

### API Endpoint Patterns

**Highlights:**
- `GET /api/highlights?tag=<tag>&limit=<n>` - List highlights (optional tag filter)
- `POST /api/highlights` - Create highlight
- `PUT /api/highlights/<id>` - Update highlight (note, tags)
- `DELETE /api/highlights/<id>` - Delete highlight
- `GET /api/highlights/tags` - Get all tags with counts

**Notes:**
- `GET /api/notes?source_type=<type>&limit=<n>` - List notes (optional source filter)
- `POST /api/notes` - Create note
- `DELETE /api/notes/<id>` - Delete note

**Database Tables:**
- `highlights` table: Stores highlighted text, user notes, tags, source metadata
- `notes` table: Stores note text, linked content ID, source metadata, captured timestamp

---

## Bookmarks Feature Requirements (To Be Implemented)

Based on the existing Highlights and Notes patterns, the **Bookmarks** feature should follow the same architecture:

### Expected Behavior

1. **Sidebar Section**: Add a "Bookmarks" section similar to Highlights/Notes
   - Display: `Bookmarks (<span id="bookmark-count">0</span>)`
   - Clickable title that opens modal
   - Count updates dynamically

2. **Database Table**: `bookmarks` table with fields:
   - `id` (primary key)
   - `user_id` (optional)
   - `content_id` (links to videos/articles)
   - `content_type` ('video' or 'article')
   - `content_title` (cached title)
   - `channel` (cached channel name)
   - `source_url` (URL to original content)
   - `summary_url` (URL to summary view)
   - `created_at` (timestamp)
   - `note` (optional user note about the bookmark)

3. **API Endpoints** (following existing patterns):
   - `GET /api/bookmarks?limit=<n>` - List all bookmarks
   - `POST /api/bookmarks` - Create bookmark
   - `DELETE /api/bookmarks/<id>` - Delete bookmark
   - `PUT /api/bookmarks/<id>` - Update bookmark (e.g., note field)

4. **Modal Display** (similar to Notes modal):
   - Title: "All Bookmarks (count)"
   - List of bookmarks showing:
     - Content title (clickable to view)
     - Channel name
     - Date bookmarked
     - Optional note
     - Actions: Delete, View source, View summary
   - Sort by most recent first

5. **Integration Points**:
   - "Add to Bookmarks" button in library cards
   - "Add to Bookmarks" button in document view
   - Bookmark indicator/icon on bookmarked items
   - Quick access via sidebar

### Implementation Notes

- Follow the exact same pattern as Highlights and Notes
- Use same modal styling (`analysis-modal` class)
- Use same API response format (`{success: true, bookmarks: [...]}`)
- Use same database service pattern (`save_bookmark()`, `get_bookmarks()`, `delete_bookmark()`)
- Update sidebar count on bookmark create/delete
- Ensure consistent UI/UX with existing features

---

## Key Technical Details

### Frontend Patterns
- **No frameworks**: Pure vanilla JavaScript
- **Template literals**: HTML generated as strings
- **Event delegation**: Inline `onclick` handlers in generated HTML
- **Modal management**: Global functions on `window` object
- **API calls**: `fetch()` with `http://localhost:5001` base URL
- **Dynamic updates**: DOM manipulation via `innerHTML` and `appendChild()`

### Backend Patterns
- **Flask routes**: `@app.route()` decorators
- **JSON responses**: `jsonify({'success': True/False, ...})`
- **Database service**: Centralized `DatabaseService` class
- **Error handling**: Try/except with error messages in JSON
- **SQLite**: Direct SQL queries with parameterized statements

### Styling
- **Dark theme**: Purple/violet accent colors (#8b5cf6)
- **Modal styling**: Dark backgrounds with borders and shadows
- **Responsive**: Max-width constraints, viewport-based sizing
- **Transitions**: CSS transitions for smooth interactions

---

This architecture ensures consistency across all sidebar features and provides a clear pattern for implementing the Bookmarks functionality.

