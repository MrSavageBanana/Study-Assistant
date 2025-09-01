#!/usr/bin/env python3
"""
Homework Mode - Practice Interface for Students
Reads pdf_pairs.json and links.json to create randomized practice sets

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
    QFormLayout, QLineEdit, QFrame, QSplitter, QGroupBox
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap, QImage, QFont, QPalette, QColor

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

class PDFViewer(QWidget):
    """Simple PDF viewer for displaying question/answer images"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.pdf_document = None
        self.current_page = None
        
        layout = QVBoxLayout()
        
        # Image display
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(400, 500)
        self.image_label.setStyleSheet("border: 2px solid #ccc; background-color: #f5f5f5;")
        
        scroll_area = QScrollArea()
        scroll_area.setWidget(self.image_label)
        scroll_area.setWidgetResizable(True)
        layout.addWidget(scroll_area)
        
        self.setLayout(layout)
    
    def load_pdf(self, pdf_path):
        """Load a PDF file"""
        try:
            self.pdf_document = fitz.open(pdf_path)
            return True
        except Exception as e:
            print(f"Error loading PDF: {e}")
            return False
    
    def show_page(self, page_num):
        """Display a specific page"""
        if not self.pdf_document or page_num >= len(self.pdf_document):
            return False
        
        try:
            page = self.pdf_document[page_num]
            mat = fitz.Matrix(1.5, 1.5)  # Scale for better viewing
            pix = page.get_pixmap(matrix=mat, alpha=False)
            
            # Convert to QPixmap
            img_data = pix.tobytes("ppm")
            qimg = QImage.fromData(img_data)
            pixmap = QPixmap.fromImage(qimg)
            
            self.image_label.setPixmap(pixmap)
            self.current_page = page_num
            return True
            
        except Exception as e:
            print(f"Error displaying page: {e}")
            return False
    
    def extract_region(self, page_num, x1, y1, x2, y2):
        """Extract and display a specific region from a page"""
        if not self.pdf_document or page_num >= len(self.pdf_document):
            return False
        
        try:
            page = self.pdf_document[page_num]
            
            # Create rectangle for extraction
            rect = fitz.Rect(x1, y1, x2, y2)
            
            # Extract the region
            mat = fitz.Matrix(2.0, 2.0)  # Higher resolution for extraction
            pix = page.get_pixmap(matrix=mat, clip=rect)
            
            # Convert to QPixmap
            img_data = pix.tobytes("ppm")
            qimg = QImage.fromData(img_data)
            pixmap = QPixmap.fromImage(qimg)
            
            self.image_label.setPixmap(pixmap)
            return True
            
        except Exception as e:
            print(f"Error extracting region: {e}")
            return False

