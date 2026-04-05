# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Application

```bash
# Activate virtual environment
source .venv/bin/activate

# Start PostgreSQL database (requires Docker Desktop running)
docker-compose up -d

# Run the application
python app.py

# Initialize/reset database schema
python init_db.py
```

There are no test or lint commands configured in this project.

## Architecture Overview

**Acknowledge** is a PySide6 desktop application for media archiving, IPTC metadata editing, and face detection, backed by PostgreSQL with pgvector.

### Layer Structure

```
UI Layer       → app.py (MainWindow), root-level widget files
Service Layer  → src/services/  (business logic, orchestration)
Repository Layer → src/repositories/  (data access via SQLAlchemy)
Domain Layer   → src/domain/entities/, src/domain/value_objects/
ORM Models     → src/models.py  (SQLAlchemy table definitions)
DB Setup       → src/database.py  (engine, session, connection management)
```

### Key Architectural Decisions

**ApplicationService as Facade** — `src/services/application_service.py` is the single entry point from `app.py` into all business logic. It instantiates and wires all repositories and services via constructor injection. `MainWindow` holds one `ApplicationService` instance and calls through it.

**Dual Metadata Persistence** — IPTC metadata is stored in two places simultaneously: written directly to image files via `iptcinfo3` and persisted in the `medias` table. On gallery load, the DB copy takes priority for speed; `_write_iptc_to_file()` in `app.py` handles file-side writes.

**Deferred Background Loading** — Gallery items pre-populate metadata from the DB immediately, then enqueue heavy file I/O (thumbnail generation, file-based IPTC) as background tasks via Qt thread pools.

**Face Detection Pipeline** — `FaceAnalysisService` (`src/services/face_analysis_service.py`) uses insightface `buffalo_l` model (ArcFace, 512-dim embeddings). Detection results are stored in `face_detections` table (normalised bbox + `Vector(512)` embedding) and linked to `Person` records via `media_persons`. Bounding boxes rendered via `FaceOverlayWidget`. `medias.face_encoding` (`Vector(128)`) is a legacy unused column.

**Search/Filter** — `GallerySearchProxyModel` (in `gallery_item_model.py`) wraps the gallery model as a Qt proxy model, enabling keyword filtering and relevance-based sorting without reloading from DB.

**Path Storage** — `src/utils/path_util.py` stores file paths in the DB as relative paths from the project root (forward slashes). `to_db_path()` converts absolute → relative on write; `from_db_path()` converts back on read. Absolute legacy paths are handled as a fallback. Always use these helpers when reading/writing `file_path` columns to avoid cross-machine path breakage.

**Thumbnail Caching** — Thumbnails are pre-generated into a `.thumbnails/` subdirectory inside each event's vault folder (e.g. `vault/EventName/.thumbnails/photo.jpg.thumb.jpg`). Generated during import in `EventService.create_and_import_event()` and lazily on first gallery load via `GalleryItemModel.generate_pixmap()`.

### Database

PostgreSQL + pgvector. Connection configured via `.env`:
```
DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME
MEDIA_VAULT_PATH
```

Schema is managed by `init_db.py` using `Base.metadata.create_all()` plus dynamic `ALTER TABLE` for IPTC columns. No migration framework is used.

Key tables: `events` → `medias` (cascade delete) ↔ `persons` (via `media_persons`), `face_detections`.

### UI Structure

`MainWindow` in `app.py` owns the full layout:
- Left panel: event list (`QScrollArea` of `EventCardWidget` items) — `event_card_widget.py`
- Center: gallery grid (`QListView` + `GalleryItemModel`) — `gallery_item_model.py`
- Right panel: IPTC metadata form + face detection controls
- Bottom: `SingleViewWidget` for full-size image with `FaceOverlayWidget` overlay — `single_view_widget.py`, `face_overlay_widget.py`
- Tab widget: Events tab (main view) + Settings tab

Event import dialog is `add_event_window.py`. `BatchFaceWorker` (QThread subclass in `app.py`) runs face detection + auto-person-matching in the background.
