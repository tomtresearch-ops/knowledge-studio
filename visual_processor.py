"""
Visual Processor — OCR classification and structured data extraction for screenshots.

Takes non-YouTube screenshots, classifies them by content type (social post, chart,
whiteboard, document, handwritten, workflow), and extracts structured data per type.

Ported from ocr-intelligence/app.py and integrated into Knowledge Studio.
"""

import os
import io
import base64
import json
import re
import sqlite3
from datetime import datetime

import anthropic
import claude_cli_client  # routes inference to the subscription (see module docstring)
from PIL import Image


# --- Model routing ---
# Haiku classifies (cheap). Extraction routes to the best model per content type.
# Whiteboards/handwritten need spatial reasoning → Sonnet minimum.
# Charts need interpretation → Sonnet.
# Social posts/documents are straightforward → Haiku is fine.
MODEL_ROUTING = {
    'whiteboard':  'claude-sonnet-4-20250514',
    'handwritten': 'claude-sonnet-4-20250514',
    'chart':       'claude-sonnet-4-20250514',
    'workflow':    'claude-sonnet-4-20250514',
    'social_post': 'claude-haiku-4-5-20251001',
    'document':    'claude-haiku-4-5-20251001',
}
CLASSIFY_MODEL = 'claude-haiku-4-5-20251001'

# Claude API pricing per model (input/output per million tokens)
MODEL_PRICING = {
    'claude-haiku-4-5-20251001': (0.25, 1.25),
    'claude-sonnet-4-20250514':  (3.00, 15.00),
    'claude-opus-4-20250514':    (15.00, 75.00),
}

# Max image size for Claude API (5MB). Images above this get resized.
MAX_IMAGE_BYTES = 5 * 1024 * 1024

DATABASE_PATH = os.path.join(os.path.dirname(__file__), 'youtube_intelligence.db')


def calculate_cost(input_tokens, output_tokens, model=CLASSIFY_MODEL):
    """Calculate estimated cost based on token usage and model."""
    pricing = MODEL_PRICING.get(model, (0.25, 1.25))
    input_cost = (input_tokens / 1_000_000) * pricing[0]
    output_cost = (output_tokens / 1_000_000) * pricing[1]
    return input_cost + output_cost


# --- Content type detection prompts ---
# Order matters: first match wins, default is "document"

CONTENT_TYPE_PROMPTS = {
    'social_post': """
    Analyze this image to determine if it's a social media post. Look for:
    - Twitter/X interface elements
    - LinkedIn post formatting
    - Instagram story layout
    - Social media UI components
    - Post-like content structure

    Respond with just: SOCIAL_POST or NOT_SOCIAL_POST
    """,

    'chart': """
    Analyze this image to determine if it's a chart, graph, or data visualization. Look for:
    - Trading charts (crypto, stock, forex)
    - Business metrics and KPIs
    - Infographics with data
    - Bar charts, line graphs, pie charts
    - Financial data displays

    Respond with just: CHART or NOT_CHART
    """,

    'whiteboard': """
    Analyze this image to determine if it's a whiteboard, planning board, framework, or brainstorming diagram. Look for:
    - Hand-drawn or marker-drawn content on a whiteboard or paper
    - Handwritten text with arrows, boxes, circles, or connections
    - Business strategy frameworks, mind maps, or concept maps
    - Planning boards with multiple topics, zones, or conceptual areas
    - Any image where the content appears to be written by hand (not typed)
    - Mixed content: diagrams, lists, notes, and frameworks combined

    IMPORTANT: If the image contains handwritten text on a whiteboard or board, this IS a whiteboard even if it also shows a workflow or process.

    Respond with just: WHITEBOARD or NOT_WHITEBOARD
    """,

    'workflow': """
    Analyze this image to determine if it's a DIGITAL workflow, pipeline, or system architecture diagram. Look for:
    - Tool chains or integration diagrams made with software (not hand-drawn)
    - Software architecture diagrams with typed text
    - Pipeline diagrams (data, CI/CD, content) created digitally
    - Agent workflow or automation diagrams
    - API flow or sequence diagrams

    IMPORTANT: Hand-drawn diagrams on whiteboards are NOT workflows — they are whiteboards. Only classify as WORKFLOW if the diagram appears to be digitally created.

    Respond with just: WORKFLOW or NOT_WORKFLOW
    """,

    'document': """
    Analyze this image to determine if it's a document or article. Look for:
    - Article or newsletter layout
    - Research paper formatting
    - Text-heavy content
    - Professional document structure
    - Reading material format

    Respond with just: DOCUMENT or NOT_DOCUMENT
    """,

    'handwritten': """
    Analyze this image to determine if it contains handwritten content. Look for:
    - Handwritten notes
    - Sketches or drawings
    - Meeting notes
    - Brainstorming sessions
    - Personal annotations

    Respond with just: HANDWRITTEN or NOT_HANDWRITTEN
    """,
}


