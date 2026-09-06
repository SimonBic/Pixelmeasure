from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QFrame, 
    QGraphicsItem, 
    QGraphicsOpacityEffect, 
    QGraphicsPixmapItem,
    QGraphicsScene, 
    QGraphicsView,
    QGroupBox, 
    QHBoxLayout,
    QHeaderView, 
    QLabel, 
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSlider,
    QTableWidget,
    QTableWidgetItem, 
    QVBoxLayout, 
    QWidget
)
from PySide6.QtGui import (
    QBrush, 
    QColor, 
    QFont,
    QImage, 
    QImageReader, 
    QPainter,
    QPainterPath, 
    QPen, 
    QPixmap,
    QRegularExpressionValidator,
)
from PySide6.QtCore import (
    Qt, 
    QPointF, 
    QRegularExpression, 
    Signal
    )
from PySide6.QtSvgWidgets import QSvgWidget
import math
from pathlib import Path
from enum import Enum, auto

from matplotlib import image
from measurements import Region, polygon_measures, region_from_seed, qimage_to_array
import numpy as np

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}
LOGO_PATH = Path(__file__).parent / "logo.svg"
LOGO_SIZE = 32
MARKER_RADIUS = 4
MIN_ZOOM = 0.05
MAX_ZOOM = 40.0
ZOOM_STEP = 1.15

class Mode(Enum):
    CALIBRATE = auto()
    DRAW = auto()
    COLOR = auto()

class CalibrationBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)

        self.length_edit = QLineEdit()
        self.length_edit.setPlaceholderText("Länge in cm")
        self.length_edit.setValidator(QRegularExpressionValidator(
            QRegularExpression(r"\d+([.,]\d{0,4})?")))
        self.length_edit.setMaximumWidth(140)

        self.calc_button = QPushButton("Pixelgröße berechnen")
        self.result_label = QLabel("—")
        self.result_label.setAlignment(Qt.AlignCenter)
        self.result_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(QLabel("Strecke:"))
        row.addWidget(self.length_edit)
        row.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addLayout(row)
        layout.addWidget(self.calc_button)
        layout.addWidget(self.result_label)

        self.set_active(False)

    def set_active(self, active: bool):
        self.setEnabled(active)
        self._effect.setOpacity(1.0 if active else 0.35)
        if not active:
            self.length_edit.clear()
            self.result_label.setText("—")



