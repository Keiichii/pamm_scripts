import argparse
import requests
import json
from time import sleep, time


deal_type = '0'
comment = 'Zabbix test deal'
base_req = {"jsonrpc":"2.0", "id":"null"}
check_result = None


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
						if pos.get('ma').get('pos_id') == ma_pos_id:
							found = True
							break
					else:
						cur_pos = pos.get('pos_id')
						if cur_pos == ma_pos_id:
							found = True
						else:
							ma_pos_close = close_MA_pos(url=url, header=header, ma_login=ma_login, ma_pos_id=cur_pos)		# Bool
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


def main(args):
	header = {'ManagerPass': args.ManagerPass}
	url = args.Server
	ma_login = args.MA_login
	# A - if no opened position
	ma_pos_id = read_pos()
	if not ma_pos_id:
		#1 Open pos
		ma_pos = open_MA_pos(url=url, header=header, ma_login=ma_login, symbol=args.Symbol, deal_type=deal_type, lot=args.Lot, comment=comment)
		if ma_pos:
			ma_pos_id = ma_pos.get('order')
			write_pos(ma_pos_id)
			if not ma_pos_id:
				print('Cannot get Master position ID')
				error_info(url=url, ma_login=ma_login, result='FAILED')
			else:
				#Waiting for coping positions
				for _ in range(int(args.Wait) // 2):
					sleep(2)
					#2 Find investor's Poses linked to MA
					ia_pose = find_IA_pose(url=url, header=header, ma_login=ma_login, ia_login=args.IA_login, ma_pos_id=ma_pos_id, log=False)		# Bool
					if ia_pose:
						break
				else:
					ia_pose = find_IA_pose(url=url, header=header, ma_login=ma_login, ia_login=args.IA_login, ma_pos_id=ma_pos_id)		# Bool
					if not ia_pose:
						ma_pos_close = close_MA_pos(url=url, header=header, ma_login=ma_login, ma_pos_id=ma_pos_id)		# Bool
						write_pos('')
	else: # if ma_opened position exist
		ma_pose = find_IA_pose(url=url, header=header, ma_login=ma_login, ia_login=ma_login, ma_pos_id=ma_pos_id, master=True)		# Bool
		# close all other posses if any:
		ia_pose = find_IA_pose(url=url, header=header, ma_login=ma_login, ia_login=args.IA_login, ma_pos_id=ma_pos_id)		# Bool
		if ma_pose and ia_pose:
			#3 Close MA Pos
			ma_pos_close = close_MA_pos(url=url, header=header, ma_login=ma_login, ma_pos_id=ma_pos_id)		# Bool
			write_pos('')
			if ma_pos_close:
				for _ in range(int(args.Wait) // 2):
					sleep(2)
					ia_pose = find_IA_pose(url=url, header=header, ma_login=ma_login, ia_login=args.IA_login, ma_pos_id=ma_pos_id, test_close=True, log=False)		# Bool
					if not ia_pose:
						break
				else:
					ia_pose = find_IA_pose(url=url, header=header, ma_login=ma_login, ia_login=args.IA_login, ma_pos_id=ma_pos_id, test_close=True)		# Bool
				if not ia_pose:
					print('Close position passed')
				else:
					print('Close position NOT passed')
		else:
			print(f'Some position not found: MA: {ma_pose}, IA: {ia_pose}')
			ma_pos_close = close_MA_pos(url=url, header=header, ma_login=ma_login, ma_pos_id=ma_pos_id)		# Bool
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