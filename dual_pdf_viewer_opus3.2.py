#!/usr/bin/env python3
"""
Dual PDF Viewer with Rectangle Annotations + Auto-Save + Home Screen
Requirements: pip install PyQt6 PyMuPDF Pillow

created with Claude. Account: Burhan Ra'if Kouri
"""

import sys
import json
import os
import time
from pathlib import Path
import fitz  # PyMuPDF
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFileDialog, QScrollArea, QStatusBar, 
    QGraphicsView, QGraphicsScene, QGraphicsRectItem, QListWidget,
    QListWidgetItem, QMessageBox, QLineEdit, QDialog, QDialogButtonBox,
    QFormLayout, QFrame, QTextEdit
)
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal, QTimer
from PyQt6.QtGui import QPixmap, QImage, QPainter, QColor, QPen, QBrush, QMouseEvent, QFont, QCloseEvent

class SavePairDialog(QDialog):
    """Dialog for entering pair name when saving"""
    def __init__(self, parent=None, default_name="", default_description=""):
        super().__init__(parent)
        self.setWindowTitle("Save PDF Pair")
        self.setModal(True)
        self.resize(400, 150)
        
        layout = QFormLayout()
        
        self.name_edit = QLineEdit()
        self.name_edit.setText(default_name)
        self.name_edit.setPlaceholderText("Enter a name for this PDF pair...")
        layout.addRow("Pair Name:", self.name_edit)
        
        self.description_edit = QTextEdit()
        self.description_edit.setPlainText(default_description)
        self.description_edit.setPlaceholderText("Optional description...")
        self.description_edit.setMaximumHeight(60)
        layout.addRow("Description:", self.description_edit)
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
        self.setLayout(layout)
        
    def get_data(self):
        return {
            'name': self.name_edit.text().strip(),
            'description': self.description_edit.toPlainText().strip()
        }

class SelectableRect(QGraphicsRectItem):
    """Rectangle that can be selected and shows resize handles like MS Paint"""
    
    def __init__(self, rect, pen, brush, page_widget=None, parent=None):
        super().__init__(rect, parent)
        self.setPen(pen)
        self.setBrush(brush)
        self.original_pen = pen
        self.selected_pen = QPen(pen.color(), pen.width())
        self.selected_pen.setStyle(Qt.PenStyle.DashLine)
        self.is_selected = False
        self.page_widget = page_widget  # Reference to the page widget for notifications
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, False)
        
    def select(self):
        self.is_selected = True
        self.setPen(self.selected_pen)
        
    def deselect(self):
        self.is_selected = False
        self.setPen(self.original_pen)
        
    def setRect(self, rect):
        super().setRect(rect)
        if self.page_widget:
            self.page_widget.emit_annotation_modified()
        
    def setPos(self, pos):
        super().setPos(pos)
        if self.page_widget:
            self.page_widget.emit_annotation_modified()

