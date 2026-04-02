# Tirnavali Acknowledge

A desktop application designed for managing, searching, and recognizing faces in large media archives. Built with Python, PySide6 (Qt), SQLAlchemy, and ONNX Runtime for high-performance facial feature extraction.

## Features

- **Media Management**: Import and organize photos into events and vaults.
- **Embedded Metadata**: Read and write IPTC metadata directly into image files (Headline, Caption, Keywords, Credit, Source, etc.).
- **Face Detection & Recognition**:
  - Uses **InsightFace (buffalo_l)** for face detection and 512-dimensional ArcFace embedding extraction.
  - Applies a **Variance of the Laplacian** blur filter before saving — completely unrecognizable faces
    (score < 20.0) are skipped to keep the pgvector index clean. Slightly blurry faces still pass through.
  - Stores vectors in PostgreSQL using the `pgvector` extension for rapid similarity search and auto-tagging.
- **Database synchronization**: Seamlessly syncs manual file metadata blocks with the robust PostgreSQL backend.

---

## 🚀 Prerequisites

To run this application, you will need the following installed on your system:

1. **Python 3.10+**: Make sure Python is in your system's PATH.
2. **Docker Desktop**: Required to run the PostgreSQL database with the `pgvector` extension.
3. **Git** (optional, for cloning the repository).

---

## 🛠️ Installation & Setup

Installation instructions vary slightly depending on your operating system. The process involves starting the database, setting up a Python virtual environment, and installing dependencies.

### Step 1: Start the Database (All Platforms)

The application requires a PostgreSQL database with Vector support. A `docker-compose.yml` file is provided to set this up instantly.

1. Open a terminal in the project root folder.
2. Run the following command:
   ```bash
   docker-compose up -d
   ```
3. Copy the `.env.example` file to `.env` (or create a new `.env` file) and configure your database endpoint (it should match the docker-compose settings by default).

### Step 2: Python Environment Setup

#### Windows 11

1. **Create a virtual environment:**
   ```powershell
   python -m venv venv
   ```
2. **Activate the virtual environment:**
   ```powershell
   .\venv\Scripts\activate
   ```
3. **Install dependencies:**
   ```powershell
   pip install -r requirements.txt
   ```
   *(Note: The face analysis module uses MediaPipe and ONNX Runtime, avoiding the complex C++ build tools typically required by dlib or InsightFace on Windows).*

#### Linux (Ubuntu/Debian)

1. **Install system dependencies:** (PySide6 may require some system-level Qt libraries)
   ```bash
   sudo apt-get update
   sudo apt-get install python3-venv libgl1-mesa-glx
   ```
2. **Create a virtual environment:**
   ```bash
   python3 -m venv venv
   ```
3. **Activate the virtual environment:**
   ```bash
   source venv/bin/activate
   ```
4. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

---

## 📦 Requirements (`requirements.txt`)

The project relies on a lightweight, highly compatible stack:

- `PySide6>=6.5.0`: The official Python module for the Qt framework (UI).
- `sqlalchemy>=2.0.0`: Python SQL toolkit and Object Relational Mapper.
- `python-dotenv>=1.0.0`: Reads key-value pairs from a `.env` file into environment variables.
- `iptcinfo3>=2.0.0`: Python port for reading and writing IPTC image metadata.
- `mediapipe`: Google's robust framework for media processing (used for face detection).
- `onnxruntime`: High-performance inference engine for ML models (used to run ArcFace).

---

## 🏃 Running the Application

Once your database is running and your virtual environment is activated, you can start the application:

```bash
python app.py
```

*Note: On the first run, the system will automatically download a ~30MB ArcFace ONNX model into a `models/` directory for face recognition tasks.*

---

## 🏗️ Project Structure

The project strictly follows a **Service-Repository Pattern** to separate UI logic, business logic, and database access.

```text
acknowledge/
├── .env                    # Environment variables (Database URL, vault paths)
├── docker-compose.yml      # Docker configs for PostgreSQL (pgvector) & pgAdmin
├── requirements.txt        # Python package dependencies
├── app.py                  # Main application entry point & MainWindow UI
├── add_event_window.py     # UI for creating new media events
├── event_card_widget.py    # UI widget for displaying events in the dashboard
├── gallery_item_model.py   # Qt Model for efficiently loading large image galleries
├── single_view_widget.py   # UI for full-screen image view & face detection overlay
├── init_db.py              # Database initialization & migration script
├── src/                    # Core Application Logic
│   ├── database.py         # SQLAlchemy engine & session management
│   ├── models.py           # SQLAlchemy ORM models (Event, Media, Face, Person)
│   ├── domain/             # Domain entities and business objects
│   ├── repositories/       # Database access layer (CRUD operations)
│   │   ├── base_repository.py
│   │   ├── event_repository.py
│   │   ├── face_repository.py
│   │   ├── media_repository.py
│   │   └── person_repository.py
│   └── services/           # Business logic and coordination layer
│       ├── application_service.py   # Service registry/locator
│       ├── base_service.py
│       ├── event_service.py
│       ├── face_analysis_service.py # Core ML logic (MediaPipe + ONNX)
│       ├── face_service.py
│       ├── media_service.py
│       └── person_service.py
└── media_vault/            # Default directory where physical media files are stored
```

---

## 📝 Coding Best Practices & Architecture

When contributing to this project, adhere to the following architectural guidelines:

### 1. The Service-Repository Pattern
- **UI Layer (`app.py`, `*_widget.py`)**: Must **never** execute raw SQL or use SQLAlchemy sessions directly. UI components should only communicate with the `src/services/` layer via the `ApplicationService`.
- **Service Layer (`src/services/`)**: Contains all business logic, orchestrates cross-repository actions, and handles error logging.
- **Repository Layer (`src/repositories/`)**: The only place where database queries (SQLAlchemy `session` or `text()`) should occur. Responsible for basic CRUD operations.

### 2. Threading for Heavy Operations
UI freezes are unacceptable. Heavy operations like parsing EXIF/IPTC data on hundreds of images or running ML inference (Face Detection) must be delegated to background threads.
- Example: `FaceDetectionWorker` (a `QThread`) in `single_view_widget.py` runs the `FaceAnalysisService` asynchronously so the UI remains responsive.

### 3. Graceful Error Handling
Network dependencies (Database via Docker) and IO operations (reading corrupted images) will fail. Always wrap these in `try/except` blocks at the Service level. The Service layer should catch specific errors and inform the UI layer gracefully.

### 4. Dependency Management
Always ensure that new features work on both Windows and Linux without requiring strict C++ compilation if possible. This is why we rely on `onnxruntime` + `mediapipe` rather than `dlib` or `insightface`.

---

## Troubleshooting

- **`module 'mediapipe' has no attribute 'solutions'`**: Ensure you are not running an extremely old or broken installation of MediaPipe. Rely on the specific imports used in `face_analysis_service.py` to bypass Windows-specific loading quirks.
- **`InvalidTextRepresentation` (psycopg2)**: This occurs when PostgreSQL expects a UUID but receives a standard string (like a file path). Ensure you are using `get_by_file_path()` instead of `get_by_id()` in repositories when dealing with paths.
- **Database Connection Failed**: Ensure Docker Desktop is running and the `docker-compose up -d` command executed successfully. Verify that ports `5432` are not blocked by local firewalls or other postgres instances.
