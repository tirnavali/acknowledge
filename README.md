# Tirnavali Acknowledge

A desktop application for managing large media archives with IPTC metadata editing, face detection & recognition, and AI-powered Turkish captioning. Built with Python, PySide6 (Qt), SQLAlchemy, and PostgreSQL (pgvector).

## Features

- **Media Management**: Import and organize photos into events and vaults.
- **Embedded Metadata**: Read and write IPTC metadata directly into image files (Headline, Caption, Keywords, Credit, Source, etc.).
- **Face Detection & Recognition**:
  - Uses **InsightFace (buffalo_l)** for face detection and 512-dimensional ArcFace embedding extraction.
  - Applies a **Variance of the Laplacian** blur filter — faces with a score below 5.0 are skipped to keep the pgvector index clean.
  - Stores vectors in PostgreSQL using the `pgvector` extension for rapid similarity search and auto-tagging.
- **AI Captioning**: Uses **Qwen2.5-VL-3B-Instruct** to automatically generate Turkish captions and keyword tags for images. Runs in the background; results are saved to the database. Auto-detects CUDA → MPS → CPU.
- **Database synchronization**: Seamlessly syncs manual file metadata with the PostgreSQL backend.

---

## Prerequisites

1. **Python 3.10+** in your system PATH.
2. **Docker Desktop** — required to run the PostgreSQL database.

---

## Installation & Setup

### Step 1: Python Environment

Follow the option for your hardware:

#### Windows (NVIDIA GPU)
```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements-cuda.txt
```

#### macOS (Apple Silicon)
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-mps.txt
```

#### CPU-only / Generic
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Step 2: Environment Configuration

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

#### Available Environment Variables:

* **Database Configuration**:
  * `DB_USER`: PostgreSQL username (default: `tirnavali`).
  * `DB_PASSWORD`: PostgreSQL password (default: `tbmm1920`).
  * `DB_HOST`: Database host address (default: `localhost`).
  * `DB_PORT`: Database port mapping on host (default: `5432`).
  * `DB_NAME`: PostgreSQL database name (default: `tirnavali_acknowledge_db`).

* **Media Storage**:
  * `MEDIA_VAULT_PATH`: Local directory path to store imported media files (default: `media_vault`).

* **Hugging Face Hub (Optional)**:
  * `HF_TOKEN`: Hugging Face User Access Token (read). Used to authenticate with the Hugging Face Hub during model downloads and to avoid rate-limiting issues.

* **Ollama Caption Backend (Optional)**:
  * `OLLAMA_URL`: Connection URL for your Ollama instance (default: `http://localhost:11434`).
  * `OLLAMA_CAPTION_MODEL`: Model tag to use for vision captioning (default: `gemma4:latest`).

* **Sentry Monitoring (Optional)**:
  * `SENTRY_DSN`: Sentry Data Source Name (DSN) URL for tracking runtime exceptions and application performance. Leave empty to disable Sentry integration.

### Step 3 (optional): Download the AI captioning model

On corporate networks with MITM SSL proxies, pre-download the Qwen model before first launch:
```bash
python download_model.py   # downloads ~3 GB to ./models/Qwen2.5-VL-3B-Instruct
```
If skipped, the model is downloaded automatically from HuggingFace Hub on first use.

---

## Running the Application

Use `run.py` — it starts Docker Desktop and the database automatically if they are not already running:

```bash
python run.py
```

To stop the database containers when you are done:
```bash
python run.py --stop
```

> **Manual start** (advanced): If Docker Desktop is already running you can also start with `docker-compose up -d` and then `python app.py` directly.

---

## Hardware Acceleration

The application automatically selects the best available accelerator:

| Feature | Windows (NVIDIA) | macOS (M-Series) | Fallback |
| :--- | :--- | :--- | :--- |
| **Face Detection** | `CUDAExecutionProvider` | `CoreMLExecutionProvider` | `CPUExecutionProvider` |
| **AI Captioning** | `cuda` (bfloat16) | `mps` (bfloat16) | `cpu` (float32) |

---

## Troubleshooting

**SSL errors during `pip install`** (corporate MITM proxies):
```bash
# Windows/CUDA
pip install -r requirements-cuda.txt --trusted-host download.pytorch.org --trusted-host pypi.org --trusted-host files.pythonhosted.org

# macOS/MPS
pip install -r requirements-mps.txt --trusted-host pypi.org --trusted-host files.pythonhosted.org
```

**Docker Desktop does not start via `run.py`**: Verify that Docker Desktop is installed at `C:\Program Files\Docker\Docker\Docker Desktop.exe`. If it is in a different location, update the `DOCKER_DESKTOP_EXE` constant at the top of `run.py`.

**Database connection failed**: Ensure Docker Desktop is running, ports 5432 are not blocked by a firewall, and no other PostgreSQL instance is using the same port.

**AI captioning model not found**: Run `python download_model.py` once to download the model locally. Set `HF_TOKEN` in `.env` if the HuggingFace Hub requires authentication.

**Otomatik güncelleme çalışmıyor (Windows)**: `git` komutunun sistem PATH'inde bulunduğundan emin olun. Git kurulumu sırasında "Add Git to PATH" seçeneğinin işaretli olması gerekir.
