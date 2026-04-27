# Sophisticated Creator Agent/Avatar Architecture

## Overview
A creator-specific agent system that enables natural conversation with a creator's body of work, maintaining their voice, perspective, and evolving views over time.

## Core Components

### 1. Creator Persona Engine
**Purpose**: Extract and maintain a dynamic profile of each creator's style, perspectives, and knowledge domains.

#### Data Sources:
- **Summaries** (`videos.ai_summary`) - Primary source for patterns
- **Transcripts** (`videos.full_transcript`) - Fallback for deep dives
- **Metadata** (titles, dates, topics) - Temporal and topical context
- **Channel description** - Background context

#### Persona Extraction Process:
```python
# Generate creator persona profile
1. Collect all processed videos for a channel
2. Extract common themes, frameworks, terminology
3. Identify speaking style (formal/casual, technical/accessible)
4. Map topic evolution over time
5. Extract key principles, recurring arguments, frameworks
6. Identify contradictions and how they evolved
```

#### Storage:
```sql
CREATE TABLE IF NOT EXISTS creator_personas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id TEXT NOT NULL UNIQUE,
    channel_name TEXT,
    
    -- Extracted persona data (JSON)
    persona_profile TEXT,  -- JSON: style, tone, common phrases
    key_frameworks TEXT,   -- JSON: recurring concepts, models, systems
    topic_expertise TEXT,  -- JSON: topics they cover, depth of coverage
    temporal_evolution TEXT,  -- JSON: how views changed over time
    
    -- Statistics
    total_videos INTEGER DEFAULT 0,
    total_transcript_chars INTEGER DEFAULT 0,
    date_range_start DATE,
    date_range_end DATE,
    
    -- Generation metadata
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    persona_version INTEGER DEFAULT 1,
    
    FOREIGN KEY(channel_id) REFERENCES channel_subscriptions(channel_id)
)
```

#### Persona Generation (One-time or periodic):
```python
def generate_creator_persona(channel_id: str) -> Dict:
    """
    Analyze all processed content for a creator and extract:
    - Speaking style and tone
    - Key frameworks and mental models
    - Topic expertise areas
    - View evolution over time
    - Common terminology and phrases
    """
    # 1. Collect all summaries and transcripts
    # 2. Use Claude to analyze patterns
    # 3. Generate structured persona profile
    # 4. Store in creator_personas table
```

---

### 2. Vector Embedding System
**Purpose**: Enable semantic search across creator's content for relevant retrieval.

#### Architecture:
- **Embedding Model**: `sentence-transformers/all-MiniLM-L6-v2` (local, free, fast)
- **Storage**: SQLite with `sqlite-vss` extension OR separate FAISS index
- **Chunking Strategy**: 
  - Summary chunks (by section: Executive Summary, Key Ideas, etc.)
  - Transcript chunks (500-1000 token windows with overlap)

#### Schema:
```sql
CREATE TABLE IF NOT EXISTS content_embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id TEXT NOT NULL,
    video_id INTEGER NOT NULL,
    content_type TEXT NOT NULL,  -- 'summary', 'transcript', 'section'
    section_name TEXT,  -- 'executive_summary', 'key_ideas', etc.
    chunk_index INTEGER,
    content_text TEXT NOT NULL,
    embedding BLOB,  -- Vector embedding (1536 dims for OpenAI, 384 for MiniLM)
    token_count INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY(video_id) REFERENCES videos(id),
    FOREIGN KEY(channel_id) REFERENCES channel_subscriptions(channel_id)
)

CREATE INDEX IF NOT EXISTS idx_embeddings_channel 
ON content_embeddings(channel_id)

CREATE VIRTUAL TABLE IF NOT EXISTS embeddings_vss USING vss0(
    embedding(384)  -- For MiniLM
)
```

