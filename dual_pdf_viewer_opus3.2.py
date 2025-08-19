#!/usr/bin/env python3
"""
Dual PDF Viewer with Rectangle Annotations + Individual/Global Page Rotation
+ Page Counter Overlay per Viewer
Requirements: pip install PyQt6 PyMuPDF Pillow
"""

import sys
import fitz  # PyMuPDF
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFileDialog,
    QSplitter, QStatusBar, QGraphicsView, QGraphicsScene,
    QGraphicsRectItem, QScrollArea
)
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QPixmap, QImage, QPainter, QColor, QPen, QBrush, QMouseEvent

class PDFPage(QGraphicsView):
    """Custom widget for displaying a PDF page with rectangle annotations and rotation"""

    def __init__(self, page, index: int, owner, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene()
        self.setScene(self.scene)
        self.pixmap_item = None
        self.drawing = False
        self.start_point = None
        self.temp_item = None
        self.annotations = []
        self.selected_item = None
        self.rotation = 0  # individual rotation per page
        self.page = page
        self.index = index
        self.owner = owner  # reference to PDFViewer for callbacks

        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

        # Annotation settings
        self.annotation_color = QColor(255, 0, 0, 100)
        self.annotation_width = 2

        # Initial render
        self.render_page()

    def render_page(self):
        # Re-render the pixmap for the current rotation.
        mat = fitz.Matrix(1, 1).prerotate(self.rotation)
        pix = self.page.get_pixmap(matrix=mat, alpha=False)
        img_data = pix.tobytes("ppm")
        qimg = QImage.fromData(img_data)
        qpixmap = QPixmap.fromImage(qimg)

        # Replace the whole scene to keep things simple (annotations do not persist across rotations)
        self.scene.clear()
        self.pixmap_item = self.scene.addPixmap(qpixmap)
        self.scene.setSceneRect(QRectF(qpixmap.rect()))
        self.setMinimumHeight(qpixmap.height() + 20)
        self.annotations = []  # clear list since scene was cleared

    def rotate(self, angle):
        self.rotation = (self.rotation + angle) % 360
        self.render_page()

    def set_annotation_mode(self, enabled: bool):
        if enabled:
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def mousePressEvent(self, event: QMouseEvent):
        # Inform the owner which page is active (by click)
        if self.owner:
            self.owner.set_current_page(self.index)
        if self.cursor().shape() == Qt.CursorShape.CrossCursor and event.button() == Qt.MouseButton.LeftButton:
            self.drawing = True
            self.start_point = self.mapToScene(event.pos())
            pen = QPen(self.annotation_color, self.annotation_width)
            brush = QBrush(QColor(self.annotation_color.red(),
                                 self.annotation_color.green(),
                                 self.annotation_color.blue(), 50))
            self.temp_item = self.scene.addRect(QRectF(self.start_point, self.start_point), pen, brush)
        else:
            item = self.itemAt(event.pos())
            if item and item != self.pixmap_item:
                self.select_item(item)
            else:
                self.deselect_item()
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.drawing and self.temp_item:
            current_point = self.mapToScene(event.pos())
            rect = QRectF(self.start_point, current_point).normalized()
            self.temp_item.setRect(rect)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self.drawing and self.temp_item:
            self.drawing = False
            self.annotations.append(self.temp_item)
            self.temp_item.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable, True)
            self.temp_item.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, True)
            self.temp_item = None
        super().mouseReleaseEvent(event)

    def select_item(self, item):
        self.deselect_item()
        self.selected_item = item
        if hasattr(item, 'setPen'):
            pen = item.pen()
            pen.setStyle(Qt.PenStyle.DashLine)
            item.setPen(pen)

    def deselect_item(self):
        if self.selected_item and hasattr(self.selected_item, 'setPen'):
            pen = self.selected_item.pen()
            pen.setStyle(Qt.PenStyle.SolidLine)
            self.selected_item.setPen(pen)
        self.selected_item = None

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete and self.selected_item:
            self.scene.removeItem(self.selected_item)
            if self.selected_item in self.annotations:
                self.annotations.remove(self.selected_item)
            self.selected_item = None
        super().keyPressEvent(event)

    def clear_annotations(self):
        for ann in self.annotations:
            self.scene.removeItem(ann)
        self.annotations.clear()

