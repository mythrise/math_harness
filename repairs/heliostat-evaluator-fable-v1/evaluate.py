#!/usr/bin/env python3
"""Independent evaluator for heliostat field optimization (CUMCM 2023A).

Recomputes all objectives and constraints from answer artifacts.
Does not trust solver-reported scores.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd


class GeometricValidator:
    """Validates geometric constraints without computing optics."""
    
    def __init__(self, field_radius: float = 350.0, tower_radius: float = 100.0):
        self.field_radius = field_radius
        self.tower_radius = tower_radius
    
    def validate_design(self, mirrors: pd.DataFrame, tower_x: float, tower_y: float) -> Dict[str, Any]:
        """Check all geometric constraints."""
        checks = {
            "finite_values": True,
            "dimension_bounds": True,
            "installation_height_valid": True,
            "field_boundary": True,
            "tower_exclusion": True,
            "pairwise_clearance": True,
            "ground_clearance": True,
            "distance_to_receiver": True
        }
        details = {}
        
        # Finite check
        if not np.all(np.isfinite(mirrors[['width_m', 'height_m', 'x_m', 'y_m', 'z_m']].values)):
            checks["finite_values"] = False
            details["finite_values"] = "Non-finite values in mirror parameters"
            return checks, details
        
        # Dimension bounds: 2 <= h <= w <= 8, 2 <= z <= 6
        w = mirrors['width_m'].values
        h = mirrors['height_m'].values
        z = mirrors['z_m'].values
        
        if np.any(h < 2) or np.any(h > 8) or np.any(w < 2) or np.any(w > 8) or np.any(h > w):
            checks["dimension_bounds"] = False
            details["dimension_bounds"] = f"Dimension violations: h in [{h.min():.3f}, {h.max():.3f}], w in [{w.min():.3f}, {w.max():.3f}]"
        
        if np.any(z < 2) or np.any(z > 6):
            checks["installation_height_valid"] = False
            details["installation_height_valid"] = f"Installation height z in [{z.min():.3f}, {z.max():.3f}] violates [2, 6]"
        
        # Ground clearance: z >= h/2 + 0.001 (full-pose sufficient condition)
        if np.any(z < h/2 + 0.001):
            checks["ground_clearance"] = False
            min_margin = (z - h/2).min()
            details["ground_clearance"] = f"Minimum z - h/2 = {min_margin:.6f} < 0.001"
        
        # Field boundary
        x = mirrors['x_m'].values
        y = mirrors['y_m'].values
        radii = np.sqrt(x**2 + y**2)
        
        # Conservative: center + half-diagonal <= 350
        half_diag = np.sqrt(w**2 + h**2) / 2
        max_extent = radii + half_diag
        if np.any(max_extent > self.field_radius):
            checks["field_boundary"] = False
            details["field_boundary"] = f"Max extent {max_extent.max():.3f} > {self.field_radius}"
        
        # Tower exclusion: center - half-diagonal >= 100
        dist_to_tower = np.sqrt((x - tower_x)**2 + (y - tower_y)**2)
        min_extent = dist_to_tower - half_diag
        if np.any(min_extent < self.tower_radius):
            checks["tower_exclusion"] = False
            details["tower_exclusion"] = f"Min extent from tower {min_extent.min():.3f} < {self.tower_radius}"
        
        # Distance to receiver center for attenuation validity (d <= 1000 m)
        R = np.array([tower_x, tower_y, 80.0])
        p = np.column_stack([x, y, z])
        d_HR = np.linalg.norm(p - R, axis=1)
        if np.any(d_HR > 1000.0):
            checks["distance_to_receiver"] = False
            details["distance_to_receiver"] = f"Max distance {d_HR.max():.3f} > 1000 m"
        
        # Pairwise clearance: STRICT > max(w_i, w_j) + 5
        N = len(mirrors)
        if N > 1:
            violations = 0
            for i in range(N):
                for j in range(i+1, N):
                    dx = x[i] - x[j]
                    dy = y[i] - y[j]
                    horiz_dist = np.sqrt(dx**2 + dy**2)
                    required = max(w[i], w[j]) + 5.0
                    if horiz_dist <= required:  # Must be STRICTLY greater
                        violations += 1
                        if violations <= 3:  # Report first few
                            if "pairwise_clearance" not in details:
                                details["pairwise_clearance"] = []
                            details["pairwise_clearance"].append(
                                f"Mirrors {i+1},{j+1}: dist={horiz_dist:.6f} <= required={required:.6f}"
                            )
            if violations > 0:
                checks["pairwise_clearance"] = False
                if "pairwise_clearance" not in details:
                    details["pairwise_clearance"] = f"{violations} violations"
                else:
                    details["pairwise_clearance"] = f"{violations} violations: " + "; ".join(details["pairwise_clearance"])
        
        return checks, details


class OpticalCalculator:
    """Computes optical performance with finite sun and geometric occlusion."""
    
    def __init__(self, latitude_deg: float = 39.4, altitude_km: float = 3.0,
                 beta_rad: float = 0.00465, n_surf: int = 4, n_sun_r: int = 4, n_sun_chi: int = 16):
        self.phi = np.deg2rad(latitude_deg)
        self.H_alt = altitude_km
        self.beta = beta_rad
        self.epsilon = 2 * np.sin(beta_rad / 2)**2
        
        # Atmospheric model coefficients
        a = 0.4237 - 0.00821 * (6 - self.H_alt)**2
        b = 0.5055 + 0.00595 * (6.5 - self.H_alt)**2
        c = 0.2711 + 0.01858 * (2.5 - self.H_alt)**2
        self.atm_a, self.atm_b, self.atm_c = a, b, c
        self.G0 = 1.366  # kW/m²
        
        # Surface quadrature (Gauss-Legendre)
        from numpy.polynomial.legendre import leggauss
        nodes_1d, weights_1d = leggauss(n_surf)
        # Map [-1,1] to [-0.5, 0.5]
        self.surf_xi = nodes_1d / 2
        self.surf_zeta = nodes_1d / 2
        self.surf_w = weights_1d / 2  # Weight adjustment
        
        # Sun disc quadrature
        nodes_r, weights_r = leggauss(n_sun_r)
        x_a = self.epsilon * (1 + nodes_r) / 2
        mu_a = 1 - x_a
        lambda_a = self.epsilon * weights_r / 2
        
        chi_b = np.linspace(0, 2*np.pi, n_sun_chi, endpoint=False)
        
        # Build all ray directions
        self.sun_mu = mu_a
        self.sun_sqrt_term = np.sqrt(x_a * (2 - x_a))
        self.sun_chi = chi_b
        # Every radial node has n_sun_chi azimuth nodes with equal azimuth weight.
        self.sun_weights = np.broadcast_to(lambda_a[:, None] * (2*np.pi / n_sun_chi),
                                           (n_sun_r, n_sun_chi)).copy()
        
        Z = np.pi * self.epsilon * (2 - self.epsilon)
        self.sun_b = self.sun_weights.flatten() / Z
        
        # Verification: sum(b * cos(theta)) should equal 1
        # We'll verify this per mirror-sun pair
        
    def compute_sun_direction(self, month: int, day: int, ST_hour: float) -> Tuple[np.ndarray, float]:
        """Compute sun direction vector (pointing toward sun) and DNI.
        
        Returns:
            s: unit vector (3,) pointing from mirror to sun
            DNI: direct normal irradiance in kW/m²
        """
        from datetime import date
        D = (date(2023, month, day) - date(2023, 3, 21)).days
        
        delta = np.arcsin(np.sin(2*np.pi*D/365) * np.sin(np.deg2rad(23.45)))
        omega = np.pi * (ST_hour - 12) / 12
        
        s_x = -np.cos(delta) * np.sin(omega)
        s_y = np.cos(self.phi) * np.sin(delta) - np.sin(self.phi) * np.cos(delta) * np.cos(omega)
        s_z = np.sin(self.phi) * np.sin(delta) + np.cos(self.phi) * np.cos(delta) * np.cos(omega)
        
        s = np.array([s_x, s_y, s_z])
        s = s / np.linalg.norm(s)
        
        if s_z <= 0:
            return s, 0.0
        
        DNI = self.G0 * (self.atm_a + self.atm_b * np.exp(-self.atm_c / s_z))
        return s, DNI
    
    def compute_mirror_normal(self, p_i: np.ndarray, R: np.ndarray, s: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Compute mirror normal using center-aiming construction.
        
        Returns:
            n: unit normal (3,)
            e_w: horizontal width unit vector (3,)
            e_h: height unit vector (3,)
        """
        r_vec = R - p_i
        r = r_vec / np.linalg.norm(r_vec)
        
        # n = (s + r) / ||s + r||
        n_unnorm = s + r
        n = n_unnorm / np.linalg.norm(n_unnorm)
        
        # e_w horizontal: (-n_y, n_x, 0) normalized, or (1,0,0) if degenerate
        if abs(n[0]) < 1e-10 and abs(n[1]) < 1e-10:
            e_w = np.array([1.0, 0.0, 0.0])
        else:
            e_w = np.array([-n[1], n[0], 0.0])
            e_w = e_w / np.linalg.norm(e_w)
        
        e_h = np.cross(n, e_w)
        return n, e_w, e_h
    
    def intersect_cylinder(self, p: np.ndarray, v: np.ndarray, t_x: float, t_y: float) -> Tuple[bool, float, bool]:
        """Test ray-cylinder intersection.
        
        Returns:
            hit: whether receiver is hit
            tau: path parameter (if hit)
            is_side: True if side hit, False if endcap
        """
        q = p[:2] - np.array([t_x, t_y])
        v_xy = v[:2]
        
        A_v = np.dot(v_xy, v_xy)
        B_v = 2 * np.dot(q, v_xy)
        C_v = np.dot(q, q) - 3.5**2
        
        # Collect every surface before selecting the earliest contact. A cap
        # can occlude a later side hit; its incident direction is not reversed.
        contacts = []
        if A_v > 1e-16:
            disc = B_v**2 - 4*A_v*C_v
            if disc >= 0:
                sqrt_disc = np.sqrt(disc)
                tau1 = (-B_v - sqrt_disc) / (2*A_v)
                tau2 = (-B_v + sqrt_disc) / (2*A_v)
                
                for tau_side in [tau1, tau2]:
                    if tau_side > 1e-9:
                        z_hit = p[2] + tau_side * v[2]
                        if 76 <= z_hit <= 84:
                            # Check if truly inward
                            q_hit = q + tau_side * v_xy
                            n_cyl = np.array([q_hit[0]/3.5, q_hit[1]/3.5, 0.0])
                            if np.dot(n_cyl, v) < 0:  # Inward
                                contacts.append((tau_side, True))
        
        # Endcap intersection
        if abs(v[2]) > 1e-16:
            for z_cap in [76.0, 84.0]:
                tau_cap = (z_cap - p[2]) / v[2]
                if tau_cap > 1e-9:
                    q_cap = q + tau_cap * v_xy
                    if np.dot(q_cap, q_cap) <= 3.5**2:
                        contacts.append((tau_cap, False))
        if not contacts:
            return False, 0.0, False
        tau_min = min(t for t, _ in contacts)
        tie = 1e-12 * max(1.0, abs(tau_min))
        nearest = [c for c in contacts if c[0] <= tau_min + tie]
        # Shared rim: the opaque cap wins, as specified by the model contract.
        tau, is_side = min(nearest, key=lambda c: (c[1], c[0]))
        return True, tau, is_side
    
    def check_occlusion(self, p: np.ndarray, direction: np.ndarray, mirrors_data: List[Dict],
                       self_idx: int, receiver_pos: np.ndarray, check_to_receiver: bool = False,
                       max_tau: float = None) -> bool:
        """Check if ray from p in direction hits other mirrors.
        
        Returns:
            True if path is clear (not occluded)
        """
        if max_tau is None:
            max_tau = 1e6  # Large value
        
        for j, m in enumerate(mirrors_data):
            if j == self_idx:
                continue
            
            p_j = np.array([m['x_m'], m['y_m'], m['z_m']])
            n_j = m['normal']
            e_w_j = m['e_w']
            e_h_j = m['e_h']
            w_j = m['width_m']
            h_j = m['height_m']
            
            denom = np.dot(direction, n_j)
            if abs(denom) < 1e-16:
                continue
            
            tau = np.dot(p_j - p, n_j) / denom
            if tau <= 1e-9 or tau >= max_tau:
                continue
            
            p_hit = p + tau * direction
            offset = p_hit - p_j
            
            xi = np.dot(offset, e_w_j)
            zeta = np.dot(offset, e_h_j)
            
            if abs(xi) <= w_j/2 and abs(zeta) <= h_j/2:
                return False  # Occluded
        
        return True  # Clear
    
    def compute_mirror_efficiency(self, mirror: Dict, R: np.ndarray, s: np.ndarray,
                                 all_mirrors: List[Dict], mirror_idx: int) -> Dict[str, float]:
        """Compute efficiency components for one mirror at one time instant."""
        p_i = np.array([mirror['x_m'], mirror['y_m'], mirror['z_m']])
        w_i = mirror['width_m']
        h_i = mirror['height_m']
        
        n, e_w, e_h = self.compute_mirror_normal(p_i, R, s)
        mirror['normal'] = n
        mirror['e_w'] = e_w
        mirror['e_h'] = e_h
        
        d_i = np.linalg.norm(R - p_i)
        eta_at = 0.99321 - 0.0001176*d_i + 1.97e-8*d_i**2
        
        # Build sun ray directions in mirror frame
        # Construct orthogonal basis perpendicular to s
        if abs(s[0]) < 0.9:
            u = np.cross(s, np.array([1, 0, 0]))
        else:
            u = np.cross(s, np.array([0, 1, 0]))
        u = u / np.linalg.norm(u)
        v = np.cross(s, u)
        
        C_i_sum = 0.0
        V_i_sum = 0.0
        T_i_sum = 0.0
        
        # Loop over surface elements and sun rays
        for l_xi, w_xi in enumerate(self.surf_w):
            for l_zeta, w_zeta in enumerate(self.surf_w):
                a_l = w_xi * w_zeta
                
                xi_l = self.surf_xi[l_xi]
                zeta_l = self.surf_zeta[l_zeta]
                p_il = p_i + w_i * xi_l * e_w + h_i * zeta_l * e_h
                
                for a_idx, mu_a in enumerate(self.sun_mu):
                    sqrt_a = self.sun_sqrt_term[a_idx]
                    for b_idx, chi_b in enumerate(self.sun_chi):
                        b_ab = self.sun_b[a_idx * len(self.sun_chi) + b_idx]
                        q_lab = a_l * b_ab
                        
                        # Sun ray direction
                        s_ab = mu_a * s + sqrt_a * (np.cos(chi_b)*u + np.sin(chi_b)*v)
                        s_ab = s_ab / np.linalg.norm(s_ab)
                        
                        c_ij = max(0, np.dot(n, s_ab))
                        
                        # s_ab points TO the sun. Incident propagation is -s_ab;
                        # its backward path from the surface is therefore +s_ab.
                        receiver_shadow = self.intersect_cylinder(p_il, s_ab, R[0], R[1])[0]
                        S_lj = int(not receiver_shadow and self.check_occlusion(p_il, s_ab, all_mirrors, mirror_idx, R))
                        
                        # Reflected direction
                        v_ij = 2 * np.dot(s_ab, n) * n - s_ab
                        
                        # Check receiver interception
                        hit, tau_recv, is_side = self.intersect_cylinder(p_il, v_ij, R[0], R[1])
                        
                        H_lj = 1 if (hit and is_side) else 0
                        
                        # Blocking check: trace reflection path to receiver
                        if hit:
                            B_lj = 1 if self.check_occlusion(p_il, v_ij, all_mirrors, mirror_idx, R, True, tau_recv) else 0
                        else:
                            B_lj = 1 if self.check_occlusion(p_il, v_ij, all_mirrors, mirror_idx, R, True, np.inf) else 0
                        
                        U_lj = S_lj * B_lj
                        
                        C_i_sum += q_lab * c_ij
                        V_i_sum += q_lab * c_ij * U_lj
                        T_i_sum += q_lab * c_ij * U_lj * H_lj
        
        # Normalize
        if C_i_sum > 1e-12:
            eta_cos = C_i_sum
            eta_sb = V_i_sum / C_i_sum
            eta_trunc = T_i_sum / V_i_sum if V_i_sum > 1e-12 else 0.0
        else:
            eta_cos = 0.0
            eta_sb = 0.0
            eta_trunc = 0.0
        
        eta_total = 0.92 * eta_at * T_i_sum
        
        return {
            'eta_cos': eta_cos,
            'eta_sb': eta_sb,
            'eta_trunc': eta_trunc,
            'eta_at': eta_at,
            'eta_total': eta_total,
            'd_HR': d_i
        }
    
    def compute_field_power(self, mirrors: pd.DataFrame, tower_x: float, tower_y: float,
                           time_points: List[Tuple[int, int, float]]) -> Dict[str, Any]:
        """Compute field power over all time points."""
        R = np.array([tower_x, tower_y, 80.0])
        
        # Prepare mirror list
        all_mirrors = []
        for _, row in mirrors.iterrows():
            all_mirrors.append({
                'x_m': row['x_m'],
                'y_m': row['y_m'],
                'z_m': row['z_m'],
                'width_m': row['width_m'],
                'height_m': row['height_m']
            })
        
        N = len(all_mirrors)
        n_times = len(time_points)
        
        # Storage
        eta_cos_array = np.zeros((N, n_times))
        eta_sb_array = np.zeros((N, n_times))
        eta_trunc_array = np.zeros((N, n_times))
        eta_at_array = np.zeros((N, n_times))
        eta_total_array = np.zeros((N, n_times))
        power_mirror_time = np.zeros((N, n_times))
        DNI_array = np.zeros(n_times)
        
        for t_idx, (month, day, ST) in enumerate(time_points):
            s, DNI = self.compute_sun_direction(month, day, ST)
            DNI_array[t_idx] = DNI
            
            if DNI < 1e-6:
                continue
            # All possible blockers must have the CURRENT instant's orientation
            # before tracing any ray. Sequential updates leave missing/stale axes.
            for mirror in all_mirrors:
                p = np.array([mirror['x_m'], mirror['y_m'], mirror['z_m']])
                mirror['normal'], mirror['e_w'], mirror['e_h'] = self.compute_mirror_normal(p, R, s)
            for i in range(N):
                eff = self.compute_mirror_efficiency(all_mirrors[i], R, s, all_mirrors, i)
                eta_cos_array[i, t_idx] = eff['eta_cos']
                eta_sb_array[i, t_idx] = eff['eta_sb']
                eta_trunc_array[i, t_idx] = eff['eta_trunc']
                eta_at_array[i, t_idx] = eff['eta_at']
                eta_total_array[i, t_idx] = eff['eta_total']
                
                A_i = all_mirrors[i]['width_m'] * all_mirrors[i]['height_m']
                power_mirror_time[i, t_idx] = DNI * A_i * eff['eta_total']  # kW
        
        # Aggregate
        A_total = mirrors['width_m'].values * mirrors['height_m'].values
        power_time = power_mirror_time.sum(axis=0) / 1000  # MW
        
        # Monthly averages (5 points per month)
        monthly_power = np.zeros(12)
        monthly_eta_cos = np.zeros(12)
        monthly_eta_sb = np.zeros(12)
        monthly_eta_trunc = np.zeros(12)
        
        for m in range(12):
            indices = [i for i, point in enumerate(time_points) if point[0] == m+1]
            if not indices:
                monthly_power[m] = np.nan
                monthly_eta_cos[m] = monthly_eta_sb[m] = monthly_eta_trunc[m] = np.nan
                continue
            monthly_power[m] = power_time[indices].mean()
            
            # Area-weighted
            monthly_eta_cos[m] = (eta_cos_array[:, indices].mean(axis=1) * A_total).sum() / A_total.sum()
            monthly_eta_sb[m] = (eta_sb_array[:, indices].mean(axis=1) * A_total).sum() / A_total.sum()
            monthly_eta_trunc[m] = (eta_trunc_array[:, indices].mean(axis=1) * A_total).sum() / A_total.sum()
        
        # Annual
        P_bar = power_time.mean()
        J = 1000 * P_bar / A_total.sum()
        
        annual_eta_cos = (eta_cos_array.mean(axis=1) * A_total).sum() / A_total.sum()
        annual_eta_sb = (eta_sb_array.mean(axis=1) * A_total).sum() / A_total.sum()
        annual_eta_trunc = (eta_trunc_array.mean(axis=1) * A_total).sum() / A_total.sum()
        # Average the actual per-mirror products, not the product of averages.
        # Reflectance was applied exactly once inside eta_total_array.
        annual_eta_total = float((eta_total_array * A_total[:, None]).sum() / (A_total.sum() * n_times))
        
        return {
            'power_time_MW': power_time,
            'monthly_power_MW': monthly_power,
            'annual_power_MW': P_bar,
            'annual_J_kW_per_m2': J,
            'monthly_eta_cos': monthly_eta_cos,
            'monthly_eta_sb': monthly_eta_sb,
            'monthly_eta_trunc': monthly_eta_trunc,
            'annual_eta_cos': annual_eta_cos,
            'annual_eta_sb': annual_eta_sb,
            'annual_eta_trunc': annual_eta_trunc,
            'annual_eta_total': annual_eta_total,
            'total_area_m2': A_total.sum()
        }


