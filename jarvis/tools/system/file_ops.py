import logging
import os

logger = logging.getLogger("jarvis.tools.files")


def open_file(path: str):
    """Open a file"""
    try:
        if not os.path.exists(path):
            raise FileNotFoundError(f"File not found: {path}")
        os.startfile(path)
        logger.info(f"Opened file: {path}")
        return f"Opened {path}"
    except Exception as e:
        logger.error(f"Failed to open file {path}: {e}")
        raise


def list_files(directory: str = "."):
    """List files in directory"""
    try:
        files = os.listdir(directory)
        return files
    except Exception as e:
        logger.error(f"Failed to list files: {e}")
        raise