class MeasurePanel(QWidget):
    mode_changed = Signal(int)          # 0 = Kalibrieren, 1 = Zeichnen, 2 = Farbe
    pick_color_requested = Signal()
    tolerance_changed = Signal(int)
    clear_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        # --- Modusauswahl ---
        self.rb_calibrate = QRadioButton("Kalibrieren")
        self.rb_draw = QRadioButton("Fläche einzeichnen")
        self.rb_color = QRadioButton("Fläche über Randfarbe")
        self.rb_calibrate.setChecked(True)

        self.mode_group = QButtonGroup(self)
        for i, rb in enumerate((self.rb_calibrate, self.rb_draw, self.rb_color)):
            self.mode_group.addButton(rb, i)
        self.mode_group.idClicked.connect(self.mode_changed)

        mode_box = QGroupBox("Modus")
        mode_layout = QVBoxLayout(mode_box)
        mode_layout.addWidget(self.rb_calibrate)
        mode_layout.addWidget(self.rb_draw)
        mode_layout.addWidget(self.rb_color)

        # --- Randfarbe ---
        self.pick_button = QPushButton("Randfarbe mit Pipette wählen")
        self.pick_button.setCheckable(True)
        self.pick_button.clicked.connect(self.pick_color_requested)

        self.color_preview = QLabel()
        self.color_preview.setFixedSize(28, 28)
        self.color_preview.setAutoFillBackground(True)
        self.color_preview.setFrameStyle(QLabel.Box | QLabel.Plain)
        self.set_color(None)

        color_row = QHBoxLayout()
        color_row.addWidget(self.pick_button, 1)
        color_row.addWidget(self.color_preview)

        self.tolerance = QSlider(Qt.Horizontal)
        self.tolerance.setRange(5, 120)
        self.tolerance.setValue(40)
        self.tolerance_value = QLabel("40")
        self.tolerance.valueChanged.connect(
            lambda v: (self.tolerance_value.setText(str(v)),
                       self.tolerance_changed.emit(v)))

        tol_row = QHBoxLayout()
        tol_row.addWidget(QLabel("Toleranz:"))
        tol_row.addWidget(self.tolerance, 1)
        tol_row.addWidget(self.tolerance_value)

        self.color_box = QGroupBox("Randfarbe")
        color_layout = QVBoxLayout(self.color_box)
        color_layout.addLayout(color_row)
        color_layout.addLayout(tol_row)
        self.color_box.setEnabled(False)

        # --- Ergebnisse ---
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Nr.", "Umfang (mm)", "Fläche (mm²)"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)

        self.clear_button = QPushButton("Flächen löschen")
        self.clear_button.clicked.connect(self.clear_requested)

        result_box = QGroupBox("Messungen")
        result_layout = QVBoxLayout(result_box)
        result_layout.addWidget(self.table)
        result_layout.addWidget(self.clear_button)

        layout = QVBoxLayout(self)
        layout.addWidget(mode_box)
        layout.addWidget(self.color_box)
        layout.addWidget(result_box, 1)

    # --- öffentliche Methoden ---

    def set_color(self, rgb: tuple[int, int, int] | None):
        if rgb is None:
            self.color_preview.setStyleSheet(
                "background: palette(window); border: 1px solid gray;")
            self.color_preview.setToolTip("Noch keine Randfarbe gewählt")
        else:
            self.color_preview.setStyleSheet(
                f"background: {QColor(*rgb).name()}; border: 1px solid gray;")
            self.color_preview.setToolTip(QColor(*rgb).name())
        self.pick_button.setChecked(False)

    def set_color_mode_enabled(self, enabled: bool):
        self.color_box.setEnabled(enabled)

    def set_regions(self, regions, mm_per_px):
        self.table.setRowCount(len(regions))
        for row, region in enumerate(regions):
            values = [
                str(region.index),
                f"{region.perimeter_mm(mm_per_px):.2f}",
                f"{region.area_mm2(mm_per_px):.2f}",
            ]
            for col, text in enumerate(values):
                item = QTableWidgetItem(text)
                if col > 0:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(row, col, item)


