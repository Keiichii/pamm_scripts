import argparse
import requests
import json

parser = argparse.ArgumentParser(description='Tests PAMM services with JSON')
parser.add_argument('WhiteLabel', help='WhiteLabel of Client')
parser.add_argument('URL', help='like http://45.32.183.177:49122/dx')
parser.add_argument('MT_login', help='MT login')
parser.add_argument('MT_pass', help='MT acc password')

args = parser.parse_args()


def error_info(msg=None, url=None, wl=None, mt_login=None, result=None):
	if msg: print(msg)
	if wl: print('WL:', wl)
	if mt_login: print('Account:', mt_login)
	if url: print('Service port:', url.split(':')[-1].split('/')[0])
	if result: print('JSON test:', result)


def request(url, method, headers, acclogin=None, accpass=None):
	result = error = None
	data = {"jsonrpc":"2.0","id":'null',"method":method,"params":{"login":acclogin,"pass":accpass}}
	try:
		response = requests.post(url, data=json.dumps(data), headers=headers, timeout=15)
	except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
		msg = f'Cannot connect: {e}'
		error_info(msg=msg, url=url, result='WARNING')
	except Exception as e:
		error = e
	else:
		data = response.json()
		if 'result' in data:
			result = data['result']
		elif 'error' in data:
			error = data['error']
	return result, error


def request_test():
	mt_login = args.MT_login
	url = args.URL
	headers = {'lbl': args.WhiteLabel}
	result, error = request(url, "logon", headers, mt_login, args.MT_pass)
	if error:
		msg = f'Error: {error}'
		error_info(msg=msg, url=url, mt_login=mt_login, result='FAILED')
	if result:
		r2 = result.get('user')
		if not r2:
			msg = 'User in result is empty. Probably user was deleted in PAMM admin UI'
			error_info(msg=msg, url=url, mt_login=mt_login, result='WARNING')
		else:
			if not r2.get('la_login'):
				msg = 'la_login in result in User is empty'
				error_info(msg=msg, url=url, mt_login=mt_login, result='WARNING')


if __name__ == "__main__":
	request_test()