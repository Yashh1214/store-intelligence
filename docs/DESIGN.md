# Architecture Design Document
## Purplle Tech Challenge 2026 — Round 2

---

## 1. System Overview

This retail analytics system processes video feeds from store cameras to track visitors, compute engagement metrics, and correlate with POS transactions. The system consists of two main components:

### Detection Pipeline
A computer vision pipeline that processes video frames to detect, track, and analyze visitor behavior:
- **Frame Processing** at 5 FPS constant rate (optimized for zone transition capture)
- **Person Detection** using YOLOv8m with ByteTrack multi-object tracking
- **Zone Occupancy** detection using polygon-based dual-rule logic
- **Dwell Tracking** with state machines and oscillation filtering
- **Staff Classification** using duration + zone coverage heuristics
- **Re-identification** for detecting re-entering visitors
- **Queue Analysis** in billing area
- **POS Correlation** for conversion tracking

### REST API
A FastAPI-based service that:
- Ingests detection events from the pipeline
- Stores events in SQLite (PostgreSQL-ready)
- Computes and serves metrics (visitors, conversion, dwell, queue, funnel)

---

## 2. Pipeline Architecture

```
Video Input (15 FPS)
    │
    ▼
┌─────────────────────────────────────┐
│ Frame Processor (5 FPS constant)    │  ← CORRECTION #1
│ Process every 3rd frame             │
│ 200ms interval captures transitions │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│ YOLOv8m + ByteTrack                │
│ Person detection (conf > 0.45)      │
│ Multi-object tracking (persistent)  │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│ Zone Occupancy Detector             │
│ Rule: center inside OR >50% bbox    │
│ Polygon-based zone geometry         │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│ Dwell Tracker (State Machine)       │
│ OUTSIDE → INSIDE → DWELLING → EXIT │
│ Oscillation filter (15 frames)      │
│ Dwell threshold: 30 seconds         │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│ Staff Classifier                    │  ← CORRECTION #2
│ 0.7 * duration + 0.3 * zones       │
│ Threshold: 0.6                      │
│ Auto-staff: > 20 minutes            │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│ Re-ID Matcher (Dual-Factor)         │  ← CORRECTION #3
│ Primary: OSNet embedding (> 0.80)   │
│ Tiebreaker: temporal + spatial      │
│ No pose estimation needed           │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│ Queue Analyzer                      │  ← CORRECTION #4
│ Queue depth = occupancy count       │
│ Works with any queue shape          │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│ POS Correlator                      │  ← CORRECTION #5
│ exit_time < txn < exit_time + 5min  │
│ Explicit, unambiguous window        │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│ Event Emitter → API → Database      │
│ ENTRY, EXIT, ZONE_*, BILLING_*,     │
│ REENTRY, STAFF_CLASSIFIED           │
└─────────────────────────────────────┘
```

---

## 3. Key Design Decisions

### 3.1 Frame Rate: 5 FPS Constant
- Zone transitions take 0.5–2 seconds
- At 5 FPS (200ms intervals), we capture 2–10 frames per transition
- Still efficient: processes only 17% of raw frames
- Constant rate is simpler and more predictable than adaptive

### 3.2 Zone Occupancy: Dual Rule
- Center point inside polygon → in zone (fast path)
- >50% bbox overlap → in zone (handles border cases)
- Uses Shapely for polygon intersection math

### 3.3 Dwell State Machine
- Prevents duplicate events and oscillation at boundaries
- 30-second threshold before emitting ZONE_DWELL
- 15-frame stability filter before confirming entry/exit

### 3.4 Staff Classification: Heuristic
- Duration is strongest signal (0.7 weight)
- Zone coverage supports it (0.3 weight)
- No appearance classifier needed (not available in dataset)

### 3.5 Queue Depth: Occupancy Count
- Count non-staff people in billing zone polygon
- Works with any queue shape (vertical, diagonal, spiral)
- Simpler and more robust than clustering

### 3.6 POS Correlation: Explicit Window
- Rule: exit_time < txn_time ≤ exit_time + 5 minutes
- Handles: kiosk delay, clock skew (±30s << 300s window)
- Asymmetric: only looks forward from exit

---

## 4. API Design

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/events/ingest` | POST | Batch event ingestion |
| `/events/ingest/single` | POST | Single event ingestion |
| `/stores/{id}/metrics` | GET | Store metrics (visitors, conversion, dwell, queue) |
| `/stores/{id}/funnel` | GET | Conversion funnel |
| `/stores/{id}/events` | GET | Raw events with filtering |
| `/health` | GET | Health check |

---

## 5. Data Model

### Events Schema
- `event_type`: ENTRY, EXIT, ZONE_ENTER, ZONE_EXIT, ZONE_DWELL, BILLING_QUEUE_JOIN, BILLING_QUEUE_EXIT, REENTRY, STAFF_CLASSIFIED
- `store_id`: Store identifier
- `visitor_id`: Unique per session
- `timestamp`: ISO-8601
- `metadata`: JSON (dwell_seconds, is_staff, queue_depth, etc.)

### Database
- SQLite for single-store deployment
- Indexed on: store_id, visitor_id, timestamp, event_type
- PostgreSQL-ready for multi-store scale

---

## 6. Scale Considerations

At 40 stores × 5K events/day = 200K events/day:
- **First bottleneck**: SQLite single-writer → migrate to PostgreSQL
- **Solution**: Redis queue for event buffering + PostgreSQL with connection pooling
- **Second bottleneck**: Query latency on large tables
- **Solution**: Composite indices, materialized views for metrics, time-based partitioning
