#!/usr/bin/env python3
"""
Dual PDF Viewer with Rectangle Annotations + Individual/Global Page Rotation
+ Page Counter Overlay per Viewer + Paint-style Rectangle Editing
Requirements: pip install PyQt6 PyMuPDF Pillow

created with Claude. Account: Milobowler
"""

import sys
import fitz  # PyMuPDF
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFileDialog,
    QSplitter, QStatusBar, QGraphicsView, QGraphicsScene,
    QGraphicsRectItem, QScrollArea
)
from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QPixmap, QImage, QPainter, QColor, QPen, QBrush, QMouseEvent, QCursor

class SelectableRect(QGraphicsRectItem):
    """Rectangle that can be selected and shows resize handles like MS Paint"""
    def __init__(self, rect, pen, brush, parent=None):
        super().__init__(rect, parent)
        self.setPen(pen)
        self.setBrush(brush)
        self.original_pen = pen
        self.selected_pen = QPen(pen.color(), pen.width())
        self.selected_pen.setStyle(Qt.PenStyle.DashLine)
        self.is_selected = False
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, False)
        
    def select(self):
        self.is_selected = True
        self.setPen(self.selected_pen)
        
    def deselect(self):
        self.is_selected = False
        self.setPen(self.original_pen)

class PDFPage(QGraphicsView):
    """Custom widget for displaying a PDF page with MS Paint-style rectangle annotations"""

    def __init__(self, page, index: int, owner, annotation_color: QColor, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene()
        self.setScene(self.scene)
        self.pixmap_item = None
        
        # Drawing state
        self.drawing = False
        self.start_point = None
        self.temp_rect = None
        
        # Selection and resize state
        self.selected_rect = None
        self.resize_mode = None  # None, 'move', 'nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'
        self.last_mouse_pos = None
        
        self.annotations = []
        self.rotation = 0
        self.page = page
        self.index = index
        self.owner = owner
        self.annotation_mode = False

        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

        # Annotation settings
        self.annotation_color = annotation_color
        self.annotation_width = 2

        # Handle size for resize detection
        self.handle_size = 6

        self.render_page()

    def render_page(self):
        mat = fitz.Matrix(1, 1).prerotate(self.rotation)
        pix = self.page.get_pixmap(matrix=mat, alpha=False)
        img_data = pix.tobytes("ppm")
        qimg = QImage.fromData(img_data)
        qpixmap = QPixmap.fromImage(qimg)

        self.scene.clear()
        self.pixmap_item = self.scene.addPixmap(qpixmap)
        self.scene.setSceneRect(QRectF(qpixmap.rect()))
        self.setMinimumHeight(qpixmap.height() + 20)
        self.annotations = []
        self.selected_rect = None

    def rotate(self, angle):
        self.rotation = (self.rotation + angle) % 360
        self.render_page()

    def set_annotation_mode(self, enabled: bool):
        self.annotation_mode = enabled
        if enabled:
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def get_handle_at_pos(self, rect_item, pos):
        """Check if position is over a resize handle of the rectangle"""
        if not rect_item.is_selected:
            return None
            
        rect = rect_item.rect()
        h = self.handle_size
        
        # Convert to scene coordinates
        rect_pos = rect_item.pos()
        adjusted_rect = QRectF(rect.x() + rect_pos.x(), rect.y() + rect_pos.y(), rect.width(), rect.height())
        
        # Define handle areas
        handles = {
            'nw': QRectF(adjusted_rect.left() - h/2, adjusted_rect.top() - h/2, h, h),
            'n':  QRectF(adjusted_rect.center().x() - h/2, adjusted_rect.top() - h/2, h, h),
            'ne': QRectF(adjusted_rect.right() - h/2, adjusted_rect.top() - h/2, h, h),
            'e':  QRectF(adjusted_rect.right() - h/2, adjusted_rect.center().y() - h/2, h, h),
            'se': QRectF(adjusted_rect.right() - h/2, adjusted_rect.bottom() - h/2, h, h),
            's':  QRectF(adjusted_rect.center().x() - h/2, adjusted_rect.bottom() - h/2, h, h),
            'sw': QRectF(adjusted_rect.left() - h/2, adjusted_rect.bottom() - h/2, h, h),
            'w':  QRectF(adjusted_rect.left() - h/2, adjusted_rect.center().y() - h/2, h, h),
        }
        
        for handle_name, handle_rect in handles.items():
            if handle_rect.contains(pos):
                return handle_name
                
        # Check if inside rectangle for move
        if adjusted_rect.contains(pos):
            return 'move'
            
        return None

    def get_cursor_for_handle(self, handle):
        """Get cursor for handle type"""
        cursors = {
            'nw': Qt.CursorShape.SizeFDiagCursor,
            'n':  Qt.CursorShape.SizeVerCursor,
            'ne': Qt.CursorShape.SizeBDiagCursor,
            'e':  Qt.CursorShape.SizeHorCursor,
            'se': Qt.CursorShape.SizeFDiagCursor,
            's':  Qt.CursorShape.SizeVerCursor,
            'sw': Qt.CursorShape.SizeBDiagCursor,
            'w':  Qt.CursorShape.SizeHorCursor,
            'move': Qt.CursorShape.SizeAllCursor
        }
        return cursors.get(handle, Qt.CursorShape.ArrowCursor)

    def mousePressEvent(self, event: QMouseEvent):
        if self.owner:
            self.owner.set_current_page(self.index)
            
        scene_pos = self.mapToScene(event.pos())
        self.last_mouse_pos = scene_pos
        
        # Check if clicking on selected rectangle's handles
        if self.selected_rect:
            handle = self.get_handle_at_pos(self.selected_rect, scene_pos)
            if handle:
                self.resize_mode = handle
                self.setCursor(self.get_cursor_for_handle(handle))
                return
        
        # Check if clicking on any rectangle
        clicked_rect = None
        for rect in self.annotations:
            rect_pos = rect.pos()
            adjusted_rect = QRectF(rect.rect().x() + rect_pos.x(), rect.rect().y() + rect_pos.y(), 
                                 rect.rect().width(), rect.rect().height())
            if adjusted_rect.contains(scene_pos):
                clicked_rect = rect
                break
        
        if clicked_rect:
            # Select this rectangle
            if self.selected_rect:
                self.selected_rect.deselect()
            self.selected_rect = clicked_rect
            self.selected_rect.select()
            # Force repaint to show selection handles
            self.viewport().update()
            
            # Check if on handle
            handle = self.get_handle_at_pos(self.selected_rect, scene_pos)
            if handle:
                self.resize_mode = handle
                self.setCursor(self.get_cursor_for_handle(handle))
            else:
                self.resize_mode = 'move'
                self.setCursor(Qt.CursorShape.SizeAllCursor)
        else:
            # Deselect current rectangle
            if self.selected_rect:
                self.selected_rect.deselect()
                self.selected_rect = None
                # Force repaint to hide selection handles
                self.viewport().update()
            
            # Start drawing new rectangle if in annotation mode
            if self.annotation_mode and event.button() == Qt.MouseButton.LeftButton:
                self.drawing = True
                self.start_point = scene_pos
                pen = QPen(self.annotation_color, self.annotation_width)
                brush = QBrush(QColor(
                    self.annotation_color.red(),
                    self.annotation_color.green(),
                    self.annotation_color.blue(),
                    50
                ))
                self.temp_rect = SelectableRect(QRectF(scene_pos, scene_pos), pen, brush)
                self.scene.addItem(self.temp_rect)
                self.setCursor(Qt.CursorShape.CrossCursor)

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        scene_pos = self.mapToScene(event.pos())
        
        # Handle drawing new rectangle
        if self.drawing and self.temp_rect:
            rect = QRectF(self.start_point, scene_pos).normalized()
            self.temp_rect.setRect(rect)
            super().mouseMoveEvent(event)
            return
        
        # Handle resizing/moving selected rectangle
        if self.selected_rect and self.resize_mode and self.last_mouse_pos:
            # Force full viewport repaint to avoid artifacts
            self.viewport().update()
            delta = scene_pos - self.last_mouse_pos
            self.resize_rectangle(delta)
            self.last_mouse_pos = scene_pos
            # Force another repaint after the operation
            self.viewport().update()
            return
        
        # Update cursor based on what's under mouse
        if self.selected_rect:
            handle = self.get_handle_at_pos(self.selected_rect, scene_pos)
            if handle:
                self.setCursor(self.get_cursor_for_handle(handle))
            elif self.annotation_mode:
                self.setCursor(Qt.CursorShape.CrossCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            # Check if over any rectangle
            over_rect = False
            for rect in self.annotations:
                rect_pos = rect.pos()
                adjusted_rect = QRectF(rect.rect().x() + rect_pos.x(), rect.rect().y() + rect_pos.y(), 
                                     rect.rect().width(), rect.rect().height())
                if adjusted_rect.contains(scene_pos):
                    over_rect = True
                    break
            
            if over_rect:
                self.setCursor(Qt.CursorShape.ArrowCursor)
            elif self.annotation_mode:
                self.setCursor(Qt.CursorShape.CrossCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
                
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        # Finish drawing new rectangle
        if self.drawing and self.temp_rect:
            self.drawing = False
            rect = self.temp_rect.rect()
            if rect.width() > 5 and rect.height() > 5:
                self.annotations.append(self.temp_rect)
                # Select the newly created rectangle
                if self.selected_rect:
                    self.selected_rect.deselect()
                self.selected_rect = self.temp_rect
                self.selected_rect.select()
            else:
                self.scene.removeItem(self.temp_rect)
            self.temp_rect = None
            # Force full repaint after drawing
            self.viewport().update()
        
        # Finish resize/move
        if self.resize_mode:
            self.resize_mode = None
            self.last_mouse_pos = None
            # Force full repaint after resize/move
            self.viewport().update()
        
        super().mouseReleaseEvent(event)

    def resize_rectangle(self, delta):
        """Resize rectangle based on current resize mode"""
        if not self.selected_rect or not self.resize_mode:
            return
            
        rect = self.selected_rect.rect()
        pos = self.selected_rect.pos()
        
        if self.resize_mode == 'move':
            # Move the entire rectangle
            new_pos = pos + delta
            self.selected_rect.setPos(new_pos)
        else:
            # Resize based on handle
            new_rect = QRectF(rect)
            
            if 'n' in self.resize_mode:  # Top
                new_rect.setTop(rect.top() + delta.y())
            if 's' in self.resize_mode:  # Bottom
                new_rect.setBottom(rect.bottom() + delta.y())
            if 'w' in self.resize_mode:  # Left
                new_rect.setLeft(rect.left() + delta.x())
            if 'e' in self.resize_mode:  # Right
                new_rect.setRight(rect.right() + delta.x())
            
            # Ensure minimum size
            if new_rect.width() > 10 and new_rect.height() > 10:
                self.selected_rect.setRect(new_rect)
        
        # Force viewport update to prevent artifacts
        self.viewport().update()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete and self.selected_rect:
            self.scene.removeItem(self.selected_rect)
            if self.selected_rect in self.annotations:
                self.annotations.remove(self.selected_rect)
            self.selected_rect = None
        super().keyPressEvent(event)

    def clear_annotations(self):
        for ann in self.annotations:
            self.scene.removeItem(ann)
        self.annotations.clear()
        self.selected_rect = None

    def paintEvent(self, event):
        super().paintEvent(event)
        
        # Draw resize handles for selected rectangle
        if self.selected_rect and self.selected_rect.is_selected:
            painter = QPainter(self.viewport())
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            
            # Get rectangle in viewport coordinates
            rect = self.selected_rect.rect()
            rect_pos = self.selected_rect.pos()
            scene_rect = QRectF(rect.x() + rect_pos.x(), rect.y() + rect_pos.y(), rect.width(), rect.height())
            viewport_rect = self.mapFromScene(scene_rect).boundingRect()
            
            # Draw handles
            handle_size = 6
            pen = QPen(QColor(0, 0, 0), 1)
            brush = QBrush(QColor(255, 255, 255))
            painter.setPen(pen)
            painter.setBrush(brush)
            
            # Corner and side handle positions
            handles = [
                QPointF(viewport_rect.left(), viewport_rect.top()),      # nw
                QPointF(viewport_rect.center().x(), viewport_rect.top()), # n
                QPointF(viewport_rect.right(), viewport_rect.top()),     # ne
                QPointF(viewport_rect.right(), viewport_rect.center().y()), # e
                QPointF(viewport_rect.right(), viewport_rect.bottom()),  # se
                QPointF(viewport_rect.center().x(), viewport_rect.bottom()), # s
                QPointF(viewport_rect.left(), viewport_rect.bottom()),   # sw
                QPointF(viewport_rect.left(), viewport_rect.center().y()) # w
            ]
            
            for handle_pos in handles:
                handle_rect = QRectF(handle_pos.x() - handle_size/2, handle_pos.y() - handle_size/2, 
                                   handle_size, handle_size)
                painter.drawRect(handle_rect)

class PDFViewer(QWidget):
    """Single PDF viewer widget with rectangle annotation and per-page/global rotation"""

    def __init__(self, viewer_id: str, annotation_color: QColor, parent=None):
        super().__init__(parent)
        self.viewer_id = viewer_id
        self.annotation_color = annotation_color
        self.pdf_document = None
        self.global_rotation = 0
        self.rotate_all = False
        self.page_widgets = []
        self.current_page_index = 0

        self.init_ui()

    def init_ui(self):
        self.layout = QVBoxLayout()

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

        self.toggle_rotate_btn = QPushButton("Rotate Individually")
        self.toggle_rotate_btn.setCheckable(True)
        self.toggle_rotate_btn.setToolTip("Toggle between rotating all pages or just the current page")
        self.toggle_rotate_btn.clicked.connect(self.toggle_rotate_mode)
        self.toolbar_layout.addWidget(self.toggle_rotate_btn)

        self.toolbar_layout.addStretch()
        self.layout.addLayout(self.toolbar_layout)
        self.hide_toolbar()

        self.open_btn = QPushButton("Open PDF")
        self.open_btn.clicked.connect(self.open_pdf)
        self.open_btn.setFixedWidth(200)
        self.open_btn.setFixedHeight(50)
        self.open_btn.setStyleSheet("font-size: 16px;")
        self.layout.addWidget(self.open_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout()
        self.scroll_content.setLayout(self.scroll_layout)
        self.scroll_area.setWidget(self.scroll_content)
        self.layout.addWidget(self.scroll_area)

        self.page_counter_label = QLabel("Page — / —")
        self.page_counter_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.page_counter_label.setStyleSheet("color: #666; font-size: 11px; padding: 2px 4px;")
        self.layout.addWidget(self.page_counter_label)

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
            self, "Open Question PDF", "", "PDF Files (*.pdf)"
        )
        if file_path:
            self.load_pdf(file_path)

    def load_pdf(self, file_path: str):
        try:
            self.pdf_document = fitz.open(file_path)
            self.global_rotation = 0
            self.current_page_index = 0
            self.open_btn.hide()
            self.show_toolbar()
            self.display_pages()
        except Exception as e:
            print(f"Error loading PDF: {e}")

    def display_pages(self):
        if not self.pdf_document:
            return

        self.page_widgets.clear()
        while self.scroll_layout.count():
            item = self.scroll_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for page_num in range(len(self.pdf_document)):
            page = self.pdf_document[page_num]
            pdf_page = PDFPage(page, page_num, owner=self, annotation_color=self.annotation_color)
            pdf_page.rotation = self.global_rotation if self.rotate_all else 0
            pdf_page.render_page()
            self.scroll_layout.addWidget(pdf_page)
            self.page_widgets.append(pdf_page)

        self.update_page_counter_label()

    def update_page_counter_label(self):
        total = len(self.page_widgets)
        if total == 0:
            self.page_counter_label.setText("Page — / —")
        else:
            self.page_counter_label.setText(f"Page {self.current_page_index + 1} / {total}")

    def set_current_page(self, index: int):
        if not self.page_widgets:
            return
        index = max(0, min(index, len(self.page_widgets) - 1))
        if index != self.current_page_index:
            self.current_page_index = index
            self.update_page_counter_label()

    def update_current_page_from_scroll(self):
        if not self.page_widgets:
            return
        vbar = self.scroll_area.verticalScrollBar()
        vy = vbar.value()
        viewport_h = self.scroll_area.viewport().height()
        viewport_center_y = vy + viewport_h / 2

        closest_idx = 0
        closest_dist = float('inf')
        for i, w in enumerate(self.page_widgets):
            top = w.y()
            h = w.height()
            center = top + h / 2
            dist = abs(center - viewport_center_y)
            if dist < closest_dist:
                closest_dist = dist
                closest_idx = i
        self.set_current_page(closest_idx)

    def rotate_pages(self, angle: int):
        if self.rotate_all:
            self.global_rotation = (self.global_rotation + angle) % 360
            current_idx = self.current_page_index
            self.display_pages()
            self.set_current_page(current_idx)
        else:
            if not self.page_widgets:
                return
            self.page_widgets[self.current_page_index].rotate(angle)

class DualPDFViewerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("StudyAssistant")
        self.setGeometry(100, 100, 1600, 900)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QHBoxLayout()
        layout.setSpacing(0)  # Remove spacing between viewers

        # Left viewer = blue (640px)
        self.viewer1 = PDFViewer("1", QColor(0, 0, 255, 150))
        self.viewer1.setFixedWidth(640)
        
        # Right viewer = orange (640px)
        self.viewer2 = PDFViewer("2", QColor(255, 165, 0, 150))
        self.viewer2.setFixedWidth(640)
        
        # Third pane = empty (320px)
        self.third_pane = QWidget()
        self.third_pane.setFixedWidth(320)
        self.third_pane.setStyleSheet("background-color: #1e1e1e; border-left: 1px solid #171717;")

        layout.addWidget(self.viewer1)
        layout.addWidget(self.viewer2)
        layout.addWidget(self.third_pane)

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
