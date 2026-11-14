"""Folder knowledge graph (`folder-graph-v1`): which kinds of documents live in which folders, and how folders
are linked by duplicate and version relations.

Nodes:
- folders, including the subfolders;
- the unfiled documents as one pseudo-folder (`null`);
- categories, using each document's current category: confirmed, else suggested (`document_categories`).

Edges:
- folder → subfolder;
- folder — category, weighted by the number of documents and counting confirmed ones apart, so the view
  shows what people decided and not only what the classifier suggested;
- folder — folder, weighted by the relations whose documents sit in the two folders, rejected relations
  excluded. This is how a version filed in a different folder from its original shows up.

It is computed from the archive on request. Nothing is stored and no document content is returned, so it
needs only the Reader role.
"""
from collections import Counter

METHOD = 'folder-graph-v1'


def build(db) -> dict:
    with db.connect() as c:
        folders = [dict(row) for row in c.execute('SELECT id, parent_id, name, path FROM folders ORDER BY path')]
        placed = {row['document_id']: row['folder_id'] for row in c.execute('SELECT document_id, folder_id FROM document_folders')}
        documents = [row['id'] for row in c.execute('SELECT id FROM documents')]
        categories = {row['id']: row['name'] for row in c.execute('SELECT id, name FROM categories')}
        current = {row['document_id']: (row['category_id'], row['state'])
                   for row in c.execute('SELECT document_id, category_id, state FROM document_categories')}
        relations = c.execute("SELECT source_id, target_id, kind, status FROM document_relations WHERE status != 'rejected'").fetchall()
    per_folder, links = Counter(), Counter()
    confirmed = Counter()
    for document in documents:
        folder = placed.get(document)
        per_folder[folder] += 1
        category, state = current.get(document, (None, 'none'))
        if category:
            links[(folder, category)] += 1
            if state == 'confirmed':
                confirmed[(folder, category)] += 1
    cross = Counter()
    for row in relations:
        a, b = placed.get(row['source_id']), placed.get(row['target_id'])
        if a != b:
            key = tuple(sorted((a or '', b or ''))) + (row['kind'],)
            cross[key] += 1
    in_use = Counter(category for (_, category) in links.elements())
    return {
        'method': METHOD,
        'folders': [{**f, 'documents': per_folder.get(f['id'], 0)} for f in folders]
        + ([{'id': None, 'parent_id': None, 'name': 'غير مصنّف في مجلد', 'path': '', 'documents': per_folder[None]}]
           if per_folder.get(None) else []),
        'categories': [{'id': k, 'name': categories.get(k, k), 'documents': n} for k, n in in_use.most_common()],
        'folder_category': [{'folder_id': f, 'category_id': c, 'documents': n, 'confirmed': confirmed.get((f, c), 0)}
                            for (f, c), n in sorted(links.items(), key=lambda item: -item[1])],
        'folder_relations': [{'a': a or None, 'b': b or None, 'kind': kind, 'count': n}
                             for (a, b, kind), n in sorted(cross.items(), key=lambda item: -item[1])],
    }
