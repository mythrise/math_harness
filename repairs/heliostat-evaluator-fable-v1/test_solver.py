#!/usr/bin/env python3
"""Test suite for heliostat field solver and evaluator.

Tests wrong answers, empty outputs, adversarial cases, and must fail incorrect solvers.
"""

import json
import tempfile
from pathlib import Path
import numpy as np
import pandas as pd
import sys
import os

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from evaluate import GeometricValidator, OpticalCalculator


def run_tests():
    """Run all test cases."""
    tests = []
    
    # Test 1: Reflection law with known angles
    try:
        s = np.array([0, 0, 1])  # Sun from above
        R = np.array([10, 0, 80])
        p = np.array([0, 0, 4])
        
        calc = OpticalCalculator()
        n, e_w, e_h = calc.compute_mirror_normal(p, R, s)
        
        # Verify reflection: v = 2(s·n)n - s
        v_expected = R - p
        v_expected = v_expected / np.linalg.norm(v_expected)
        
        v_computed = 2 * np.dot(s, n) * n - s
        v_computed = v_computed / np.linalg.norm(v_computed)
        
        error = np.linalg.norm(v_computed - v_expected)
        passed = error < 1e-6
        
        tests.append({
            "name": "reflection_law_analytic",
            "passed": passed,
            "detail": f"Reflection error {error:.2e}, expected < 1e-6"
        })
    except Exception as e:
        tests.append({"name": "reflection_law_analytic", "passed": False, "detail": str(e)})
    
    # Test 2: Sun disc projection normalization
    try:
        calc = OpticalCalculator(n_surf=2, n_sun_r=2, n_sun_chi=8)
        
        # Construct orthogonal basis
        s = np.array([0, 0, 1])
        u = np.array([1, 0, 0])
        v = np.array([0, 1, 0])
        
        # Build all ray directions
        total_cos_weight = 0.0
        for a_idx, mu_a in enumerate(calc.sun_mu):
            sqrt_a = calc.sun_sqrt_term[a_idx]
            for b_idx, chi_b in enumerate(calc.sun_chi):
                b_ab = calc.sun_b[a_idx * len(calc.sun_chi) + b_idx]
                s_ab = mu_a * s + sqrt_a * (np.cos(chi_b)*u + np.sin(chi_b)*v)
                s_ab = s_ab / np.linalg.norm(s_ab)
                total_cos_weight += b_ab * np.dot(s, s_ab)
        
        error = abs(total_cos_weight - 1.0)
        passed = error < 1e-10
        
        tests.append({
            "name": "sun_disc_projection_normalization",
            "passed": passed,
            "detail": f"Normalization error {error:.2e}, expected < 1e-10"
        })
    except Exception as e:
        tests.append({"name": "sun_disc_projection_normalization", "passed": False, "detail": str(e)})
    
    # Test 3: Two-mirror occlusion
    try:
        mirror1 = {'x_m': 0, 'y_m': 0, 'z_m': 4, 'width_m': 6, 'height_m': 6}
        mirror2 = {'x_m': 0, 'y_m': 20, 'z_m': 4, 'width_m': 6, 'height_m': 6}
        
        # Add normals (will be computed)
        s = np.array([0, 1, 0])  # Sun from north
        R = np.array([0, 0, 80])
        
        calc = OpticalCalculator()
        n1, e_w1, e_h1 = calc.compute_mirror_normal(np.array([0, 0, 4]), R, s)
        n2, e_w2, e_h2 = calc.compute_mirror_normal(np.array([0, 20, 4]), R, s)
        
        mirror1['normal'] = n1
        mirror1['e_w'] = e_w1
        mirror1['e_h'] = e_h1
        mirror2['normal'] = n2
        mirror2['e_w'] = e_w2
        mirror2['e_h'] = e_h2
        
        mirrors = [mirror1, mirror2]
        
        # Mirror 1 should be shadowed by mirror 2 when sun from north
        p1 = np.array([0, 0, 4])
        is_clear = calc.check_occlusion(p1, s, mirrors, 0, R, False)
        
        # Should be occluded
        passed = not is_clear
        
        tests.append({
            "name": "two_mirror_shadow",
            "passed": passed,
            "detail": f"Shadow detection: {'blocked' if not is_clear else 'clear (wrong)'}"
        })
    except Exception as e:
        tests.append({"name": "two_mirror_shadow", "passed": False, "detail": str(e)})
    
    # Test 4: Cylinder side vs endcap
    try:
        calc = OpticalCalculator()
        
        # Ray hitting side
        p_side = np.array([10, 0, 80])
        v_side = np.array([-1, 0, 0])  # Toward center
        hit, tau, is_side = calc.intersect_cylinder(p_side, v_side, 0, 0)
        
        passed_side = hit and is_side
        
        # Ray hitting endcap
        p_cap = np.array([0, 0, 90])
        v_cap = np.array([0, 0, -1])  # Downward
        hit, tau, is_side = calc.intersect_cylinder(p_cap, v_cap, 0, 0)
        
        passed_cap = hit and not is_side
        
        tests.append({
            "name": "cylinder_side_vs_endcap",
            "passed": passed_side and passed_cap,
            "detail": f"Side: {passed_side}, Endcap: {passed_cap}"
        })
    except Exception as e:
        tests.append({"name": "cylinder_side_vs_endcap", "passed": False, "detail": str(e)})
    
    # Test 5: Pairwise clearance equality (must fail)
    try:
        validator = GeometricValidator()
        
        # Two mirrors with distance exactly equal to required
        mirrors = pd.DataFrame([
            {'x_m': 0, 'y_m': 0, 'z_m': 4, 'width_m': 6, 'height_m': 6},
            {'x_m': 11, 'y_m': 0, 'z_m': 4, 'width_m': 6, 'height_m': 6}
        ])
        
        # Distance = 11, required = max(6,6) + 5 = 11, so EQUAL (not strictly greater)
        checks, details = validator.validate_design(mirrors, 0, 0)
        
        passed = not checks['pairwise_clearance']
        
        tests.append({
            "name": "strict_clearance_equality_fails",
            "passed": passed,
            "detail": f"Correctly rejected equal clearance: {passed}"
        })
    except Exception as e:
        tests.append({"name": "strict_clearance_equality_fails", "passed": False, "detail": str(e)})
    
    # Test 6: Tampered power value (evaluator must recompute)
    try:
        # Create fake answer with claimed high power but wrong geometry
        answer = {
            'Q1': {
                'mirrors': [
                    {'x_m': 100, 'y_m': 0, 'z_m': 4, 'width_m': 6, 'height_m': 6}
                ],
                'claimed_power': 1000.0  # Fake
            },
            'Q2': {
                'tower_x_m': 0, 'tower_y_m': 0,
                'mirrors': [
                    {'x_m': 100, 'y_m': 0, 'z_m': 4, 'width_m': 6, 'height_m': 6}
                ],
                'claimed_power': 100.0  # Fake
            },
            'Q3': {
                'tower_x_m': 0, 'tower_y_m': 0,
                'mirrors': [
                    {'x_m': 100, 'y_m': 0, 'z_m': 4, 'width_m': 6, 'height_m': 6}
                ],
                'claimed_power': 100.0  # Fake
            }
        }
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            answer_dir = tmp_path / 'answer'
            answer_dir.mkdir()
            
            with open(answer_dir / 'answer.json', 'w') as f:
                json.dump(answer, f)
            
            # Create minimal input
            input_dir = tmp_path / 'input'
            public_dir = input_dir / 'public'
            public_dir.mkdir(parents=True)
            
            # Fake reference (Q1 will fail on count)
            ref = pd.DataFrame([{'x_m': 100, 'y_m': 0}])
            ref.to_csv(public_dir / 'heliostat_coordinates.csv', index=False)
            
            output_dir = tmp_path / 'output'
            
            from evaluate import evaluate
            result = evaluate(input_dir, answer_dir, output_dir, 1, 192, 'baseline')
            
            # Should fail Q1 count, Q2/Q3 power
            passed = not result['valid']
            
            tests.append({
                "name": "tampered_power_rejected",
                "passed": passed,
                "detail": f"Correctly rejected tampered answer: {passed}"
            })
    except Exception as e:
        tests.append({"name": "tampered_power_rejected", "passed": False, "detail": str(e)})
    
    # Test 7: Empty answer
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            answer_dir = tmp_path / 'answer'
            answer_dir.mkdir()
            
            # No answer.json
            input_dir = tmp_path / 'input'
            input_dir.mkdir()
            output_dir = tmp_path / 'output'
            
            from evaluate import evaluate
            result = evaluate(input_dir, answer_dir, output_dir, 1, 192, 'baseline')
            
            passed = not result['valid'] and result['score'] == 0.0
            
            tests.append({
                "name": "empty_answer_rejected",
                "passed": passed,
                "detail": f"Correctly rejected missing answer: {passed}"
            })
    except Exception as e:
        tests.append({"name": "empty_answer_rejected", "passed": False, "detail": str(e)})
    
    # Test 8: Malformed JSON
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            answer_dir = tmp_path / 'answer'
            answer_dir.mkdir()
            
            # Write malformed JSON
            with open(answer_dir / 'answer.json', 'w') as f:
                f.write('{"Q1": incomplete')
            
            input_dir = tmp_path / 'input'
            input_dir.mkdir()
            output_dir = tmp_path / 'output'
            
            from evaluate import evaluate
            try:
                result = evaluate(input_dir, answer_dir, output_dir, 1, 192, 'baseline')
                passed = not result['valid']
            except:
                passed = True  # Exception is acceptable
            
            tests.append({
                "name": "malformed_json_rejected",
                "passed": passed,
                "detail": "Correctly handled malformed JSON"
            })
    except Exception as e:
        tests.append({"name": "malformed_json_rejected", "passed": False, "detail": str(e)})
    
    # Test 9: Distance to receiver > 1000 m
    try:
        validator = GeometricValidator()
        
        # Mirror very far from tower at (0, 0, 80)
        mirrors = pd.DataFrame([
            {'x_m': 900, 'y_m': 0, 'z_m': 4, 'width_m': 6, 'height_m': 6}
        ])
        
        checks, details = validator.validate_design(mirrors, 0, 0)
        
        passed = not checks['distance_to_receiver']
        
        tests.append({
            "name": "distance_limit_1000m",
            "passed": passed,
            "detail": f"Correctly rejected d > 1000 m: {passed}"
        })
    except Exception as e:
        tests.append({"name": "distance_limit_1000m", "passed": False, "detail": str(e)})
    
    # Test 10: Ground clearance violation
    try:
        validator = GeometricValidator()
        
        # z < h/2 + 0.001
        mirrors = pd.DataFrame([
            {'x_m': 150, 'y_m': 0, 'z_m': 2.0, 'width_m': 6, 'height_m': 6}  # z=2, h/2=3
        ])
        
        checks, details = validator.validate_design(mirrors, 0, 0)
        
        passed = not checks['ground_clearance']
        
        tests.append({
            "name": "ground_clearance_violation",
            "passed": passed,
            "detail": f"Correctly rejected ground clearance violation: {passed}"
        })
    except Exception as e:
        tests.append({"name": "ground_clearance_violation", "passed": False, "detail": str(e)})
    
    # Summarize
    all_passed = all(t['passed'] for t in tests)
    
    result = {
        "cases": tests,
        "all_passed": all_passed
    }
    
    return result


def main():
    result = run_tests()
    
    output_path = Path('tests.json')
    with open(output_path, 'w') as f:
        json.dump(result, f, indent=2)
    
    print(f"Tests complete. All passed: {result['all_passed']}")
    print(f"Results written to {output_path}")
    
    for test in result['cases']:
        status = 'PASS' if test['passed'] else 'FAIL'
        print(f"  [{status}] {test['name']}: {test['detail']}")
    
    sys.exit(0 if result['all_passed'] else 1)


if __name__ == '__main__':
    main()
