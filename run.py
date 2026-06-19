"""
run.py — Acknowledge uygulama başlatıcısı

Kullanım:
    python run.py          # Uygulamayı başlatır (Docker'ı da otomatik başlatır)
    python run.py --stop   # Docker container'larını durdurur ve çıkar
"""
import subprocess
import sys
import time
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

COMPOSE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docker-compose.yml")
CONTAINER_NAME = "tirnavali_acknowledge_db"

# How long to wait (seconds) for Docker Desktop to become responsive after launch
DOCKER_STARTUP_TIMEOUT = 60


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def is_docker_running() -> bool:
    """Return True if the Docker daemon is reachable."""
    result = _run(["docker", "info"])
    return result.returncode == 0


def start_docker_desktop() -> bool:
    """Launch Docker Desktop if it is not already running. Returns True when ready."""
    if is_docker_running():
        return True

    print("Docker Desktop başlatılıyor, lütfen bekleyin…")
    
    if sys.platform == "win32":
        docker_desktop_exe = r"C:\Program Files\Docker\Docker\Docker Desktop.exe"
        if os.path.exists(docker_desktop_exe):
            subprocess.Popen([docker_desktop_exe], shell=False)
        else:
            print(
                f"HATA: Docker Desktop bulunamadı: {docker_desktop_exe}\n"
                "Lütfen Docker Desktop'ı yükleyin veya manuel olarak başlatın."
            )
            return False
    elif sys.platform == "darwin":
        if os.path.exists("/Applications/Docker.app"):
            try:
                subprocess.Popen(["open", "-g", "-a", "Docker"])
            except Exception as e:
                print(f"Docker başlatılırken hata oluştu: {e}")
                return False
        else:
            print(
                "HATA: Docker Desktop bulunamadı (/Applications/Docker.app).\n"
                "Lütfen Docker Desktop veya Docker daemon'ı manuel olarak başlatın."
            )
            return False
    else:
        print("Docker çalışmıyor. Lütfen sisteminizde Docker daemon'ını başlatın.")
        return False

    deadline = time.time() + DOCKER_STARTUP_TIMEOUT
    while time.time() < deadline:
        time.sleep(3)
        if is_docker_running():
            print("Docker Desktop hazır.")
            return True
        print("  Bekleniyor…")

    print("HATA: Docker Desktop başlatılamadı. Lütfen manuel olarak başlatın.")
    return False


def is_container_running() -> bool:
    result = _run(["docker", "inspect", "-f", "{{.State.Running}}", CONTAINER_NAME])
    return result.returncode == 0 and result.stdout.strip() == "true"


def start_containers() -> bool:
    """Bring up docker-compose services. Returns True on success."""
    if is_container_running():
        return True

    print("Veritabanı container'ı başlatılıyor…")
    result = _run(["docker", "compose", "-f", COMPOSE_FILE, "up", "-d"])
    if result.returncode != 0:
        # Fallback for older Docker installations that use "docker-compose"
        result = _run(["docker-compose", "-f", COMPOSE_FILE, "up", "-d"])

    if result.returncode != 0:
        print(f"HATA: Container başlatılamadı:\n{result.stderr}")
        return False

    # Wait for PostgreSQL to be ready (up to 30 s)
    deadline = time.time() + 30
    db_user = os.getenv("DB_USER", "tirnavali")
    while time.time() < deadline:
        health = _run(
            ["docker", "exec", CONTAINER_NAME, "pg_isready", "-U", db_user],
        )
        if health.returncode == 0:
            print("Veritabanı hazır.")
            return True
        time.sleep(2)

    print("Uyarı: Veritabanı henüz hazır olmayabilir, uygulama yine de başlatılıyor.")
    return True


def stop_containers():
    """Stop and remove docker-compose containers."""
    print("Container'lar durduruluyor…")
    result = _run(["docker", "compose", "-f", COMPOSE_FILE, "down"])
    if result.returncode != 0:
        result = _run(["docker-compose", "-f", COMPOSE_FILE, "down"])
    if result.returncode == 0:
        print("Container'lar durduruldu.")
    else:
        print(f"HATA: Container durdurulamadı:\n{result.stderr}")


def main():
    # Enforce execution inside the local virtual environment (.venv) to prevent 
    # dependency conflicts and tokenizer corruption between Anaconda and the venv.
    current_dir = os.path.dirname(os.path.abspath(__file__))
    is_pythonw = sys.executable.lower().endswith("pythonw.exe")
    if sys.platform == "win32":
        exe_name = "pythonw.exe" if is_pythonw else "python.exe"
        venv_python = os.path.join(current_dir, ".venv", "Scripts", exe_name)
    else:
        venv_python = os.path.join(current_dir, ".venv", "bin", "python")

    if os.path.exists(venv_python) and os.path.abspath(sys.executable) != os.path.abspath(venv_python):
        # Sanity-check that the target venv has the core dependencies before re-execing.
        # A broken/empty .venv would otherwise cause a cryptic ModuleNotFoundError on startup.
        probe = subprocess.run(
            [venv_python, "-c", "import sqlalchemy, PySide6"],
            capture_output=True,
        )
        if probe.returncode != 0:
            print(
                "HATA: .venv sanal ortamı eksik bağımlılıklar içeriyor ve kullanılamaz.\n"
                "Lütfen şu komutla sanal ortamı yeniden kurun:\n"
                "  pip install -r requirements.txt   (veya requirements-cuda.txt / requirements-mps.txt)\n"
                "Uygulama mevcut Python ortamıyla devam ediyor.",
                flush=True,
            )
        else:
            print(f"Sanal ortam (.venv) algılandı. Uygulama sanal ortam python'ı ile yeniden başlatılıyor: {venv_python}", flush=True)
            sys.stdout.flush()
            sys.stderr.flush()
            os.execv(venv_python, [venv_python] + sys.argv)

    if "--stop" in sys.argv:
        if not is_docker_running():
            print("Docker zaten çalışmıyor.")
            return
        stop_containers()
        return

    # --- Start flow ---
    if not start_docker_desktop():
        sys.exit(1)

    if not start_containers():
        sys.exit(1)

    print("Uygulama başlatılıyor…")
    # Replace this process with app.py so it runs in the same terminal window.
    # Using sys.executable ensures the same venv Python is used.
    os.execv(sys.executable, [sys.executable, "app.py"])


if __name__ == "__main__":
    main()
