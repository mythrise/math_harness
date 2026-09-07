"""SQLite authority + CAS artifacts. Detects accidental/stale tampering, not a
malicious administrator rewriting the entire database and all external anchors.
"""
from __future__ import annotations
import contextlib, json, os, sqlite3, time
from pathlib import Path
from typing import Any, Callable
from .common import *

class Store:
    def __init__(self, root: Path):
        self.root=Path(root).resolve();self.root.mkdir(parents=True,exist_ok=True)
        self.db=self.root/'control.sqlite3'
        with self.connect() as c:
            c.executescript('''
            CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL,
                prev TEXT NOT NULL, hash TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS steps(key TEXT PRIMARY KEY,input_digest TEXT NOT NULL,status TEXT NOT NULL,
                result TEXT,error TEXT);
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,status TEXT NOT NULL,intent TEXT NOT NULL,
                owner TEXT,receipt TEXT);
            CREATE TABLE IF NOT EXISTS grants(token TEXT PRIMARY KEY,job TEXT NOT NULL,used INTEGER NOT NULL);
            ''')
    def connect(self):
        c=sqlite3.connect(self.db,timeout=30);c.row_factory=sqlite3.Row
        c.execute('PRAGMA journal_mode=WAL'); c.execute('PRAGMA synchronous=FULL')
        return c
    def _event(self,c,kind,payload):
        r=c.execute('SELECT seq,hash FROM events ORDER BY seq DESC LIMIT 1').fetchone()
        seq=r['seq']+1 if r else 1; prev=r['hash'] if r else '0'*64
        body={'seq':seq,'kind':kind,'payload':payload,'prev':prev};h=digest(body)
        c.execute('INSERT INTO events VALUES(?,?,?,?,?)',(seq,kind,canonical(payload).decode(),prev,h))
        return h
    def event(self,kind,payload):
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE');return self._event(c,kind,payload)
    def events(self):
        with self.connect() as c:return [dict(x) for x in c.execute('SELECT * FROM events ORDER BY seq')]
    def audit(self):
        prev='0'*64
        for i,r in enumerate(self.events(),1):
            p=json.loads(r['payload']); expected=digest({'seq':i,'kind':r['kind'],'payload':p,'prev':prev})
            if r['seq']!=i or r['prev']!=prev or r['hash']!=expected:raise IntegrityError(f'Broken ledger at {i}')
            prev=expected
        for p in (self.root/'objects').glob('*.json') if (self.root/'objects').exists() else []:
            if digest(read_json(p))!=p.stem:raise IntegrityError(f'Corrupt object {p.stem}')
        return {'events':len(self.events()),'root_hash':prev,'integrity':'PASS','authority':'LOCAL_SQLITE'}
    def get(self,key,default=None):
        with self.connect() as c:r=c.execute('SELECT value FROM kv WHERE key=?',(key,)).fetchone()
        return json.loads(r['value']) if r else default
    def set(self,key,value):
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute('INSERT OR REPLACE INTO kv VALUES(?,?)',(key,canonical(value).decode()))
            self._event(c,'STATE',{'key':key,'value':value})
    def put(self,value):
        h=digest(value);p=self.root/'objects'/f'{h}.json'
        if p.exists():
            if read_json(p)!=value:raise IntegrityError('CAS collision/corruption')
        else:write_json(p,value)
        return h
    def load(self,h):
        if not isinstance(h,str) or not __import__('re').fullmatch('[0-9a-f]{64}',h):raise IntegrityError('Invalid object digest')
        v=read_json(self.root/'objects'/f'{h}.json')
        if digest(v)!=h:raise IntegrityError('CAS digest mismatch')
        return v
    def step(self,key,inputs,fn:Callable[[],Any]):
        h=digest(inputs)
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE');r=c.execute('SELECT * FROM steps WHERE key=?',(key,)).fetchone()
            if r:
                if r['input_digest']!=h:raise IntegrityError(f'Stale step {key}; create a new version')
                if r['status']=='DONE':return self.load(r['result'])
                raise Blocked(f'{key} is {r["status"]}; inspect then use recover-step explicitly (billing/external effects may have occurred)')
            c.execute('INSERT INTO steps VALUES(?,?,?,NULL,NULL)',(key,h,'RUNNING'));self._event(c,'STEP_START',{'key':key,'input_digest':h})
        try:
            value=fn();out=self.put(value)
            with self.connect() as c:
                c.execute('BEGIN IMMEDIATE');c.execute('UPDATE steps SET status=?,result=? WHERE key=?',('DONE',out,key))
                self._event(c,'STEP_DONE',{'key':key,'result_digest':out})
            return value
        except Exception as e:
            with self.connect() as c:
                c.execute('BEGIN IMMEDIATE');c.execute('UPDATE steps SET status=?,error=? WHERE key=?',('FAILED',f'{type(e).__name__}: {e}',key))
                self._event(c,'STEP_FAILED',{'key':key,'error':f'{type(e).__name__}: {e}'})
            raise
    def recover_step(self,key,reason):
        if len(reason.strip())<12:raise IntegrityError('Recovery requires an audit reason')
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE');r=c.execute('SELECT * FROM steps WHERE key=?',(key,)).fetchone()
            if not r or r['status']=='DONE':raise IntegrityError('Only failed/unknown steps may be explicitly retried')
            self._event(c,'STEP_RECOVERY',{'old':dict(r),'reason':reason})
            c.execute('DELETE FROM steps WHERE key=?',(key,))
    def recover_job(self,job_id,reason):
        """Explicit operator reconciliation. Preserve old attempt, never overwrite it.
        Caller must first stop/reconcile any external Docker process for this job.
        """
        if len(reason.strip())<12:raise IntegrityError('Recovery requires an audit reason')
        if not __import__('re').fullmatch('[0-9a-f]{64}',job_id):raise IntegrityError('Invalid job id')
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE');r=c.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone()
            if not r or r['status']=='DONE':raise IntegrityError('Only unfinished jobs may be reconciled')
            original=self.root/'jobs'/job_id
            dest=self.root/'recovery'/f'{job_id}-{time.time_ns()}'
            if original.exists():dest.parent.mkdir(parents=True,exist_ok=True);os.replace(original,dest)
            self._event(c,'JOB_RECOVERY',{'old':dict(r),'reason':reason,'preserved_attempt':str(dest.relative_to(self.root))})
            c.execute('DELETE FROM grants WHERE job=?',(job_id,));c.execute('DELETE FROM jobs WHERE id=?',(job_id,))
    def publish_bundle(self,bundle):
        from .contracts import validate
        validate('bundle',bundle);h=digest(bundle);folder=self.root/'code'/h
        expected={f['path']:__import__('hashlib').sha256(f['content'].encode()).hexdigest() for f in bundle['files']}
        # Per-bundle OS lock covers the first publication, not only job claiming.
        # Parallel cells can otherwise race through a shared stage directory.
        import fcntl
        locks=self.root/'bundle-locks';locks.mkdir(exist_ok=True)
        with (locks/h).open('a+') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            try:
                if folder.exists():verify_tree(folder,expected);return folder
                tmp=self.root/'code'/('stage-'+h);tmp.mkdir(parents=True,exist_ok=True)
                if list(tmp.iterdir()):raise Blocked('Interrupted bundle staging; inspect/remove stage directory')
                for f in bundle['files']:atomic_write(under(tmp,f['path']),f['content'])
                verify_tree(tmp,expected);os.replace(tmp,folder)
                return folder
            finally:fcntl.flock(lock,fcntl.LOCK_UN)
    def grant(self,job_id,intent):
        token=__import__('secrets').token_hex(24)
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            r=c.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone()
            if r:
                if r['intent']!=canonical(intent).decode():raise IntegrityError('Job id collision')
                raise Blocked(f'Existing job {job_id}: {r["status"]}')
            c.execute('INSERT INTO jobs VALUES(?,?,?,NULL,NULL)',(job_id,'QUEUED',canonical(intent).decode()))
            c.execute('INSERT INTO grants VALUES(?,?,0)',(token,job_id));self._event(c,'GRANT',{'job':job_id,'intent':digest(intent)})
        return token
    def consume(self,token,job_id,owner='operator'):
        if owner!='operator':raise IntegrityError('Only operator may launch experiments')
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE');r=c.execute('SELECT * FROM grants WHERE token=?',(token,)).fetchone()
            if not r or r['used'] or r['job']!=job_id:raise IntegrityError('Invalid, reused or wrong-scope grant')
            changed=c.execute('UPDATE jobs SET status=?,owner=? WHERE id=? AND status=?',('RUNNING',owner,job_id,'QUEUED')).rowcount
            if changed!=1:raise IntegrityError('Job already claimed')
            c.execute('UPDATE grants SET used=1 WHERE token=?',(token,));self._event(c,'JOB_START',{'job':job_id,'owner':owner})
    def fail_job(self,job_id,error):
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            n=c.execute('UPDATE jobs SET status=?,receipt=? WHERE id=? AND status=?',('FAILED',canonical({'error':error}).decode(),job_id,'RUNNING')).rowcount
            if n:self._event(c,'JOB_FAILED',{'job':job_id,'error':error})
    def finish_job(self,job_id,receipt):
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            n=c.execute('UPDATE jobs SET status=?,receipt=? WHERE id=? AND status=?',('DONE',canonical(receipt).decode(),job_id,'RUNNING')).rowcount
            if n!=1:raise IntegrityError('Cannot complete an unowned/nonrunning job')
            self._event(c,'JOB_DONE',{'job':job_id,'receipt':receipt})
    def job(self,job_id):
        with self.connect() as c:r=c.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone()
        return dict(r) if r else None
    def memory(self,role,record):
        # Separate physical DB and bounded projection for each role. Not LLM chain of thought.
        name=''.join(x for x in role if x.isalnum() or x=='_')+'-'+digest(role)[:8]
        mem=Store(self.root/'agents'/name);h=mem.event('PHASE_RECEIPT',record)
        atomic_write(mem.root/'FOCUS.md',f'# {role}\n\nReceipt: {h}\n\n'+json.dumps(record,ensure_ascii=False,indent=2)[-12000:]+'\n')

@contextlib.contextmanager
def controller_lock(root:Path):
    """OS lock released on process death. Linux/macOS implementation; Windows uses WSL."""
    import fcntl
    root.mkdir(parents=True,exist_ok=True)
    with (root/'.controller.lock').open('a+') as f:
        try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as e:raise Blocked('Another controller owns this workspace') from e
        try:yield
        finally:fcntl.flock(f,fcntl.LOCK_UN)
