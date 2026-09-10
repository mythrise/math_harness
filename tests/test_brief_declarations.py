"""Presentation-only symbol wrappers must not masquerade as source errors.

These are reconstructed generic formulas, not private live responses or new
scientific evidence. Source quotations remain byte-for-byte Python strings.
"""
from copy import deepcopy
import pytest

from cumcm_harness.brief_contracts import check_fact, check_facts, check_ambiguities
from cumcm_harness.brief_validation import BriefContractError, definition_conflicts
from cumcm_harness.common import IntegrityError, ScientificRejection
from cumcm_harness.brief_workflow import BriefWorkflow
from test_brief_rc3 import (problem_units, source_fact, sample_brief, source_workspace,
                           FixedController, FixedScript, batch_response)

SYMBOL = r'\eta_{\mathrm{loss}}'
QUOTE = r'损失效率 $\eta_{\mathrm{loss}} = 1 - L$'


def formula_fact(subject=SYMBOL):
    units = problem_units(QUOTE + '，L 为损失比例；N 为总量。')
    fact = source_fact(units[0])
    fact.update(category='formula', declarations=[{'subject': subject, 'quote': QUOTE}])
    return fact, units


@pytest.mark.parametrize('subject', [SYMBOL, '$'+SYMBOL+'$', '$$'+SYMBOL+'$$',
                                   r'\('+SYMBOL+r'\)', r'\['+SYMBOL+r'\]',
                                   '  $ '+SYMBOL+' $  '])
def test_balanced_subject_wrappers_preserve_original_fact_and_source(subject):
    fact, units = formula_fact(subject)
    before = deepcopy((fact, units))
    assert check_fact(fact, units, ['Q1', 'Q2']) is fact
    assert (fact, units) == before


@pytest.mark.parametrize('subject', ['η_loss', 'eta_loss', r'\eta_{\mathrm{other}}'])
def test_symbol_aliases_and_changed_subscripts_are_not_guessed(subject):
    fact, units = formula_fact(subject)
    with pytest.raises(BriefContractError) as caught:
        check_fact(fact, units, ['Q1', 'Q2'])
    assert any(f['code'] == 'DECLARATION_SUBJECT_NOT_IN_SOURCE' for f in caught.value.findings)


def test_subject_cannot_borrow_an_unrelated_definition_from_the_same_source():
    fact, units = formula_fact('N')
    with pytest.raises(BriefContractError) as caught:
        check_fact(fact, units, ['Q1', 'Q2'])
    assert [f['code'] for f in caught.value.findings] == ['DECLARATION_SUBJECT_NOT_IN_QUOTE']


def test_quotations_are_not_normalized_when_subject_wrappers_are_accepted():
    fact, units = formula_fact('$'+SYMBOL+'$')
    fact['declarations'][0]['quote'] = QUOTE.replace(' = ', '=')
    with pytest.raises(BriefContractError) as caught:
        check_fact(fact, units, ['Q1', 'Q2'])
    assert {f['code'] for f in caught.value.findings} == {
        'DECLARATION_QUOTE_NOT_IN_SOURCE', 'DECLARATION_QUOTE_NOT_IN_STATEMENT'}


@pytest.mark.parametrize('replacement', [QUOTE.replace('1', '2'), QUOTE.replace(' - ', ' + '),
                                       QUOTE.replace('loss', 'other')])
def test_changed_quoted_constants_operators_and_subscripts_still_fail(replacement):
    fact, units = formula_fact('$'+SYMBOL+'$')
    fact['declarations'][0]['quote'] = replacement
    with pytest.raises(BriefContractError) as caught:
        check_fact(fact, units, ['Q1', 'Q2'])
    assert 'DECLARATION_QUOTE_NOT_IN_SOURCE' in {f['code'] for f in caught.value.findings}


@pytest.mark.parametrize('subject', ['$$', '$ $', '$$$'+SYMBOL+'$$$', '$'+SYMBOL, SYMBOL+'$'])
def test_empty_nested_and_unbalanced_wrappers_do_not_create_a_symbol(subject):
    fact, units = formula_fact(subject)
    with pytest.raises(BriefContractError):
        check_fact(fact, units, ['Q1', 'Q2'])


def test_statement_must_still_include_the_exact_quote():
    fact, units = formula_fact('$'+SYMBOL+'$')
    fact['statement'] = 'L 为损失比例；N 为总量。'
    with pytest.raises(BriefContractError) as caught:
        check_fact(fact, units, ['Q1', 'Q2'])
    assert [f['code'] for f in caught.value.findings] == ['DECLARATION_QUOTE_NOT_IN_STATEMENT']


def test_wrapped_duplicate_declarations_are_rejected():
    fact, units = formula_fact()
    fact['declarations'].append({'subject':'$'+SYMBOL+'$', 'quote':QUOTE})
    with pytest.raises(BriefContractError, match='DUPLICATE_DECLARATION_SUBJECT'):
        check_fact(fact, units, ['Q1', 'Q2'])


def test_one_batch_reports_all_bad_declaration_locations_without_mutation():
    fact, units = formula_fact('unknown_symbol')
    second = deepcopy(fact)
    second['declarations'] = [{'subject':'N', 'quote':QUOTE}]
    packet = {'status':'COMPLETE', 'facts':[fact,second], 'exclusions':[], 'unreadable':[], 'reason':''}
    before = deepcopy(packet)
    with pytest.raises(BriefContractError) as caught:
        check_facts(packet, units, ['Q1','Q2'])
    assert {f['location'] for f in caught.value.findings} == {
        'facts[0].declarations[0].subject','facts[1].declarations[0].subject'}
    assert all(f['source_unit_ids'] == fact['source_unit_ids'] and f['required_fix'] for f in caught.value.findings)
    assert packet == before


