"""Explicit local application configuration; no research directories are reused."""
from dataclasses import dataclass
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    storage_dir: Path = ROOT / 'storage'
    max_upload_bytes: int = 32 * 1024 * 1024
    max_pages: int = 200
    max_image_pixels: int = 40_000_000
    allowed_origins: tuple[str, ...] = ('http://localhost:3000', 'http://127.0.0.1:3000')

    @classmethod
    def from_env(cls):
        size = int(os.getenv('SMARTARCHIVE_MAX_UPLOAD_MB', '32'))
        if not 1 <= size <= 128:
            raise ValueError('SMARTARCHIVE_MAX_UPLOAD_MB must be between 1 and 128')
        origins = tuple(value.strip() for value in os.getenv(
            'SMARTARCHIVE_CORS_ORIGINS', 'http://localhost:3000,http://127.0.0.1:3000').split(',') if value.strip())
        if not origins or '*' in origins:
            raise ValueError('Use explicit CORS origins')
        return cls(storage_dir=Path(os.getenv('SMARTARCHIVE_STORAGE_DIR', str(ROOT / 'storage'))).resolve(),
                   max_upload_bytes=size * 1024 * 1024, allowed_origins=origins)
