# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Application

```bash
# Activate virtual environment
source venv/bin/activate

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

**Face Detection Pipeline** — MediaPipe detects faces → bounding boxes rendered via `FaceOverlayWidget` → embeddings (128-dim vectors) stored in `medias.face_encoding` (pgvector `Vector(128)` column) → linked to `Person` records via `media_persons` junction table.

**Search/Filter** — `GallerySearchProxyModel` (in `gallery_item_model.py`) wraps the gallery model as a Qt proxy model, enabling keyword filtering and relevance-based sorting without reloading from DB.

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
- Left panel: event list (`QScrollArea` of `EventCardWidget` items)
- Center: gallery grid (`QListView` + `GalleryItemModel`)
- Right panel: IPTC metadata form + face detection controls
- Bottom: `SingleViewWidget` for full-size image with `FaceOverlayWidget` overlay
- Tab widget: Events tab (main view) + Settings tab
