"""Generate synthetic part photos: light part on dark background, stamped work order,
optional crack (dark line) or scratch (bright line)."""
import os

import cv2
import numpy as np

OUT = os.path.join(os.path.dirname(__file__), "..", "samples")
PART_COLOR = (180, 180, 180)
BG = 30


def make(name, work_order, defect):
    img = np.full((360, 560, 3), BG, np.uint8)
    w, h = (400, 290) if defect == "dimensional_deviation" else (400, 250)
    x, y = (560 - w) // 2, (360 - h) // 2

    cv2.rectangle(img, (x, y), (x + w, y + h), PART_COLOR, -1)
    cv2.putText(img, work_order, (x + 30, y + 58), cv2.FONT_HERSHEY_SIMPLEX,
                1.0, (20, 20, 20), 2, cv2.LINE_AA)

    if defect == "crack":
        cv2.line(img, (x + 60, y + h - 30), (x + 250, y + 110), (40, 40, 40), 2, cv2.LINE_AA)
    elif defect == "surface_scratch":
        cv2.line(img, (x + 80, y + h - 40), (x + 310, y + 120), (235, 235, 235), 2, cv2.LINE_AA)

    path = os.path.join(OUT, name)
    cv2.imwrite(path, img)
    print("wrote %s (%s)" % (path, defect))


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    make("part_ok.png", "WO-1042", "no_defect")
    make("part_crack.png", "WO-1042", "crack")
    make("part_scratch.png", "WO-2381", "surface_scratch")
    make("part_dimensional.png", "WO-2381", "dimensional_deviation")
