from pathlib import Path
import subprocess
import sys


def test_vercel_package_entrypoint_imports_from_repository_root():
    repository_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "-c", "from backend.app.main import app; assert app is not None"],
        cwd=repository_root,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