# --- Content-specific extraction prompts ---

EXTRACTION_PROMPTS = {
    'social_post': """
    You are an intelligence analyst. Analyze this social media post and extract BOTH the raw content AND your interpretation of why it matters.

    ## Layer 1 — Extraction
    - Platform, author, post text, engagement metrics, hashtags, quoted content

    ## Layer 2 — Intelligence (this is the valuable part)
    - **Claims analysis**: What is the author actually arguing? What's the subtext?
    - **Signal strength**: Is this a leading indicator, consensus view, or contrarian take?
    - **Context**: What broader trend or debate does this connect to?
    - **Why it was captured**: What makes this worth saving? What's the insight?

    Return as JSON:
    {
        "platform": "twitter|linkedin|instagram|other",
        "author": "username or name",
        "content": "main post text",
        "key_claims": ["claim1", "claim2"],
        "quoted_content": "any quoted text",
        "hashtags": ["#tag1", "#tag2"],
        "engagement": {"likes": 0, "retweets": 0, "comments": 0},
        "synthesis": {
            "core_argument": "What the author is really saying, in your words",
            "signal_type": "leading_indicator|consensus|contrarian|breaking_news|analysis",
            "connects_to": "What broader trend, debate, or theme this relates to",
            "why_it_matters": "1-2 sentences on why someone would save this"
        }
    }
    """,

    'chart': """
    You are a financial and data analyst. Analyze this chart/visualization and provide BOTH precise data extraction AND interpretive analysis.

    ## Layer 1 — Data Extraction
    - Chart type, title, labels, data points with exact values
    - Time period, assets/metrics tracked, scale and ranges
    - Any indicators, overlays, or technical signals visible

    ## Layer 2 — Analysis (this is the valuable part)
    - **What the data is saying**: Interpret the trends, not just list them. What story does this chart tell?
    - **Historical context**: How does the current reading compare to historical patterns? What happened last time this pattern appeared?
    - **Implications**: What does this suggest about what comes next? What should the viewer be watching for?
    - **Confidence level**: How reliable is this signal? What could invalidate the thesis?

    Return as JSON:
    {
        "chart_type": "line|bar|pie|candlestick|scatter|area|overlay|other",
        "title": "exact chart title",
        "indicator": "any technical indicator or overlay shown",
        "data_points": [{"label": "label", "value": "value", "unit": "unit"}],
        "legend": {"key": "description for each legend item"},
        "trends": ["specific trend"],
        "timeframe": "time period covered",
        "asset": "asset or metric name",
        "scale_info": "value ranges and thresholds",
        "synthesis": {
            "narrative": "2-3 sentences telling the story this chart shows",
            "current_signal": "What the chart is signaling right now",
            "historical_pattern": "How this compares to past instances of similar patterns",
            "implication": "What this suggests about the near future",
            "watch_for": "What would confirm or invalidate this reading",
            "confidence": "high|medium|low with brief explanation"
        }
    }
    """,

    'workflow': """
    You are a systems architect and strategic analyst. Analyze this workflow/pipeline/architecture diagram and provide BOTH a technical inventory AND strategic analysis.

    ## Layer 1 — Technical Extraction
    - All tools, services, components, and their roles
    - Data flow sequence and connections
    - Inputs, outputs, architecture pattern

    ## Layer 2 — Strategic Analysis (this is the valuable part)
    - **System intent**: What problem is this architecture solving? What's the big idea?
    - **Strengths**: What's clever or well-designed about this approach?
    - **Vulnerabilities**: Where are the single points of failure, bottlenecks, or scaling risks?
    - **Build vs. buy**: Which components are custom-built vs. off-the-shelf?
    - **Evolution path**: How would this system need to evolve as scale increases?

    Return as JSON:
    {
        "title": "system or workflow name",
        "purpose": "what this system does — the big picture, not just mechanics",
        "tools": ["tool1", "tool2"],
        "flow": [{"step": 1, "component": "name", "action": "what it does"}],
        "connections": [{"from": "A", "to": "B", "method": "API/webhook/etc"}],
        "inputs": ["input1"],
        "outputs": ["output1"],
        "architecture_pattern": "pipeline|event-driven|request-response|other",
        "synthesis": {
            "strategic_intent": "What problem this solves and why this approach was chosen",
            "strengths": ["What's well-designed about this architecture"],
            "vulnerabilities": ["Single points of failure, bottlenecks, or risks"],
            "key_insight": "The most important thing to understand about this system",
            "evolution": "How this would need to change at 10x scale"
        }
    }
    """,

    'whiteboard': """
    You are a strategic analyst examining a whiteboard or planning board. You must do TWO things: TRANSCRIBE what's actually written, then INTERPRET it.

    ## CRITICAL RULE: Read the actual text first.
    Do NOT summarize or abstract. Whiteboards contain the author's actual words and phrases — these are the data. Your first job is to read and transcribe every word, label, phrase, and annotation you can see. Your second job is to make sense of it.

    ## Layer 1 — Faithful Transcription
    - Divide the board into zones based on visual groupings (circled areas, boxed sections, clusters of related text)
    - For each zone: transcribe ALL visible text — every word, label, bullet point, annotation
    - Use the author's EXACT words as the zone name, not your summary of what the zone is about
    - Note arrows and connectors between zones — these show the author's thinking about relationships
    - List every name, brand, tool, or entity mentioned anywhere on the board

    ## Layer 2 — Strategic Synthesis (after you've read everything)
    - **Core thesis**: What is this whiteboard trying to figure out or plan?
    - **Key insight**: The most important thing someone should understand from this board
    - **Connections**: What relationships between concepts is the author exploring?
    - **Gaps**: What's missing or needs further development?
    - **Action items**: What next steps does this board suggest?

    Return as JSON:
    {
        "title": "Main title or header written on the board (use exact text)",
        "zones": [
            {
                "zone": "exact text of zone header or label",
                "location": "position on board (top-left, center, etc.)",
                "transcribed_text": ["every line/phrase/label visible in this zone, one per array item"],
                "arrows_to": ["other zone names this connects to, if arrows visible"],
                "interpretation": "1-2 sentences on what this zone represents"
            }
        ],
        "key_concepts": ["every significant concept, topic, or theme mentioned on the board"],
        "relationships": [{"from": "A", "to": "B", "type": "relationship type shown by arrow/connector"}],
        "people_or_brands": ["every name, brand, tool, or entity mentioned anywhere"],
        "framework_type": "mind_map|process_flow|strategy|organizational|brainstorm|other",
        "synthesis": {
            "core_thesis": "What this whiteboard is fundamentally about",
            "key_insight": "The most important takeaway",
            "connections": "What relationships between ideas the author is exploring",
            "gaps": "What's missing, implied, or needs further development",
            "action_items": ["Concrete next steps suggested by this board"]
        }
    }

    **IMPORTANT**: Only include "data_points" if there is an actual chart, graph, table, or numeric data visible. If none, omit it.
    """,

    'document': """
    You are an intelligence analyst processing a captured document. Extract the content AND provide analysis that makes this document more useful than reading it raw.

    ## Layer 1 — Content Extraction
    - Title, section headers, key points, specific facts/numbers
    - Document type, structure, source if identifiable

    ## Layer 2 — Intelligence Analysis (this is the valuable part)
    - **Core argument**: What is this document actually saying? Summarize the thesis in 1-2 sentences.
    - **Signal value**: Is this reporting consensus, revealing something new, or making a prediction?
    - **Implications**: What should the reader do differently after reading this?
    - **Context**: How does this connect to broader industry trends or debates?

    Return as JSON:
    {
        "title": "document title",
        "document_type": "article|report|newsletter|research|tweet_thread|other",
        "headlines": ["section headers"],
        "key_points": ["main arguments"],
        "facts": [{"fact": "statement", "value": "number", "context": "why it matters"}],
        "sections": [{"title": "section", "content": "summary"}],
        "synthesis": {
            "core_argument": "The document's thesis in 1-2 clear sentences",
            "signal_value": "new_information|consensus|prediction|analysis|opinion",
            "implications": "What this means for the reader — what to watch, do, or think about",
            "connects_to": "Broader trends or debates this relates to"
        }
    }
    """,

    'handwritten': """
    You are a strategic analyst deciphering handwritten notes. Your job is to convert messy human thinking into clear, structured intelligence.

    ## Layer 1 — Transcription
    - Convert ALL handwritten text to digital text, preserving structure
    - Identify lists, bullet points, numbering, indentation
    - Extract names, dates, numbers, and key terms
    - Note any sketches, diagrams, or visual elements

    ## Layer 2 — Interpretation (this is the valuable part)
    - **What was being worked on**: What problem or question prompted these notes?
    - **Key decisions or insights**: What did the author figure out or decide?
    - **Unfinished threads**: What was started but not completed? What needs follow-up?
    - **Clean summary**: Restate the notes as a clear, organized brief

    Return as JSON:
    {
        "converted_text": "full text transcription preserving structure",
        "sections": [{"title": "section or topic", "items": ["item1", "item2"]}],
        "key_info": {"names": [], "dates": [], "numbers": [], "key_terms": []},
        "purpose": "meeting_notes|brainstorming|planning|personal|list|other",
        "synthesis": {
            "context": "What was being worked on — the situation that prompted these notes",
            "key_decisions": ["Decisions or conclusions reached"],
            "unfinished": ["Threads that need follow-up"],
            "clean_summary": "The notes restated as a clear 2-4 sentence brief"
        }
    }
    """,
}


