"""Apply the organized snapshot to an existing repo without overwriting divergent files.

Run from the EXTRACTED archive: python tools/apply_organization.py --target /path/to/repo
Then repeat with --apply after inspecting the dry run. Never commits or pushes.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

SOURCE = Path(__file__).resolve().parents[1]
MANIFEST = 'docs/organization_manifest.json'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() and not path.is_symlink() else None


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--target', required=True, type=Path)
    p.add_argument('--apply', action='store_true')
    args = p.parse_args()
    target = args.target.expanduser().resolve()
    if target == SOURCE or not (target / '.git').exists():
        p.error('target must be a separate existing Git working tree; extract archive outside it')
    manifest = json.loads((SOURCE / MANIFEST).read_text())
    old, new = manifest['before'], manifest['after']
    new = {**new, MANIFEST: digest(SOURCE / MANIFEST)}
    errors, remove, write = [], [], []
    for path, expected in new.items():
        if digest(SOURCE / path) != expected:
            errors.append(f'release integrity: {path}')
    for path in sorted(set(old) | set(new)):
        f = target / path
        before, after, actual = old.get(path), new.get(path), digest(f)
        if f.is_symlink() or any(p.is_symlink() for p in f.parents if p != target and target in p.parents):
            errors.append(f'symlink in managed path: {path}'); continue
        if f.exists() and not f.is_file():
            errors.append(f'not a regular file: {path}'); continue
        if actual == after:
            continue
        # Preserve local modifications to files that this release did not change.
        if before == after and actual is not None:
            print('KEEP LOCAL:', path); continue
        if actual is not None and actual != before:
            errors.append(f'local file differs from uploaded branch and new release: {path}'); continue
        if after is None:
            if actual is not None:
                remove.append(path)
        else:
            # Refuse new path under an existing non-directory parent.
            if any(q.exists() and not q.is_dir() for q in f.parents if q != target and target in q.parents):
                errors.append(f'parent path is not a directory: {path}'); continue
            write.append(path)
    if errors:
        print('\n'.join('CONFLICT: '+e for e in errors), file=sys.stderr)
        print('No changes made. Reconcile these paths manually and retry.', file=sys.stderr)
        return 2
    print('\n'.join(['REMOVE (old layout): '+x for x in remove] + ['COPY (new layout): '+x for x in write]))
    print(f'Planned: {len(remove)} removals, {len(write)} copies. Unrelated files untouched.')
    if not args.apply:
        print('DRY RUN: no files changed. Repeat with --apply to proceed.'); return 0
    # Copy first, then remove verified old paths. No recursive deletion.
    for path in write:
        out = target / path; out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SOURCE / path, out)
    for path in remove:
        (target / path).unlink()
    for parent in sorted({(target / x).parent for x in remove}, key=lambda q: len(q.parts), reverse=True):
        while parent != target:
            try: parent.rmdir()
            except OSError: break
            parent = parent.parent
    print('Applied. Inspect git status and git diff. No commit or push performed.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