#### Embedding Generation:
```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('all-MiniLM-L6-v2')

def generate_embeddings_for_creator(channel_id: str):
    """
    For each processed video:
    1. Chunk the summary by sections
    2. Generate embeddings for each chunk
    3. Store in content_embeddings table
    4. Optionally: Chunk transcripts for deeper search
    """
```

---

### 3. Hybrid Retrieval System
**Purpose**: Find the most relevant content chunks for a query using both semantic and keyword search.

#### Retrieval Strategy:
```python
def retrieve_relevant_content(
    channel_id: str,
    query: str,
    mode: str = 'hybrid',  # 'hybrid', 'semantic', 'keyword'
    top_k: int = 5,
    min_score: float = 0.6
) -> List[Dict]:
    """
    Hybrid retrieval:
    1. Semantic search (vector similarity) - finds conceptually related content
    2. Keyword search (FTS) - finds exact matches
    3. Combine and re-rank by relevance
    4. Filter by channel_id
    5. Return top_k results with metadata
    """
```

#### Re-ranking:
- Use Claude Haiku to score relevance (cheap, accurate)
- Combine semantic similarity + keyword match + temporal relevance
- Prioritize recent content or content explicitly about the topic

---

### 4. Persona-Aware Prompting System
**Purpose**: Construct prompts that make Claude respond as the creator would.

#### Prompt Template:
```python
def build_creator_prompt(
    creator_persona: Dict,
    retrieved_content: List[Dict],
    user_question: str,
    conversation_history: List[Dict],
    mode: str = 'grounded'  # 'grounded' or 'interpolated'
) -> str:
    """
    Construct a prompt that:
    1. Establishes the creator's persona
    2. Provides relevant content excerpts
    3. Instructs Claude to respond as the creator
    4. Sets strictness level (grounded vs interpolated)
    5. Includes conversation context
    """
    
    persona_context = f"""
You are {creator_persona['channel_name']}, responding in your usual style and perspective.

Your speaking style: {persona_context['style']}
Key frameworks you use: {persona_context['frameworks']}
Common topics: {persona_context['topics']}

IMPORTANT: Answer based ONLY on the provided content excerpts from your videos/articles.
"""
    
    if mode == 'grounded':
        persona_context += """
- Only use information explicitly stated in the provided excerpts
- If information is not in the excerpts, say "I haven't discussed this in my content"
- Cite specific videos/articles with titles and approximate timestamps
"""
    elif mode == 'interpolated':
        persona_context += """
- Use the provided excerpts as your primary source
- You may make logical connections BETWEEN excerpts
- You may reason about implications of your stated views
- If extrapolating, clearly state: "Based on my content about X and Y, I would likely think..."
- Never use general knowledge from your training data - only reason from the provided excerpts
"""
    
    # Add conversation history
    if conversation_history:
        history_text = "\n".join([
            f"User: {msg['question']}\nYou: {msg['answer']}"
            for msg in conversation_history[-5:]  # Last 5 exchanges
        ])
        persona_context += f"\n\nPrevious conversation:\n{history_text}\n"
    
    # Add retrieved content
    content_excerpts = "\n\n".join([
        f"From: {item['title']} (Published: {item['date']})\n{item['content']}"
        for item in retrieved_content
    ])
    
    final_prompt = f"""
{persona_context}

Relevant content from your videos/articles:
{content_excerpts}

Current question: {user_question}

Provide your answer:
"""
    
    return final_prompt
```

---

### 5. Conversation Management
**Purpose**: Maintain context across multiple questions in a session.

#### Storage:
```sql
CREATE TABLE IF NOT EXISTS chat_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id TEXT NOT NULL,
    session_id TEXT NOT NULL UNIQUE,  -- UUID
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    mode TEXT DEFAULT 'grounded',  -- 'grounded' or 'interpolated'
    
    FOREIGN KEY(channel_id) REFERENCES channel_subscriptions(channel_id)
)

CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,  -- 'user' or 'assistant'
    message TEXT NOT NULL,
    retrieved_content_ids TEXT,  -- JSON array of content_embeddings.id
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY(session_id) REFERENCES chat_sessions(session_id)
)
```

