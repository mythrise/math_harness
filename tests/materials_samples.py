from copy import deepcopy
from cumcm_harness.common import digest
from cumcm_harness.materials_contracts import STEPS

PROBLEM='第一问：估计模型并报告误差。第二问：解释模型适用边界。约束：仅使用已提供的历史记录。'

def samples():
    sentences=PROBLEM.split('。')[:3];requirements=[]
    for i,text in enumerate(sentences):
        a=PROBLEM.index(text);requirements.append({'id':f'R{i+1}','kind':'deliverable' if i<2 else 'constraint',
            'statement':text,'anchor':{'start':a,'end':a+len(text),'quote':text},'question_ids':[f'Q{i+1}'] if i<2 else ['Q1','Q2']})
    brief={'problem_sha256':digest(PROBLEM),'questions':[], 'requirements':requirements,'ambiguities':[],
        'unit_risks':['数值单位来自输入定义，不从教程推测。'],'completion_criteria':['逐问产物对应真实运行。']}
    for i in range(2):brief['questions'].append({'id':f'Q{i+1}','title':sentences[i],'direct_goal':sentences[i],
        'inferred_goal':'不对未见分布作无依据推广','inputs':['history.csv'],'outputs':['误差报告' if i==0 else '适用边界说明'],
        'constraint_ids':['R3'],'depends_on':[] if i==0 else ['Q1'],'answer_type':'quantitative' if i==0 else 'qualitative',
        'family':'prediction' if i==0 else 'statistics'})
    audit={'files':[{'file':'history.csv'}]}
    data={'sampling_unit':'独立序列','split':'time','group_key':'NOT_APPLICABLE','time_key':'t',
        'sources':[{'file':'history.csv','origin':'provided','purpose':'observed_evidence','source_id':'NOT_APPLICABLE'}],
        'transforms':[{'file':'history.csv','operation':'none','columns':[],'reason':'本例完整，不需要填补。',
            'fit_scope':'none','time_causal':True,'raw_immutable':True,'output_path':'processed/history.csv','verification':'校验原始摘要不变。'}],
        'required_data':[],'optional_data':[],'leakage_checks':['按时间划分，预处理不看未来。'],'quality_checks':['读取范围和缺失情况保留。']}
    methods=[{'id':'regression'},{'id':'statistics'}]
    portfolio={'questions':[],'shared_computation':['只复用不依赖折的输入解析。'],'rejected_innovations':['没有证据就不强行融合。'],'stopping_rule':'达到冻结预算则停止。'}
    for i in range(2):portfolio['questions'].append({'question_id':f'Q{i+1}','options':[{'id':f'M{i+1}','kind':'baseline',
        'method_card_id':methods[i]['id'],'principle':'使用题意允许的基本估计方法。','fit_reason':'适合当前样本与可识别参数。',
        'limitations':'样本外规律尚未验证。','validation':'独立留出误差与边界检查。','single_change':'无，基准方法。','implementation_status':'AVAILABLE_LOCAL'}],
        'recommendation':f'M{i+1}','decision_basis':'在冻结预算下可执行并可独立核验。'})
    plan={'summary':'验证分层交接接口。','assumptions':['这是一项固定合成问题的工程测试。'],
        'questions':[{'id':'Q1','question':sentences[0],'metric':'mae','unit':'units','acceptance':'独立重算误差。'},
                     {'id':'Q2','question':sentences[1],'metric':'boundary','unit':'text','acceptance':'保留事实与限制。','answer_type':'qualitative'}],
        'tasks':[{'id':'estimate','depends_on':[],'goal':'拟合与验证','algorithm_skill':'regression','outputs':['answer.json']},
                 {'id':'interpret','depends_on':['estimate'],'goal':'说明限制','algorithm_skill':'statistics','outputs':['scope.txt']}],
        'variables':[{'symbol':'t','meaning':'观测时间','unit':'day'},{'symbol':'y','meaning':'目标变量','unit':'units'}],
        'equations':[r'y=a+bt'],'constraints':['只用历史观测。'],'baseline':'常数预测。',
        'ablations':[{'id':'no_trend','change':'关闭趋势项。'}],'sensitivity':[{'id':'short_history','change':'缩短历史。'}],
        'limitations':['未建立跨数据集泛化。'],'primary_metric':'mae','direction':'minimize','min_effect':0.0,
        'evaluator_spec':'独立重算预测误差及逐问证据。','resources':{'cpu_threads':1,'memory_mb':512,'expected_seconds':10.0,'row_sharding':False,'checkpointing':False,'fold_invariant_precompute':True}}
    claims={'result_error':{'value':0.2,'unit':'units','question_id':'Q1','evidence':[{'job_id':'example','selector':'error'}]}}
    draft={'title':'固定合成序列的预测与适用边界','abstract':'独立误差为{{claim:result_error}}，仅适用当前测试。',
        'keywords':['模型核验','时间序列'],'sections':[{'heading':'问题重述','text':'逐问回答误差与边界，不引入新数据。','equations':[],'claim_ids':[]},
            {'heading':'建模、求解与检验','text':'固定关系经实际估计后，由独立评价核验，误差为{{claim:result_error}}。受样本范围限制，不外推为通用结论。',
             'equations':[r'y=a+bt'],'claim_ids':['result_error']}], 'limitations':['仅用于流程工程检验。'],'figure_caption':'逐问任务与证据流。','citation_ids':[]}
    ev=[{'id':'qe_a','question_id':'Q2','text':'仅限固定合成序列，不证明外推能力。'}]
    mapping={'draft_digest':digest(draft),'questions':[], 'symbols':deepcopy(plan['variables']), 'abstract_claim_ids':['result_error'],'limitations':['仅结构检查。']}
    for i in range(2):mapping['questions'].append({'question_id':f'Q{i+1}',
        'bindings':[{'step':k,'section_indices':[1],'state':'PRESENT','reason':'定位到当前模型和结果段落，语义充分性仍需审查。'} for k in STEPS],
        'claim_ids':['result_error'] if i==0 else [],'qualitative_evidence_ids':['qe_a'] if i else []})
    return brief,data,audit,portfolio,methods,plan,draft,claims,ev,mapping
