import argparse
import requests
import json
from time import sleep, time, ctime


deal_type = '0'
comment = 'Zabbix test deal'
base_req = {"jsonrpc":"2.0", "id":"null"}
check_result = None

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
		if method == 'pos.open':
			action = 'open master position'
		elif method == 'pos.close':
			action = 'close master position'
		elif method == 'acc.pos':
			action = 'list investor positions'
		print(f'Cannot connect for {action}:', e)
		error_info(url=url, result='WARNING')
	except Exception as e:
		error = e
	else:
		data = response.json()
		if 'result' in data:
			result = data['result']
		elif 'error' in data:
			error = data['error']
			if error.get('message') == 'access token not found':
				print('Cannot connect, access token not found.')
				error_info(url=url, result='WARNING')
				error = None
	return result, error


def open_MA_pos(url, header, ma_login, symbol, deal_type, lot, comment=''):
	'Returns {data} of opened pos'
	params = {"login":ma_login, "symbol": symbol, "type": deal_type, "lot": lot, "comment": comment}
	ma_pos, error = request(url=url, method='pos.open', header=header, params=params)
	if error:
		print('Error opening Master position:', error)
		error_info(url=url, ma_login=ma_login, result='FAILED')
	return ma_pos


def close_MA_pos(url, header, ma_login, ma_pos_id):
	result = False
	params = {"login": ma_login, 'pos_id': ma_pos_id}
	ma_pos_close, error = request(url=url, method='pos.close', header=header, params=params)
	if error:
		print("Error closing MA position:", error)
		error_info(url=url, ma_login=ma_login, result='WARNING', ma_pos_id=ma_pos_id)
	elif ma_pos_close:
		print('MA Position closed with message:', ma_pos_close)
		result = True
	else:
		result = True
	return result


def find_IA_pose(url, header, ma_login, ia_login, ma_pos_id, log=True, test_close=False, master=False):
	global ma_pos_data, ia_pos_data
	print('===== Inside find_IA_pose =====')
	found = False
	params = {"login": ia_login}
	ia_poses, error = request(url=url, method='acc.pos', header=header, params=params)
	if error and log:
		print("Error getting Investor positions:", error)
		error_info(url=url, ma_login=ma_login, ia_login=ia_login, result='WARNING')
	elif ia_poses:
		list_of_poses = ia_poses.get('poss')
		if not test_close:
			if not list_of_poses and log:
				print('List of investor posses is empty')
				error_info(url=url, ma_login=ma_login, ia_login=ia_login, result='FAILED')
			else:
				for pos in list_of_poses:
					if not master:
						ia_pos = pos.get('ma').get('pos_id')
						if ia_pos == ma_pos_id:
							found = True
							ia_pos_data = pos
							print('if ia_pose found => Compare time between poses...')
							break
					else:
						print('>>> Master flag enabled...')
						cur_pos = pos.get('pos_id')
						if cur_pos == ma_pos_id:
							print('cur_pos == ma_pos_id, FOUND')
							found = True
							ma_pos_data = pos
						else:
							print('cur_pos != ma_pos_id, closing this position:', cur_pos)
							ma_pos_close = close_MA_pos(url=url, header=header, ma_login=ma_login, ma_pos_id=cur_pos)		# Bool
							print('ma_pos_close:', ma_pos_close)
				if not found and log:
					print('Error: no copied position found on investor')
					error_info(url=url, ma_login=ma_login, ia_login=ia_login, result='FAILED', ma_pos_id=ma_pos_id)
		else:
			if not list_of_poses and log:
				print('List of investor posses is empty')
				error_info(url=url, ma_login=ma_login, ia_login=ia_login, result='PASSED')
			else:
				for pos in list_of_poses:
					if pos.get('ma').get('pos_id') == ma_pos_id and log:
						found = True
						print('ERROR - Pose found in List of investor posses')
						error_info(url=url, ma_login=ma_login, ia_login=ia_login, result='FAILED', ma_pos_id=ma_pos_id)
						break
				if not found and log:
					print('No copied position found on investor')
					error_info(url=url, ma_login=ma_login, ia_login=ia_login, result='PASSED', ma_pos_id=ma_pos_id)
	print('===== END of find_IA_pose =====')
	print('\n')
	return found


