from time import sleep, time, ctime
start_time = time()

import argparse
import requests
import json
from logger import logger, create_con_logger, states


deal_type = '0'     #0 = buy; 1 = sell
comment = 'Zabbix test deal'
base_request = {"jsonrpc":"2.0", "id":"null"}
ma_pos_data = {}
ia_pos_data = {}
error_log = {'msgs': [],}	# [(status, text),], status, additional info


def check_runtime():
	'returns False if no free time left (<2 sec)'
	time_left = args.Timeout - (time() - start_time)
	if time_left < 2:
		add_log('ERROR', 'Script timeout! Please, check logs.')
		return False
	else:
		return True


def add_log(status, msg):
	'''add (status, msg) to error log list.

	statuses: DEBUG, INFO, WARNING, ERROR, CRITICAL'''
	error_log['msgs'].append((status, msg))


def report(debug, result):
	'send error report with additional info to logger'
	#set report level
	if debug:
		create_con_logger('DEBUG')		# report ALL
	elif result == 'FAILED' or result == 'FAILED - BALANCE':
		create_con_logger('INFO')		# test FAILED, report main steps and errors
	else:									
		create_con_logger('WARNING')	# test PASSED, report only warnings
	#add general test result
	if result == 'WARNING' or result == 'TIME WARNING':
		add_log('WARNING', f'Copy test: {result}')
	else:
		add_log('INFO', f'Copy test: {result}')
	#report all messages from queue
	for msg in error_log['msgs']:
		m_state, m_text = msg
		if (m_state == 'REQUEST' and args.request) or (m_state == 'DATA' and args.data):
			m_state = 'WARNING'
		elif m_state == 'REQUEST' or m_state == 'DATA':
			continue
		logger.log(states[m_state], m_text)


def request(method, params):
	'''return result from response[result]
	
	or return TIMEOUT if timeout'''
	if not check_runtime():
		return 'TIMEOUT'
	result = None
	header = {'ManagerPass': args.ManagerPass}
	data = base_request
	data['method'] = method
	data['params'] = params
	add_log('REQUEST', f'    >>> request header: {header}')
	add_log('REQUEST', f'    >>> request data: {data}')
	try:
		s = time()
		response = requests.post(f'http://{args.Server}/dx', data=json.dumps(data), headers=header, timeout=args.Timeout-2)
	except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
		add_log('WARNING', f'    Cannot connect to service: {e}')
	except Exception as e:
		error = f'Connection exception: {e}'
	else:
		data = response.json()
		result = data.get('result')
		error = data.get("error")
		if error:
			add_log('WARNING', f'    Request returned error: {error}')
		#special case for 'pos.close' because it return empty 'result' if ok, and return 'error' if any
		if method == 'pos.close' and not error:
			result = True
	finally:
		add_log('DEBUG', f'    >>> time for request {method} = {time()-s}')
	return result


def close_pos(ma_pos_id):
	'close MA pos and return True if ok, or TIMEOUT if timeout'
	add_log('INFO', "Closing Master's position...")
	params = {"login": args.MA_login, 'pos_id': ma_pos_id}
	data = request(method='pos.close', params=params)
	add_log('DATA', f'    >>> response data for closing pos: {data}')
	return data


def close_other_poses(ma_pos_id):
	'close MA poses except inputed and return WARNING if timeout'
	add_log('INFO', "Closing all other Master's position...")
	params = {"login": args.MA_login}
	data = request(method='acc.pos', params=params)
	add_log('DATA', f'    >>> response data for closing pos: {data}')
	if data and isinstance(data, dict):
		poses = data.get('poss')
		if poses:
			add_log('DEBUG', f'    >>> number of poses: {len(poses)}')
			for pos in poses:
				pos_id = pos.get('pos_id')
				if pos_id != ma_pos_id:
					add_log('DEBUG', f"    >>> closing position {pos_id}")
					close_pos(pos_id)


def compare_time(closed=False):
	'Compare difference between MA and IA positions OPEN and CLOSE time and report if >3 sec'
	if closed:
		w = 'CLOSE'
		t = 'time_close'
	else:
		w = 'OPEN'
		t = 'time_create'
	add_log('INFO', f"Comparing {w} time between MA and IA positions...")
	ma_pos_time = ma_pos_data.get(t)
	ia_pos_time = ia_pos_data.get(t)
	diff = ia_pos_time - ma_pos_time
	add_log('DEBUG', f"    >>> {w} time between MA and IA positions = {diff} sec")
	if diff > 3:
		add_log('WARNING', f'    {w} time difference between MA and IA positions: {diff} sec.')
		return False
	elif diff < 0:
		add_log('WARNING', f'    {w} time difference between MA and IA positions is NEGATIVE: {diff} sec.')
		return False
	return True


