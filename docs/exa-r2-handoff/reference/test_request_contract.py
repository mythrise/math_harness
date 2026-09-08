import copy
import json
from pathlib import Path
import unittest
from request_contract import BETA, ContractError, dynamic_fallback, validate_request, request_shape_digest
ROOT=Path(__file__).resolve().parents[1]
EXAMPLES={r['name']:r for r in json.loads((ROOT/'examples/raw-exa-requests.json').read_text())['requests']}

def example(name='foundations'):
    r=copy.deepcopy(EXAMPLES[name]);return r['endpoint'],r['body'],r['public_headers']

class RequestContractTests(unittest.TestCase):
    def test_all_eight_examples(self):
        self.assertEqual(len(EXAMPLES),8)
        for row in EXAMPLES.values():
            validate_request(row['endpoint'], row['body'], row['public_headers'])
    def test_dynamic_requires_beta(self):
        e,b,h=example('discovery_beta');h.pop('Exa-Beta')
        with self.assertRaises(ContractError):validate_request(e,b,h)
    def test_dynamic_wrong_beta(self):
        e,b,h=example('discovery_beta');h['Exa-Beta']='outdated-preview'
        with self.assertRaises(ContractError):validate_request(e,b,h)
    def test_dynamic_cap_conflict(self):
        e,b,h=example('discovery_beta');b['contents']['highlights']['maxCharacters']=2000
        with self.assertRaises(ContractError):validate_request(e,b,h)
    def test_dynamic_false_cap_is_allowed(self):
        e,b,h=example();b['contents']['highlights']['dynamic']=False
        validate_request(e,b,h)
    def test_dynamic_not_boolean(self):
        e,b,h=example();b['contents']['highlights']['dynamic']='false'
        with self.assertRaises(ContractError):validate_request(e,b,h)
    def test_stable_no_beta(self):
        e,b,h=example();h['Exa-Beta']=BETA
        with self.assertRaises(ContractError):validate_request(e,b,h)
    def test_search_top_level_text_rejected(self):
        e,b,h=example();b['text']=True
        with self.assertRaises(ContractError):validate_request(e,b,h)
    def test_contents_nested_content_rejected(self):
        e,b,h=example('primary_source_read');b['contents']={'text':True}
        with self.assertRaises(ContractError):validate_request(e,b,h)
    def test_workflow_field_never_forwarded(self):
        e,b,h=example();b['max_total_http_attempts']=80
        with self.assertRaises(ContractError):validate_request(e,b,h)
    def test_rest_nested_snake_case_rejected(self):
        e,b,h=example();b['contents']['highlights']={'max_characters':2000}
        with self.assertRaises(ContractError):validate_request(e,b,h)
    def test_legacy_parameters_rejected(self):
        for k in ('tokensNum','useAutoprompt','livecrawl','includeUrls'):
            e,b,h=example();b[k]=True
            with self.subTest(k=k), self.assertRaises(ContractError):validate_request(e,b,h)
    def test_legacy_highlights_parameters_rejected(self):
        for k in ('numSentences','highlightsPerUrl'):
            e,b,h=example();b['contents']['highlights'][k]=3
            with self.subTest(k=k),self.assertRaises(ContractError):validate_request(e,b,h)
    def test_category_publication_not_legacy(self):
        e,b,h=example();b['category']='research paper'
        with self.assertRaises(ContractError):validate_request(e,b,h)
    def test_boolean_results_rejected(self):
        e,b,h=example();b['numResults']=True
        with self.assertRaises(ContractError):validate_request(e,b,h)
    def test_null_optional_rejected(self):
        e,b,h=example();b['category']=None
        with self.assertRaises(ContractError):validate_request(e,b,h)
    def test_sse_rejected(self):
        e,b,h=example();b['stream']=True
        with self.assertRaises(ContractError):validate_request(e,b,h)
    def test_additional_query_on_auto_rejected(self):
        e,b,h=example();b['additionalQueries']=['another scholarly query']
        with self.assertRaises(ContractError):validate_request(e,b,h)
    def test_nested_output_schema_rejected_by_local_subset(self):
        e,b,h=example('deep_escalation');b['outputSchema']['properties']['limitations']={'type':'object','properties':{'a':{'type':'string'}}}
        with self.assertRaises(ContractError):validate_request(e,b,h)
    def test_no_citation_fields_in_output_schema(self):
        e,b,h=example('deep_escalation');b['outputSchema']['properties']['citations']={'type':'string'}
        with self.assertRaises(ContractError):validate_request(e,b,h)
    def test_more_than_ten_properties(self):
        e,b,h=example('deep_escalation');b['outputSchema']={'type':'object','properties':{f'k{i}':{'type':'string'} for i in range(11)},'required':[]}
        with self.assertRaises(ContractError):validate_request(e,b,h)
    def test_company_date_filters_rejected(self):
        e,b,h=example('recent_methods');b['category']='company'
        with self.assertRaises(ContractError):validate_request(e,b,h)
    def test_reverse_dates_rejected(self):
        e,b,h=example('recent_methods');b['startPublishedDate']='2027-01-01'
        with self.assertRaises(ContractError):validate_request(e,b,h)
    def test_fulltext_expansion_allowed(self):
        e,b,h=example('primary_source_read');b['text']['maxCharacters']=60000
        validate_request(e,b,h)
    def test_credential_not_allowed_in_public_header_receipt(self):
        e,b,h=example();h['Authorization']='Bearer PLACEHOLDER_FOR_TEST_NOT_A_KEY'
        with self.assertRaises(ContractError):validate_request(e,b,h)
    def test_fallback_preserves_scope_and_input(self):
        e,b,h=example('discovery_beta');b['includeDomains']=['arxiv.org'];b['endPublishedDate']='2026-09-08T00:00:00Z'
        old=copy.deepcopy(b);new,hdr=dynamic_fallback(b,h,'UNSUPPORTED_DYNAMIC_HIGHLIGHTS')
        self.assertEqual(b,old);self.assertNotIn('Exa-Beta',hdr)
        for k in ('query','category','includeDomains','endPublishedDate'):self.assertEqual(new[k],b[k])
        self.assertNotIn('dynamic',new['contents']['highlights'])
    def test_fallback_not_for_auth_or_negative_review(self):
        e,b,h=example('discovery_beta')
        for reason in ('HTTP_401','VALID_FAIL','BUDGET_EXHAUSTED','TIMEOUT','UNKNOWN_400'):
            with self.subTest(reason=reason),self.assertRaises(ContractError):dynamic_fallback(b,h,reason)
    def test_boolean_highlights_cannot_use_preview_fallback(self):
        e,b,h=example();b['contents']['highlights']=True
        with self.assertRaises(ContractError):dynamic_fallback(b,h,'UNSUPPORTED_DYNAMIC_HIGHLIGHTS')
    def test_request_shape_digest_reproducible_and_different_modes(self):
        e,b,h=example('discovery_beta');d=request_shape_digest(e,b,h)
        self.assertEqual(d,request_shape_digest(e,copy.deepcopy(b),dict(h)))
        new,hdr=dynamic_fallback(b,h,'UNSUPPORTED_DYNAMIC_HIGHLIGHTS')
        self.assertNotEqual(d,request_shape_digest(e,new,hdr))
    def test_policy_preview_default_and_budget(self):
        p=json.loads((ROOT/'specs/exa-research-policy.proposed.json').read_text())
        self.assertFalse(p['dynamic_highlights']['default_enabled'])
        self.assertFalse(p['search_profiles']['discovery_beta']['enabled_by_default'])
        self.assertEqual(sum(p['budget']['stage_allocations'].values()),80)
        self.assertEqual(p['budget']['max_total_http_attempts'],80)
    def test_compatible_profile_only_three_changed_values(self):
        p=json.loads((ROOT/'configs/exa-modeling-compatible.json').read_text())
        self.assertEqual((p['exa_max_requests'],p['exa_results_per_query'],p['exa_timeout']),(80,6,45))
        self.assertEqual(p['review_members_per_role'],2)
        self.assertIsNone(p['claude_model']);self.assertIsNone(p['codex_model'])
        self.assertEqual(p['max_model_calls'],180)
        self.assertNotIn('dynamic_highlights',p)

if __name__=='__main__':unittest.main(verbosity=2)
