import os
import glob
import logging
import mne
from PyQt6.QtWidgets import (QMainWindow, QVBoxLayout, QHBoxLayout, 
                            QWidget, QPushButton, QLabel, QFileDialog, QMessageBox,
                            QListWidget, QTextEdit, QSizePolicy, QApplication)
from PyQt6.QtCore import Qt, QEvent, QTimer
from PyQt6.QtGui import QFont
import time
import psutil

# Local imports
from iom import IOM_file
from log_viewer import LogViewer

logger = logging.getLogger(__name__)

class AnnotationTool(QMainWindow):
    
    def __init__(self):
        super().__init__()
        self.selected_folder = None
        self.found_files = []
        self.subfolder_iom_info = []  # Store subfolder info for later use
        self.open_annotation_windows = {}  # Track opened annotation windows
        self.open_log_windows = {}  # Track opened log viewer windows
        
        # Track filename-specific windows for monitoring
        self.tracked_filename_windows = {}  # {filename: {'title': window_title, 'status': 'open'/'closed'}}
        self.previous_window_titles = set()  # To detect window closures
        
        # Global array to store data instances for opened files
        self.opened_data_instances = {}  # {filename: mne.Raw data instance}
        
        # Start continuous window monitoring using event loop
        self.start_window_monitoring()
        
        self.init_ui()
        
    def init_ui(self):
        """Initialize the user interface components."""
        self.setWindowTitle("TRACER - Seizure Annotation Tool")
        self.setGeometry(100, 100, 800, 600)
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QVBoxLayout(central_widget)
        
        # Title
        title_label = QLabel("TRACER Seizure Annotation Tool")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        main_layout.addWidget(title_label)
        
        # Folder selection section
        folder_layout = QHBoxLayout()
        self.folder_label = QLabel("No folder selected")
        self.folder_label.setStyleSheet("padding: 10px; border: 1px solid gray; background-color: #f0f0f0; color: #333333;")
        folder_layout.addWidget(self.folder_label)
        
        select_folder_btn = QPushButton("Select Folder")
        select_folder_btn.clicked.connect(self.select_folder)
        select_folder_btn.setStyleSheet("padding: 10px; font-size: 12px;")
        select_folder_btn.setFixedHeight(44)  # Match the label height with padding
        folder_layout.addWidget(select_folder_btn)
        
        main_layout.addLayout(folder_layout)
        
        # File information section
        files_label = QLabel("Found Files:")
        files_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        main_layout.addWidget(files_label)
        
        self.files_list = QListWidget()
        self.files_list.setMaximumHeight(150)
        self.files_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)  # Enable multi-selection
        self.files_list.itemSelectionChanged.connect(self.on_file_selection_changed)
        main_layout.addWidget(self.files_list)
        
        # Status/Info section
        self.info_text = QTextEdit()
        self.info_text.setMaximumHeight(100)
        self.info_text.setPlainText("Please select a folder containing .h5 or .iom files to begin.")
        self.info_text.setReadOnly(True)
        main_layout.addWidget(self.info_text)
        
        # Action buttons section
        button_layout = QHBoxLayout()
        
        self.review_btn = QPushButton("Review")
        self.review_btn.setEnabled(False)
        self.review_btn.clicked.connect(self.review_files)
        self.review_btn.setStyleSheet("QPushButton { padding: 10px; font-size: 12px; }")
        button_layout.addWidget(self.review_btn)
        
        self.annotate_btn = QPushButton("Annotate")
        self.annotate_btn.setEnabled(False)
        self.annotate_btn.clicked.connect(self.annotate_files)
        self.annotate_btn.setStyleSheet("QPushButton { padding: 10px; font-size: 12px; }")
        button_layout.addWidget(self.annotate_btn)
        
        self.parse_btn = QPushButton("Parse")
        self.parse_btn.setEnabled(False)
        self.parse_btn.setVisible(False)  # Hidden by default
        self.parse_btn.clicked.connect(self.parse_files)
        self.parse_btn.setStyleSheet("QPushButton { padding: 10px; font-size: 12px; }")
        button_layout.addWidget(self.parse_btn)
        
        self.read_log_btn = QPushButton("Read Log")
        self.read_log_btn.setEnabled(False)
        self.read_log_btn.setVisible(False)  # Hidden by default
        self.read_log_btn.clicked.connect(self.read_log_files)
        self.read_log_btn.setStyleSheet("QPushButton { padding: 10px; font-size: 12px; }")
        button_layout.addWidget(self.read_log_btn)
        
        main_layout.addLayout(button_layout)
        
        # Status tracking section
        status_label = QLabel("Annotation Status:")
        status_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        main_layout.addWidget(status_label)
        
        self.status_text = QTextEdit()
        self.status_text.setMinimumHeight(120)  # Set minimum instead of maximum height
        self.status_text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.status_text.setReadOnly(True)
        self.status_text.setStyleSheet("background-color: #f9f9f9; border: 1px solid #ccc; color: #333;")
        self.status_text.setPlainText("Ready to open annotation windows. Status updates will appear here.")
        main_layout.addWidget(self.status_text, 1)  # Add stretch factor to prioritize expansion
        
        # Add some spacing
        main_layout.addStretch()
    
    def start_window_monitoring(self):
        """Start continuous monitoring of PyQt6 windows using QApplication event loop."""
        self.monitoring_active = True
        # Use QApplication.processEvents to continuously monitor
        self.monitor_windows_continuous()
    
    def get_qt_window_titles(self):
        """Get all PyQt6 window titles from the current QApplication."""
        window_titles = []
        
        try:
            app = QApplication.instance()
            if app:
                # Get all top-level widgets (windows)
                for widget in app.topLevelWidgets():
                    if widget.isVisible() and hasattr(widget, 'windowTitle'):
                        title = widget.windowTitle()
                        if title and title.strip():
                            window_titles.append(title)
                            
                # Also check for any matplotlib/mne windows using psutil
                for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                    try:
                        proc_info = proc.info
                        if proc_info['name'] and 'python' in proc_info['name'].lower():
                            # Check if it's related to matplotlib or mne
                            cmdline = proc_info.get('cmdline', [])
                            if any('matplotlib' in str(arg) or 'mne' in str(arg) or 'qt' in str(arg).lower() 
                                   for arg in cmdline if arg):
                                # Try to get window title from process (this is a simplified approach)
                                window_titles.append(f"Python Process (PID: {proc_info['pid']})")
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        continue
                        
        except Exception as e:
            logger.error(f"Error getting Qt window titles: {e}")
        
        return list(set(window_titles))  # Remove duplicates
    
    def print_qt_window_titles(self):
        """Print all PyQt6 window titles to console and track filename windows."""
        try:
            window_titles = self.get_qt_window_titles()
            current_window_titles = set(window_titles)
            
            # Detect newly closed windows
            closed_windows = self.previous_window_titles - current_window_titles
            
            # Check for filename-specific window closures
            for closed_title in closed_windows:
                self.check_filename_window_closure(closed_title)
            
            # Detect newly opened windows and track filename windows (silent)
            new_windows = current_window_titles - self.previous_window_titles
            for new_title in new_windows:
                self.check_filename_window_opening_silent(new_title)
            
            # Update previous window titles
            self.previous_window_titles = current_window_titles
            
            # Remove the total count display - just show window list
            # print(f"\n=== PyQt6 WINDOWS ({len(window_titles)} total) ===")
            # for i, title in enumerate(window_titles, 1):
            #     print(f"{i:2d}. {title}")
            # print("=" * 50)
            
        except Exception as e:
            logger.error(f"Error printing Qt window titles: {e}")
            print(f"Error getting Qt window titles: {e}")
    
    def check_filename_window_opening_silent(self, window_title):
        """Silently check if a newly opened window contains a filename and track it."""
        try:
            # Look for .h5 files in window title
            for filename in [os.path.basename(f) for f in self.found_files if f.endswith('.h5')]:
                base_filename = filename.replace('.h5', '')
                if base_filename in window_title or filename in window_title:
                    self.tracked_filename_windows[filename] = {
                        'title': window_title,
                        'status': 'open'
                    }
                    return
            
            # Also check for any .iom files or folder names
            for subfolder_info in self.subfolder_iom_info:
                folder_name = subfolder_info['folder_name']
                if folder_name in window_title:
                    display_name = f"{folder_name}.iom"
                    self.tracked_filename_windows[display_name] = {
                        'title': window_title,
                        'status': 'open'
                    }
                    return
                    
        except Exception as e:
            logger.error(f"Error checking filename window opening: {e}")
    
    def check_filename_window_closure(self, window_title):
        """Check if a closed window was tracked and print the closure."""
        try:
            # Find which filename this window belongs to
            for filename, info in list(self.tracked_filename_windows.items()):
                if info['title'] == window_title and info['status'] == 'open':
                    # Mark as closed
                    self.tracked_filename_windows[filename]['status'] = 'closed'
                    
                    # Only print closure message
                    print(f"� WINDOW CLOSED: {filename}")
                    
                    # Remove data instance from global array when window closes
                    if filename in self.opened_data_instances:
                        data = self.opened_data_instances[filename]

                        try:
                            exports_path = self.ensure_exports_folder()
                            base_name = filename.replace('.h5', '')
                            export_subfolder = os.path.join(exports_path, base_name)

                            self.add_status_message(f"💾 Saving changes for: {filename}")
                
                            # Save back to the same location, overwriting existing files
                            export_base_path = os.path.join(export_subfolder, base_name)
                            
                            mne.export.export_raw(export_base_path + '.eeg', data, overwrite=True)
                            
                            self.add_status_message(f"✅ Review and save completed: {filename}")
                            logger.info(f"Successfully completed review and save for: {filename}")

                            self.mark_exported_files()
                            
                        except FileNotFoundError as e:
                            logger.error(f"Export files not found for {filename}: {e}")
                            self.add_status_message(f"❌ ERROR: Export files not found - {filename}")
                            
                        except PermissionError:
                            logger.error(f"Permission denied accessing exports for: {filename}")
                            self.add_status_message(f"❌ ERROR: Permission denied - {filename}")
                            
                        except Exception as e:
                            error_msg = str(e)
                            logger.error(f"Error reviewing file {filename}: {error_msg}")
                            self.add_status_message(f"❌ ERROR: Review failed - {filename} ({error_msg})")

                        del data
                        print(f"🗑️ REMOVED DATA INSTANCE: {filename}")
                    
                    # Call the existing closure handlers if they exist
                    if filename.endswith('.h5'):
                        self.on_annotation_window_closed(filename)
                    elif 'log' in filename.lower() or '_log' in filename:
                        self.on_log_window_closed(filename.replace('_log', ''))
                    
                    return
                    
        except Exception as e:
            logger.error(f"Error checking filename window closure: {e}")
    
    def register_filename_window(self, filename, window_title=None):
        """Silently register a filename window for tracking."""
        try:
            if not window_title:
                window_title = f"MNE Browser - {filename}"
            
            self.tracked_filename_windows[filename] = {
                'title': window_title,
                'status': 'open'
            }
            
        except Exception as e:
            logger.error(f"Error registering filename window: {e}")
    
    def get_data_instance(self, filename):
        """Get the MNE data instance for a specific filename."""
        return self.opened_data_instances.get(filename, None)
    
    def get_all_opened_files(self):
        """Get list of all currently opened filenames with data instances."""
        return list(self.opened_data_instances.keys())
    
    def get_opened_data_count(self):
        """Get the count of currently opened data instances."""
        return len(self.opened_data_instances)
    
    def print_opened_data_status(self):
        """Print status of all opened data instances."""
        if not self.opened_data_instances:
            print("📊 No data instances currently opened")
        else:
            print(f"📊 OPENED DATA INSTANCES ({len(self.opened_data_instances)} total):")
            for filename in self.opened_data_instances.keys():
                print(f"  📂 {filename}")
    
    def monitor_windows_continuous(self):
        """Continuously monitor and print window titles using event loop."""
        def monitor_loop():
            if hasattr(self, 'monitoring_active') and self.monitoring_active:
                self.print_qt_window_titles()
                # Schedule next monitoring cycle
                QTimer.singleShot(2000, monitor_loop)  # Print every 2 seconds
        
        # Start the monitoring loop
        monitor_loop()
        
    def stop_window_monitoring(self):
        """Stop the window monitoring."""
        self.monitoring_active = False
        
    def closeEvent(self, event):
        """Handle application closing."""
        self.stop_window_monitoring()
        super().closeEvent(event)
        
    def ensure_exports_folder(self):
        """Create exports folder if it doesn't exist."""
        if self.selected_folder:
            # Move exports to parent directory (same level as data folder)
            parent_dir = os.path.dirname(self.selected_folder)
            exports_path = os.path.join(parent_dir, 'exports')
            if not os.path.exists(exports_path):
                try:
                    os.makedirs(exports_path)
                    self.add_status_message(f"📁 Created exports folder: {exports_path}")
                    logger.info(f"Created exports folder: {exports_path}")
                except Exception as e:
                    logger.error(f"Failed to create exports folder: {e}")
                    self.add_status_message(f"❌ Failed to create exports folder: {e}")
            return exports_path
        return None
    
    def get_exported_files(self):
        """Get list of .h5 files that already have exports."""
        exported_files = []
        if self.selected_folder:
            # Look in parent directory for exports folder
            parent_dir = os.path.dirname(self.selected_folder)
            exports_path = os.path.join(parent_dir, 'exports')
            if os.path.exists(exports_path):
                # Look for subfolders in exports folder
                try:
                    for item in os.listdir(exports_path):
                        item_path = os.path.join(exports_path, item)
                        if os.path.isdir(item_path):
                            # Check if this subfolder contains a .vhdr file (BrainVision header)
                            expected_vhdr_file = f"{item}.vhdr"
                            vhdr_file_path = os.path.join(item_path, expected_vhdr_file)
                            if os.path.exists(vhdr_file_path):
                                # Convert subfolder name back to .h5 filename
                                h5_filename = f"{item}.h5"
                                if h5_filename in [os.path.basename(f) for f in self.found_files]:
                                    exported_files.append(h5_filename)
                    logger.info(f"Found {len(exported_files)} exported files: {exported_files}")
                except Exception as e:
                    logger.error(f"Error scanning exports folder: {e}")
        return exported_files
    
    def mark_exported_files(self):
        """Mark .h5 files with tick if they already have exports."""
        exported_files = self.get_exported_files()
        
        for i in range(self.files_list.count()):
            item = self.files_list.item(i)
            filename = item.text()
            
            # Remove existing tick marks first
            if filename.startswith("✓ "):
                filename = filename[2:]
                item.setText(filename)
            
            # Add tick mark if file has been exported
            if filename in exported_files:
                item.setText(f"✓ {filename}")
                item.setToolTip(f"This file has been exported to the exports folder")
                
        if exported_files:
            self.add_status_message(f"📊 Marked {len(exported_files)} files with exports: {', '.join(exported_files)}")
    
    def create_export_for_file(self, filename, raw_data):
        """Create export folder and save raw data for a .h5 file."""
        try:
            exports_path = self.ensure_exports_folder()
            if not exports_path:
                return False
            
            # Create subfolder for this file (e.g., CHP_12312 folder for CHP_12312.h5)
            folder_file_name = filename.split('.h5')[0]  # Get base name without extension
            file_export_path = os.path.join(exports_path, folder_file_name)
            
            # Create the subfolder if it doesn't exist
            if not os.path.exists(file_export_path):
                os.makedirs(file_export_path)
            
            # Create base path for BrainVision format (without extension)
            base_export_path = os.path.join(file_export_path, folder_file_name)
            
            # Export the raw data as BrainVision format (.eeg, .vhdr, .vmrk files)
            mne.export.export_raw(base_export_path + '.eeg', raw_data, overwrite=True)
            
            self.add_status_message(f"💾 Exported: {filename} → {folder_file_name}/ (BrainVision format)")
            logger.info(f"Successfully exported {filename} to BrainVision format at {base_export_path}")
            
            # Update the file list to show tick mark
            self.mark_exported_files()
            
            return True
            
        except Exception as e:
            error_msg = f"Failed to export {filename}: {str(e)}"
            self.add_status_message(f"❌ {error_msg}")
            logger.error(error_msg)
            return False
        
    def add_status_message(self, message):
        """Add a timestamped status message to the status text area."""
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_message = f"[{timestamp}] {message}"
        
        # Add to the status text
        current_text = self.status_text.toPlainText()
        if current_text == "Ready to open annotation windows. Status updates will appear here.":
            # Replace initial message
            self.status_text.setPlainText(formatted_message)
        else:
            # Append new message
            self.status_text.setPlainText(current_text + "\n" + formatted_message)
        
        # Auto-scroll to bottom
        cursor = self.status_text.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.status_text.setTextCursor(cursor)
        
        # Log the message as well
        logger.info(f"Status: {message}")
        
    def update_window_count(self):
        """Update the status with current open window count."""
        annotation_count = len(self.open_annotation_windows)
        log_count = len(self.open_log_windows)
        total_count = annotation_count + log_count
        
        if total_count == 0:
            status = "No windows currently open."
        else:
            status_parts = []
            if annotation_count > 0:
                status_parts.append(f"{annotation_count} annotation window{'s' if annotation_count != 1 else ''}")
            if log_count > 0:
                status_parts.append(f"{log_count} log viewer{'s' if log_count != 1 else ''}")
            
            status = " + ".join(status_parts) + " currently open."
        
        self.add_status_message(status)
        
    def open_log_viewer(self, log_data, filename):
        """Open a log viewer window for the given log data."""
        try:
            # Create and show log viewer window
            log_viewer = LogViewer(log_data, filename, self)
            log_viewer.show()
            
            # Track the log window
            self.open_log_windows[filename] = log_viewer
            
            # Update status
            log_count = len(log_data) if not log_data.empty else 0
            self.add_status_message(f"📊 Log viewer opened: {filename} ({log_count} entries)")
            
            logger.info(f"Log viewer opened for {filename} with {log_count} entries")
            return log_viewer
            
        except Exception as e:
            logger.error(f"Error opening log viewer for {filename}: {e}")
            self.add_status_message(f"❌ ERROR: Could not open log viewer for {filename}")
            return None
            
    def on_log_window_closed(self, filename):
        """Handle log viewer window closure."""
        try:
            if filename in self.open_log_windows:
                del self.open_log_windows[filename]
                self.add_status_message(f"📊 Log viewer closed: {filename}")
                self.update_window_count()
                logger.info(f"Log viewer tracking removed for: {filename}")
        except Exception as e:
            logger.error(f"Error handling log window closure for {filename}: {e}")
    
    def on_annotation_window_closed(self, filename):
        """Handle annotation window closure and export data if in review mode."""
        try:
            if filename in self.open_annotation_windows:
                window_info = self.open_annotation_windows[filename]
                
                # If this was a review window, export the data
                if window_info.get('mode') == 'review' and 'raw_data' in window_info:
                    self.add_status_message(f"💾 Exporting data for: {filename}")
                    success = self.create_export_for_file(filename, window_info['raw_data'])
                    if success:
                        self.add_status_message(f"✅ Export completed: {filename}")
                    else:
                        self.add_status_message(f"❌ Export failed: {filename}")
                
                # Remove from tracking
                del self.open_annotation_windows[filename]
                self.add_status_message(f"🔍 Annotation window closed: {filename}")
                self.update_window_count()
                logger.info(f"Annotation window tracking removed for: {filename}")
        except Exception as e:
            logger.error(f"Error handling annotation window closure for {filename}: {e}")
            self.add_status_message(f"❌ Error handling window closure for {filename}: {e}")
        
    def select_folder(self):
        """Open a dialog to select a data folder."""
        folder = QFileDialog.getExistingDirectory(
            self, 
            "Select Data Folder", 
            "", 
            QFileDialog.Option.ShowDirsOnly
        )
        
        if folder:
            self.selected_folder = folder
            self.folder_label.setText(f"Selected: {folder}")
            self.scan_for_files()
            logger.info(f"Selected folder: {folder}")
            
    def on_file_selection_changed(self):
        """Handle when files or folders are selected from the list."""
        selected_items = self.files_list.selectedItems()
        
        if not selected_items:
            # No selection - disable all buttons
            self.review_btn.setEnabled(False)
            self.annotate_btn.setEnabled(False)
            self.read_log_btn.setEnabled(False)
            self.parse_btn.setEnabled(False)
            return
        
        # Analyze selection to determine what buttons to show
        has_h5_files = False
        has_iom_folders = False
        mixed_selection = False
        
        # For .h5 files, also check export status
        ticked_h5_files = []
        unticked_h5_files = []
        
        for item in selected_items:
            selected_text = item.text()
            if selected_text.endswith(" (iom)"):
                has_iom_folders = True
            elif selected_text.endswith('.h5') or (selected_text.startswith("✓ ") and selected_text[2:].endswith('.h5')):
                has_h5_files = True
                # Check if file is ticked (exported)
                if selected_text.startswith("✓ "):
                    ticked_h5_files.append(selected_text)
                else:
                    unticked_h5_files.append(selected_text)
            
        # Check for mixed selection
        if has_h5_files and has_iom_folders:
            mixed_selection = True
        
        if mixed_selection:
            # Mixed selection - disable all buttons and show warning
            self.review_btn.setEnabled(False)
            self.annotate_btn.setEnabled(False)
            self.read_log_btn.setEnabled(False)
            self.parse_btn.setEnabled(False)
            self.add_status_message("⚠️ Mixed selection: Please select either .h5 files OR .iom folders, not both")
            logger.info("Mixed selection detected - disabling buttons")
            
        elif has_iom_folders and not has_h5_files:
            # Only .iom folders selected - show parse button
            if len(selected_items) > 1:
                # Multiple .iom folders - not supported yet
                self.review_btn.setVisible(False)
                self.annotate_btn.setVisible(False)
                self.read_log_btn.setVisible(False)
                self.parse_btn.setVisible(True)
                self.parse_btn.setEnabled(False)
                self.add_status_message("⚠️ Multiple .iom folder selection not yet supported")
            else:
                # Single .iom folder
                self.review_btn.setVisible(False)
                self.annotate_btn.setVisible(False)
                self.read_log_btn.setVisible(False)
                self.parse_btn.setVisible(True)
                self.parse_btn.setEnabled(True)
                logger.info(f"Selected .iom folder: {selected_items[0].text()}")
                
        elif has_h5_files and not has_iom_folders:
            # Only .h5 files selected - show review/annotate/read log buttons
            self.parse_btn.setVisible(False)
            self.review_btn.setVisible(True)
            self.annotate_btn.setVisible(True)
            self.read_log_btn.setVisible(True)
            self.read_log_btn.setEnabled(True)  # Always enable read log
            
            # Determine button availability based on export status
            if len(ticked_h5_files) > 0 and len(unticked_h5_files) > 0:
                # Mixed ticked/unticked selection - disable review and annotate
                self.review_btn.setEnabled(False)
                self.annotate_btn.setEnabled(False)
                self.add_status_message("⚠️ Mixed selection: Please select either exported (✓) OR non-exported files, not both")
                logger.info("Mixed ticked/unticked selection - disabling review and annotate buttons")
                
            elif len(ticked_h5_files) > 0 and len(unticked_h5_files) == 0:
                # Only ticked (exported) files selected - enable review, disable annotate
                self.review_btn.setEnabled(True)
                self.annotate_btn.setEnabled(False)
                if len(ticked_h5_files) == 1:
                    self.add_status_message(f"📊 Exported file selected: {ticked_h5_files[0]} - Review mode available")
                    logger.info(f"Selected exported .h5 file: {ticked_h5_files[0]}")
                else:
                    self.add_status_message(f"📊 {len(ticked_h5_files)} exported files selected - Review mode available")
                    logger.info(f"Selected {len(ticked_h5_files)} exported .h5 files")
                    
            elif len(unticked_h5_files) > 0 and len(ticked_h5_files) == 0:
                # Only unticked (non-exported) files selected - enable annotate, disable review
                self.review_btn.setEnabled(False)
                self.annotate_btn.setEnabled(True)
                if len(unticked_h5_files) == 1:
                    self.add_status_message(f"📝 Non-exported file selected: {unticked_h5_files[0]} - Annotation mode available")
                    logger.info(f"Selected non-exported .h5 file: {unticked_h5_files[0]}")
                else:
                    self.add_status_message(f"📝 {len(unticked_h5_files)} non-exported files selected - Annotation mode available")
                    logger.info(f"Selected {len(unticked_h5_files)} non-exported .h5 files")
            else:
                # No files selected somehow
                self.review_btn.setEnabled(False)
                self.annotate_btn.setEnabled(False)
                
        else:
            # No valid files selected
            self.review_btn.setEnabled(False)
            self.annotate_btn.setEnabled(False)
            self.read_log_btn.setEnabled(False)
            self.parse_btn.setEnabled(False)
            
    def reset_button_visibility(self):
        """Reset all buttons to default state when no specific file is selected."""
        # Show all buttons but disable them
        self.review_btn.setVisible(True)
        self.annotate_btn.setVisible(True)
        self.read_log_btn.setVisible(False)  # Hide by default
        self.parse_btn.setVisible(False)
        
        # Enable based on whether files were found
        has_files = len(self.found_files) > 0 or len(self.subfolder_iom_info) > 0
        self.review_btn.setEnabled(has_files)
        self.annotate_btn.setEnabled(has_files)
            
    def scan_for_files(self):
        """
        Scan the selected folder for .h5 and .iom files.
        Also scans subfolders (one level deep) for .iom files.
        """
        if not self.selected_folder:
            return
            
        # Clear previous results
        self.files_list.clear()
        self.found_files = []
        self.subfolder_iom_info = []
        
        # Look for .h5 and .iom files in main folder
        h5_files = glob.glob(os.path.join(self.selected_folder, '*.h5'))
        iom_files = glob.glob(os.path.join(self.selected_folder, '*.iom'))
        
        # Look for .iom files in subfolders (one level deep only)
        try:
            for item in os.listdir(self.selected_folder):
                item_path = os.path.join(self.selected_folder, item)
                if os.path.isdir(item_path):
                    # Check for .iom files in this subfolder
                    subfolder_iom_files = glob.glob(os.path.join(item_path, '*.iom'))
                    if subfolder_iom_files:
                        self.subfolder_iom_info.append({
                            'folder_name': item,
                            'iom_files': subfolder_iom_files
                        })
        except (PermissionError, OSError) as e:
            # Skip if we can't access subfolders
            logger.warning(f"Could not access some subfolders: {e}")
        
        self.found_files = h5_files + iom_files
        
        if self.found_files or self.subfolder_iom_info:
            # Update file list - add main folder files first
            for file_path in self.found_files:
                filename = os.path.basename(file_path)
                self.files_list.addItem(filename)
            
            # Add subfolder information
            for subfolder_info in self.subfolder_iom_info:
                folder_display = f"{subfolder_info['folder_name']} (iom)"
                self.files_list.addItem(folder_display)
            
            # Update info text
            h5_count = len(h5_files)
            iom_count = len(iom_files)
            subfolder_count = len(self.subfolder_iom_info)
            
            info_text = f"Found files in selected directory:\n"
            if h5_count > 0:
                info_text += f"• {h5_count} .h5 files\n"
            if iom_count > 0:
                info_text += f"• {iom_count} .iom files\n"
            if subfolder_count > 0:
                total_subfolder_iom = sum(len(info['iom_files']) for info in self.subfolder_iom_info)
                info_text += f"• {subfolder_count} subfolders with {total_subfolder_iom} .iom files\n"
            info_text += "\nSelect a file or folder from the list above to continue."
            self.info_text.setPlainText(info_text)
            
            # Reset buttons to default state
            self.reset_button_visibility()
            
            # Check for existing exports and mark files
            self.mark_exported_files()
            
            logger.info(f"Found {h5_count} .h5 files, {iom_count} .iom files, and {subfolder_count} subfolders with .iom files")
        else:
            self.info_text.setPlainText("No .h5 or .iom files found in the selected folder or its subfolders.")
            self.review_btn.setEnabled(False)
            self.annotate_btn.setEnabled(False)
            self.read_log_btn.setEnabled(False)
            self.parse_btn.setEnabled(False)
            logger.info("No files found in selected folder")
            
    def parse_files(self):
        """Handle parse functionality for .iom folders (placeholder)."""
        selected_items = self.files_list.selectedItems()
        if selected_items:
            selected_text = selected_items[0].text()
            folder_name = selected_text.replace(" (iom)", "")
            
            # Find the actual folder info
            folder_info = None
            for info in self.subfolder_iom_info:
                if info['folder_name'] == folder_name:
                    folder_info = info
                    break
            
            if folder_info:
                num_files = len(folder_info['iom_files'])
                QMessageBox.information(
                    self, 
                    "Parse Mode", 
                    f"Parse functionality will be implemented here.\n\n"
                    f"Selected folder: {folder_name}\n"
                    f"Contains {num_files} .iom file(s)\n\n"
                    f"This will convert .iom files to a suitable format for annotation."
                )
                logger.info(f"Parse mode activated for folder: {folder_name} with {num_files} .iom files")
            else:
                QMessageBox.warning(self, "Error", "Could not find folder information.")
        else:
            QMessageBox.warning(self, "Error", "No folder selected for parsing.")
        
    def review_files(self):
        """Handle review mode functionality for .h5 files - loads from exports folder."""
        selected_items = self.files_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Error", "No files selected for review.")
            return
        
        # Filter and validate selected files
        h5_files = []
        invalid_files = []
        
        for item in selected_items:
            filename = item.text()
            # Remove tick mark if present
            if filename.startswith("✓ "):
                filename = filename[2:]
            
            if filename.endswith('.h5'):
                h5_files.append(filename)
            else:
                invalid_files.append(filename)
        
        # Explicitly log files being opened for review
        print(f"\n🔍 REVIEW MODE STARTED: Opening {len(h5_files)} files for review")
        for filename in h5_files:
            print(f"  📂 {filename}")
        print("=" * 50)
        
        # Check for invalid file types
        if invalid_files:
            QMessageBox.warning(
                self, 
                "Invalid File Types", 
                f"Review is only available for .h5 files.\n\n"
                f"Invalid files selected:\n" + "\n".join(f"• {f}" for f in invalid_files) + 
                f"\n\nWill process {len(h5_files)} valid .h5 files."
            )
        
        if not h5_files:
            QMessageBox.warning(self, "Error", "No valid .h5 files selected for review.")
            return
        
        # Get exports folder path
        exports_path = self.ensure_exports_folder()
        if not exports_path:
            QMessageBox.critical(self, "Error", "Could not access exports folder.")
            return
        
        # Show confirmation for multiple files
        if len(h5_files) > 1:
            reply = QMessageBox.question(
                self,
                "Multiple Files",
                f"You have selected {len(h5_files)} .h5 files for review.\n\n"
                "This will load data from exports folder and open multiple review windows.\n"
                "Changes will be saved when windows are closed.\n\n"
                "Do you want to continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )
            if reply == QMessageBox.StandardButton.No:
                return
        
        # Process each file
        # successful_files = []
        failed_files = []
        
        self.add_status_message(f"🔄 Loading {len(h5_files)} file(s) from exports for review")
        
        for filename in h5_files:
            # try:
            # Get the base name for the export subfolder
            base_name = filename.replace('.h5', '')
            export_subfolder = os.path.join(exports_path, base_name)

            
            # Look for .vhdr file in the export subfolder
            vhdr_file = None
            if os.path.exists(export_subfolder):
                for file in os.listdir(export_subfolder):
                    if file.endswith('.vhdr'):
                        vhdr_file = os.path.join(export_subfolder, file)
                        break
            
            if not vhdr_file or not os.path.exists(vhdr_file):
                self.add_status_message(f"❌ ERROR: No .vhdr file found for {filename} in exports")
                failed_files.append(filename)
                continue
            
            self.add_status_message(f"🔄 Loading exported data for: {filename}")
            logger.info(f"Loading BrainVision data from: {vhdr_file}")
            
            # Load data using MNE BrainVision reader
            raw_data = mne.io.read_raw_brainvision(vhdr_file, preload=True)
            data = raw_data.load_data()  # Load data into memory
            
            # Store data instance in global array when file is opened
            self.opened_data_instances[filename] = data
            print(f"📝 STORED DATA INSTANCE: {filename}")
            
            self.add_status_message(f"📊 Opening review window for: {filename}")
            logger.info(f"Opening review window for exported file: {filename}")
            
            # Explicitly log opening this file for review
            print(f"🔍 OPENING FOR REVIEW: {filename}")
            
            # Register the window for tracking before opening
            self.register_filename_window(filename, f"MNE Browser - {filename}")
            
            # Use PyQt6 event loop to properly wait for window closure
            with mne.viz.use_browser_backend('qt'):
                # Get the figure and set up close event handling
                data.plot(time_format='clock', theme="light", block=False, precompute=False, title=filename)
            
        
        # Update window count and show summary
        self.update_window_count()
        
        
    def annotate_files(self):
        """Handle annotation mode functionality for .h5 files (supports multiple files)."""
        selected_items = self.files_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Error", "No files selected for annotation.")
            return
        
        # Filter and validate selected files
        h5_files = []
        invalid_files = []
        
        for item in selected_items:
            filename = item.text()
            # Remove tick mark if present
            if filename.startswith("✓ "):
                filename = filename[2:]
            
            if filename.endswith('.h5'):
                h5_files.append(filename)
            else:
                invalid_files.append(filename)
        
        # Check for invalid file types
        if invalid_files:
            QMessageBox.warning(
                self, 
                "Invalid File Types", 
                f"Annotation is only available for .h5 files.\n\n"
                f"Invalid files selected:\n" + "\n".join(f"• {f}" for f in invalid_files) + 
                f"\n\nWill process {len(h5_files)} valid .h5 files."
            )
        
        if not h5_files:
            QMessageBox.warning(self, "Error", "No valid .h5 files selected for annotation.")
            return
        
        # Show confirmation for multiple files
        if len(h5_files) > 1:
            reply = QMessageBox.question(
                self,
                "Multiple Files",
                f"You have selected {len(h5_files)} .h5 files for annotation.\n\n"
                "This will open multiple annotation windows simultaneously.\n\n"
                "Do you want to continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )
            if reply == QMessageBox.StandardButton.No:
                return
        
        # Process each file
        successful_files = []
        failed_files = []
        
        self.add_status_message(f"🔄 Starting annotation for {len(h5_files)} file(s)")
        
        for filename in h5_files:
            file_path = os.path.join(self.selected_folder, filename)
            
            # Verify file exists
            if not os.path.exists(file_path):
                self.add_status_message(f"❌ ERROR: File not found - {filename}")
                failed_files.append(filename)
                continue
            
            self.add_status_message(f"🔄 Opening annotation window for: {filename}")
            logger.info(f"Starting annotation for file: {file_path}")
            
            # Create IOM_file instance and load data
            iom_file = IOM_file(file_path)
            iom_file.read_data()
            
            
            # Check if EEG data is present
            if not iom_file.is_eeg_present:
                self.add_status_message(f"❌ ERROR: No EEG data found in {filename}")
                failed_files.append(filename)
                continue
            
            # Plot EEG data (this will block until window is closed)
            logger.info(f"Plotting EEG data for file: {filename}")
            
            # Register the window for tracking before opening
            self.register_filename_window(filename, f"MNE Browser - {filename}")
            
            raw_data, start_time, channels = iom_file.plot_eeg(title=filename, block=False)
            self.add_status_message(f"Offset hours : {iom_file.offset_hours}")

            # Store data instance in global array when annotation window closes
            self.opened_data_instances[filename] = raw_data
            print(f"📝 STORED DATA INSTANCE: {filename}")
            
            self.add_status_message(f"📊 Opening annotation window for: {filename}")
            logger.info(f"Opening annotation window for exported file: {filename}")

            # Explicitly log opening this file for annotation
            print(f"🔍 OPENING FOR ANNOTATION: {filename}")
        
        # Update window count and show summary
        self.update_window_count()
        
        # Show summary message
        if successful_files and failed_files:
            summary = f"✅ {len(successful_files)} files opened successfully\n❌ {len(failed_files)} files failed"
        elif successful_files:
            summary = f"✅ All {len(successful_files)} files opened successfully"
        else:
            summary = f"❌ All {len(failed_files)} files failed to open"
        
        self.add_status_message(f"📊 Summary: {summary}")
        logger.info(f"Multi-file annotation complete: {len(successful_files)} success, {len(failed_files)} failed")
    
    def read_log_files(self):
        """Handle reading and displaying log data from selected .h5 files."""
        selected_items = self.files_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Error", "No files selected for log reading.")
            return
        
        # Filter and validate selected files
        h5_files = []
        invalid_files = []
        
        for item in selected_items:
            filename = item.text()
            # Remove tick mark if present
            if filename.startswith("✓ "):
                filename = filename[2:]
            
            if filename.endswith('.h5'):
                h5_files.append(filename)
            else:
                invalid_files.append(filename)
        
        # Check for invalid file types
        if invalid_files:
            QMessageBox.warning(
                self, 
                "Invalid File Types", 
                f"Log reading is only available for .h5 files.\n\n"
                f"Invalid files selected:\n" + "\n".join(f"• {f}" for f in invalid_files) + 
                f"\n\nWill process {len(h5_files)} valid .h5 files."
            )
        
        if not h5_files:
            QMessageBox.warning(self, "Error", "No valid .h5 files selected for log reading.")
            return
        
        # Show confirmation for multiple files
        if len(h5_files) > 1:
            reply = QMessageBox.question(
                self,
                "Multiple Files",
                f"You have selected {len(h5_files)} .h5 files for log reading.\n\n"
                "This will open multiple log viewer windows.\n\n"
                "Do you want to continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )
            if reply == QMessageBox.StandardButton.No:
                return
        
        # Process each file
        successful_files = []
        failed_files = []
        no_log_files = []
        
        self.add_status_message(f"🔄 Reading log data from {len(h5_files)} file(s)")
        
        for filename in h5_files:
            try:
                file_path = os.path.join(self.selected_folder, filename)
                
                # Verify file exists
                if not os.path.exists(file_path):
                    self.add_status_message(f"❌ ERROR: File not found - {filename}")
                    failed_files.append(filename)
                    continue
                
                self.add_status_message(f"🔄 Reading log data from: {filename}")
                logger.info(f"Reading log data from file: {file_path}")
                
                # Create IOM_file instance and load data
                iom_file = IOM_file(file_path)
                iom_file.read_data()
                
                # Check for log data and open log viewer if available
                if hasattr(iom_file, 'log') and not iom_file.log.empty:
                    self.open_log_viewer(iom_file.log, filename)
                    self.add_status_message(f"✅ Log viewer opened: {filename}")
                    successful_files.append(filename)
                    logger.info(f"Successfully opened log viewer for: {filename}")
                else:
                    self.add_status_message(f"⚠️ No log data found in: {filename}")
                    no_log_files.append(filename)
                    logger.info(f"No log data available in file: {filename}")
                    
            except PermissionError:
                logger.error(f"Permission denied for file: {file_path}")
                self.add_status_message(f"❌ ERROR: Permission denied - {filename}")
                failed_files.append(filename)
                
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Error reading log from file {file_path}: {error_msg}")
                self.add_status_message(f"❌ ERROR: Log reading failed - {filename} ({error_msg})")
                failed_files.append(filename)
        
        # Update window count 
        self.update_window_count()
        
        # Show detailed summary message
        summary_parts = []
        if successful_files:
            summary_parts.append(f"✅ {len(successful_files)} log viewers opened")
        if no_log_files:
            summary_parts.append(f"⚠️ {len(no_log_files)} files had no log data")
        if failed_files:
            summary_parts.append(f"❌ {len(failed_files)} files failed")
        
        if summary_parts:
            summary = " | ".join(summary_parts)
        else:
            summary = "No files processed"
        
        self.add_status_message(f"📊 Log Reading Summary: {summary}")
        logger.info(f"Log reading complete: {len(successful_files)} success, {len(no_log_files)} no data, {len(failed_files)} failed")