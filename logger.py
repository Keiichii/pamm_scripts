import logging
import logging.handlers


# Create logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
states = {'DEBUG': 10, 'INFO': 20, 'WARNING': 30, 'ERROR': 40, 'CRITICAL': 50}



def create_con_logger(level):
    'levels: DEBUG, INFO, WARNING, ERROR, CRITICAL'
    # Create handlers
    con_handler = logging.StreamHandler()     # to console
    con_handler.setLevel(level)

    # Create formatters and add it to handlers
    c_format = logging.Formatter('%(message)s')
    con_handler.setFormatter(c_format)

    # Add handlers to the logger
    logger.addHandler(con_handler)

def create_file_logger(level, log_file):
    # Create handlers
    file_handler = logging.handlers.RotatingFileHandler(log_file, maxBytes=1000000, backupCount=2)
    file_handler.setLevel(level)

    # Create formatters and add it to handlers
    f_format = logging.Formatter('\n%(asctime)s - %(levelname)s - %(message)s', '%d/%m/%Y %H:%M:%S')
    file_handler.setFormatter(f_format)

    # Add handlers to the logger
    logger.addHandler(con_handler)
    logger.addHandler(file_handler)