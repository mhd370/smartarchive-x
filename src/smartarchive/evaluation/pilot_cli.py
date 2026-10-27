"""Pilot inventory, human GT workflow and historical-output comparison CLI."""
import argparse
from pathlib import Path

from .ground_truth import current, submit, transition
from .historical import prepare
from .metrics import POLICIES
from .pilot import inventory, load_dataset
from .runner import run
from .tracking import write_json
from .validation import ValidationError, parse_json, read_bytes


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument('--dataset', type=Path, default=Path('docs/pilot/dataset.json'))
    parser.add_argument('--store', type=Path, default=Path('data/ground_truth/pilot'))
    commands = parser.add_subparsers(dest='command', required=True)
    scan = commands.add_parser('inventory', help='Deterministic source inventory; never overwrite')
    scan.add_argument('--input', type=Path, default=Path('data/input'))
    scan.add_argument('--output', type=Path, default=Path('docs/pilot/dataset.json'))
    scan.add_argument('--check', action='store_true')
    commands.add_parser('inspect', help='Validate and list source pages/current GT status')
    add = commands.add_parser('submit', help='Snapshot independently transcribed page as a new draft')
    add.add_argument('--text', type=Path, required=True)
    add.add_argument('--transcriber', required=True)
    add.add_argument('--reading-order', nargs='+', required=True)
    add.add_argument('--reason', required=True)
    add.add_argument('--manual', action='store_true')
    add.add_argument('--complete', action='store_true')
    add.add_argument('--blank', action='store_true')
    for name in ('review', 'approve'):
        command = commands.add_parser(name)
        command.add_argument('--reviewer', required=True)
        command.add_argument('--attest', action='store_true')
    for command in (add, commands.choices['review'], commands.choices['approve']):
        command.add_argument('--document', required=True)
        command.add_argument('--page', type=int, required=True)
        command.add_argument('--expected-version', type=int, required=True)
    compare = commands.add_parser('compare', help='Import saved predictions and benchmark; no OCR')
    compare.add_argument('--bindings', type=Path, default=Path('docs/pilot/historical_bindings.json'))
    compare.add_argument('--output-root', type=Path, default=Path('results/pilot'))
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        if args.command == 'inventory':
            value = inventory(root, root / args.input)
            output = root / args.output
            if args.check:
                if parse_json(read_bytes(output), str(output)) != value:
                    raise ValidationError('Inventory drift detected; create/review a new dataset version')
                print('Inventory matches source bytes and page pixels')
            else:
                output.parent.mkdir(parents=True, exist_ok=True)
                write_json(output, value)
                print(output)
            return 0
        dataset = load_dataset(root / args.dataset, root)
        store = root / args.store
        if args.command == 'inspect':
            for document in dataset['documents']:
                for page in document['pages']:
                    state = current(store, document, page['page'])
                    print(f"{document['document_id']} page={page['page']} "
                          f"{page['width']}x{page['height']} GT={state['status'] if state else 'PENDING'} "
                          f"version={state['version'] if state else 0} source={document['source_path']} "
                          f"sidecar={state['sidecar'] if state else 'none'}")
            return 0
        if args.command == 'submit':
            state = submit(store, dataset, args.document, args.page, root / args.text,
                           transcriber=args.transcriber, reading_order=args.reading_order,
                           reason=args.reason, expected_version=args.expected_version,
                           complete=args.complete, manual=args.manual, is_blank=args.blank)
        elif args.command in ('review', 'approve'):
            state = transition(store, dataset, args.document, args.page, actor=args.reviewer,
                               expected_version=args.expected_version, action=args.command, attest=args.attest)
        else:
            bindings_path = root / args.bindings
            bindings = parse_json(read_bytes(bindings_path), str(bindings_path))
            bundle = prepare(root, dataset, bindings, root / args.output_root, store)
            print(f'Historical import bundle: {bundle}')
            folder, report = run(bundle / 'benchmark.json', bundle / 'evaluation', list(POLICIES))
            print(f"{report['status']}: {folder}")
            for row in report['pages']:
                print(f"{row['variant']}: {row['status']} {row.get('reason') or ''}")
            return 0 if report['status'] == 'COMPLETED' else 2
        print(f"GT version={state['version']} status={state['status']} sidecar={state['sidecar']}")
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, f'Pilot validation error: {exc}\n')


if __name__ == '__main__':
    raise SystemExit(main())
