import os
import sys
import logging

def app_path(*parts):
    """
    Get the application path for files relative to the main executable or script.
    
    Args:
        *parts: Path components to join with the base path
        
    Returns:
        str: The full path to the requested file/directory
    """
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)   # folder containing main.exe
    else:
        base = os.path.abspath(os.path.dirname(__file__))
    return os.path.join(base, *parts)

def setup_logging(log_to_file=False, log_filename=None):
    """
    Set up logging configuration for the application.
    
    Args:
        log_to_file (bool): Whether to log to a file
        log_filename (str): Name of the log file (optional)
        
    Returns:
        logging.Logger: Configured logger instance
    """
    logger = logging.getLogger(__name__)
    
    try:
        if log_to_file and log_filename:
            logging.basicConfig(
                level=logging.INFO, 
                filename=log_filename, 
                filemode='a',
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
        else:
            logging.basicConfig(
                level=logging.INFO, 
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
        logger.info("Logging initialized successfully")
        return logger
    except Exception as e:
        print(f"Failed to set up logging: {e.__class__.__name__}: {e}")
        return logger

def ensure_directory_exists(directory_path):
    """
    Ensure that a directory exists, creating it if necessary.
    
    Args:
        directory_path (str): Path to the directory
        
    Returns:
        bool: True if directory exists or was created successfully
    """
    try:
        if not os.path.exists(directory_path):
            os.makedirs(directory_path)
            return True
        return True
    except OSError as e:
        print(f"Failed to create directory {directory_path}: {e}")
        return False