"""Deterministic source/page inventory. Decoding is lazy; no OCR is invoked."""
import hashlib
from importlib.metadata import version
from pathlib import Path

from .validation import ValidationError, digest, nonempty, page_number, parse_json, read_bytes

IMAGE_TYPES = {'.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp'}


def pixel_hash(image) -> str:
    rgb = image.convert('RGB')
    header = f'RGB:{rgb.width}:{rgb.height}:'.encode('ascii')
    return hashlib.sha256(header + rgb.tobytes()).hexdigest()


def pages(path: Path):
    """Yield every raster frame, or PDF page rendered at explicit 300 DPI."""
    if path.suffix.lower() == '.pdf':
        import pymupdf
        from PIL import Image
        with pymupdf.open(path) as document:
            for number, page in enumerate(document, 1):
                pix = page.get_pixmap(dpi=300, alpha=False, colorspace=pymupdf.csRGB)
                yield number, Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
    elif path.suffix.lower() in IMAGE_TYPES:
        from PIL import Image, ImageSequence
        with Image.open(path) as image:
            for number, frame in enumerate(ImageSequence.Iterator(image), 1):
                yield number, frame.convert('RGB').copy()
    else:
        raise ValidationError(f'Unsupported source format: {path}')


def inventory(root: Path, input_directory: Path) -> dict:
    root = root.resolve()
    documents = {}
    for path in sorted(input_directory.rglob('*')):
        if not path.is_file() or path.name.startswith('.'):
            continue
        if path.suffix.lower() not in IMAGE_TYPES | {'.pdf'}:
            raise ValidationError(f'Unsupported input requires explicit exclusion: {path}')
        source_hash = digest(read_bytes(path))
        relative = path.resolve().relative_to(root).as_posix()
        if source_hash in documents:
            documents[source_hash]['source_aliases'].append(relative)
            continue
        page_records = []
        for number, image in pages(path):
            page_records.append({'page': number, 'width': image.width, 'height': image.height,
                                 'pixel_sha256': pixel_hash(image), 'ground_truth_status': 'PENDING',
                                 'reading_order_status': 'PENDING_HUMAN_REVIEW'})
        if not page_records:
            raise ValidationError(f'Source contains no pages: {path}')
        documents[source_hash] = {
            'document_id': 'doc-' + source_hash, 'source_path': relative,
            'source_aliases': [], 'source_sha256': source_hash, 'bytes': path.stat().st_size,
            'split': 'pilot', 'authorization_status': 'PENDING_CONFIRMATION',
            'pages': page_records,
        }
    if not documents:
        raise ValidationError('No supported input documents')
    related = []
    # These are candidate byte/pixel copies, not new source documents or GT.
    for path in sorted((root / 'results').rglob('original*')):
        if not path.is_file() or path.suffix.lower() not in IMAGE_TYPES:
            continue
        matches = []
        for frame, image in pages(path):
            fingerprint = pixel_hash(image)
            matches.extend({'frame': frame, 'document_id': doc['document_id'], 'page': page['page']}
                           for doc in documents.values() for page in doc['pages']
                           if page['pixel_sha256'] == fingerprint)
        related.append({'path': path.relative_to(root).as_posix(),
                        'sha256': digest(read_bytes(path)), 'pixel_matches': matches})
    return {'schema_version': 'pilot-v1',
            'decoding_environment': {'Pillow': version('Pillow'),
                                     'PyMuPDF': version('PyMuPDF') if any(
                                         doc['source_path'].lower().endswith('.pdf')
                                         for doc in documents.values()) else None},
            'pixel_policy': 'RGB dimensions + decoded bytes; no EXIF rotation',
            'pdf_render_policy': 'PyMuPDF RGB 300 DPI, annotations default; no enhancement',
            'related_original_images': related,
            'documents': sorted(documents.values(), key=lambda item: item['document_id'])}


def load_dataset(path: Path, root: Path) -> dict:
    dataset = parse_json(read_bytes(path), str(path))
    if dataset.get('schema_version') != 'pilot-v1' or not isinstance(dataset.get('documents'), list):
        raise ValidationError('Expected pilot-v1 dataset with documents')
    seen = set()
    for document in dataset['documents']:
        if not isinstance(document, dict):
            raise ValidationError('Invalid document record')
        identifier = nonempty(document.get('document_id'), 'document_id')
        if identifier in seen:
            raise ValidationError('Duplicate document ID')
        seen.add(identifier)
        source = root / nonempty(document.get('source_path'), 'source_path')
        if digest(read_bytes(source)) != document.get('source_sha256'):
            raise ValidationError('Dataset source hash mismatch')
        records = document.get('pages')
        if not isinstance(records, list) or not records:
            raise ValidationError('Document must list pages')
        if any(not isinstance(record, dict) for record in records):
            raise ValidationError('Invalid page record')
        numbers = [page_number(record.get('page')) for record in records]
        if numbers != list(range(1, len(records) + 1)):
            raise ValidationError('Duplicate, missing or unordered page IDs')
        actual = [(n, image.width, image.height, pixel_hash(image)) for n, image in pages(source)]
        declared = [(r['page'], r.get('width'), r.get('height'), r.get('pixel_sha256')) for r in records]
        if actual != declared:
            raise ValidationError('Dataset page pixels/dimensions do not match source')
        if document.get('split') not in ('pilot', 'dev', 'test'):
            raise ValidationError('Invalid document split')
    if not seen:
        raise ValidationError('Empty dataset')
    return dataset


def find_page(dataset: dict, document_id: str, page: int) -> tuple[dict, dict]:
    page_number(page)
    matches = [(document, record) for document in dataset['documents']
               if document['document_id'] == document_id for record in document['pages']
               if record['page'] == page]
    if len(matches) != 1:
        raise ValidationError('Unknown or ambiguous document/page association')
    return matches[0]
