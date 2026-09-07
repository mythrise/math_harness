"""Read the complete persisted evidence; small source packages explicitly skip."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import pytest
R=Path(__file__).resolve().parents[1]

def test_complete_stage_counts_and_errors():
 expected={'dev':160,'dev2':128,'confirm':1152,'cap_ablation':72,'original':60,'stress':60,'serial':108,'baseline_codec_audit':144}
 for stage,n in expected.items():
  fp=R/f'results/{stage}/raw.csv'
  if not fp.exists():pytest.skip('Full benchmark evidence not included in the small source package')
  d=pd.read_csv(fp);assert len(d)==n and (d.fe==d.physical_calls).all() and (d.fe==d.budget).all()

def test_all_saved_parity_results():
 d=pd.read_csv(R/'results/analysis/all_trace_parity.csv')
 assert len(d)==348 and d[['X','F','output_X','output_F']].all().all()
 assert len(d[(d.candidate=='fast_h0')&(d.baseline=='h0')])==180

def test_physical_truth_and_source_audit():
 d=json.loads((R/'results/analysis/FULL_AUDIT.json').read_text())
 assert d['all_audits_pass'] and d['baseline_source_unchanged']
 assert d['complete_runs']==1884 and d['search_FE']==1843200
 assert d['forecast_temporal_checks']>1000000
 assert all(d['stage_source_freezes'].values())

def test_kept_selection_before_confirmation():
 s=json.loads((R/'protocol/SELECTION_BEFORE_CONFIRM.json').read_text())
 assert s['quality_candidate']=='refit32' and not s['quality_development_pass']
 assert s['efficiency_secondary']=='local24'
