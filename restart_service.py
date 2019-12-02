from win32service import SERVICE_WIN32, SERVICE_STATE_ALL, SERVICE_QUERY_STATUS, SERVICE_QUERY_CONFIG
from win32service import OpenSCManager, OpenService, EnumServicesStatus, QueryServiceConfig
from win32con import GENERIC_READ
from itertools import product
import logging
import argparse
from re import match
import configparser
from win32service import QueryServiceStatus
from win32serviceutil import StartService, StopService, RestartService
from subprocess import PIPE, Popen
from time import sleep
from re import findall


log_format = '%(asctime)s - %(levelname)s - %(message)s'
logging.basicConfig(filename="restart_service_log.txt", level=logging.INFO, format=log_format)
services = dict()  # Список задач с параметрами для воркеров
daxel_ports = dict()
dapli_ports = dict()
max_retries = 3

service_statuses = {
    5: 'The service continue is pending.',
    6: 'The service pause is pending.',
    7: 'The service is paused.',
    4: 'The service is running.',
    2: 'The service is starting.',
    3: 'The service is stopping.',
    1: 'The service is not running.',
}


def find_services(services_list:list):
    '''Imputs: 
        1) List of services to search
        2) Secs to wait for service restart
        3) number of max retries to restart service
        
    Returns:  Dict with services'''

    # 1 Enumerate all services
    hscm = OpenSCManager(None,None, GENERIC_READ)   #handle Service Control Manager
    all_services  = EnumServicesStatus(hscm, SERVICE_WIN32, SERVICE_STATE_ALL)   #((Svc, Svc dispay name, (statuses)), )
    """ 
                example: ('AdobeFlashPlayerUpdateSvc', 'Adobe Flash Player Update Service', (16, 1, 0, 0, 0, 0, 0))
                statuses: [0] int : serviceType = The type of service.
                !       [1] int : serviceState = The current state of the service.
                        [2] int : controlsAccepted = The controls the service accepts.
                        [3] int : win32ExitCode = The win32 error code for the service.
                        [4] int : serviceSpecificErrorCode = The service specific error code.
                        [5] int : checkPoint = The checkpoint reported by the service.
                        [6] int : waitHint = The wait hint reported by the service. """
    
    # 2 Find needed services
    for s in product(services_list, all_services):
        pattern = s[0]
        s_name = s[1][0]
        if match(pattern, s_name.lower()):
            handle = OpenService(hscm, s_name, SERVICE_QUERY_STATUS)
            cmd = QueryServiceConfig(OpenService(hscm, s_name, SERVICE_QUERY_CONFIG))[3]
            wd = cmd[:cmd.rfind('\\')]
            daxel_port = dapli_port = None
            config = configparser.ConfigParser()
            result = config.read(f'{wd}\\{pattern}.ini')
            if result:
                try:    #IF it's Daxel
                    dapli_port = config.get('DapliConn', 'port')
                except (configparser.NoSectionError, configparser.NoOptionError) as e:
                    pass
                    # logging.error(['Loading Dapli port error:', e])
                if dapli_port:  #For Daxel
                    try:
                        daxel_port = config.get('Web', 'port')
                        daxel_ports[daxel_port] = s_name
                    except (configparser.NoSectionError, configparser.NoOptionError) as e:
                        logging.error(f'Loading Daxel port error: {e}')
                else:       #For Dapli
                    try:
                        dapli_port = config.get('Web', 'port')
                        dapli_ports[dapli_port] = s_name
                    except (configparser.NoSectionError, configparser.NoOptionError) as e:
                        logging.error(f'Loading Dapli port error: {e}')
                        logging.error(f'{wd}\\{pattern}.ini')
                        logging.error(config)
            else:
                logging.error('Config file not found.')
            services[s_name] = {'handle': handle, 
                                'daxel_port': daxel_port, 
                                'dapli_port': dapli_port}


def service_manager(action: str, service: str):
    '''Actions: start/stop/restart/kill;
    service name '''
    logging.info(f'service {service} - action: {action}')
    try:
        if action == 'start':
            StartService(service)
        elif action == 'stop':
            StopService(service)
        elif action == 'restart':
            RestartService(service)
        elif action == 'kill':
            kill(service)
    except Exception as e:
        logging.error(f'action: {action} exception: {e}')


