"""SmartArchive-X: explainable, *heuristic* image quality check and conservative enhancement.
Run: python quality_analyzer.py --input data/input/sample.png
Requires: opencv-python, numpy, Pillow, PyMuPDF; pytesseract optional (--ocr).
"""
import argparse
import csv
import hashlib
import json
import shutil
import time
from pathlib import Path
import cv2
import numpy as np


def image_pages(path, dpi=250):
    if path.suffix.lower() == '.pdf':
        import fitz
        with fitz.open(path) as doc:
            for n, page in enumerate(doc, 1):
                pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), alpha=False)
                b = np.frombuffer(pix.tobytes('png'), np.uint8)
                img = cv2.imdecode(b, cv2.IMREAD_COLOR)
                yield n, img
    else:
        img = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError('Cannot decode image. Supported: PDF, PNG, JPG, TIFF, BMP.')
        yield 1, img


def metrics(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    # The measures are proxies, not calibrated image/OCR accuracy.
    resized = cv2.resize(gray, (min(w, 1400), min(h, 1800)), interpolation=cv2.INTER_AREA)
    lap = cv2.Laplacian(resized, cv2.CV_64F)
    sharpness = float(lap.var())
    contrast = float(np.percentile(resized, 95) - np.percentile(resized, 5))
    background = float(np.mean(resized > 245))
    # QR/text-free images could score similarly; do not present as a universal quality prediction.
    short_side = min(h, w)
    resolution_score = float(np.clip((short_side - 450) / (1700 - 450), 0, 1))
    focus_score = float(np.clip(np.log1p(sharpness) / np.log1p(450.0), 0, 1))
    contrast_score = float(np.clip((contrast - 45) / (205 - 45), 0, 1))
    # Demo weights; calibrate on ground-truth pages before using for routing.
    score = round(100 * (0.45 * focus_score + 0.35 * contrast_score + 0.20 * resolution_score), 1)
    flags = []
    if short_side < 900:
        flags.append('Low pixel dimensions for small text (not necessarily low DPI)')
    if sharpness < 75:
        flags.append('Low edge sharpness / possible blur')
    if contrast < 120:
        flags.append('Low global contrast / possible faint print')
    return dict(width_px=w, height_px=h, sharpness_laplacian_variance=round(sharpness, 2),
                contrast_p95_p5=round(contrast, 2), bright_pixel_fraction=round(background, 3),
                quality_score_heuristic_0_100=score, flags=flags,
                warning='Heuristic quality score, NOT image accuracy, OCR confidence or CER/WER. Score may increase while OCR worsens.')


def candidates(img, m):
    yield 'original', img
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=1.6, tileGridSize=(8, 8)).apply(gray)
    yield 'mild_contrast', cv2.cvtColor(clahe, cv2.COLOR_GRAY2BGR)
    if m['sharpness_laplacian_variance'] < 180:
        soft = cv2.GaussianBlur(clahe, (0, 0), sigmaX=0.65)
        sharpened = cv2.addWeighted(clahe, 1.35, soft, -0.35, 0)
        yield 'mild_sharpen', cv2.cvtColor(sharpened, cv2.COLOR_GRAY2BGR)
    if min(img.shape[:2]) < 1100:
        up = cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        yield 'upscale_2x', up


def try_ocr(img, tesseract_path):
    import pytesseract
    from PIL import Image
    from pytesseract import Output
    if tesseract_path:
        pytesseract.pytesseract.tesseract_cmd = tesseract_path
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    start = time.perf_counter()
    data = pytesseract.image_to_data(Image.fromarray(rgb), lang='ara', config='--oem 1 --psm 3', output_type=Output.DICT)
    text = pytesseract.image_to_string(Image.fromarray(rgb), lang='ara', config='--oem 1 --psm 3')
    secs = time.perf_counter() - start
    conf = [float(v) for v,t in zip(data['conf'],data['text']) if str(t).strip() and float(v)>=0]
    return dict(text=text, time_s=round(secs, 3), mean_word_confidence=round(float(np.mean(conf)), 2) if conf else None,
                detected_words=len(conf), character_count=len(text),
                caveat='Model confidence is not measured OCR accuracy; compare against ground truth.')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--input', required=True, help='Image or PDF')
    p.add_argument('--out', default='results/quality_analysis')
    p.add_argument('--ocr', action='store_true', help='Also run Arabic Tesseract on each version (optional)')
    p.add_argument('--tesseract', default=r'C:\Program Files\Tesseract-OCR\tesseract.exe')
    p.add_argument('--dpi', type=int, default=250)
    args = p.parse_args()
    source = Path(args.input)
    if not source.is_file():
        p.error(f'Input file not found: {source}')
    if source.suffix.lower() not in {'.pdf','.jpg','.jpeg','.png','.tif','.tiff','.bmp'}:
        p.error('Supported files: PDF, JPG, PNG, TIFF, BMP')
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    # Preserve a byte-for-byte copy, not just a re-encoded image.
    original = out / ('original_file' + source.suffix.lower())
    if source.resolve() != original.resolve():
        shutil.copy2(source, original)
    file_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    pages = []
    summary_rows = []
    for n, img in image_pages(source, args.dpi):
        page_folder = out / f'page_{n:03d}'
        page_folder.mkdir(exist_ok=True)
        base = metrics(img)
        entries = []
        for label, candidate in candidates(img, base):
            img_path = page_folder / f'{label}.png'
            cv2.imwrite(str(img_path), candidate)
            row = dict(variant=label, image_path=str(img_path), metrics=metrics(candidate))
            if args.ocr:
                record = try_ocr(candidate, args.tesseract)
                (page_folder / f'{label}_ocr.txt').write_text(record.pop('text'), encoding='utf-8-sig')
                row['ocr'] = record
            entries.append(row)
            summary_rows.append(dict(page=n, variant=label,
                                     quality_heuristic=row['metrics']['quality_score_heuristic_0_100'],
                                     ocr_confidence=(row.get('ocr') or {}).get('mean_word_confidence'),
                                     recognized_characters=(row.get('ocr') or {}).get('character_count'),
                                     ocr_time_s=(row.get('ocr') or {}).get('time_s')))
        pages.append(dict(page=n, baseline=base, variants=entries,
                          policy='Keep original as default. Do not auto-select a variant by image score or mean OCR confidence alone. Human review/ground truth required to verify improvements.'))
        print(f'Page {n}: heuristic original quality={base["quality_score_heuristic_0_100"]}/100; '
              f'variants={", ".join(x["variant"] for x in entries)}')
    report = dict(input_file=str(source), sha256=file_sha, page_count=len(pages), pages=pages,
                  disclaimer='No OCR accuracy (CER/WER) calculated. No automatic repair is guaranteed. DPI of an image cannot be inferred reliably from pixel dimensions alone.')
    (out/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    with (out/'summary.csv').open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=list(summary_rows[0].keys()))
        writer.writeheader(); writer.writerows(summary_rows)
    print('Done:', out.resolve())


if __name__ == '__main__':
    main()
