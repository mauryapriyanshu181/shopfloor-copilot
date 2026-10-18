import cv2
import numpy as np

NOMINAL_ASPECT = 1.60
ASPECT_TOL = 0.08

CRACK_CONTRAST = 20.0
SCRATCH_CONTRAST = -12.0


def part_box(gray):
    _, th = cv2.threshold(gray, 60, 255, cv2.THRESH_BINARY)
    cnts, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return None
    return cv2.boundingRect(max(cnts, key=cv2.contourArea))


def _linear_defects(gray, box):
    x, y, w, h = box
    pad = int(0.08 * min(w, h))
    roi = gray[y + pad:y + h - pad, x + pad:x + w - pad]
    if roi.size == 0:
        return []

    # the part ID is stamped in the top band; mask it out so letter strokes
    # are not picked up as linear defects
    roi = roi[int(0.32 * roi.shape[0]):, :]

    edges = cv2.Canny(cv2.GaussianBlur(roi, (3, 3), 0), 40, 120)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=25,
                            minLineLength=int(0.30 * min(roi.shape)), maxLineGap=6)
    if lines is None:
        return []

    base = float(np.median(roi))
    found = []
    for x1, y1, x2, y2 in lines.reshape(-1, 4):
        mask = np.zeros(roi.shape, np.uint8)
        cv2.line(mask, (x1, y1), (x2, y2), 255, 3)
        contrast = base - float(cv2.mean(roi, mask=mask)[0])
        found.append({"contrast": round(contrast, 1),
                      "length_px": int(np.hypot(x2 - x1, y2 - y1))})
    return found


def classify(image_bgr):
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    box = part_box(gray)
    if box is None:
        return {"category": "no_defect", "confidence": 0.3,
                "evidence": "no part region isolated from background"}

    x, y, w, h = box
    aspect = max(w, h) / float(min(w, h))
    defects = _linear_defects(gray, box)
    cracks = [d for d in defects if d["contrast"] >= CRACK_CONTRAST]
    scratches = [d for d in defects if d["contrast"] <= SCRATCH_CONTRAST]

    if cracks:
        peak = max(d["contrast"] for d in cracks)
        return {"category": "crack", "confidence": round(min(0.95, 0.55 + peak / 150), 2),
                "evidence": "%d dark linear discontinuity(ies), peak contrast %.0f" % (len(cracks), peak)}

    if abs(aspect - NOMINAL_ASPECT) > ASPECT_TOL:
        return {"category": "dimensional_deviation", "confidence": 0.85,
                "evidence": "aspect %.2f vs nominal %.2f +/- %.2f" % (aspect, NOMINAL_ASPECT, ASPECT_TOL)}

    if scratches:
        peak = min(d["contrast"] for d in scratches)
        return {"category": "surface_scratch", "confidence": round(min(0.9, 0.5 + abs(peak) / 150), 2),
                "evidence": "%d bright linear mark(s), peak contrast %.0f" % (len(scratches), peak)}

    return {"category": "no_defect", "confidence": 0.8,
            "evidence": "aspect %.2f within tolerance, no linear defects" % aspect}
