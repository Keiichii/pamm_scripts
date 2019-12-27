import argparse
import requests
import json
from time import sleep


#Repo changes

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
		response = requests.post(f'http://{url}/dx', data=json.dumps(data), headers=header, timeout=15)
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


def find_IA_pose(url, header, ma_login, ia_login, ma_pos_id):
	found = False
	params = {"login": ia_login}
	ia_poses, error = request(url=url, method='acc.pos', header=header, params=params)
	if error:
		print("Error getting Investor positions:", error)
		error_info(url=url, ma_login=ma_login, ia_login=ia_login, result='WARNING')
	elif ia_poses:
		list_of_poses = ia_poses.get('poss')
		if not list_of_poses:
			print('List of investor posses is empty')
			error_info(url=url, ma_login=ma_login, ia_login=ia_login, result='FAILED')
		else:
			for pos in list_of_poses:
				if pos.get('ma').get('pos_id') == ma_pos_id:
					found = True
					break
			if not found:
				print('Error: no copied position found on investor')
				error_info(url=url, ma_login=ma_login, ia_login=ia_login, result='FAILED', ma_pos_id=ma_pos_id)
	return found


def error_info(url=None, ma_login=None, ia_login=None, result=None, ma_pos_id=None):
	if ma_login: print('Master acc:', ma_login)
	if ma_pos_id: print('Master position:', ma_pos_id)
	if ia_login: print('Investor acc:', ia_login)
	if url: print('Service port:', url.split(':')[-1])
	if result: print('Copy test:', result)


def main(args):
	header = {'ManagerPass': args.ManagerPass}
	url = args.Server
	ma_login = args.MA_login
	#1 Open pos
	ma_pos = open_MA_pos(url=url, header=header, ma_login=ma_login, symbol=args.Symbol, deal_type=deal_type, lot=args.Lot, comment=comment)
	if ma_pos:
		ma_pos_id = ma_pos.get('order')
		if not ma_pos_id:
			print('Cannot get Master position ID')
			error_info(url=url, ma_login=ma_login, result='FAILED')
		else:
			#Waiting for coping positions
			sleep(int(args.Wait))
			
			#2 Find investor's Poses linked to MA
			ia_pose = find_IA_pose(url=url, header=header, ma_login=ma_login, ia_login=args.IA_login, ma_pos_id=ma_pos_id)		# Bool

			#3 Close MA Pos
			ma_pos_close = close_MA_pos(url=url, header=header, ma_login=ma_login, ma_pos_id=ma_pos_id)		# Bool


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