def _get_media_type(filepath):
    """Detect media type from image file."""
    with Image.open(filepath) as img:
        fmt = (img.format or 'jpeg').lower()
        return {
            'jpeg': 'image/jpeg',
            'jpg': 'image/jpeg',
            'png': 'image/png',
            'gif': 'image/gif',
            'webp': 'image/webp',
        }.get(fmt, 'image/jpeg')


def _encode_image(filepath):
    """Read, resize if needed, and base64-encode an image file.

    Claude API has a 5MB limit. If the image exceeds that, resize it
    while maintaining aspect ratio until it fits.
    """
    raw = open(filepath, 'rb').read()
    # Base64 encoding inflates size by ~33%, so check against that
    estimated_b64_size = len(raw) * 4 // 3
    if estimated_b64_size <= MAX_IMAGE_BYTES:
        return base64.b64encode(raw).decode('utf-8')

    # Resize progressively until under 5MB
    print(f"  Image {len(raw)/1024/1024:.1f}MB > 5MB limit, resizing...")
    with Image.open(filepath) as img:
        quality = 85
        scale = 0.8
        while True:
            new_size = (int(img.width * scale), int(img.height * scale))
            resized = img.resize(new_size, Image.LANCZOS)
            buf = io.BytesIO()
            resized.save(buf, format='JPEG', quality=quality)
            data = buf.getvalue()
            if len(data) <= MAX_IMAGE_BYTES:
                print(f"  Resized to {new_size[0]}x{new_size[1]} ({len(data)/1024/1024:.1f}MB)")
                return base64.b64encode(data).decode('utf-8')
            scale *= 0.8
            quality = max(60, quality - 5)


