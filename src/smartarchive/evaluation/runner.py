"""CLI benchmark for existing OCR text; never imports an OCR implementation."""
import argparse
import csv
import json
import math
from pathlib import Path
import time

from .metrics import POLICIES, evaluate
from .tracking import create_run, environment, timestamp, write_json
from .validation import (ValidationError, decode_text, digest, fields, nonempty,
                         page_number, parse_json, read_bytes, resolve_file, sha256)

ENTRY_FIELDS = {
    'document_id', 'source_path', 'source_sha256', 'page', 'split', 'variant',
    'prediction_path', 'ground_truth_path', 'engine', 'language', 'configuration',
    'preprocessing', 'ocr_runtime_seconds',
}
GT_FIELDS = {
    'schema_version', 'document_id', 'source_sha256', 'page', 'text_path',
    'text_sha256', 'is_blank', 'reading_order', 'transcriber', 'review',
}


def validate_entry(entry: dict, base: Path) -> dict:
    fields(entry, ENTRY_FIELDS, 'entry')
    for key in ('document_id', 'variant', 'language'):
        nonempty(entry[key], key)
    page_number(entry['page'])
    sha256(entry['source_sha256'], 'source_sha256')
    if entry['split'] not in ('pilot', 'dev', 'test'):
        raise ValidationError('split must be pilot, dev or test')
    fields(entry['engine'], {'name', 'version'}, 'engine')
    nonempty(entry['engine']['name'], 'engine.name')
    if entry['engine']['version'] is not None:
        nonempty(entry['engine']['version'], 'engine.version')
    for key in ('configuration', 'preprocessing'):
        if not isinstance(entry[key], dict):
            raise ValidationError(f'{key} must be an object (explicit settings or unknown notes)')
    runtime = entry['ocr_runtime_seconds']
    if runtime is not None and (type(runtime) not in (int, float)
                                or not math.isfinite(runtime) or runtime < 0):
        raise ValidationError('ocr_runtime_seconds must be null or finite nonnegative number')
    source = resolve_file(base, entry['source_path'], 'source_path')
    source_data = read_bytes(source)
    if digest(source_data) != entry['source_sha256']:
        raise ValidationError('source_sha256 mismatch')
    prediction = resolve_file(base, entry['prediction_path'], 'prediction_path')
    prediction_data = read_bytes(prediction)
    prediction_text = decode_text(prediction_data, str(prediction))
    return {
        'source_path': str(source), 'source_sha256': digest(source_data),
        'prediction_path': str(prediction), 'prediction_sha256': digest(prediction_data),
        'prediction_data': prediction_data, 'prediction_text': prediction_text,
    }


def load_ground_truth(path: Path, entry: dict) -> dict:
    data = read_bytes(path)
    gt = parse_json(data, str(path))
    fields(gt, GT_FIELDS, 'ground truth')
    if gt['schema_version'] != 'gt-v1':
        raise ValidationError('ground truth schema_version must be gt-v1')
    page_number(gt['page'])
    for key in ('document_id', 'source_sha256', 'page'):
        if gt[key] != entry[key]:
            raise ValidationError(f'ground truth {key} does not match entry')
    sha256(gt['text_sha256'], 'text_sha256')
    if type(gt['is_blank']) is not bool:
        raise ValidationError('is_blank must be boolean')
    order = gt['reading_order']
    if (not isinstance(order, list) or not order
            or any(not isinstance(item, str) or not item.strip() for item in order)
            or len(set(order)) != len(order)):
        raise ValidationError('reading_order must list unique ordered nonempty region descriptions')
    nonempty(gt['transcriber'], 'transcriber')
    fields(gt['review'], {'status', 'reviewer', 'reviewed_at'}, 'review')
    review = gt['review']
    if review['status'] not in ('draft', 'reviewed', 'approved'):
        raise ValidationError('review.status must be draft, reviewed or approved')
    if review['status'] in ('reviewed', 'approved'):
        nonempty(review['reviewer'], 'reviewer')
        if review['reviewer'] == gt['transcriber']:
            raise ValidationError('reviewer must differ from transcriber for reviewed/approved GT')
        from datetime import datetime
        try:
            reviewed = datetime.fromisoformat(nonempty(review['reviewed_at'], 'reviewed_at'))
            if reviewed.tzinfo is None:
                raise ValueError('timezone required')
        except ValueError as exc:
            raise ValidationError('reviewed_at must be an ISO-8601 timestamp with timezone') from exc
    elif review['reviewer'] is not None or review['reviewed_at'] is not None:
        raise ValidationError('draft review fields must be null')
    text_path = resolve_file(path.parent, gt['text_path'], 'text_path')
    text_data = read_bytes(text_path)
    text = decode_text(text_data, str(text_path), allow_empty=gt['is_blank'])
    if gt['is_blank'] and text:
        raise ValidationError('is_blank requires an exactly empty transcript (zero bytes)')
    if digest(text_data) != gt['text_sha256']:
        raise ValidationError('transcript hash mismatch: changed content requires re-review')
    return {'metadata': gt, 'metadata_data': data, 'metadata_path': str(path),
            'metadata_sha256': digest(data), 'text_path': str(text_path),
            'text_sha256': digest(text_data), 'text_data': text_data, 'text': text}


