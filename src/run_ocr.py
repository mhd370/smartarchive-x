"""SmartArchive-X OCR baseline experiment (not the final adaptive router)."""
import argparse, csv, hashlib, json, re, time
from pathlib import Path
from PIL import Image
import fitz

IMAGE_EXT={'.png','.jpg','.jpeg','.tif','.tiff','.bmp'}

def edit_distance(a,b):
    previous=list(range(len(b)+1))
    for i,x in enumerate(a,1):
        current=[i]
        for j,y in enumerate(b,1):
            current.append(min(current[j-1]+1,previous[j]+1,previous[j-1]+(x!=y)))
        previous=current
    return previous[-1]

def normalize(s):
    # Conservative: whitespace only; no letter/hamza/number removal.
    return re.sub(r'\s+',' ',s).strip()

def metrics(pred, gold):
    a,b=normalize(gold),normalize(pred)
    return {'cer':edit_distance(list(a),list(b))/max(1,len(a)),
            'wer':edit_distance(a.split(),b.split())/max(1,len(a.split()))}

def iter_pages(path,dpi):
    if path.suffix.lower()=='.pdf':
        with fitz.open(path) as pdf:
            for idx,page in enumerate(pdf):
                pix=page.get_pixmap(dpi=dpi,alpha=False)
                yield idx+1,Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
    elif path.suffix.lower() in IMAGE_EXT:
        with Image.open(path) as im:
            yield 1,im.convert('RGB').copy()

def tesseract_ocr(image):
    import pytesseract
    from pytesseract import Output
    raw=pytesseract.image_to_data(image,lang='ara+eng',config='--psm 3',output_type=Output.DICT)
    blocks=[]
    for i,s in enumerate(raw['text']):
        if not str(s).strip(): continue
        try: confidence=float(raw['conf'][i])
        except (ValueError,TypeError): confidence=-1
        blocks.append({'text':s,'bbox':[int(raw[k][i]) for k in ('left','top','width','height')],
                       'confidence':confidence/100 if confidence>=0 else None})
    return {'text':pytesseract.image_to_string(image,lang='ara+eng',config='--psm 3'), 'blocks':blocks}

def paddle_ocr(image):
    import numpy as np
    from paddleocr import PaddleOCR
    # Version 3.x prediction API, Arabic language support varies by released model/version.
    engine=PaddleOCR(lang='ar',use_doc_orientation_classify=False,use_doc_unwarping=False,use_textline_orientation=False)
    result=engine.predict(np.array(image))
    blocks=[]
    for item in result:
        d=item.json if hasattr(item,'json') else item
        if isinstance(d,str):d=json.loads(d)
        if 'res' in d:d=d['res']
        for txt,score,poly in zip(d.get('rec_texts',[]),d.get('rec_scores',[]),d.get('rec_polys',[])):
            blocks.append({'text':txt,'confidence':float(score),'polygon':getattr(poly,'tolist',lambda:poly)()})
    return {'text':'\n'.join(x['text'] for x in blocks),'blocks':blocks}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--input',default='data/input');ap.add_argument('--output',default='results')
    ap.add_argument('--ground-truth',default='data/ground_truth')
    ap.add_argument('--engines',nargs='+',choices=['tesseract','paddle'],default=['tesseract'])
    ap.add_argument('--dpi',type=int,default=300)
    args=ap.parse_args()
    source=Path(args.input); out=Path(args.output); gt=Path(args.ground_truth)
    out.mkdir(parents=True,exist_ok=True)
    paths=sorted(p for p in source.iterdir() if p.is_file() and (p.suffix.lower() in IMAGE_EXT|{'.pdf'})) if source.exists() else []
    if not paths:raise SystemExit('No PDF/images in input folder. Add authorized samples first.')
    records=[]
    for path in paths:
        fingerprint=hashlib.sha256(path.read_bytes()).hexdigest()
        for page_no,image in iter_pages(path,args.dpi):
            key=f'{path.stem}__p{page_no:03d}'
            # ground truth filename convention: original filename stem + page number
            truth=gt/f'{key}.txt'
            gold=truth.read_text(encoding='utf-8') if truth.exists() else None
            for engine_name in args.engines:
                t0=time.perf_counter(); error=None
                try: result={'tesseract':tesseract_ocr,'paddle':paddle_ocr}[engine_name](image)
                except Exception as exc:
                    error=f'{type(exc).__name__}: {exc}'; result={'text':'','blocks':[]}
                elapsed=round(time.perf_counter()-t0,4)
                row={'file':path.name,'sha256':fingerprint,'page':page_no,'page_id':key,'engine':engine_name,
                     'dpi':args.dpi,'width':image.width,'height':image.height,'seconds':elapsed,
                     'gt_available':gold is not None,'error':error,'cer':None,'wer':None}
                if gold is not None and error is None:row.update(metrics(result['text'],gold))
                records.append(row)
                payload={**row,**result}
                (out/f'{key}__{engine_name}.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
                print(key,engine_name,'FAILED' if error else 'OK',elapsed,'sec',f"CER={row['cer']:.4f}" if row['cer'] is not None else '(no GT)')
    with (out/'metrics.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(records[0]));writer.writeheader();writer.writerows(records)
    print('Saved',out/'metrics.csv','| evaluated',sum(r['cer'] is not None for r in records),'engine-page pairs')
if __name__=='__main__':main()