def _parse_json_response(text):
    """Parse JSON from Claude response, handling markdown code blocks."""
    text = text.strip()

    # Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Extract from markdown code block
    match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Find any JSON object
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return {"raw_text": text}


def detect_content_type(image_b64, media_type="image/jpeg"):
    """Classify image content type using sequential Claude Vision calls.

    Uses Haiku for classification (cheap — just needs a yes/no per type).
    Returns (content_type, usage_stats).
    """
    client = claude_cli_client.make_client()
    usage_stats = {'api_calls': 0, 'input_tokens': 0, 'output_tokens': 0, 'cost': 0.0}

    for content_type, prompt in CONTENT_TYPE_PROMPTS.items():
        try:
            response = client.messages.create(
                model=CLASSIFY_MODEL,
                max_tokens=50,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image", "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_b64,
                        }},
                    ],
                }],
            )
            usage_stats['api_calls'] += 1
            if hasattr(response, 'usage'):
                usage_stats['input_tokens'] += response.usage.input_tokens
                usage_stats['output_tokens'] += response.usage.output_tokens
                usage_stats['cost'] += calculate_cost(
                    response.usage.input_tokens,
                    response.usage.output_tokens,
                    CLASSIFY_MODEL)

            result = response.content[0].text.strip().upper()
            expected = content_type.upper()
            if result.startswith(expected):
                return content_type, usage_stats

        except Exception as e:
            print(f"  Warning: classification call failed for {content_type}: {e}")
            continue

    return 'document', usage_stats