def aggregate(rows: list[dict], policy: str) -> dict:
    evaluated = [row['evaluations'][policy] for row in rows if row['status'] == 'EVALUATED']
    result = {'policy': policy, 'total_pages': len(rows), 'evaluated_pages': len(evaluated),
              'not_evaluated_pages': sum(r['status'] == 'NOT_EVALUATED' for r in rows),
              'invalid_pages': sum(r['status'] == 'VALIDATION_ERROR' for r in rows)}
    for metric in ('cer', 'wer'):
        counts = {key: sum(item[metric][key] for item in evaluated) for key in (
            'substitutions', 'deletions', 'insertions', 'distance', 'reference_units', 'hypothesis_units')}
        rates = [item[metric]['rate'] for item in evaluated if item[metric]['rate'] is not None]
        result[metric] = {
            **counts,
            'micro_rate': counts['distance'] / counts['reference_units'] if counts['reference_units'] else None,
            'macro_rate': sum(rates) / len(rates) if rates else None,
            'defined_page_rates': len(rates),
        }
    return result


def build_summaries(rows: list[dict], policies: list[str]) -> list[dict]:
    groups = {}
    for row in rows:
        if not all(isinstance(row.get(key), str) for key in ('document_id', 'variant')):
            continue
        for scope, identifier in [('document', row['document_id']), ('corpus', None)]:
            groups.setdefault((scope, identifier, row['variant']), []).append(row)
    return [
        {'scope': scope, 'document_id': document, 'variant': variant, **aggregate(group, policy)}
        for (scope, document, variant), group in groups.items() for policy in policies
    ]


def write_csv(path: Path, rows: list[dict], *, summary: bool) -> None:
    keys = (['scope', 'document_id', 'variant', 'policy', 'total_pages', 'evaluated_pages',
             'not_evaluated_pages', 'invalid_pages'] if summary else
            ['entry_index', 'document_id', 'page', 'variant', 'status', 'reason', 'policy',
             'source_sha256', 'prediction_sha256'])
    for metric in ('cer', 'wer'):
        keys.extend(f'{metric}_{key}' for key in (
            ('substitutions', 'deletions', 'insertions', 'distance', 'reference_units',
             'hypothesis_units', 'micro_rate', 'macro_rate', 'defined_page_rates') if summary else
            ('substitutions', 'deletions', 'insertions', 'distance', 'reference_units',
             'hypothesis_units', 'rate', 'rate_status')))
    with path.open('x', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=keys)
        writer.writeheader()
        for row in rows:
            flattened = {key: row.get(key) for key in keys}
            for metric in ('cer', 'wer'):
                flattened.update({f'{metric}_{key}': value for key, value in row.get(metric, {}).items()})
            writer.writerow(flattened)