#### Conversation Flow:
```python
def handle_chat_message(
    channel_id: str,
    question: str,
    session_id: str,
    mode: str = 'grounded'
) -> Dict:
    """
    1. Load or create chat session
    2. Load conversation history (last N messages)
    3. Retrieve relevant content (hybrid search)
    4. Load creator persona
    5. Build persona-aware prompt
    6. Call Claude with prompt
    7. Store message in chat_messages
    8. Return response with citations
    """
```

---

### 6. Citation and Provenance System
**Purpose**: Track which content was used to generate each answer.

#### Citation Format:
```python
{
    "answer": "...",
    "citations": [
        {
            "video_id": 123,
            "title": "Video Title",
            "url": "https://youtube.com/...",
            "timestamp": "12:34",  # Approximate
            "excerpt": "Relevant quote...",
            "relevance_score": 0.89
        }
    ],
    "confidence": "high",  # 'high', 'medium', 'low'
    "sources_count": 3,
    "mode": "grounded"
}
```

---

### 7. Temporal Awareness
**Purpose**: Handle evolving views and contradictions over time.

#### Evolution Detection:
```python
def detect_view_evolution(
    channel_id: str,
    topic: str
) -> Dict:
    """
    Analyze how creator's views on a topic changed over time:
    1. Find all videos/articles about the topic
    2. Sort by date
    3. Extract key statements
    4. Identify shifts, contradictions, refinements
    5. Present evolution timeline
    """
```

#### Temporal Prompting:
```python
# When user asks about a topic, include temporal context:
"Note: The creator's views on this topic evolved:
- In 2022: [early view]
- In 2023: [shifted to...]
- In 2024: [current view]

Answer based on their most recent content, but acknowledge the evolution if relevant."
```

---

## Implementation Phases

### Phase 1: Foundation (Quick Win)
**Goal**: Channel-filtered chat with conversation history
- [x] Filter chat by channel_id
- [x] Add conversation history (session-based)
- [x] Use summaries instead of full transcripts
- [x] Basic persona extraction (from summaries)
- **Cost**: ~$0.001-0.003 per question
- **Time**: 2-3 hours

### Phase 2: Embeddings and Semantic Search
**Goal**: Better retrieval with vector search
- [ ] Install sentence-transformers
- [ ] Generate embeddings for existing content
- [ ] Implement hybrid retrieval (semantic + keyword)
- [ ] Add embedding generation to processing pipeline
- **Cost**: One-time embedding generation (~free with local model)
- **Time**: 4-6 hours

### Phase 3: Persona System
**Goal**: Extract and use creator personas
- [ ] Create creator_personas table
- [ ] Build persona extraction function
- [ ] Generate personas for existing creators
- [ ] Integrate persona into prompts
- **Cost**: ~$0.01-0.05 per persona generation (one-time)
- **Time**: 6-8 hours

### Phase 4: Advanced Features
**Goal**: Temporal awareness, citations, interpolation mode
- [ ] Add citation system
- [ ] Implement view evolution detection
- [ ] Add interpolation mode toggle
- [ ] Improve UI with citations and confidence indicators
- **Cost**: Same as Phase 1 (~$0.001-0.003 per question)
- **Time**: 8-10 hours

---

## API Endpoints

### Chat Endpoints
```python
# Start a chat session with a creator
POST /api/creators/<channel_id>/chat/session
{
    "mode": "grounded"  # or "interpolated"
}
Response: {
    "session_id": "uuid",
    "channel_name": "...",
    "mode": "grounded"
}

# Send a message
POST /api/creators/<channel_id>/chat/message
{
    "session_id": "uuid",
    "question": "...",
    "mode": "grounded"  # optional, overrides session mode
}
Response: {
    "answer": "...",
    "citations": [...],
    "confidence": "high",
    "sources_count": 3
}

# Get conversation history
GET /api/creators/<channel_id>/chat/session/<session_id>
Response: {
    "messages": [...],
    "mode": "grounded",
    "created_at": "..."
}

# Generate/update persona
POST /api/creators/<channel_id>/persona/generate
Response: {
    "persona": {...},
    "version": 1,
    "last_updated": "..."
}
```

