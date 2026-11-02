# SPDX-License-Identifier: MIT
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from package_el_purifier.cli import configuration_root

SOURCE = Path(__file__).resolve().parents[1]

class CliTests(unittest.TestCase):
    def test_explicit_init_directory(self):
        self.assertEqual(configuration_root(['--init-directory=/tmp/config'], Path('/tmp')), Path('/tmp/config'))
        self.assertEqual(configuration_root(['--init-directory', '/tmp/config'], Path('/tmp')), Path('/tmp/config'))

    def test_project_config(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root/'packages.el').touch()
            self.assertEqual(configuration_root([], root), root)

    def test_user_config(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch('pathlib.Path.home', return_value=root), patch.dict(os.environ, {'XDG_CONFIG_HOME': str(root/'xdg')}):
                self.assertEqual(configuration_root([], root/'elsewhere'), root/'xdg/emacs')
                (root/'.emacs.d').mkdir()
                self.assertEqual(configuration_root([], root/'elsewhere'), root/'.emacs.d')

    def test_fallback_preserves_arguments_streams_and_status(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            tool=root/'emacs'
            tool.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\nprintf "native stderr\\n" >&2\nexit 23\n')
            tool.chmod(0o755)
            result=subprocess.run([sys.executable,'-m','package_el_purifier.cli','native','--','--batch','--eval','(message "a b")'],cwd=root,env={**os.environ,'PYTHONPATH':str(SOURCE),'HOME':temp,'PACKAGE_EL_PURIFIER_EMACS':str(tool)},text=True,capture_output=True)
            self.assertEqual(result.returncode,23)
            self.assertEqual(result.stdout,'--batch\n--eval\n(message "a b")\n')
            self.assertIn('warning: no lockfile',result.stderr)
            self.assertIn('native stderr',result.stderr)

    def test_invalid_lock_fails_without_exec(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); (root/'packages.el').write_text(''); (root/'package-el-purifier.lock.json').write_text('{}')
            result=subprocess.run([sys.executable,'-m','package_el_purifier.cli','native','--','--version'],cwd=root,env={**os.environ,'PYTHONPATH':str(SOURCE),'PACKAGE_EL_PURIFIER_EMACS':'/does/not/exist'},text=True,capture_output=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('unsupported lock format',result.stderr)
            self.assertNotIn('warning: no lockfile',result.stderr)
