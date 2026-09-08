"""Atomic Exa attempt budgets and a shared local rate/concurrency circuit.

Remote exactly-once billing is impossible: intent without a durable response
remains UNKNOWN and requires explicit reconciliation, never lease-time guessing.
"""
from __future__ import annotations
import contextlib
import fcntl
import json
import sqlite3
import time
import uuid
from pathlib import Path
from .common import Blocked, IntegrityError, canonical, digest
from .literature import ResearchUnavailable


class ExaWait(ResearchUnavailable):
    def __init__(self, code, *, status='WAITING_RESEARCH_PROVIDER', retry_at=None):
        super().__init__(code)
        self.code=code;self.status=status;self.retry_at=retry_at


class ExaLedger:
    def __init__(self, store, policy, *, max_attempts=None):
        self.store=store;self.policy=policy
        self.maximum=min(policy['budget']['max_total_http_attempts'],max_attempts or 80)
        with store.connect() as c:
            c.executescript('''
            CREATE TABLE IF NOT EXISTS exa_requests(
                id TEXT PRIMARY KEY,identity TEXT NOT NULL,status TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,response_digest TEXT,retry_at REAL NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS exa_attempts(
                id TEXT PRIMARY KEY,request_id TEXT NOT NULL,stage TEXT NOT NULL,
                status TEXT NOT NULL,started REAL NOT NULL,receipt TEXT);
            CREATE TABLE IF NOT EXISTS exa_resources(kind TEXT NOT NULL,id TEXT NOT NULL,
                PRIMARY KEY(kind,id));
            ''')

    @contextlib.contextmanager
    def single_flight(self, key):
        folder=self.store.root/'literature/exa-locks';folder.mkdir(parents=True,exist_ok=True)
        with (folder/(key+'.lock')).open('a+') as handle:
            deadline=time.monotonic()+60
            while True:
                try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB);break
                except BlockingIOError:
                    if time.monotonic()>=deadline:raise ExaWait('EXA_SINGLE_FLIGHT_BUSY') from None
                    time.sleep(.02)
            try:yield
            finally:fcntl.flock(handle,fcntl.LOCK_UN)

    def get(self, key):
        with self.store.connect() as c:r=c.execute('SELECT * FROM exa_requests WHERE id=?',(key,)).fetchone()
        return dict(r) if r else None

    def prepare(self, key, identity):
        with self.store.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            r=c.execute('SELECT * FROM exa_requests WHERE id=?',(key,)).fetchone()
            if r:
                if r['identity']!=canonical(identity).decode():raise IntegrityError('Exa request identity collision')
                if r['status'] in ('RUNNING','UNKNOWN'):
                    raise ExaWait('EXA_UNKNOWN_INFLIGHT; inspect and use recover-exa explicitly',status='WAITING_EXA_RECONCILIATION')
                return dict(r)
            c.execute('INSERT INTO exa_requests(id,identity,status) VALUES(?,?,?)',(key,canonical(identity).decode(),'READY'))
            self.store._event(c,'EXA_REQUEST_INTENT',{'request':key,'identity_digest':digest(identity)})
        return self.get(key)

    def reserve(self, key, stage):
        if stage not in self.policy['budget']['stage_allocations']:raise IntegrityError('Unknown Exa budget stage')
        with self.store.connect() as c:
            c.execute('BEGIN IMMEDIATE');r=c.execute('SELECT * FROM exa_requests WHERE id=?',(key,)).fetchone()
            if not r or r['status'] in ('RUNNING','UNKNOWN','DONE'):raise IntegrityError('Exa request cannot reserve an attempt')
            if r['attempts']>=self.policy['http']['max_attempts_per_logical_request']:
                raise ExaWait('EXA_LOGICAL_ATTEMPT_LIMIT')
            total=c.execute('SELECT count(*) FROM exa_attempts').fetchone()[0]
            used=c.execute('SELECT count(*) FROM exa_attempts WHERE stage=?',(stage,)).fetchone()[0]
            if total>=self.maximum or used>=self.policy['budget']['stage_allocations'][stage]:
                raise ExaWait('EXA_REQUEST_BUDGET_EXHAUSTED',status='WAITING_RESEARCH_BUDGET')
            attempt=uuid.uuid4().hex
            c.execute('INSERT INTO exa_attempts VALUES(?,?,?,?,?,NULL)',(attempt,key,stage,'SENT_OR_UNKNOWN',time.time()))
            c.execute('UPDATE exa_requests SET status=?,attempts=attempts+1 WHERE id=?',('RUNNING',key))
            self.store._event(c,'EXA_HTTP_RESERVED',{'attempt':attempt,'request':key,'stage':stage,'ordinal':total+1})
            # Keep the established status projection, atomically with the attempt.
            c.execute('INSERT OR REPLACE INTO kv VALUES(?,?)',('exa_requests_reserved',str(total+1)))
        return attempt

    def finish_attempt(self, attempt, receipt, *, unknown=False, retry_at=0):
        with self.store.connect() as c:
            c.execute('BEGIN IMMEDIATE');r=c.execute('SELECT * FROM exa_attempts WHERE id=?',(attempt,)).fetchone()
            if not r or r['status']!='SENT_OR_UNKNOWN':raise IntegrityError('Exa attempt already completed or absent')
            c.execute('UPDATE exa_attempts SET status=?,receipt=? WHERE id=?',
                      ('UNKNOWN' if unknown else 'RESPONDED',canonical(receipt).decode(),attempt))
            c.execute('UPDATE exa_requests SET status=?,retry_at=? WHERE id=?',
                      ('UNKNOWN' if unknown else 'READY',retry_at,r['request_id']))
            self.store._event(c,'EXA_HTTP_OUTCOME',{'attempt':attempt,'receipt':receipt,'unknown':unknown})

    def complete(self, key, response):
        ref=self.store.put(response)
        with self.store.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            n=c.execute('UPDATE exa_requests SET status=?,response_digest=? WHERE id=? AND status=?',('DONE',ref,key,'READY')).rowcount
            if n!=1:raise IntegrityError('Cannot cache an unfinished Exa request')
            self.store._event(c,'EXA_REQUEST_DONE',{'request':key,'response_digest':ref})
        return response

    def resource(self, kind, ids, maximum):
        ids=set(ids)
        with self.store.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            old={r[0] for r in c.execute('SELECT id FROM exa_resources WHERE kind=?',(kind,))}
            if len(old|ids)>maximum:raise ExaWait('EXA_RESOURCE_LIMIT:'+kind,status='WAITING_RESEARCH_BUDGET')
            c.executemany('INSERT OR IGNORE INTO exa_resources VALUES(?,?)',[(kind,i) for i in ids])
            if ids-old:self.store._event(c,'EXA_RESOURCE_RESERVED',{'kind':kind,'ids':sorted(ids-old),'total':len(old|ids)})

    def reconcile(self, key, reason):
        if len(reason.strip())<12:raise IntegrityError('Exa reconciliation requires a concrete audit reason')
        with self.store.connect() as c:
            c.execute('BEGIN IMMEDIATE');r=c.execute('SELECT * FROM exa_requests WHERE id=?',(key,)).fetchone()
            if not r or r['status'] not in ('RUNNING','UNKNOWN'):raise IntegrityError('Only unknown Exa requests need reconciliation')
            attempts=[dict(x) for x in c.execute('SELECT * FROM exa_attempts WHERE request_id=?',(key,))]
            self.store._event(c,'EXA_EXPLICIT_RECONCILIATION',{'request':key,'old_attempts':attempts,'reason':reason,'remote_cost':'UNKNOWN_UNLESS_SEPARATELY_VERIFIED'})
            c.execute('UPDATE exa_attempts SET status=? WHERE request_id=? AND status IN (?,?)',('RECONCILED_UNKNOWN',key,'UNKNOWN','SENT_OR_UNKNOWN'))
            c.execute('UPDATE exa_requests SET status=? WHERE id=?',('READY',key))
        return [a['id'] for a in attempts]

    def summary(self):
        with self.store.connect() as c:
            rows=[dict(r) for r in c.execute('SELECT * FROM exa_attempts ORDER BY started')]
            requests=[{'id':r['id'],'status':r['status'],'attempts':r['attempts']} for r in c.execute('SELECT * FROM exa_requests')]
        receipts=[json.loads(r['receipt']) for r in rows if r['receipt']]
        costs=[r.get('cost_dollars','UNKNOWN') for r in receipts]
        return {'http_attempts_reserved':len(rows),'max_http_attempts':self.maximum,'requests':requests,
                'known_cost_dollars':sum(x for x in costs if type(x) in (int,float)),
                'unknown_cost_attempts':len(rows)-sum(type(x) in (int,float) for x in costs),
                'remote_exactly_once_billing':False}


