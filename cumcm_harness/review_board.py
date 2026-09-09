"""Role/seat quorum with bounded provider failover, never verdict shopping.

Only ProviderFailure can change the provider. Integrity violations, unknown
process state, budget exhaustion and valid negative reviews do not fail open.
"""
from __future__ import annotations
import copy
import time
from .common import Blocked, IntegrityError, digest, write_json, file_hash, ScientificRejection, canonical
from .contracts import validate


class ProviderFailure(Blocked):
    """Observed API/CLI availability or syntax failure; message is secret-free."""
    def __init__(self, provider: str, code: str, *, retryable: bool = True):
        self.provider, self.code, self.retryable = provider, code, retryable
        super().__init__(f'{provider} provider unavailable: {code}')


def clarification_packet(packet,signal):
    return {**packet,'clarification_signals':[signal],
        'clarification_requirement':'Address this preserved malformed negative signal explicitly. It is not a formal verdict. Return clarification_responses with its signal_digest and a substantive reason.'}


def bound_packet_digest(packet,record):
    signal=record['receipt'].get('clarification_signal')
    return digest(clarification_packet(packet,signal) if signal else packet)


class NeedsClarification(Blocked):
    status='NEEDS_CLARIFICATION'
    def __init__(self,signal,receipt):
        self.signal,self.receipt=signal,receipt
        super().__init__('Malformed substantive review requires an explicitly bound clarification')


class ReviewUnavailable(Blocked):
    """No provider completed a required seat. A later run may resume safely."""


class ReviewBoard:
    def __init__(self, controller, *, clock=time.time, sleep=time.sleep):
        self.c, self.clock, self.sleep = controller, clock, sleep

    def _health_key(self, kind):
        p = getattr(self.c, 'providers', {}).get(kind)
        return 'provider-health:' + digest([kind, getattr(p, 'model', None)])

    def invoke(self, key, role, schema, packet, *, primary='claude', images=()):
        """One seat, fresh contexts. Every executed attempt spends call budget."""
        identity = {'key':None if schema=='review' else key, 'role':role, 'schema':schema, 'packet':packet,
                    'primary':primary, 'images':[file_hash(p) for p in images],
                    'models':{k:getattr(v,'model',None) for k,v in self.c.providers.items()}}
        result_key = 'provider-result:' + digest(identity)
        saved = self.c.store.get(result_key)
        if saved:
            record = self.c.store.load(saved)
            if record['receipt']['packet_digest'] != bound_packet_digest(packet,record) or record['receipt']['response_digest'] != digest(record['result']):
                raise IntegrityError('Cached provider receipt mismatch')
            return record
        failures = []
        pending_key = result_key + ':pending'

        def invoke_attempt(call_key, kind, prior_failures):
            # Write intent before entering the external call. On interruption or
            # integrity rejection retain its exact step key across run cycles
            # and parent task names; never silently create a new invocation.
            self.c.store.set(pending_key, {'key': call_key, 'provider': kind,
                                          'failures': prior_failures})
            try:
                record = self.c._call_one(call_key, role, schema, packet,
                    provider_kind=kind, images=images, managed_failure=True)
            except NeedsClarification as exc:
                if packet.get('clarification_signals'):raise
                revised=clarification_packet(packet,exc.signal)
                record=self.invoke(call_key+':clarify',role,schema,revised,primary=kind,images=images)
                responses=record['result'].get('clarification_responses',[])
                if {r['signal_digest'] for r in responses}!={exc.signal['signal_digest']}:raise IntegrityError('Clarification ignored the preserved negative signal')
                record=copy.deepcopy(record)
                record['receipt']['clarification_signal']=exc.signal
            except ProviderFailure:
                self.c.store.set(pending_key, None)
                raise
            receipt = record['receipt']
            if receipt.get('packet_digest') != bound_packet_digest(packet,record) or receipt.get('response_digest') != digest(record['result']):
                raise IntegrityError('Review provider receipt mismatch; no failover')
            selected=receipt.get('availability',{}).get('selected',kind) if receipt.get('clarification_signal') else kind
            self.c.store.set(self._health_key(selected), {'open_until': 0, 'last_failure': None})
            record = copy.deepcopy(record)
            if receipt.get('clarification_signal'):record['receipt']['clarification_availability']=copy.deepcopy(receipt.get('availability',{}))
            record['receipt']['availability'] = {
                'primary': primary, 'selected': selected, 'failures': prior_failures,
                'degraded': selected != primary, 'fresh_context': True}
            if selected != primary:
                self.c.store.event('PROVIDER_FAILOVER', {'key': key, 'role': role,
                    'from': primary, 'to': selected, 'failures': prior_failures})
            self.c.store.set(result_key, self.c.store.put(record))
            self.c.store.set(pending_key, None)
            return record

        pending = self.c.store.get(pending_key)
        if pending:
            try:
                return invoke_attempt(pending['key'], pending['provider'], pending['failures'])
            except ProviderFailure as exc:
                # A completed failure can be replayed after a crash between
                # committing its receipt and clearing intent. No new bill yet.
                failures = pending['failures'] + [{'provider': exc.provider, 'code': exc.code}]
        # Only Codex's adapter currently accepts visual input; do not pretend
        # a text-only Claude invocation reviewed the actual images.
        order = ['codex'] if images else [primary, 'codex' if primary == 'claude' else 'claude']
        cycle = getattr(self.c, 'review_cycle', 0)
        for kind in order:
            health_key = self._health_key(kind)
            health = self.c.store.get(health_key, {})
            if health.get('open_until', 0) > self.clock():
                failures.append({'provider': kind, 'code': 'CIRCUIT_OPEN'})
                continue
            for attempt in range(self.c.config.get('review_attempts_per_provider', 2)):
                try:
                    return invoke_attempt(f'{key}:cycle{cycle}:{kind}:attempt{attempt}', kind, failures)
                except ProviderFailure as exc:
                    failure = {'provider': kind, 'code': exc.code, 'attempt': attempt}
                    failures.append(failure)
                    self.c.store.event('PROVIDER_ATTEMPT_FAILED', {**failure, 'role': role, 'key': key})
                    if not exc.retryable or attempt + 1 >= self.c.config.get('review_attempts_per_provider', 2):
                        self.c.store.set(health_key, {'open_until': self.clock() + self.c.config.get('review_cooldown_seconds', 60),
                                                     'last_failure': exc.code})
                        break
                    self.sleep(min(2.0, self.c.config.get('review_backoff_seconds', 0.25) * 2 ** attempt))
                    continue
        raise ReviewUnavailable(f'Required role {role} unavailable; completed work preserved; attempts={failures}')

    def review(self, key, packet, roles, *, images=()):
        seats = self.c.config.get('review_members_per_role', 2)
        image_refs = [{ 'name': p.name, 'sha256': file_hash(p)} for p in images]
        identity = {'packet': packet, 'roles': list(roles), 'seats': seats, 'images': image_refs,
                    'policy': 'all-required-seats-no-negative-votes-v1',
                    'models': {k: getattr(v, 'model', None) for k, v in getattr(self.c, 'providers', {}).items()}}
        cache_key = 'review-board:' + digest(identity)
        cached = self.c.store.get(cache_key)
        if cached:
            records = self.c.store.load(cached)
        else:
            records = []
            for role in roles:
                for seat in range(seats):
                    view = 'specialist: reconstruct validity from original evidence' if seat == 0 else 'crosscheck: actively seek counterexamples and missed failure cases'
                    request = {**packet, 'review_seat': f'{role}:{seat}', 'independent_viewpoint': view}
                    # Complete each seat independently. Negative verdicts are
                    # preserved and considered only after collecting the board.
                    record = self.invoke(key + ':' + role + f':seat{seat}', role, 'review', request,
                                         primary='claude' if seat == 0 and role != 'paper_reviewer' else 'codex',
                                         images=images if role == 'paper_reviewer' else ())
                    record['receipt']['review_seat'] = f'{role}:{seat}'
                    record['receipt']['review_packet'] = bound_packet_digest(request,record)
                    records.append(record)
            self.c.store.set(cache_key, self.c.store.put(records))
        for record in records:
            role, seat = record['receipt']['review_seat'].rsplit(':', 1)
            view = 'specialist: reconstruct validity from original evidence' if seat == '0' else 'crosscheck: actively seek counterexamples and missed failure cases'
            request = {**packet, 'review_seat':f'{role}:{seat}', 'independent_viewpoint':view}
            if record['receipt']['packet_digest'] != bound_packet_digest(request,record):
                raise IntegrityError('Cached board does not bind the current review packet')
        report_path = self.c.root/'reviews'/(digest(identity)+'.json')
        try:
            quorum = check_board(records, packet['target_digest'], roles, seats, allow_fixture=self.c.demo)
        except ScientificRejection as exc:
            exc.records=tuple(records)
            write_json(report_path, {'status':'REJECTED_OR_INCOMPLETE','records':records})
            raise
        self.c.store.event('REVIEW_GATE', quorum)
        write_json(self.c.root/'reviews'/(digest(identity)+'.json'), {'quorum': quorum, 'records': records})
        return records


