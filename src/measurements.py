from dataclasses import dataclass, field
import numpy as np
import cv2
from PySide6.QtGui import QImage


@dataclass
class Region:
    index: int
    contour: np.ndarray           # (N, 2) in Bildkoordinaten, float
    area_px: float
    perimeter_px: float
    source: str                   # "manual" oder "color"

    def area_mm2(self, mm_per_px: float) -> float:
        return self.area_px * mm_per_px ** 2

    def perimeter_mm(self, mm_per_px: float) -> float:
        return self.perimeter_px * mm_per_px

    def centroid(self) -> tuple[float, float]:
        m = cv2.moments(self.contour.astype(np.float32))
        if abs(m["m00"]) < 1e-9:
            return tuple(self.contour.mean(axis=0))
        return m["m10"] / m["m00"], m["m01"] / m["m00"]


def qimage_to_array(image: QImage) -> np.ndarray:
    """QImage -> (H, W, 3) uint8 RGB."""
    image = image.convertToFormat(QImage.Format_RGB888)
    h, w, stride = image.height(), image.width(), image.bytesPerLine()
    buf = np.frombuffer(image.constBits(), dtype=np.uint8, count=h * stride)
    return buf.reshape(h, stride)[:, : w * 3].reshape(h, w, 3).copy()


def polygon_measures(points: np.ndarray) -> tuple[float, float]:
    """Gauss-Fläche und Umfang eines geschlossenen Polygons."""
    x, y = points[:, 0], points[:, 1]
    area = 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y))
    d = np.diff(np.vstack([points, points[:1]]), axis=0)
    perimeter = float(np.hypot(d[:, 0], d[:, 1]).sum())
    return float(area), perimeter


def color_barrier(rgb: np.ndarray, 
                  target: tuple[int, int, int],
                  tolerance: float) -> np.ndarray:
    """Maske der Pixel, die der Randfarbe hinreichend ähnlich sind."""
    diff = rgb.astype(np.int16) - np.array(target, dtype=np.int16)
    dist = np.sqrt((diff.astype(np.float32) ** 2).sum(axis=2))
    return (dist <= tolerance).astype(np.uint8)


def region_from_seed(rgb: np.ndarray, 
                     seed: tuple[int, int],
                     target: tuple[int, int, int], 
                     tolerance: float,
                     smoothing: float = 1.5) -> tuple[np.ndarray, float, float] | None:
    """Flutet ab seed bis zur Randfarbe. Gibt Kontur, Fläche, Umfang zurueck."""
    h, w = rgb.shape[:2]
    barrier = color_barrier(rgb, target, tolerance)
    barrier = cv2.morphologyEx(barrier, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))

    x, y = seed
    if not (0 <= x < w and 0 <= y < h) or barrier[y, x]:
        return None

    mask = np.zeros((h + 2, w + 2), np.uint8)
    mask[1:-1, 1:-1] = barrier
    canvas = np.zeros((h, w), np.uint8)
    cv2.floodFill(canvas, mask, (x, y), 255, flags=4 | cv2.FLOODFILL_FIXED_RANGE)

    filled = (canvas > 0).astype(np.uint8)
    if filled.sum() < 20:
        return None
    if filled.sum() > 0.9 * h * w:      # ausgelaufen, Rand nicht geschlossen
        return None

    #--- Rand und die Strichstärke mitdazunehmen
    kernel = np.ones((3, 3), np.uint8)
    n_labels, labels = cv2.connectedComponents(barrier, connectivity=8)
    neighbours = cv2.dilate(filled, kernel)
    touching = np.unique(labels[(neighbours > 0) & (barrier > 0)])
    touching = touching[touching != 0]

    with_border = filled.copy()
    for label in touching:
        with_border[labels == label] = 1

    if with_border.sum() > 3 * filled.sum():
        with_border = filled          # Rand hängt mit anderen Strichen zusammen

    filled = with_border
    
    filled = cv2.morphologyEx(filled, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(filled, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        return None

    contour = max(contours, key=cv2.contourArea)
    area = float(filled.sum())                       # Pixelzaehlung, nicht Polygon
    smooth = cv2.approxPolyDP(contour, smoothing, True)
    perimeter = float(cv2.arcLength(smooth, True))
    return contour.reshape(-1, 2).astype(np.float32), area, perimeter