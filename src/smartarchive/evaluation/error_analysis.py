"""Describe existing approved-GT benchmark results without recalculating metrics."""
import csv
from pathlib import Path

from .tracking import timestamp, write_json
from .validation import ValidationError, decode_text, digest, parse_json, read_bytes


def summarize(report_path: Path, *, associations_path: Path | None = None) -> dict:
    raw_report = read_bytes(report_path)
    report = parse_json(raw_report, str(report_path))
    if report.get('schema_version') != 'benchmark-run-v1':
        raise ValidationError('Error analysis requires a benchmark-run-v1 report')
    results, evaluated = [], 0
    for row in report['pages']:
        metadata = row.get('input_metadata', {})
        engine = metadata.get('engine', {'name': 'unknown', 'version': None})
        diagnostics = None
        if row['status'] == 'EVALUATED':
            if row.get('ground_truth', {}).get('metadata', {}).get('review', {}).get('status') != 'approved':
                raise ValidationError('An evaluated page must carry approved reference provenance')
            artifact = report_path.parent / f"entry_{row['entry_index']:05d}"
            ref_bytes, pred_bytes = read_bytes(artifact / 'reference.txt'), read_bytes(artifact / 'prediction.txt')
            if (digest(ref_bytes) != row['ground_truth']['text_sha256']
                    or digest(pred_bytes) != row['prediction_sha256']):
                raise ValidationError('Benchmark text snapshot hash mismatch')
            reference = decode_text(ref_bytes, 'reference snapshot', allow_empty=True)
            prediction = decode_text(pred_bytes, 'prediction snapshot', allow_empty=True)
            diagnostics = {
                'reference_crlf_count': reference.count('\r\n'),
                'prediction_crlf_count': prediction.count('\r\n'),
                'reference_lf_count': reference.count('\n'),
                'prediction_lf_count': prediction.count('\n'),
                'note': 'Line-ending counts describe artifacts, not omitted-text proof. '
                        'Strict versus normalized gaps combine several policy effects.',
            }
            evaluated += 1
        for policy in report['policies']:
            measurement = row['evaluations'].get(policy) if row['status'] == 'EVALUATED' else None
            results.append({
                'document_id': row.get('document_id'), 'page': row.get('page'),
                'variant': row.get('variant'), 'engine': engine, 'policy': policy,
                'status': row['status'], 'reason': row.get('reason'),
                'cer': measurement['cer'] if measurement else None,
                'wer': measurement['wer'] if measurement else None, 'diagnostics': diagnostics,
            })
    invalid = report.get('status') == 'FAILED_VALIDATION'
    status = ('VALIDATION_ERRORS' if invalid else 'NOT_EVALUATED' if not evaluated
              else 'EVALUATED' if evaluated == len(report['pages']) else 'PARTIALLY_EVALUATED')
    result = {
        'schema_version': 'ocr-error-analysis-v1', 'created_at': timestamp(), 'status': status,
        'run_id': report['run_id'], 'report_sha256': digest(raw_report),
        'associations_sha256': digest(read_bytes(associations_path)) if associations_path else None,
        'page_variant_count': len(report['pages']), 'evaluated_page_variants': evaluated,
        'results': results, 'summaries': report['summaries'],
        'interpretation': (
            'No approved reference was evaluated. Accuracy and error patterns cannot be established.'
            if not evaluated else
            'Operation counts and rates are copied from the versioned benchmark. '
            'Substitutions, deletions and insertions are reference-to-prediction edits. '
            'They do not establish the cause of an OCR error or an improvement claim.'),
        'limitations': [
            'All seven historical variants use Tesseract; engine version is unknown.',
            'Raw historical confidence and output length are not accuracy evidence.',
            'Review reading order against the source; edit counts alone cannot diagnose layout errors.',
            'Compare strict and normalized policies separately; inspect reference coverage.',
            'One pilot page cannot establish institutional generalization. No winner is selected.',
        ],
    }
    return result


def write_analysis(report_path: Path, *, associations_path: Path | None = None) -> dict:
    result = summarize(report_path, associations_path=associations_path)
    folder = report_path.parent
    # Each artifact is exclusive; rerunning against the same run cannot overwrite.
    write_json(folder / 'error_analysis.json', result)
    fields = ['document_id', 'page', 'variant', 'engine', 'engine_version', 'policy', 'status', 'reason']
    for metric in ('cer', 'wer'):
        fields.extend(f'{metric}_{key}' for key in ('rate', 'substitutions', 'deletions', 'insertions',
                                                   'reference_units', 'rate_status'))
    with (folder / 'accuracy_by_page.csv').open('x', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in result['results']:
            flat = {key: row.get(key) for key in fields}
            flat.update(engine=row['engine']['name'], engine_version=row['engine']['version'])
            for metric in ('cer', 'wer'):
                flat.update({f'{metric}_{key}': row[metric].get(key) if row[metric] else None
                             for key in ('rate', 'substitutions', 'deletions', 'insertions',
                                         'reference_units', 'rate_status')})
            writer.writerow(flat)
    lines = ['# OCR error-analysis summary', '', f"Status: **{result['status']}**.", '',
             result['interpretation'], '',
             '| Variant | Policy | Status | CER | WER | Character S/D/I |',
             '| --- | --- | --- | --- | --- | --- |']
    safe = lambda value: str(value).replace('|', '\\|').replace('\n', ' ')
    for row in result['results']:
        rate = lambda key: f"{row[key]['rate']:.6f}" if row[key] and row[key]['rate'] is not None else 'Unavailable'
        edits = '/'.join(str(row['cer'][key]) for key in ('substitutions', 'deletions', 'insertions')) if row['cer'] else 'Unavailable'
        lines.append(f"| {safe(row['variant'])} | {row['policy']} | {row['status']} | {rate('cer')} | {rate('wer')} | {edits} |")
    lines.extend(['', '## Interpretation limits', ''])
    lines.extend('- ' + note for note in result['limitations'])
    with (folder / 'error_analysis.md').open('x', encoding='utf-8', newline='\n') as stream:
        stream.write('\n'.join(lines) + '\n')
    return result
