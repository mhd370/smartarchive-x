"""Explicit historical adapters with source pixel and ordering checks; no OCR."""
from pathlib import Path
import re

from .ground_truth import current
from .pilot import find_page, pages, pixel_hash
from .tracking import create_run, timestamp, write_json
from .validation import ValidationError, decode_text, digest, nonempty, parse_json, read_bytes


def ordered_regions(report: dict, layout: str, width: int, height: int) -> list[dict]:
    regions = report.get('regions')
    if not isinstance(regions, list) or not regions:
        raise ValidationError('Missing region ordering labels')
    result = []
    for index, region in enumerate(regions, 1):
        order = region.get('reading_order' if layout == 'v1' else 'order')
        if layout == 'v3':
            order = index  # v03 report list order is its documented contract.
        if type(order) is not int or order != index:
            raise ValidationError('Duplicate, missing or unordered region IDs')
        box = region.get('bbox_xyxy' if layout == 'v1' else 'bbox')
        if (not isinstance(box, list) or len(box) != 4 or any(type(v) is not int for v in box)
                or not (0 <= box[0] < box[2] <= width and 0 <= box[1] < box[3] <= height)):
            raise ValidationError('Invalid region bounding box')
        result.append({**region, 'box': box})
    if layout != 'v1':
        types = [region.get('type') for region in result]
        if types not in (['single_page'], ['right_column', 'left_column'],
                         ['shared_header', 'right_column', 'left_column']):
            raise ValidationError('Unsupported/ambiguous RTL region ordering')
    if len(result) >= 2:
        right, left = result[-2:]
        if right['box'][0] + right['box'][2] <= left['box'][0] + left['box'][2]:
            raise ValidationError('Expected right column before left column')
    return result


def line_reconstruction(folder: Path, report: dict, regions: list[dict]) -> str:
    blocks = parse_json(b'{"blocks":' + read_bytes(folder / 'line_blocks.json') + b'}',
                        'line_blocks.json')['blocks']
    if not isinstance(blocks, list) or len(blocks) != report.get('line_count'):
        raise ValidationError('Incomplete line labels/count')
    per_region, offset = [], 0
    for region_order, region in enumerate(regions, 1):
        count = region.get('lines_detected')
        if type(count) is not int or count < 0:
            raise ValidationError('Missing region line count')
        texts, previous_y = [], -1
        for line_order in range(1, count + 1):
            if offset >= len(blocks) or not isinstance(blocks[offset], dict):
                raise ValidationError('Incomplete line records')
            block = blocks[offset]
            offset += 1
            if (type(block.get('region_order')) is not int or block['region_order'] != region_order
                    or type(block.get('line_order')) is not int or block['line_order'] != line_order
                    or block.get('region_type') != region['type']):
                raise ValidationError('Duplicate, missing or unordered line IDs')
            box, bounds = block.get('bbox'), region['box']
            if (not isinstance(box, list) or len(box) != 4 or any(type(v) is not int for v in box)
                    or not (bounds[0] <= box[0] < box[2] <= bounds[2]
                            and bounds[1] <= box[1] < box[3] <= bounds[3]) or box[1] < previous_y):
                raise ValidationError('Invalid or non-top-to-bottom line geometry')
            previous_y = box[1]
            if not isinstance(block.get('text'), str):
                raise ValidationError('Missing line text label (empty recognized text is allowed)')
            if block['text'].strip():
                texts.append(block['text'].strip())
        per_region.append('\n'.join(texts))
    if offset != len(blocks):
        raise ValidationError('Unassigned line records')
    return '\n\n'.join(value for value in per_region if value).strip() + '\n'


