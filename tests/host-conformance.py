# SPDX-License-Identifier: MIT
"""Run the real package.el solver against a versioned local ELPA archive."""
import functools
import hashlib
import http.server
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading

SOURCE=Path(__file__).resolve().parents[1]
case=sys.argv[1]
def run(args,**kwargs):
    result=subprocess.run(list(map(str,args)),text=True,**kwargs)
    if result.returncode:
        if result.stderr: print(result.stderr,file=sys.stderr)
        result.check_returncode()
    return result
with tempfile.TemporaryDirectory(prefix='package-el-conformance-') as temp:
    temp=Path(temp)
    run(['nix','build',SOURCE,'--out-link',temp/'cli'])
    cli=temp/'cli/bin/package-el-purifier'
    wrapper=temp/'cli/bin/emacs'
    archive=temp/'archive'; archive.mkdir()
    handler=functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(archive))
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    root=temp/'config';root.mkdir()
    config=root/'packages.el'
    config.write_text(f"(require 'package)\n(setq package-archives '((\"test\" . \"http://127.0.0.1:{server.server_port}/\")))\n(setq package-selected-packages '(purifier-demo purifier-other))\n")
    def publish(version):
        for name in ('purifier-demo','purifier-other'):
            (archive/f'{name}-{version}.el').write_text(f';;; {name}.el --- Native conformance package -*- lexical-binding: t; -*-\n;; Version: {version}\n;; Package-Requires: ((emacs "29.1"))\n;;; Commentary:\n;; Test.\n;;; Code:\n(defconst {name}-version "{version}")\n(provide \'{name})\n;;; {name}.el ends here\n')
        (archive/'archive-contents').write_text('(1 '+ ' '.join(f'({name} . [({version.replace("."," ")}) ((emacs (29 1))) "Native conformance" single])' for name in ('purifier-demo','purifier-other')) + ')\n')
    external=temp/'locks/state.json'
    lockfile=external if case=='external' else root/'package-el-purifier.lock.json'
    def purifier(*args):run([cli,'--config',config,'--lockfile',lockfile,*args],cwd=root)
    try:
        publish('1.0'); purifier('lock')
        original=lockfile.read_bytes()
        if case=='relock':
            purifier('lock');assert lockfile.read_bytes()==original
            lockfile.write_text('{broken');purifier('lock');assert lockfile.read_bytes()==original
        elif case=='update':
            publish('2.0')
            purifier('lock');assert lockfile.read_bytes()==original
            purifier('update','purifier-demo')
            versions={p['name']:p['version'] for p in json.loads(lockfile.read_text())['packages']}
            assert versions=={'purifier-demo':'2.0','purifier-other':'1.0'},versions
            purifier('update')
            assert all(p['version']=='2.0' for p in json.loads(lockfile.read_text())['packages'])
        elif case!='external':raise ValueError(case)
        purifier('prefetch')
        # Configuration selection follows --init-directory from another cwd.
        # From this point, native package operations must work without a server.
        server.shutdown();server.server_close();thread.join()
        env={**os.environ,'PACKAGE_EL_PURIFIER_LOCKFILE':str(lockfile)}
        result=run([wrapper,'--init-directory',root,'--batch','-Q','--eval',"(progn (require 'purifier-demo) (require 'purifier-other) (setq package-archives '((\"bad\" . \"http://127.0.0.1:1/\"))) (package-refresh-contents) (princ purifier-demo-version))"],cwd=temp,env=env,capture_output=True)
        assert result.stdout==('2.0' if case=='update' else '1.0'),result
        # Exercise the native Lisp integration separately from the wrapper,
        # including its impure-plugin warning and CLI JSON response handling.
        toolchain=run(['nix','eval','--raw','--impure','--expr',f'(let f = builtins.getFlake {json.dumps(str(SOURCE))}; in (import f.inputs.nixpkgs {{ }}).emacs.outPath)'],capture_output=True).stdout
        plugin_env={**env,'PATH':str(cli.parent)+os.pathsep+os.environ['PATH']}
        plugin_env.pop('EMACSLOADPATH',None)
        expression=f"(progn (setq package-el-purifier-directory {json.dumps(str(root))}) (package-el-purifier-mode 1) (require 'purifier-demo) (princ purifier-demo-version))"
        native=run([Path(toolchain)/'bin/emacs','--batch','-Q','--load',SOURCE/'lisp/package-el-purifier.el','--eval',expression],cwd=temp,env=plugin_env,capture_output=True)
        assert native.stdout==result.stdout,native
        assert 'Plugin resolved impurely' in native.stderr,native.stderr
        if case=='external':
            run(['nix','build','--impure','--file',temp/'cli/lib/package-el-purifier/nix/realize.nix','--argstr','project',root,'--argstr','configFile',config,'--argstr','lockFile',lockfile,'--argstr','target','release','--out-link',temp/'release'])
        if case=='external':
            assert not (root/'package-el-purifier.lock.json').exists()
            assert lockfile.read_bytes()==original
            assert not list(root.glob('*.nix'))
        print(case+': native solver, locked packages and offline Emacs passed')
    finally:
        if thread.is_alive():server.shutdown();server.server_close();thread.join()
