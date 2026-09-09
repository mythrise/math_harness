"""Production orchestration must bind actual edits and rendered page receipts."""
from pathlib import Path
import copy
import pytest
from cumcm_harness.common import IntegrityError,InfrastructureUnavailable,UnknownExternalState,file_hash,digest,read_json,write_json,tree_manifest
from cumcm_harness.entry_documents import read_document,sha_text
from cumcm_harness.revision_layout import prepare_revision
from cumcm_harness.store import Store
from test_three_inputs_revision import setup_revision,responder
from cumcm_harness.paper_revision import RevisionController
from cumcm_harness.providers import FixtureProvider


def stub_production_models(c,monkeypatch):
    # Test the production document branch with explicit transport-free stubs.
    # No LIVE receipt is invented, and no reviewer/provider contract is weakened.
    monkeypatch.setattr(c.review_board,'invoke',lambda key,role,schema,packet,**kw:{'result':responder(role,schema,packet),'receipt':{'fixture':True}})
    def review(key,target,**kw):
        return c.store.step('test:review:'+key,{'target':digest(target),'stage':kw['stage']},lambda:[{'fixture':True,'target_digest':digest(target)}])
    monkeypatch.setattr(c,'reviews',review)
    monkeypatch.setattr(c,'all_ai_records',lambda:[])

def source_and_patch(tmp_path):
    source=tmp_path/'paper.tex';source.write_text('本文模型的误差为 0.25。')
    doc=read_document(source,purpose='paper');b=doc['blocks'][0]
    return source,doc,[{'block_id':b['id'],'before_sha256':b['sha256'],'replacement':'本文所用模型的误差为 0.25。','reason':'只改变语言连接，数值和含义全部保留。'}]


def test_actual_edited_source_sent_to_renderer_and_replayed(tmp_path,monkeypatch):
    source,doc,edits=source_and_patch(tmp_path);store=Store(tmp_path/'run');seen=[]
    def render(before,after,folder):
        seen.append((before.read_text(),after.read_text()))
        assert after.read_text()==edits[0]['replacement'] and before==source
        folder.mkdir();write_json(folder/'real-input-hashes.json',{'before':file_hash(before),'after':file_hash(after)})
        return {'status':'RENDERED_PENDING_VISUAL_REVIEW','source_sha256':file_hash(before),'modified_sha256':file_hash(after)}
    monkeypatch.setattr('cumcm_harness.revision_layout.render_actual_pair',render)
    result=prepare_revision(store,source,doc,edits,fixture=False)
    assert len(seen)==1 and result['layout']['modified_sha256']==file_hash(store.root/result['directory']/result['revised_name'])
    assert prepare_revision(store,source,doc,edits,fixture=False)==result and len(seen)==1
    assert file_hash(source)==doc['source_sha256']


def test_missing_render_tool_is_explicit_draft(tmp_path,monkeypatch):
    source,doc,edits=source_and_patch(tmp_path);store=Store(tmp_path/'run')
    def absent(*a):raise InfrastructureUnavailable('document image absent')
    monkeypatch.setattr('cumcm_harness.revision_layout.render_actual_pair',absent)
    result=prepare_revision(store,source,doc,edits,fixture=False)
    assert result['layout']['status']=='DRAFT_PENDING_LAYOUT'
    assert 'image absent' in result['layout']['reason'] and not result['layout']['contest_ready']
    assert (store.root/result['directory']/result['revised_name']).exists()


def test_unknown_render_is_not_retried_or_called_a_draft(tmp_path,monkeypatch):
    source,doc,edits=source_and_patch(tmp_path);store=Store(tmp_path/'run')
    def unknown(*a):raise UnknownExternalState('reconcile actual renderer first')
    monkeypatch.setattr('cumcm_harness.revision_layout.render_actual_pair',unknown)
    with pytest.raises(UnknownExternalState):prepare_revision(store,source,doc,edits,fixture=False)
    assert not (store.root/'deliverables').exists()


def test_prepared_document_tamper_blocks_export_replay(tmp_path):
    source,doc,edits=source_and_patch(tmp_path);store=Store(tmp_path/'run')
    result=prepare_revision(store,source,doc,edits,fixture=True)
    (store.root/result['directory']/result['revised_name']).write_text('tampered')
    with pytest.raises(IntegrityError):prepare_revision(store,source,doc,edits,fixture=True)


def test_production_copy_without_layout_never_requests_submission_approval(tmp_path,monkeypatch):
    root,source=setup_revision(tmp_path,'docx');c=RevisionController(root,fixture_provider=FixtureProvider(responder))
    # Explicit fixture models testing production branch plumbing, not LIVE evidence.
    c.demo=False;c.config['mode']='contest';stub_production_models(c,monkeypatch)
    seen=[]
    def absent(*a):raise InfrastructureUnavailable('fixture missing renderer')
    monkeypatch.setattr('cumcm_harness.revision_layout.render_actual_pair',absent)
    monkeypatch.setattr('cumcm_harness.approval.request',lambda *a,**k:seen.append('approval'))
    result=c._revision_run()
    assert not seen and result['status']=='EDITORIAL_COPY_DRAFT_PENDING_LAYOUT' and not result['contest_ready']
    assert read_json(root/'deliverables/revision-report.json')['original_layout_render_review']=='DRAFT_PENDING_LAYOUT'
    assert not (root/'deliverables/revised.pdf').exists()


def test_production_visual_review_is_bound_to_actual_pages_and_replays(tmp_path,monkeypatch):
    from PIL import Image
    root,source=setup_revision(tmp_path,'docx');provider=FixtureProvider(responder);c=RevisionController(root,fixture_provider=provider);c.demo=False;stub_production_models(c,monkeypatch)
    def render(before,after,folder):
        folder.mkdir()
        for label in ('before','after'):
            pages=folder/'output'/label/'pages';pages.mkdir(parents=True)
            Image.new('RGB',(10,10),'white').save(pages/'page-001.png')
            (folder/'output'/label/(label+'.pdf')).write_bytes(b'EXPLICIT_TEST_RENDER_STUB')
        return {'status':'RENDERED_PENDING_VISUAL_REVIEW','source_sha256':file_hash(before),'modified_sha256':file_hash(after),'checks':{'fixture':True}}
    monkeypatch.setattr('cumcm_harness.revision_layout.render_actual_pair',render)
    original=c.reviews;calls=[]
    def reviews(key,target,**kwargs):
        if kwargs['stage']=='editorial_layout':
            calls.append(kwargs);assert len(kwargs['images'])==2
            assert [x['sha256'] for x in target['page_images']]==[file_hash(p) for p in kwargs['images']]
        return original(key,target,**kwargs)
    monkeypatch.setattr(c,'reviews',reviews)
    result=c.run();reserved=c.store.get('model_calls_reserved');manifest=tree_manifest(root/'deliverables')
    assert result['layout_status']=='LAYOUT_REVIEW_COMPLETE_NOT_SCIENTIFIC_REVALIDATION' and calls
    assert (root/'deliverables/revised.pdf').exists()
    c.run();assert c.store.get('model_calls_reserved')==reserved and tree_manifest(root/'deliverables')==manifest