def extract_structured_data(image_b64, content_type, media_type="image/jpeg"):
    """Extract structured data based on detected content type.

    Routes to the appropriate model:
    - Whiteboards, handwritten, charts, workflows → Sonnet (needs interpretation)
    - Social posts, documents → Haiku (straightforward extraction)

    Returns (structured_data_dict, usage_stats).
    """
    client = claude_cli_client.make_client()
    model = MODEL_ROUTING.get(content_type, CLASSIFY_MODEL)
    usage_stats = {'api_calls': 0, 'input_tokens': 0, 'output_tokens': 0, 'cost': 0.0, 'model': model}

    prompt = EXTRACTION_PROMPTS.get(content_type, EXTRACTION_PROMPTS['document'])

    print(f"  Routing to {model} for {content_type} extraction")

    try:
        response = client.messages.create(
            model=model,
            max_tokens=4000,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image", "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": image_b64,
                    }},
                ],
            }],
        )
        usage_stats['api_calls'] += 1
        if hasattr(response, 'usage'):
            usage_stats['input_tokens'] += response.usage.input_tokens
            usage_stats['output_tokens'] += response.usage.output_tokens
            usage_stats['cost'] = calculate_cost(
                response.usage.input_tokens,
                response.usage.output_tokens,
                model)

        return _parse_json_response(response.content[0].text), usage_stats

    except Exception as e:
        print(f"  Error in extraction: {e}")
        return {"error": str(e)}, usage_stats


def generate_auto_tags(structured_data, content_type):
    """Generate tags from extracted structured data."""
    tags = [content_type]

    if not isinstance(structured_data, dict):
        return tags

    if content_type == 'social_post':
        if 'platform' in structured_data:
            tags.append(structured_data['platform'])
        if 'hashtags' in structured_data:
            tags.extend(structured_data['hashtags'][:5])
        if 'author' in structured_data and structured_data['author']:
            tags.append(structured_data['author'])

    elif content_type == 'chart':
        if 'chart_type' in structured_data:
            tags.append(structured_data['chart_type'])
        if 'asset' in structured_data and structured_data['asset']:
            tags.append(structured_data['asset'])

    elif content_type == 'workflow':
        if 'tools' in structured_data:
            tags.extend(structured_data['tools'][:5])
        if 'architecture_pattern' in structured_data:
            tags.append(structured_data['architecture_pattern'])

    elif content_type == 'whiteboard':
        if 'framework_type' in structured_data:
            tags.append(structured_data['framework_type'])
        if 'key_concepts' in structured_data:
            tags.extend(structured_data['key_concepts'][:3])

    elif content_type == 'document':
        if 'document_type' in structured_data:
            tags.append(structured_data['document_type'])
        if 'headlines' in structured_data:
            tags.extend(structured_data['headlines'][:2])

    elif content_type == 'handwritten':
        if 'purpose' in structured_data:
            tags.append(structured_data['purpose'])

    return list(set(tags))


