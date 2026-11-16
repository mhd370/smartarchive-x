r"""Search ablation, confidence-aware fusion and cross-encoder re-ranking on an evaluated synthetic corpus.

  .\.venv\Scripts\python.exe tools/search_experiments.py data\synthetic\corpus_v1 --work results\synthetic_eval\corpus_v1_layout
  .\.venv\Scripts\python.exe tools/search_experiments.py data\synthetic\corpus_v2 --work results\synthetic_eval\corpus_v2_layout ^
      --alpha 0.5 --rerank-mode fuse

It reuses the archive that tools/evaluate_synthetic.py built for the corpus (its OCR text, no new OCR) and runs
the same document-level ranked search as the API (PageTexts.search_ranked) under each configuration:
- ablation: every non-empty subset of the three lexical rankings (exact, BM25 stems, character trigrams);
- confidence-aware fusion (ranked.py) with alpha 0.25, 0.5, 1 on the development set, or the --alpha chosen there;
- cross-encoder re-ranking of the top 20 (rerank.py), `fuse` and `replace`, when the model is present
  (tools/fetch_reranker_model.py), or only the --rerank-mode chosen on the development set.
Recall@10, MRR@10 and nDCG@10 per query kind. Results: search_experiments.json and .md in the work folder.
Choose settings on corpus_v1 only; corpus_v2 is the held-out test set.
"""
import argparse
from itertools import combinations
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'tools'))
KINDS = ('all', 'subject', 'reference_number', 'paraphrase')


def run(texts, queries, back) -> dict:
    from evaluate_synthetic import mean, retrieval
    scored = []
    for query in queries:
        result = texts.search_ranked(query['query'], 10, 0)
        ranking = [back.get(item['document']['id']) for item in result['items']]
        scored.append({'kind': query['kind'], **retrieval(ranking, set(query['relevant']))})
    block = {}
    for kind in KINDS:
        items = [s for s in scored if (s['kind'] != 'paraphrase' if kind == 'all' else s['kind'] == kind)]
        if items:
            block[kind] = {'queries': len(items), 'recall@10': mean(s['recall'] for s in items),
                           'mrr@10': mean(s['mrr'] for s in items), 'ndcg@10': mean(s['ndcg'] for s in items)}
    return block


def choose(dev: dict) -> tuple[float | None, str | None]:
    """Best confidence weight and re-ranking mode on the development set, by nDCG@10 over the original queries."""
    def ndcg(row):
        return row['scores']['all']['ndcg@10']
    alphas = [r for r in dev['runs'] if r['name'].startswith('confidence alpha=') and '+' not in r['name']]
    modes = [r for r in dev['runs'] if r['name'].startswith('cross-encoder ')]
    alpha = float(max(alphas, key=ndcg)['name'].split('=')[1]) if alphas else None
    mode = max(modes, key=ndcg)['name'].split()[1] if modes else None
    return alpha, mode


