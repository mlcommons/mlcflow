from colorama import Fore, Style, init as colorama_init
import logging
import os

# Initialize colorama for Windows support
colorama_init(autoreset=True)

class ColoredFormatter(logging.Formatter):
    """Custom formatter class to add colors to log levels"""
    COLORS = {
        'INFO': Fore.GREEN,
        'DEBUG': Fore.CYAN + Style.DIM,
        'WARNING': Fore.YELLOW,
        'ERROR': Fore.RED
    }

    def format(self, record):
        # Pad filename and line number for alignment
        record.filename = f"{record.filename:<15}"  # Left-align filename with 15 char width
        record.lineno = f"{record.lineno:>4}"  # Right-align line number with 4 char width
        
        # Trim WARNING to WARN
        levelname = "WARN" if record.levelname == "WARNING" else record.levelname
        
        # Pad and add color to the levelname
        levelname_padded = f"{levelname:<5}"  # Left-align levelname with 5 char width
        if record.levelname in self.COLORS:
            record.levelname = f"{self.COLORS[record.levelname]}{levelname_padded}{Style.RESET_ALL}"
        else:
            record.levelname = levelname_padded
        return super().format(record)


# Set up logging configuration
def setup_logging(log_path = os.getcwd(), log_file = '.mlc-log.txt'):
    
    if not logger.hasHandlers():
        logFormatter = ColoredFormatter('[%(asctime)s %(filename)s:%(lineno)s %(levelname)s] - %(message)s')
        # by default logging level is set to INFO is being set
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
