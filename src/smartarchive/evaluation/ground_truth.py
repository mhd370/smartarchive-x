"""Append-only local transcription revisions and explicit human attestations.

Review metadata is an attestation, not authentication. No OCR is called here.
"""
from contextlib import contextmanager
from pathlib import Path
import unicodedata

from .pilot import find_page
from .runner import load_ground_truth
from .tracking import timestamp, write_json
from .validation import ValidationError, decode_text, digest, nonempty, parse_json, read_bytes


def page_directory(store: Path, document_id: str, page: int) -> Path:
    return store / digest(document_id.encode('utf-8')) / f'page_{page:03d}'


@contextmanager
def locked(folder: Path):
    folder.mkdir(parents=True, exist_ok=True)
    lock = folder / '.workflow.lock'
    try:
        stream = lock.open('x', encoding='utf-8')
    except FileExistsError as exc:
        raise ValidationError('GT workflow is locked; inspect interrupted work before recovery') from exc
    try:
        stream.close()
        yield
    finally:
        lock.unlink()


def entry_for(document: dict, page: int) -> dict:
    return {'document_id': document['document_id'], 'page': page,
            'source_sha256': document['source_sha256']}


def current(store: Path, document: dict, page: int) -> dict | None:
    folder = page_directory(store, document['document_id'], page)
    if not folder.exists():
        return None
    revisions = sorted(folder.glob('v*'))
    parent_state, result = None, None
    for number, revision in enumerate(revisions, 1):
        if revision.name != f'v{number:06d}' or not revision.is_dir():
            raise ValidationError('Noncontiguous GT revision history')
        metadata_path = revision / 'revision.json'
        metadata_data = read_bytes(metadata_path)
        metadata = parse_json(metadata_data, str(metadata_path))
        if (metadata.get('version') != number or metadata.get('parent_state_sha256') != parent_state
                or metadata.get('schema_version') != 'gt-revision-v1'
                or type(metadata.get('complete')) is not bool
                or metadata.get('manual_attestation') is not True):
            raise ValidationError('Invalid GT revision version/parent/completeness')
        sidecar = revision / 'gt.json'
        if digest(read_bytes(sidecar)) != metadata.get('sidecar_sha256'):
            raise ValidationError('GT initial sidecar changed')
        loaded = load_ground_truth(sidecar, entry_for(document, page))
        initial = loaded['metadata']
        if initial['review']['status'] != 'draft' or metadata.get('actor') != initial['transcriber']:
            raise ValidationError('Revision must begin as draft')
        state_hash, status = digest(metadata_data), 'draft'
        events = sorted((revision / 'events').glob('*.event.json'))
        sidecars = sorted((revision / 'events').glob('*.gt.json'))
        if len(events) != len(sidecars):
            raise ValidationError('Incomplete GT decision transaction; inspect before recovery')
        for event_number, event_path in enumerate(events, 1):
            if event_path.name != f'{event_number:06d}.event.json':
                raise ValidationError('Noncontiguous GT review events')
            event_data = read_bytes(event_path)
            event = parse_json(event_data, str(event_path))
            if (event.get('previous_state_sha256') != state_hash
                    or event.get('attests_source_and_reading_order') is not True):
                raise ValidationError('GT event history hash mismatch')
            next_status = 'reviewed' if status == 'draft' else 'approved' if status == 'reviewed' else None
            if next_status is None or event.get('status') != next_status or not metadata['complete']:
                raise ValidationError('Invalid GT review transition or incomplete labels')
            sidecar = event_path.with_name(f'{event_number:06d}.gt.json')
            if digest(read_bytes(sidecar)) != event.get('sidecar_sha256'):
                raise ValidationError('GT decision sidecar changed')
            next_gt = load_ground_truth(sidecar, entry_for(document, page))
            candidate = next_gt['metadata']
            if any(candidate[key] != initial[key] for key in initial
                   if key not in ('review', 'text_path')):
                raise ValidationError('Review event cannot alter transcription/reading order')
            if next_gt['text_sha256'] != loaded['text_sha256']:
                raise ValidationError('Review event cannot alter reference bytes')
            if (candidate['review']['status'] != next_status
                    or candidate['review']['reviewer'] != event.get('actor')
                    or candidate['review']['reviewed_at'] != event.get('created_at')):
                raise ValidationError('GT event identity/status/time mismatch')
            if status == 'reviewed' and candidate['review']['reviewer'] != loaded['metadata']['review']['reviewer']:
                raise ValidationError('Approval must use the recorded reviewer identity')
            loaded, status, state_hash = next_gt, next_status, digest(event_data)
        result = {'version': number, 'status': status, 'complete': metadata['complete'],
                  'sidecar': sidecar.resolve(), 'state_sha256': state_hash,
                  'metadata': metadata, 'ground_truth': loaded['metadata'], 'event_count': len(events)}
        parent_state = state_hash
    return result