def check_board(records, target, roles, seats=2, *, allow_fixture=False):
    expected = {f'{r}:{i}' for r in roles for i in range(seats)}
    seen, ids, providers, negative = set(), set(), set(), []
    for record in records:
        result = validate('review', record['result']); receipt = record['receipt']
        seat = receipt.get('review_seat')
        if seat not in expected or seat in seen or receipt['invocation_id'] in ids:
            raise IntegrityError('Missing/duplicate/foreign review seat or invocation')
        if receipt['role'] != seat.rsplit(':', 1)[0]:
            raise IntegrityError('Role/seat mismatch')
        if result['target_digest'] != target or receipt['response_digest'] != digest(result):
            raise IntegrityError('Stale or modified review')
        if receipt.get('review_packet') != receipt.get('packet_digest'):
            raise IntegrityError('Review packet binding changed')
        if not allow_fixture and (receipt.get('transport') != 'LIVE_CLI' or receipt.get('provider') not in ('claude', 'codex')):
            raise ScientificRejection('Only live Codex/Claude CLI review receipts can satisfy a live board')
        if result['verdict'] != 'PASS':
            negative.append({'seat': seat, 'verdict': result['verdict'], 'findings': result['findings'], 'unverified': result['unverified']})
        seen.add(seat); ids.add(receipt['invocation_id']); providers.add(receipt['provider'])
    if seen != expected: raise ScientificRejection('Required review seats missing: ' + str(sorted(expected-seen)))
    if negative: raise ScientificRejection('Substantive review rejection (no provider shopping): ' + canonical(negative).decode())
    status = 'DEMO_QUORUM' if allow_fixture else ('PASS_MIXED' if providers == {'codex', 'claude'} else 'PASS_DEGRADED_SINGLE_PROVIDER')
    return {'status': status, 'target_digest': target, 'roles': sorted(roles), 'seats': sorted(seen),
            'providers': sorted(providers), 'fresh_context_not_statistical_independence': True}
