"""Bounded, validated, write-once original storage. Never uses client paths."""
import hashlib
from io import BytesIO
import os
from pathlib import Path
import re
import uuid
import warnings
from PIL.Image import DecompressionBombError

from smartarchive.config import Settings
from smartarchive.domain.documents import ArchiveError

EXTENSIONS = {'.pdf': 'application/pdf', '.png': 'image/png', '.jpg': 'image/jpeg',
              '.jpeg': 'image/jpeg', '.webp': 'image/webp', '.tif': 'image/tiff', '.tiff': 'image/tiff'}


def safe_filename(value: str | None) -> str:
    name = (value or '').replace('\\', '/').rsplit('/', 1)[-1].strip()
    if not name or len(name) > 200 or any(ord(char) < 32 or ord(char) == 127 for char in name):
        raise ArchiveError('invalid_filename', 'اسم الملف غير صالح.')
    if Path(name).suffix.lower() not in EXTENSIONS:
        raise ArchiveError('unsupported_type', 'الأنواع المدعومة: PDF وPNG وJPEG وWebP وTIFF.', 415)
    return name


class OriginalStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.root = settings.storage_dir.resolve() / 'originals'

    def initialize(self):
        self.root.mkdir(parents=True, exist_ok=True)

    def _validate(self, path: Path, expected_mime: str) -> int:
        try:
            if expected_mime == 'application/pdf':
                import pymupdf
                if not path.read_bytes().startswith(b'%PDF-'):
                    raise ValueError('invalid PDF signature')
                with pymupdf.open(path) as document:
                    if not document.is_pdf or document.needs_pass or not 1 <= document.page_count <= self.settings.max_pages:
                        raise ValueError('encrypted, empty or oversized PDF')
                    # Parse page structure without OCR or altering source bytes.
                    for page in document:
                        if page.rect.is_empty or page.rect.is_infinite:
                            raise ValueError('invalid page geometry')
                    return document.page_count
            from PIL import Image, ImageSequence
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(path) as image:
                    if Image.MIME.get(image.format) != expected_mime:
                        raise ValueError('image type mismatch')
                    total, count = 0, 0
                    for frame in ImageSequence.Iterator(image):
                        count += 1
                        pixels = frame.width * frame.height
                        total += pixels
                        if (pixels > self.settings.max_image_pixels or total > self.settings.max_image_pixels * 2
                                or count > self.settings.max_pages):
                            raise ValueError('image resource limit')
                        frame.load()
                    return count
        except (OSError, ValueError, RuntimeError, Warning, DecompressionBombError) as exc:
            raise ArchiveError('invalid_document', 'تعذر التحقق من الملف. تأكد أنه غير تالف أو مشفر وأن حجمه وأبعاده ضمن الحدود.', 422) from exc

    def save(self, stream, filename: str, declared_mime: str | None) -> dict:
        suffix = Path(filename).suffix.lower()
        mime = EXTENSIONS[suffix]
        if declared_mime and declared_mime not in (mime, 'application/octet-stream'):
            raise ArchiveError('mime_mismatch', 'نوع الملف المرسل لا يطابق امتداده.', 415)
        identifier = str(uuid.uuid4())
        folder = self.root / identifier
        folder.mkdir(exist_ok=False)
        stage, final = folder / 'upload.part', folder / ('original' + suffix)
        hasher, size = hashlib.sha256(), 0
        try:
            with stage.open('xb') as target:
                while chunk := stream.read(64 * 1024):
                    size += len(chunk)
                    if size > self.settings.max_upload_bytes:
                        raise ArchiveError('too_large', 'حجم الملف يتجاوز الحد المسموح.', 413)
                    hasher.update(chunk)
                    target.write(chunk)
                target.flush()
                os.fsync(target.fileno())
            if size == 0:
                raise ArchiveError('empty_document', 'الملف فارغ.', 422)
            page_count = self._validate(stage, mime)
            # Hard-link publication fails if a target exists; no overwrite path.
            os.link(stage, final)
            stage.unlink()
            return {'id': identifier, 'filename': filename, 'size_bytes': size, 'mime_type': mime,
                    'sha256': hasher.hexdigest(), 'storage_key': f'{identifier}/{final.name}',
                    'page_count': page_count}
        except Exception:
            # Only remove this request's unpublished, owned temporary file.
            if stage.exists():
                stage.unlink()
            if not final.exists():
                folder.rmdir()
            raise

    def verified_path(self, record: dict) -> Path:
        key = record['storage_key']
        if not re.fullmatch(r'[0-9a-f-]{36}/original\.(pdf|png|jpe?g|webp|tiff?)', key):
            raise ArchiveError('integrity_error', 'تعذر التحقق من مسار الأصل المحفوظ.', 409)
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root.resolve()) or not path.is_file():
            raise ArchiveError('integrity_error', 'الأصل المحفوظ غير متاح.', 409)
        with path.open('rb') as source:
            actual = hashlib.file_digest(source, 'sha256').hexdigest()
        if actual != record['sha256'] or path.stat().st_size != record['size_bytes']:
            raise ArchiveError('integrity_error', 'فشل فحص سلامة الملف الأصلي.', 409)
        return path

    def preview(self, record: dict, page: int = 1) -> bytes:
        from PIL import Image
        if not 1 <= page <= record['page_count']:
            raise ArchiveError('page_not_found', 'الصفحة المطلوبة غير موجودة.', 404)
        path = self.verified_path(record)
        if record['mime_type'] == 'application/pdf':
            import pymupdf
            try:
                with pymupdf.open(path) as document:
                    source = document.load_page(page - 1)
                    scale = min(1800 / source.rect.width, 2400 / source.rect.height, 2)
                    pixels = source.get_pixmap(matrix=pymupdf.Matrix(scale, scale),
                                               alpha=False, colorspace=pymupdf.csRGB)
                    return pixels.tobytes('png')
            except (OSError, ValueError, RuntimeError) as exc:
                raise ArchiveError('preview_error', 'تعذر تجهيز المعاينة. يمكنك تنزيل الأصل.', 422) from exc
        with Image.open(path) as image:
            image.seek(page - 1)
            preview = image.convert('RGB')
            preview.thumbnail((1800, 2400))
            buffer = BytesIO()
            preview.save(buffer, format='PNG')
            return buffer.getvalue()