def import_binding(root: Path, dataset: dict, binding: dict) -> tuple[bytes, dict, dict]:
    if not isinstance(binding, dict) or set(binding) != {'document_id', 'page', 'layout', 'kind', 'directory'}:
        raise ValidationError('Binding requires document_id/page/layout/kind/directory; no filename inference')
    document, page = find_page(dataset, binding['document_id'], binding['page'])
    if digest(read_bytes(root / document['source_path'])) != document['source_sha256']:
        raise ValidationError('Bound source bytes changed; rebuild/review inventory')
    layout, kind = binding['layout'], binding['kind']
    if layout not in ('v1', 'v2', 'v3') or kind not in ('whole', 'regions', 'lines'):
        raise ValidationError('Unsupported historical adapter')
    if kind == 'lines' and layout != 'v3':
        raise ValidationError('Line adapter requires v3 metadata')
    folder = (root / nonempty(binding['directory'], 'directory')).resolve()
    match = re.fullmatch(r'page_(\d+)', folder.name)
    if not match or int(match.group(1)) != page['page']:
        raise ValidationError('Directory page number conflicts with explicit binding')
    originals = list(pages(folder / 'original.png'))
    if len(originals) != 1 or pixel_hash(originals[0][1]) != page['pixel_sha256']:
        raise ValidationError('Historical original pixels do not match bound source page')
    pixel_matches = [(doc['document_id'], item['page']) for doc in dataset['documents']
                     for item in doc['pages'] if item['pixel_sha256'] == page['pixel_sha256']]
    if len(pixel_matches) != 1:
        raise ValidationError('Ambiguous identical page images in dataset; curate unique association first')
    report_path = folder / ('report.json' if layout == 'v3' else 'layout_report.json')
    report = parse_json(read_bytes(report_path), str(report_path))
    if type(report.get('page')) is not int or report['page'] != page['page']:
        raise ValidationError('Historical report belongs to wrong page')
    if layout != 'v1' and report.get('image_size' if layout == 'v3' else 'page_size') != [page['width'], page['height']]:
        raise ValidationError('Historical page dimensions conflict')
    regions = ordered_regions(report, layout, page['width'], page['height'])
    name = ('baseline_psm3.txt' if kind == 'whole' else 'line_psm.txt' if kind == 'lines'
            else 'region_psm.txt' if layout == 'v3' else 'rtl_reading_order.txt')
    prediction_path = folder / name
    prediction = read_bytes(prediction_path)
    text = decode_text(prediction, str(prediction_path))
    # Legacy Windows write_text translated LF to CRLF after in-memory counts.
    # This view is ONLY for producer-consistency checks; raw bytes are exported.
    producer_text = text.replace('\r\n', '\n')
    evidence = [folder / 'original.png', report_path, prediction_path]
    if kind == 'regions' and layout in ('v1', 'v2'):
        parts = []
        for index, _ in enumerate(regions, 1):
            part_path = folder / f'region_{index:02d}_ocr.txt'
            parts.append(decode_text(read_bytes(part_path), str(part_path), allow_empty=True)
                         .replace('\r\n', '\n').strip())
            evidence.append(part_path)
        reconstructed = '\n\n'.join(value for value in parts if value) + '\n'
        if producer_text != reconstructed:
            raise ValidationError('Region aggregate differs from ordered raw region predictions')
    if kind == 'lines':
        if producer_text != line_reconstruction(folder, report, regions):
            raise ValidationError('Line aggregate differs from ordered line labels')
        evidence.append(folder / 'line_blocks.json')
    if layout == 'v3':
        variant_key = {'whole': 'baseline_psm3', 'regions': 'region_psm', 'lines': 'line_psm'}[kind]
        recorded = report.get('variants', {}).get(variant_key, {})
        if recorded.get('characters') != len(producer_text):
            raise ValidationError('Historical variant length conflicts with report')
        runtime = recorded.get('seconds')
    else:
        runtime = report.get('baseline', {}).get('seconds') if kind == 'whole' else None
    settings = {'oem': 1, 'psm': 3 if kind == 'whole' else 7 if kind == 'lines' else 6,
                'historical_layout': layout,
                'header_psm': 7 if kind == 'regions' and layout != 'v1' else None,
                'producer_defaults_only': True, 'original_engine_version': 'not recorded',
                'settings_provenance': 'preserved producer defaults; full historical CLI invocation not recorded'}
    provenance = {
        'binding': binding, 'source_sha256': document['source_sha256'],
        'source_pixel_sha256': page['pixel_sha256'], 'adapter': 'historical-v1',
        'ordering_validation': 'metadata order/geometry and aggregate where component text exists',
        'producer_consistency_view': 'CRLF -> LF only for metadata/aggregate checks; exported bytes unchanged',
        'limitation': 'v3 region component text is not saved separately; geometric list order only',
        'artifacts': [{'path': str(path), 'sha256': digest(read_bytes(path))} for path in evidence],
    }
    metadata = {'engine': {'name': 'tesseract', 'version': None}, 'language': 'ara',
                'configuration': settings,
                'preprocessing': {'kind': kind, 'layout': layout,
                                  'details': 'original page' if kind == 'whole' else
                                  'geometric crops; v3 small line crops may be upscaled'},
                'ocr_runtime_seconds': runtime}
    return prediction, metadata, provenance


def prepare(root: Path, dataset: dict, bindings: dict, output_root: Path, store: Path) -> Path:
    if bindings.get('schema_version') != 'historical-bindings-v1' or not isinstance(bindings.get('bindings'), list):
        raise ValidationError('Expected historical-bindings-v1')
    if not bindings['bindings']:
        raise ValidationError('No historical bindings')
    # Validate every association and review history before writing an import bundle.
    adapted, identities = [], set()
    for binding in bindings['bindings']:
        prediction, metadata, provenance = import_binding(root, dataset, binding)
        identity = (binding['document_id'], binding['page'], binding['layout'], binding['kind'])
        if identity in identities:
            raise ValidationError('Duplicate historical binding ID')
        identities.add(identity)
        document, page = find_page(dataset, binding['document_id'], binding['page'])
        gt = current(store, document, page['page'])
        adapted.append((binding, prediction, metadata, provenance, document, gt))
    bundle = create_run(output_root)
    entries, associations = [], []
    for index, (binding, prediction, metadata, provenance, document, gt) in enumerate(adapted, 1):
        filename = f'prediction_{index:05d}.txt'
        (bundle / filename).write_bytes(prediction)
        state = 'PENDING' if gt is None else gt['status'].upper()
        associations.append({**provenance, 'prediction_snapshot': filename,
                             'prediction_sha256': digest(prediction), 'gt_status': state,
                             'transcription_version': gt['version'] if gt else None,
                             'gt_history_state_sha256': gt['state_sha256'] if gt else None})
        entries.append({
            'document_id': binding['document_id'], 'page': binding['page'],
            'source_path': str((root / document['source_path']).resolve()),
            'source_sha256': document['source_sha256'], 'split': document['split'],
            'variant': f"historical-{binding['layout']}-{binding['kind']}",
            'prediction_path': filename,
            'ground_truth_path': str(gt['sidecar']) if gt else None, **metadata,
        })
    write_json(bundle / 'benchmark.json', {'schema_version': 'benchmark-v1', 'entries': entries})
    write_json(bundle / 'associations.json', {
        'schema_version': 'historical-import-v1', 'created_at': timestamp(),
        'dataset': dataset, 'bindings': bindings, 'associations': associations,
        'note': 'No OCR rerun and no ranking. Explicit bindings validated against source pixels.',
    })
    return bundle
