"""Small analytic regressions; no optimization or full-field certification."""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from evaluate import OpticalCalculator, GeometricValidator


def run_tests():
    cases=[]
    def test(name, fn):
        try:
            detail=fn()
            cases.append({'name':name,'passed':True,'detail':str(detail)})
        except Exception as exc:
            cases.append({'name':name,'passed':False,'detail':type(exc).__name__+': '+str(exc)})
    def weights():
        for nr,nchi in [(1,4),(2,8),(4,16)]:
            c=OpticalCalculator(n_surf=1,n_sun_r=nr,n_sun_chi=nchi)
            assert c.sun_weights.shape==(nr,nchi)
            assert len(c.sun_b)==nr*nchi
            integral=sum(c.sun_b[i*nchi+j]*mu for i,mu in enumerate(c.sun_mu) for j in range(nchi))
            assert abs(integral-1)<1e-12,(nr,nchi,integral)
            assert abs(c.sun_b.sum()-2/(1+np.cos(c.beta)))<1e-12
        return '1x4, 2x8, 4x16 weights; projected normalization residual < 1e-12'
    test('sun_disc_shapes_and_normalization',weights)
    def reflection():
        c=OpticalCalculator();s=np.array([0.,0.,1.]);p=np.array([0.,0.,4.]);R=np.array([80.,0.,80.])
        n,ew,eh=c.compute_mirror_normal(p,R,s)
        np.testing.assert_allclose(2*np.dot(s,n)*n-s,(R-p)/np.linalg.norm(R-p),atol=1e-14)
        assert abs(ew[2])<1e-14
        np.testing.assert_allclose(np.cross(n,ew),eh,atol=1e-14)
        return 'Reflection closes on target; mirror width is horizontal'
    test('reflection_target_and_mirror_axes',reflection)
    blocker={'x_m':0.,'y_m':0.,'z_m':5.,'width_m':2.,'height_m':2.,
             'normal':np.array([0.,0.,1.]),'e_w':np.array([1.,0.,0.]),'e_h':np.array([0.,1.,0.])}
    def shadow():
        c=OpticalCalculator();p=np.zeros(3);s=np.array([0.,0.,1.]);R=np.array([0.,0.,80.])
        assert not c.check_occlusion(p,s,[blocker],-1,R)
        assert c.check_occlusion(p,-s,[blocker],-1,R)
        assert c.check_occlusion(p,s,[blocker],-1,R,True,4.)
        assert not c.check_occlusion(p,s,[blocker],-1,R,True,6.)
        return 'Blocker at +5 m blocks +s, not -s; a blocker after receiver is ignored'
    test('shadow_direction_and_blocker_distance',shadow)
    def actual_shadow_call():
        class Capture(OpticalCalculator):
            def check_occlusion(self,p,d,mirrors,index,R,check_to_receiver=False,max_tau=None):
                if not check_to_receiver:assert d[2]>0, 'incident shadow must trace toward the sun'
                return True
        c=Capture(n_surf=1,n_sun_r=1,n_sun_chi=4)
        c.compute_mirror_efficiency({'x_m':120.,'y_m':0.,'z_m':4.,'width_m':2.,'height_m':2.},
                                    np.array([0.,0.,80.]),np.array([0.,0.,1.]),[],0)
        return 'Actual finite-sun efficiency path calls shadow query with +s'
    test('integrated_shadow_query_sign',actual_shadow_call)
    def cylinder():
        c=OpticalCalculator()
        hit,t,side=c.intersect_cylinder(np.array([10.,0.,80.]),np.array([-1.,0.,0.]),0.,0.)
        assert hit and side and abs(t-6.5)<1e-12
        hit,t,side=c.intersect_cylinder(np.array([0.,0.,90.]),np.array([0.,0.,-1.]),0.,0.)
        assert hit and not side and abs(t-6.)<1e-12,(hit,t,side)
        assert not c.intersect_cylinder(np.array([-10.,3.5,80.]),np.array([1.,0.,0.]),0.,0.)[0]
        hit,t,side=c.intersect_cylinder(np.array([-10.,0.,90.]),np.array([6.5,0.,-6.])/np.sqrt(6.5**2+6**2),0.,0.)
        assert hit and not side,'cap must win shared-rim tie'
        return 'Side entry, nearest top cap, tangent exclusion, cap-first rim tie'
    test('receiver_first_contact_and_boundaries',cylinder)
    def geometry():
        v=GeometricValidator()
        def frame(dx):return pd.DataFrame([dict(x_m=x,y_m=0.,z_m=4.,width_m=6.,height_m=6.) for x in [150.,150.+dx]])
        assert not v.validate_design(frame(11.),0.,0.)[0]['pairwise_clearance']
        assert v.validate_design(frame(11.001),0.,0.)[0]['pairwise_clearance']
        return 'Exactly width+5 fails; strictly larger distance passes'
    test('strict_spacing_boundary',geometry)
    def all_orientations():
        c=OpticalCalculator(n_surf=1,n_sun_r=1,n_sun_chi=4)
        frame=pd.DataFrame([dict(x_m=x,y_m=20.,z_m=4.,width_m=2.,height_m=2.) for x in [120.,150.]])
        result=c.compute_field_power(frame,0.,0.,[(m,21,st) for m in range(1,13) for st in [9.,10.5,12.,13.5,15.]])
        assert np.isfinite(result['power_time_MW']).all()
        assert result['annual_power_MW']>0
        return 'Two-mirror, sixty-instant real trace finishes without missing/stale neighbor axes'
    test('all_mirror_orientations_initialized',all_orientations)
    def product_aggregation():
        class AnalyticOptics(OpticalCalculator):
            def compute_sun_direction(self,*args):return np.array([0.,0.,1.]),1.
            def compute_mirror_efficiency(self,mirror,R,s,all_mirrors,mirror_idx):
                cos,sb=((.8,.2) if mirror_idx==0 else (.2,.8))
                return dict(eta_cos=cos,eta_sb=sb,eta_trunc=1.,eta_at=1.,eta_total=.92*cos*sb)
        frame=pd.DataFrame([dict(x_m=x,y_m=0.,z_m=4.,width_m=2.,height_m=2.) for x in [120.,150.]])
        result=AnalyticOptics().compute_field_power(frame,0.,0.,[(m,21,st) for m in range(1,13) for st in [9.,10.5,12.,13.5,15.]])
        assert abs(result['annual_eta_total']-.1472)<1e-14,result['annual_eta_total']
        assert abs(result['annual_power_MW']-.0011776)<1e-14
        return 'Exact correlated-components case gives eta=.1472, not product-of-means .23'
    test('mean_of_efficiency_products_and_single_reflectance',product_aggregation)
    return {'cases':cases,'all_passed':all(c['passed'] for c in cases),
            'scope':'REGRESSION_PRIMITIVES_ONLY_NOT_FULL_FIELD_ACCURACY'}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input');p.add_argument('--out',type=Path,required=True)
    p.add_argument('--seed');p.add_argument('--budget');p.add_argument('--variant');a=p.parse_args()
    r=run_tests();(a.out/'tests.json').write_text(json.dumps(r,indent=2,allow_nan=False)+'\n')
    print(json.dumps(r))
