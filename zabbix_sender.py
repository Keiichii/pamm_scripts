from pyzabbix import ZabbixMetric, ZabbixSender
from os.path import exists


conf_pathes = ['c:\Program Files\Zabbix Agent\zabbix_agentd.conf', 'c:\zabbix\zabbix_agentd.conf', 'zabbix_agentd.conf']


def send(result, msg):
    report = ''
    for path in conf_pathes:
        if exists(path):
            with open(path) as f:
                for line in f.readlines():
                    if '#' in line:
                        continue
                    elif 'Hostname' in line:
                        hostname = line[line.find('=')+1:].strip()
                        break
            break
    else:
        return 'Error'
    if not isinstance(msg, list):
        report = msg
    else:
        if result == 'FAILED' or result == 'BALANCE FAILED' or result == 'WARNING':
            for m in msg:
                if 'REQUEST' == m[0] or 'DATA' == m[0]:
                    continue
                if report:
                    report = f'{report}\n{m[1]}'
                else:
                    report = m[1]
        else:									
            for m in msg:
                if 'WARNING' == m[0]:
                    if report:
                        report = f'{report}\n{m[1]}'
                    else:
                        report = m[1]
    packet = [ZabbixMetric(hostname, 'test_trap', report)]
    result = ZabbixSender(use_config=path).send(packet)
    if result.failed != 0:
        error = f'Zabbix-sender: Error sending {msg}'
        return error