def ensure_table(db_path=None):
    """Create visual_captures table if it doesn't exist."""
    if db_path is None:
        db_path = DATABASE_PATH
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS visual_captures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            content_type TEXT NOT NULL,
            raw_ocr_text TEXT,
            structured_data TEXT,
            tags TEXT,
            source_context TEXT,
            api_calls_count INTEGER DEFAULT 0,
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            estimated_cost REAL DEFAULT 0.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            review_status TEXT DEFAULT 'complete',
            summary_50 TEXT
        )
    ''')
    try:
        cursor.execute("ALTER TABLE visual_captures ADD COLUMN summary_50 TEXT")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()


def is_already_processed(filename, db_path=None):
    """Check if a filename has already been processed."""
    if db_path is None:
        db_path = DATABASE_PATH
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM visual_captures WHERE filename = ?', (filename,))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists


def process_visual_capture(filepath, source_context=None, db_path=None):
    """Process a single image: classify, extract, store.

    Args:
        filepath: Path to the image file
        source_context: Optional context string (e.g. 'upload', 'batch_import')
        db_path: Optional database path override

    Returns:
        dict with id, content_type, structured_data, tags, estimated_cost
    """
    if db_path is None:
        db_path = DATABASE_PATH

    ensure_table(db_path)

    filename = os.path.basename(filepath)

    # Encode image
    image_b64 = _encode_image(filepath)
    media_type = _get_media_type(filepath)

    print(f"  Classifying: {filename}")
    content_type, detect_stats = detect_content_type(image_b64, media_type)
    print(f"  Detected: {content_type}")

    # Whiteboards, charts, and handwritten → queue for Claude Code (Opus) review
    # These need full project context for quality extraction.
    # Simple types (social_post, document, workflow) → extract immediately with API.
    QUEUE_FOR_REVIEW = {'whiteboard', 'handwritten', 'chart'}

    if content_type in QUEUE_FOR_REVIEW:
        print(f"  Queued for Claude Code review (type: {content_type})")
        structured_data = {"pending": True, "note": "Awaiting Claude Code analysis for full context extraction"}
        tags = [content_type, 'pending_review']
        review_status = 'pending_review'
        total_api_calls = detect_stats['api_calls']
        total_input = detect_stats['input_tokens']
        total_output = detect_stats['output_tokens']
        cost = detect_stats.get('cost', 0.0)
    else:
        print(f"  Extracting structured data...")
        structured_data, extract_stats = extract_structured_data(image_b64, content_type, media_type)
        tags = generate_auto_tags(structured_data, content_type)
        review_status = 'complete'
        total_api_calls = detect_stats['api_calls'] + extract_stats['api_calls']
        total_input = detect_stats['input_tokens'] + extract_stats['input_tokens']
        total_output = detect_stats['output_tokens'] + extract_stats['output_tokens']
        cost = detect_stats.get('cost', 0.0) + extract_stats.get('cost', 0.0)
        extraction_model = extract_stats.get('model', CLASSIFY_MODEL)
        print(f"  Model: {extraction_model} | Cost: ${cost:.4f}")

    # Store in database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO visual_captures
        (filename, content_type, raw_ocr_text, structured_data, tags, source_context,
         api_calls_count, input_tokens, output_tokens, estimated_cost, review_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        filename,
        content_type,
        json.dumps(structured_data),
        json.dumps(structured_data),
        json.dumps(tags),
        source_context or 'upload',
        total_api_calls,
        total_input,
        total_output,
        cost,
        review_status,
    ))
    capture_id = cursor.lastrowid
    conn.commit()
    conn.close()

    status_label = "QUEUED" if review_status == 'pending_review' else f"${cost:.4f}"
    print(f"  Stored as visual capture #{capture_id} ({status_label})")

    return {
        'id': capture_id,
        'content_type': content_type,
        'review_status': review_status,
        'structured_data': structured_data,
        'tags': tags,
        'estimated_cost': cost,
        'filename': filename,
    }