class HomeworkMode(QMainWindow):
    """Main Homework Mode application"""
    
    def __init__(self):
        super().__init__()
        self.pdf_pairs_data = {}
        self.links_data = {}
        self.help_data = {}
        self.current_questions = []
        self.current_question_index = 0
        self.current_question = None
        
        # File paths
        self.pdf_pairs_file = "pdf_pairs.json"
        self.links_file = "links.json"
        self.help_file = "help.json"
        
        self.init_ui()
        self.load_data()
        self.setup_practice_session()
    
    def init_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle("Homework Mode - Practice Interface")
        self.setGeometry(100, 100, 1400, 900)
        
        # Main widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QHBoxLayout()
        
        # Left panel - Question navigation and controls
        left_panel = QWidget()
        left_panel.setFixedWidth(400)
        left_layout = QVBoxLayout()
        
        # Title
        title = QLabel("Homework Mode")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #0078d4; margin: 10px;")
        left_layout.addWidget(title)
        
        # Question counter
        self.question_counter = QLabel("Question 0/0")
        self.question_counter.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.question_counter.setStyleSheet("font-size: 14px; color: #666; margin: 5px;")
        left_layout.addWidget(self.question_counter)
        
        # Navigation buttons
        nav_layout = QHBoxLayout()
        
        self.prev_btn = QPushButton("◀ Previous")
        self.prev_btn.clicked.connect(self.previous_question)
        self.prev_btn.setEnabled(False)
        nav_layout.addWidget(self.prev_btn)
        
        self.next_btn = QPushButton("Next ▶")
        self.next_btn.clicked.connect(self.next_question)
        nav_layout.addWidget(self.next_btn)
        
        left_layout.addLayout(nav_layout)
        
        # Question info group
        question_group = QGroupBox("Question Information")
        question_layout = QVBoxLayout()
        
        self.question_id_label = QLabel("ID: None")
        self.question_id_label.setStyleSheet("font-weight: bold; color: #333;")
        question_layout.addWidget(self.question_id_label)
        
        self.stem_label = QLabel("Stem: None")
        self.stem_label.setWordWrap(True)
        self.stem_label.setStyleSheet("color: #666; font-style: italic;")
        question_layout.addWidget(self.stem_label)
        
        question_group.setLayout(question_layout)
        left_layout.addWidget(question_group)
        
        # Action buttons
        actions_group = QGroupBox("Actions")
        actions_layout = QVBoxLayout()
        
        self.show_answer_btn = QPushButton("Show Answer")
        self.show_answer_btn.clicked.connect(self.toggle_answer)
        self.show_answer_btn.setEnabled(False)
        actions_layout.addWidget(self.show_answer_btn)
        
        self.help_btn = QPushButton("Mark for Help")
        self.help_btn.clicked.connect(self.mark_for_help)
        self.help_btn.setEnabled(False)
        actions_layout.addWidget(self.help_btn)
        
        self.new_session_btn = QPushButton("New Practice Session")
        self.new_session_btn.clicked.connect(self.setup_practice_session)
        actions_layout.addWidget(self.new_session_btn)
        
        self.help_review_btn = QPushButton("Help Review")
        self.help_review_btn.clicked.connect(self.show_help_review)
        actions_layout.addWidget(self.help_review_btn)
        
        actions_group.setLayout(actions_layout)
        left_layout.addWidget(actions_group)
        
        # Status
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #666; font-size: 12px;")
        left_layout.addWidget(self.status_label)
        
        left_layout.addStretch()
        left_panel.setLayout(left_layout)
        
        # Right panel - PDF viewer
        right_panel = QWidget()
        right_layout = QVBoxLayout()
        
        # Viewer title
        self.viewer_title = QLabel("Question")
        self.viewer_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.viewer_title.setStyleSheet("font-size: 16px; font-weight: bold; margin: 5px;")
        right_layout.addWidget(self.viewer_title)
        
        # PDF viewer
        self.pdf_viewer = PDFViewer()
        right_layout.addWidget(self.pdf_viewer)
        
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
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error loading data: {e}")
    
    def setup_practice_session(self):
        """Set up a new randomized practice session"""
        try:
            # Get all question IDs from links.json
            questions = list(self.links_data.get('questions', {}).keys())
            
            if not questions:
                QMessageBox.information(self, "No Questions", "No questions found in links.json")
                return
            
            # Shuffle questions
            self.current_questions = questions.copy()
            random.shuffle(self.current_questions)
            
            # Reset session
            self.current_question_index = 0
            self.current_question = None
            
            # Update UI
            self.update_question_counter()
            self.load_current_question()
            
            self.status_label.setText(f"New practice session started with {len(questions)} questions")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error setting up practice session: {e}")
    
    def load_current_question(self):
        """Load and display the current question"""
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
        if stem_id:
            stem_data = self.links_data.get('questions', {}).get(stem_id, {})
            if stem_data.get('isStem'):
                self.stem_label.setText(f"Stem: {stem_id}")
                # Load stem image
                self.load_question_image(stem_id, "Stem")
            else:
                self.stem_label.setText("Stem: Invalid stem reference")
                self.load_question_image(question_id, "Question")
        else:
            self.stem_label.setText("Stem: None")
            self.load_question_image(question_id, "Question")
        
        # Update button states
        self.show_answer_btn.setEnabled(True)
        self.help_btn.setEnabled(True)
        
        # Check if question is marked for help
        if question_id in self.help_data.get('help', {}):
            self.help_btn.setText("Help ✓")
            self.help_btn.setStyleSheet("background-color: #ff9800; color: white;")
        else:
            self.help_btn.setText("Mark for Help")
            self.help_btn.setStyleSheet("")
    
    def load_question_image(self, question_id, image_type):
        """Load and display the image for a question or stem"""
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
                                self.pdf_viewer.load_pdf(pdf_path)
                                coords = ann.get('coordinates', {})
                                
                                if 'x1' in coords:
                                    # New format
                                    success = self.pdf_viewer.extract_region(
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
                                    
                                    success = self.pdf_viewer.extract_region(
                                        int(page_num), x1, y1, x2, y2
                                    )
                                
                                if success:
                                    self.viewer_title.setText(f"{image_type}: {question_id}")
                                    return
                
                # Search in PDF2 (answers)
                for page_num, page_annotations in pdf2_annotations.items():
                    for ann in page_annotations:
                        if ann.get('selection_id') == question_id:
                            # Load PDF and extract region
                            pdf_path = pair_data.get('pdf2_path')
                            if pdf_path and os.path.exists(pdf_path):
                                self.pdf_viewer.load_pdf(pdf_path)
                                coords = ann.get('coordinates', {})
                                
                                if 'x1' in coords:
                                    # New format
                                    success = self.pdf_viewer.extract_region(
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
                                    
                                    success = self.pdf_viewer.extract_region(
                                        int(page_num), x1, y1, x2, y2
                                    )
                                
                                if success:
                                    self.viewer_title.setText(f"{image_type}: {question_id}")
                                    return
            
            # If we get here, question wasn't found
            self.viewer_title.setText(f"Question not found: {question_id}")
            
        except Exception as e:
            print(f"Error loading question image: {e}")
            self.viewer_title.setText(f"Error loading image")
    
    def load_answer_image(self, question_id):
        """Load and display the answer image for a question"""
        try:
            question_data = self.links_data.get('questions', {}).get(question_id, {})
            answer_id = question_data.get('answer')
            
            if not answer_id:
                QMessageBox.information(self, "No Answer", "This question has no answer linked to it.")
                return
            
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
                                self.pdf_viewer.load_pdf(pdf_path)
                                coords = ann.get('coordinates', {})
                                
                                if 'x1' in coords:
                                    # New format
                                    success = self.pdf_viewer.extract_region(
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
                                    
                                    success = self.pdf_viewer.extract_region(
                                        int(page_num), x1, y1, x2, y2
                                    )
                                
                                if success:
                                    self.viewer_title.setText(f"Answer: {answer_id}")
                                    return
                
                # Search in PDF2 (answers)
                for page_num, page_annotations in pdf2_annotations.items():
                    for ann in page_annotations:
                        if ann.get('selection_id') == answer_id:
                            # Load PDF and extract region
                            pdf_path = pair_data.get('pdf2_path')
                            if pdf_path and os.path.exists(pdf_path):
                                self.pdf_viewer.load_pdf(pdf_path)
                                coords = ann.get('coordinates', {})
                                
                                if 'x1' in coords:
                                    # New format
                                    success = self.pdf_viewer.extract_region(
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
                                    
                                    success = self.pdf_viewer.extract_region(
                                        int(page_num), x1, y1, x2, y2
                                    )
                                
                                if success:
                                    self.viewer_title.setText(f"Answer: {answer_id}")
                                    return
            
            # If we get here, answer wasn't found
            QMessageBox.warning(self, "Answer Not Found", f"Could not find answer: {answer_id}")
            
        except Exception as e:
            print(f"Error loading answer image: {e}")
            QMessageBox.critical(self, "Error", f"Error loading answer: {e}")
    
    def toggle_answer(self):
        """Toggle between showing question and answer"""
        if not self.current_question:
            return
        
        if self.viewer_title.text().startswith("Answer:"):
            # Currently showing answer, switch back to question
            self.load_current_question()
            self.show_answer_btn.setText("Show Answer")
        else:
            # Currently showing question, switch to answer
            self.load_answer_image(self.current_question)
            self.show_answer_btn.setText("Show Question")
    
    def mark_for_help(self):
        """Mark current question for help"""
        if not self.current_question:
            return
        
        if self.current_question in self.help_data.get('help', {}):
            # Remove from help
            del self.help_data['help'][self.current_question]
            self.help_btn.setText("Mark for Help")
            self.help_btn.setStyleSheet("")
            self.status_label.setText("Removed from help list")
        else:
            # Add to help
            dialog = HelpNoteDialog(self.current_question, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                note = dialog.get_note()
                if note:
                    self.help_data['help'][self.current_question] = note
                    self.help_btn.setText("Help ✓")
                    self.help_btn.setStyleSheet("background-color: #ff9800; color: white;")
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
    
    def next_question(self):
        """Go to next question"""
        if self.current_question_index < len(self.current_questions) - 1:
            self.current_question_index += 1
            self.update_question_counter()
            self.load_current_question()
            self.show_answer_btn.setText("Show Answer")
    
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
        self.resize(800, 600)
        
        self.init_ui()
        self.load_current_question()
    
    def init_ui(self):
        """Initialize the help review UI"""
        layout = QVBoxLayout()
        
        # Title
        title = QLabel("Help Review")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #0078d4;")
        layout.addWidget(title)
        
        # Question counter
        self.help_counter = QLabel("Help Question 0/0")
        self.help_counter.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.help_counter.setStyleSheet("font-size: 14px; color: #666;")
        layout.addWidget(self.help_counter)
        
        # Navigation
        nav_layout = QHBoxLayout()
        
        self.help_prev_btn = QPushButton("◀ Previous")
        self.help_prev_btn.clicked.connect(self.previous_help_question)
        nav_layout.addWidget(self.help_prev_btn)
        
        self.help_next_btn = QPushButton("Next ▶")
        self.help_next_btn.clicked.connect(self.next_help_question)
        nav_layout.addWidget(self.help_next_btn)
        
        layout.addLayout(nav_layout)
        
        # Question info
        self.help_question_id = QLabel("Question ID: None")
        self.help_question_id.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.help_question_id)
        
        # Help note
        note_label = QLabel("Help Note:")
        layout.addWidget(note_label)
        
        self.help_note_display = QTextEdit()
        self.help_note_display.setReadOnly(True)
        self.help_note_display.setMaximumHeight(100)
        layout.addWidget(self.help_note_display)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.remove_help_btn = QPushButton("Remove from Help")
        self.remove_help_btn.clicked.connect(self.remove_from_help)
        button_layout.addWidget(self.remove_help_btn)
        
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.accept)
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
    app.setApplicationName("Homework Mode")
    app.setApplicationVersion("1.0")
    
    # Create and show the main window
    homework_mode = HomeworkMode()
    homework_mode.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
