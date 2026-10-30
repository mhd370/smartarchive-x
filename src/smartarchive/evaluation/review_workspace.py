"""Offline source/transcript workspace; never submits or approves ground truth."""
import base64
from html import escape
from io import BytesIO
from pathlib import Path

from .ground_truth import current
from .pilot import find_page, pages, pixel_hash
from .runner import load_ground_truth
from .tracking import create_run, environment, timestamp, write_json
from .validation import ValidationError, digest, read_bytes


def create_workspace(root: Path, dataset: dict, store: Path, document_id: str,
                     page_number: int, output_root: Path, *, review_only: bool = False) -> Path:
    document, page = find_page(dataset, document_id, page_number)
    source = root / document['source_path']
    if digest(read_bytes(source)) != document['source_sha256']:
        raise ValidationError('Source hash changed; cannot prepare a transcription workspace')
    image = next((image for number, image in pages(source) if number == page_number), None)
    if image is None or pixel_hash(image) != page['pixel_sha256']:
        raise ValidationError('Source page pixels do not match the pilot inventory')
    state = current(store, document, page_number)
    if review_only and state is None:
        raise ValidationError('No submitted transcription to review; create a manual draft first')
    text, reference_hash = '', None
    if state:
        loaded = load_ground_truth(state['sidecar'], {
            'document_id': document_id, 'page': page_number, 'source_sha256': document['source_sha256']})
        text, reference_hash = loaded['text'], loaded['text_sha256']
    buffer = BytesIO()
    image.save(buffer, format='PNG')
    preview = buffer.getvalue()
    folder = create_run(output_root)
    (folder / 'source_page.png').write_bytes(preview)
    if state:
        (folder / 'reference_snapshot.txt').write_bytes(loaded['text_data'])
        (folder / 'ground_truth_snapshot.json').write_bytes(loaded['metadata_data'])
    status = state['status'].upper() if state else 'PENDING'
    version = state['version'] if state else 0
    order = state['ground_truth']['reading_order'] if state else []
    metadata = {
        'schema_version': 'transcription-workspace-v1', 'created_at': timestamp(),
        'mode': 'read-only-review' if review_only else 'working-copy',
        'document_id': document_id, 'page': page_number, 'source_path': str(source.resolve()),
        'source_sha256': document['source_sha256'], 'source_pixel_sha256': page['pixel_sha256'],
        'preview_sha256': digest(preview), 'gt_status': status, 'transcription_version': version,
        'reference_sha256': reference_hash, 'reading_order': order,
        'gt_history_state_sha256': state['state_sha256'] if state else None,
        'complete_attestation': state['complete'] if state else False,
        'sidecar_path': str(state['sidecar']) if state else None,
        'environment': environment(),
        'note': 'Human workspace only. No OCR, submission, review transition or approval occurs here.',
    }
    title = 'Frozen transcription review' if review_only else 'Manual Arabic transcription'
    order_html = ''.join(f'<li>{escape(item)}</li>' for item in order) or '<li>Not yet declared. Confirm heading, right column, then left column against this source.</li>'
    readonly = ' readonly' if review_only else ''
    controls = '' if review_only else '''
<label>Download line endings <select id="endings"><option value="lf">LF</option><option value="crlf">CRLF</option></select></label>
<button id="save" type="button">Download UTF-8 text (no BOM)</button>
<p>Save drafts often. Closing this page loses unsaved edits. Downloading does not submit or approve GT.</p>'''
    html = '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'none'; object-src 'none'; base-uri 'none'">
