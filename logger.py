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


def create_file_logger(level, log_file, logger=logger):
    'levels: DEBUG, INFO, WARNING, ERROR, CRITICAL'
    # Create handlers
    file_handler = logging.handlers.RotatingFileHandler(log_file, maxBytes=1000000, backupCount=2)
    file_handler.setLevel(level)

    # Create formatters and add it to handlers
    f_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', '%d/%m/%Y %H:%M:%S')
    file_handler.setFormatter(f_format)

    # Add handlers to the logger
    logger.addHandler(file_handler)
    logger.addHandler(file_handler)


def add_log(status, msg):
	'''add (status, msg) to error log list.

	statuses: DEBUG, INFO, WARNING, ERROR, CRITICAL'''
	error_log['msgs'].append((status, msg))


def report(debug, result):
	'''example reporter
    
    send error report with additional info to logger'''
	#set report level
	if debug:
		create_con_logger('DEBUG')		# report ALL
	elif result == 'FAILED' or result == 'BALANCE FAILED' or result == 'WARNING':
		create_con_logger('INFO')		# test FAILED, report main steps and errors
	else:									
		create_con_logger('WARNING')	# test PASSED, report only warnings
	add_log('WARNING', f'Copy test: {result}')
	#report all messages from queue
	for msg in error_log['msgs']:
		m_state, m_text = msg
		if (m_state == 'REQUEST' and args.request) or (m_state == 'DATA' and args.data) or (m_state == 'TIME' and args.time):
			m_state = 'WARNING'
		elif m_state == 'REQUEST' or m_state == 'DATA' or m_state == 'TIME':
			continue
		logger.log(states[m_state], m_text)