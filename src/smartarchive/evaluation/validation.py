"""Small explicit validators; no schema-validation dependency required."""
import hashlib
import json
from pathlib import Path
import re


class ValidationError(ValueError):
    """Invalid benchmark input, not a successful empty OCR result."""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise ValidationError(f'Cannot read {path}: {exc}') from exc


def decode_text(data: bytes, label: str, *, allow_empty: bool = False) -> str:
    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise ValidationError(f'{label}: invalid UTF-8') from exc
    if text.startswith('\ufeff'):
        raise ValidationError(f'{label}: UTF-8 BOM is not permitted; save as UTF-8 without BOM')
    if any(ord(char) < 32 and char not in '\r\n\t' for char in text):
        raise ValidationError(f'{label}: unsupported control character')
    if not allow_empty and not text.strip():
        raise ValidationError(f'{label}: empty or whitespace-only text')
    return text


def parse_json(data: bytes, label: str) -> dict:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValidationError(f'{label}: duplicate JSON key {key}')
            result[key] = value
        return result
    try:
        value = json.loads(decode_text(data, label), object_pairs_hook=pairs,
                           parse_constant=lambda value: (_ for _ in ()).throw(
                               ValidationError(f'{label}: invalid JSON constant {value}')))
    except ValidationError:
        raise
    except (ValueError, RecursionError) as exc:
        raise ValidationError(f'{label}: malformed JSON: {exc}') from exc
    if not isinstance(value, dict):
        raise ValidationError(f'{label}: expected JSON object')
    return value


def fields(value: dict, required: set, label: str) -> None:
    if not isinstance(value, dict):
        raise ValidationError(f'{label}: expected object')
    missing = required - value.keys()
    extra = value.keys() - required
    if missing or extra:
        raise ValidationError(f'{label}: missing fields {sorted(missing)}, unknown fields {sorted(extra)}')


def nonempty(value, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f'{label}: expected nonempty string')
    return value


def sha256(value, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
        raise ValidationError(f'{label}: expected lowercase SHA-256')
    return value


def page_number(value) -> int:
    if type(value) is not int or value < 1:
        raise ValidationError('page must be a positive integer (one-based)')
    return value


def resolve_file(base: Path, value, label: str) -> Path:
    return (base / nonempty(value, label)).resolve()
