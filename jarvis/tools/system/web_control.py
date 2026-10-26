import logging
import webbrowser
from urllib.parse import urlparse

from jarvis.config.settings import config

logger = logging.getLogger("jarvis.tools.web")


def open_website(url: str):
    """Open a website"""
    try:
        # Add https if missing
        if not url.startswith('http://') and not url.startswith('https://'):
            url = 'https://' + url

        parsed = urlparse(url)
        if parsed.scheme not in ['http', 'https']:
            raise ValueError("Only HTTP/HTTPS URLs allowed")

        # Check allowed domains
        if config.require_confirmation:
            # Will be confirmed by registry
            pass

        webbrowser.open(url, new=2)
        logger.info(f"Opened website: {url}")
        return f"Opened {url}"
    except Exception as e:
        logger.error(f"Failed to open website {url}: {e}")
        raise