---

## Cost Analysis

### One-Time Setup Costs:
- **Embedding generation**: Free (local model)
- **Persona generation**: ~$0.01-0.05 per creator (one-time, uses Haiku)
- **Total**: ~$0.05-0.25 for 5 creators

### Per-Question Costs:
- **Retrieval**: Free (local vector search)
- **Relevance filtering**: ~$0.0001 (Haiku, optional)
- **Main answer**: ~$0.001-0.003 (Haiku 4.5)
- **Total**: ~$0.001-0.003 per question

### Monthly Estimate (Example):
- 100 questions/month × $0.002 = $0.20/month
- 500 questions/month × $0.002 = $1.00/month
- 1000 questions/month × $0.002 = $2.00/month

---

## Quality Safeguards

### 1. Grounded Mode (Strict):
- Only uses content from knowledge base
- No extrapolation
- Clear "I don't know" responses

### 2. Interpolated Mode (Reasoned):
- Uses knowledge base as primary source
- Allows logical connections between excerpts
- Requires clear qualifiers for extrapolation
- Never uses general training data

### 3. Citation System:
- Every answer cites specific sources
- Shows relevance scores
- Links back to original content

### 4. Confidence Indicators:
- "Based on 3 videos" vs "Based on 1 video"
- "High confidence" vs "Low confidence"
- Shows when views evolved over time

### 5. Contradiction Detection:
- Highlights when views conflict
- Shows temporal evolution
- Explains shifts in perspective

---

## UI/UX Integration

### Channels Page:
- Add "Ask [Creator]" button for each subscription
- Show number of processed videos
- Indicate if persona is available

### Chat Interface:
- Dedicated modal or page for creator chat
- Toggle between "Grounded" and "Interpolated" modes
- Display citations with links to source videos
- Show confidence indicators
- Conversation history sidebar
- Export conversation option

### Document View Integration:
- Link citations back to document view
- Show "Related videos" based on chat context
- Highlight relevant sections in source content

---

## Next Steps

1. **Start with Phase 1** (channel-filtered chat)
2. **Test with real questions** to validate approach
3. **Add embeddings** if keyword search isn't sufficient
4. **Build persona system** for more authentic responses
5. **Add advanced features** (citations, temporal awareness)

---

## Technical Decisions

### Embedding Model:
- **Choice**: `sentence-transformers/all-MiniLM-L6-v2`
- **Reason**: Free, local, fast, good quality for semantic search
- **Alternative**: OpenAI embeddings (paid, better quality)

### Vector Database:
- **Choice**: SQLite with `sqlite-vss` OR FAISS
- **Reason**: Local, no extra infrastructure, good enough for <100k chunks
- **Alternative**: Pinecone (cloud, scalable, paid)

### LLM Model:
- **Choice**: Claude Haiku 4.5
- **Reason**: Cost-effective, good quality, fast
- **Alternative**: Claude Sonnet (better quality, 3x cost)

### Persona Storage:
- **Choice**: JSON in SQLite
- **Reason**: Simple, queryable, versioned
- **Alternative**: Separate vector store (overkill for personas)

---

## Future Enhancements

1. **Multi-creator comparison**: "How do Creator A and Creator B differ on topic X?"
2. **Topic exploration**: "What has [Creator] said about AI regulation?"
3. **Content recommendations**: "Based on this conversation, you might like these videos..."
4. **Export functionality**: Export conversations as markdown
5. **Analytics**: Track which topics are asked about most
6. **Fine-tuning**: Fine-tune a small model on creator's content (expensive, advanced)





