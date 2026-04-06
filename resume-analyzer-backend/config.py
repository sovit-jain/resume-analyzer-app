import logging
import os
from dotenv import load_dotenv

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def configure_logging() -> None:
    level = getattr(logging, LOG_LEVEL, logging.INFO)
    root_logger = logging.getLogger()

    if not root_logger.handlers:
        logging.basicConfig(level=level, format=LOG_FORMAT)
    else:
        root_logger.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)


configure_logging()
logger = get_logger(__name__)
logger.info(
    "log-33 config.py | Configuration loaded | openai_api_key_present=%s log_level=%s",
    bool(OPENAI_API_KEY),
    LOG_LEVEL,
)

if __name__ == "__main__":
    logger.info("log-36 config.py | Config module executed directly.")