def run_cmd(service: str, cmd: str) -> tuple:
    'CMD => stdout, strerr'
    p = Popen(cmd, shell=True, stdout=PIPE, stderr=PIPE, encoding='cp866')
    stdout, stderr = p.communicate()
    # if stdout:
    #     logging.info(f'CMD stdOUT: {stdout}')
    # if stderr:
    #     logging.error(f'CMD stdERR: {stderr}')
    return stdout, stderr


def kill(service: str):
    logging.info(f'killing {service}')
    # GET PID - возвращает по точному совпадению имени службы
    cmd = f'tasklist /FI "services eq {service}" /svc'
    # logging.info(f'Running cmd: TaskLIST')
    stdout, stderr = run_cmd(service, cmd)
    if stderr:
        logging.error(f'Finding service in tasklist error: {stderr}')
    if stdout:
        try:
            pid = int(stdout.split()[-2])
        except ValueError as e:
            logging.error(f'GET service PID exception: {e}')
        else:
            cmd = f'taskkill /PID {pid} /F'
            # logging.info(f'Running cmd: TaskKILL')
            stdout, stderr = run_cmd(service, cmd)
            if stderr:
                logging.error(f'Killing service error: {stderr}')
            else:
                logging.info(f'Service killed, result: {stdout}')
        


def find_Dapli(daxel_port):
    'Takes Daxel port -> returns Dapli service name'
    dapli_name = None
    daxel_name = daxel_ports.get(daxel_port)
    if not daxel_name:
        logging.error(f'Daxel service with port {daxel_port} not found:')
    else:
        try:
            dapli_port = services[daxel_name]['dapli_port']
            dapli_name = dapli_ports[dapli_port]
        except TypeError as e:
            logging.error(f'Exception finding Dapli service: {e}')
    return dapli_name            


def check_service(service_name):
    #1 find linked Dapli by Daxel's port
    if service_name:
        handle = services[service_name]['handle']
        #2 Try to stop service
        for _ in range(max_retries):
            service_manager('stop', service_name)
            sleep(0.5)
            #Check if it stopped
            status = QueryServiceStatus(handle)[1] # ex(48, 4, 5, 0, 0, 0, 0), status [1]
            if status == 1:
                break
        if status != 1:
            #Kill process
            service_manager('kill', service_name)
            sleep(0.5)
        #Check if it stopped
        status = QueryServiceStatus(handle)[1] # ex(48, 4, 5, 0, 0, 0, 0), status [1]
        if status != 1:
            logging.error(f'Service {service_name} not stopped, trying to restart')
            service_manager('restart', service_name)
        else:
            logging.info(f'Service {service_name} stopped, starting it')
            for _ in range(max_retries):
                service_manager('start', service_name)
                sleep(0.5)
                #Check if it stopped
                status = QueryServiceStatus(handle)[1] # ex(48, 4, 5, 0, 0, 0, 0), status [1]
                if status == 4:
                    break
            if status == 4:
                logging.info(f'Service {service_name} started')
            else:
                logging.error(f'Service {service_name} NOT started')


def find_port(string):
    port = service_name = None
    try:
        if 'json_checklogin' in string:
            port = findall(r':(\d+)/', string)[0]
        elif 'copy_test' in string:
            port = findall(r':(\d+),', string)[0]
        elif 'service.info' in string:
            service_name = findall(r'\[(\w+),', string)[0]
        elif 'error_monitor' ib string:
            port = findall(r'\d{5}', string)[0]
        elif 'web.page.get' in string:
            port = findall(r',(\d+)]', string)[0]
    except IndexError as e:
        logging.error(f'Exception parsing args: {e}')
    return port, service_name



if __name__ == "__main__":
    services_list = ['dapli', 'daxel', 'finexmart']
    parser = argparse.ArgumentParser(description='Restarts Dapli and kill it if needed')
    parser.add_argument('Port', help='Daxel port')
    args = parser.parse_args()
    
    logging.info(f'\n START \n')
    daxel_port, service_name = find_port(args.Port)
    if daxel_port:
        find_services(services_list=services_list)
        dapli_name = find_Dapli(daxel_port)
        check_service(service_name=dapli_name)
    elif service_name:
        find_services(services_list=services_list)
        check_service(service_name=service_name)
    else:
        logging.error(f'Cannot parse port number')