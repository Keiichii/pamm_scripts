import argparse
import requests
import json
from time import sleep, time, ctime
import logger


#Repo changes

deal_type = '0'
comment = 'Zabbix test deal'
base_req = {"jsonrpc":"2.0", "id":"null"}
check_result = None
pos_file = ''

ma_pos_data = {}
ia_pos_data = {}


def request(url, method, header, params):
	result = error = None
	data = base_req
	data['method'] = method
	data['params'] = params
	try:
		response = requests.post(f'http://{url}/dx', data=json.dumps(data), headers=header, timeout=30)
	except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
		error = f'Cannot connect: {e}'
	except Exception as e:
		error = f'Exception: {e}'
	else:
		data = response.json()
		if 'result' in data:
			result = data['result']
		elif 'error' in data:
			error = data['error']
			if error.get('message') == 'access token not found':
				error = 'Cannot connect, access token not found.'
	return result, error


def open_MA_pos(url, header, ma_login, symbol, deal_type, lot, comment=''):
	'Returns {data} of opened pos'
	params = {"login":ma_login, "symbol": symbol, "type": deal_type, "lot": lot, "comment": comment}
	ma_pos, error = request(url=url, method='pos.open', header=header, params=params)
	return ma_pos, error


def close_MA_pos(url, header, ma_login, ma_pos_id, logger):
	result = False
	params = {"login": ma_login, 'pos_id': ma_pos_id}
	ma_pos_close, error = request(url=url, method='pos.close', header=header, params=params)
	if error:
		msg = f"Error closing MA position: {error}"
		error_info(msg=msg, url=url, ma_login=ma_login, result='WARNING', ma_pos_id=ma_pos_id, logger=logger)
	elif ma_pos_close:
		logger.info(f'MA Position closed with message: {ma_pos_close}')
		result = True
	else:
		result = True
	return result


def find_pose(url, header, ma_login, ia_login, ma_pos_id, logger, log=True, test_close=False, master=False):
	if master: acc = 'Master'
	else: acc = 'Inverstor'
	global ma_pos_data, ia_pos_data
	found = False
	params = {"login": ia_login}
	data, error = request(url=url, method='acc.pos', header=header, params=params)
	if error and log:
		msg = f"Error getting {acc} positions: {error}"
		error_info(msg=msg, url=url, ma_login=ma_login, ia_login=ia_login, result='WARNING', logger=logger)
	elif data:
		list_of_poses = data.get('poss')
		if not test_close:
			if not list_of_poses and log:
				msg = f'List of {acc} posses is empty'
				if master: error_info(msg=msg, url=url, ma_login=ma_login, ia_login=ia_login, result='WARNING', logger=logger)
				else: error_info(msg=msg, url=url, ma_login=ma_login, ia_login=ia_login, result='FAILED', logger=logger)
			else:
				for pos in list_of_poses:
					if not master:
						ia_pos = pos.get('ma').get('pos_id')
						if ia_pos == ma_pos_id:
							found = True
							ia_pos_data = pos
							break
					else:
						cur_pos = pos.get('pos_id')
						if cur_pos == ma_pos_id:
							found = True
							print(pos)
							ma_pos_data = pos
							print(ma_pos_data)
						else:
							#close all other positions
							ma_pos_close = close_MA_pos(url=url, header=header, ma_login=ma_login, ma_pos_id=cur_pos, logger=logger)		# Bool
				if not found and log:
					if master: msg = 'Error: no saved position found on Master'
					else: msg = 'Error: no copied position found on Investor'
					error_info(msg=msg, url=url, ma_login=ma_login, ia_login=ia_login, result='FAILED', ma_pos_id=ma_pos_id, logger=logger)
		else:
			if list_of_poses:
				for pos in list_of_poses:
					if pos.get('ma').get('pos_id') == ma_pos_id and log:
						found = True
						msg = 'ERROR - Pose found in investor, it hasnt been closed with master position.'
						error_info(msg=msg, url=url, ma_login=ma_login, ia_login=ia_login, result='FAILED', ma_pos_id=ma_pos_id, logger=logger)
						break
	return found


