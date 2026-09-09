"""First-party office/PDF worker, invoked only through the restricted executor."""
from pathlib import Path
import argparse,shutil,subprocess,re,unicodedata,zipfile
from collections import Counter
from cumcm_harness.common import IntegrityError,file_hash,write_json


def metrics(pdf,out):
    import fitz
    out.mkdir(parents=True,exist_ok=True);text=[];pages=[];outside=[]
    with fitz.open(pdf) as doc:
        if not 1<=len(doc)<=100:raise IntegrityError('Unsupported editorial page count')
        for i,page in enumerate(doc):
            body=page.get_text();text.append(body)
            for block in page.get_text('blocks'):
                if block[6]!=0:continue
                rect=fitz.Rect(block[:4]);bounds=page.rect+(-1,-1,1,1)
                if not bounds.contains(rect):outside.append({'page':i+1,'bbox':list(rect)})
            png=out/f'page-{i+1:03d}.png';page.get_pixmap(matrix=fitz.Matrix(1.2,1.2)).save(png)
            pages.append({'page':i+1,'width':page.rect.width,'height':page.rect.height,'image':png.name,'sha256':file_hash(png)})
    content=unicodedata.normalize('NFKC','\n'.join(text))
    from cumcm_harness.entry_documents import protected_tokens
    return {'pages':pages,'page_count':len(pages),'pdf_sha256':file_hash(pdf),'text':content,
        'technical_tokens':dict(protected_tokens(content)),'text_outside_page':outside,
        'replacement_glyphs':content.count('\ufffd'),'visual_review':'REQUIRED_SEPARATELY'}


def run(input_dir,out):
    out.mkdir(parents=True,exist_ok=True);rendered={}
    for label in ('before','after'):
        sources=list(input_dir.glob(label+'.*'))
        if len(sources)!=1:raise IntegrityError('Expected exact original and actual edited input pair')
        source=sources[0];folder=out/label;folder.mkdir()
        pdf=folder/(label+'.pdf')
        if source.suffix=='.docx':
            profile=Path('/tmp')/('cumcm-office-'+label)
            command=['soffice','-env:UserInstallation='+profile.as_uri(),'--headless','--convert-to','pdf','--outdir',str(folder),str(source)]
            proc=subprocess.run(command,capture_output=True,timeout=150)
            (folder/'office.stdout.log').write_bytes(proc.stdout);(folder/'office.stderr.log').write_bytes(proc.stderr)
            if proc.returncode or not pdf.is_file():raise IntegrityError('Office converter failed to produce the actual document PDF')
        elif source.suffix=='.pdf':shutil.copy2(source,pdf)
        else:raise IntegrityError('Unsupported isolated rendering input')
        result=metrics(pdf,folder/'pages')
        # A preserved OOXML equation must also remain visible; Writer without
        # Math can silently drop it. Complex extraction stays pending review.
        if source.suffix=='.docx':
            from lxml import etree as ET
            from cumcm_harness.entry_documents import M
            with zipfile.ZipFile(source) as z:body=ET.fromstring(z.read('word/document.xml'))
            equations=[''.join(e.itertext()) for e in body.iter('{'+M+'}oMath')]
            normalize=lambda s:re.sub(r'\s+','',unicodedata.normalize('NFKC',s))
            result['source_equations']=equations
            result['source_equations_visible']=all(normalize(s) in normalize(result['text']) for s in equations)
        else:result['source_equations_visible']=None
        (folder/'extracted.txt').write_text(result.pop('text'))
        rendered[label]=result
    a,b=rendered['before'],rendered['after']
    checks={'rendered_numeric_formula_citation_tokens_unchanged':a['technical_tokens']==b['technical_tokens'],
        'no_text_outside_page':not a['text_outside_page'] and not b['text_outside_page'],
        'no_replacement_glyphs':a['replacement_glyphs']==b['replacement_glyphs']==0,
        'original_and_modified_equations_visible':all(x['source_equations_visible'] is not False for x in (a,b)),
        'page_count_preserved':a['page_count']==b['page_count']}
    write_json(out/'layout.json',{'status':'RENDERED_PENDING_VISUAL_REVIEW' if all(checks.values()) else 'DRAFT_PENDING_LAYOUT',
        'input_hashes':{p.name:file_hash(p) for p in input_dir.iterdir()},'documents':rendered,'checks':checks,
        'science_revalidated':False,'citation_truth_revalidated':False,'same_page_count_does_not_prove_same_layout':True})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();run(a.input,a.out)