class PDFPage(QGraphicsView):
    """Custom widget for displaying a PDF page with MS Paint-style rectangle annotations"""
    
    annotation_modified = pyqtSignal()  # Signal when annotations are modified

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
        self.resize_mode = None
        self.last_mouse_pos = None
        
        self.annotations = []
        self.rotation = 0
        self.page = page
        self.index = index
        self.owner = owner
        self.annotation_mode = False
        self.page_width = 0
        self.page_height = 0

        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

        # Annotation settings
        self.annotation_color = annotation_color
        self.annotation_width = 2
        self.handle_size = 6

        self.render_page()

    def emit_annotation_modified(self):
        """Emit signal that annotations were modified"""
        self.annotation_modified.emit()

    def render_page(self):
        mat = fitz.Matrix(1, 1).prerotate(self.rotation)
        pix = self.page.get_pixmap(matrix=mat, alpha=False)
        img_data = pix.tobytes("ppm")
        qimg = QImage.fromData(img_data)
        qpixmap = QPixmap.fromImage(qimg)

        self.page_width = qpixmap.width()
        self.page_height = qpixmap.height()

        self.scene.clear()
        self.pixmap_item = self.scene.addPixmap(qpixmap)
        self.scene.setSceneRect(QRectF(qpixmap.rect()))
        self.setMinimumHeight(qpixmap.height() + 20)
        self.annotations = []
        self.selected_rect = None

    def load_annotations(self, annotation_data):
        """Load annotations from relative coordinates"""
        for ann_data in annotation_data:
            coords = ann_data['coordinates']
            
            # Convert relative coordinates to absolute pixel coordinates
            x = coords['x'] * self.page_width
            y = coords['y'] * self.page_height
            width = coords['width'] * self.page_width
            height = coords['height'] * self.page_height
            
            rect = QRectF(x, y, width, height)
            pen = QPen(self.annotation_color, self.annotation_width)
            brush = QBrush(QColor(
                self.annotation_color.red(),
                self.annotation_color.green(),
                self.annotation_color.blue(),
                50
            ))
            
            annotation = SelectableRect(rect, pen, brush, page_widget=self)
            self.scene.addItem(annotation)
            self.annotations.append(annotation)

    def get_annotations_data(self):
        """Convert annotations to relative coordinates for saving"""
        annotations_data = []
        for annotation in self.annotations:
            rect = annotation.rect()
            pos = annotation.pos()
            
            # Calculate absolute coordinates
            abs_x = rect.x() + pos.x()
            abs_y = rect.y() + pos.y()
            abs_width = rect.width()
            abs_height = rect.height()
            
            # Convert to relative coordinates
            rel_x = abs_x / self.page_width if self.page_width > 0 else 0
            rel_y = abs_y / self.page_height if self.page_height > 0 else 0
            rel_width = abs_width / self.page_width if self.page_width > 0 else 0
            rel_height = abs_height / self.page_height if self.page_height > 0 else 0
            
            annotations_data.append({
                'coordinates': {
                    'x': rel_x,
                    'y': rel_y,
                    'width': rel_width,
                    'height': rel_height
                }
            })
        
        return annotations_data

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
        
        rect_pos = rect_item.pos()
        adjusted_rect = QRectF(rect.x() + rect_pos.x(), rect.y() + rect_pos.y(), rect.width(), rect.height())
        
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
        
        if self.selected_rect:
            handle = self.get_handle_at_pos(self.selected_rect, scene_pos)
            if handle:
                self.resize_mode = handle
                self.setCursor(self.get_cursor_for_handle(handle))
                return
        
        clicked_rect = None
        for rect in self.annotations:
            rect_pos = rect.pos()
            adjusted_rect = QRectF(rect.rect().x() + rect_pos.x(), rect.rect().y() + rect_pos.y(), 
                                 rect.rect().width(), rect.rect().height())
            if adjusted_rect.contains(scene_pos):
                clicked_rect = rect
                break
        
        if clicked_rect:
            if self.selected_rect:
                self.selected_rect.deselect()
            self.selected_rect = clicked_rect
            self.selected_rect.select()
            self.viewport().update()
            
            handle = self.get_handle_at_pos(self.selected_rect, scene_pos)
            if handle:
                self.resize_mode = handle
                self.setCursor(self.get_cursor_for_handle(handle))
            else:
                self.resize_mode = 'move'
                self.setCursor(Qt.CursorShape.SizeAllCursor)
        else:
            if self.selected_rect:
                self.selected_rect.deselect()
                self.selected_rect = None
                self.viewport().update()
            
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
                self.temp_rect = SelectableRect(QRectF(scene_pos, scene_pos), pen, brush, page_widget=self)
                self.scene.addItem(self.temp_rect)
                self.setCursor(Qt.CursorShape.CrossCursor)

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        scene_pos = self.mapToScene(event.pos())
        
        if self.drawing and self.temp_rect:
            rect = QRectF(self.start_point, scene_pos).normalized()
            self.temp_rect.setRect(rect)
            super().mouseMoveEvent(event)
            return
        
        if self.selected_rect and self.resize_mode and self.last_mouse_pos:
            self.viewport().update()
            delta = scene_pos - self.last_mouse_pos
            self.resize_rectangle(delta)
            self.last_mouse_pos = scene_pos
            self.viewport().update()
            return
        
        if self.selected_rect:
            handle = self.get_handle_at_pos(self.selected_rect, scene_pos)
            if handle:
                self.setCursor(self.get_cursor_for_handle(handle))
            elif self.annotation_mode:
                self.setCursor(Qt.CursorShape.CrossCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
        else:
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
        if self.drawing and self.temp_rect:
            self.drawing = False
            rect = self.temp_rect.rect()
            if rect.width() > 5 and rect.height() > 5:
                self.annotations.append(self.temp_rect)
                if self.selected_rect:
                    self.selected_rect.deselect()
                self.selected_rect = self.temp_rect
                self.selected_rect.select()
                self.emit_annotation_modified()  # New annotation created
            else:
                self.scene.removeItem(self.temp_rect)
            self.temp_rect = None
            self.viewport().update()
        
        if self.resize_mode:
            self.resize_mode = None
            self.last_mouse_pos = None
            self.viewport().update()
        
        super().mouseReleaseEvent(event)

    def resize_rectangle(self, delta):
        """Resize rectangle based on current resize mode"""
        if not self.selected_rect or not self.resize_mode:
            return
            
        rect = self.selected_rect.rect()
        pos = self.selected_rect.pos()
        
        if self.resize_mode == 'move':
            new_pos = pos + delta
            self.selected_rect.setPos(new_pos)
        else:
            new_rect = QRectF(rect)
            
            if 'n' in self.resize_mode:
                new_rect.setTop(rect.top() + delta.y())
            if 's' in self.resize_mode:
                new_rect.setBottom(rect.bottom() + delta.y())
            if 'w' in self.resize_mode:
                new_rect.setLeft(rect.left() + delta.x())
            if 'e' in self.resize_mode:
                new_rect.setRight(rect.right() + delta.x())
            
            if new_rect.width() > 10 and new_rect.height() > 10:
                self.selected_rect.setRect(new_rect)
        
        self.viewport().update()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete and self.selected_rect:
            self.scene.removeItem(self.selected_rect)
            if self.selected_rect in self.annotations:
                self.annotations.remove(self.selected_rect)
            self.selected_rect = None
            self.emit_annotation_modified()  # Annotation deleted
        super().keyPressEvent(event)

    def clear_annotations(self):
        for ann in self.annotations:
            self.scene.removeItem(ann)
        self.annotations.clear()
        self.selected_rect = None
        self.emit_annotation_modified()  # Annotations cleared

    def paintEvent(self, event):
        super().paintEvent(event)
        
        if self.selected_rect and self.selected_rect.is_selected:
            painter = QPainter(self.viewport())
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            
            rect = self.selected_rect.rect()
            rect_pos = self.selected_rect.pos()
            scene_rect = QRectF(rect.x() + rect_pos.x(), rect.y() + rect_pos.y(), rect.width(), rect.height())
            viewport_rect = self.mapFromScene(scene_rect).boundingRect()
            
            handle_size = 6
            pen = QPen(QColor(0, 0, 0), 1)
            brush = QBrush(QColor(255, 255, 255))
            painter.setPen(pen)
            painter.setBrush(brush)
            
            handles = [
                QPointF(viewport_rect.left(), viewport_rect.top()),
                QPointF(viewport_rect.center().x(), viewport_rect.top()),
                QPointF(viewport_rect.right(), viewport_rect.top()),
                QPointF(viewport_rect.right(), viewport_rect.center().y()),
                QPointF(viewport_rect.right(), viewport_rect.bottom()),
                QPointF(viewport_rect.center().x(), viewport_rect.bottom()),
                QPointF(viewport_rect.left(), viewport_rect.bottom()),
                QPointF(viewport_rect.left(), viewport_rect.center().y())
            ]
            
            for handle_pos in handles:
                handle_rect = QRectF(handle_pos.x() - handle_size/2, handle_pos.y() - handle_size/2, 
                                   handle_size, handle_size)
                painter.drawRect(handle_rect)

class PDFViewer(QWidget):
    """Single PDF viewer widget with rectangle annotation and per-page/global rotation"""
    
    annotations_changed = pyqtSignal()  # Signal when any annotations change

    def __init__(self, viewer_id: str, annotation_color: QColor, parent=None):
        super().__init__(parent)
        self.viewer_id = viewer_id
        self.annotation_color = annotation_color
        self.pdf_document = None
        self.pdf_path = None
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

    def connect_page_signals(self, page_widget):
        """Connect annotation change signals from a page widget"""
        page_widget.annotation_modified.connect(self.annotations_changed.emit)

    def load_pdf_with_annotations(self, pdf_path, annotations_data):
        """Load PDF and apply saved annotations"""
        self.load_pdf(pdf_path)
        
        # Apply annotations to each page
        for page_num, page_annotations in annotations_data.items():
            page_index = int(page_num)
            if page_index < len(self.page_widgets):
                self.page_widgets[page_index].load_annotations(page_annotations)

    def get_all_annotations_data(self):
        """Get annotations data for all pages"""
        all_annotations = {}
        for i, page_widget in enumerate(self.page_widgets):
            page_annotations = page_widget.get_annotations_data()
            if page_annotations:  # Only save pages with annotations
                all_annotations[str(i)] = page_annotations
        return all_annotations

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
            self, "Open PDF", "", "PDF Files (*.pdf)"
        )
        if file_path:
            self.load_pdf(file_path)

    def load_pdf(self, file_path: str):
        try:
            self.pdf_document = fitz.open(file_path)
            self.pdf_path = file_path
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
            self.connect_page_signals(pdf_page)  # Connect annotation change signals
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

