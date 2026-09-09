"""Native PaperKit additions: symbol table and truthful usage disclosure."""
from __future__ import annotations
from .common import IntegrityError, digest
from .role_skills import ROLE_PURPOSES


def symbols_latex(materials):
    if not materials:return []
    from .paper import esc,equation
    plan=materials['plan'];mapping=materials['paper_map']
    if mapping['symbols']!=plan['variables']:
        # The checker permits a reordered symbol table; match by key, never by guess.
        if {r['symbol']:r for r in mapping['symbols']}!={r['symbol']:r for r in plan['variables']}:
            raise IntegrityError('Symbol table differs from the model')
    lines=[r'\section{符号说明}',
           r'\begin{longtable}{p{.18\linewidth}p{.52\linewidth}p{.20\linewidth}}',
           r'\toprule 符号 & 含义 & 单位\\\midrule\endhead']
    for row in mapping['symbols']:
        lines.append('$'+equation(row['symbol'])+'$ & '+esc(row['meaning'])+' & '+esc(row['unit'])+r'\\')
    lines+=[r'\bottomrule\end{longtable}']
    return lines


def usage_statement(records,demo=False):
    if demo:
        return ('本工程演示使用显式角色回复夹具，未调用真实Codex或Claude；数值与排版验证的执行范围见支撑材料。'
                '这不是当届赛题解答，未取得正式参赛人工签核。')
    if not records:raise IntegrityError('A live AI-assisted paper needs actual usage records')
    if any(r.get('transport')=='FIXTURE_NOT_LLM' for r in records):
        raise IntegrityError('Fixture cannot be described as actual AI usage')
    purposes=list(dict.fromkeys(ROLE_PURPOSES[r['role']] for r in records if r.get('role') in ROLE_PURPOSES))
    if not purposes:raise IntegrityError('Missing real purpose metadata')
    return ('本参赛队在竞赛过程中使用了AI工具，主要用于'+ '、'.join(purposes)+
            '，详细使用情况见支撑材料。具体记录见《AI工具使用详情.pdf》，人工核验状态以真实签核记录为准。')


def usage_lines(record):
    """Public, source-derived disclosure. No raw prompt, secrets or guessed version."""
    from .paper import esc
    item=record.get('usage_disclosure')
    if not item:
        return ['主要提示方式：此历史回执未保存实际输入字段与提示方式；不可用默认角色说明补造。'+r'\par']
    if item.get('skill_digest')!=record.get('skill_digest'):
        raise IntegrityError('Usage skill digest mismatch')
    # Packet keys are identifiers, so TeX's word hyphenation does not split them.
    # Escape source text first, then add legal breaks at the escaped separators.
    fields='、'.join(esc(field).replace(r'\_',r'\_\allowbreak{}') for field in item['actual_input_fields'])
    return [esc('目的与环节：'+item['stage']+'；'+item['purpose'])+r'\par',
            '实际输入类别：'+fields+r'\par',
            esc('主要提示方式：'+item['prompt_method'])+r'\par',
            esc('输出与过程：'+item['output_summary'])+r'\par',
            esc('本次是否产生可用模型回复：'+record.get('model_execution_status','返回已校验结构化结果')).replace(r'\_',r'\_\allowbreak{}')+r'\par']


def claim_display(key,claim):
    labels={'mean_baseline':'基准确认均值','mean_improvement':'配对平均改善',
        'ci_low':'改善区间下界','ci_high':'改善区间上界','result_hv':'代表运行超体积',
        'result_reward':'代表方案收益','result_duration':'代表方案总时长'}
    name=labels.get(key)
    if name is None:name=('候选 '+key[5:]+' 确认均值') if key.startswith('mean_') else key
    unit={'normalized_hv':'无量纲','ratio':'无量纲','reward_units':'收益单位','minutes':'分钟'}.get(claim['unit'],claim['unit'])
    return name,unit