def close_pos_and_check(ma_pos_id):
	'return test result: PASSED / FAILED / WARNING / TIME WARNING'
	#at first check that position exist on both acounts
	add_log('INFO', "***  Start fase B - close position test  ***")
	ma_pos = check_pos(args.MA_login, ma_pos_id, master=True)
	ia_pos = check_pos(args.IA_login, ma_pos_id)
	if not all((ma_pos, ia_pos)):
		add_log('ERROR', f"Searching for open position on {'master' if not ma_pos else 'investor'}...FAIL")
		return 'FAILED'
	elif ma_pos == 'TIMEOUT' or ia_pos == 'TIMEOUT':
		return 'WARNING'
	else:
		add_log('INFO', "Searching for open position on both accounts...OK")
		#close Master position
		result = close_pos(ma_pos_id)
		if not result:
			add_log('ERROR', f"Closing Master's position...FAIL")
			return 'FAILED'
		elif result == 'TIMEOUT':
			return 'WARNING'
		else:
			add_log('INFO', f"Closing Master's position...OK")
			#check that linked pos on investor closed too
			ma_pos = check_pos(args.MA_login, ma_pos_id, master=True, closed=True)
			ia_pos = check_pos(args.IA_login, ma_pos_id, closed=True)
			if not all((ma_pos, ia_pos)):
				add_log('ERROR', f"Searching for closed position on {'master' if not ma_pos else 'investor'}...FAIL")
				return 'FAILED'
			elif ma_pos == 'TIMEOUT' or ia_pos == 'TIMEOUT':
				return 'WARNING'
			else:
				add_log('INFO', "Searching for closed position on both accounts...OK")
				#compare close time between master and investor positions
				result = compare_time(closed=True)
				if not result:
					add_log('ERROR', 'Comparing CLOSE time between MA and IA positions...FAIL')
					return 'TIME WARNING'
				else:
					add_log('INFO', "Comparing CLOSE time between MA and IA positions...OK")
	return 'PASSED'


def check_pos(acc, pos_id, master=False, closed=False):
	'''search for pose on account and return True is found, and TIMEOUT if timeout
	
	also add pos data to global ma_pos_data & ia_pos_data'''
	global ia_pos_data, ma_pos_data
	x = 0
	add_log('INFO', f"Searching for position on {'Master' if master else 'Investor'}...")
	result = data = poses = None
	pos = {}
	params = {"login": acc}
	if closed:
		params.update({"close_time": True, "limit": 1, "offset": 0})
	while check_runtime() and x < 3 :
		data = request(method='acc.pos', params=params)
		if data == 'TIMEOUT':
			return data
		if data:
			poses = data.get('poss')
			if poses:
				for pos in poses:
					if master:
						ma_pos_id = pos.get('pos_id')
					else:
						ma_pos_id = pos.get('ma').get('pos_id')
					if pos_id == ma_pos_id:
						if master:
							ma_pos_data = pos
						else:
							ia_pos_data = pos
						result = True
						break
				if result:
					break
		sleep(1)		#wait between requests
		x += 1
	add_log('DATA', f'    >>> response data for searching pos: {data}')
	if not poses:
		add_log('ERROR', f'    list of {acc} posses is empty')
	if not result:
		if master:
			add_log('ERROR', f'    pos not found on master: {pos_id}')
		else:
			add_log('ERROR', f'    copied pos not found for ma pos: {pos_id}')
	else:
		add_log('DEBUG', f'    >>> pos found: {pos.get("pos_id")}')
		add_log('DATA', f'    >>> pos found: {pos}')
	return result


def open_ma_pos():
	'open MA pos and return pos id, and TIMEOUT if timeout'
	add_log('INFO', "Opening Master's position...")
	params = {"login": args.MA_login, "symbol": args.Symbol, "type": deal_type, "lot": args.Lot, "comment": comment}
	data = request(method='pos.open', params=params)
	add_log('DATA', f'    >>> response data for opening pos: {data}')
	if data == 'TIMEOUT':
		return data
	elif data and data.get('order'):
		add_log('DEBUG', f'    >>> MA pos #: {data["order"]}')
		return data['order']


def check_balances(accounts):
	'check balances of MA and IA and return True if both ok, and TIMEOUT if timeout'
	add_log('INFO', 'Checking accounts balances...')
	result = []
	for acc in accounts:
		params = {"login": acc, "as_my": True}
		data = request(method='acc.prop', params=params)
		add_log('DATA', f'    >>> response data for {acc}: {data}')
		if data == 'TIMEOUT':
			return data
		elif data:
			margin_free = data.get('acc').get('margin_free')
			add_log('DEBUG', f'    >>> acc {acc} has free margin = {margin_free}')
			if margin_free < 10:
				add_log('ERROR', f'    acc {acc} has not enough free margin = {margin_free} - ADD BALANCE!')
				result.append(False)
			else:
				result.append(True)
		else:
			result.append(False)
	return all(result)


