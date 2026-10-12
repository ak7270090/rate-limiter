import logging

import uvicorn

from ratelab.app import create_app
from ratelab.config import get_api_settings

if __name__ == "__main__":
    settings = get_api_settings()
    logging.basicConfig(level=settings.log_level.upper())
    uvicorn.run(
        create_app(settings), host=settings.host, port=settings.port, log_level=settings.log_level
    )
