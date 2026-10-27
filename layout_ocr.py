"""SmartArchive-X Layout POC: conservative two-column detection + Arabic RTL OCR.
Not a trained layout model. Outputs inspectable crops and diagnostics, never silently drops original.
"""
import argparse
import json
import time
from pathlib import Path

import cv2
import numpy as np


def load_pages(path, dpi):
    if path.suffix.lower() == '.pdf':
        import fitz
        with fitz.open(str(path)) as pdf:
            for index, page in enumerate(pdf, 1):
                pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), alpha=False)
                arr = np.frombuffer(pix.tobytes('png'), dtype=np.uint8)
                yield index, cv2.imdecode(arr, cv2.IMREAD_COLOR)
    else:
        image = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError('Cannot read image: ' + str(path))
        yield 1, image


def detect_columns(img):
    """Heuristic: find wide whitespace gutter near center in text-ink projection.
    Conservative: ambiguous pages stay single-column. Never crop away top/bottom.
    """
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if w < 420 or h < 300:
        return [(0, 0, w, h)], {'reason': 'page_too_small', 'confidence': 0.0}
    # Adaptive threshold reduces impacts of uneven paper illumination.
    ink = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                cv2.THRESH_BINARY_INV, 31, 13) > 0
    # Work in body, ignoring header and footer so a spanning title does not dominate.
    y0, y1 = int(.16*h), int(.92*h)
    body = ink[y0:y1]
    # Smooth horizontal projection across x. A text gutter should be largely empty.
    counts = body.sum(axis=0).astype(float) / max(1, len(body))
    smooth = np.convolve(counts, np.ones(9)/9, mode='same')
    low, high = int(.33*w), int(.67*w)
    central = smooth[low:high]
    if len(central) == 0:
        return [(0, 0, w, h)], {'reason': 'invalid_width', 'confidence': 0.0}
    # Find best contiguous nearly-empty interval, or fallback to minimum in center.
    threshold = max(.012, float(np.quantile(central, .30)))
    candidates = np.flatnonzero(central <= threshold)
    groups = np.split(candidates, np.where(np.diff(candidates) > 1)[0] + 1) if len(candidates) else []
    groups = [g for g in groups if len(g) >= max(7, int(.012*w))]
    if not groups:
        return [(0, 0, w, h)], {'reason': 'no_clear_gutter', 'confidence': 0.0, 'min_ink': round(float(central.min()), 4)}
    gutter = max(groups, key=lambda g: (len(g), -abs(low+float(g.mean())-w/2)))
    start, end = low + int(gutter[0]), low + int(gutter[-1]) + 1
    # Require text ink on BOTH sides of gap; otherwise could be empty half-page.
    left = float(np.mean(smooth[int(.12*w):max(int(.12*w)+1,start-8)]))
    right = float(np.mean(smooth[min(w-1,end+8):int(.88*w)]))
    gap = float(np.mean(smooth[start:end]))
    if min(left, right) < .008 or gap > .58 * min(left, right):
        return [(0, 0, w, h)], {'reason': 'ambiguous_column_support', 'confidence': 0.0,
                                  'left_density': left, 'right_density': right, 'gutter_density': gap}
    divider = (start + end)//2
    margin = max(2, int(w * .009))
    # Small OVERLAP prevents cutting touching characters at the divider.
    boxes = [(max(0,divider-margin), 0, w, h), (0, 0, min(w,divider+margin), h)]
    confidence = float(np.clip((min(left,right)-gap)/max(min(left,right), 1e-5), 0, 1))
    return boxes, {'reason': 'two_column_gutter', 'confidence_heuristic': round(confidence,3),
                   'gutter_x': [start, end], 'divider_x': divider, 'left_density': round(left,4),
                   'right_density': round(right,4), 'gutter_density': round(gap,4),
                   'warning': 'Geometric heuristic, not calibrated confidence or layout accuracy.'}


def extract(img, lang, psm, exe):
    import pytesseract
    from PIL import Image
    if exe:
        pytesseract.pytesseract.tesseract_cmd = exe
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    begin = time.perf_counter()
    text = pytesseract.image_to_string(Image.fromarray(rgb), lang=lang, config=f'--oem 1 --psm {psm}')
    return text, round(time.perf_counter()-begin, 3)


def run(args):
    src = Path(args.input)
    if not src.is_file():
        raise FileNotFoundError(src)
    target = Path(args.output)
    target.mkdir(parents=True, exist_ok=True)
    summary = []
    for n, image in load_pages(src, args.dpi):
        folder = target / f'page_{n:03d}'
        folder.mkdir(exist_ok=True)
        boxes, diagnostic = detect_columns(image)
        marked = image.copy()
        for i, (x0,y0,x1,y1) in enumerate(boxes,1):
            cv2.rectangle(marked,(x0,y0),(x1-1,y1-1),(0,0,255) if i==1 else (255,0,0),2)
            cv2.putText(marked, f'RTL {i}', (x0+7, max(22,y0+23)), cv2.FONT_HERSHEY_SIMPLEX,
                        .65, (0,0,255) if i==1 else (255,0,0),2)
        cv2.imwrite(str(folder/'layout_overlay.png'),marked)
        cv2.imwrite(str(folder/'original.png'),image)
        entry = {'page':n,'layout':diagnostic,'regions':[]}
        all_text = []
        if not args.skip_ocr:
            base, base_time = extract(image,args.lang,3,args.tesseract)
            (folder/'baseline_psm3.txt').write_text(base,encoding='utf-8')
            entry['baseline'] = {'seconds':base_time,'characters':len(base)}
        for i, (x0,y0,x1,y1) in enumerate(boxes,1):
            crop = image[y0:y1, x0:x1]
            cv2.imwrite(str(folder/f'region_{i:02d}.png'),crop)
            region = {'reading_order': i,'bbox_xyxy':[x0,y0,x1,y1]}
            if not args.skip_ocr:
                txt, seconds = extract(crop,args.lang,args.psm,args.tesseract)
                (folder/f'region_{i:02d}_ocr.txt').write_text(txt,encoding='utf-8')
                region.update({'seconds':seconds,'characters':len(txt)})
                all_text.append(txt.strip())
            entry['regions'].append(region)
        if not args.skip_ocr:
            joined = '\n\n'.join(filter(None,all_text))+'\n'
            (folder/'rtl_reading_order.txt').write_text(joined,encoding='utf-8')
            entry['combined_characters'] = len(joined)
        (folder/'layout_report.json').write_text(json.dumps(entry,ensure_ascii=False,indent=2),encoding='utf-8')
        summary.append(entry)
        print(f'Page {n}: {len(boxes)} region(s) | {diagnostic["reason"]} | output: {folder}')
    (target/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Done. Review layout_overlay.png and compare baseline_psm3.txt with rtl_reading_order.txt.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',required=True,help='PDF or image path')
    parser.add_argument('--output',default='results/layout_ocr')
    parser.add_argument('--dpi',type=int,default=250)
    parser.add_argument('--lang',default='ara')
    parser.add_argument('--psm',type=int,default=6,help='Tesseract PSM per region; try 4 or 6')
    parser.add_argument('--tesseract',default=r'C:\Program Files\Tesseract-OCR\tesseract.exe')
    parser.add_argument('--skip-ocr',action='store_true',help='Test segmentation without Tesseract')
    run(parser.parse_args())
