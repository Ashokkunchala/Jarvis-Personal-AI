#!/usr/bin/env python
\"\"\"Run the enhanced JARVIS server.\"\"\"
import uvicorn
from app.core.config import get_settings

if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "app.main_enhanced:app",
        host=settings.host,
        port=settings.port,
        reload=settings.environment == "development",
        log_level="info",
    )
