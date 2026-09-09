"""Conservative relation guard, supplemented by independent semantic review.

Keep the ordered content of each scientific clause, while allowing whole-clause
reordering and a small explicit set of grammatical adjustments. Rejected broader
paraphrases need a narrower edit; this does not certify the original science.
"""
import re
import unicodedata
from collections import Counter

SENSITIVE=re.compile(r'\d|[A-Za-z]|不|未|无|否|高于|低于|超过|至少|至多|导致|使得|因果|相关|显著|证明|可能|保证|确定|[<>≤≥≠=∈∉±]|\$')


def association_records(text):
    text=unicodedata.normalize('NFKC',text)
    records=[]
    for clause in re.split(r'[。！？；;\n]|,(?!\d{3}(?:\D|$))|，',text):
        clause=re.sub(r'\s+','',clause).strip('. ')
        if not clause or not SENSITIVE.search(clause):continue
        clause=re.sub(r'^(其中|此外|另外|同时)[,:：]?', '',clause)
        clause=re.sub(r'^这里(?=采用)', '',clause)
        clause=re.sub(r'^有关说明(?=参见)', '',clause)
        clause=re.sub(r'^计算(?=使用)', '',clause)
        clause=clause.replace('之后进行比较','后比较')
        clause=clause.replace('本文所用模型','本文模型').replace('本研究所用模型','本研究模型')
        clause=re.sub(r'的(?=成本|误差|准确率|效率|收益|功率|面积|高度|距离)', '',clause)
        clause=re.sub(r'(?:为|是)(?=[+-]?(?:\d|\.\d))', '',clause)
        records.append(clause)
    return Counter(records)
