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


DEFAULT_CONFIDENCE_ALPHA = 0.0  # set from tools/search_experiments.py on the development set (ADR 0014)
# set from tools/ocr_paths_experiment.py on the development set (ADR 0016)
# Test set: CER 32.1% (standard alone) -> 27.8% at about 3.4x the OCR time; SMARTARCHIVE_OCR_PATHS=standard
# restores the single fast path.
DEFAULT_OCR_PATHS = ('standard', 'binarized', 'upscaled')
DEFAULT_OCR_PATH_RULE = 'confident-chars'
DEFAULT_OCR_PATH_GATE = 1.0


@dataclass(frozen=True)
class Settings:
    storage_dir: Path = ROOT / 'storage'
    backup_dir: Path | None = None  # default: <storage>/backups; copy backups to another disk as well
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
    # Folder of .traineddata files used instead of Tesseract's own (tools/fetch_ocr_models.py fills
    # models/tessdata with pinned, hash-checked models, including script/Arabic for Arabic-Indic digits).
    tessdata_dir: Path | None = None
    ocr_auto: bool = True
    ocr_worker: bool = True
    # PDF pages are rendered at this resolution for OCR. 200 beat 300 on the synthetic development corpus
    # (born-digital CER 12.9% vs 17.1% with script/Arabic+ara; ADR 0008).
    ocr_dpi: int = 200
    ocr_page_timeout_seconds: int = 120
    # Ruled tables cell by cell and two-column reading order (processing/layout.py, ADR 0012).
    layout_analysis: bool = True
    # OCR paths read per page and the automatic choice between them (processing/paths.py, ADR 0016).
    # One path = the single-path pipeline. Defaults are chosen on the development set.
    ocr_paths: tuple[str, ...] = DEFAULT_OCR_PATHS
    ocr_path_rule: str = DEFAULT_OCR_PATH_RULE
    ocr_path_gate: float = DEFAULT_OCR_PATH_GATE
    # Dense retrieval (search/semantic.py, ADR 0013): off unless SMARTARCHIVE_SEMANTIC=1 and the model is present;
    # it helped paraphrased queries on the development set but not on the held-out test set.
    semantic_model_dir: Path | None = None
    # Cross-encoder re-ranking of the top 20 (search/rerank.py, ADR 0014): off unless SMARTARCHIVE_RERANK=1.
    reranker_model_dir: Path | None = None
    rerank_mode: str = 'fuse'
    # Confidence-aware fusion (search/ranked.py, ADR 0014): 0 turns it off.
    confidence_alpha: float = 0.0
    # First-run admin setup on a public server: when set, creating the first admin needs this code (deploy guide).
    setup_token: str | None = None
    # Rankings fused by ranked search (ADR 0014): exact, words (BM25 stems), grams (trigrams), dense.
    search_components: tuple[str, ...] = ('exact', 'words', 'dense')
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
        backups = os.getenv('SMARTARCHIVE_BACKUP_DIR')
        return cls(storage_dir=Path(os.getenv('SMARTARCHIVE_STORAGE_DIR', str(ROOT / 'storage'))).resolve(),
                   backup_dir=Path(backups).resolve() if backups else None,
                   max_upload_bytes=size * 1024 * 1024, allowed_origins=origins,
                   secure_cookies=flag('SMARTARCHIVE_SECURE_COOKIES', 'false'),
                   tesseract_cmd=os.getenv('SMARTARCHIVE_TESSERACT_CMD') or None,
                   ocr_languages=os.getenv('SMARTARCHIVE_OCR_LANGUAGES', 'ara+eng'),
                   ocr_dpi=int(os.getenv('SMARTARCHIVE_OCR_DPI', '200')),
                   tessdata_dir=Path(os.environ['SMARTARCHIVE_TESSDATA_DIR']).resolve()
                   if os.getenv('SMARTARCHIVE_TESSDATA_DIR') else None,
                   ocr_auto=flag('SMARTARCHIVE_OCR_AUTO', 'true'),
                   layout_analysis=flag('SMARTARCHIVE_LAYOUT', 'true'),
                   ocr_paths=tuple(c.strip() for c in os.getenv(
                       'SMARTARCHIVE_OCR_PATHS', ','.join(DEFAULT_OCR_PATHS)).split(',') if c.strip()),
                   ocr_path_rule=os.getenv('SMARTARCHIVE_OCR_PATH_RULE', DEFAULT_OCR_PATH_RULE),
                   ocr_path_gate=float(os.getenv('SMARTARCHIVE_OCR_PATH_GATE', str(DEFAULT_OCR_PATH_GATE))),
                   semantic_model_dir=(Path(os.environ['SMARTARCHIVE_SEMANTIC_MODEL']).resolve()
                                       if os.getenv('SMARTARCHIVE_SEMANTIC_MODEL') else ROOT / 'models' / 'semantic'
                                       / 'multilingual-e5-small') if flag('SMARTARCHIVE_SEMANTIC', 'false') else None,
                   reranker_model_dir=(Path(os.environ['SMARTARCHIVE_RERANK_MODEL']).resolve()
                                       if os.getenv('SMARTARCHIVE_RERANK_MODEL') else ROOT / 'models' / 'reranker'
                                       / 'mmarco-mMiniLMv2-L12') if flag('SMARTARCHIVE_RERANK', 'false') else None,
                   rerank_mode=os.getenv('SMARTARCHIVE_RERANK_MODE', 'fuse'),
                   setup_token=os.getenv('SMARTARCHIVE_SETUP_TOKEN') or None,
                   search_components=tuple(c.strip() for c in os.getenv(
                       'SMARTARCHIVE_SEARCH_COMPONENTS', 'exact,words,dense').split(',') if c.strip()),
                   confidence_alpha=float(os.getenv('SMARTARCHIVE_CONFIDENCE_ALPHA', str(DEFAULT_CONFIDENCE_ALPHA))),
                   ocr_worker=flag('SMARTARCHIVE_OCR_WORKER', 'true'))
