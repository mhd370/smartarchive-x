"""SmartArchive-X baseline experiment: compare Arabic OCR preprocessing and columns.
Run from project root: python compare_ocr.py --input data/input/sample.png
"""
import argparse
import csv
import time
from pathlib import Path
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
import pytesseract
from pytesseract import Output

parser = argparse.ArgumentParser()
parser.add_argument('--input', default='data/input/sample.png')
parser.add_argument('--tesseract', default=r'C:\Program Files\Tesseract-OCR\tesseract.exe')
args = parser.parse_args()
pytesseract.pytesseract.tesseract_cmd = args.tesseract
im = Image.open(args.input).convert('RGB')
out = Path('results/ocr_comparison')
out.mkdir(parents=True, exist_ok=True)

# Use geometric enlargement only; it cannot restore original missing detail.
up = im.resize((im.width * 3, im.height * 3), Image.Resampling.LANCZOS)
gray = ImageOps.grayscale(up)
sharp = ImageEnhance.Contrast(gray).enhance(1.7).filter(ImageFilter.UnsharpMask(radius=1.5, percent=140, threshold=3))
sharp.save(out / 'preprocessed.png')

variants = [
    ('original_ara_eng', im, 'ara+eng', 3),
    ('original_ara', im, 'ara', 3),
    ('enhanced_ara', sharp, 'ara', 3),
]
# Treat the heading as separate and each column as a text region.
# Crop ratios are specific to THIS sample and must not be generalized blindly.
# Image right column first (Arabic reading order), then left.
w, h = sharp.size
header = sharp.crop((0, 0, w, int(h * .16)))
right = sharp.crop((int(w * .60), int(h * .16), w, h))
left = sharp.crop((int(w * .07), int(h * .16), int(w * .52), h))
for name, region in [('header', header), ('right', right), ('left', left)]:
    region.save(out / f'{name}_region.png')

rows=[]
for name, picture, lang, psm in variants:
    start=time.perf_counter()
    txt=pytesseract.image_to_string(picture, lang=lang, config=f'--oem 1 --psm {psm}')
    seconds=time.perf_counter()-start
    (out / f'{name}.txt').write_text(txt, encoding='utf-8-sig')
    rows.append([name, round(seconds, 3), len(txt), 'Not measured: ground truth required'])
start=time.perf_counter()
parts=[pytesseract.image_to_string(region, lang='ara', config='--oem 1 --psm 6') for region in [header,right,left]]
text='\n\n'.join(parts)
seconds=time.perf_counter()-start
(out / 'split_columns_ara.txt').write_text(text, encoding='utf-8-sig')
rows.append(['split_columns_ara', round(seconds,3),len(text),'Not measured: ground truth required'])
with (out/'comparison.csv').open('w',newline='',encoding='utf-8-sig') as f:
    writer=csv.writer(f)
    writer.writerow(['variant','time_seconds','output_characters','accuracy'])
    writer.writerows(rows)
print('Finished. Check:',out.resolve())
for row in rows: print(row)
print('No accuracy comparison is valid without manually transcribed reference text.')