<title>SmartArchive-X manual review</title>
<style>
body{font-family:Segoe UI,Arial,sans-serif;margin:1rem;background:#f4f6f8;color:#17212b}
header,section{background:white;padding:1rem;border:1px solid #ccd3da;border-radius:6px}
main{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:1rem;margin-top:1rem}
.source{height:75vh;overflow:auto;background:#e9edf0}img{display:block;width:100%;max-width:none}
textarea{box-sizing:border-box;width:100%;height:58vh;font:1.35rem/1.9 Tahoma,Arial,sans-serif;unicode-bidi:plaintext;padding:1rem}
code{overflow-wrap:anywhere}button,select{padding:.5rem;margin:.4rem}li{margin-bottom:.3rem}
@media(max-width:800px){main{grid-template-columns:1fr}}
</style></head><body>
<header><h1>__TITLE__</h1><p><strong>No OCR text is used to populate a new transcription.</strong></p>
<p>Document <code>__DOCUMENT__</code> — page __PAGE__ — GT __STATUS__ — version __VERSION__</p>
<p>Source SHA-256: <code>__HASH__</code><br>Reference SHA-256: <code>__REFERENCE__</code></p>
<p>Read the original logical Arabic text. Preserve visible punctuation and diacritics; do not reverse characters.
For columns, finish the right column before the left after any spanning heading, once confirmed against the source.</p>
<p>Completeness is a human check: verify every heading, line, column, numeral and punctuation mark.
Flag unresolved text by leaving the revision incomplete; do not guess or insert an OCR suggestion.</p>
<details><summary>Declared reading order for this snapshot</summary><ol>__ORDER__</ol></details></header>
<main><section><h2>Original page</h2><label>Zoom <input id="zoom" type="range" min="100" max="300" value="100"></label>
<div class="source"><img id="source" alt="Exact pilot page preview" src="data:image/png;base64,__IMAGE__"></div></section>
<section><h2>__EDITOR_TITLE__</h2><textarea id="transcript" lang="ar" dir="rtl" spellcheck="false"__READONLY__>
__TEXT__</textarea>
<p id="count"></p>__CONTROLS__
<p>This page is offline and sends no text anywhere. Independent review and approval use the existing CLI with an expected version.</p>
</section></main>
<script>
const editor=document.getElementById('transcript');
const update=()=>{document.getElementById('count').textContent=Array.from(editor.value).length+' code points; '+(editor.value?editor.value.split(/\\r?\\n/).length:0)+' lines (not completeness evidence)';};
editor.addEventListener('input',update);update();
document.getElementById('zoom').addEventListener('input',event=>{document.getElementById('source').style.width=event.target.value+'%';});
const save=document.getElementById('save');
if(save){save.addEventListener('click',()=>{
 if(!editor.value.trim()){alert('A nonblank page needs manual text. For a truly blank page use the explicit CLI blank-page workflow.');return;}
 let text=editor.value.replace(/\\r\\n?/g,'\\n');
 if(document.getElementById('endings').value==='crlf'){text=text.replace(/\\n/g,'\\r\\n');}
 const url=URL.createObjectURL(new Blob([text],{type:'text/plain;charset=utf-8'}));
 const link=document.createElement('a');link.href=url;link.download='smartarchive_page___PAGE__.txt';link.click();
 setTimeout(()=>URL.revokeObjectURL(url),1000);
});}
</script></body></html>'''
    replacements = {
        '__TITLE__': title, '__DOCUMENT__': escape(document_id), '__PAGE__': str(page_number),
        '__STATUS__': status, '__VERSION__': str(version), '__HASH__': document['source_sha256'],
        '__REFERENCE__': reference_hash or 'No submitted reference', '__ORDER__': order_html,
        '__IMAGE__': base64.b64encode(preview).decode('ascii'), '__READONLY__': readonly,
        '__TEXT__': escape(text), '__CONTROLS__': controls,
        '__EDITOR_TITLE__': 'Read-only submitted snapshot' if review_only else 'Working copy — type manually',
    }
    # Replace in one pass so reference text resembling a placeholder stays literal.
    import re
    html = re.sub('|'.join(map(re.escape, replacements)), lambda match: replacements[match.group()], html)
    (folder / 'workspace.html').write_text(html, encoding='utf-8', newline='\n')
    metadata['workspace_html_sha256'] = digest(read_bytes(folder / 'workspace.html'))
    write_json(folder / 'workspace.json', metadata)
    return folder
