r"""Train the learned classifier (tfidf-svm-v1).

  # on the archive's confirmed categories (same as the admin button):
  .\.venv\Scripts\python.exe tools/train_classifier.py --archive
  # on a labelled synthetic corpus, from the OCR text of its evaluation run (for held-out testing):
  .\.venv\Scripts\python.exe tools/train_classifier.py --corpus data\synthetic\corpus_v1 ^
      --work results\synthetic_eval\corpus_v1_script-Arabic_ara_200dpi --out results\models\corpus_v1

The corpus mode trains on OCR text, not on the clean ground-truth text, so the model learns what OCR
produces. Pass the output folder to tools/evaluate_synthetic.py --classifier-model and evaluate on the
other corpus (corpus_v2), which the model has never seen.
"""
import argparse
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))


def corpus_training_set(corpus: Path, work: Path) -> tuple[list[str], list[str], list[str]]:
    manifest = {e['doc_id']: e for e in json.loads((corpus / 'manifest.json').read_text(encoding='utf-8'))['documents']}
    ids = json.loads((work / 'state.json').read_text(encoding='utf-8'))['ids']
    db = sqlite3.connect(work / 'storage' / 'archive.sqlite3')
    texts, names, labels = [], [], []
    for doc_id, document_id in ids.items():
        text = '\n'.join(row[0] for row in db.execute(
            'SELECT text FROM page_texts WHERE document_id=? ORDER BY page_no', (document_id,)))
        if text.strip() and doc_id in manifest:
            texts.append(text)
            names.append(Path(manifest[doc_id]['file']).name)
            labels.append(manifest[doc_id]['type'])
    db.close()
    return texts, names, labels


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--archive', action='store_true', help="train on the archive's confirmed categories")
    parser.add_argument('--corpus', type=Path)
    parser.add_argument('--work', type=Path, help='evaluation work folder of that corpus (its OCR text)')
    parser.add_argument('--out', type=Path, help='model folder to write (corpus mode)')
    parser.add_argument('--method', default='tfidf-svm-v1', choices=('tfidf-svm-v1', 'tfidf-char-lr-v1'),
                        help='corpus mode: which learned baseline to train')
    args = parser.parse_args(argv)
    from smartarchive.classification import learned
    if args.archive:
        from smartarchive.classification.service import Classifications
        from smartarchive.config import Settings
        from smartarchive.persistence.database import Database
        settings = Settings.from_env()
        db = Database(settings.storage_dir / 'archive.sqlite3')
        db.initialize()
        card = Classifications(db, models_dir=settings.storage_dir / 'models').train('cli')
    elif args.corpus and args.work and args.out:
        if 'corpus_v2' in str(args.corpus):
            parser.error('corpus_v2 is the held-out test set; train on corpus_v1')
        texts, names, labels = corpus_training_set(args.corpus.resolve(), args.work.resolve())
        model = learned.train(texts, names, labels, f'synthetic corpus {args.corpus.name} ({len(labels)} documents, OCR text)',
                              method=args.method)
        learned.save(model, args.out.resolve())
        card = model['card']
    else:
        parser.error('use --archive, or --corpus with --work and --out')
    print(json.dumps(card, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
