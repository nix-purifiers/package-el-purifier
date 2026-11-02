# SPDX-License-Identifier: MIT
"""Validate locked Emacs package archives and their dependency closure."""
import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

ADVICE = 'run package-el-purifier lock (use --lockfile for an external lock)'


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def seal(data):
    data = {k: v for k, v in data.items() if k != 'contentHash'}
    return {**data, 'contentHash': digest(data)}


def safe_name(value):
    return isinstance(value, str) and re.fullmatch('[A-Za-z0-9][A-Za-z0-9+-]*', value) is not None


def problems(config, data):
    try:
        if not isinstance(data, dict) or data.get('version') != 1:
            raise ValueError('unsupported lock format')
        if data.get('contentHash') != digest({k: v for k, v in data.items() if k != 'contentHash'}):
            raise ValueError('contentHash mismatch')
        if data.get('configHash') != file_hash(config):
            raise ValueError('package declarations changed after locking')
        if not isinstance(data.get('emacsVersion'), str):
            raise ValueError('missing Emacs version')
        for key in ['packages', 'selected']:
            if not isinstance(data.get(key), list):
                raise ValueError(f'{key} must be a list')
        if not all(safe_name(n) for n in data['selected'] + list(data['builtins'])):
            raise ValueError('invalid selected or builtin package name')
        if not isinstance(data.get('builtins'), dict) or not all(isinstance(v, list) and all(isinstance(x, int) and x >= 0 for x in v) for v in data['builtins'].values()):
            raise ValueError('invalid builtin version map')
        names = []
        for package in data['packages']:
            if not isinstance(package, dict) or not safe_name(package.get('name')):
                raise ValueError('invalid package name')
            name = package['name']; names.append(name)
            if not isinstance(package.get('version'), str) or not re.fullmatch('[0-9][A-Za-z0-9.-]*', package['version']) or '..' in package['version']:
                raise ValueError(f'{name}: invalid version')
            if package.get('kind') not in ('tar', 'single'):
                raise ValueError(f'{name}: unsupported package kind')
            if not isinstance(package.get('hash'), str) or not re.fullmatch(r'sha256-[A-Za-z0-9+/]{43}=', package['hash']):
                raise ValueError(f'{name}: invalid archive hash')
            parsed = urlsplit(package['url'])
            if parsed.scheme not in ('https', 'http') or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
                raise ValueError(f'{name}: invalid archive URL')
            if not isinstance(package.get('versionList'), list) or not package['versionList'] or not all(isinstance(n, int) and n >= 0 for n in package['versionList']):
                raise ValueError(f'{name}: invalid native version vector')
            if not isinstance(package.get('summary'), str) or not isinstance(package.get('requirements'), list):
                raise ValueError(f'{name}: missing native package metadata')
        if len(set(names)) != len(names):
            raise ValueError('duplicate package names')
        available = set(names + list(data['builtins']))
        required = set(data['selected'])
        for package in data['packages']:
            for req in package['requirements']:
                if not isinstance(req, list) or len(req) != 2 or not safe_name(req[0]) or not isinstance(req[1], list) or not all(isinstance(n, int) and n >= 0 for n in req[1]):
                    raise ValueError('invalid dependency requirement')
                required.add(req[0])
        versions = {**data['builtins'], **{p['name']: p['versionList'] for p in data['packages']}}
        for package in data['packages']:
            for name, minimum in package['requirements']:
                if name in versions:
                    width = max(len(minimum), len(versions[name]))
                    actual = versions[name] + [0] * (width - len(versions[name]))
                    expected = minimum + [0] * (width - len(minimum))
                    if actual < expected:
                        raise ValueError(f'{name}: locked version is below the native requirement')
        if missing := required - available:
            raise ValueError('missing package entries: ' + ', '.join(sorted(missing)))
        return []
    except (ValueError, TypeError, KeyError, AttributeError, OSError) as error:
        return [f'package-el-purifier: {error}; {ADVICE}']
