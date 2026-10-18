import re

import cv2
import pytesseract

from .vision import part_box

STAMP_BAND = 0.32   # the work order is stamped in the top third of the part face
WO_PATTERN = re.compile(r"W[O0][^A-Za-z]{0,4}?(\d{3,})")


def _stamp_region(image_bgr):
    """Crop to the strip holding the work order. Tesseract reads one clean line
    far better than a whole photo that is mostly blank part face."""
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    box = part_box(gray)
    if box is None:
        return gray
    x, y, w, h = box
    return gray[y:y + int(STAMP_BAND * h), x:x + w]


def extract(image_bgr):
    band = _stamp_region(image_bgr)
    band = cv2.resize(band, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    _, th = cv2.threshold(band, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    try:
        raw = pytesseract.image_to_string(th, config="--psm 7").strip()
    except Exception as exc:
        return {"engine": "pytesseract", "text": "", "work_order_id": None, "error": str(exc)}

    match = WO_PATTERN.search(raw.upper())
    return {"engine": "pytesseract", "text": raw,
            "work_order_id": "WO-" + match.group(1) if match else None}