class SharedHTTPGate:
    """Local workers share limits by credential source, never by secret key value."""
    def __init__(self, path, *, clock=time.time, sleep=time.sleep):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.clock=clock;self.sleep=sleep
        with self.connect() as c:
            c.executescript('''CREATE TABLE IF NOT EXISTS gate(id TEXT PRIMARY KEY,next_at REAL NOT NULL,failures INTEGER NOT NULL,open_until REAL NOT NULL,half_open TEXT);
            CREATE TABLE IF NOT EXISTS leases(id TEXT PRIMARY KEY,source TEXT NOT NULL,run TEXT NOT NULL,attempt TEXT,started REAL NOT NULL);''')

    def connect(self):
        c=sqlite3.connect(self.path,timeout=30);c.row_factory=sqlite3.Row
        c.execute('PRAGMA journal_mode=WAL');return c

    def acquire(self, source, run, policy):
        begun=self.clock();h=policy['http']
        while True:
            with self.connect() as c:
                c.execute('BEGIN IMMEDIATE');now=self.clock()
                c.execute('INSERT OR IGNORE INTO gate VALUES(?,0,0,0,NULL)',(source,))
                g=c.execute('SELECT * FROM gate WHERE id=?',(source,)).fetchone()
                if g['open_until']>now:raise ExaWait('EXA_CIRCUIT_OPEN',retry_at=g['open_until'])
                if g['half_open']:raise ExaWait('EXA_CIRCUIT_HALF_OPEN_BUSY')
                count=c.execute('SELECT count(*) FROM leases WHERE source=?',(source,)).fetchone()[0]
                if count<h['max_concurrent_requests']:
                    lease=uuid.uuid4().hex
                    slot=max(now,g['next_at']);delay=slot-now
                    if delay>60:raise ExaWait('EXA_SHARED_RATE_WAIT',retry_at=slot)
                    c.execute('INSERT INTO leases VALUES(?,?,?,NULL,?)',(lease,source,run,now))
                    c.execute('UPDATE gate SET next_at=?,half_open=? WHERE id=?',
                              (slot+1/h['soft_requests_per_second'],lease if g['open_until'] else None,source))
                    break
            if self.clock()-begun>=60:raise ExaWait('EXA_SHARED_CONCURRENCY_BUSY; reconcile stale local requests')
            self.sleep(.05)
        if delay:
            try:self.sleep(delay)
            except BaseException:
                self.release(lease,policy,outcome='cancel')
                raise
        return lease

    def bind(self, lease, attempt):
        with self.connect() as c:c.execute('UPDATE leases SET attempt=? WHERE id=?',(attempt,lease))

    def release(self, lease, policy, *, outcome='success'):
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE');r=c.execute('SELECT * FROM leases WHERE id=?',(lease,)).fetchone()
            if not r:return
            g=c.execute('SELECT * FROM gate WHERE id=?',(r['source'],)).fetchone()
            fail=g['failures']+1 if outcome=='transient' else 0 if outcome=='success' else g['failures']
            opened=g['open_until']
            if outcome=='transient' and (fail>=policy['http']['circuit_breaker_consecutive_transient_failures'] or g['half_open']==lease):
                opened=self.clock()+policy['http']['circuit_breaker_cooldown_seconds']
            elif outcome=='success':opened=0
            half=None if g['half_open']==lease else g['half_open']
            c.execute('UPDATE gate SET failures=?,open_until=?,half_open=? WHERE id=?',(fail,opened,half,r['source']))
            c.execute('DELETE FROM leases WHERE id=?',(lease,))

    def reconcile(self, run, attempts):
        # Called only after explicit external-state reconciliation by the CLI.
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            for attempt in attempts:
                ids=[r[0] for r in c.execute('SELECT id FROM leases WHERE run=? AND attempt=?',(run,attempt))]
                for lease in ids:
                    c.execute('UPDATE gate SET half_open=NULL WHERE half_open=?',(lease,))
                    c.execute('DELETE FROM leases WHERE id=?',(lease,))
