#!/usr/bin/env python3
"""
Dual PDF Viewer with Rectangle Annotations + Auto-Save + Home Screen + Annotation Lock Mode
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
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal, QTimer, QEvent
from PyQt6.QtGui import QPixmap, QImage, QPainter, QColor, QPen, QBrush, QMouseEvent, QFont, QCloseEvent, QCursor

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
    annotation_created = pyqtSignal()   # Signal when a new annotation is created (for lock mode)
    selection_changed = pyqtSignal()    # Signal when selection changes

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
        app = self.window()
        if app.auto_teleport_mode and int(self.owner.viewer_id) != app.current_active_viewer:
            return

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
            self.selection_changed.emit()  # Emit selection changed signal
            
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
                self.selection_changed.emit()  # Emit selection changed signal
            
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
        app = self.window()
        if app.auto_teleport_mode and int(self.owner.viewer_id) != app.current_active_viewer:
            return

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
        app = self.window()
        if app.auto_teleport_mode and int(self.owner.viewer_id) != app.current_active_viewer:
            return

        if self.drawing and self.temp_rect:
            self.drawing = False
            rect = self.temp_rect.rect()
            if rect.width() > 5 and rect.height() > 5:
                self.annotations.append(self.temp_rect)
                if self.selected_rect:
                    self.selected_rect.deselect()
                self.selected_rect = self.temp_rect
                self.selected_rect.select()
                self.selection_changed.emit()  # Emit selection changed signal
                self.emit_annotation_modified()  # Existing annotation modified signal
                self.annotation_created.emit()   # NEW: Signal for lock mode
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
        app = self.window()
        if app.auto_teleport_mode and int(self.owner.viewer_id) != app.current_active_viewer:
            return

        if event.key() == Qt.Key.Key_Delete and self.selected_rect:
            self.scene.removeItem(self.selected_rect)
            if self.selected_rect in self.annotations:
                self.annotations.remove(self.selected_rect)
            self.selected_rect = None
            self.selection_changed.emit()  # Emit selection changed signal
            self.emit_annotation_modified()  # Annotation deleted
        super().keyPressEvent(event)

    def clear_annotations(self):
        for ann in self.annotations:
            self.scene.removeItem(ann)
        self.annotations.clear()
        if self.selected_rect:
            self.selected_rect.deselect()
        self.selected_rect = None
        self.selection_changed.emit()  # Emit selection changed signal
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
    annotation_created = pyqtSignal()   # Signal when a new annotation is created (for lock mode)
    selection_changed = pyqtSignal()    # Signal when selection changes
    pdf_loaded = pyqtSignal()          # Signal when PDF is loaded

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
        page_widget.annotation_created.connect(self.annotation_created.emit)  # NEW
        page_widget.selection_changed.connect(self.selection_changed.emit)  # NEW: Connect selection changed signal

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
    
    def hide_specific_buttons(self):
        """Hide specific buttons for link mode"""
        self.rect_btn.hide()
        self.clear_ann_btn.hide()
        self.rotate_left_btn.hide()
        self.rotate_right_btn.hide()
        self.toggle_rotate_btn.hide()
    
    def show_specific_buttons(self):
        """Show specific buttons for normal mode"""
        self.rect_btn.show()
        self.clear_ann_btn.show()
        self.rotate_left_btn.show()
        self.rotate_right_btn.show()
        self.toggle_rotate_btn.show()

    def reset_viewer(self):
        """Reset viewer to initial empty state"""
        # Clear any loaded PDF
        self.pdf_document = None
        self.pdf_path = None
        self.global_rotation = 0
        self.current_page_index = 0
        
        # Clear all page widgets
        self.page_widgets.clear()
        while self.scroll_layout.count():
            item = self.scroll_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # Hide toolbar and show open button
        self.hide_toolbar()
        self.open_btn.show()
        
        # Reset page counter
        self.update_page_counter_label()
        
        # Emit signal to update annotation counter
        self.annotations_changed.emit()
        
        # Reset navigation state
        if hasattr(self, 'owner') and hasattr(self.owner, 'current_annotation_index'):
            viewer_id = int(self.viewer_id)
            self.owner.current_annotation_index[viewer_id] = 0
            self.owner.all_annotations[viewer_id].clear()
            if hasattr(self.owner, 'update_navigation_labels'):
                self.owner.update_navigation_labels()

    def toggle_annotation(self):
        for w in self.page_widgets:
            w.set_annotation_mode(self.rect_btn.isChecked())

    def clear_annotations(self):
        for w in self.page_widgets:
            w.clear_annotations()
        self.annotations_changed.emit()  # Emit signal when annotations are cleared

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
            self.pdf_loaded.emit()  # Emit signal when PDF is loaded
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

class LinkScreen(QWidget):
    """Link screen showing PDF viewer with red rectangles and hidden buttons"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_app = parent
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        
        # Top toolbar with same elements as main app
        toolbar = QHBoxLayout()
        
        self.home_btn = QPushButton("🏠 Home")
        self.home_btn.clicked.connect(self.go_to_home)
        toolbar.addWidget(self.home_btn)
        
        self.save_btn = QPushButton("💾 Save")
        self.save_btn.clicked.connect(self.manual_save_pair)
        toolbar.addWidget(self.save_btn)
        
        # Auto Teleport toggle
        self.teleport_mode_btn = QPushButton("🔓 Auto Teleport")
        self.teleport_mode_btn.setCheckable(True)
        self.teleport_mode_btn.setToolTip("Toggle Auto Teleport - Middle mouse click to switch between PDFs")
        self.teleport_mode_btn.clicked.connect(self.toggle_auto_teleport_mode)
        self.teleport_mode_btn.setStyleSheet("QPushButton:checked { background-color: #ff6b35; color: white; }")
        toolbar.addWidget(self.teleport_mode_btn)
        
        # Auto-save status indicator
        self.autosave_label = QLabel("Auto-save: Ready")
        self.autosave_label.setStyleSheet("color: #666; font-size: 11px; padding: 2px 4px;")
        toolbar.addWidget(self.autosave_label)
        
        toolbar.addStretch()
        layout.addLayout(toolbar)
        
        # PDF viewers (duplicate of main viewer but with red rectangles)
        pdf_layout = QHBoxLayout()
        pdf_layout.setSpacing(0)

        # Left viewer = red rectangles (640px)
        self.viewer1 = PDFViewer("1", QColor(255, 0, 0, 150))  # Red color
        self.viewer1.setFixedWidth(640)
        self.viewer1.annotations_changed.connect(self.on_annotations_changed)
        self.viewer1.selection_changed.connect(self.on_selection_changed)
        
        # Right viewer = red rectangles (640px)  
        self.viewer2 = PDFViewer("2", QColor(255, 0, 0, 150))  # Red color
        self.viewer2.setFixedWidth(640)
        self.viewer2.annotations_changed.connect(self.on_annotations_changed)
        self.viewer2.selection_changed.connect(self.on_selection_changed)
        
        # Connect annotation signals to parent app for auto-save functionality
        if self.parent_app:
            self.viewer1.annotations_changed.connect(self.parent_app.on_annotations_changed)
            self.viewer2.annotations_changed.connect(self.parent_app.on_annotations_changed)
        
        # Third pane = side panel (320px)
        self.third_pane = QWidget()
        self.third_pane.setFixedWidth(320)
        self.third_pane.setStyleSheet("background-color: transparent; border: none;")
        
        # Create side panel layout
        side_layout = QVBoxLayout()
        side_layout.setContentsMargins(20, 20, 20, 20)
        side_layout.setSpacing(20)
        
        # Go back to Selection Editor button at the top
        self.back_to_selection_btn = QPushButton("← Go back to Selection Editor")
        self.back_to_selection_btn.setFixedHeight(50)
        self.back_to_selection_btn.setStyleSheet("QPushButton { background-color: #0078d4; color: white; border: none; border-radius: 8px; font-size: 16px; font-weight: bold; } QPushButton:hover { background-color: #106ebe; }")
        self.back_to_selection_btn.clicked.connect(self.go_back_to_selection)
        side_layout.addWidget(self.back_to_selection_btn)
        
        # Mark selection as Stem button
        self.mark_stem_btn = QPushButton("Mark selection as Stem")
        self.mark_stem_btn.setFixedHeight(50)
        self.mark_stem_btn.setStyleSheet("QPushButton { background-color: #6c757d; color: white; border: none; border-radius: 8px; font-size: 16px; font-weight: bold; } QPushButton:hover:enabled { background-color: #5a6268; } QPushButton:disabled { background-color: #6c757d; color: #999; }")
        self.mark_stem_btn.setEnabled(False)  # Initially disabled
        self.mark_stem_btn.clicked.connect(self.mark_selection_as_stem)
        side_layout.addWidget(self.mark_stem_btn)
        
        side_layout.addStretch()
        self.third_pane.setLayout(side_layout)

        pdf_layout.addWidget(self.viewer1)
        pdf_layout.addWidget(self.viewer2)
        pdf_layout.addWidget(self.third_pane)
        
        layout.addLayout(pdf_layout)
        self.setLayout(layout)
        
    def load_pdfs_from_parent(self):
        """Load PDFs and annotations from the parent app's viewers"""
        if not self.parent_app:
            return
            
        # Load PDFs if they exist in parent
        if hasattr(self.parent_app, 'viewer1') and self.parent_app.viewer1.pdf_path:
            self.viewer1.load_pdf_with_annotations(
                self.parent_app.viewer1.pdf_path,
                self.parent_app.viewer1.get_all_annotations_data()
            )
            # Hide specific buttons for link mode
            self.viewer1.hide_specific_buttons()
            
            # Restore scroll position to maintain current page
            if hasattr(self.parent_app.viewer1, 'scroll_area'):
                parent_scroll = self.parent_app.viewer1.scroll_area.verticalScrollBar().value()
                self.viewer1.scroll_area.verticalScrollBar().setValue(parent_scroll)
        else:
            # No PDF loaded in viewer1, show open button
            self.viewer1.show_toolbar()
            self.viewer1.hide_specific_buttons()
            
        if hasattr(self.parent_app, 'viewer2') and self.parent_app.viewer2.pdf_path:
            self.viewer2.load_pdf_with_annotations(
                self.parent_app.viewer2.pdf_path,
                self.parent_app.viewer2.get_all_annotations_data()
            )
            # Hide specific buttons for link mode
            self.viewer2.hide_specific_buttons()
            
            # Restore scroll position to maintain current page
            if hasattr(self.parent_app.viewer2, 'scroll_area'):
                parent_scroll = self.parent_app.viewer2.scroll_area.verticalScrollBar().value()
                self.viewer2.scroll_area.verticalScrollBar().setValue(parent_scroll)
        else:
            # No PDF loaded in viewer2, show open button
            self.viewer2.show_toolbar()
            self.viewer2.hide_specific_buttons()
        

        
        # Update the mark stem button state
        self.update_mark_stem_button_state()
        
        # Sync toolbar state with parent app
        if self.parent_app:
            # Sync auto-save label
            if hasattr(self.parent_app, 'autosave_label'):
                self.autosave_label.setText(self.parent_app.autosave_label.text())
                self.autosave_label.setStyleSheet(self.parent_app.autosave_label.styleSheet())
            
            # Sync auto teleport button state
            if hasattr(self.parent_app, 'teleport_mode_btn'):
                self.teleport_mode_btn.setChecked(self.parent_app.teleport_mode_btn.isChecked())
                if self.parent_app.teleport_mode_btn.isChecked():
                    self.teleport_mode_btn.setText("🔒 Auto Teleport")
                else:
                    self.teleport_mode_btn.setText("🔓 Auto Teleport")
    
    def on_annotations_changed(self):
        """Handle annotation changes in link mode"""
        # Update the mark stem button state when annotations change
        self.update_mark_stem_button_state()
        
        # Sync auto-save label with parent app
        if self.parent_app and hasattr(self.parent_app, 'autosave_label'):
            self.autosave_label.setText(self.parent_app.autosave_label.text())
            self.autosave_label.setStyleSheet(self.parent_app.autosave_label.styleSheet())
    
    def on_selection_changed(self):
        """Handle selection changes in link mode"""
        # Update the mark stem button state when selection changes
        self.update_mark_stem_button_state()
    
    def go_to_home(self):
        """Navigate to home screen"""
        if self.parent_app:
            # Show the specific buttons again before going home
            if hasattr(self.parent_app, 'viewer1'):
                self.parent_app.viewer1.show_specific_buttons()
            if hasattr(self.parent_app, 'viewer2'):
                self.parent_app.viewer2.show_specific_buttons()
            
            # Sync the parent app's toolbar state before going home
            if hasattr(self.parent_app, 'autosave_label'):
                self.parent_app.autosave_label.setText(self.autosave_label.text())
                self.parent_app.autosave_label.setStyleSheet(self.autosave_label.styleSheet())
            
            if hasattr(self.parent_app, 'teleport_mode_btn'):
                self.parent_app.teleport_mode_btn.setChecked(self.teleport_mode_btn.isChecked())
                if self.teleport_mode_btn.isChecked():
                    self.parent_app.teleport_mode_btn.setText("🔒 Auto Teleport")
                else:
                    self.parent_app.teleport_mode_btn.setText("🔓 Auto Teleport")
            
            self.parent_app.show_home_screen()
    
    def go_back_to_selection(self):
        """Go back to the main selection editor"""
        if self.parent_app:
            # Show the specific buttons again before going back
            if hasattr(self.parent_app, 'viewer1'):
                self.parent_app.viewer1.show_specific_buttons()
            if hasattr(self.parent_app, 'viewer2'):
                self.parent_app.viewer2.show_specific_buttons()
            
            # Sync the parent app's toolbar state before going back
            if hasattr(self.parent_app, 'autosave_label'):
                self.parent_app.autosave_label.setText(self.autosave_label.text())
                self.parent_app.autosave_label.setStyleSheet(self.autosave_label.styleSheet())
            
            if hasattr(self.parent_app, 'teleport_mode_btn'):
                self.parent_app.teleport_mode_btn.setChecked(self.teleport_mode_btn.isChecked())
                if self.teleport_mode_btn.isChecked():
                    self.parent_app.teleport_mode_btn.setText("🔒 Auto Teleport")
                else:
                    self.parent_app.teleport_mode_btn.setText("🔓 Auto Teleport")
            
            self.parent_app.show_pdf_viewer()
    
    def mark_selection_as_stem(self):
        """Mark the selected selection as stem (dummy function)"""
        # This is a dummy function that does nothing when clicked
        pass
    
    def update_mark_stem_button_state(self):
        """Update the state of the Mark selection as Stem button based on current selection"""
        if not self.parent_app:
            return
            
        # Check if there's a selection in the Question PDF (viewer1)
        question_selection = None
        if hasattr(self.parent_app, 'viewer1') and hasattr(self.parent_app.viewer1, 'page_widgets'):
            for page_widget in self.parent_app.viewer1.page_widgets:
                if hasattr(page_widget, 'selected_rect') and page_widget.selected_rect:
                    question_selection = page_widget.selected_rect
                    break
        
        # Check if there's a selection in the Answer PDF (viewer2)
        answer_selection = None
        if hasattr(self.parent_app, 'viewer2') and hasattr(self.parent_app.viewer2, 'page_widgets'):
            for page_widget in self.parent_app.viewer2.page_widgets:
                if hasattr(page_widget, 'selected_rect') and page_widget.selected_rect:
                    answer_selection = page_widget.selected_rect
                    break
        
        # Enable button only if there's a selection in Question PDF and no selection in Answer PDF
        if question_selection and not answer_selection:
            self.mark_stem_btn.setEnabled(True)
        else:
            self.mark_stem_btn.setEnabled(False)
    
    def manual_save_pair(self):
        """Manually save the current PDF pair with annotations"""
        if self.parent_app:
            self.parent_app.manual_save_pair()
    
    def toggle_auto_teleport_mode(self):
        """Toggle the auto teleport mode on/off"""
        if self.parent_app:
            self.parent_app.toggle_auto_teleport_mode()

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
        
        # Auto Teleport Mode variables
        self.auto_teleport_mode = False
        self.current_active_viewer = None  # Which viewer is currently active (1 or 2)
        
        # Navigation tracking variables
        self.current_annotation_index = {1: 0, 2: 0}  # Current annotation index for each viewer
        self.all_annotations = {1: [], 2: []}  # List of all annotations for each viewer
        
        self.init_ui()
        
        # Install event filter for middle mouse click
        QApplication.instance().installEventFilter(self)
        
        # Setup keyboard shortcuts for navigation
        self.setup_keyboard_shortcuts()
        
        # Check if we should show home screen or viewer
        if self.has_valid_pairs():
            self.show_home_screen()
        else:
            self.show_pdf_viewer()

    def eventFilter(self, obj, event):
        if self.auto_teleport_mode and event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.MiddleButton:
            self.switch_active_viewer()
            return True
        return super().eventFilter(obj, event)

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
        self.home_screen.new_pair_requested.connect(self.create_new_pair)

        # PDF viewer layout
        self.viewer_widget = QWidget()
        self.init_pdf_viewer()
        
        # Link screen
        self.link_screen = LinkScreen(self)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

    def create_new_pair(self):
        """Create a completely new, empty PDF pair"""
        # Reset current pair info
        self.current_pair_id = None
        self.current_pair_name = ""
        self.current_pair_description = ""
        self.has_unsaved_changes = False
        
        # Reset both viewers to empty state
        self.viewer1.reset_viewer()
        self.viewer2.reset_viewer()
        
        # Reset auto teleport mode
        self.disable_auto_teleport_mode()
        
        # Show the PDF viewer
        self.show_pdf_viewer()
        
        # Make sure specific buttons are visible
        self.viewer1.show_specific_buttons()
        self.viewer2.show_specific_buttons()
        
        # Reset auto-save label
        self.autosave_label.setText("Auto-save: Ready")
        self.autosave_label.setStyleSheet("color: #666; font-size: 11px; padding: 2px 4px;")
        
        # Reset annotation counter
        self.update_annotation_counter()
        
        # Reset navigation state
        self.current_annotation_index = {1: 0, 2: 0}
        self.all_annotations = {1: [], 2: []}
        self.update_navigation_labels()
        
        self.status_bar.showMessage("New PDF Pair - Open PDFs in both viewers to start")

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
        
        # Auto Teleport toggle
        self.teleport_mode_btn = QPushButton("🔓 Auto Teleport")
        self.teleport_mode_btn.setCheckable(True)
        self.teleport_mode_btn.setToolTip("Toggle Auto Teleport - Middle mouse click to switch between PDFs")
        self.teleport_mode_btn.clicked.connect(self.toggle_auto_teleport_mode)
        self.teleport_mode_btn.setStyleSheet("QPushButton:checked { background-color: #ff6b35; color: white; }")
        toolbar.addWidget(self.teleport_mode_btn)
        
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
        self.viewer1.annotation_created.connect(lambda: self.on_annotation_created(1))  # NEW
        self.viewer1.selection_changed.connect(self.on_selection_changed)  # NEW: Connect selection changed signal
        
        # Right viewer = orange (640px)  
        self.viewer2 = PDFViewer("2", QColor(255, 165, 0, 150))
        self.viewer2.setFixedWidth(640)
        self.viewer2.annotations_changed.connect(self.on_annotations_changed)
        self.viewer2.annotation_created.connect(lambda: self.on_annotation_created(2))  # NEW
        self.viewer2.selection_changed.connect(self.on_selection_changed)  # NEW: Connect selection changed signal
        
        # Connect annotation signals to update counter
        self.viewer1.annotations_changed.connect(self.update_annotation_counter)
        self.viewer2.annotations_changed.connect(self.update_annotation_counter)
        
        # Connect PDF loaded signals to update counter
        self.viewer1.pdf_loaded.connect(self.update_annotation_counter)
        self.viewer2.pdf_loaded.connect(self.update_annotation_counter)
        
        # Third pane = counter panel (320px)
        self.third_pane = QWidget()
        self.third_pane.setFixedWidth(320)
        self.third_pane.setStyleSheet("background-color: #1e1e1e; border-left: 1px solid #171717;")
        
        # Create counter layout
        counter_layout = QVBoxLayout()
        counter_layout.setContentsMargins(20, 20, 20, 20)
        counter_layout.setSpacing(20)
        
        # Title
        counter_title = QLabel("Annotation Count")
        counter_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        counter_title.setStyleSheet("color: #ffffff; font-size: 18px; font-weight: bold;")
        counter_layout.addWidget(counter_title)
        
        # Counter display
        counter_display_layout = QHBoxLayout()
        counter_display_layout.setSpacing(40)
        
        # Questions (Left PDF) counter
        questions_layout = QVBoxLayout()
        questions_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.questions_label = QLabel("Q")
        self.questions_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.questions_label.setStyleSheet("color: #ffffff; font-size: 24px; font-weight: bold;")
        questions_layout.addWidget(self.questions_label)
        
        self.questions_count = QLabel("0")
        self.questions_count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.questions_count.setStyleSheet("color: #4a9eff; font-size: 32px; font-weight: bold;")
        questions_layout.addWidget(self.questions_count)
        
        counter_display_layout.addLayout(questions_layout)
        
        # Separator
        separator = QLabel("|")
        separator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        separator.setStyleSheet("color: #666666; font-size: 24px; font-weight: bold;")
        counter_display_layout.addWidget(separator)
        
        # Answers (Right PDF) counter
        answers_layout = QVBoxLayout()
        answers_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.answers_label = QLabel("A")
        self.answers_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.answers_label.setStyleSheet("color: #ffffff; font-size: 24px; font-weight: bold;")
        answers_layout.addWidget(self.answers_label)
        
        self.answers_count = QLabel("0")
        self.answers_count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.answers_count.setStyleSheet("color: #ffa500; font-size: 32px; font-weight: bold;")
        answers_layout.addWidget(self.answers_count)
        
        counter_display_layout.addLayout(answers_layout)
        
        counter_layout.addLayout(counter_display_layout)
        
        # Navigation controls - positioned right underneath the counters
        navigation_layout = QVBoxLayout()
        navigation_layout.setSpacing(10)
        
        # Questions navigation
        questions_nav_layout = QHBoxLayout()
        questions_nav_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.questions_prev_btn = QPushButton("◀")
        self.questions_prev_btn.setFixedSize(30, 30)
        self.questions_prev_btn.setStyleSheet("QPushButton { background-color: #4a9eff; color: white; border: none; border-radius: 15px; font-size: 14px; } QPushButton:hover { background-color: #3a8eef; } QPushButton:disabled { background-color: #666; }")
        self.questions_prev_btn.clicked.connect(lambda: self.navigate_annotations(1, -1))
        self.questions_prev_btn.setToolTip("Previous Question (Ctrl+Shift+Left)")
        questions_nav_layout.addWidget(self.questions_prev_btn)
        
        self.questions_nav_label = QLabel("0/0")
        self.questions_nav_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.questions_nav_label.setStyleSheet("color: #ffffff; font-size: 14px; font-weight: bold; min-width: 40px;")
        questions_nav_layout.addWidget(self.questions_nav_label)
        
        self.questions_next_btn = QPushButton("▶")
        self.questions_next_btn.setFixedSize(30, 30)
        self.questions_next_btn.setStyleSheet("QPushButton { background-color: #4a9eff; color: white; border: none; border-radius: 15px; font-size: 14px; } QPushButton:hover { background-color: #3a8eef; } QPushButton:disabled { background-color: #666; }")
        self.questions_next_btn.clicked.connect(lambda: self.navigate_annotations(1, 1))
        self.questions_next_btn.setToolTip("Next Question (Ctrl+Shift+Right)")
        questions_nav_layout.addWidget(self.questions_next_btn)
        
        navigation_layout.addLayout(questions_nav_layout)
        
        # Separator
        nav_separator = QLabel("|")
        nav_separator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nav_separator.setStyleSheet("color: #666666; font-size: 18px; font-weight: bold;")
        navigation_layout.addWidget(nav_separator)
        
        # Answers navigation
        answers_nav_layout = QHBoxLayout()
        answers_nav_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.answers_prev_btn = QPushButton("◀")
        self.answers_prev_btn.setFixedSize(30, 30)
        self.answers_prev_btn.setStyleSheet("QPushButton { background-color: #ffa500; color: white; border: none; border-radius: 15px; font-size: 14px; } QPushButton:hover { background-color: #ff9500; } QPushButton:disabled { background-color: #666; }")
        self.answers_prev_btn.clicked.connect(lambda: self.navigate_annotations(2, -1))
        self.answers_prev_btn.setToolTip("Previous Answer (Ctrl+Alt+Left)")
        answers_nav_layout.addWidget(self.answers_prev_btn)
        
        self.answers_nav_label = QLabel("0/0")
        self.answers_nav_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.answers_nav_label.setStyleSheet("color: #ffffff; font-size: 14px; font-weight: bold; min-width: 40px;")
        answers_nav_layout.addWidget(self.answers_nav_label)
        
        self.answers_next_btn = QPushButton("▶")
        self.answers_next_btn.setFixedSize(30, 30)
        self.answers_next_btn.setStyleSheet("QPushButton { background-color: #ffa500; color: white; border: none; border-radius: 15px; font-size: 14px; } QPushButton:hover { background-color: #ff9500; } QPushButton:disabled { background-color: #666; }")
        self.answers_next_btn.clicked.connect(lambda: self.navigate_annotations(2, 1))
        self.answers_next_btn.setToolTip("Next Answer (Ctrl+Alt+Right)")
        answers_nav_layout.addWidget(self.answers_next_btn)
        
        navigation_layout.addLayout(answers_nav_layout)
        
        counter_layout.addLayout(navigation_layout)
        
        # Add some spacing
        counter_layout.addStretch()
        
        # Link button - positioned where navigation was before
        self.link_btn = QPushButton("Link🔗")
        self.link_btn.setFixedHeight(50)
        self.link_btn.setStyleSheet("QPushButton { background-color: #28a745; color: white; border: none; border-radius: 8px; font-size: 16px; font-weight: bold; } QPushButton:hover { background-color: #218838; }")
        self.link_btn.setToolTip("Click to enter Link Mode")
        self.link_btn.clicked.connect(self.show_link_screen)
        counter_layout.addWidget(self.link_btn)
        

        
        self.third_pane.setLayout(counter_layout)

        pdf_layout.addWidget(self.viewer1)
        pdf_layout.addWidget(self.viewer2)
        pdf_layout.addWidget(self.third_pane)
        
        layout.addLayout(pdf_layout)
        self.viewer_widget.setLayout(layout)

    def setup_keyboard_shortcuts(self):
        """Setup keyboard shortcuts for navigation"""
        from PyQt6.QtGui import QShortcut, QKeySequence
        
        # Left PDF navigation (Questions)
        self.questions_prev_shortcut = QShortcut(QKeySequence("Ctrl+Shift+Left"), self)
        self.questions_prev_shortcut.activated.connect(lambda: self.navigate_annotations(1, -1))
        
        self.questions_next_shortcut = QShortcut(QKeySequence("Ctrl+Shift+Right"), self)
        self.questions_next_shortcut.activated.connect(lambda: self.navigate_annotations(1, 1))
        
        # Right PDF navigation (Answers)
        self.answers_prev_shortcut = QShortcut(QKeySequence("Ctrl+Alt+Left"), self)
        self.answers_prev_shortcut.activated.connect(lambda: self.navigate_annotations(2, -1))
        
        self.answers_next_shortcut = QShortcut(QKeySequence("Ctrl+Alt+Right"), self)
        self.answers_next_shortcut.activated.connect(lambda: self.navigate_annotations(2, 1))

    def toggle_auto_teleport_mode(self):
        """Toggle the auto teleport mode on/off"""
        if self.teleport_mode_btn.isChecked():
            self.enable_auto_teleport_mode()
        else:
            self.disable_auto_teleport_mode()

    def enable_auto_teleport_mode(self):
        """Enable auto teleport mode"""
        # Check if both PDFs are loaded
        if not self.viewer1.pdf_path or not self.viewer2.pdf_path:
            QMessageBox.warning(self, 'Auto Teleport Error', 'Please load PDFs in both viewers before enabling Auto Teleport.')
            self.teleport_mode_btn.setChecked(False)
            return
            
        self.auto_teleport_mode = True
        self.current_active_viewer = 1  # Start with viewer 1
        
        # Enable annotation mode on both viewers
        self.viewer1.rect_btn.setChecked(True)
        self.viewer1.toggle_annotation()
        self.viewer2.rect_btn.setChecked(True)
        self.viewer2.toggle_annotation()
        
        # Update button appearance
        self.teleport_mode_btn.setText("🔒 Auto Teleport")
        
        # Apply restrictions
        self.apply_teleport_restrictions()
        
        # Update status bar
        self.update_teleport_status()

    def disable_auto_teleport_mode(self):
        """Disable auto teleport mode"""
        self.auto_teleport_mode = False
        self.current_active_viewer = None
        
        # Restore normal cursor for both viewers
        self.viewer1.setCursor(Qt.CursorShape.ArrowCursor)
        self.viewer2.setCursor(Qt.CursorShape.ArrowCursor)
        self.viewer1.unsetCursor()
        self.viewer2.unsetCursor()
        
        # Update button appearance
        self.teleport_mode_btn.setChecked(False)
        self.teleport_mode_btn.setText("🔓 Auto Teleport")
        
        # Clear status bar message
        self.status_bar.showMessage("Auto Teleport disabled")

    def apply_teleport_restrictions(self):
        """Apply cursor restrictions for auto teleport mode"""
        if not self.auto_teleport_mode or self.current_active_viewer is None:
            return
            
        if self.current_active_viewer == 1:
            self.viewer1.setCursor(Qt.CursorShape.CrossCursor)
            self.viewer2.setCursor(Qt.CursorShape.ForbiddenCursor)
        else:
            self.viewer1.setCursor(Qt.CursorShape.ForbiddenCursor)
            self.viewer2.setCursor(Qt.CursorShape.CrossCursor)

    def update_teleport_status(self):
        """Update status bar with current auto teleport state"""
        if not self.auto_teleport_mode:
            return
            
        viewer_name = "PDF A (Left)" if self.current_active_viewer == 1 else "PDF B (Right)"
        message = f"🔒 AUTO TELEPORT: Active in {viewer_name} | Middle click to switch"
        self.status_bar.showMessage(message)

    def update_annotation_counter(self):
        """Update the annotation counter display"""
        # Count annotations in left PDF (Questions)
        left_count = 0
        if hasattr(self.viewer1, 'page_widgets'):
            for page_widget in self.viewer1.page_widgets:
                left_count += len(page_widget.annotations)
        
        # Count annotations in right PDF (Answers)
        right_count = 0
        if hasattr(self.viewer2, 'page_widgets'):
            for page_widget in self.viewer2.page_widgets:
                right_count += len(page_widget.annotations)
        
        # Update the counter labels
        self.questions_count.setText(str(left_count))
        self.answers_count.setText(str(right_count))
        
        # Update navigation labels and rebuild annotation lists
        self.update_navigation_labels()
        self.rebuild_annotation_lists()

    def navigate_annotations(self, viewer_id, direction):
        """Navigate to next/previous annotation in the specified viewer"""
        if not self.all_annotations[viewer_id]:
            return
            
        # Update current index
        current_idx = self.current_annotation_index[viewer_id]
        total_annotations = len(self.all_annotations[viewer_id])
        
        if direction == 1:  # Next
            new_idx = (current_idx + 1) % total_annotations
        else:  # Previous
            new_idx = (current_idx - 1) % total_annotations
            
        self.current_annotation_index[viewer_id] = new_idx
        
        # Navigate to the annotation
        self.go_to_annotation(viewer_id, new_idx)
        
        # Update navigation labels
        self.update_navigation_labels()

    def go_to_annotation(self, viewer_id, annotation_index):
        """Go to a specific annotation and highlight it"""
        if not self.all_annotations[viewer_id] or annotation_index >= len(self.all_annotations[viewer_id]):
            return
            
        viewer = self.viewer1 if viewer_id == 1 else self.viewer2
        annotation_info = self.all_annotations[viewer_id][annotation_index]
        
        # Clear previous highlights
        self.clear_all_highlights(viewer_id)
        
        # Go to the page with this annotation
        target_page = annotation_info['page_index']
        if target_page < len(viewer.page_widgets):
            # Get the target page widget
            page_widget = viewer.page_widgets[target_page]
            
            # Calculate the position to center the page in the viewport
            scroll_area = viewer.scroll_area
            viewport_height = scroll_area.viewport().height()
            
            # Get the page's position relative to the scroll content
            page_pos = page_widget.mapTo(viewer.scroll_content, QPointF(0, 0))
            page_height = page_widget.height()
            
            # Calculate scroll position to center the page
            target_scroll_y = page_pos.y() - (viewport_height - page_height) / 2
            
            # Ensure scroll position is within bounds
            max_scroll = viewer.scroll_content.height() - viewport_height
            target_scroll_y = max(0, min(target_scroll_y, max_scroll))
            
            # Scroll to the calculated position
            scroll_area.verticalScrollBar().setValue(int(target_scroll_y))
            
            # Highlight the annotation
            annotation_item = annotation_info['annotation']
            if annotation_item:
                # Select and highlight the annotation
                page_widget.selected_rect = annotation_item
                annotation_item.select()
                
                # Update the page widget
                page_widget.viewport().update()

    def clear_all_highlights(self, viewer_id):
        """Clear all highlights in the specified viewer"""
        viewer = self.viewer1 if viewer_id == 1 else self.viewer2
        if hasattr(viewer, 'page_widgets'):
            for page_widget in viewer.page_widgets:
                if hasattr(page_widget, 'selected_rect') and page_widget.selected_rect:
                    page_widget.selected_rect.deselect()
                    page_widget.selected_rect = None
                for annotation in page_widget.annotations:
                    annotation.deselect()
                page_widget.viewport().update()

    def rebuild_annotation_lists(self):
        """Rebuild the list of all annotations for navigation"""
        # Clear existing lists
        self.all_annotations[1].clear()
        self.all_annotations[2].clear()
        
        # Rebuild for viewer 1 (Questions)
        if hasattr(self.viewer1, 'page_widgets'):
            for page_index, page_widget in enumerate(self.viewer1.page_widgets):
                for annotation in page_widget.annotations:
                    # Get the Y position of the annotation for sorting within the page
                    rect = annotation.rect()
                    pos = annotation.pos()
                    y_pos = rect.y() + pos.y()
                    
                    self.all_annotations[1].append({
                        'page_index': page_index,
                        'annotation': annotation,
                        'y_position': y_pos
                    })
        
        # Rebuild for viewer 2 (Answers)
        if hasattr(self.viewer2, 'page_widgets'):
            for page_index, page_widget in enumerate(self.viewer2.page_widgets):
                for annotation in page_widget.annotations:
                    # Get the Y position of the annotation for sorting within the page
                    rect = annotation.rect()
                    pos = annotation.pos()
                    y_pos = rect.y() + pos.y()
                    
                    self.all_annotations[2].append({
                        'page_index': page_index,
                        'annotation': annotation,
                        'y_position': y_pos
                    })
        
        # Sort annotations by page number first, then by Y position (top to bottom)
        for viewer_id in [1, 2]:
            self.all_annotations[viewer_id].sort(key=lambda x: (x['page_index'], x['y_position']))
        
        # Reset current indices if they're out of bounds
        for viewer_id in [1, 2]:
            if self.current_annotation_index[viewer_id] >= len(self.all_annotations[viewer_id]):
                self.current_annotation_index[viewer_id] = 0

    def update_navigation_labels(self):
        """Update the navigation labels with current counts"""
        # Update Questions navigation
        left_count = len(self.all_annotations[1])
        current_left = self.current_annotation_index[1] + 1 if left_count > 0 else 0
        self.questions_nav_label.setText(f"{current_left}/{left_count}")
        
        # Update Answers navigation
        right_count = len(self.all_annotations[2])
        current_right = self.current_annotation_index[2] + 1 if right_count > 0 else 0
        self.answers_nav_label.setText(f"{current_right}/{right_count}")
        
        # Update button states
        self.questions_prev_btn.setEnabled(left_count > 0)
        self.questions_next_btn.setEnabled(left_count > 0)
        self.answers_prev_btn.setEnabled(right_count > 0)
        self.answers_next_btn.setEnabled(right_count > 0)

    def on_annotation_created(self, viewer_id):
        pass  # Removed
    
    def on_selection_changed(self):
        """Called when selection changes - updates link screen button state"""
        # Update link screen button state if it exists
        if hasattr(self, 'link_screen') and hasattr(self.link_screen, 'update_mark_stem_button_state'):
            self.link_screen.update_mark_stem_button_state()

    def switch_active_viewer(self):
        """Switch to the other PDF viewer"""
        if not self.auto_teleport_mode:
            return
        
        # Get mouse position relative to old viewer
        old_viewer = self.viewer1 if self.current_active_viewer == 1 else self.viewer2
        mouse_global = QCursor.pos()
        mouse_local = old_viewer.mapFromGlobal(mouse_global)
            
        # Switch viewer
        self.current_active_viewer = 2 if self.current_active_viewer == 1 else 1
        
        # Apply new restrictions
        self.apply_teleport_restrictions()
        
        # Update status
        self.update_teleport_status()
        
        # Teleport mouse to same relative position in new viewer
        new_viewer = self.viewer1 if self.current_active_viewer == 1 else self.viewer2
        new_global = new_viewer.mapToGlobal(mouse_local)
        QCursor.setPos(new_global)

    def on_annotations_changed(self):
        """Called when annotations are modified - triggers auto-save"""
        if not self.is_closing and self.current_pair_id:
            self.has_unsaved_changes = True
            
            # Don't interfere with auto teleport status messages
            if not self.auto_teleport_mode:
                self.autosave_label.setText("Auto-save: Pending...")
                self.autosave_label.setStyleSheet("color: #ff9800; font-size: 11px; padding: 2px 4px;")
            
            # Restart the timer - this debounces rapid changes
            self.autosave_timer.stop()
            self.autosave_timer.start(1000)  # Wait 1 second after last change
        
        # Rebuild annotation lists for navigation
        self.rebuild_annotation_lists()
        self.update_navigation_labels()
        


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
            # Only update autosave label if not in auto teleport mode
            if not self.auto_teleport_mode:
                self.autosave_label.setText("Auto-save: ✓ Saved")
                self.autosave_label.setStyleSheet("color: #4caf50; font-size: 11px; padding: 2px 4px;")
                
                # Reset to "Ready" after 3 seconds
                QTimer.singleShot(3000, self.reset_autosave_label)
            
        except Exception as e:
            print(f"Auto-save error: {e}")
            if not self.auto_teleport_mode:
                self.autosave_label.setText("Auto-save: Error")
                self.autosave_label.setStyleSheet("color: #f44336; font-size: 11px; padding: 2px 4px;")

    def reset_autosave_label(self):
        """Reset auto-save label to ready state"""
        if not self.has_unsaved_changes and not self.auto_teleport_mode:
            self.autosave_label.setText("Auto-save: Ready")
            self.autosave_label.setStyleSheet("color: #666; font-size: 11px; padding: 2px 4px;")

    def go_to_home(self):
        """Navigate to home screen with auto-save"""
        if self.has_unsaved_changes and self.current_pair_id:
            self.perform_autosave()
        
        # Disable auto teleport mode when going home
        self.disable_auto_teleport_mode()
        
        # Make sure specific buttons are visible when going home
        if hasattr(self, 'viewer1'):
            self.viewer1.show_specific_buttons()
        if hasattr(self, 'viewer2'):
            self.viewer2.show_specific_buttons()
        
        self.show_home_screen()

    def show_home_screen(self):
        """Show the home screen"""
        # Auto-save before leaving if needed
        if self.has_unsaved_changes and self.current_pair_id:
            self.perform_autosave()
        
        # Disable auto teleport mode
        self.disable_auto_teleport_mode()
        
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

    def show_link_screen(self):
        """Show the link screen"""
        # Clear the main layout
        while self.main_layout.count():
            item = self.main_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        
        # Add link screen
        self.main_layout.addWidget(self.link_screen)
        
        # Load PDFs and annotations from parent viewers
        self.link_screen.load_pdfs_from_parent()
        
        # Disable auto teleport mode when entering link mode
        self.disable_auto_teleport_mode()
        
        self.status_bar.showMessage("Link Mode - All rectangles are unlinked (red)")

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
            
            # Disable auto teleport mode before loading
            self.disable_auto_teleport_mode()
            
            # Switch to PDF viewer
            self.show_pdf_viewer()
            
            # Load PDFs and annotations
            pdf1_annotations = pair_data.get('pdf1_annotations', {})
            pdf2_annotations = pair_data.get('pdf2_annotations', {})
            
            self.viewer1.load_pdf_with_annotations(pdf1_path, pdf1_annotations)
            self.viewer2.load_pdf_with_annotations(pdf2_path, pdf2_annotations)
            
            # Make sure specific buttons are visible
            self.viewer1.show_specific_buttons()
            self.viewer2.show_specific_buttons()
            
            # Store current pair info
            self.current_pair_id = pair_data.get('pair_id')
            self.current_pair_name = pair_data.get('name', '')
            self.current_pair_description = pair_data.get('description', '')
            self.has_unsaved_changes = False
            
            # Update annotation counter after loading
            self.update_annotation_counter()
            
            # Also update navigation
            self.rebuild_annotation_lists()
            self.update_navigation_labels()
            
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
        
        # Disable auto teleport mode
        self.disable_auto_teleport_mode()
        
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
