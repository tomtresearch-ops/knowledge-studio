## Creator Avatar / Agent Plan

This document captures the working plan for turning a creator’s channel feed into an interactive agent that can answer questions in their style. Update it as the system evolves.

### 1. Aggregate the Source Material
- Ensure the channel subscription is enabled and the queue runs until all desired videos are processed.
- For each processed item, store:
  - Full transcript (`videos.full_transcript`).
  - Structured summary (`videos.ai_summary` or `videos.summary`).
  - Key metadata: published date, tags/topics, duration, channel name, processed_video_id, etc.
- Optional enrichment: Classification tags, episode categories, manual highlights.

### 2. Build a Searchable Knowledge Base
- Normalize the text (remove boilerplate intros/outros where possible).
- Generate embeddings for:
  - Raw transcript chunks (e.g., 500–1,000 token windows).
  - Structured summary sections (Executive Summary, Key Ideas, etc.).
  - Any manually curated notes.
- Store embeddings in a vector index (Pinecone, pgvector, FAISS, SQLite VSS, etc.) with metadata linking back to `videos.id`, timestamps, and content type.
- Maintain a lightweight keyword index (SQLite FTS or OpenSearch) for exact searches alongside embeddings.

### 3. Retrieval Strategy
- Given a user query:
  1. Pull top-N relevant items from the embedding index (hybrid search is ideal: vector similarity + keyword filter).
  2. Gather associated metadata (title, publish date, transcript excerpt, summary).
  3. Compose a context bundle emphasizing: “Answer strictly using the provided passages; cite video titles/timestamps.”

### 4. Persona Prompting
- Construct an LLM/system prompt such as:
  ```
  You are <Creator Name>, responding in your usual tone and perspective.
  Use ONLY the supplied source excerpts. If a question is outside the content, acknowledge the gap.
  Reference the original clips (title + timestamp) when possible.
  ```
- Allow configurable strictness:
  - **Grounded mode**: refuse to speculate beyond the provided evidence.
  - **Interpolated mode**: allow reasoned extrapolation but require a “This is my interpretation” qualifier.

### 5. Dialogue Loop
- Keep a chat history so the agent can handle follow-up questions.
- For each turn, re-run retrieval based on the new question + conversation state.
- Optionally summarize earlier dialogue to stay within context limits.

### 6. UI / UX Integration
- Add an “Ask <Creator>” tab or modal on the Channels page once sufficient processed content exists.
- Display:
  - Answer text.
  - Citations with links back to document view (`viewAsDocument`) or YouTube with timestamps.
  - Confidence / grounding indicator (“Based on 3 clips”, etc.).
- Offer a toggle between “Grounded” and “Interpolated” modes.

### 7. Maintenance & Quality
- Periodically re-index when new episodes are processed.
- Track unanswered or low-confidence questions to identify content gaps.
- Allow manual curation: pin authoritative clips, blacklist irrelevant sections, annotate corrections.

### 8. Stretch Ideas
- Auto-generate creator “takes” summaries (daily/weekly digest).
- Provide topic filters (“Ask about business strategy”).
- Blend in external sources (creator’s blog, newsletter) with clear provenance tags.

---

**Next steps checklist**
- [ ] Finish populating the channel history (RSS + playlist fetch).
- [ ] Decide on embedding backend.
- [ ] Prototype retrieval + persona prompting (can start via notebook or CLI).
- [ ] Integrate the chat UX once retrieval output looks solid.





