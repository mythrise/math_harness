"""Transport compatibility must never weaken local acceptance."""
import copy
import json
import pytest
from jsonschema import Draft202012Validator
from cumcm_harness import literature_r2  # registers live output contracts
from cumcm_harness.contracts import SCHEMAS, validate
from cumcm_harness.common import IntegrityError, read_json, digest
from cumcm_harness.provider_schema import codex_schema, normalize_codex_response
from cumcm_harness.providers import CLIProvider
from test_cli_contracts import fake_cli


@pytest.mark.parametrize('name', sorted(set(SCHEMAS)-{'exa_policy'}))
def test_model_output_transport_schemas(name):
    original = copy.deepcopy(SCHEMAS[name])
    projected = codex_schema(original)
    Draft202012Validator.check_schema(projected)
    def inspect(node):
        if isinstance(node, dict):
            assert 'oneOf' not in node and 'uniqueItems' not in node
            if 'properties' in node:
                assert set(node['required']) == set(node['properties'])
            for value in node.values(): inspect(value)
        elif isinstance(node, list):
            for value in node: inspect(value)
    inspect(projected)
    assert original == SCHEMAS[name]


def test_duplicate_hypothesis_ids_still_rejected_locally():
    value = {'queries': [{'query':'generic method limitations', 'purpose':'support',
        'profile':'foundations', 'hypothesis_ids':['H1','H1'], 'additional_queries':[]}]}
    assert Draft202012Validator(codex_schema(SCHEMAS['research_queries_r2'])).is_valid(value)
    with pytest.raises(IntegrityError, match='non-unique'):
        validate('research_queries_r2', normalize_codex_response(value, SCHEMAS['research_queries_r2']))


def test_only_optional_nonnullable_nulls_removed():
    schema = {'type':'object', 'properties': {
        'required':{'type':'string'}, 'optional':{'type':'string'},
        'nullable':{'type':['string','null']}, 'nested':{'type':'array','items':{
            'type':'object','properties':{'a':{'type':'string'}},'required':[]}}},
        'required':['required'], 'additionalProperties':False}
    value = {'required':None,'optional':None,'nullable':None,'unknown':None,'nested':[{'a':None}]}
    normalized = normalize_codex_response(value, schema)
    assert normalized == {'required':None,'nullable':None,'unknown':None,'nested':[{}]}
    assert not Draft202012Validator(schema).is_valid(normalized)
    assert value['optional'] is None


def test_adapter_preserves_raw_response_and_normalized_identity(fake_cli, tmp_path):
    binary = fake_cli('codex')
    binary.write_text(binary.read_text().replace("pathlib.Path(args[args.index('--output-last-message')+1])",
        "result.update(clarification_responses=None);pathlib.Path(args[args.index('--output-last-message')+1])"))
    response = CLIProvider('codex').invoke('math_reviewer','review',{'target_digest':'a'*64},tmp_path/'logs')
    raw = read_json(tmp_path/'logs/raw_response.json')
    assert raw['clarification_responses'] is None
    assert 'clarification_responses' not in response['result']
    assert response['receipt']['raw_response_digest'] == digest(raw)
    assert response['receipt']['response_digest'] == digest(response['result'])
    assert response['receipt']['raw_response_digest'] != response['receipt']['response_digest']