class ImageView(QGraphicsView):
    points_changed = Signal(list)
    regions_changed = Signal(list)
    color_picked = Signal(tuple)
    region_failed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)

        self._pixmap_item: QGraphicsPixmapItem | None = None
        self._points: list[QPointF] = []
        self._markers: list = []
        self._line = None
        self._user_zoomed = False

        self.setContextMenuPolicy(Qt.PreventContextMenu)
        self.setAcceptDrops(True)

        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setAlignment(Qt.AlignCenter)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setDragMode(QGraphicsView.ScrollHandDrag)

        self._hint = self._scene.addText("Bild hierher ziehen")
        self._hint.setDefaultTextColor(QColor("gray"))
        self._scene.setSceneRect(self._hint.boundingRect())

        self._mode = Mode.CALIBRATE
        self._regions: list[Region] = []
        self._region_items: list = []
        self._rgb = None                  
        self._border_color = None
        self._tolerance = 40
        self._picking_color = False
        self._drawing = False
        self._draft: list[QPointF] = []
        self._draft_item = None

        

    # --- Bild laden -----------------------------------------------------

    def set_image(self, image: QImage):
        pixmap = QPixmap.fromImage(image)

        self._scene.clear()
        self._hint = None
        self._markers.clear()
        self._points.clear()
        self._line = None
        self._region_items.clear()
        self._regions.clear()
        self._draft_item = None
        self._draft = []

        self._rgb = qimage_to_array(image)

        self._pixmap_item = self._scene.addPixmap(pixmap)
        self._scene.setSceneRect(self._pixmap_item.boundingRect())
        self.resetTransform()
        self._user_zoomed = False
        self.fitInView(self._pixmap_item, Qt.KeepAspectRatio)

        self.points_changed.emit([])
        self.regions_changed.emit([])


    # --- Drag & Drop ----------------------------------------------------

    def _urls_are_images(self, mime):
        if not mime.hasUrls():
            return False
        return all(
            Path(url.toLocalFile()).suffix.lower() in IMAGE_SUFFIXES
            for url in mime.urls()
        )

    def dragEnterEvent(self, event):
        if self._urls_are_images(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if self._urls_are_images(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        path = Path(event.mimeData().urls()[0].toLocalFile())
        reader = QImageReader(str(path))
        reader.setAutoTransform(True)
        image = reader.read()
        if image.isNull():
            return
        self.set_image(image)
        event.acceptProposedAction()

    # --- Punkte ---------------------------------------------------------

    def set_mode(self, mode: Mode):
        self._mode = mode
        self._drawing = False

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton and self._pixmap_item is not None:
            pos = self._image_pos(event)
            if pos is None:
                return
            if self._picking_color:
                self._pick_color(pos)
                event.accept()
                return
            if self._mode is Mode.CALIBRATE:
                self._add_point(pos)
            elif self._mode is Mode.DRAW:
                self._drawing = True
                self._draft = [pos]
            elif self._mode is Mode.COLOR:
                self._seed_region(pos)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drawing:
            pos = self._image_pos(event)
            if pos is not None and self._far_enough(pos):
                self._draft.append(pos)
                self._update_draft_path()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drawing and event.button() == Qt.RightButton:
            self._drawing = False
            self._finish_draft()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _image_pos(self, event) -> QPointF | None:
        scene_pos = self.mapToScene(event.position().toPoint())
        pos = self._pixmap_item.mapFromScene(scene_pos)
        return pos if self._pixmap_item.boundingRect().contains(pos) else None

    def _far_enough(self, pos: QPointF, min_dist: float = 2.0) -> bool:
        last = self._draft[-1]
        return math.hypot(pos.x() - last.x(), pos.y() - last.y()) >= min_dist

    def _finish_draft(self):
        if len(self._draft) < 3:
            self._clear_draft()
            return
        points = np.array([[p.x(), p.y()] for p in self._draft], dtype=np.float32)
        area, perimeter = polygon_measures(points)
        self._clear_draft()
        self._add_region(Region(len(self._regions) + 1, points, area, perimeter, "manual"))

    def _seed_region(self, pos: QPointF):
        if self._border_color is None or self._rgb is None:
            return
        result = region_from_seed(
            self._rgb, (int(pos.x()), int(pos.y())),
            self._border_color, self._tolerance)
        if result is None:
            self.region_failed.emit()
            return
        contour, area, perimeter = result
        self._add_region(Region(len(self._regions) + 1, contour, area, perimeter, "color"))

    def _add_point(self, image_pos: QPointF):
        if len(self._points) >= 2:
            self._clear_markers()

        self._points.append(image_pos)
        scene_pos = self._pixmap_item.mapToScene(image_pos)

        marker = self._scene.addEllipse(
            -MARKER_RADIUS, -MARKER_RADIUS,
            2 * MARKER_RADIUS, 2 * MARKER_RADIUS,
            QPen(QColor("red"), 0), QBrush(QColor("red")),
        )
        marker.setPos(scene_pos)
        marker.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        marker.setZValue(10)
        self._markers.append(marker)

        if len(self._points) == 2:
            self._draw_connection()

        self.points_changed.emit(list(self._points))

    def _draw_connection(self):
        p1 = self._pixmap_item.mapToScene(self._points[0])
        p2 = self._pixmap_item.mapToScene(self._points[1])
        self._line = self._scene.addLine(
            p1.x(), p1.y(), p2.x(), p2.y(), QPen(QColor("red"), 0))
        self._line.setZValue(9)

    def _clear_markers(self):
        for item in self._markers:
            self._scene.removeItem(item)
        self._markers.clear()
        if self._line is not None:
            self._scene.removeItem(self._line)
            self._line = None
        self._points.clear()

    # --- Zoom und Pan ---------------------------------------------------

    def wheelEvent(self, event):
        if self._pixmap_item is None:
            return
        factor = ZOOM_STEP if event.angleDelta().y() > 0 else 1 / ZOOM_STEP
        if not (MIN_ZOOM <= self.transform().m11() * factor <= MAX_ZOOM):
            return
        self.scale(factor, factor)
        self._user_zoomed = True

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._pixmap_item is not None and not self._user_zoomed:
            self.fitInView(self._pixmap_item, Qt.KeepAspectRatio)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton and self._pixmap_item is not None:
            self.resetTransform()
            self.fitInView(self._pixmap_item, Qt.KeepAspectRatio)
            self._user_zoomed = False
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    # --- Overlay der flächen ----
    def _add_region(self, region: Region):
        self._regions.append(region)

        path = QPainterPath()
        path.moveTo(self._pixmap_item.mapToScene(QPointF(*region.contour[0])))
        for x, y in region.contour[1:]:
            path.lineTo(self._pixmap_item.mapToScene(QPointF(x, y)))
        path.closeSubpath()

        item = self._scene.addPath(path, QPen(QColor("red"), 0))
        item.setZValue(8)

        cx, cy = region.centroid()
        label = self._scene.addSimpleText(str(region.index))
        label.setBrush(QBrush(QColor("red")))
        label.setPos(self._pixmap_item.mapToScene(QPointF(cx, cy)))
        label.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        label.setZValue(11)

        self._region_items.append((item, label))
        self.regions_changed.emit(list(self._regions))


    #---Hilfsfunktionen ---

    def set_mode(self, mode: Mode):
        self._mode = mode
        self._drawing = False
        self._clear_draft()

    def set_tolerance(self, value: int):
        self._tolerance = int(value)

    def set_border_color(self, rgb: tuple[int, int, int] | None):
        self._border_color = rgb

    def start_color_picking(self):
        self._picking_color = True

    def clear_regions(self):
        for path_item, label in self._region_items:
            self._scene.removeItem(path_item)
            self._scene.removeItem(label)
        self._region_items.clear()
        self._regions.clear()
        self.regions_changed.emit([])

    def _clear_draft(self):
        if self._draft_item is not None:
            self._scene.removeItem(self._draft_item)
            self._draft_item = None
        self._draft = []

    def _update_draft_path(self):
        path = QPainterPath()
        path.moveTo(self._pixmap_item.mapToScene(self._draft[0]))
        for p in self._draft[1:]:
            path.lineTo(self._pixmap_item.mapToScene(p))

        pen = QPen(QColor("red"), 0)
        pen.setStyle(Qt.DashLine)
        if self._draft_item is None:
            self._draft_item = self._scene.addPath(path, pen)
            self._draft_item.setZValue(7)
        else:
            self._draft_item.setPath(path)

    def _pick_color(self, pos: QPointF):
        if self._rgb is None:
            return
        x, y = int(pos.x()), int(pos.y())
        h, w = self._rgb.shape[:2]
        x = min(max(x, 1), w - 2)
        y = min(max(y, 1), h - 2)
        patch = self._rgb[y - 1:y + 2, x - 1:x + 2].reshape(-1, 3)
        rgb = tuple(int(v) for v in patch.mean(axis=0).round())
        self._border_color = rgb
        self._picking_color = False
        self.color_picked.emit(rgb)

class HeaderBar(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.NoFrame)
        self.setFixedHeight(48)

        self.logo = QSvgWidget(str(LOGO_PATH))
        self.logo.setFixedSize(LOGO_SIZE, LOGO_SIZE)

        title = QLabel("Pixelmeasure")
        font = title.font()
        font.setPointSize(14)
        font.setWeight(QFont.DemiBold)
        title.setFont(font)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(10)
        layout.addWidget(self.logo)
        layout.addWidget(title)
        layout.addStretch(1)


class MainWindow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._points = []
        self.scale_x = None
        self.scale_y = None

        self.image_view = ImageView(self)
        self.calibration_bar = CalibrationBar(self)
        header = HeaderBar(self)

        self.measure_panel = MeasurePanel(self)

        panel = QVBoxLayout()
        panel.addWidget(self.calibration_bar)
        panel.addWidget(self.measure_panel, 1)

        self.measure_panel.mode_changed.connect(self._on_mode_changed)
        self.measure_panel.tolerance_changed.connect(self.image_view.set_tolerance)
        self.measure_panel.clear_requested.connect(self.image_view.clear_regions)
        self.image_view.regions_changed.connect(self._on_regions_changed)

        content = QHBoxLayout()
        content.addLayout(panel, 1)
        content.addWidget(self.image_view, 4)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(header)
        layout.addLayout(content)

        self.image_view.points_changed.connect(self._on_points_changed)
        self.image_view.regions_changed.connect(self._on_regions_changed)
        self.image_view.color_picked.connect(self.measure_panel.set_color)
        self.image_view.region_failed.connect(self._on_region_failed)

        self.calibration_bar.calc_button.clicked.connect(self._update_scale)

        self.measure_panel.mode_changed.connect(self._on_mode_changed)
        self.measure_panel.pick_color_requested.connect(self.image_view.start_color_picking)
        self.measure_panel.tolerance_changed.connect(self.image_view.set_tolerance)
        self.measure_panel.clear_requested.connect(self.image_view.clear_regions)

        self.resize(1980, 1080)

    def _on_mode_changed(self, mode_id: int):
        self.image_view.set_mode([Mode.CALIBRATE, Mode.DRAW, Mode.COLOR][mode_id])
        self.measure_panel.set_color_mode_enabled(mode_id == 2)

    def _on_regions_changed(self, regions):
        if self.scale_x is None:
            return
        self.measure_panel.set_regions(regions, self.scale_x)

    def _on_points_changed(self, points):
        self._points = points
        self.calibration_bar.set_active(len(points) == 2)

    def _update_scale(self):
        self.scale_x = self.scale_y = None

        text = self.calibration_bar.length_edit.text().replace(",", ".")
        if len(self._points) != 2:
            self.calibration_bar.result_label.setText("Bitte zwei Punkte setzen")
            return
        try:
            length_cm = float(text)
        except ValueError:
            self.calibration_bar.result_label.setText("Ungültige Länge")
            return
        if length_cm <= 0:
            self.calibration_bar.result_label.setText("Länge muss größer 0 sein")
            return

        p1, p2 = self._points
        d_px = math.hypot(p2.x() - p1.x(), p2.y() - p1.y())
        if d_px < 1e-6:
            self.calibration_bar.result_label.setText("Punkte liegen zu dicht beieinander")
            return

        mm_per_px = length_cm * 10.0 / d_px
        self.scale_x = self.scale_y = mm_per_px
        self.calibration_bar.result_label.setText(
            f"{mm_per_px * 1000:.2f} µm/px   ({d_px:.1f} px)")

    def _on_region_failed(self):
        QMessageBox.information(
            self, "Keine Fläche gefunden",
            "Der Rand ist an dieser Stelle nicht geschlossen oder die Toleranz "
            "passt nicht. Toleranz anpassen oder näher an die Mitte klicken.")

