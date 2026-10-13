"""Install bundled configuration without replacing hatch records or edited files."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

STATE_FILE = 'tryon_quail_hatchery/installed-files.json'


def safe_target(root: Path, relative: str) -> Path:
    """Reject absolute paths, traversal and symlinks escaping the config directory."""
    root = root.resolve()
    path = (root / relative).resolve()
    if Path(relative).is_absolute() or not path.is_relative_to(root):
        raise ValueError(f'Unsafe bundle path: {relative}')
    return path


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.quail-tmp')
    # Reject an existing symlink even if it points inside the config directory.
    if temporary.is_symlink():
        raise ValueError('Temporary path is a symlink')
    with temporary.open('wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def install_bundle(config_dir: str, payload_dir: str) -> dict[str, Any]:
    """Seed data once; update only files matching the previously installed hash."""
    root, payload = Path(config_dir).resolve(), Path(payload_dir).resolve()
    manifest = json.loads((payload / 'bundle.json').read_text(encoding='utf-8'))
    state_path = safe_target(root, STATE_FILE)
    previous = {}
    if state_path.exists():
        previous = json.loads(state_path.read_text(encoding='utf-8')).get('files', {})
    managed = dict(previous)
    result = {'version': manifest['version'], 'installed': [], 'updated': [],
              'preserved': [], 'conflicts': [], 'unchanged': []}
    for item in manifest['files']:
        source = safe_target(payload, item['source'])
        destination = safe_target(root, item['destination'])
        content = source.read_bytes()
        content_hash = digest(content)
        if content_hash != item['sha256']:
            raise ValueError(f"Bundle checksum mismatch: {item['source']}")
        relative = item['destination']
        if item.get('seed_only') and destination.exists():
            result['preserved'].append(relative)
            continue
        if not destination.exists():
            atomic_write(destination, content)
            if not item.get('seed_only'):
                managed[relative] = content_hash
            result['installed'].append(relative)
        elif digest(destination.read_bytes()) == content_hash:
            if not item.get('seed_only'):
                managed[relative] = content_hash
            result['unchanged'].append(relative)
        elif previous.get(relative) == digest(destination.read_bytes()):
            backup = safe_target(root, relative + '.quail-backup')
            atomic_write(backup, destination.read_bytes())
            atomic_write(destination, content)
            managed[relative] = content_hash
            result['updated'].append(relative)
        else:
            # A staged update is never named .py or .yaml, so HA cannot load both.
            staged = safe_target(root, relative + '.quail-update')
            atomic_write(staged, content)
            result['conflicts'].append(relative)
    atomic_write(state_path, (json.dumps({'version': manifest['version'], 'files': managed,
                                        'last_result': result}, indent=2) + '\n').encode())
    return result
