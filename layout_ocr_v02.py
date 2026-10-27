"""SmartArchive-X Layout-Aware OCR v0.2. Heuristic prototype, not learned layout AI.
Never replaces originals; tracks tentative regions and flags OCR regressions.
"""
import argparse
import json
import re
import time
from pathlib import Path
from difflib import SequenceMatcher
import cv2
import numpy as np


def pages(path, dpi):
    if path.suffix.lower() == '.pdf':
        import fitz
        with fitz.open(path) as doc:
            for i, pg in enumerate(doc, 1):
                pix = pg.get_pixmap(matrix=fitz.Matrix(dpi/72, dpi/72), alpha=False)
                a = np.frombuffer(pix.tobytes('png'), np.uint8)
                yield i, cv2.imdecode(a, cv2.IMREAD_COLOR)
    else:
        arr = np.fromfile(str(path), dtype=np.uint8)
        im = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if im is None: raise ValueError(f'Could not load {path}')
        yield 1, im


def ink_mask(im):
    gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    return cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                 cv2.THRESH_BINARY_INV, 31, 13)


def guess_divider(ink):
    h, w = ink.shape
    if w < 420 or h < 300: return None, {'reason': 'small_page'}
    body = ink[int(.16*h):int(.92*h)] > 0
    density = body.mean(axis=0)
    smoothed = np.convolve(density, np.ones(9)/9, mode='same')
    x0, x1 = int(.33*w), int(.67*w)
    center = smoothed[x0:x1]
    threshold = max(.012, float(np.quantile(center, .30)))
    candidates = np.flatnonzero(center <= threshold)
    groups = np.split(candidates,np.where(np.diff(candidates)>1)[0]+1) if len(candidates) else []
    groups = [g for g in groups if len(g)>=max(7,int(.012*w))]
    if not groups: return None, {'reason':'no_clear_gutter'}
    best = max(groups,key=lambda g: (len(g),-abs(x0+g.mean()-w/2)))
    start,end = x0+int(best[0]), x0+int(best[-1])+1
    l = smoothed[int(.12*w):max(int(.12*w)+1,start-8)].mean()
    r = smoothed[min(w-1,end+8):int(.88*w)].mean()
    gap = smoothed[start:end].mean()
    if min(l,r)<.008 or gap>.58*min(l,r):
        return None, {'reason':'ambiguous_columns','density':[float(l),float(gap),float(r)]}
    div = (start+end)//2
    return div, {'reason':'two_column_gutter','divider_x':div,'gutter_x':[start,end],
                 'confidence_heuristic':round(float(np.clip((min(l,r)-gap)/max(min(l,r),1e-5),0,1)),3)}


def find_spanning_header(ink, divider):
    """Find a top centered text LINE overlapping the intercolumn split; never take arbitrary body lines.
    This is conservative and primarily handles printed centered headings.
    """
    h,w=ink.shape
    if divider is None: return None, 'not_multicolumn'
    top=ink[:int(h*.18)]
    # Join glyphs into lines, keeping text lines on separate rows.
    kernel=cv2.getStructuringElement(cv2.MORPH_RECT,(max(13,int(w*.035)),3))
    merged=cv2.dilate(top,kernel,iterations=1)
    n,_,stats,_=cv2.connectedComponentsWithStats(merged,8)
    opts=[]
    for x,y,bw,bh,area in stats[1:]:
        if bh<8 or bw<int(w*.09) or bw>int(w*.80): continue
        if not (x < divider-3 and x+bw > divider+3): continue
        if y>int(h*.11): continue
        # avoid selecting a whole textual paragraph; thin line candidates only
        if bh>int(h*.055): continue
        opts.append((y,x,bw,bh))
    if not opts: return None, 'no_spanning_header_found'
    y,x,bw,bh=sorted(opts)[0]
    pad=max(4,int(h*.007))
    cutoff=int(min(h, y+bh+pad))
    # Use full page width to avoid trimming the header's first/last letters.
    return (0,0,w,cutoff), 'top_centered_spanning_line_heuristic'


def plan_regions(im):
    h,w=im.shape[:2]
    ink=ink_mask(im)
    div, diag=guess_divider(ink)
    if div is None:
        return [{'type':'single_page','bbox':[0,0,w,h]}],diag
    header,header_reason=find_spanning_header(ink,div)
    diag['header_detection']=header_reason
    regions=[]
    body_y=header[3] if header else 0
    if header:
        regions.append({'type':'shared_header','bbox':list(header)})
    overlap=max(2,int(w*.009))
    regions.extend([
        {'type':'right_column','bbox':[max(0,div-overlap),body_y,w,h]},
        {'type':'left_column','bbox':[0,body_y,min(w,div+overlap),h]},
    ])
    # If title was not located, make it an explicit concern: do not say it was preserved.
    if not header: diag['warning']='Spanning titles may still be split. Inspect overlay.'
    return regions,diag