def run(manifest: Path, output_root: Path, policies: list[str]) -> tuple[Path, dict]:
    if not policies or any(policy not in POLICIES for policy in policies) or len(set(policies)) != len(policies):
        raise ValidationError('Select unique supported policies')
    start = time.perf_counter()
    folder = create_run(output_root)
    info = {'schema_version': 'benchmark-run-v1', 'run_id': folder.name, 'started_at': timestamp(),
            'policies': policies, 'manifest_path': str(manifest.resolve()), 'environment': environment()}
    write_json(folder / 'started.json', {**info, 'status': 'RUNNING'})
    rows, errors = [], []
    try:
        manifest_data = read_bytes(manifest)
        (folder / 'input_manifest.json').write_bytes(manifest_data)
        info['manifest_sha256'] = digest(manifest_data)
        specification = parse_json(manifest_data, str(manifest))
        fields(specification, {'schema_version', 'entries'}, 'manifest')
        if specification['schema_version'] != 'benchmark-v1':
            raise ValidationError('manifest schema_version must be benchmark-v1')
        entries = specification['entries']
        if not isinstance(entries, list) or not entries:
            raise ValidationError('entries must be a nonempty list')
        seen, documents, variants, source_splits = set(), {}, {}, {}
        for index, entry in enumerate(entries, 1):
            row = {'entry_index': index, 'status': 'VALIDATION_ERROR', 'evaluations': {}}
            rows.append(row)
            if isinstance(entry, dict):
                row.update({key: entry.get(key) for key in ('document_id', 'page', 'variant')})
            try:
                files = validate_entry(entry, manifest.resolve().parent)
                identity = (entry['document_id'], entry['page'], entry['variant'])
                if identity in seen:
                    raise ValidationError('duplicate document/page/variant entry')
                seen.add(identity)
                document_contract = (entry['source_sha256'], entry['split'])
                if documents.setdefault(entry['document_id'], document_contract) != document_contract:
                    raise ValidationError('document ID has conflicting source hash or split')
                if source_splits.setdefault(entry['source_sha256'], entry['split']) != entry['split']:
                    raise ValidationError('identical source bytes assigned to different dataset splits')
                variant_contract = json.dumps({key: entry[key] for key in (
                    'engine', 'language', 'configuration', 'preprocessing')}, sort_keys=True)
                if variants.setdefault(entry['variant'], variant_contract) != variant_contract:
                    raise ValidationError('variant has conflicting engine/configuration metadata')
                artifact = folder / f'entry_{index:05d}'
                artifact.mkdir()
                (artifact / 'prediction.txt').write_bytes(files['prediction_data'])
                row.update({key: value for key, value in files.items()
                            if key not in ('prediction_data', 'prediction_text')})
                row['prediction_snapshot'] = f'{artifact.name}/prediction.txt'
                row['input_metadata'] = entry
                row['metadata_warnings'] = [key for key, value in (
                    ('unknown historical engine version', entry['engine']['version']),
                    ('unknown historical OCR runtime', entry['ocr_runtime_seconds'])) if value is None]
                gt_value = entry['ground_truth_path']
                if gt_value is None:
                    row.update(status='NOT_EVALUATED', reason='MISSING_GROUND_TRUTH')
                    continue
                gt_path = resolve_file(manifest.resolve().parent, gt_value, 'ground_truth_path')
                gt = load_ground_truth(gt_path, entry)
                (artifact / 'reference.txt').write_bytes(gt['text_data'])
                (artifact / 'ground_truth.json').write_bytes(gt['metadata_data'])
                row['ground_truth'] = {key: value for key, value in gt.items()
                                       if key not in ('metadata_data', 'text_data', 'text')}
                if gt['metadata']['review']['status'] != 'approved':
                    row.update(status='NOT_EVALUATED', reason='GROUND_TRUTH_NOT_APPROVED')
                    continue
                if gt['text_path'] == files['prediction_path']:
                    raise ValidationError('reference and prediction must be separate files')
                row['evaluations'] = {policy: evaluate(reference=gt['text'],
                                                     hypothesis=files['prediction_text'], policy=policy)
                                      for policy in policies}
                row.update(status='EVALUATED', reason=None)
            except (ValidationError, OSError) as exc:
                row.update(status='VALIDATION_ERROR', reason=str(exc))
    except (ValidationError, OSError) as exc:
        errors.append(str(exc))
    summaries = build_summaries(rows, policies)
    invalid = bool(errors) or any(row['status'] == 'VALIDATION_ERROR' for row in rows)
    result = {**info, 'finished_at': timestamp(), 'evaluation_runtime_seconds': time.perf_counter() - start,
              'status': 'FAILED_VALIDATION' if invalid else 'COMPLETED', 'errors': errors,
              'pages': rows, 'summaries': summaries,
              'note': 'Saved-text evaluation only. No engine invoked, no winner selected. '
                      'Source/page assignments and historical engine metadata are supplied assertions.'}
    write_json(folder / 'report.json', result)
    page_csv_rows = []
    for row in rows:
        for policy in policies:
            page_csv_rows.append({**row, 'policy': policy, **row['evaluations'].get(policy, {})})
    write_csv(folder / 'pages.csv', page_csv_rows, summary=False)
    write_csv(folder / 'summaries.csv', summaries, summary=True)
    return folder, result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--output-root', type=Path, default=Path('results/benchmark'))
    parser.add_argument('--policies', nargs='+', choices=POLICIES, default=list(POLICIES))
    args = parser.parse_args(argv)
    try:
        folder, report = run(args.manifest, args.output_root, args.policies)
    except (OSError, ValidationError) as exc:
        parser.exit(2, f'Benchmark error: {exc}\n')
    print(f"{report['status']}: {folder}")
    for row in report['pages']:
        print(f"entry {row['entry_index']}: {row['status']} {row.get('reason') or ''}")
    for error in report['errors']:
        print(f'Validation error: {error}')
    return 2 if report['status'] == 'FAILED_VALIDATION' else 0


if __name__ == '__main__':
    raise SystemExit(main())
