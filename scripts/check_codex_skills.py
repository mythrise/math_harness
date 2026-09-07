"""Ask the local Codex app server to discover project skills; no model call."""
import json
from pathlib import Path
import queue
import subprocess
import threading
import time

root = Path(__file__).resolve().parents[1]
report = root / 'reports/local-deployment'
report.mkdir(parents=True, exist_ok=True)
messages = queue.Queue()

with (report / 'codex-discovery.stderr.log').open('w') as stderr:
    process = subprocess.Popen(
        ['codex', 'app-server', '--stdio'], cwd=root,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr, text=True,
    )

    def reader():
        for line in process.stdout:
            try:
                messages.put(json.loads(line))
            except json.JSONDecodeError:
                pass
        messages.put({'server_exited': True})

    threading.Thread(target=reader, daemon=True).start()

    def request(identifier, method, params):
        process.stdin.write(json.dumps({'id': identifier, 'method': method, 'params': params}) + '\n')
        process.stdin.flush()
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            message = messages.get(timeout=max(.1, deadline - time.monotonic()))
            if message.get('server_exited'):
                raise RuntimeError('Codex app server exited; inspect codex-discovery.stderr.log')
            if message.get('id') == identifier:
                if 'error' in message:
                    raise RuntimeError(message['error'])
                return message['result']
        raise TimeoutError(method)

    try:
        request(1, 'initialize', {'clientInfo': {'name': 'cumcm_deployment_check', 'version': '0.1.0'}})
        process.stdin.write(json.dumps({'method': 'initialized'}) + '\n')
        process.stdin.flush()
        result = request(2, 'skills/list', {'cwds': [str(root)], 'forceReload': True})
        selected = []
        errors = []
        for item in result.get('data', []):
            errors.extend(item.get('errors', []))
            selected.extend(skill for skill in item.get('skills', [])
                            if str(skill.get('path', '')).startswith(str(root / '.agents/skills') + '/'))
        expected = {p.parent.name for p in (root / '.agents/skills').glob('*/SKILL.md')}
        passed = {s['name'] for s in selected} == expected and len(expected) == 8 and all(s.get('enabled', True) for s in selected)
        record = {'status': 'PASS' if passed else 'FAIL', 'project_skills': selected,
                  'errors': errors, 'model_calls': 'NOT_RUN'}
        (report / 'codex-skills-discovery.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps({'status': record['status'], 'count': len(selected),
                          'skills': [s['name'] for s in selected], 'errors': errors}, ensure_ascii=False))
        if not passed:
            raise SystemExit(1)
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
