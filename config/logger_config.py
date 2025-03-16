import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("cursor_project_creator.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)
