# Purplle Retail Analytics — Store Intelligence Challenge

An end-to-end computer vision and analytics pipeline that processes raw retail CCTV footage to extract business-relevant metrics like conversion rates, zone dwell times, and queue depths — with a **live, real-time WebSocket dashboard**.

## Architecture

1. **Inference Pipeline (`run_pipeline.py`)**
   - Extracts CCTV footage from zip archives automatically.
   - Processes video at an optimized 5 FPS.
   - Utilizes YOLOv8 (with BotSort tracking) to detect and track individuals.
   - Uses `shapely` geometric polygons to map bounding boxes to store zones.
   - Emits structured events (ENTRY, EXIT, ZONE_DWELL, BILLING) to a local SQLite database.
   - **In `--live` mode**, streams every event to the API via HTTP in real time.

2. **Metrics API (`app/main.py`)**
   - A FastAPI application that serves the ingested events.
   - Computes unique visitors, average session durations, queue depths, and conversion funnels dynamically.
   - Flags anomalies (e.g., excessively long dwell times).
   - **WebSocket endpoint (`/ws/live`)** broadcasts events to connected dashboard clients instantly.

3. **Live Dashboard (`app/static/index.html`)** *(Part E — +10 bonus)*
   - Connects via WebSocket to `/ws/live`.
   - Updates metrics, event log, and conversion funnel **in real time** as the pipeline processes video.
   - Shows connection status, live event stream, event rate, and synchronized server timestamps.
   - **No page reload required** — the dashboard is genuinely live.

## Execution (Docker)

The system is fully containerized and will automatically spin up the API.

```bash
docker compose build
docker compose up -d
```

The API will be available at `http://localhost:8000`.
- Health Check: `GET /health`
- Store Metrics: `GET /metrics`
- **Live Dashboard**: `http://localhost:8000/dashboard/index.html`

## Execution (Local — Live Demo)

To run the full live system with the dashboard updating in real time:

1. **Install Dependencies**
```bash
pip install -r requirements.txt
```

2. **Start the API Server** *(Terminal 1)*
```bash
python -m uvicorn app.main:app
```

3. **Open the Live Dashboard** *(Browser)*
```
http://127.0.0.1:8000/dashboard/index.html
```

4. **Run the Pipeline in Live Mode** *(Terminal 2)*
```bash
python run_pipeline.py --live --extract-videos --pos-csv "datasets/Brigade_Bangalore_10_April_26 (1)bc6219c.csv"
```
*(To test quickly, append `--max-frames 300` for ~60 seconds of footage.)*

Watch the dashboard — metrics, the live event stream, and the conversion funnel update in real time as the pipeline detects and tracks people in the CCTV footage.

## Real-Time Data Flow

```
CCTV Video → YOLOv8 Detection → BotSort Tracking → Event Emitter
                                                        │
                                                        ▼
                                              POST /events/ingest
                                                        │
                                            ┌───────────┼───────────┐
                                            ▼           ▼           ▼
                                        SQLite DB   WebSocket    Metrics
                                                    Broadcast    Compute
                                                        │           │
                                                        ▼           ▼
                                                  Dashboard UI   /metrics
                                                  (real-time)    endpoint
```

## Evaluation Verification

- **System Execution**: Verified via `docker compose up`.
- **Live Dashboard**: WebSocket-powered, updates as pipeline runs. Proof of genuine Pipeline → API → Dashboard connection.
- **API Availability**: `/metrics` returns comprehensive funnel and anomaly stats.
- **Event Generation**: Pipeline creates `outputs/results/real_pos_events.json` and populates SQLite.
- **Documentation**: See `docs/DESIGN.md` for architecture and `docs/CHOICES.md` for trade-offs.
