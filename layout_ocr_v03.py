"""SmartArchive-X v0.3: experimental Arabic line-level OCR, no automatic promotion.
Requires layout_ocr_v02.py in same folder. Keeps original and each OCR variant.
"""
import argparse, csv, json, re, time
from pathlib import Path
from difflib import SequenceMatcher
import cv2
import numpy as np
from layout_ocr_v02 import pages, plan_regions, read_ocr, regression_candidates


def detect_lines(crop, lang, exe):
    """Return padded bounding boxes for likely lines, via horizontal ink projection.
    A heuristic: fails on complex tables, overlapping text, handwriting.
    """
    h, w = crop.shape[:2]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    # Suppress reverse-side ghost text where possible; only use mask for finding boxes.
    mask = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                 cv2.THRESH_BINARY_INV, 31, 13)
    # Preserve diacritics and punctuation by dilating vertically a few pixels.
    k = max(2, round(h / 350))
    mask = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2*k+1)))
    proj = np.sum(mask > 0, axis=1)
    threshold = max(2, int(w * 0.006))
    occupied = np.flatnonzero(proj >= threshold)
    if len(occupied) == 0: return []
    groups = np.split(occupied, np.where(np.diff(occupied) > 1)[0]+1)
    spans = [[int(g[0]), int(g[-1]+1)] for g in groups if len(g)]
    # Merge nearby bands (Arabic diacritics may appear as distinct bands).
    merged=[]
    merge_gap=max(3, int(h*.006))
    for y0,y1 in spans:
        if merged and y0-merged[-1][1] <= merge_gap:
            merged[-1][1]=y1
        else:
            merged.append([y0,y1])
    boxes=[]
    for y0,y1 in merged:
        if y1-y0 < 5: continue
        slice_ = mask[y0:y1, :]
        xs = np.flatnonzero((slice_>0).sum(axis=0) >= 2)
        if len(xs)<max(12, int(w*.05)): continue
        pad_y=max(5,int((y1-y0)*.25))
        pad_x=max(7,int(w*.02))
        x0=max(0,int(xs[0])-pad_x);x1=min(w,int(xs[-1])+1+pad_x)
        boxes.append([x0,max(0,y0-pad_y),x1,min(h,y1+pad_y)])
    # Cross-check geometric detection against a Tesseract layout pass.
    # On ghosted pages, projection may join dozens of lines into one; recover
    # individual line boxes from recognized TSV rows instead of trusting that merge.
    if len(boxes) < max(3, int(h / 65)):
        try:
            import pytesseract
            from PIL import Image
            from collections import defaultdict
            if exe: pytesseract.pytesseract.tesseract_cmd = exe
            rgb = cv2.cvtColor(crop,cv2.COLOR_BGR2RGB)
            data=pytesseract.image_to_data(Image.fromarray(rgb),lang=lang,
                config='--oem 1 --psm 6',output_type=pytesseract.Output.DICT)
            groups=defaultdict(list)
            for i,txt in enumerate(data['text']):
                if not txt.strip(): continue
                key=tuple(data[k][i] for k in ['block_num','par_num','line_num'])
                groups[key].append(i)
            tsvboxes=[]
            for members in groups.values():
                l=min(data['left'][i] for i in members)
                t=min(data['top'][i] for i in members)
                r=max(data['left'][i]+data['width'][i] for i in members)
                b=max(data['top'][i]+data['height'][i] for i in members)
                if r-l<10 or b-t<3: continue
                px=max(6,int(w*.018));py=max(5,int((b-t)*.25))
                tsvboxes.append([max(0,l-px),max(0,t-py),min(w,r+px),min(h,b+py)])
            tsvboxes.sort(key=lambda box:(box[1],box[0]))
            if len(tsvboxes)>len(boxes): return tsvboxes
        except Exception:
            pass
    return boxes


def edit_distance(a,b):
    prev=list(range(len(b)+1))
    for i,ac in enumerate(a,1):
        curr=[i]+[0]*len(b)
        for j,bc in enumerate(b,1):
            curr[j]=min(curr[j-1]+1,prev[j]+1,prev[j-1]+(ac!=bc))
        prev=curr
    return prev[-1]


def metrics(reference,prediction):
    # Exact comparison after line-ending normalization only; no silent removal of Arabic diacritics.
    def clean(s): return s.replace('\r\n','\n').replace('\r','\n').strip()
    ref=clean(reference);pred=clean(prediction)
    rwords=ref.split();pwords=pred.split()
    return {'cer':round(edit_distance(ref,pred)/max(len(ref),1),4),
            'wer':round(edit_distance(rwords,pwords)/max(len(rwords),1),4),
            'reference_characters':len(ref),'reference_words':len(rwords)}