def error_info(logger, msg=None, url=None, ma_login=None, ia_login=None, result=None, ma_pos_id=None):
	if msg: logger.error(msg)
	if ma_login: logger.error(f'Master acc: {ma_login}')
	if ma_pos_id: logger.error(f'Master position: {ma_pos_id}')
	if ia_login: logger.error(f'Investor acc: {ia_login}')
	if url: logger.error(f"Service port: {url.split(':')[-1]}")
	if result: logger.error(f'Copy test: {result}')


def write_pos(position_number):
	with open(pos_file, 'w') as f:
		f.write(str(position_number))


def read_pos(logger):
	try:
		with open(pos_file, 'r') as f:
			position_number = f.read()
	except FileNotFoundError:
		logger.info('File with pos id not found')
		return False
	else:
		return int(position_number) if position_number else False


def compare_time(ma_login, ia_login, ma_pose, ia_pose, flag, logger, url=None, header=None):
	if flag == 'open':
		print(ma_pose)
		ma_open_pos_time = ma_pose.get('time_create')
		ia_open_pos_time = ia_pose.get("time_create")
		diff = ia_open_pos_time - ma_open_pos_time
		if diff > 3:
			msg = f'Time difference between MA pos and IA positions OPEN times: {diff} sec.'
			error_info(msg=msg, url=url, ma_login=ma_login, ia_login=ia_login, result='TIME WARNING', logger=logger, ma_pos_id=ma_pose.get('order'))
	else:
		ma_pos_id = ma_pose.get('pos_id')
		ia_pos_id = ia_pose.get('pos_id')
		def found_pos(login, pos_id):
			found = False
			offset = 0
			limit = 1
			while not found:
				params = {"login": login, "close_time": True, "limit": limit, 'offset': offset}
				ma_data, error = request(url=url, method='acc.pos', header=header, params=params)
				ma_closed_poses = ma_data.get('poss')
				if ma_closed_poses:
					for pos in ma_closed_poses:
						if pos.get('pos_id') == pos_id:
							pos_close_time = pos.get('time_close')
							return pos_close_time
					offset += 101
					limit = 101
				else:
					break
		ma_pos_close_time = found_pos(ma_login, ma_pos_id)
		ia_pos_close_time = found_pos(ia_login, ia_pos_id)
		if ma_pos_close_time and ia_pos_close_time:
			diff = ia_pos_close_time - ma_pos_close_time
			if diff > 3:
				msg = f'Time difference between MA pos and IA positions CLOSE times: {diff} sec.'
				error_info(msg=msg, url=url, ma_login=ma_login, ia_login=ia_login, result='TIME WARNING', logger=logger, ma_pos_id=ma_pos_id)
		else:
			msg = f'Cant get time: ma_pos_close_time={ma_pos_close_time}, ia_pos_close_time={ia_pos_close_time}.'
			error_info(msg=msg, url=url, ma_login=ma_login, ia_login=ia_login, result='WARNING', logger=logger, ma_pos_id=ma_pos_id)	