def read_ocr(im,lang,psm,exe):
    import pytesseract
    from PIL import Image
    if exe: pytesseract.pytesseract.tesseract_cmd=exe
    start=time.perf_counter()
    text=pytesseract.image_to_string(Image.fromarray(cv2.cvtColor(im,cv2.COLOR_BGR2RGB)),
                                     lang=lang,config=f'--oem 1 --psm {psm}')
    return text,round(time.perf_counter()-start,3)


def normalize(text):
    # Normalize spaces and limited Arabic variations only for regression diagnostics.
    text=re.sub(r'[\u064b-\u065f\u0670\u0640]','',text)
    return re.sub(r'\s+',' ',text).strip()


def regression_candidates(baseline, candidate):
    """Heuristic snippets that appear in baseline but not output. NOT verified ground truth."""
    base_words=normalize(baseline).split()
    alt_words=normalize(candidate).split()
    matcher=SequenceMatcher(None,base_words,alt_words,autojunk=False)
    pieces=[]
    for op,a,b,c,d in matcher.get_opcodes():
        if op in ('delete','replace') and b-a>=3:
            fragment=' '.join(base_words[a:b])
            if len(fragment)>=14:
                pieces.append({'baseline_candidate':fragment[:260], 'words':b-a})
    return pieces[:35]


def main(opts):
    source=Path(opts.input)
    if not source.exists(): raise FileNotFoundError(source)
    output=Path(opts.output);output.mkdir(parents=True,exist_ok=True)
    runs=[]
    for index,img in pages(source,opts.dpi):
        folder=output/f'page_{index:03d}';folder.mkdir(exist_ok=True)
        h,w=img.shape[:2]
        overlay=img.copy()
        regions,diag=plan_regions(img)
        cv2.imwrite(str(folder/'original.png'),img)
        report={'page':index,'page_size':[w,h],'detection':diag,'regions':[]}
        baseline='';texts=[]
        if not opts.skip_ocr:
            baseline,sec=read_ocr(img,opts.lang,3,opts.tesseract)
            (folder/'baseline_psm3.txt').write_text(baseline,encoding='utf-8')
            report['baseline']={'characters':len(baseline),'seconds':sec}
        colors={'shared_header':(10,180,40),'right_column':(0,40,240),
                'left_column':(240,80,0),'single_page':(0,40,240)}
        for number,region in enumerate(regions,1):
            x0,y0,x1,y1=region['bbox']
            crop=img[y0:y1,x0:x1]
            if not crop.size: continue
            color=colors[region['type']]
            cv2.rectangle(overlay,(x0,y0),(x1-1,y1-1),color,2)
            cv2.putText(overlay,f'{number}: {region["type"]}',(x0+5,min(y1-5,max(18,y0+19))),
                        cv2.FONT_HERSHEY_SIMPLEX,.47,color,2)
            cv2.imwrite(str(folder/f'region_{number:02d}.png'),crop)
            item={**region,'order':number}
            if not opts.skip_ocr:
                psm=opts.header_psm if region['type']=='shared_header' else opts.psm
                text,seconds=read_ocr(crop,opts.lang,psm,opts.tesseract)
                (folder/f'region_{number:02d}_ocr.txt').write_text(text,encoding='utf-8')
                texts.append(text.strip())
                item.update({'characters':len(text),'seconds':seconds,'psm':psm})
            report['regions'].append(item)
        cv2.imwrite(str(folder/'layout_overlay.png'),overlay)
        if not opts.skip_ocr:
            combined='\n\n'.join(t for t in texts if t)+'\n'
            (folder/'rtl_reading_order.txt').write_text(combined,encoding='utf-8')
            candidates=regression_candidates(baseline,combined)
            (folder/'potential_missing_from_baseline.json').write_text(json.dumps(candidates,ensure_ascii=False,indent=2),encoding='utf-8')
            report['comparison']={'combined_characters':len(combined),
                                  'baseline_characters':len(baseline),
                                  'possible_missing_snippets':len(candidates),
                                  'automatically_accepted':False,
                                  'note':'Baseline may contain errors; differences do not establish omissions or CER/WER.'}
        (folder/'layout_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        runs.append(report)
        print(f'Page {index}: {[r["type"] for r in regions]} | {diag["reason"]}')
    (output/'summary.json').write_text(json.dumps(runs,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Completed:',output,'| Review overlays, OCR text and potential_missing_from_baseline.json')


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--input',required=True)
    ap.add_argument('--output',default='results/layout_ocr_v02')
    ap.add_argument('--dpi',type=int,default=250)
    ap.add_argument('--lang',default='ara')
    ap.add_argument('--psm',type=int,default=6)
    ap.add_argument('--header-psm',type=int,default=7)
    ap.add_argument('--tesseract',default=r'C:\Program Files\Tesseract-OCR\tesseract.exe')
    ap.add_argument('--skip-ocr',action='store_true')
    main(ap.parse_args())