def markdown(report: dict) -> str:
    lines = [f"# Search experiments ({report['corpus']}, seed {report['seed']})", '',
             'Synthetic data. Recall@10 / MRR@10 per query kind; `all` = original subject and reference-number queries.',
             '', '| Configuration | All | Subject | Reference number | Paraphrase | s/query |', '|---|---|---|---|---|---|']
    for row in report['runs']:
        cells = []
        for kind in KINDS:
            b = row['scores'].get(kind)
            cells.append(f"{b['recall@10'] * 100:.1f}% / {b['mrr@10'] * 100:.1f}%" if b else '—')
        lines.append(f"| {row['name']} | {' | '.join(cells)} | {row['seconds_per_query']:.3f} |")
    return '\n'.join(lines) + '\n'


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('corpus', type=Path)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--alpha', type=float, help='only this confidence weight (chosen on the development set)')
    parser.add_argument('--rerank-mode', choices=('fuse', 'replace'), help='only this re-ranking mode')
    parser.add_argument('--reranker', type=Path, default=ROOT / 'models' / 'reranker' / 'mmarco-mMiniLMv2-L12')
    parser.add_argument('--skip-ablation', action='store_true')
    parser.add_argument('--tag', default='', help='suffix for the result files, e.g. _ce')
    parser.add_argument('--choose-from', type=Path,
                        help="the development set's search_experiments.json: use its best alpha and re-ranking mode")
    args = parser.parse_args(argv)
    if args.choose_from:
        args.alpha, args.rerank_mode = choose(json.loads(args.choose_from.read_text(encoding='utf-8')))
        print(f'chosen on the development set: alpha={args.alpha}, re-ranking mode={args.rerank_mode}')
    from smartarchive.persistence.database import Database
    from smartarchive.search import ranked, rerank
    from smartarchive.search.pages import PageTexts
    corpus, work = args.corpus.resolve(), args.work.resolve()
    manifest = json.loads((corpus / 'manifest.json').read_text(encoding='utf-8'))
    ids = json.loads((work / 'state.json').read_text(encoding='utf-8'))['ids']
    back = {value: key for key, value in ids.items()}
    queries = json.loads((corpus / 'queries.json').read_text(encoding='utf-8'))
    if (corpus / 'queries_paraphrase.json').is_file():
        queries += json.loads((corpus / 'queries_paraphrase.json').read_text(encoding='utf-8'))
    db = Database(work / 'storage' / 'archive.sqlite3')
    db.initialize()
    texts = PageTexts(db)
    texts.ensure_indexed()
    configs = []
    if not args.skip_ablation:
        for size in (1, 2, 3):
            for subset in combinations(('exact', 'words', 'grams'), size):
                configs.append(('+'.join(subset), {'components': subset}))
    else:
        configs.append(('exact+words+grams', {'components': ('exact', 'words', 'grams')}))
    for alpha in ([args.alpha] if args.alpha is not None else [0.25, 0.5, 1.0]):
        configs.append((f'confidence alpha={alpha:g}', {'confidence_alpha': alpha}))
    model = rerank.load(args.reranker) if args.reranker else None
    if model:
        for mode in ([args.rerank_mode] if args.rerank_mode else ['fuse', 'replace']):
            configs.append((f'cross-encoder {mode} (top {rerank.DEPTH})', {'reranker': model, 'mode': mode}))
            if args.alpha:
                configs.append((f'confidence alpha={args.alpha:g} + cross-encoder {mode}',
                                {'reranker': model, 'mode': mode, 'confidence_alpha': args.alpha}))
    else:
        print(f'no re-ranker at {args.reranker}; re-ranking skipped')
    runs = []
    for name, options in configs:
        texts.components = options.get('components', ranked.COMPONENTS)
        texts.confidence_alpha = options.get('confidence_alpha', 0.0)
        texts.reranker = options.get('reranker')
        if texts.reranker:
            texts.reranker.mode = options['mode']
        started = time.time()
        scores = run(texts, queries, back)
        seconds = (time.time() - started) / max(1, len(queries))
        runs.append({'name': name, 'scores': scores, 'seconds_per_query': round(seconds, 4)})
        print(f"{name}: all R@10 {scores['all']['recall@10']:.3f} MRR {scores['all']['mrr@10']:.3f}"
              + (f" | paraphrase R@10 {scores['paraphrase']['recall@10']:.3f}" if 'paraphrase' in scores else '')
              + f' ({seconds:.3f} s/query)', flush=True)
    report = {'corpus': corpus.name, 'seed': manifest.get('seed'), 'synthetic': True, 'queries': len(queries),
              'reranker': json.loads((args.reranker / 'SOURCE.json').read_text(encoding='utf-8'))
              if model and (args.reranker / 'SOURCE.json').is_file() else None, 'runs': runs}
    (work / f'search_experiments{args.tag}.json').write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    (work / f'search_experiments{args.tag}.md').write_text(markdown(report), encoding='utf-8')
    print(markdown(report))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