def open_pos_and_check(args, logger, header, url, ma_login):
	#Open pos
	ma_pos, error = open_MA_pos(url=url, header=header, ma_login=ma_login, symbol=args.Symbol, deal_type=deal_type, lot=args.Lot, comment=comment)
	global ma_pos_data
	if error:
		msg = f'Error opening Master position: {error}'
		error_info(msg=msg, url=url, ma_login=ma_login, result='FAILED', logger=logger)
	elif ma_pos:
		ma_pos_id = ma_pos.get('order')
		if not ma_pos_id:
			msg = 'Cannot get Master position ID'
			error_info(msg=msg, url=url, ma_login=ma_login, result='FAILED', logger=logger)
		else:
			write_pos(ma_pos_id)
			for _ in range(int(args.Wait) // 2):
				#Waiting for coping positions
				sleep(2)
				#2 Find investor's Poses linked to MA
				ia_pose = find_pose(url=url, header=header, ma_login=ma_login, ia_login=args.IA_login, ma_pos_id=ma_pos_id, log=False, logger=logger)		# Bool
				if ia_pose:
					break
			else:
				ia_pose = find_pose(url=url, header=header, ma_login=ma_login, ia_login=args.IA_login, ma_pos_id=ma_pos_id, logger=logger)		# Bool
			if not ia_pose:
				ma_pos_close = close_MA_pos(url=url, header=header, ma_login=ma_login, ma_pos_id=ma_pos_id, logger=logger)		# Bool
				write_pos('')
			else:
				ma_pose = find_pose(url=url, header=header, ma_login=ma_login, ia_login=ma_login, ma_pos_id=ma_pos_id, master=True, log=False, logger=logger)		# Bool
				compare_time(ma_login=ma_login, ia_login=args.IA_login, ma_pose=ma_pos_data, ia_pose=ia_pos_data, flag='open', logger=logger, url=url)


def close_pos_and_check(args, logger, header, url, ma_login, ma_pos_id):
	#Close MA Pos
	ma_pos_close = close_MA_pos(url=url, header=header, ma_login=ma_login, ma_pos_id=ma_pos_id, logger=logger)		# Bool
	write_pos('')
	if ma_pos_close:
		for _ in range(int(args.Wait) // 2):
			sleep(2)
			ia_pose = find_pose(url=url, header=header, ma_login=ma_login, ia_login=args.IA_login, ma_pos_id=ma_pos_id, test_close=True, log=False, logger=logger)		# Bool
			if not ia_pose:
				break
		else:
			ia_pose = find_pose(url=url, header=header, ma_login=ma_login, ia_login=args.IA_login, ma_pos_id=ma_pos_id, test_close=True, logger=logger)		# Bool
		if not ia_pose:
			compare_time(ma_login=ma_login, ia_login=args.IA_login, ma_pose=ma_pos_data, ia_pose=ia_pos_data, flag='close', url=url, header=header, logger=logger)


def main(args, logger):
	global ma_pos_data, ia_pos_data, pos_file
	header = {'ManagerPass': args.ManagerPass}
	url = args.Server
	ma_login = args.MA_login
	pos_file = f'c:\\scripts\\copy_test_pos_{ma_login}.txt'
	ma_pos_id = read_pos(logger)
	if not ma_pos_id:			# A - if no opened position
		open_pos_and_check(args=args, logger=logger, header=header, url=url, ma_login=ma_login)
	else: 						# B ma_opened position exist
		ma_pose = find_pose(url=url, header=header, ma_login=ma_login, ia_login=ma_login, ma_pos_id=ma_pos_id, master=True, log=False, logger=logger)		# Bool
		ia_pose = find_pose(url=url, header=header, ma_login=ma_login, ia_login=args.IA_login, ma_pos_id=ma_pos_id, log=False, logger=logger)		# Bool
		if ma_pose and ia_pose:
			close_pos_and_check(args=args, logger=logger, header=header, url=url, ma_login=ma_login, ma_pos_id=ma_pos_id)
		else:
			ma_pos_close = close_MA_pos(url=url, header=header, ma_login=ma_login, ma_pos_id=ma_pos_id, logger=logger)		# Bool
			write_pos('')
			open_pos_and_check(args=args, logger=logger, header=header, url=url, ma_login=ma_login)


if __name__ == "__main__":
	parser = argparse.ArgumentParser(description='Tests PAMM services with copying deals')
	parser.add_argument('Server', help='IP:port')
	parser.add_argument('ManagerPass', help='PAMM manager password')
	parser.add_argument('MA_login', help='MT Master login')
	parser.add_argument('IA_login', help='MT Investor login')
	parser.add_argument('Wait', help='Wait for copy deal, sec')
	parser.add_argument('Symbol', help='Symbol, default is XRPUSD')
	parser.add_argument('Lot', help='Lot size, default is 1 for XRPUSD')

	args = parser.parse_args()
	logger.create_con_logger('INFO')
	main(args, logger.logger)