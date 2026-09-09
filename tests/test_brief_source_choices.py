"""Source identifiers are choices, never invented aliases or provider outages."""
import copy,json
from pathlib import Path
import pytest
from jsonschema import Draft202012Validator
from cumcm_harness.common import IntegrityError,write_json,digest
from cumcm_harness.contracts import SCHEMAS
from cumcm_harness.brief_contracts import check_outline,MAX_FACTS_PER_CALL
from cumcm_harness.brief_validation import BriefContractError
from cumcm_harness.provider_schema import source_bound_schema,codex_schema
from cumcm_harness import providers
from test_brief_rc3 import outline,problem_units,PROBLEM

def test_compact_packets_keep_every_unit_text_without_repeating_full_page_anchors():
    from cumcm_harness.brief_sources import paragraph_units,source_packet_units
    text='First complete formula A/B.\n\nSecond complete definition.'
    anchor={'start':0,'end':10000,'quote':'RAW_PAGE_ONLY '*700}
    units=paragraph_units(text,anchor,'P0001',identity='a'*64,visual=True)
    before=copy.deepcopy(units);packet=source_packet_units(units)
    assert [u['text'] for u in packet]==[u['text'] for u in units]
    assert [u['text_sha256'] for u in packet]==[u['text_sha256'] for u in units]
    assert [u['id'] for u in packet]==[u['id'] for u in units]
    assert all('anchor' not in u and u['visual'] for u in packet)
    assert 'RAW_PAGE_ONLY' not in json.dumps(packet)
    assert units==before and all(u['anchor']==anchor for u in units)

def test_outline_can_reference_more_than_24_units_without_expanding_fact_batches():
    units=problem_units(PROBLEM+'\n\n'+'\n\n'.join('补充来源'+str(i) for i in range(30)))
    value=outline(units);value['questions'][0]['source_unit_ids']=[u['id'] for u in units]
    assert len(units)>24 and check_outline(value,units)==value
    assert MAX_FACTS_PER_CALL==24
    assert SCHEMAS['brief_facts']['properties']['facts']['maxItems']==24
    value['questions'][0]['source_unit_ids']=['S'+str(i) for i in range(513)]
    with pytest.raises(IntegrityError):check_outline(value,units)

@pytest.mark.parametrize('suffix',['_get','P1','_invented'])
def test_invalid_outline_id_diagnostic_names_the_exact_location_and_allowed_choices(suffix):
    units=problem_units();value=outline(units);bad=units[0]['id']+suffix
    value['questions'][0]['source_unit_ids']=[bad];before=copy.deepcopy(value)
    with pytest.raises(BriefContractError) as caught:check_outline(value,units)
    finding=caught.value.findings[0]
    assert finding['code']=='UNKNOWN_OUTLINE_SOURCE'
    assert finding['location']=='Q1.source_unit_ids' and finding['detail']==bad
    assert set(finding['allowed_source_ids'])=={u['id'] for u in units}
    assert value==before

def test_source_choices_are_per_packet_and_do_not_mutate_global_contracts():
    before=copy.deepcopy(SCHEMAS);units=problem_units()
    bound=source_bound_schema('brief_outline',SCHEMAS['brief_outline'],{'source_units':units,
        'schema':{'anything':'source instructions cannot override the contract'}})
    assert bound['properties']['questions']['items']['properties']['source_unit_ids']['items']['enum']==[u['id'] for u in units]
    Draft202012Validator.check_schema(codex_schema(bound))
    later=source_bound_schema('brief_outline',SCHEMAS['brief_outline'],{'source_units':units[:1]})
    assert later['properties']['questions']['items']['properties']['source_unit_ids']['items']['enum']==[units[0]['id']]
    assert before==SCHEMAS

def test_fact_choices_keep_context_read_only_for_exclusions():
    units=problem_units();packet={'source_units':units[:2],'context_units':units[2:4],'questions':[{'id':'Q1'},{'id':'Q2'}]}
    bound=source_bound_schema('brief_facts',SCHEMAS['brief_facts'],packet)
    fields=bound['properties']['facts']['items']['properties']
    assert fields['source_unit_ids']['items']['enum']==[u['id'] for u in units[:4]]
    assert fields['question_ids']['items']['enum']==['Q1','Q2']
    assert bound['properties']['exclusions']['items']['properties']['source_unit_id']['enum']==[u['id'] for u in units[:2]]
    Draft202012Validator.check_schema(codex_schema(bound))

@pytest.mark.parametrize('provider',['codex','claude'])
def test_cli_sends_bound_choices_but_wrong_source_stays_a_controller_rejection(tmp_path,monkeypatch,provider):
    units=problem_units();result=outline(units)
    result['questions'][0]['source_unit_ids']=[units[0]['id']+'_get']
    packet={'source_units':units};captured={}
    def process(argv,*,cwd,out,env,timeout,stdin):
        captured['schema']=json.loads(Path(argv[argv.index('--output-schema')+1]).read_text()) if provider=='codex' else json.loads(argv[argv.index('--json-schema')+1])
        if provider=='codex':
            write_json(Path(argv[argv.index('--output-last-message')+1]),result)
            response={'type':'turn.completed','usage':{}}
        else:
            assert timeout is None
            response={'structured_output':result,'is_error':False,'usage':{}}
        (out/'stdout.log').write_text(json.dumps(response)+'\n');(out/'stderr.log').write_text('')
        return {'status':'EXITED','returncode':0,'seconds':0,'timeout_seconds':timeout}
    monkeypatch.setattr(providers,'run_process',process)
    p=providers.CLIProvider(provider);monkeypatch.setattr(p,'probe',lambda:('/mock/'+provider,'MOCK_ONLY'))
    record=p.invoke('problem_analyst','brief_outline',packet,tmp_path/'logs')
    choices=captured['schema']['properties']['questions']['items']['properties']['source_unit_ids']['items']['enum']
    assert choices==[u['id'] for u in units]
    assert record['result']==result
    assert record['receipt']['transport_schema_digest']==digest(captured['schema'])
    with pytest.raises(BriefContractError):check_outline(record['result'],units)