def submit(store: Path, dataset: dict, document_id: str, page: int, transcript: Path, *,
           transcriber: str, reading_order: list[str], reason: str, expected_version: int,
           complete: bool, manual: bool, is_blank: bool = False) -> dict:
    document, _ = find_page(dataset, document_id, page)
    actor = nonempty(transcriber, 'transcriber').strip()
    nonempty(reason, 'reason')
    if type(expected_version) is not int or expected_version < 0:
        raise ValidationError('expected_version must be a nonnegative integer')
    if type(complete) is not bool or type(manual) is not bool or type(is_blank) is not bool:
        raise ValidationError('Completeness, manual and blank attestations must be booleans')
    if not manual:
        raise ValidationError('Explicit independent manual-transcription attestation required')
    if (not reading_order or any(not isinstance(value, str) or not value.strip() for value in reading_order)
            or len(set(reading_order)) != len(reading_order)):
        raise ValidationError('Reading order requires unique ordered descriptions')
    data = read_bytes(transcript)
    decode_text(data, str(transcript), allow_empty=is_blank)
    if is_blank and data:
        raise ValidationError('Blank reference must be zero bytes')
    folder = page_directory(store, document_id, page)
    with locked(folder):
        previous = current(store, document, page)
        version = previous['version'] if previous else 0
        if expected_version != version:
            raise ValidationError(f'Stale transcription version; current version is {version}')
        target = folder / f'v{version + 1:06d}'
        target.mkdir(exist_ok=False)
        (target / 'transcript.txt').write_bytes(data)
        gt = {'schema_version': 'gt-v1', **entry_for(document, page),
              'text_path': 'transcript.txt', 'text_sha256': digest(data), 'is_blank': is_blank,
              'reading_order': reading_order, 'transcriber': actor,
              'review': {'status': 'draft', 'reviewer': None, 'reviewed_at': None}}
        write_json(target / 'gt.json', gt)
        write_json(target / 'revision.json', {
            'schema_version': 'gt-revision-v1', 'version': version + 1,
            'created_at': timestamp(), 'actor': actor, 'reason': reason,
            'complete': complete, 'manual_attestation': True,
            'parent_state_sha256': previous['state_sha256'] if previous else None,
            'sidecar_sha256': digest(read_bytes(target / 'gt.json')),
        })
        return current(store, document, page)


def transition(store: Path, dataset: dict, document_id: str, page: int, *,
               actor: str, expected_version: int, action: str, attest: bool) -> dict:
    document, _ = find_page(dataset, document_id, page)
    actor = nonempty(actor, 'reviewer').strip()
    with locked(page_directory(store, document_id, page)):
        state = current(store, document, page)
        if state is None or state['version'] != expected_version:
            raise ValidationError('Missing or stale GT version')
        if not attest or not state['complete']:
            raise ValidationError('Complete labels and explicit source/reading-order review attestation required')
        identity = lambda value: unicodedata.normalize('NFC', value).casefold()
        if identity(actor) == identity(state['ground_truth']['transcriber']):
            raise ValidationError('Reviewer must be independent of transcriber')
        expected_status = {'review': ('draft', 'reviewed'), 'approve': ('reviewed', 'approved')}.get(action)
        if expected_status is None or state['status'] != expected_status[0]:
            raise ValidationError('Expected draft -> reviewed -> approved; no skipped transitions')
        if action == 'approve' and actor != state['ground_truth']['review']['reviewer']:
            raise ValidationError('Approver must be the recorded reviewer')
        gt = {**state['ground_truth'], 'text_path': '../transcript.txt',
              'review': {'status': expected_status[1], 'reviewer': actor, 'reviewed_at': timestamp()}}
        events = state['sidecar'].parent
        if events.name != 'events':
            events = events / 'events'
        events.mkdir(exist_ok=True)
        index = state['event_count'] + 1
        sidecar = events / f'{index:06d}.gt.json'
        write_json(sidecar, gt)
        write_json(events / f'{index:06d}.event.json', {
            'status': expected_status[1], 'actor': actor, 'created_at': gt['review']['reviewed_at'],
            'attests_source_and_reading_order': True,
            'previous_state_sha256': state['state_sha256'],
            'sidecar_sha256': digest(read_bytes(sidecar)),
        })
        return current(store, document, page)