@pytest.mark.parametrize('declared,ambiguous', [('ST','$ST$'),('$ST$','ST'),(r'\(ST\)',r'\[ST\]')])
def test_presentation_wrappers_cannot_reopen_a_known_definition(declared,ambiguous):
    brief,_ = sample_brief()
    row = next(r for r in brief['requirements'] if r['declarations'])
    row['declarations'][0]['subject'] = declared
    brief['ambiguities'] = [{'id':'A01','kind':'missing_information','subject':ambiguous,
        'issue':'时间定义缺失','impact':'输入不同','resolution':'重新定义','related_requirement_ids':[row['id']]}]
    with pytest.raises(BriefContractError, match='REOPENED_EXPLICIT_DEFINITION'):
        definition_conflicts(brief)


def test_consistency_register_covers_all_source_rows_across_wrapper_variants():
    brief,_ = sample_brief()
    row = next(r for r in brief['requirements'] if r['declarations'])
    second = deepcopy(row);second['id']='R999';second['declarations'][0]['subject']='$ST$'
    brief['requirements'].append(second)
    value = {'ambiguities':[], 'accepted_definitions':[{'subject':r'\(ST\)','requirement_ids':[row['id'],'R999']}]}
    before = deepcopy((brief,value))
    assert check_ambiguities(value,brief) is value and (brief,value) == before
    value['accepted_definitions'][0]['requirement_ids'].pop()
    with pytest.raises(IntegrityError, match='recognition mismatch'):
        check_ambiguities(value,brief)


def test_contract_exhaustion_is_not_a_scientific_verdict_or_provider_failover(tmp_path):
    from cumcm_harness.brief_validation import SourceContractFailure
    root,text,intake = source_workspace(tmp_path)
    script = FixedScript()
    def hook(role,schema,packet,provider):
        if schema == 'brief_facts':
            value = batch_response(packet['source_units'])
            for fact in value['facts']:
                for d in fact['declarations']:d['subject']='NOT_IN_SOURCE'
            return value
    script.hook=hook;controller=FixedController(root,text,intake,script)
    with pytest.raises(SourceContractFailure) as caught:
        BriefWorkflow(controller).run({},{})
    assert not isinstance(caught.value,ScientificRejection)
    assert all(r['diagnostic']['category']=='SOURCE_CONTRACT' for r in caught.value.records)
    assert any(r['diagnostic']['findings'][0]['location']=='facts[3].declarations[0].subject' for r in caught.value.records)
    assert not any(e['kind']=='PROVIDER_FAILOVER' for e in controller.store.events())
    assert not (root/'brief/accepted.json').exists()
    assert controller.store.audit()['integrity']=='PASS'


def test_exact_field_feedback_repairs_one_chunk_and_preserves_failed_evidence(tmp_path):
    root,text,intake = source_workspace(tmp_path)
    script=FixedScript();seen=[]
    def hook(role,schema,packet,provider):
        if schema != 'brief_facts':return
        value=batch_response(packet['source_units'])
        for fact in value['facts']:
            for d in fact['declarations']:
                if not packet['repair_feedback']:d['subject']='NOT_IN_SOURCE'
                else:
                    diagnostic=packet['repair_feedback'][0]
                    assert diagnostic['category']=='SOURCE_CONTRACT'
                    assert diagnostic['findings'][0]['location']=='facts[3].declarations[0].subject'
                    seen.append(diagnostic['full_diagnostic_ref']);d['subject']='$ST$'
        return value
    script.hook=hook;controller=FixedController(root,text,intake,script)
    brief=BriefWorkflow(controller).run({},{})
    assert brief and len(seen)==1
    original=controller.store.load(seen[0])
    assert original['category']=='SOURCE_CONTRACT'
    assert original['latest_artifact']['facts'][3]['declarations'][0]['subject']=='NOT_IN_SOURCE'
    assert controller.store.audit()['integrity']=='PASS'


def test_a_real_negative_review_stays_negative_when_later_repair_is_malformed(tmp_path):
    root,text,intake = source_workspace(tmp_path)
    script=FixedScript()
    def hook(role,schema,packet,provider):
        if schema=='review':
            return {'target_digest':packet['target_digest'],'verdict':'FAIL','scope':'source fidelity',
                'findings':[{'severity':'P1','location':'source','issue':'Missing complete definition','required_fix':'Restore definition'}],
                'evidence':['FIXTURE negative, not live evidence'],'unverified':[]}
        if schema=='brief_outline' and packet['repair_feedback']:
            from test_brief_rc3 import outline
            value=outline(packet['source_units']);value['questions'][0]['source_unit_ids']=['Sbad'];return value
    script.hook=hook;controller=FixedController(root,text,intake,script)
    with pytest.raises(ScientificRejection) as caught:
        BriefWorkflow(controller).run({},{})
    assert {r['diagnostic']['category'] for r in caught.value.records}=={'SCIENTIFIC_REVIEW','SOURCE_CONTRACT'}
    assert not any(e['kind']=='PROVIDER_FAILOVER' for e in controller.store.events())
