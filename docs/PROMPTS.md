# PROMPTS.md — AI Workflow & Agentic Decision Making

This document satisfies the requirement for "AI usage depth (prompts, DESIGN.md, CHOICES.md)". Below is a summary of the iterative AI prompting, planning, and agentic workflows utilized to build this complete Store Intelligence pipeline from scratch.

## Phase 1: Exploration and Deconstruction
**Goal**: Understand the raw datasets, physical layouts, and assess the initial mock structure provided in the repo.
**Prompt Concept**: 
*"Analyze all datasets inside the `datasets/` folder. Understand their schema, columns, labels, formats, missing values, and relationships. Compare the dataset structure with our current pipeline/codebase."*

**AI Agent Workflow**:
- Used standard data analysis tools (`pandas`) to parse the provided `Brigade_Bangalore_10_April_26.csv`.
- Read and extracted the geometric bounds from `Brigade Road - Store layoutc5f5d56.xlsx`.
- Reviewed the original boilerplate code and identified that it was using mock `run_demo_pipeline` logic rather than processing the real MP4 video files.

## Phase 2: Complete Architectural Rebuild
**Goal**: Strip away mock logic and implement a genuine CV inference pipeline using YOLOv8, capable of converting video to structured database events.
**Prompt Concept**: 
*"I want you to rebuild and clean the entire project using ONLY the datasets present inside the datasets/ folder. Remove all old/sample/temporary datasets previously used in the project... Rebuild the complete pipeline so the project works end-to-end with these datasets... Correct dataset loading, Data preprocessing, Feature engineering, Model training, Validation/testing, Prediction/inference pipeline..."*

**AI Agent Workflow**:
- Evaluated heavy-weight visual ReID approaches vs pure algorithmic zone tracking.
- Chose `YOLOv8m` + `BotSort` + `Shapely` based on CPU constraints and OS interoperability (abandoning ByteTrack due to `lap` dependencies on Windows).
- Drafted a multi-step execution plan encompassing:
  1. `extract_videos.py` to handle the large zip file.
  2. `FrameProcessor` to limit frame rate processing to 5 FPS.
  3. `SessionManager` to handle re-entries and state without AI bloat.
  4. Integration with POS timestamps.

## Phase 3: The "Acceptance Gate" Audit
**Goal**: Ensure every single line-item in the Evaluation Framework PDF was hit perfectly.
**Prompt Concept**:
*"Now perform a complete audit of the project against the requirements mentioned in the Purple Tech Challenge document. Verify whether the system is fully working and submission-ready... If anything is missing, implement/fix it before giving the final verdict."*

**AI Agent Workflow**:
- Scraped the PDF using OCR-to-Text conversion tools.
- Iterated line-by-line over the Rubric:
  - Added Docker containerization.
  - Implemented the specific `/metrics` endpoint.
  - Added Anomaly Detection (`metrics.py`).
  - Swapped standard Python `logging` for `structlog` to achieve 100% JSON structured logs.
  - Built a real-time Vanilla CSS Dashboard served over FastAPI to secure the +10 bonus points.

## Conclusion
The AI usage throughout this project was not purely code generation. It was deeply architectural—acting as a Principal Engineer evaluating trade-offs (e.g., dropping ByteTrack for BotSort, implementing dual-rule BBox matching over purely center-point matching), defining state lifecycles, and ensuring compliance against a strict grading rubric.
