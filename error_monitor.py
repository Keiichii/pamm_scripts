import argparse
import requests
from time import strftime, gmtime


parser = argparse.ArgumentParser(description='Request PAMM service errors')
parser.add_argument('IP', help='15.32.163.117')
parser.add_argument('Port', help='Daxel port')

args = parser.parse_args()


def error_info(msg=None, url=None, result=None):
    if msg: print(msg)
    if url: print('Service port:', url.split(':')[-1].split('/')[0])
    if result: print('Monitor request:', result)


def request(url):
    result = error = None
    try:
        response = requests.get(url, timeout=15)
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


def convert_time(secs):
    return strftime('%d.%m.%Y %H:%M:%S', gmtime(secs))


def request_monitor(ip, port):
    url = f'http://{ip}:{port}/dx?Monitor=yes&Password=12345'
    result, error = request(url)
    if error:
        msg = f'Error: {error}'
        error_info(msg=msg, url=url, result='FAILED')
    if result:
        error_list = result.get('em')
        if error_list:
            print('*List of current errors:* _(time of server)_')
            for row in error_list:
                msg = f'''    Time: {convert_time(row.get("ut"))}
    Function: {row.get("f")}
    Text: {row.get("t")}\n'''
                error_info(msg=msg)



if __name__ == "__main__":
    request_monitor(args.IP, args.Port)