def error_info(url=None, ma_login=None, ia_login=None, result=None, ma_pos_id=None):
	if ma_login: print('Master acc:', ma_login)
	if ma_pos_id: print('Master position:', ma_pos_id)
	if ia_login: print('Investor acc:', ia_login)
	if url: print('Service port:', url.split(':')[-1])
	if result: print('Copy test:', result)


def write_pos(position_number):
	with open('copy_test_pos.txt', 'w') as f:
		f.write(str(position_number))


def read_pos():
	try:
		with open('copy_test_pos.txt', 'r') as f:
			position_number = f.read()
	except FileNotFoundError:
		print('File with pos id not found')
		return False
	else:
		return int(position_number) if position_number else False


def compare_time(ma_pose, ia_pose, flag, url=None, header=None):
	if flag == 'open':
		print('ma_pose', ma_pose)
		print('ia_pose', ia_pose)
		ma_open_pos_time = ma_pose.get('time')
		ia_open_pos_time = ia_pose.get("time_create")
		diff = ia_open_pos_time - ma_open_pos_time
		if diff > 3:
			print('Time difference between MA pos and IA positions OPEN times, sec:', diff)
			error_info(url=url, ma_login=ma_login, ia_login=ia_login, result='WARNING')
	else:
		ma_pos_id = ma_pose.get('pos_id')
		print('Searching for:', ma_pos_id)
		ia_pos_id = ia_pose.get('pos_id')
		ma_id = ma_pose.get('login')
		ia_id = ia_pose.get('login')
		def found_pos(login, pos_id):
			found = False
			offset = 0
			limit = 1
			print('\nstarting while')
			while not found:
				params = {"login": login, "close_time": True, "limit": limit, 'offset': offset}
				ma_data, error = request(url=url, method='acc.pos', header=header, params=params)
				ma_closed_poses = ma_data.get('poss')
				if ma_closed_poses:
					for pos in ma_closed_poses:
						if pos.get('pos_id') == pos_id:
							pos_close_time = pos.get('time_close')
							found = True
							print(pos)
							break
					offset += 101
					print('offset', offset)
					limit = 101
				else:
					break
			return pos_close_time
		ma_pos_close_time = found_pos(ma_id, ma_pos_id)
		ia_pos_close_time = found_pos(ia_id, ia_pos_id)
		diff = ia_pos_close_time - ma_pos_close_time
		if diff > 3:
			print('Time difference between MA pos and IA positions CLOSE times, sec:', diff)
			error_info(url=url, ma_login=ma_login, ia_login=ia_login, result='WARNING')