class PDFViewer(QWidget):
    """Single PDF viewer widget with rectangle annotation and per-page/global rotation"""

    def __init__(self, viewer_id: str, parent=None):
        super().__init__(parent)
        self.viewer_id = viewer_id
        self.pdf_document = None
        self.global_rotation = 0
        self.rotate_all = False  # toggle state
        self.page_widgets = []
        self.current_page_index = 0

        self.init_ui()

    def init_ui(self):
        self.layout = QVBoxLayout()

        # Toolbar
        self.toolbar_layout = QHBoxLayout()

        self.rect_btn = QPushButton("□")
        self.rect_btn.setCheckable(True)
        self.rect_btn.clicked.connect(self.toggle_annotation)
        self.toolbar_layout.addWidget(self.rect_btn)

        self.clear_ann_btn = QPushButton("Clear")
        self.clear_ann_btn.clicked.connect(self.clear_annotations)
        self.toolbar_layout.addWidget(self.clear_ann_btn)

        self.rotate_left_btn = QPushButton("↺")
        self.rotate_left_btn.clicked.connect(lambda: self.rotate_pages(-90))
        self.toolbar_layout.addWidget(self.rotate_left_btn)

        self.rotate_right_btn = QPushButton("↻")
        self.rotate_right_btn.clicked.connect(lambda: self.rotate_pages(90))
        self.toolbar_layout.addWidget(self.rotate_right_btn)

        # Toggle for rotate all vs individual
        self.toggle_rotate_btn = QPushButton("Rotate Individually")
        self.toggle_rotate_btn.setCheckable(True)
        self.toggle_rotate_btn.setToolTip("Toggle between rotating all pages or just the current page")
        self.toggle_rotate_btn.clicked.connect(self.toggle_rotate_mode)
        self.toolbar_layout.addWidget(self.toggle_rotate_btn)

        self.toolbar_layout.addStretch()
        self.layout.addLayout(self.toolbar_layout)
        self.hide_toolbar()

        # Open button
        self.open_btn = QPushButton("Open PDF")
        self.open_btn.clicked.connect(self.open_pdf)
        self.open_btn.setFixedWidth(200)
        self.open_btn.setFixedHeight(50)
        self.open_btn.setStyleSheet("font-size: 16px;")
        self.layout.addWidget(self.open_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        # Scroll area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout()
        self.scroll_content.setLayout(self.scroll_layout)
        self.scroll_area.setWidget(self.scroll_content)
        self.layout.addWidget(self.scroll_area)

        # Page counter label UNDERNEATH the PDF viewer (small overlay-like indicator)
        self.page_counter_label = QLabel("Page – / –")
        self.page_counter_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.page_counter_label.setStyleSheet("color: #666; font-size: 11px; padding: 2px 4px;")
        self.layout.addWidget(self.page_counter_label)

        # Track scrolling to update current page
        self.scroll_area.verticalScrollBar().valueChanged.connect(self.update_current_page_from_scroll)

        self.setLayout(self.layout)

    def toggle_rotate_mode(self):
        self.rotate_all = self.toggle_rotate_btn.isChecked()
        if self.rotate_all:
            self.toggle_rotate_btn.setText("Rotate All")
        else:
            self.toggle_rotate_btn.setText("Rotate Individually")

    def show_toolbar(self):
        for i in range(self.toolbar_layout.count()):
            widget = self.toolbar_layout.itemAt(i).widget()
            if widget:
                widget.show()

    def hide_toolbar(self):
        for i in range(self.toolbar_layout.count()):
            widget = self.toolbar_layout.itemAt(i).widget()
            if widget:
                widget.hide()

    def toggle_annotation(self):
        for w in self.page_widgets:
            w.set_annotation_mode(self.rect_btn.isChecked())

    def clear_annotations(self):
        for w in self.page_widgets:
            w.clear_annotations()

    def open_pdf(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, f"Open PDF - Viewer {self.viewer_id}", "", "PDF Files (*.pdf)"
        )
        if file_path:
            self.load_pdf(file_path)

    def load_pdf(self, file_path: str):
        try:
            self.pdf_document = fitz.open(file_path)
            self.global_rotation = 0
            self.current_page_index = 0

            # Hide open button and show toolbar
            self.open_btn.hide()
            self.show_toolbar()

            # Render all pages
            self.display_pages()

        except Exception as e:
            print(f"Error loading PDF: {e}")

    def display_pages(self):
        if not self.pdf_document:
            return

        # Clear current widgets list and layout
        self.page_widgets.clear()
        while self.scroll_layout.count():
            item = self.scroll_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Create page widgets
        for page_num in range(len(self.pdf_document)):
            page = self.pdf_document[page_num]
            pdf_page = PDFPage(page, page_num, owner=self)
            pdf_page.rotation = self.global_rotation if self.rotate_all else 0
            pdf_page.render_page()
            self.scroll_layout.addWidget(pdf_page)
            self.page_widgets.append(pdf_page)

        self.update_page_counter_label()

    def update_page_counter_label(self):
        total = len(self.page_widgets)
        if total == 0:
            self.page_counter_label.setText("Page – / –")
        else:
            # 1-based page number in label
            self.page_counter_label.setText(f"Page {self.current_page_index + 1} / {total}")

    def set_current_page(self, index: int):
        # Clamp and set
        if not self.page_widgets:
            return
        index = max(0, min(index, len(self.page_widgets) - 1))
        if index != self.current_page_index:
            self.current_page_index = index
            self.update_page_counter_label()

    def update_current_page_from_scroll(self):
        if not self.page_widgets:
            return
        # Determine which page center is closest to viewport center
        vbar = self.scroll_area.verticalScrollBar()
        vy = vbar.value()
        viewport_h = self.scroll_area.viewport().height()
        viewport_center_y = vy + viewport_h / 2

        closest_idx = 0
        closest_dist = float('inf')
        for i, w in enumerate(self.page_widgets):
            top = w.y()  # position relative to scroll_content
            h = w.height()
            center = top + h / 2
            dist = abs(center - viewport_center_y)
            if dist < closest_dist:
                closest_dist = dist
                closest_idx = i
        self.set_current_page(closest_idx)

    def rotate_pages(self, angle: int):
        if self.rotate_all:
            # Global rotation for all pages
            self.global_rotation = (self.global_rotation + angle) % 360
            # Preserve current page index visually if possible
            current_idx = self.current_page_index
            self.display_pages()
            self.set_current_page(current_idx)
        else:
            # Rotate only the current page
            if not self.page_widgets:
                return
            self.page_widgets[self.current_page_index].rotate(angle)

class DualPDFViewerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Dual PDF Viewer (Annotations + Individual/Global Rotation)")
        self.setGeometry(100, 100, 1600, 900)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QHBoxLayout()
        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.viewer1 = PDFViewer("1")
        self.viewer2 = PDFViewer("2")

        splitter.addWidget(self.viewer1)
        splitter.addWidget(self.viewer2)
        splitter.setSizes([800, 800])

        layout.addWidget(splitter)
        central_widget.setLayout(layout)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    viewer = DualPDFViewerApp()
    viewer.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
