import datetime
import logging
import platform

import psutil

logger = logging.getLogger("jarvis.tools.system")


def get_time():
    """Get current time"""
    now = datetime.datetime.now()
    return {
        "time": now.strftime("%I:%M:%S %p"),
        "date": now.strftime("%A, %B %d, %Y"),
        "iso": now.isoformat()
    }


def get_system_info():
    """Get system information"""
    try:
        return {
            "platform": platform.system(),
            "platform_release": platform.release(),
            "processor": platform.processor(),
            "cpu_count": psutil.cpu_count(),
            "memory_total_gb": round(psutil.virtual_memory().total / (1024**3), 2),
            "memory_percent": psutil.virtual_memory().percent
        }
    except Exception as e:
        logger.error(f"Failed to get system info: {e}")
        raise