def main(args):
	global ma_pos_data, ia_pos_data
	header = {'ManagerPass': args.ManagerPass}
	url = args.Server
	ma_login = args.MA_login
	# A - if no opened position
	print('Read MA pose from file')
	ma_pos_id = read_pos()
	print('MA pose from file:', ma_pos_id)
	print('\n')
	if not ma_pos_id:
		print('if not ma_pos_id => No MA pos in file, opening MA pos')
		#1 Open pos
		ma_pos = open_MA_pos(url=url, header=header, ma_login=ma_login, symbol=args.Symbol, deal_type=deal_type, lot=args.Lot, comment=comment)
		print('MA pos:', ma_pos)
		ma_pos_data = ma_pos
		print('\n')
		if ma_pos:
			print('if ma_pos => ma_pose opened successfully')
			ma_pos_id = ma_pos.get('order')
			print('Get order # from ma_pos:', ma_pos_id)
			print('write it to the file...')
			write_pos(ma_pos_id)
			print('\n')
			if not ma_pos_id:
				print('if not ma_pos_id => ')
				print('Cannot get Master position ID')
				error_info(url=url, ma_login=ma_login, result='FAILED')
			else:
				print('if ma_pos_id => checking investor for copy...')
				#Waiting for coping positions
				print('\n')
				for _ in range(int(args.Wait) // 2):
					print('waiting 2 sec...')
					sleep(2)
					#2 Find investor's Poses linked to MA
					print('checking investor...')
					ia_pose = find_IA_pose(url=url, header=header, ma_login=ma_login, ia_login=args.IA_login, ma_pos_id=ma_pos_id, log=False)		# Bool
					print('find_IA_pose returned ia_pose:', ia_pose)
					if ia_pose:
						print('ia_pose found in IA!')
						compare_time(ma_pose=ma_pos_data, ia_pose=ia_pos_data, flag='open')
						break
				else:
					print('ia_pose NOT found in IA! Checking last time with error logging...')
					ia_pose = find_IA_pose(url=url, header=header, ma_login=ma_login, ia_login=args.IA_login, ma_pos_id=ma_pos_id)		# Bool
					print('find_IA_pose returned ia_pose:', ia_pose)
					print('\n')
					if not ia_pose:
						print('if not ia_pose => IA pos NOT found, closing MA pos...')
						ma_pos_close = close_MA_pos(url=url, header=header, ma_login=ma_login, ma_pos_id=ma_pos_id)		# Bool
						print('ma_pos_close:', ma_pos_close)
						print('Clearing file with pos ID')
						write_pos('')
					else:
						compare_time(ma_pose=ma_pos_data, ia_pose=ia_pos_data, flag='open')
	else: # if ma_opened position exist
		print('if ma_pos_id => MA pos in file. Checking it on MA and IA...')
		ma_pose = find_IA_pose(url=url, header=header, ma_login=ma_login, ia_login=ma_login, ma_pos_id=ma_pos_id, master=True)		# Bool
		print('ma_pose found:', ma_pose)
		ia_pose = find_IA_pose(url=url, header=header, ma_login=ma_login, ia_login=args.IA_login, ma_pos_id=ma_pos_id)		# Bool
		print('ia_pose found:', ia_pose)
		print('\n')
		# close all posses if any:
		if ma_pose and ia_pose:
			print('if ma_pose and ia_pose => close MA pos, and check it closed on IA...')
			#3 Close MA Pos
			ma_pos_close = close_MA_pos(url=url, header=header, ma_login=ma_login, ma_pos_id=ma_pos_id)		# Bool
			print('MA pos close:', ma_pos_close)
			print('Clearing file with pos ID')
			write_pos('')
			print('\n')
			if ma_pos_close:
				print('if ma_pos_close => Find this pos on IA')
				print('\n')
				for _ in range(int(args.Wait) // 2):
					print('waiting 2 sec...')
					sleep(2)
					ia_pose = find_IA_pose(url=url, header=header, ma_login=ma_login, ia_login=args.IA_login, ma_pos_id=ma_pos_id, test_close=True, log=False)		# Bool
					print('find_IA_pose returned ia_pose:', ia_pose)
					if not ia_pose:
						print('ia_pose NOT found in IA! - it was closed, OK!')
						break
				else:
					print('ia_pose still found in IA! - it was NOT closed. Last check with logging...')
					ia_pose = find_IA_pose(url=url, header=header, ma_login=ma_login, ia_login=args.IA_login, ma_pos_id=ma_pos_id, test_close=True)		# Bool
					print('find_IA_pose returned ia_pose:', ia_pose)
				if not ia_pose:
					print('Close position passed')
					compare_time(ma_pose=ma_pos_data, ia_pose=ia_pos_data, flag='close', url=url, header=header)
				else:
					print('Close position NOT passed')
		else:
			print('if ma_pose and ia_pose : NOT => close MA pos')
			print(f'Same position not found: MA: {ma_pose}, IA: {ia_pose}')
			ma_pos_close = close_MA_pos(url=url, header=header, ma_login=ma_login, ma_pos_id=ma_pos_id)		# Bool
			print('MA pos close:', ma_pos_close)
			print('Clearing file with pos ID')
			write_pos('')


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

	main(args)