def run(args):
    src=Path(args.input)
    if not src.is_file(): raise FileNotFoundError(f'Input not found: {src}')
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    allrows=[]
    for page_num,image in pages(src,args.dpi):
        folder=out/f'page_{page_num:03d}';folder.mkdir(exist_ok=True)
        cv2.imwrite(str(folder/'original.png'),image)
        regions,diagnostics=plan_regions(image)
        overlay=image.copy()
        all_variants={};timings={}
        if not args.skip_ocr:
            all_variants['baseline_psm3'],timings['baseline_psm3']=read_ocr(image,args.lang,3,args.tesseract)
        region_texts=[];line_texts=[];line_records=[];region_infos=[]
        for region_id,region in enumerate(regions,1):
            x0,y0,x1,y1=region['bbox']; crop=image[y0:y1,x0:x1]
            if crop.size==0:continue
            cv2.rectangle(overlay,(x0,y0),(x1-1,y1-1),(255,70,40),2)
            cv2.imwrite(str(folder/f'region_{region_id:02d}.png'),crop)
            psm = args.header_psm if region['type']=='shared_header' else args.region_psm
            if not args.skip_ocr:
                region_text,secs=read_ocr(crop,args.lang,psm,args.tesseract)
                region_texts.append(region_text.strip())
                timings.setdefault('region_psm',0.0);timings['region_psm']+=secs
            boxes=detect_lines(crop,args.lang,args.tesseract)
            lines=[]
            for line_no,bbox in enumerate(boxes,1):
                a,b,c,d=bbox
                patch=crop[b:d,a:c]
                # upscale small line crops before passing to Tesseract
                if patch.shape[0]<args.min_line_height:
                    scale=args.min_line_height/max(patch.shape[0],1)
                    patch=cv2.resize(patch,None,fx=scale,fy=scale,interpolation=cv2.INTER_CUBIC)
                globalbox=[x0+a,y0+b,x0+c,y0+d]
                cv2.rectangle(overlay,(globalbox[0],globalbox[1]),(globalbox[2],globalbox[3]),(30,160,20),1)
                cv2.imwrite(str(folder/f'region_{region_id:02d}_line_{line_no:03d}.png'),patch)
                record={'region_type':region['type'],'region_order':region_id,'line_order':line_no,'bbox':globalbox}
                if not args.skip_ocr:
                    line,secs=read_ocr(patch,args.lang,args.line_psm,args.tesseract)
                    line=line.strip();record.update({'text':line,'seconds':secs})
                    timings.setdefault('line_psm',0.0);timings['line_psm']+=secs
                    if line:lines.append(line)
                line_records.append(record)
            region_infos.append({'type':region['type'],'bbox':region['bbox'],'lines_detected':len(boxes)})
            line_texts.append('\n'.join(lines))
        cv2.imwrite(str(folder/'layout_and_lines_overlay.png'),overlay)
        (folder/'line_blocks.json').write_text(json.dumps(line_records,ensure_ascii=False,indent=2),encoding='utf-8')
        if not args.skip_ocr:
            all_variants['region_psm']='\n\n'.join(x for x in region_texts if x).strip()+'\n'
            all_variants['line_psm']='\n\n'.join(x for x in line_texts if x).strip()+'\n'
            for name,txt in all_variants.items():
                (folder/f'{name}.txt').write_text(txt,encoding='utf-8')
            suspects=regression_candidates(all_variants['baseline_psm3'],all_variants['line_psm'])
            (folder/'potential_missing_from_baseline.json').write_text(json.dumps(suspects,ensure_ascii=False,indent=2),encoding='utf-8')
        report={'page':page_num,'image_size':[image.shape[1],image.shape[0]],'diagnostics':diagnostics,
                'regions':region_infos,'line_count':len(line_records),'timings_seconds':timings,
                'selected_automatically':False,
                'warnings':['This is a geometric line heuristic, not a trained detector.',
                            'OCR word count/confidence cannot prove accuracy.',
                            'Use ground truth with the same reading-order convention before comparing.']}
        if not args.skip_ocr:
            report['variants']={k:{'characters':len(v),'seconds':round(timings.get(k,0),3)} for k,v in all_variants.items()}
            report['potential_missing_snippets']=len(suspects)
            # User-provided correct transcript. A single page can use --ground-truth FILE;
            # multipage input requires --ground-truth-dir/page_001.txt etc.
            ref_path=Path(args.ground_truth) if args.ground_truth else (Path(args.ground_truth_dir)/f'page_{page_num:03d}.txt' if args.ground_truth_dir else None)
            if ref_path and ref_path.is_file():
                reference=ref_path.read_text(encoding='utf-8-sig')
                report['ground_truth_source']=str(ref_path)
                report['accuracy']={k:metrics(reference,v) for k,v in all_variants.items()}
            elif ref_path:
                report['ground_truth_missing']=str(ref_path)
            for name,txt in all_variants.items():
                a={'page':page_num,'method':name,'chars':len(txt),'seconds':round(timings.get(name,0),3)}
                if 'accuracy' in report:a.update({k:report['accuracy'][name][k] for k in ['cer','wer']})
                allrows.append(a)
        (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(f'Page {page_num}: {len(regions)} regions; {len(line_records)} line boxes; ground truth:', 'yes' if 'accuracy' in report else 'no')
    if allrows:
        with (out/'comparison.csv').open('w',newline='',encoding='utf-8-sig') as f:
            writer=csv.DictWriter(f,fieldnames=['page','method','chars','seconds']+(['cer','wer'] if any('cer' in r for r in allrows) else []))
            writer.writeheader();writer.writerows(allrows)
    print('Completed:',out)
    print('CAUTION: outputs are experiments, not automatically trusted archival transcriptions.')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',required=True)
    p.add_argument('--output',default='results/layout_ocr_v03')
    p.add_argument('--dpi',type=int,default=250)
    p.add_argument('--lang',default='ara')
    p.add_argument('--region-psm',type=int,default=6)
    p.add_argument('--line-psm',type=int,default=7)
    p.add_argument('--header-psm',type=int,default=7)
    p.add_argument('--min-line-height',type=int,default=42)
    p.add_argument('--tesseract',default=r'C:\Program Files\Tesseract-OCR\tesseract.exe')
    p.add_argument('--ground-truth',help='UTF-8 correct transcription for single page only')
    p.add_argument('--ground-truth-dir',help='Directory of page_001.txt etc. for multi-page PDFs')
    p.add_argument('--skip-ocr',action='store_true')
    args=p.parse_args()
    if args.ground_truth and args.ground_truth_dir:p.error('Use only one ground-truth option')
    if args.ground_truth and Path(args.input).suffix.lower()=='.pdf':
        p.error('For PDFs, use --ground-truth-dir with page_001.txt etc.')
    run(args)
