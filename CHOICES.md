# CHOICES.md — Engineering Decisions and Trade-offs

This document details the critical architectural decisions, options considered, AI suggestions, and final trade-offs chosen for the Purplle Retail Analytics system.

---

## Decision 1: Detection & Tracking Model Selection

### 1. Options Considered
- **Option A**: High-fidelity visual foundation models (e.g., GPT-4V or Gemini 1.5 Flash VLM) running per-frame zone queries.
- **Option B**: YOLOv8 Medium (`yolov8m.pt`) for detection + ByteTrack + local OSNet embeddings for visual Re-ID matching.
- **Option C**: YOLOv8 Nano (`yolov8n.pt`) with native `botsort` tracking, and fallback to pythonic spatial-temporal heuristics.

### 2. What AI Suggested
The AI recommended **Option B** (YOLOv8 Medium + OSNet). It reasoned that a visual Re-ID network would provide the highest accuracy for matching visitors stepping in and out of camera angles.

### 3. What We Chose and Why
We chose **Option C** (YOLOv8 Nano + BotSort) for real-time video processing, and kept Option B as an offline high-precision validation configuration.
- **Dependency Isolation**: ByteTrack relies on the `lap` bipartite matching library, which frequently fails to compile on Windows target systems without full MSVC Build Tools. BotSort uses alternative distance functions and does not require local compiler setup, ensuring seamless `docker compose` execution on a clean machine.
- **Latency & Throughput**: Running YOLOv8 Medium with a secondary OSNet network on 5 concurrent camera feeds maxes out average CPU systems, resulting in heavy frame dropping. Selecting YOLOv8 Nano allows our pipeline to process at a constant 5 FPS, easily capturing quick zone crossings and billing queue joins.

---

## Decision 2: Event Schema Design Rationale

### 1. Options Considered
- **Option A**: Heavy, nested document-based JSON structure capturing the full user trajectory, bounding box coordinates, and visual features in a single session block.
- **Option B**: A lightweight, flat transaction event stream mapping discrete state changes (`ENTRY`, `EXIT`, `ZONE_ENTER`, `ZONE_EXIT`, `ZONE_DWELL`, `BILLING_*`) combined with a flexible key-value `metadata` dictionary.

### 2. What AI Suggested
The AI suggested **Option A**, arguing that keeping the entire visitor history in a single nested session payload simplifies frontend API requests.

### 3. What We Chose and Why
We chose **Option B** (Flat Transaction Event Stream).
- **Database Indexing**: Large nested JSON documents are highly inefficient to index and query in standard relational databases (SQLite/PostgreSQL). A flat schema allows us to index `store_id`, `visitor_id`, `timestamp`, and `event_type` columns directly.
- **Real-Time Stream Processing**: Ingesting discrete events allows the pipeline to act as a stateless emitter. Endpoints like `/metrics` and `/funnel` compile state dynamically from flat event tables rather than parsing deep nested JSON fields, maintaining sub-10ms API latency as the volume grows.

---

## Decision 3: API Architecture & Storage Engine

### 1. Options Considered
- **Option A**: Node.js / Express + MongoDB for dynamic event document storage.
- **Option B**: FastAPI + SQLite (with ORM layer fully compatible with PostgreSQL connection pooling).

### 2. What AI Suggested
The AI suggested **Option B** (FastAPI + Relational SQL) as the most suitable design for high-throughput transactional analytics.

### 3. What We Chose and Why
We chose **Option B** (FastAPI + SQLite/PostgreSQL-ready schema).
- **Asynchronous Execution**: FastAPI's asynchronous request loops (`async def`) are perfect for non-blocking event ingestion, allowing a single lightweight container to process concurrent batches from all 5 cameras.
- **SQL Aggregations**: Relational databases excel at dynamic time-window aggregations. We can compute complex metrics (such as the 5-minute asymmetric POS correlation window) using highly optimized SQL queries with indexing rather than loading large event arrays into memory and sorting in Python.
- **Enterprise Ready**: While SQLite provides zero-dependency, plug-and-play simplicity for local developer evaluation, the ORM design allows a simple configuration flag to swap the backend database to PostgreSQL for production scaling.
