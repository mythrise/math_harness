"""Reproducible minimal patch; legacy baseline files are never changed."""
from pathlib import Path
import hashlib,difflib,json
root=Path(__file__).resolve().parents[1]
p=root/'legacy/mosaic_lqmoe.py'; old=p.read_text();new=old
needle='    collapse_patience: int = 4,\n) -> core.RunResult:'
assert new.count(needle)==1
new=new.replace(needle,'    collapse_patience: int = 4,\n    extension=None,\n) -> core.RunResult:')
needle='            childF = problem.evaluate(child)[0]\n'
assert new.count(needle)==1
new=new.replace(needle,'''            extension_ticket = None
            if extension is not None:
                child, extension_ticket = extension.propose(
                    child, parent, parentF, X, F, W, search_i,
                    ideal, nadir, progress, evals, op, stagnation[search_i]
                )
                child = np.clip(child, problem.xl, problem.xu)
            childF = problem.evaluate(child)[0]
''')
needle='            else:\n                core_step = (shared_child if shared_child is not None else child) - parent'
assert new.count(needle)==1
new=new.replace(needle,'            elif extension_ticket is None:\n                core_step = (shared_child if shared_child is not None else child) - parent')
needle='            if "fixed_router" not in flags:\n                if op == 5:'
assert new.count(needle)==1
new=new.replace(needle,'''            if extension_ticket is not None:
                extension.observe(extension_ticket, childF, entered, replaced)
            if "fixed_router" not in flags and extension_ticket is None:
                if op == 5:''')
needle='            op_counts[op] += 1\n            op_rewards[op] += reward'
assert new.count(needle)==1
new=new.replace(needle,'''            if extension_ticket is None:
                op_counts[op] += 1
                op_rewards[op] += reward''')
(root/'mosaic/extended_core.py').write_text(new)
(root/'docs/extension.patch').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='legacy/mosaic_lqmoe.py',tofile='mosaic/extended_core.py')))
(root/'docs/legacy_hashes.json').write_text(json.dumps({x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in (root/'legacy').glob('*.py')},indent=2))
