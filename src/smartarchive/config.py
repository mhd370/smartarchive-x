"""Explicit local application configuration; no research directories are reused."""
from dataclasses import dataclass
import os
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]
WINDOWS_TESSERACT = Path(r'C:\Program Files\Tesseract-OCR\tesseract.exe')


def find_tesseract(explicit: str | None = None) -> str | None:
    """Locate the Tesseract executable without guessing beyond known install paths."""
    for candidate in (explicit, shutil.which('tesseract'), str(WINDOWS_TESSERACT)):
        if candidate and Path(candidate).is_file():
            return str(Path(candidate))
    return None


@dataclass(frozen=True)
class Settings:
    storage_dir: Path = ROOT / 'storage'
    max_upload_bytes: int = 32 * 1024 * 1024
    max_pages: int = 200
    max_image_pixels: int = 40_000_000
    allowed_origins: tuple[str, ...] = ('http://localhost:3000', 'http://127.0.0.1:3000')
    # Sessions: HttpOnly cookie, server-side token hash, fixed lifetime.
    session_hours: int = 12
    secure_cookies: bool = False
    # OCR processing. Thresholds are initial engineering values, tuned later on validation data.
    tesseract_cmd: str | None = None
    ocr_languages: str = 'ara+eng'
    ocr_auto: bool = True
    ocr_worker: bool = True
    ocr_dpi: int = 300
    ocr_page_timeout_seconds: int = 120
    review_confidence_threshold: float = 0.60
    quality_weights: tuple[float, float, float, float, float] = (0.2, 0.2, 0.2, 0.2, 0.2)

    @property
    def tesseract(self) -> str | None:
        return find_tesseract(self.tesseract_cmd)

    @classmethod
    def from_env(cls):
        size = int(os.getenv('SMARTARCHIVE_MAX_UPLOAD_MB', '32'))
        if not 1 <= size <= 128:
            raise ValueError('SMARTARCHIVE_MAX_UPLOAD_MB must be between 1 and 128')
        origins = tuple(value.strip() for value in os.getenv(
            'SMARTARCHIVE_CORS_ORIGINS', 'http://localhost:3000,http://127.0.0.1:3000').split(',') if value.strip())
        if not origins or '*' in origins:
            raise ValueError('Use explicit CORS origins')
        flag = lambda name, default: os.getenv(name, default).strip().lower() in ('1', 'true', 'yes')
        return cls(storage_dir=Path(os.getenv('SMARTARCHIVE_STORAGE_DIR', str(ROOT / 'storage'))).resolve(),
                   max_upload_bytes=size * 1024 * 1024, allowed_origins=origins,
                   secure_cookies=flag('SMARTARCHIVE_SECURE_COOKIES', 'false'),
                   tesseract_cmd=os.getenv('SMARTARCHIVE_TESSERACT_CMD') or None,
                   ocr_languages=os.getenv('SMARTARCHIVE_OCR_LANGUAGES', 'ara+eng'),
                   ocr_auto=flag('SMARTARCHIVE_OCR_AUTO', 'true'),
                   ocr_worker=flag('SMARTARCHIVE_OCR_WORKER', 'true'))