def load_answer(answer_dir: Path) -> Dict[str, Any]:
    """Load solver answer."""
    answer_path = answer_dir / 'answer.json'
    if not answer_path.exists():
        return None
    
    with open(answer_path) as f:
        return json.load(f)


def invalid_answer(detail):
    """Schema-valid rejection; validity flags are not fabricated power values."""
    return {'valid':False,'score':0.0,'metric':'Q3_feasible_annual_power_per_area',
            'question_coverage':['Q1','Q2','Q3'],
            'checks':[{'name':'answer_contract','passed':False,'detail':str(detail)}],
            'measurements':[{'id':q+'_valid','value':0,'unit':'bool','question_id':q,
                             'description':'Answer rejected before numerical verification; no power measured'}
                            for q in ['Q1','Q2','Q3']]}


def evaluate(input_dir: Path, answer_dir: Path, output_dir: Path, seed: int, budget: int, variant: str) -> Dict[str, Any]:
    """Main evaluation function."""
    
    # Load answer
    try:
        answer = load_answer(answer_dir)
    except (OSError, ValueError, TypeError) as exc:
        return invalid_answer(type(exc).__name__+': '+str(exc))
    if not isinstance(answer,dict):
        return invalid_answer('answer.json must exist and contain an object')
    
    checks = []
    measurements = []
    question_coverage = []
    
    # Check question coverage
    if 'Q1' not in answer or 'Q2' not in answer or 'Q3' not in answer:
        return invalid_answer('Missing one or more questions')
    
    question_coverage = ['Q1', 'Q2', 'Q3']
    checks.append({"name": "question_coverage", "passed": True, "detail": "All three questions present"})
    
    # Load reference coordinates for Q1
    ref_coords = pd.read_csv(input_dir / 'public' / 'heliostat_coordinates.csv')
    
    # Time points
    time_points = []
    for m in range(1, 13):
        for h in [9.0, 10.5, 12.0, 13.5, 15.0]:
            time_points.append((m, 21, h))
    
    validator = GeometricValidator()
    calculator = OpticalCalculator(n_surf=4, n_sun_r=4, n_sun_chi=16)
    
    all_valid = True
    q1_valid = False
    q2_valid = False
    q3_valid = False
    q3_score = 0.0
    
    # Evaluate Q1
    try:
        q1 = answer['Q1']
        if 'mirrors' not in q1:
            checks.append({"name": "Q1_mirrors", "passed": False, "detail": "No mirrors field"})
            all_valid = False
        else:
            mirrors_q1 = pd.DataFrame(q1['mirrors'])
            
            # Check count
            if len(mirrors_q1) != 1745:
                checks.append({"name": "Q1_count", "passed": False, "detail": f"Expected 1745 mirrors, got {len(mirrors_q1)}"})
                all_valid = False
            else:
                checks.append({"name": "Q1_count", "passed": True, "detail": "Correct mirror count"})
            
            # Check fixed dimensions
            if not np.allclose(mirrors_q1['width_m'], 6.0, atol=1e-6) or not np.allclose(mirrors_q1['height_m'], 6.0, atol=1e-6):
                checks.append({"name": "Q1_dimensions", "passed": False, "detail": "Dimensions not 6x6 m"})
                all_valid = False
            else:
                checks.append({"name": "Q1_dimensions", "passed": True, "detail": "Dimensions 6x6 m"})
            
            if not np.allclose(mirrors_q1['z_m'], 4.0, atol=1e-6):
                checks.append({"name": "Q1_installation_height", "passed": False, "detail": "Installation height not 4 m"})
                all_valid = False
            else:
                checks.append({"name": "Q1_installation_height", "passed": True, "detail": "Installation height 4 m"})
            
            # Check coordinate correspondence
            coord_match = True
            for i in range(min(len(mirrors_q1), len(ref_coords))):
                if abs(mirrors_q1.iloc[i]['x_m'] - ref_coords.iloc[i]['x_m']) > 1e-6 or \
                   abs(mirrors_q1.iloc[i]['y_m'] - ref_coords.iloc[i]['y_m']) > 1e-6:
                    coord_match = False
                    break
            
            if coord_match and len(mirrors_q1) == 1745:
                checks.append({"name": "Q1_coordinates", "passed": True, "detail": "Coordinates match reference"})
                q1_valid = True
                
                # Compute Q1 power
                tower_x, tower_y = 0.0, 0.0
                geom_checks, geom_details = validator.validate_design(mirrors_q1, tower_x, tower_y)
                
                result = calculator.compute_field_power(mirrors_q1, tower_x, tower_y, time_points)
                
                measurements.append({
                    "id": "Q1_annual_power_MW",
                    "value": result['annual_power_MW'],
                    "unit": "MW",
                    "question_id": "Q1",
                    "description": "Annual average power"
                })
                measurements.append({
                    "id": "Q1_annual_J",
                    "value": result['annual_J_kW_per_m2'],
                    "unit": "kW/m²",
                    "question_id": "Q1",
                    "description": "Annual power per unit area"
                })
            else:
                checks.append({"name": "Q1_coordinates", "passed": False, "detail": "Coordinates do not match reference"})
                all_valid = False
                measurements.append({"id": "Q1_valid", "value": 0, "unit": "bool", "question_id": "Q1", "description": "Q1 validation"})
    except Exception as e:
        checks.append({"name": "Q1_evaluation", "passed": False, "detail": f"Exception: {str(e)}"})
        all_valid = False
        measurements.append({"id": "Q1_valid", "value": 0, "unit": "bool", "question_id": "Q1", "description": "Q1 validation"})
    
    # Evaluate Q2
    try:
        q2 = answer['Q2']
        mirrors_q2 = pd.DataFrame(q2['mirrors'])
        tower_x = q2['tower_x_m']
        tower_y = q2['tower_y_m']
        
        # Geometric validation
        geom_checks, geom_details = validator.validate_design(mirrors_q2, tower_x, tower_y)
        
        if not all(geom_checks.values()):
            checks.append({"name": "Q2_geometry", "passed": False, "detail": str(geom_details)})
            all_valid = False
        else:
            checks.append({"name": "Q2_geometry", "passed": True, "detail": "All geometric constraints satisfied"})
        
        # Check uniform dimensions
        if mirrors_q2['width_m'].nunique() > 1 or mirrors_q2['height_m'].nunique() > 1 or mirrors_q2['z_m'].nunique() > 1:
            checks.append({"name": "Q2_uniform", "passed": False, "detail": "Non-uniform dimensions"})
            all_valid = False
        else:
            checks.append({"name": "Q2_uniform", "passed": True, "detail": "Uniform dimensions"})
        
        # Compute power
        result = calculator.compute_field_power(mirrors_q2, tower_x, tower_y, time_points)
        
        if result['annual_power_MW'] >= 60.0:
            checks.append({"name": "Q2_power_threshold", "passed": True, "detail": f"Power {result['annual_power_MW']:.3f} >= 60 MW"})
            q2_valid = True
        else:
            checks.append({"name": "Q2_power_threshold", "passed": False, "detail": f"Power {result['annual_power_MW']:.3f} < 60 MW"})
            all_valid = False
        
        measurements.append({"id": "Q2_annual_power_MW", "value": result['annual_power_MW'], "unit": "MW", "question_id": "Q2", "description": "Annual average power"})
        measurements.append({"id": "Q2_annual_J", "value": result['annual_J_kW_per_m2'], "unit": "kW/m²", "question_id": "Q2", "description": "Annual power per unit area"})
        
    except Exception as e:
        checks.append({"name": "Q2_evaluation", "passed": False, "detail": f"Exception: {str(e)}"})
        all_valid = False
        measurements.append({"id": "Q2_valid", "value": 0, "unit": "bool", "question_id": "Q2", "description": "Q2 validation"})
    
    # Evaluate Q3
    try:
        q3 = answer['Q3']
        mirrors_q3 = pd.DataFrame(q3['mirrors'])
        tower_x = q3['tower_x_m']
        tower_y = q3['tower_y_m']
        
        # Geometric validation
        geom_checks, geom_details = validator.validate_design(mirrors_q3, tower_x, tower_y)
        
        if not all(geom_checks.values()):
            checks.append({"name": "Q3_geometry", "passed": False, "detail": str(geom_details)})
            all_valid = False
        else:
            checks.append({"name": "Q3_geometry", "passed": True, "detail": "All geometric constraints satisfied"})
        
        # Compute power
        result = calculator.compute_field_power(mirrors_q3, tower_x, tower_y, time_points)
        
        if result['annual_power_MW'] >= 60.0:
            checks.append({"name": "Q3_power_threshold", "passed": True, "detail": f"Power {result['annual_power_MW']:.3f} >= 60 MW"})
            q3_valid = True
            q3_score = result['annual_J_kW_per_m2']
        else:
            checks.append({"name": "Q3_power_threshold", "passed": False, "detail": f"Power {result['annual_power_MW']:.3f} < 60 MW"})
            all_valid = False
        
        measurements.append({"id": "Q3_annual_power_MW", "value": result['annual_power_MW'], "unit": "MW", "question_id": "Q3", "description": "Annual average power"})
        measurements.append({"id": "Q3_annual_J", "value": result['annual_J_kW_per_m2'], "unit": "kW/m²", "question_id": "Q3", "description": "Annual power per unit area"})
        
    except Exception as e:
        checks.append({"name": "Q3_evaluation", "passed": False, "detail": f"Exception: {str(e)}"})
        all_valid = False
        measurements.append({"id": "Q3_valid", "value": 0, "unit": "bool", "question_id": "Q3", "description": "Q3 validation"})
    
    return {
        "valid": all_valid and q1_valid and q2_valid and q3_valid,
        "score": q3_score if (all_valid and q3_valid) else 0.0,
        "metric": "Q3_feasible_annual_power_per_area",
        "question_coverage": question_coverage,
        "checks": checks,
        "measurements": measurements
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--answer', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--seed', type=int, required=True)
    parser.add_argument('--budget', type=int, required=True)
    parser.add_argument('--variant', type=str, required=True)
    args = parser.parse_args()
    
    result = evaluate(args.input, args.answer, args.out, args.seed, args.budget, args.variant)
    
    args.out.mkdir(parents=True, exist_ok=True)
    with open(args.out / 'evaluation.json', 'w') as f:
        json.dump(result, f, indent=2)
    
    print(f"Evaluation complete. Valid: {result['valid']}, Score: {result['score']:.6f}")


if __name__ == '__main__':
    main()
