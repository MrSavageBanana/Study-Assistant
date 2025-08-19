#!/usr/bin/env python3
"""
Dual PDF Viewer with Rectangle Annotations Only (Continuous Scroll Version)
Requirements: pip install PyQt6 PyMuPDF Pillow
"""

import sys
import fitz  # PyMuPDF
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFileDialog,
    QSplitter, QStatusBar, QGraphicsView, QGraphicsScene,
    QGraphicsPixmapItem, QGraphicsRectItem, QScrollArea
)
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QPixmap, QImage, QPainter, QColor, QPen, QBrush, QMouseEvent

class PDFPage(QGraphicsView):
    """Custom widget for displaying a PDF page with rectangle annotations"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene()
        self.setScene(self.scene)
        self.pixmap_item = None
        self.drawing = False
        self.start_point = None
        self.temp_item = None
        self.annotations = []
        self.selected_item = None

        self.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Annotation settings
        self.annotation_color = QColor(255, 0, 0, 100)
        self.annotation_width = 2

    def set_annotation_mode(self, enabled: bool):
        if enabled:
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def mousePressEvent(self, event: QMouseEvent):
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
    """Single PDF viewer widget with rectangle annotation only"""

    def __init__(self, viewer_id: str, parent=None):
        super().__init__(parent)
        self.viewer_id = viewer_id
        self.pdf_document = None
        self.rotation = 0

        self.init_ui()

    def init_ui(self):
        self.layout = QVBoxLayout()

        # Toolbar area (hidden until PDF is loaded)
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

        self.toolbar_layout.addStretch()
        self.layout.addLayout(self.toolbar_layout)
        self.hide_toolbar()

        # Centered Open button (only shown before loading)
        self.open_btn = QPushButton("Open PDF")
        self.open_btn.clicked.connect(self.open_pdf)
        self.open_btn.setFixedWidth(200)
        self.open_btn.setFixedHeight(50)
        self.open_btn.setStyleSheet("font-size: 16px;")
        self.layout.addWidget(self.open_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        # Scroll area for continuous pages
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout()
        self.scroll_content.setLayout(self.scroll_layout)
        self.scroll_area.setWidget(self.scroll_content)
        self.layout.addWidget(self.scroll_area)

        self.setLayout(self.layout)

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
        for i in range(self.scroll_layout.count()):
            widget = self.scroll_layout.itemAt(i).widget()
            if isinstance(widget, PDFPage):
                widget.set_annotation_mode(self.rect_btn.isChecked())

    def clear_annotations(self):
        for i in range(self.scroll_layout.count()):
            widget = self.scroll_layout.itemAt(i).widget()
            if isinstance(widget, PDFPage):
                widget.clear_annotations()

    def open_pdf(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, f"Open PDF - Viewer {self.viewer_id}", "", "PDF Files (*.pdf)"
        )
        if file_path:
            self.load_pdf(file_path)

    def load_pdf(self, file_path: str):
        try:
            self.pdf_document = fitz.open(file_path)
            self.rotation = 0

            # Hide open button and show toolbar after loading
            self.open_btn.hide()
            self.show_toolbar()

            # Clear existing pages
            while self.scroll_layout.count():
                item = self.scroll_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

            # Render and stack all pages vertically
            self.display_pages()

        except Exception as e:
            print(f"Error loading PDF: {e}")

    def display_pages(self):
        if not self.pdf_document:
            return

        # Clear current
        while self.scroll_layout.count():
            item = self.scroll_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for page_num in range(len(self.pdf_document)):
            page = self.pdf_document[page_num]
            mat = fitz.Matrix(1, 1).prerotate(self.rotation)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img_data = pix.tobytes("ppm")
            qimg = QImage.fromData(img_data)
            qpixmap = QPixmap.fromImage(qimg)

            pdf_page = PDFPage()
            pdf_page.pixmap_item = pdf_page.scene.addPixmap(qpixmap)
            pdf_page.scene.setSceneRect(QRectF(qpixmap.rect()))
            pdf_page.setMinimumHeight(qpixmap.height() + 20)
            self.scroll_layout.addWidget(pdf_page)

    def rotate_pages(self, angle: int):
        self.rotation = (self.rotation + angle) % 360
        self.display_pages()

class DualPDFViewerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Dual PDF Viewer (Rectangle Annotations Only - Continuous Scroll)")
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
