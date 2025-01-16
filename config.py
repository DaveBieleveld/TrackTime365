from dotenv import load_dotenv
import logging
import os
from logging.handlers import TimedRotatingFileHandler

# Load environment variables from .env file
load_dotenv(override=True)

# Office 365 Configuration
CLIENT_ID = os.getenv('CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET')

# Database Configuration
DB_SERVER = os.getenv('DB_SERVER')
DB_NAME = os.getenv('DB_NAME')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')

# Application Settings
LOG_LEVEL = 'DEBUG'
SYNC_INTERVAL_MINUTES = int(os.getenv('SYNC_INTERVAL_MINUTES', '15'))
LOG_RETENTION_DAYS = int(os.getenv('LOG_RETENTION_DAYS', '7'))

# Logging Configuration
def setup_logging():
    # Create logs directory if it doesn't exist
    if not os.path.exists('logs'):
        os.makedirs('logs')

    # Configure logging
    logger = logging.getLogger('calendar_sync')
    logger.setLevel(getattr(logging, LOG_LEVEL.upper()))

    # File handler with rotation
    file_handler = TimedRotatingFileHandler(
        'logs/calendar_sync.log',
        when='midnight',
        interval=1,
        backupCount=LOG_RETENTION_DAYS
    )
    
    # Console handler
    console_handler = logging.StreamHandler()
    
    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

# Initialize logger
logger = setup_logging() 

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,  # Temporarily set to DEBUG
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join('logs', 'calendar_sync.log'))
    ]
) 