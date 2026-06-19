import sys
import logging
import matplotlib
from PyQt6.QtWidgets import QApplication

# Local imports
from gui import AnnotationTool
from utils import setup_logging

matplotlib.use('QtAgg')

def main():
    """
    Main entry point for the TRACER Seizure Annotation Tool.
    
    Sets up logging and launches the GUI application.
    """
    # Set up logging
    logger = setup_logging()
    logger.info("TRACER Annotation Tool started")

    # Create and run the GUI application
    app = QApplication(sys.argv)
    window = AnnotationTool()
    window.show()
    
    logger.info("GUI application launched")
    sys.exit(app.exec())

if __name__ == "__main__":
    main()