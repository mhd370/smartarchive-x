"""Controlled, seeded degradation of real pages for the simulation experiments.

Each output records its exact parameters and the source hash, so a degraded page is always a
reproducible derivative of a real page, never a new or invented document.
"""
from dataclasses import dataclass
from io import BytesIO
import random

import cv2
import numpy as np
from PIL import Image, ImageFilter

LEVELS = {
    'clean': {},
    'mild': {'rotate': 1, 'gaussian_blur': 0.6, 'jpeg_quality': 70, 'contrast': 0.9, 'dpi_scale': 1.0},
    'medium': {'rotate': 3, 'gaussian_blur': 1.2, 'motion_blur': 5, 'jpeg_quality': 45, 'contrast': 0.7,
               'shadow': 0.25, 'stains': 3, 'dpi_scale': 200 / 300},
    'severe': {'rotate': 5, 'gaussian_blur': 2.0, 'motion_blur': 9, 'jpeg_quality': 25, 'contrast': 0.5,
               'shadow': 0.45, 'stains': 8, 'crop': 0.03, 'dpi_scale': 150 / 300},
}


@dataclass
class Degraded:
    image: Image.Image
    level: str
    params: dict


def _motion_blur(array: np.ndarray, size: int, angle: float) -> np.ndarray:
    kernel = np.zeros((size, size), np.float32)
    kernel[size // 2, :] = 1.0
    rotation = cv2.getRotationMatrix2D((size / 2 - 0.5, size / 2 - 0.5), angle, 1.0)
    kernel = cv2.warpAffine(kernel, rotation, (size, size))
    return cv2.filter2D(array, -1, kernel / max(kernel.sum(), 1e-6))


def degrade(image: Image.Image, level: str, seed: int) -> Degraded:
    if level not in LEVELS:
        raise ValueError(f'unknown level {level}')
    spec, rng = dict(LEVELS[level]), random.Random(f'{seed}:{level}')
    params: dict = {'seed': seed}
    current = image.convert('RGB')
    if 'dpi_scale' in spec and spec['dpi_scale'] < 1:
        size = (max(1, round(current.width * spec['dpi_scale'])), max(1, round(current.height * spec['dpi_scale'])))
        current = current.resize(size, Image.Resampling.BILINEAR)
        params['dpi_scale'] = round(spec['dpi_scale'], 4)
    if 'rotate' in spec:
        angle = rng.choice([-1, 1]) * spec['rotate']
        current = current.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor='white')
        params['rotate_degrees'] = angle
    array = np.asarray(current).astype(np.float32)
    if 'contrast' in spec:
        array = 255 - (255 - array) * spec['contrast']
        params['contrast_factor'] = spec['contrast']
    if 'shadow' in spec:
        height, width = array.shape[:2]
        ramp = np.linspace(1 - spec['shadow'], 1, width, dtype=np.float32)
        array *= (ramp if rng.random() < 0.5 else ramp[::-1])[None, :, None]
        params['shadow_strength'] = spec['shadow']
    if 'stains' in spec:
        height, width = array.shape[:2]
        stains = []
        for _ in range(spec['stains']):
            cx, cy, r = rng.randrange(width), rng.randrange(height), rng.randint(width // 60 + 2, width // 15 + 3)
            mask = np.zeros((height, width), np.float32)
            cv2.circle(mask, (cx, cy), r, 1.0, -1)
            mask = cv2.GaussianBlur(mask, (0, 0), r / 2)
            array = array * (1 - 0.25 * mask[..., None]) + np.array([200, 180, 120], np.float32) * 0.25 * mask[..., None]
            stains.append([cx, cy, r])
        params['stains'] = stains
    array = np.clip(array, 0, 255).astype(np.uint8)
    if 'motion_blur' in spec:
        angle = rng.uniform(0, 180)
        array = _motion_blur(array, spec['motion_blur'], angle)
        params['motion_blur'] = {'size': spec['motion_blur'], 'angle': round(angle, 2)}
    current = Image.fromarray(array)
    if 'gaussian_blur' in spec:
        current = current.filter(ImageFilter.GaussianBlur(spec['gaussian_blur']))
        params['gaussian_blur_radius'] = spec['gaussian_blur']
    if 'crop' in spec:
        dx, dy = round(current.width * spec['crop']), round(current.height * spec['crop'])
        current = current.crop((dx, dy, current.width - dx, current.height - dy))
        params['crop_fraction'] = spec['crop']
    if 'jpeg_quality' in spec:
        buffer = BytesIO()
        current.save(buffer, format='JPEG', quality=spec['jpeg_quality'])
        current = Image.open(BytesIO(buffer.getvalue())).convert('RGB')
        params['jpeg_quality'] = spec['jpeg_quality']
    return Degraded(current, level, params)
