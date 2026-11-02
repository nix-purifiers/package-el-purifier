# SPDX-License-Identifier: MIT
"""Resolve with package.el, then use Nix to install a locked ELPA environment."""
import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
from . import lock


def read(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError) as error:
        raise ValueError(f'cannot read {path}: {error}; {lock.ADVICE}') from error


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, mode='w', delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(json.dumps(data, sort_keys=True, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def do_lock(root, config, sidecar, update=False, names=()):
    previous = None
    if sidecar.exists():
        try:
            previous = read(sidecar)
            if not isinstance(previous, dict) or previous.get('contentHash') != lock.seal(previous)['contentHash']:
                previous = None
                raise ValueError('invalid prior lock')
            # A changed declaration still retains existing pins. Validate its
            # structure against its original fingerprint before reusing it.
            checked = lock.seal({**previous, 'configHash': lock.file_hash(config)})
            if lock.problems(config, checked):
                previous = None
            if not update and previous and not lock.problems(config, previous):
                print(f'Existing package resolution retained in {sidecar}')
                return
        except ValueError:
            previous = None
    if names and not previous:
        raise ValueError('named updates require a valid existing lockfile; run lock first')
    if names:
        known = set(previous['selected']) | {p['name'] for p in previous['packages']}
        if unknown := set(names) - known:
            raise ValueError('packages are not locked: ' + ', '.join(sorted(unknown)))
    with tempfile.TemporaryDirectory(prefix='package-el-purifier-') as temp:
        resolved = Path(temp) / 'resolution.json'
        env = {**os.environ, 'PACKAGE_EL_PURIFIER_MANIFEST': str(config), 'PACKAGE_EL_PURIFIER_RESOLUTION': str(resolved), 'PACKAGE_EL_PURIFIER_LOCKING': '1'}
        if previous and (not update or names):
            frozen = [p for p in previous['packages'] if p['name'] not in names]
            pins = Path(temp) / 'pins.json'
            write(pins, frozen)
            env['PACKAGE_EL_PURIFIER_PINS'] = str(pins)
        env.pop('EMACSLOADPATH', None)
        run([os.environ.get('PACKAGE_EL_PURIFIER_EMACS', 'emacs'), '--batch', '-Q', '--load', os.environ['PACKAGE_EL_PURIFIER_RESOLVER']], env=env)
        data = read(resolved)
        for package in data['packages']:
            archive = package.pop('archive')
            if 'melpa.org' in archive:
                raise ValueError('rolling MELPA archives are not supported yet; use GNU or NonGNU ELPA for durable version archives')
            suffix = '.el' if package['kind'] == 'single' else '.tar'
            url = archive.rstrip('/') + '/' + package['name'] + '-' + package['version'] + suffix
            old = next((p for p in (previous or {}).get('packages', []) if p['name'] == package['name'] and p['version'] == package['version'] and p['url'] == url), None)
            if old:
                package.update(url=url, hash=old['hash'])
            else:
                with urllib.request.urlopen(url, timeout=60) as response:
                    digest = hashlib.file_digest(response, 'sha256').digest()
                package.update(url=url, hash='sha256-' + base64.b64encode(digest).decode())
        data['packages'].sort(key=lambda p: p['name'])
        # Retain only the builtin names the actual transaction needs.
        names = set(data['selected']) | {r[0] for p in data['packages'] for r in p['requirements']}
        data['builtins'] = {name: version for name, version in sorted(data['builtins']) if name in names}
        data['selected'] = sorted(set(data['selected']))
        data.update(version=1, configHash=lock.file_hash(config))
        data = lock.seal(data)
        if errors := lock.problems(config, data):
            raise ValueError('\n'.join(errors))
        write(sidecar, data)
    print(f'Locked {len(data["packages"])} Emacs packages in {sidecar}')


def prepare(root, config, sidecar):
    data = read(sidecar)
    if errors := lock.problems(config, data):
        raise ValueError('\n'.join(errors))
    state = sidecar.parent / '.package-el-purifier' / lock.digest(str(root))[:12]
    state.mkdir(parents=True, exist_ok=True)
    for target in ['environment', 'runtime']:
        run(['nix', 'build', '--impure', '--file', os.environ['PACKAGE_EL_PURIFIER_REALIZE'], '--argstr', 'project', str(root), '--argstr', 'configFile', str(config), '--argstr', 'lockFile', str(sidecar), '--argstr', 'target', target, '--out-link', str(state / target)])
    return (state / 'environment').resolve()


def configuration_root(arguments, cwd):
    """Follow Emacs' explicit init directory, then project and user configs."""
    for index, argument in enumerate(arguments):
        if argument.startswith('--init-directory='):
            return Path(argument.split('=', 1)[1]).expanduser().resolve()
        if argument == '--init-directory' and index + 1 < len(arguments):
            return Path(arguments[index + 1]).expanduser().resolve()
    if (cwd / 'packages.el').exists():
        return cwd
    legacy = Path.home() / '.emacs.d'
    xdg = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'emacs'
    # Match Emacs' preference for an existing legacy configuration.
    return legacy if legacy.exists() else xdg


def main(argv=None):
    parser=argparse.ArgumentParser(prog='package-el-purifier')
    parser.add_argument('--lockfile'); parser.add_argument('--config')
    sub=parser.add_subparsers(dest='command', required=True)
    sub.add_parser('lock')
    update=sub.add_parser('update'); update.add_argument('packages', nargs='*')
    prefetch=sub.add_parser('prefetch'); prefetch.add_argument('--json', action='store_true')
    native=sub.add_parser('native', help=argparse.SUPPRESS); native.add_argument('args',nargs=argparse.REMAINDER)
    publish=sub.add_parser('publish'); publish.add_argument('--repo', required=True); publish.add_argument('--tag', required=True)
    args=parser.parse_args(argv)
    root=Path.cwd()
    if args.command == 'native':
        root=configuration_root(args.args, root)
    config=Path(args.config or os.environ.get('PACKAGE_EL_PURIFIER_CONFIG',root/'packages.el')).resolve()
    if args.config or os.environ.get('PACKAGE_EL_PURIFIER_CONFIG'):
        root=config.parent
    sidecar=Path(args.lockfile or os.environ.get('PACKAGE_EL_PURIFIER_LOCKFILE',root/'package-el-purifier.lock.json')).resolve()
    try:
        if args.command in ('lock','update'):
            do_lock(root,config,sidecar,args.command=='update',getattr(args,'packages',()))
        elif args.command=='prefetch':
            environment=prepare(root,config,sidecar)
            print(json.dumps({'environment':str(environment)}) if args.json else environment)
        elif args.command=='publish':
            prepare(root,config,sidecar)
            with tempfile.TemporaryDirectory(prefix='package-el-publish-') as temp:
                result=Path(temp)/'release'
                run(['nix','build','--impure','--file',os.environ['PACKAGE_EL_PURIFIER_REALIZE'],'--argstr','project',str(root),'--argstr','configFile',str(config),'--argstr','lockFile',str(sidecar),'--argstr','target','release','--out-link',str(result)])
                run(['gh','release','create',args.tag,str(result/'config.tar.gz'),'--repo',args.repo,'--title',args.tag])
        else:
            command=args.args[1:] if args.args[:1]==['--'] else args.args
            tool=os.environ.get('PACKAGE_EL_PURIFIER_EMACS','emacs')
            if not sidecar.exists() and not sidecar.is_symlink():
                print('package-el-purifier: warning: no lockfile; using ordinary, impure Emacs package resolution',file=sys.stderr)
                os.execv(tool,[tool,*command])
            environment=prepare(root,config,sidecar)
            os.environ['EMACSLOADPATH']=str(environment/'site-lisp')+os.pathsep+os.environ.get('EMACSLOADPATH','')
            os.environ['PACKAGE_EL_PURIFIER_ENVIRONMENT']=str(environment)
            os.execv(tool,[tool,'--load',str(environment/'site-lisp/site-start.el'),*command])
    except (ValueError,KeyError,TypeError,OSError) as error:
        print(f'package-el-purifier: {error}',file=sys.stderr); return 1
    except subprocess.CalledProcessError as error:
        return error.returncode if error.returncode>0 else 1
    return 0

if __name__=='__main__': sys.exit(main())
