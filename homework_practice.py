#!/usr/bin/env python3
"""
Homework Practice Mode - Simplified Practice Interface
Reads pdf_pairs.json and links.json to create randomized practice sets
with perfectly cut out images from PDFs.

Requirements: pip install PyQt6 PyMuPDF Pillow
"""

import sys
import json
import os
import random
from pathlib import Path
import fitz  # PyMuPDF
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTextEdit, QScrollArea, QMessageBox, 
    QListWidget, QListWidgetItem, QDialog, QDialogButtonBox,
    QFormLayout, QLineEdit, QFrame, QSplitter, QGroupBox,
    QGridLayout, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer, QSize
from PyQt6.QtGui import QPixmap, QImage, QFont, QPalette, QColor, QPainter

class HelpNoteDialog(QDialog):
    """Dialog for adding help notes to questions"""
    def __init__(self, question_id, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Add Help Note - {question_id}")
        self.setModal(True)
        self.resize(500, 300)
        
        layout = QVBoxLayout()
        
        # Question ID label
        question_label = QLabel(f"Question ID: {question_id}")
        question_label.setStyleSheet("font-weight: bold; color: #0078d4;")
        layout.addWidget(question_label)
        
        # Note input
        note_label = QLabel("Help Note:")
        layout.addWidget(note_label)
        
        self.note_edit = QTextEdit()
        self.note_edit.setPlaceholderText("Enter your help note here...")
        layout.addWidget(self.note_edit)
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
        self.setLayout(layout)
    
    def get_note(self):
        return self.note_edit.toPlainText().strip()

class PerfectImageViewer(QWidget):
    """Advanced PDF viewer for displaying perfectly cut out question/answer images"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.pdf_document = None
        self.current_page = None
        self.stem_pixmap = None
        self.question_pixmap = None
        
        layout = QVBoxLayout()
        
        # Main image display with better styling
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(500, 600)
        self.image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.image_label.setStyleSheet("""
            QLabel {
                border: 3px solid #e0e0e0;
                border-radius: 8px;
                background-color: #fafafa;
                padding: 10px;
            }
        """)
        
        # Scroll area for large images
        scroll_area = QScrollArea()
        scroll_area.setWidget(self.image_label)
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: #f5f5f5;
            }
        """)
        layout.addWidget(scroll_area)
        
        # Status label
        self.status_label = QLabel("No image loaded")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("color: #666; font-size: 12px; margin: 5px;")
        layout.addWidget(self.status_label)
        
        self.setLayout(layout)
    
    def load_pdf(self, pdf_path):
        """Load a PDF file"""
        try:
            if self.pdf_document:
                self.pdf_document.close()
            self.pdf_document = fitz.open(pdf_path)
            return True
        except Exception as e:
            print(f"Error loading PDF: {e}")
            self.status_label.setText(f"Error loading PDF: {e}")
            return False
    
    def extract_perfect_region(self, page_num, x1, y1, x2, y2):
        """Extract a perfectly cut out region from a page and return as QPixmap"""
        if not self.pdf_document or page_num >= len(self.pdf_document):
            self.status_label.setText("Invalid page number")
            return None
        
        try:
            page = self.pdf_document[page_num]
            
            # Create rectangle for extraction
            rect = fitz.Rect(x1, y1, x2, y2)
            
            # Extract the region with high resolution
            mat = fitz.Matrix(3.0, 3.0)  # High resolution for crisp images
            pix = page.get_pixmap(matrix=mat, clip=rect, alpha=False)
            
            # Convert to QPixmap
            img_data = pix.tobytes("ppm")
            qimg = QImage.fromData(img_data)
            pixmap = QPixmap.fromImage(qimg)
            
            return pixmap
            
        except Exception as e:
            print(f"Error extracting region: {e}")
            self.status_label.setText(f"Error extracting image: {e}")
            return None
    
    def display_combined_images(self, stem_pixmap=None, question_pixmap=None):
        """Display stem and question images side by side or stacked"""
        try:
            if not stem_pixmap and not question_pixmap:
                self.image_label.clear()
                self.status_label.setText("No images to display")
                return
            
            # Get available space
            available_width = self.image_label.width() - 20  # Account for padding
            available_height = self.image_label.height() - 20
            
            if stem_pixmap and question_pixmap:
                # Both images available - display side by side
                stem_scaled = stem_pixmap.scaled(
                    available_width // 2 - 10, available_height,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                
                question_scaled = question_pixmap.scaled(
                    available_width // 2 - 10, available_height,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                
                # Create combined image
                combined_width = stem_scaled.width() + question_scaled.width() + 20
                combined_height = max(stem_scaled.height(), question_scaled.height())
                
                combined_pixmap = QPixmap(combined_width, combined_height)
                combined_pixmap.fill(Qt.GlobalColor.white)
                
                # Draw stem on left
                painter = QPainter(combined_pixmap)
                painter.drawPixmap(0, 0, stem_scaled)
                painter.drawPixmap(stem_scaled.width() + 20, 0, question_scaled)
                painter.end()
                
                self.image_label.setPixmap(combined_pixmap)
                self.status_label.setText(f"Stem + Question: {stem_scaled.width()}×{stem_scaled.height()} + {question_scaled.width()}×{question_scaled.height()}")
                
            elif stem_pixmap:
                # Only stem available
                scaled_pixmap = stem_pixmap.scaled(
                    available_width, available_height,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self.image_label.setPixmap(scaled_pixmap)
                self.status_label.setText(f"Stem only: {scaled_pixmap.width()}×{scaled_pixmap.height()}")
                
            elif question_pixmap:
                # Only question available
                scaled_pixmap = question_pixmap.scaled(
                    available_width, available_height,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self.image_label.setPixmap(scaled_pixmap)
                self.status_label.setText(f"Question only: {scaled_pixmap.width()}×{scaled_pixmap.height()}")
                
        except Exception as e:
            print(f"Error displaying combined images: {e}")
            self.status_label.setText(f"Error displaying images: {e}")
    
    def display_single_image(self, pixmap):
        """Display a single image"""
        if not pixmap:
            self.image_label.clear()
            self.status_label.setText("No image to display")
            return
        
        try:
            # Scale to fit the label while maintaining aspect ratio
            available_width = self.image_label.width() - 20
            available_height = self.image_label.height() - 20
            
            scaled_pixmap = pixmap.scaled(
                available_width, available_height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            
            self.image_label.setPixmap(scaled_pixmap)
            self.status_label.setText(f"Image loaded: {scaled_pixmap.width()}×{scaled_pixmap.height()}")
            
        except Exception as e:
            print(f"Error displaying image: {e}")
            self.status_label.setText(f"Error displaying image: {e}")
    
    def clear_image(self):
        """Clear the current image"""
        self.image_label.clear()
        self.status_label.setText("No image loaded")

class HomeworkPractice(QMainWindow):
    """Main Homework Practice application"""
    
    def __init__(self):
        super().__init__()
        self.pdf_pairs_data = {}
        self.links_data = {}
        self.help_data = {}
        self.current_questions = []
        self.current_question_index = 0
        self.current_question = None
        self.showing_answer = False
        self.showing_stem = False
        self.current_stem_id = None
        self.random_order = True  # Default to random order
        self.filter_completed = False  # Default to showing all questions
        self.current_session_id = None
        self.sessions_data = {}
        self.original_session_order = []  # Store original order for toggling

        # File paths
        self.pdf_pairs_file = "pdf_pairs.json"
        self.links_file = "links.json"
        self.help_file = "help.json"
        self.completed_file = "completed.json"
        self.sessions_file = "ids.json"

        self.init_ui()
        self.load_data()
        self.setup_practice_session()
    
    def init_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle("Homework Practice Mode")
        self.setGeometry(100, 100, 1600, 1000)
        
        # Main widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QHBoxLayout()
        
        # Left panel - Controls and navigation
        left_panel = QWidget()
        left_panel.setFixedWidth(450)
        left_panel.setStyleSheet("""
            QWidget {
                background-color: #f8f9fa;
                border-right: 2px solid #e9ecef;
            }
        """)
        left_layout = QVBoxLayout()
        
        # Title
        title = QLabel("Homework Practice")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("""
            font-size: 24px; 
            font-weight: bold; 
            color: #0078d4; 
            margin: 20px 10px;
            padding: 10px;
            background-color: white;
            border-radius: 8px;
        """)
        left_layout.addWidget(title)
        
        # Question counter
        self.question_counter = QLabel("Question 0/0")
        self.question_counter.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.question_counter.setStyleSheet("""
            font-size: 16px; 
            color: #495057; 
            margin: 10px;
            padding: 8px;
            background-color: white;
            border-radius: 6px;
            border: 1px solid #dee2e6;
        """)
        left_layout.addWidget(self.question_counter)
        
        # Navigation buttons
        nav_layout = QHBoxLayout()
        
        self.prev_btn = QPushButton("◀ Previous")
        self.prev_btn.clicked.connect(self.previous_question)
        self.prev_btn.setEnabled(False)
        self.prev_btn.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                border: none;
                padding: 10px 15px;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
            QPushButton:disabled {
                background-color: #adb5bd;
            }
        """)
        nav_layout.addWidget(self.prev_btn)
        
        self.next_btn = QPushButton("Next ▶")
        self.next_btn.clicked.connect(self.next_question)
        self.next_btn.setStyleSheet("""
            QPushButton {
                background-color: #0078d4;
                color: white;
                border: none;
                padding: 10px 15px;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #106ebe;
            }
            QPushButton:disabled {
                background-color: #adb5bd;
            }
        """)
        nav_layout.addWidget(self.next_btn)
        
        left_layout.addLayout(nav_layout)
        
        # Question info group
        question_group = QGroupBox("Question Information")
        question_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #dee2e6;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
                background-color: white;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)
        question_layout = QVBoxLayout()
        
        self.question_id_label = QLabel("ID: None")
        self.question_id_label.setStyleSheet("font-weight: bold; color: #333; padding: 5px;")
        question_layout.addWidget(self.question_id_label)
        
        self.stem_label = QLabel("Stem: None")
        self.stem_label.setWordWrap(True)
        self.stem_label.setStyleSheet("color: #666; font-style: italic; padding: 5px;")
        question_layout.addWidget(self.stem_label)
        
        question_group.setLayout(question_layout)
        left_layout.addWidget(question_group)
        
        # Action buttons
        actions_group = QGroupBox("Actions")
        actions_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #dee2e6;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
                background-color: white;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)
        actions_layout = QVBoxLayout()
        
        self.show_answer_btn = QPushButton("Show Answer")
        self.show_answer_btn.clicked.connect(self.toggle_answer)
        self.show_answer_btn.setEnabled(False)
        self.show_answer_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                border: none;
                padding: 12px;
                border-radius: 6px;
                font-weight: bold;
                margin: 5px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
            QPushButton:disabled {
                background-color: #adb5bd;
            }
        """)
        actions_layout.addWidget(self.show_answer_btn)
        
        self.help_btn = QPushButton("Mark for Help")
        self.help_btn.clicked.connect(self.mark_for_help)
        self.help_btn.setEnabled(False)
        self.help_btn.setStyleSheet("""
            QPushButton {
                background-color: #ffc107;
                color: #212529;
                border: none;
                padding: 12px;
                border-radius: 6px;
                font-weight: bold;
                margin: 5px;
            }
            QPushButton:hover {
                background-color: #e0a800;
            }
            QPushButton:disabled {
                background-color: #adb5bd;
            }
        """)
        actions_layout.addWidget(self.help_btn)
        
        self.complete_btn = QPushButton("Mark Complete")
        self.complete_btn.clicked.connect(self.mark_complete)
        self.complete_btn.setEnabled(False)
        self.complete_btn.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                border: none;
                padding: 12px;
                border-radius: 6px;
                font-weight: bold;
                margin: 5px;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
            QPushButton:disabled {
                background-color: #adb5bd;
            }
        """)
        actions_layout.addWidget(self.complete_btn)
        
        self.show_stem_btn = QPushButton("Show Stem")
        self.show_stem_btn.clicked.connect(self.toggle_stem_question)
        self.show_stem_btn.setEnabled(False)
        self.show_stem_btn.setStyleSheet("""
            QPushButton {
                background-color: #20c997;
                color: white;
                border: none;
                padding: 12px;
                border-radius: 6px;
                font-weight: bold;
                margin: 5px;
            }
            QPushButton:hover {
                background-color: #1ea085;
            }
            QPushButton:disabled {
                background-color: #adb5bd;
            }
        """)
        actions_layout.addWidget(self.show_stem_btn)
        
        self.new_session_btn = QPushButton("New Practice Session")
        self.new_session_btn.clicked.connect(self.setup_practice_session)
        self.new_session_btn.setStyleSheet("""
            QPushButton {
                background-color: #17a2b8;
                color: white;
                border: none;
                padding: 12px;
                border-radius: 6px;
                font-weight: bold;
                margin: 5px;
            }
            QPushButton:hover {
                background-color: #138496;
            }
        """)
        actions_layout.addWidget(self.new_session_btn)
        
        self.order_toggle_btn = QPushButton("Random Order ✓")
        self.order_toggle_btn.clicked.connect(self.toggle_order)
        self.order_toggle_btn.setStyleSheet("""
            QPushButton {
                background-color: #6f42c1;
                color: white;
                border: none;
                padding: 12px;
                border-radius: 6px;
                font-weight: bold;
                margin: 5px;
            }
            QPushButton:hover {
                background-color: #5a32a3;
            }
        """)
        actions_layout.addWidget(self.order_toggle_btn)
        
        self.help_review_btn = QPushButton("Help Review")
        self.help_review_btn.clicked.connect(self.show_help_review)
        self.help_review_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                border: none;
                padding: 12px;
                border-radius: 6px;
                font-weight: bold;
                margin: 5px;
            }
            QPushButton:hover {
                background-color: #c82333;
            }
        """)
        actions_layout.addWidget(self.help_review_btn)
        
        self.filter_completed_btn = QPushButton("Show All Questions ✓")
        self.filter_completed_btn.clicked.connect(self.toggle_filter_completed)
        self.filter_completed_btn.setStyleSheet("""
            QPushButton {
                background-color: #343a40;
                color: white;
                border: none;
                padding: 12px;
                border-radius: 6px;
                font-weight: bold;
                margin: 5px;
            }
            QPushButton:hover {
                background-color: #23272b;
            }
        """)
        actions_layout.addWidget(self.filter_completed_btn)
                # Session ID input section
        session_layout = QVBoxLayout()
        session_label = QLabel("Session ID:")
        session_label.setStyleSheet("font-weight: bold; color: #333; padding: 5px;")
        session_layout.addWidget(session_label)
        
        self.session_id_input = QLineEdit()
        self.session_id_input.setPlaceholderText("Enter session ID to load...")
        self.session_id_input.setStyleSheet("""
            QLineEdit {
                padding: 8px;
                border: 2px solid #dee2e6;
                border-radius: 4px;
                background-color: white;
                color: #212529;
            }
            QLineEdit:focus {
                border-color: #0078d4;
            }
        """)
        session_layout.addWidget(self.session_id_input)
        
        self.load_session_btn = QPushButton("Load Session")
        self.load_session_btn.clicked.connect(self.load_session_by_id)
        self.load_session_btn.setStyleSheet("""
            QPushButton {
                background-color: #17a2b8;
                color: white;
                border: none;
                padding: 10px;
                border-radius: 6px;
                font-weight: bold;
                margin: 5px;
            }
            QPushButton:hover {
                background-color: #138496;
            }
        """)
        session_layout.addWidget(self.load_session_btn)
        
        self.current_session_label = QLabel("Current Session: None")
        self.current_session_label.setStyleSheet("""
            color: #0078d4; 
            font-weight: bold; 
            padding: 5px;
            background-color: white;
            border-radius: 4px;
            border: 1px solid #dee2e6;
        """)
        self.current_session_label.setWordWrap(True)
        session_layout.addWidget(self.current_session_label)
        
        actions_layout.addLayout(session_layout)

        actions_group.setLayout(actions_layout)
        left_layout.addWidget(actions_group)
        
        # Status
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #666; font-size: 12px; padding: 10px;")
        left_layout.addWidget(self.status_label)
        
        left_layout.addStretch()
        left_panel.setLayout(left_layout)
        
        # Right panel - Image viewer
        right_panel = QWidget()
        right_layout = QVBoxLayout()
        
        # Viewer title
        self.viewer_title = QLabel("Question")
        self.viewer_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.viewer_title.setStyleSheet("""
            font-size: 18px; 
            font-weight: bold; 
            margin: 10px;
            padding: 10px;
            background-color: #0078d4;
            color: white;
            border-radius: 6px;
        """)
        right_layout.addWidget(self.viewer_title)
        
        # Perfect image viewer
        self.image_viewer = PerfectImageViewer()
        right_layout.addWidget(self.image_viewer)
        
        right_panel.setLayout(right_layout)
        
        # Add panels to main layout
        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_panel)
        
        central_widget.setLayout(main_layout)
    
    def load_data(self):
        """Load data from JSON files"""
        try:
            # Load PDF pairs data
            if os.path.exists(self.pdf_pairs_file):
                with open(self.pdf_pairs_file, 'r') as f:
                    self.pdf_pairs_data = json.load(f)
                print(f"Loaded {len(self.pdf_pairs_data.get('pairs', {}))} PDF pairs")
            else:
                QMessageBox.warning(self, "File Not Found", f"Could not find {self.pdf_pairs_file}")
                return
            
            # Load links data
            if os.path.exists(self.links_file):
                with open(self.links_file, 'r') as f:
                    self.links_data = json.load(f)
                print(f"Loaded {len(self.links_data.get('questions', {}))} question links")
            else:
                QMessageBox.warning(self, "File Not Found", f"Could not find {self.links_file}")
                return
            
            # Load help data
            if os.path.exists(self.help_file):
                with open(self.help_file, 'r') as f:
                    self.help_data = json.load(f)
                print(f"Loaded {len(self.help_data.get('help', {}))} help entries")
            else:
                self.help_data = {"help": {}}
            if os.path.exists(self.completed_file):
                with open(self.completed_file, 'r') as f:
                    self.completed_data = json.load(f)
                print(f"Loaded {len(self.completed_data.get('completed', []))} completed questions")
            else:
                self.completed_data = {"completed": []}

            # Load sessions data
            if os.path.exists(self.sessions_file):
                with open(self.sessions_file, 'r') as f:
                    self.sessions_data = json.load(f)
                print(f"Loaded {len(self.sessions_data.get('sessions', {}))} saved sessions")
            else:
                self.sessions_data = {"sessions": {}}
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error loading data: {e}")
    
    def setup_practice_session(self):
        """Set up a new practice session with valid questions only"""
        try:
            # Get all question IDs from links.json and validate them
            valid_questions = []
            for question_id, question_data in self.links_data.get('questions', {}).items():
                # Only include questions that have answers (not stems)
                if question_data.get('answer') and not question_data.get('isStem'):
                    answer_id = question_data.get('answer')
                    # Check if both question and answer exist in PDF pairs data
                    if (self.question_exists_in_pdfs(question_id) and 
                        self.answer_exists_in_pdfs(answer_id)):
                        valid_questions.append(question_id)
            
            if not valid_questions:
                QMessageBox.information(self, "No Valid Questions", "No questions with answers and valid PDF data found.")
                return
                        # Filter out completed questions if filter is enabled
            if self.filter_completed:
                completed_list = self.completed_data.get('completed', [])
                valid_questions = [q for q in valid_questions if q not in completed_list]
                
                if not valid_questions:
                    QMessageBox.information(self, "All Complete", "All questions are marked as complete!")
                    return
            
            # Set questions based on order preference
            self.current_questions = valid_questions.copy()
            if self.random_order:
                random.shuffle(self.current_questions)
                self.original_session_order = self.current_questions.copy()  # Save original random order
                
                # Generate unique session ID and save order
                import time
                session_id = f"session_{int(time.time())}_{random.randint(1000, 9999)}"
                self.current_session_id = session_id
                
                # Save session to ids.json
                if 'sessions' not in self.sessions_data:
                    self.sessions_data['sessions'] = {}
                
                self.sessions_data['sessions'][session_id] = {
                    'question_order': self.current_questions.copy(),
                    'created': time.strftime('%Y-%m-%d %H:%M:%S'),
                    'total_questions': len(self.current_questions),
                    'filter_completed': self.filter_completed
                }
                
                self.save_sessions_data()
                self.current_session_label.setText(f"Current Session: {session_id}")
            else:
                self.current_session_id = None
                self.current_session_label.setText("Current Session: None (Structured)")

            # Reset session
            self.current_question_index = 0
            self.current_question = None
            self.showing_answer = False
            
            # Update UI
            self.update_question_counter()
            self.load_current_question()
            
            order_type = "randomized" if self.random_order else "structured"
            self.status_label.setText(f"New {order_type} session started with {len(valid_questions)} valid questions")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error setting up practice session: {e}")
    
    def question_exists_in_pdfs(self, question_id):
        """Check if a question exists in the PDF pairs data"""
        for pair_id, pair_data in self.pdf_pairs_data.get('pairs', {}).items():
            pdf1_annotations = pair_data.get('pdf1_annotations', {})
            pdf2_annotations = pair_data.get('pdf2_annotations', {})
            
            # Search in both PDFs
            for page_annotations in pdf1_annotations.values():
                for ann in page_annotations:
                    if ann.get('selection_id') == question_id:
                        return True
            
            for page_annotations in pdf2_annotations.values():
                for ann in page_annotations:
                    if ann.get('selection_id') == question_id:
                        return True
        
        return False
    
    def answer_exists_in_pdfs(self, answer_id):
        """Check if an answer exists in the PDF pairs data"""
        for pair_id, pair_data in self.pdf_pairs_data.get('pairs', {}).items():
            pdf1_annotations = pair_data.get('pdf1_annotations', {})
            pdf2_annotations = pair_data.get('pdf2_annotations', {})
            
            # Search in both PDFs
            for page_annotations in pdf1_annotations.values():
                for ann in page_annotations:
                    if ann.get('selection_id') == answer_id:
                        return True
            
            for page_annotations in pdf2_annotations.values():
                for ann in page_annotations:
                    if ann.get('selection_id') == answer_id:
                        return True
        
        return False
    
    def load_current_question(self):
        """Load and display the current question with stem if available"""
        if not self.current_questions or self.current_question_index >= len(self.current_questions):
            return
        
        question_id = self.current_questions[self.current_question_index]
        self.current_question = question_id
        
        # Get question data
        question_data = self.links_data.get('questions', {}).get(question_id, {})
        
        # Update UI
        self.question_id_label.setText(f"ID: {question_id}")
        
        # Check if question has a stem
        stem_id = question_data.get('stem')
        self.current_stem_id = stem_id
        
        # Load both stem and question images
        stem_pixmap = None
        question_pixmap = None
        
        if stem_id:
            stem_data = self.links_data.get('questions', {}).get(stem_id, {})
            if stem_data.get('isStem'):
                self.stem_label.setText(f"Stem: {stem_id}")
                stem_pixmap = self.extract_question_image(stem_id)
                self.show_stem_btn.setEnabled(True)
                self.show_stem_btn.setText("Show Stem Only")
            else:
                self.stem_label.setText("Stem: Invalid stem reference")
                self.show_stem_btn.setEnabled(False)
        else:
            self.stem_label.setText("Stem: None")
            self.show_stem_btn.setEnabled(False)
        
        # Always load the question image
        question_pixmap = self.extract_question_image(question_id)
        
        # Display combined images
        self.image_viewer.display_combined_images(stem_pixmap, question_pixmap)
        self.viewer_title.setText(f"Question: {question_id}")
        
        # Update button states
        self.show_answer_btn.setEnabled(True)
        self.help_btn.setEnabled(True)
        self.complete_btn.setEnabled(True)  # <-- Add this line
        
        # Check if question is marked for help
        if question_id in self.help_data.get('help', {}):
            self.help_btn.setText("Help ✓")
            self.help_btn.setStyleSheet("""
                QPushButton {
                    background-color: #ff9800;
                    color: white;
                    border: none;
                    padding: 12px;
                    border-radius: 6px;
                    font-weight: bold;
                    margin: 5px;
                }
                QPushButton:hover {
                    background-color: #f57c00;
                }
            """)
        else:
            self.help_btn.setText("Mark for Help")
            self.help_btn.setStyleSheet("""
                QPushButton {
                    background-color: #ffc107;
                    color: #212529;
                    border: none;
                    padding: 12px;
                    border-radius: 6px;
                    font-weight: bold;
                    margin: 5px;
                }
                QPushButton:hover {
                    background-color: #e0a800;
                }
            """)

        # Check if question is marked as complete
        completed_list = self.completed_data.get('completed', [])
        if question_id in completed_list:
            self.complete_btn.setText("Complete ✓")
            self.complete_btn.setStyleSheet("""
                QPushButton {
                    background-color: #28a745;
                    color: white;
                    border: none;
                    padding: 12px;
                    border-radius: 6px;
                    font-weight: bold;
                    margin: 5px;
                }
                QPushButton:hover {
                    background-color: #218838;
                }
            """)
        else:
            self.complete_btn.setText("Mark Complete")
            self.complete_btn.setStyleSheet("""
                QPushButton {
                    background-color: #6c757d;
                    color: white;
                    border: none;
                    padding: 12px;
                    border-radius: 6px;
                    font-weight: bold;
                    margin: 5px;
                }
                QPushButton:hover {
                    background-color: #5a6268;
                }
            """)
       
    def extract_question_image(self, question_id):
        """Extract the perfectly cut out image for a question or stem and return as QPixmap"""
        try:
            # Find the question in PDF pairs data
            for pair_id, pair_data in self.pdf_pairs_data.get('pairs', {}).items():
                pdf1_annotations = pair_data.get('pdf1_annotations', {})
                pdf2_annotations = pair_data.get('pdf2_annotations', {})
                
                # Search in both PDFs
                for page_num, page_annotations in pdf1_annotations.items():
                    for ann in page_annotations:
                        if ann.get('selection_id') == question_id:
                            # Load PDF and extract region
                            pdf_path = pair_data.get('pdf1_path')
                            if pdf_path and os.path.exists(pdf_path):
                                self.image_viewer.load_pdf(pdf_path)
                                coords = ann.get('coordinates', {})
                                
                                if 'x1' in coords:
                                    # New format with absolute coordinates
                                    return self.image_viewer.extract_perfect_region(
                                        int(page_num), 
                                        coords['x1'], coords['y1'], 
                                        coords['x2'], coords['y2']
                                    )
                                else:
                                    # Legacy format - convert to absolute coordinates
                                    page_width = 612  # Standard PDF page width
                                    page_height = 792  # Standard PDF page height
                                    x1 = coords['x'] * page_width
                                    y1 = coords['y'] * page_height
                                    x2 = x1 + (coords['width'] * page_width)
                                    y2 = y1 + (coords['height'] * page_height)
                                    
                                    return self.image_viewer.extract_perfect_region(
                                        int(page_num), x1, y1, x2, y2
                                    )
                
                # Search in PDF2 (answers)
                for page_num, page_annotations in pdf2_annotations.items():
                    for ann in page_annotations:
                        if ann.get('selection_id') == question_id:
                            # Load PDF and extract region
                            pdf_path = pair_data.get('pdf2_path')
                            if pdf_path and os.path.exists(pdf_path):
                                self.image_viewer.load_pdf(pdf_path)
                                coords = ann.get('coordinates', {})
                                
                                if 'x1' in coords:
                                    # New format with absolute coordinates
                                    return self.image_viewer.extract_perfect_region(
                                        int(page_num), 
                                        coords['x1'], coords['y1'], 
                                        coords['x2'], coords['y2']
                                    )
                                else:
                                    # Legacy format - convert to absolute coordinates
                                    page_width = 612  # Standard PDF page width
                                    page_height = 792  # Standard PDF page height
                                    x1 = coords['x'] * page_width
                                    y1 = coords['y'] * page_height
                                    x2 = x1 + (coords['width'] * page_width)
                                    y2 = y1 + (coords['height'] * page_height)
                                    
                                    return self.image_viewer.extract_perfect_region(
                                        int(page_num), x1, y1, x2, y2
                                    )
            
            # If we get here, question wasn't found
            print(f"Question not found: {question_id}")
            return None
            
        except Exception as e:
            print(f"Error extracting question image: {e}")
            return None
    
    def extract_answer_image(self, question_id):
        """Extract the perfectly cut out answer image for a question and return as QPixmap"""
        try:
            question_data = self.links_data.get('questions', {}).get(question_id, {})
            answer_id = question_data.get('answer')
            
            if not answer_id:
                print(f"No answer linked to question: {question_id}")
                return None
            
            # Find the answer in PDF pairs data
            for pair_id, pair_data in self.pdf_pairs_data.get('pairs', {}).items():
                pdf1_annotations = pair_data.get('pdf1_annotations', {})
                pdf2_annotations = pair_data.get('pdf2_annotations', {})
                
                # Search in both PDFs
                for page_num, page_annotations in pdf1_annotations.items():
                    for ann in page_annotations:
                        if ann.get('selection_id') == answer_id:
                            # Load PDF and extract region
                            pdf_path = pair_data.get('pdf1_path')
                            if pdf_path and os.path.exists(pdf_path):
                                self.image_viewer.load_pdf(pdf_path)
                                coords = ann.get('coordinates', {})
                                
                                if 'x1' in coords:
                                    # New format with absolute coordinates
                                    return self.image_viewer.extract_perfect_region(
                                        int(page_num), 
                                        coords['x1'], coords['y1'], 
                                        coords['x2'], coords['y2']
                                    )
                                else:
                                    # Legacy format - convert to absolute coordinates
                                    page_width = 612  # Standard PDF page width
                                    page_height = 792  # Standard PDF page height
                                    x1 = coords['x'] * page_width
                                    y1 = coords['y'] * page_height
                                    x2 = x1 + (coords['width'] * page_width)
                                    y2 = y1 + (coords['height'] * page_height)
                                    
                                    return self.image_viewer.extract_perfect_region(
                                        int(page_num), x1, y1, x2, y2
                                    )
                
                # Search in PDF2 (answers)
                for page_num, page_annotations in pdf2_annotations.items():
                    for ann in page_annotations:
                        if ann.get('selection_id') == answer_id:
                            # Load PDF and extract region
                            pdf_path = pair_data.get('pdf2_path')
                            if pdf_path and os.path.exists(pdf_path):
                                self.image_viewer.load_pdf(pdf_path)
                                coords = ann.get('coordinates', {})
                                
                                if 'x1' in coords:
                                    # New format with absolute coordinates
                                    return self.image_viewer.extract_perfect_region(
                                        int(page_num), 
                                        coords['x1'], coords['y1'], 
                                        coords['x2'], coords['y2']
                                    )
                                else:
                                    # Legacy format - convert to absolute coordinates
                                    page_width = 612  # Standard PDF page width
                                    page_height = 792  # Standard PDF page height
                                    x1 = coords['x'] * page_width
                                    y1 = coords['y'] * page_height
                                    x2 = x1 + (coords['width'] * page_width)
                                    y2 = y1 + (coords['height'] * page_height)
                                    
                                    return self.image_viewer.extract_perfect_region(
                                        int(page_num), x1, y1, x2, y2
                                    )
            
            # If we get here, answer wasn't found
            print(f"Answer not found: {answer_id}")
            return None
            
        except Exception as e:
            print(f"Error extracting answer image: {e}")
            return None
    
    def toggle_stem_question(self):
        """Toggle between showing combined view and stem only"""
        if not self.current_question or not self.current_stem_id:
            return
        
        if self.showing_stem:
            # Currently showing stem only, switch to combined view
            stem_pixmap = self.extract_question_image(self.current_stem_id)
            question_pixmap = self.extract_question_image(self.current_question)
            self.image_viewer.display_combined_images(stem_pixmap, question_pixmap)
            self.show_stem_btn.setText("Show Stem Only")
            self.showing_stem = False
            self.viewer_title.setText(f"Question: {self.current_question}")
        else:
            # Currently showing combined view, switch to stem only
            stem_pixmap = self.extract_question_image(self.current_stem_id)
            self.image_viewer.display_single_image(stem_pixmap)
            self.show_stem_btn.setText("Show Combined")
            self.showing_stem = True
            self.viewer_title.setText(f"Stem: {self.current_stem_id}")
    
    def toggle_answer(self):
        """Toggle between showing question and answer"""
        if not self.current_question:
            return
        
        if self.showing_answer:
            # Currently showing answer, switch back to question
            self.load_current_question()
            self.show_answer_btn.setText("Show Answer")
            self.showing_answer = False
        else:
            # Currently showing question, switch to answer
            answer_pixmap = self.extract_answer_image(self.current_question)
            if answer_pixmap:
                self.image_viewer.display_single_image(answer_pixmap)
                self.show_answer_btn.setText("Show Question")
                self.showing_answer = True
                self.viewer_title.setText(f"Answer: {self.current_question}")
            else:
                QMessageBox.warning(self, "Answer Not Found", "Could not find answer image.")
    
    def mark_for_help(self):
        """Mark current question for help"""
        if not self.current_question:
            return
        
        if self.current_question in self.help_data.get('help', {}):
            # Remove from help
            del self.help_data['help'][self.current_question]
            self.help_btn.setText("Mark for Help")
            self.help_btn.setStyleSheet("""
                QPushButton {
                    background-color: #ffc107;
                    color: #212529;
                    border: none;
                    padding: 12px;
                    border-radius: 6px;
                    font-weight: bold;
                    margin: 5px;
                }
                QPushButton:hover {
                    background-color: #e0a800;
                }
            """)
            self.status_label.setText("Removed from help list")
        else:
            # Add to help
            dialog = HelpNoteDialog(self.current_question, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                note = dialog.get_note()
                if note:
                    self.help_data['help'][self.current_question] = note
                    self.help_btn.setText("Help ✓")
                    self.help_btn.setStyleSheet("""
                        QPushButton {
                            background-color: #ff9800;
                            color: white;
                            border: none;
                            padding: 12px;
                            border-radius: 6px;
                            font-weight: bold;
                            margin: 5px;
                        }
                        QPushButton:hover {
                            background-color: #f57c00;
                        }
                    """)
                    self.status_label.setText("Added to help list")
                else:
                    QMessageBox.information(self, "Note Required", "Please enter a help note.")
        
        # Save help data
        self.save_help_data()
    
    def save_help_data(self):
        """Save help data to JSON file"""
        try:
            with open(self.help_file, 'w') as f:
                json.dump(self.help_data, f, indent=2)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error saving help data: {e}")
    
    def mark_complete(self):
        """Mark current question as complete or incomplete"""
        if not self.current_question:
            return
        
        completed_list = self.completed_data.get('completed', [])
        
        if self.current_question in completed_list:
            # Remove from completed
            completed_list.remove(self.current_question)
            self.complete_btn.setText("Mark Complete")
            self.complete_btn.setStyleSheet("""
                QPushButton {
                    background-color: #6c757d;
                    color: white;
                    border: none;
                    padding: 12px;
                    border-radius: 6px;
                    font-weight: bold;
                    margin: 5px;
                }
                QPushButton:hover {
                    background-color: #5a6268;
                }
            """)
            self.status_label.setText("Marked as incomplete")
        else:
            # Add to completed
            completed_list.append(self.current_question)
            self.complete_btn.setText("Complete ✓")
            self.complete_btn.setStyleSheet("""
                QPushButton {
                    background-color: #28a745;
                    color: white;
                    border: none;
                    padding: 12px;
                    border-radius: 6px;
                    font-weight: bold;
                    margin: 5px;
                }
                QPushButton:hover {
                    background-color: #218838;
                }
            """)
            self.status_label.setText("Marked as complete")
        
        self.completed_data['completed'] = completed_list
        self.save_completed_data()
    
    def save_completed_data(self):
        """Save completed data to JSON file"""
        try:
            with open(self.completed_file, 'w') as f:
                json.dump(self.completed_data, f, indent=2)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error saving completed data: {e}")
    def save_sessions_data(self):
        """Save sessions data to JSON file"""
        try:
            with open(self.sessions_file, 'w') as f:
                json.dump(self.sessions_data, f, indent=2)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error saving sessions data: {e}")
    
    def load_session_by_id(self):
        """Load a saved session by its ID"""
        session_id = self.session_id_input.text().strip()
        
        if not session_id:
            QMessageBox.warning(self, "No Session ID", "Please enter a session ID to load.")
            return
        
        sessions = self.sessions_data.get('sessions', {})
        
        if session_id not in sessions:
            QMessageBox.warning(self, "Session Not Found", f"Session ID '{session_id}' not found.")
            return
        
        try:
            session_data = sessions[session_id]
            question_order = session_data.get('question_order', [])
            
            if not question_order:
                QMessageBox.warning(self, "Empty Session", "This session has no questions.")
                return
            
            # Apply current filter settings to the saved order
            if self.filter_completed:
                completed_list = self.completed_data.get('completed', [])
                self.current_questions = [q for q in question_order if q not in completed_list]
            else:
                self.current_questions = question_order.copy()
            # Save original order for toggling
            self.original_session_order = self.current_questions.copy()
            
            if not self.current_questions:
                QMessageBox.information(self, "All Complete", "All questions in this session are marked as complete!")
                return
            
            # Set current session
            self.current_session_id = session_id
            self.current_session_label.setText(f"Current Session: {session_id}")
            
            # Reset session state
            self.current_question_index = 0
            self.current_question = None
            self.showing_answer = False
            
            # Update UI
            self.update_question_counter()
            self.load_current_question()
            
            created = session_data.get('created', 'Unknown')
            total = session_data.get('total_questions', len(question_order))
            self.status_label.setText(f"Loaded session from {created} ({len(self.current_questions)}/{total} questions)")
            
            # Clear the input field
            self.session_id_input.clear()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error loading session: {e}")
    
    def toggle_filter_completed(self):
        """Toggle between showing all questions and hiding completed ones"""
        self.filter_completed = not self.filter_completed
        
        if self.filter_completed:
            self.filter_completed_btn.setText("Hide Completed ✓")
            self.filter_completed_btn.setStyleSheet("""
                QPushButton {
                    background-color: #28a745;
                    color: white;
                    border: none;
                    padding: 12px;
                    border-radius: 6px;
                    font-weight: bold;
                    margin: 5px;
                }
                QPushButton:hover {
                    background-color: #218838;
                }
            """)
        else:
            self.filter_completed_btn.setText("Show All Questions ✓")
            self.filter_completed_btn.setStyleSheet("""
                QPushButton {
                    background-color: #343a40;
                    color: white;
                    border: none;
                    padding: 12px;
                    border-radius: 6px;
                    font-weight: bold;
                    margin: 5px;
                }
                QPushButton:hover {
                    background-color: #23272b;
                }
            """)
        
        self.setup_practice_session()
        filter_type = "completed questions hidden" if self.filter_completed else "all questions shown"
        self.status_label.setText(f"Filter updated: {filter_type}")
    


    def show_help_review(self):
        """Show the help review dialog"""
        help_questions = list(self.help_data.get('help', {}).keys())
        
        if not help_questions:
            QMessageBox.information(self, "No Help Questions", "No questions are marked for help.")
            return
        
        dialog = HelpReviewDialog(help_questions, self.help_data.get('help', {}), self)
        dialog.exec()
    
    def previous_question(self):
        """Go to previous question"""
        if self.current_question_index > 0:
            self.current_question_index -= 1
            self.update_question_counter()
            self.load_current_question()
            self.show_answer_btn.setText("Show Answer")
            self.showing_answer = False
            self.showing_stem = False
    
    def next_question(self):
        """Go to next question"""
        if self.current_question_index < len(self.current_questions) - 1:
            self.current_question_index += 1
            self.update_question_counter()
            self.load_current_question()
            self.show_answer_btn.setText("Show Answer")
            self.showing_answer = False
            self.showing_stem = False
    
    def toggle_order(self):
        """Toggle between random and structured order"""
        if not self.current_questions or not self.original_session_order:
            # No active session, just toggle preference
            self.random_order = not self.random_order
            
            if self.random_order:
                self.order_toggle_btn.setText("Random Order ✓")
                self.order_toggle_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #6f42c1;
                        color: white;
                        border: none;
                        padding: 12px;
                        border-radius: 6px;
                        font-weight: bold;
                        margin: 5px;
                    }
                    QPushButton:hover {
                        background-color: #5a32a3;
                    }
                """)
                self.status_label.setText("Next session will use random order")
            else:
                self.order_toggle_btn.setText("Structured Order ✓")
                self.order_toggle_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #fd7e14;
                        color: white;
                        border: none;
                        padding: 12px;
                        border-radius: 6px;
                        font-weight: bold;
                        margin: 5px;
                    }
                    QPushButton:hover {
                        background-color: #e8690b;
                    }
                """)
                self.status_label.setText("Next session will use structured order")
            return
        
        # Toggle between current session's random order and structured order
        self.random_order = not self.random_order
        
        if self.random_order:
            # Switch back to original random order
            self.current_questions = self.original_session_order.copy()
            self.order_toggle_btn.setText("Random Order ✓")
            self.order_toggle_btn.setStyleSheet("""
                QPushButton {
                    background-color: #6f42c1;
                    color: white;
                    border: none;
                    padding: 12px;
                    border-radius: 6px;
                    font-weight: bold;
                    margin: 5px;
                }
                QPushButton:hover {
                    background-color: #5a32a3;
                }
            """)
            self.status_label.setText("Switched back to original random order")
        else:
            # Switch to structured order
            all_questions = list(self.links_data.get('questions', {}).keys())
            self.current_questions.sort(key=lambda x: all_questions.index(x) if x in all_questions else len(all_questions))
            self.order_toggle_btn.setText("Structured Order ✓")
            self.order_toggle_btn.setStyleSheet("""
                QPushButton {
                    background-color: #fd7e14;
                    color: white;
                    border: none;
                    padding: 12px;
                    border-radius: 6px;
                    font-weight: bold;
                    margin: 5px;
                }
                QPushButton:hover {
                    background-color: #e8690b;
                }
            """)
            self.status_label.setText("Switched to structured order")
        
        # Reset to first question
        self.current_question_index = 0
        self.update_question_counter()
        self.load_current_question()
    def update_question_counter(self):
        """Update the question counter display"""
        total = len(self.current_questions)
        current = self.current_question_index + 1 if total > 0 else 0
        self.question_counter.setText(f"Question {current}/{total}")
        
        # Update navigation button states
        self.prev_btn.setEnabled(self.current_question_index > 0)
        self.next_btn.setEnabled(self.current_question_index < total - 1)

class HelpReviewDialog(QDialog):
    """Dialog for reviewing help-marked questions"""
    
    def __init__(self, help_questions, help_data, parent=None):
        super().__init__(parent)
        self.help_questions = help_questions
        self.help_data = help_data
        self.current_index = 0
        
        self.setWindowTitle("Help Review")
        self.setModal(True)
        self.resize(900, 700)
        
        self.init_ui()
        self.load_current_question()
    
    def init_ui(self):
        """Initialize the help review UI"""
        layout = QVBoxLayout()
        
        # Title
        title = QLabel("Help Review")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #0078d4; margin: 10px;")
        layout.addWidget(title)
        
        # Question counter
        self.help_counter = QLabel("Help Question 0/0")
        self.help_counter.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.help_counter.setStyleSheet("font-size: 14px; color: #666; margin: 5px;")
        layout.addWidget(self.help_counter)
        
        # Navigation
        nav_layout = QHBoxLayout()
        
        self.help_prev_btn = QPushButton("◀ Previous")
        self.help_prev_btn.clicked.connect(self.previous_help_question)
        self.help_prev_btn.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                border: none;
                padding: 8px 12px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
        """)
        nav_layout.addWidget(self.help_prev_btn)
        
        self.help_next_btn = QPushButton("Next ▶")
        self.help_next_btn.clicked.connect(self.next_help_question)
        self.help_next_btn.setStyleSheet("""
            QPushButton {
                background-color: #0078d4;
                color: white;
                border: none;
                padding: 8px 12px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #106ebe;
            }
        """)
        nav_layout.addWidget(self.help_next_btn)
        
        layout.addLayout(nav_layout)
        
        # Question info
        self.help_question_id = QLabel("Question ID: None")
        self.help_question_id.setStyleSheet("font-weight: bold; padding: 10px; background-color: #f8f9fa; border-radius: 4px;")
        layout.addWidget(self.help_question_id)
        
        # Help note
        note_label = QLabel("Help Note:")
        note_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        layout.addWidget(note_label)
        
        self.help_note_display = QTextEdit()
        self.help_note_display.setReadOnly(True)
        self.help_note_display.setMaximumHeight(120)
        self.help_note_display.setStyleSheet("""
            QTextEdit {
                border: 2px solid #dee2e6;
                border-radius: 4px;
                padding: 8px;
                background-color: #fff3cd;
                color: #212529;
            }
        """)
        layout.addWidget(self.help_note_display)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.remove_help_btn = QPushButton("Remove from Help")
        self.remove_help_btn.clicked.connect(self.remove_from_help)
        self.remove_help_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                border: none;
                padding: 10px 15px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #c82333;
            }
        """)
        button_layout.addWidget(self.remove_help_btn)
        
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.accept)
        self.close_btn.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                border: none;
                padding: 10px 15px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
        """)
        button_layout.addWidget(self.close_btn)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def load_current_question(self):
        """Load the current help question"""
        if not self.help_questions:
            return
        
        question_id = self.help_questions[self.current_index]
        note = self.help_data.get(question_id, "")
        
        self.help_question_id.setText(f"Question ID: {question_id}")
        self.help_note_display.setPlainText(note)
        
        # Update counter
        total = len(self.help_questions)
        current = self.current_index + 1
        self.help_counter.setText(f"Help Question {current}/{total}")
        
        # Update navigation buttons
        self.help_prev_btn.setEnabled(self.current_index > 0)
        self.help_next_btn.setEnabled(self.current_index < total - 1)
    
    def previous_help_question(self):
        """Go to previous help question"""
        if self.current_index > 0:
            self.current_index -= 1
            self.load_current_question()
    
    def next_help_question(self):
        """Go to next help question"""
        if self.current_index < len(self.help_questions) - 1:
            self.current_index += 1
            self.load_current_question()
    
    def remove_from_help(self):
        """Remove current question from help list"""
        if not self.help_questions:
            return
        
        question_id = self.help_questions[self.current_index]
        
        reply = QMessageBox.question(
            self, 'Remove from Help',
            f'Remove "{question_id}" from help list?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # Remove from help data
            if question_id in self.help_data:
                del self.help_data[question_id]
            
            # Remove from questions list
            self.help_questions.pop(self.current_index)
            
            # Adjust index if necessary
            if self.current_index >= len(self.help_questions):
                self.current_index = max(0, len(self.help_questions) - 1)
            
            # Reload or close if no more questions
            if self.help_questions:
                self.load_current_question()
            else:
                QMessageBox.information(self, "No More Questions", "No more help questions remaining.")
                self.accept()

def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    # Set application properties
    app.setApplicationName("Homework Practice Mode")
    app.setApplicationVersion("1.0")
    
    # Create and show the main window
    homework_practice = HomeworkPractice()
    homework_practice.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