class HomeScreen(QWidget):
    """Home screen showing saved PDF pairs"""
    
    pair_selected = pyqtSignal(dict)  # Signal emitted when a pair is selected
    new_pair_requested = pyqtSignal()  # Signal emitted when new pair button is clicked
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.data_file = "pdf_pairs.json"
        self.init_ui()
        self.load_pairs()
    
    def init_ui(self):
        layout = QVBoxLayout()
        
        # Title
        title = QLabel("StudyAssistant - PDF Pairs")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 24px; font-weight: bold; margin: 20px 0;")
        layout.addWidget(title)
        
        # New pair button
        new_pair_btn = QPushButton("Create New PDF Pair")
        new_pair_btn.setFixedHeight(40)
        new_pair_btn.setStyleSheet("font-size: 14px; background-color: #0078d4; color: white;")
        new_pair_btn.clicked.connect(self.new_pair_requested.emit)
        layout.addWidget(new_pair_btn)
        
        # Pairs list
        self.pairs_list = QListWidget()
        self.pairs_list.itemDoubleClicked.connect(self.on_pair_selected)
        layout.addWidget(self.pairs_list)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        open_btn = QPushButton("Open Selected")
        open_btn.clicked.connect(self.open_selected_pair)
        button_layout.addWidget(open_btn)
        
        delete_btn = QPushButton("Delete Selected")
        delete_btn.clicked.connect(self.delete_selected_pair)
        delete_btn.setStyleSheet("background-color: #dc3545; color: white;")
        button_layout.addWidget(delete_btn)
        
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def load_pairs(self):
        """Load PDF pairs from JSON file"""
        self.pairs_list.clear()
        
        if not os.path.exists(self.data_file):
            return
            
        try:
            with open(self.data_file, 'r') as f:
                data = json.load(f)
                
            for pair_id, pair_data in data.get('pairs', {}).items():
                # Check if both PDFs still exist
                pdf1_exists = os.path.exists(pair_data.get('pdf1_path', ''))
                pdf2_exists = os.path.exists(pair_data.get('pdf2_path', ''))
                
                item = QListWidgetItem()
                name = pair_data.get('name', f'Pair {pair_id}')
                description = pair_data.get('description', '')
                
                # Create display text
                display_text = name
                if description:
                    display_text += f"\n{description}"
                
                # Add status indicators
                if not pdf1_exists or not pdf2_exists:
                    display_text += "\n⚠️ Some PDF files are missing"
                    item.setBackground(QColor(255, 200, 200))  # Light red background
                
                item.setText(display_text)
                item.setData(Qt.ItemDataRole.UserRole, pair_data)
                self.pairs_list.addItem(item)
                
        except Exception as e:
            print(f"Error loading pairs: {e}")
    
    def on_pair_selected(self, item):
        """Handle double-click on pair item"""
        pair_data = item.data(Qt.ItemDataRole.UserRole)
        if pair_data:
            self.pair_selected.emit(pair_data)
    
    def open_selected_pair(self):
        """Open the currently selected pair"""
        current_item = self.pairs_list.currentItem()
        if current_item:
            self.on_pair_selected(current_item)
    
    def delete_selected_pair(self):
        """Delete the selected pair"""
        current_item = self.pairs_list.currentItem()
        if not current_item:
            return
            
        pair_data = current_item.data(Qt.ItemDataRole.UserRole)
        name = pair_data.get('name', 'Unknown')
        
        reply = QMessageBox.question(
            self, 'Delete PDF Pair',
            f'Are you sure you want to delete "{name}"?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # Remove from JSON file
            try:
                if os.path.exists(self.data_file):
                    with open(self.data_file, 'r') as f:
                        data = json.load(f)
                    
                    # Find and remove the pair
                    pairs = data.get('pairs', {})
                    pair_id_to_remove = None
                    for pair_id, stored_pair_data in pairs.items():
                        if (stored_pair_data.get('name') == pair_data.get('name') and
                            stored_pair_data.get('pdf1_path') == pair_data.get('pdf1_path') and
                            stored_pair_data.get('pdf2_path') == pair_data.get('pdf2_path')):
                            pair_id_to_remove = pair_id
                            break
                    
                    if pair_id_to_remove:
                        del pairs[pair_id_to_remove]
                        data['pairs'] = pairs
                        
                        with open(self.data_file, 'w') as f:
                            json.dump(data, f, indent=2)
                        
                        self.load_pairs()  # Refresh the list
                        
            except Exception as e:
                QMessageBox.critical(self, 'Error', f'Failed to delete pair: {e}')

class DualPDFViewerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.data_file = "pdf_pairs.json"
        self.current_pair_id = None
        self.current_pair_name = ""
        self.current_pair_description = ""
        self.has_unsaved_changes = False
        self.is_closing = False
        
        # Auto-save timer - used for debouncing rapid changes
        self.autosave_timer = QTimer()
        self.autosave_timer.setSingleShot(True)
        self.autosave_timer.timeout.connect(self.perform_autosave)
        
        self.init_ui()
        
        # Check if we should show home screen or viewer
        if self.has_valid_pairs():
            self.show_home_screen()
        else:
            self.show_pdf_viewer()

    def has_valid_pairs(self):
        """Check if there are any valid PDF pairs saved"""
        if not os.path.exists(self.data_file):
            return False
            
        try:
            with open(self.data_file, 'r') as f:
                data = json.load(f)
            
            pairs = data.get('pairs', {})
            for pair_data in pairs.values():
                pdf1_path = pair_data.get('pdf1_path', '')
                pdf2_path = pair_data.get('pdf2_path', '')
                if os.path.exists(pdf1_path) and os.path.exists(pdf2_path):
                    return True
            return False
        except:
            return False

    def init_ui(self):
        self.setWindowTitle("StudyAssistant")
        self.setGeometry(100, 100, 1600, 900)

        # Create stacked widget to switch between home screen and viewer
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout()
        self.central_widget.setLayout(self.main_layout)

        # Home screen
        self.home_screen = HomeScreen()
        self.home_screen.pair_selected.connect(self.load_pair)
        self.home_screen.new_pair_requested.connect(self.show_pdf_viewer)

        # PDF viewer layout
        self.viewer_widget = QWidget()
        self.init_pdf_viewer()

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

    def init_pdf_viewer(self):
        """Initialize the PDF viewer components"""
        layout = QVBoxLayout()
        
        # Top toolbar
        toolbar = QHBoxLayout()
        
        self.home_btn = QPushButton("🏠 Home")
        self.home_btn.clicked.connect(self.go_to_home)
        toolbar.addWidget(self.home_btn)
        
        self.save_btn = QPushButton("💾 Save")
        self.save_btn.clicked.connect(self.manual_save_pair)
        toolbar.addWidget(self.save_btn)
        
        # Auto-save status indicator
        self.autosave_label = QLabel("Auto-save: Ready")
        self.autosave_label.setStyleSheet("color: #666; font-size: 11px; padding: 2px 4px;")
        toolbar.addWidget(self.autosave_label)
        
        toolbar.addStretch()
        layout.addLayout(toolbar)
        
        # PDF viewers
        pdf_layout = QHBoxLayout()
        pdf_layout.setSpacing(0)

        # Left viewer = blue (640px)
        self.viewer1 = PDFViewer("1", QColor(0, 0, 255, 150))
        self.viewer1.setFixedWidth(640)
        self.viewer1.annotations_changed.connect(self.on_annotations_changed)
        
        # Right viewer = orange (640px)  
        self.viewer2 = PDFViewer("2", QColor(255, 165, 0, 150))
        self.viewer2.setFixedWidth(640)
        self.viewer2.annotations_changed.connect(self.on_annotations_changed)
        
        # Third pane = empty (320px)
        self.third_pane = QWidget()
        self.third_pane.setFixedWidth(320)
        self.third_pane.setStyleSheet("background-color: #1e1e1e; border-left: 1px solid #171717;")

        pdf_layout.addWidget(self.viewer1)
        pdf_layout.addWidget(self.viewer2)
        pdf_layout.addWidget(self.third_pane)
        
        layout.addLayout(pdf_layout)
        self.viewer_widget.setLayout(layout)

    def on_annotations_changed(self):
        """Called when annotations are modified - triggers auto-save"""
        if not self.is_closing and self.current_pair_id:
            self.has_unsaved_changes = True
            self.autosave_label.setText("Auto-save: Pending...")
            self.autosave_label.setStyleSheet("color: #ff9800; font-size: 11px; padding: 2px 4px;")
            
            # Restart the timer - this debounces rapid changes
            self.autosave_timer.stop()
            self.autosave_timer.start(1000)  # Wait 1 second after last change

    def perform_autosave(self):
        """Perform the actual auto-save operation"""
        if not self.has_unsaved_changes or not self.current_pair_id:
            return
            
        if not self.viewer1.pdf_path or not self.viewer2.pdf_path:
            return
        
        try:
            # Load existing data or create new
            data = {'pairs': {}}
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r') as f:
                    data = json.load(f)
            
            # Collect annotations from both viewers
            pdf1_annotations = self.viewer1.get_all_annotations_data()
            pdf2_annotations = self.viewer2.get_all_annotations_data()
            
            # Update existing pair data or create new
            if self.current_pair_id in data['pairs']:
                pair_data = data['pairs'][self.current_pair_id]
                pair_data['pdf1_annotations'] = pdf1_annotations
                pair_data['pdf2_annotations'] = pdf2_annotations
                pair_data['updated_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
            else:
                # This shouldn't happen normally, but handle it just in case
                pair_data = {
                    'pair_id': self.current_pair_id,
                    'name': self.current_pair_name or f"Auto-saved Pair {self.current_pair_id}",
                    'description': self.current_pair_description,
                    'pdf1_path': self.viewer1.pdf_path,
                    'pdf2_path': self.viewer2.pdf_path,
                    'pdf1_annotations': pdf1_annotations,
                    'pdf2_annotations': pdf2_annotations,
                    'created_at': time.strftime('%Y-%m-%d %H:%M:%S'),
                    'updated_at': time.strftime('%Y-%m-%d %H:%M:%S')
                }
                data['pairs'][self.current_pair_id] = pair_data
            
            # Write to file
            with open(self.data_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            self.has_unsaved_changes = False
            self.autosave_label.setText("Auto-save: ✓ Saved")
            self.autosave_label.setStyleSheet("color: #4caf50; font-size: 11px; padding: 2px 4px;")
            
            # Reset to "Ready" after 3 seconds
            QTimer.singleShot(3000, self.reset_autosave_label)
            
        except Exception as e:
            print(f"Auto-save error: {e}")
            self.autosave_label.setText("Auto-save: Error")
            self.autosave_label.setStyleSheet("color: #f44336; font-size: 11px; padding: 2px 4px;")

    def reset_autosave_label(self):
        """Reset auto-save label to ready state"""
        if not self.has_unsaved_changes:
            self.autosave_label.setText("Auto-save: Ready")
            self.autosave_label.setStyleSheet("color: #666; font-size: 11px; padding: 2px 4px;")

    def go_to_home(self):
        """Navigate to home screen with auto-save"""
        if self.has_unsaved_changes and self.current_pair_id:
            self.perform_autosave()
        self.show_home_screen()

    def show_home_screen(self):
        """Show the home screen"""
        # Auto-save before leaving if needed
        if self.has_unsaved_changes and self.current_pair_id:
            self.perform_autosave()
        
        # Clear the main layout
        while self.main_layout.count():
            item = self.main_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        
        # Add home screen
        self.main_layout.addWidget(self.home_screen)
        self.home_screen.load_pairs()  # Refresh pairs list
        self.status_bar.showMessage("Home - Select a PDF pair or create a new one")

    def show_pdf_viewer(self):
        """Show the PDF viewer"""
        # Clear the main layout
        while self.main_layout.count():
            item = self.main_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        
        # Add PDF viewer
        self.main_layout.addWidget(self.viewer_widget)
        self.status_bar.showMessage("PDF Viewer - Open PDFs to start annotating")

    def load_pair(self, pair_data):
        """Load a PDF pair with its annotations"""
        try:
            pdf1_path = pair_data.get('pdf1_path', '')
            pdf2_path = pair_data.get('pdf2_path', '')
            
            # Check if files exist
            if not os.path.exists(pdf1_path):
                QMessageBox.warning(self, 'File Not Found', f'PDF 1 not found: {pdf1_path}')
                return
                
            if not os.path.exists(pdf2_path):
                QMessageBox.warning(self, 'File Not Found', f'PDF 2 not found: {pdf2_path}')
                return
            
            # Switch to PDF viewer
            self.show_pdf_viewer()
            
            # Load PDFs and annotations
            pdf1_annotations = pair_data.get('pdf1_annotations', {})
            pdf2_annotations = pair_data.get('pdf2_annotations', {})
            
            self.viewer1.load_pdf_with_annotations(pdf1_path, pdf1_annotations)
            self.viewer2.load_pdf_with_annotations(pdf2_path, pdf2_annotations)
            
            # Store current pair info
            self.current_pair_id = pair_data.get('pair_id')
            self.current_pair_name = pair_data.get('name', '')
            self.current_pair_description = pair_data.get('description', '')
            self.has_unsaved_changes = False
            
            name = pair_data.get('name', 'Unknown')
            self.status_bar.showMessage(f"Loaded pair: {name}")
            
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Failed to load PDF pair: {e}')

    def manual_save_pair(self):
        """Manually save the current PDF pair with annotations"""
        # Check if both viewers have PDFs loaded
        if not self.viewer1.pdf_path or not self.viewer2.pdf_path:
            QMessageBox.warning(self, 'Save Error', 'Please load PDFs in both viewers before saving.')
            return
        
        # If we have a current pair, just update it
        if self.current_pair_id:
            self.perform_autosave()
            QMessageBox.information(self, 'Save Successful', f'PDF pair "{self.current_pair_name}" has been updated.')
            return
        
        # Get pair name from user for new pair
        dialog = SavePairDialog(self, self.current_pair_name, self.current_pair_description)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        
        pair_info = dialog.get_data()
        if not pair_info['name']:
            QMessageBox.warning(self, 'Save Error', 'Please enter a name for the PDF pair.')
            return
        
        try:
            # Load existing data or create new
            data = {'pairs': {}}
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r') as f:
                    data = json.load(f)
            
            # Generate unique pair ID
            if not self.current_pair_id:
                self.current_pair_id = str(int(time.time()))
            
            # Store pair info
            self.current_pair_name = pair_info['name']
            self.current_pair_description = pair_info['description']
            
            # Collect annotations from both viewers
            pdf1_annotations = self.viewer1.get_all_annotations_data()
            pdf2_annotations = self.viewer2.get_all_annotations_data()
            
            # Save pair data
            pair_data = {
                'pair_id': self.current_pair_id,
                'name': self.current_pair_name,
                'description': self.current_pair_description,
                'pdf1_path': self.viewer1.pdf_path,
                'pdf2_path': self.viewer2.pdf_path,
                'pdf1_annotations': pdf1_annotations,
                'pdf2_annotations': pdf2_annotations,
                'created_at': time.strftime('%Y-%m-%d %H:%M:%S'),
                'updated_at': time.strftime('%Y-%m-%d %H:%M:%S')
            }
            
            data['pairs'][self.current_pair_id] = pair_data
            
            # Write to file
            with open(self.data_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            self.has_unsaved_changes = False
            self.status_bar.showMessage(f"Saved pair: {self.current_pair_name}")
            QMessageBox.information(self, 'Save Successful', f'PDF pair "{self.current_pair_name}" has been saved successfully.')
            
        except Exception as e:
            QMessageBox.critical(self, 'Save Error', f'Failed to save PDF pair: {e}')

    def closeEvent(self, event: QCloseEvent):
        """Handle application close event with auto-save"""
        self.is_closing = True
        
        # Perform final auto-save if needed
        if self.has_unsaved_changes and self.current_pair_id:
            try:
                self.perform_autosave()
            except Exception as e:
                print(f"Error during final auto-save: {e}")
        
        event.accept()

def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    viewer = DualPDFViewerApp()
    viewer.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
