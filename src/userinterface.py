from PySide6.QtWidgets import (
    QFrame, 
    QGraphicsItem, 
    QGraphicsOpacityEffect, 
    QGraphicsPixmapItem,
    QGraphicsScene, 
    QGraphicsView, 
    QHBoxLayout, 
    QLabel, 
    QLineEdit,
    QPushButton, 
    QVBoxLayout, 
    QWidget
)
from PySide6.QtGui import (
    QBrush, 
    QColor, 
    QFont, 
    QImageReader, 
    QPainter, 
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

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}
LOGO_PATH = Path(__file__).parent / "logo.svg"
LOGO_SIZE = 32
MARKER_RADIUS = 4
MIN_ZOOM = 0.05
MAX_ZOOM = 40.0
ZOOM_STEP = 1.15


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


class ImageView(QGraphicsView):
    points_changed = Signal(list)

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

    # --- Bild laden -----------------------------------------------------

    def set_image(self, pixmap: QPixmap):
        self._scene.clear()
        self._hint = None
        self._markers.clear()
        self._points.clear()
        self._line = None

        self._pixmap_item = self._scene.addPixmap(pixmap)
        self._scene.setSceneRect(self._pixmap_item.boundingRect())
        self.resetTransform()
        self._user_zoomed = False
        self.fitInView(self._pixmap_item, Qt.KeepAspectRatio)
        self.points_changed.emit(list(self._points))

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
        self.set_image(QPixmap.fromImage(image))
        event.acceptProposedAction()

    # --- Punkte ---------------------------------------------------------

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton and self._pixmap_item is not None:
            scene_pos = self.mapToScene(event.position().toPoint())
            image_pos = self._pixmap_item.mapFromScene(scene_pos)
            if self._pixmap_item.boundingRect().contains(image_pos):
                self._add_point(image_pos)
            event.accept()
            return
        super().mousePressEvent(event)

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

        panel = QVBoxLayout()
        panel.addStretch(1)
        panel.addWidget(self.calibration_bar)
        panel.addStretch(1)

        content = QHBoxLayout()
        content.addLayout(panel, 1)
        content.addWidget(self.image_view, 4)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(header)
        layout.addLayout(content)

        self.image_view.points_changed.connect(self._on_points_changed)
        self.calibration_bar.calc_button.clicked.connect(self._update_scale)

        self.resize(1600, 1000)

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

