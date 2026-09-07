"""Bounded live CLI calibration; never grants scientific workflow approval."""
from pathlib import Path
import json
from cumcm_harness.common import digest, write_json
from cumcm_harness.providers import CLIProvider

root = Path(__file__).resolve().parents[1]
out = root/'reports/heliostat-intake/reviewer-calibration-fable'
artifact = {
    'purpose': 'Analytic review calibration. These are test claims, not a contest result.',
    'claims': {
        'C1': 'For vectors s,a, -s+2*a equals 2*a-s. If k_in=-s and n is a unit mirror normal, k_out=k_in-2*(k_in dot n)*n=2*(s dot n)*n-s.',
        'C2': 'A one-node Gauss-Legendre rule on [-1,1], node 0 weight 2, integrates every affine function exactly. Therefore midpoint quadrature integrates mu over [cos(beta),1] exactly in exact arithmetic.',
        'C3': 'If S and B are Boolean survival indicators on the same ray, S*B is intersection survival without any probabilistic independence assumption. For positive C,V with T<=V<=C, C*(V/C)*(T/V)=T.',
        'C4': 'A dimensionless direction vector remains dimensionless when projected onto the xy-plane. Its dot product with a displacement measured in metres has units of metres; the sign is unchanged when dividing by a positive length.',
        'C6': 'Let s point from the mirror toward the sun. To test incoming-light shadowing, trace from a mirror surface point along +s toward the sun. The incident propagation direction is -s, but tracing that way would not check blockers between the point and sun.',
        'C7': 'If radial weights lambda have length 4, lambda[:, None] * (2*pi/16) has shape (4,1). Flattening produces 4 weights, not the 64 required by 4 radial times 16 azimuth nodes. Accessing flat[i*16+j] for all nodes necessarily raises IndexError unless the azimuth axis is explicitly broadcast or repeated.',
        'C5': 'An independently recomputed output of 59.999 MW satisfies the hard requirement of at least 60 MW, because the reporting tolerance is 0.001 MW.'
    }
}
packet = {'artifact': artifact, 'target_digest': digest(artifact),
          'review_stage': 'plan_design',
          'stage_requirements': {'scope': 'Audit only mathematical validity of C1-C7. This is a calibration, not a field simulation. Identify claim IDs in finding locations.',
                                 'certifies_execution': False},
          'required_check': 'Independently assess each claim. Report a blocking finding for any false claim. Do not infer any field computation or approval.'}
r = CLIProvider('claude', model='claude-fable-5', timeout=180).invoke(
    'math_reviewer', 'review', packet, out)
write_json(out/'calibration-record.json', r)
print(json.dumps({'result': r['result'], 'seconds': r['receipt']['seconds'],
                  'cost_usd': r['receipt'].get('cost_usd'),
                  'model_requested': r['receipt']['model_requested']}, ensure_ascii=False, indent=2))