def open_pos_and_check():
	'return test result: PASSED / FAILED / FAILED - BALANCE / WARNING / TIME WARNING'
	#check balances before open positions
	add_log('INFO', "***  Start fase A - open position test  ***")
	answer = ma_pos_id = None
	result = check_balances([args.MA_login, args.IA_login])
	if not result:
		add_log('ERROR', 'Checking accounts balances...FAIL')
		answer = 'FAILED - BALANCE'
	elif result == 'TIMEOUT':
		answer = 'WARNING'
	else:
		add_log('INFO', 'Checking accounts balances...OK')
		#open MA position
		ma_pos_id = open_ma_pos()
		if not ma_pos_id:
			add_log('ERROR', "Opening Master's position...FAIL")
			answer = 'FAILED'
		elif ma_pos_id == 'TIMEOUT':
			answer = 'WARNING'
		else:	
			add_log('INFO', "Opening Master's position...OK")
			#get master's position data
			found_ma = check_pos(args.MA_login, ma_pos_id, master=True)
			if not found_ma:
				add_log('ERROR', "Searching for open position on master...FAIL")
				answer = 'FAILED'
			elif found_ma == 'TIMEOUT':
				answer = 'WARNING'
			else:
				add_log('INFO', "Searching for open position on master...OK")
				#check that position was copied to investor
				found = check_pos(args.IA_login, ma_pos_id)
				if not found:
					add_log('ERROR', "Searching for open position on investor...FAIL")
					answer = 'FAILED'
				elif found == 'TIMEOUT':
					answer = 'WARNING'
				else:
					add_log('INFO', "Searching for open position on investor...OK")
					#write pos id to file for fase B
					write_pos(ma_pos_id)
					#compare open time between master and investor positions
					result = compare_time()
					if not result:
						add_log('ERROR', 'Comparing OPEN time between MA and IA positions...FAIL')
						answer = 'TIME WARNING'
					else:
						add_log('INFO', "Comparing OPEN time between MA and IA positions...OK")
	answer = 'PASSED'
	return answer, ma_pos_id


def read_pos():
	'return pos id from file'
	try:
		with open(pos_file, 'r') as f:
			pos_id = f.read()
	except FileNotFoundError:
		add_log('INFO', 'File with position id not found')
		return False
	except Exception as e:
		add_log('WARNING', f'Read pos id from file Exception: {e}')
		return False
	else:
		return int(pos_id) if pos_id else False


def write_pos(ma_pos_id):
	'write pos id to file, return True if ok'
	try:
		with open(pos_file, 'w') as f:
			f.write(str(ma_pos_id))
	except Exception as e:
		add_log('WARNING', f'Write pos id to file Exception: {e}')
		return False
	else:
		return True


def start_test():
	'return: PASSED / FAILED / FAILED - BALANCE / WARNING / TIME WARNING'
	# read file with position ID
	ma_pos_id = read_pos()
	add_log('DEBUG', f'>>> pos id from file: {ma_pos_id}')
	if not ma_pos_id:
		#fase A
		result, ma_pos_id = open_pos_and_check()
	else:
		#fase B
		result = close_pos_and_check(ma_pos_id)
		#clear pos id in file for fase A
		write_pos('')
		if result == 'FAILED':
			result, ma_pos_id = open_pos_and_check()
	#close all other positions
	if ma_pos_id:
		close_other_poses(ma_pos_id)
	return result


if __name__ == "__main__":
	parser = argparse.ArgumentParser(description='Tests PAMM services with copying deals')
	parser.add_argument('Server', help='IP:port')
	parser.add_argument('ManagerPass', help='Manager password')
	parser.add_argument('MA_login', help='MT Master login')
	parser.add_argument('IA_login', help='MT Investor login')
	parser.add_argument('Timeout', help='Timeout for copy deal, 5-30 sec', type=int, choices=range(5, 30), metavar='Timeout')
	parser.add_argument('Symbol', help='Symbol, default is XRPUSD')
	parser.add_argument('Lot', help='Lot size, default is 1 for XRPUSD, 0.01 for FX')
	parser.add_argument('--debug', help='Print all debug information', action='store_true')
	parser.add_argument('--request', help='Print all requests', action='store_true')
	parser.add_argument('--data', help='Print all data responses', action='store_true')
	args = parser.parse_args()
	
	pos_file = f'c:\\scripts\\copy_test_pos_{args.MA_login}.txt'

	result = start_test()

	report(args.debug, result)
	logger.debug(f'>>> Time: {time() - start_time}')