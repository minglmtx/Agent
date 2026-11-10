import json
import os
from pathlib import Path
import sys
import unittest
from isolation import restrict, runtime_reads

root = Path(sys.argv[1]).resolve()
os.chdir(root)
sys.path.insert(0, str(root))
restrict(runtime_reads() + [sys.prefix], [root, '/dev/null'])
suite = unittest.defaultTestLoader.discover('.', pattern='*_test.py')
r = unittest.TextTestRunner(verbosity=0).run(suite)
print(json.dumps(dict(tests=r.testsRun, failures=len(r.failures), errors=len(r.errors), skipped=len(r.skipped), successful=r.wasSuccessful())))
