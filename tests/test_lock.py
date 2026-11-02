# SPDX-License-Identifier: MIT
import tempfile
import unittest
from pathlib import Path
from package_el_purifier import lock

class LockTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.config=self.root/'packages.el'; self.config.write_text("(setq package-selected-packages '(example))")
        self.package={'name':'example','version':'1.0','versionList':[1,0],'requirements':[['emacs',[29,1]]],'summary':'Example','kind':'tar','url':'https://elpa.gnu.org/packages/example-1.0.tar','hash':'sha256-'+'A'*43+'='}
        self.data=lock.seal({'version':1,'configHash':lock.file_hash(self.config),'emacsVersion':'31.1','selected':['example'],'builtins':{'emacs':[31,1]},'packages':[self.package]})
    def test_valid(self): self.assertEqual(lock.problems(self.config,self.data),[])
    def test_stale(self):
        self.config.write_text('changed'); self.assertTrue(lock.problems(self.config,self.data))
    def test_tampered(self):
        self.data['packages']=[]; self.assertTrue(lock.problems(self.config,self.data))
    def test_missing_resealed(self):
        self.data['packages']=[]; self.assertIn('example',' '.join(lock.problems(self.config,lock.seal(self.data))))
    def test_missing_transitive_resealed(self):
        self.package['requirements'].append(['missing',[1,0]])
        self.assertIn('missing',' '.join(lock.problems(self.config,lock.seal(self.data))))
    def test_builtin_too_old(self):
        self.data['builtins']['emacs']=[28]
        self.assertTrue(lock.problems(self.config,lock.seal(self.data)))
    def test_unsafe_names(self):
        self.package['name']='../escape'; self.assertTrue(lock.problems(self.config,lock.seal(self.data)))
    def test_bad_hash(self):
        self.package['hash']='bad'; self.assertTrue(lock.problems(self.config,lock.seal(self.data)))
    def test_unknown_format(self): self.assertTrue(lock.problems(self.config,[]))
    def test_builtin_selected(self):
        self.data['selected']=['emacs'];self.data['packages']=[]
        self.assertEqual(lock.problems(self.config,lock.seal(self.data)),[])
if __name__=='__main__': unittest.main()
