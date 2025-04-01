from colorama import Fore, Style, init as colorama_init
import logging
import os

# Initialize colorama for Windows support
colorama_init(autoreset=True)

class ColoredFormatter(logging.Formatter):
    """Custom formatter class to add colors to log levels"""
    COLORS = {
        'INFO': Fore.GREEN,
        'WARNING': Fore.YELLOW,
        'ERROR': Fore.RED
    }

    def format(self, record):
        # Add color to the levelname
        if record.levelname in self.COLORS:
            record.levelname = f"{self.COLORS[record.levelname]}{record.levelname}{Style.RESET_ALL}"
        return super().format(record)


# Set up logging configuration
def setup_logging(log_path = os.getcwd(),log_file = 'mlc-log.txt'):
    
    if not logger.hasHandlers():
        logFormatter = ColoredFormatter('[%(asctime)s %(filename)s:%(lineno)d %(levelname)s] - %(message)s')
        logger.setLevel(logging.INFO)
   

        # File hander for logging in file in the specified path
        file_handler = logging.FileHandler("{0}/{1}".format(log_path, log_file))
        file_handler.setFormatter(logging.Formatter('[%(asctime)s %(filename)s:%(lineno)d %(levelname)s] - %(message)s'))
        logger.addHandler(file_handler)
    
        # Console handler for logging on console
        consoleHandler = logging.StreamHandler()
        consoleHandler.setFormatter(logFormatter)
        logger.addHandler(consoleHandler)
        logger.propagate = False

logger = logging.getLogger(__name__)
