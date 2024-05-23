import os
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    filename='logfile.log', format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv('TOKEN')
MOUNT_POINT = os.getenv('MOUNT_POINT')
STORAGE_PATH = os.getenv('STORAGE_PATH')
BACKUP_FILE = os.getenv('BACKUP_FILE')
