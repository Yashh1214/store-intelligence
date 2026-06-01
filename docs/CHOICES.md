# CHOICES.md — Engineering Decisions and Trade-offs

This document outlines the core architectural and implementation decisions made during the construction of the Purplle Retail Analytics pipeline.

## 1. Tracking Engine: BotSort vs ByteTrack
**Decision**: We configured YOLOv8 to use the `botsort` tracking algorithm by default instead of `bytetrack`.
**Trade-off**: 
While ByteTrack is exceptionally fast, it relies on the `lap` (Linear Assignment Problem) library for bipartite matching. The `lap` library often fails to install or compile on Windows environments lacking specific C++ Build Tools. BotSort, while marginally slower on CPU, does not carry this strict dependency and ensures the system can be deployed universally (including via standard Docker containers) without manual compiler intervention.

## 2. Zone Mapping Strategy
**Decision**: We implemented a **dual-rule boundary logic** in `ZoneOccupancyDetector`:
1. If the center-point of the bounding box is strictly inside the polygon, the person is in the zone.
2. If the center-point is outside, but the bounding box overlaps with the zone by >50%, they are also considered in the zone.
**Trade-off**:
A strict center-point rule fails when a person is standing near the edge of a zone (e.g., reaching for a product in the MAKEUP zone while standing in the aisle). However, purely using overlap can cause a person to oscillate between zones. The dual-rule strategy prioritizes the center-point for stability but falls back to overlap coverage for edge cases, yielding a much higher spatial accuracy at the cost of a slightly more expensive geometric computation via `shapely`.

## 3. Re-identification and Session Management
**Decision**: We manage re-entry and tracking loss exclusively via time-based and zone-based state memory in `SessionManager`, rather than deploying a heavy visual ReID (Re-Identification) model.
**Trade-off**:
Deploying a secondary visual ReID model (like OSNet or Torchreid) on top of YOLOv8 for every frame would exponentially increase CPU requirements, making it impossible to process 5 high-resolution cameras simultaneously on consumer hardware without massive frame dropping. By implementing a 15-frame stability filter and tracking exit/entry zones, we accurately construct sessions and handle minor occlusions purely through algorithmic logic rather than deep learning, sacrificing perfect cross-camera tracking for a massive leap in processing efficiency.

## 4. Video Frame Sampling
**Decision**: The pipeline reads the 24/29 FPS videos but processes only 5 FPS using `FrameProcessor`.
**Trade-off**:
5 frames per second is the exact sweet spot for retail analytics. It is fast enough to capture rapid zone crossings and queue movements, but it strips out 80% of redundant frames, drastically lowering inference times.

## 5. Mock Data Purge
**Decision**: All synthetic demo data and mock logic previously used in the system were completely removed.
**Trade-off**:
While demo logic allows the application to be tested without raw CCTV footage, it violates the requirement for real computation. The entire pipeline now strictly depends on running inference directly on the `.mp4` files.

## 6. Cross-Camera Session Finalization Timeout
**Decision**: Instead of finalizing visitor sessions immediately when a local camera track is lost, we implement a grace-period-based finalization strategy based on the last seen location.
1. If a person was last seen in the `ENTRY` zone (near physical exit doors), we apply a **10-second grace period** before finalizing their session.
2. If they were in any other browse/product zone (e.g. `MAKEUP`, `SKINCARE`), they might just be occluded by shelves or in transit between overlapping camera views, so we apply a **30-second grace period**.
**Trade-off**:
While immediate finalization is simpler, it breaks multi-camera identity linkage. In a true multi-camera environment, visitors walk in and out of camera views, causing the local trackers to drop and recreate tracks. By introducing a grace period, we prevent a single visitor journey from being split into multiple independent visitor sessions, resolving the visitor inflation issue and producing mathematically sound conversion funnel counts.
