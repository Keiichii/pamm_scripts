import requests
from win32service import SERVICE_WIN32, SERVICE_STATE_ALL, SERVICE_QUERY_STATUS, SERVICE_QUERY_CONFIG
from win32service import OpenSCManager, OpenService, EnumServicesStatus, QueryServiceConfig
from win32con import GENERIC_READ
from win32serviceutil import StartService, StopService, RestartService
from win32service import QueryServiceStatus
from subprocess import PIPE, Popen
from itertools import product
from re import match, search
import configparser
import logging
from logging import handlers
import os
import tempfile
from time import sleep


# Create logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create handlers
c_handler = logging.StreamHandler()     # to console
c_handler.setLevel(logging.INFO)
f_handler = handlers.RotatingFileHandler('c:\\scripts\\update_pamm_log.txt', maxBytes=1000000, backupCount=2)
f_handler.setLevel(logging.INFO)

# Create formatters and add it to handlers
c_format = logging.Formatter('\n%(asctime)s - %(levelname)s - %(message)s')
c_handler.setFormatter(c_format)
f_format = logging.Formatter('\n%(asctime)s - %(levelname)s - %(message)s')
f_handler.setFormatter(f_format)

# Add handlers to the logger
logger.addHandler(c_handler)
logger.addHandler(f_handler)

service_mask = ['dapli', 'daxel']

service_statuses = {
    5: 'The service continue is pending.',
    6: 'The service pause is pending.',
    7: 'The service is paused.',
    4: 'The service is running.',
    2: 'The service is starting.',
    3: 'The service is stopping.',
    1: 'The service is not running.',
}


def service_manager(action: str, service: str):
    '''Actions: start/stop/restart/kill;
    service name '''
    logger.info(f'service {service} - action: {action}')
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
        logger.exception(f'action: {action} exception:')


def run_cmd(cmd: str) -> tuple:
    'CMD => stdout, strerr'
    p = Popen(cmd, shell=True, stdout=PIPE, stderr=PIPE, encoding='cp866')
    stdout, stderr = p.communicate()
    # if stdout:
    #     logger.info(f'CMD stdOUT: {stdout}')
    if stderr:
        logger.error(f'CMD {cmd} stdERR: {stderr}')
    return stdout, stderr


def close_app(exe):
    error = False
    cmd = f'tasklist /FI "IMAGENAME eq {exe}" /svc'
    logger.info(cmd)
    stdout, stderr = run_cmd(cmd)
    if stderr:
        logger.error(f'Finding app in tasklist error: {stderr}')
        error = True
    if stdout:
        logger.info(stdout)
        for pid in stdout.split():
            try: int(pid)
            except ValueError: pass
            else:
                cmd = f'taskkill /PID {pid} /F'
                stdout, stderr = run_cmd(cmd)
                if stderr:
                    logger.error(f'Killing app: {stderr}')
                    error = True
                else:
                    logger.info(f'App killed: {stdout}')
    return error


def kill(service: str):
    logger.info(f'killing {service}')
    # GET PID - возвращает по точному совпадению имени службы
    cmd = f'tasklist /FI "services eq {service}" /svc'
    # logger.info(f'Running cmd: TaskLIST')
    stdout, stderr = run_cmd(cmd)
    if stderr:
        logger.error(f'Finding service in tasklist error: {stderr}')
    if stdout:
        try:
            pid = int(stdout.split()[-2])
        except ValueError as e:
            logger.exception('GET service PID exception:')
        else:
            cmd = f'taskkill /PID {pid} /F'
            # logger.info(f'Running cmd: TaskKILL')
            stdout, stderr = run_cmd(cmd)
            if stderr:
                logger.error(f'Killing service error: {stderr}')
            else:
                logger.info(f'Service killed, result: {stdout}')


def stop_or_kill(service_name, handle):
    for _ in range(3):
        service_manager('stop', service_name)
        sleep(2)
        #Check if it stopped
        status = QueryServiceStatus(handle)[1] # ex(48, 4, 5, 0, 0, 0, 0), status [1]
        if status == 1:
            break
    if status != 1:
        #Kill process
        service_manager('kill', service_name)
        sleep(2)
    #Check if it stopped
    status = QueryServiceStatus(handle)[1] # ex(48, 4, 5, 0, 0, 0, 0), status [1]
    if status != 1:
        logger.error(f'Service {service_name} not stopped, aborting update.')
        return False
    else:
        return True

def start(service_name, handle):        
    logger.info(f'Service {service_name} starting...')
    for _ in range(3):
        service_manager('start', service_name)
        sleep(2)
        #Check if it stopped
        status = QueryServiceStatus(handle)[1] # ex(48, 4, 5, 0, 0, 0, 0), status [1]
        if status == 4:
            break
    if status == 4:
        logger.info(f'Service {service_name} started')
    else:
        logger.error(f'Service {service_name} NOT started')


def find_services():
    '''Returns Dict: s_name 
    = {path', 'ver', 'exe','cfg_exe', 'handle', 'daxel_port', 'dapli_port'}'''
    services = {}
    services_to_search: list = service_mask
    
    # 1 Enumerate all services
    hscm = OpenSCManager(None,None, GENERIC_READ)   #handle Service Control Manager
    all_services  = EnumServicesStatus(hscm, SERVICE_WIN32, SERVICE_STATE_ALL)   #((Svc, Svc dispay name, (statuses)), )    TODO add only enabled statuses - filter
    #example: ('AdobeFlashPlayerUpdateSvc', 'Adobe Flash Player Update Service', (16, 1, 0, 0, 0, 0, 0))
    # statuses: [0] int : serviceType = The type of service.
    #   !       [1] int : serviceState = The current state of the service.
    #           [2] int : controlsAccepted = The controls the service accepts.
    #           [3] int : win32ExitCode = The win32 error code for the service.
    #           [4] int : serviceSpecificErrorCode = The service specific error code.
    #           [5] int : checkPoint = The checkpoint reported by the service.
    #           [6] int : waitHint = The wait hint reported by the service.
    
    # 2 Find needed services
    for s in product(services_to_search, all_services):
        pattern = s[0]
        s_name = s[1][0]
        if match(pattern, s_name.lower()):
            handle = OpenService(hscm, s_name, SERVICE_QUERY_STATUS)
            cmd = QueryServiceConfig(OpenService(hscm, s_name, SERVICE_QUERY_CONFIG))[3]
            wd = cmd[:cmd.rfind('\\')]
            exe = cmd[cmd.rfind('\\')+1:]
            daxel_port = dapli_port = None
            try:
                config = configparser.ConfigParser()
                config.read(f'{wd}\\{pattern}.ini')
                ver = config.get('Info', 'vbr')
                try:
                    dapli_port = config.get('DapliConn', 'port')
                except (configparser.NoSectionError, configparser.NoOptionError) as e:
                    pass
                    # logger.exception("Loading Dapli port Exception:")
                if dapli_port:
                    try:
                        daxel_port = config.get('Web', 'port')
                    except (configparser.NoSectionError, configparser.NoOptionError) as e:
                        logger.exception("Loading Daxel port Exception:")
                else:
                    try:
                        dapli_port = config.get('Web', 'port')
                    except (configparser.NoSectionError, configparser.NoOptionError) as e:
                        logger.exception("Loading Dapli port Exception:")
            except FileNotFoundError:
                daxel_port = dapli_port = None    #TODO временное решение для тестов
            services[s_name] = {'path': wd,
                                'ver' : ver,
                                'exe': exe,
                                'cfg_exe': s_name[:5] + 'cfg.exe',
                                'handle': handle, 
                                'daxel_port': daxel_port, 
                                'dapli_port': dapli_port,}
    return services


def request(url, header=None, body=None, timeout=None, json=True):
    result = error = None
    try:
        response = requests.get(url, timeout=timeout)
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
        logger.exception("Request connection Exception:")
    except Exception as e:
        logger.exception("Request general Exception:")
    else:
        status = response.status_code
        if not response.ok:
            logger.error(f"Request status code: {status}, url= {url}")
        else:
            if json:
                data = response.json()
                if 'result' in data:
                    result = data['result']
                elif 'error' in data:
                    error = data['error']
                    logger.info(f"Request returned error: {error}")
                else:
                    result = data
            else:
                return response, None
    return result, error


def get_versions():
    '''Returns Dict: 
    ['dapli4svc', 'dapli5svc', 'daxel', 'daddy']
    = {'ver', 'files_list', 'update_path', 'name'}
    '''
    versions = {}
    app_names = ['dapli4svc', 'dapli5svc', 'daxel', 'daddy']
    for name in app_names:
        data, error = request(url=f'http://prod.finexware.com/get_actual_version?guid={name}')
        """ {'id': 22, 'id_product': 17, 'version': '1', 'build': '44', 'rev': 2, 'api_version': '1', 'update_path': '/prod_setup/Dapli/Dapli4/', 'update_file': '_setup.lst', 'comment': 'Dapli', 'name': 'Dapli4Svc', 'suff': 'Copy4 Server'}
        {'id': 23, 'id_product': 18, 'version': '1', 'build': '44', 'rev': 2, 'api_version': '1', 'update_path': '/prod_setup/Dapli/Dapli5/', 'update_file': '_setup.lst', 'comment': 'Dapli', 'name': 'Dapli5Svc', 'suff': 'Copy5 Server'}
        {'id': 25, 'id_product': 14, 'version': '1', 'build': '44', 'rev': 2, 'api_version': '1', 'update_path': '/prod_setup/Dapli/Daxel/', 'update_file': '_setup.lst', 'comment': 'Daxel access', 'name': 'Daxel', 'suff': 'Access Server'}
        {'id': 24, 'id_product': 15, 'version': '1', 'build': '44', 'rev': 2, 'api_version': '1', 'update_path': '/prod_setup/Dapli/Daddy/', 'update_file': '_setup.lst', 'comment': 'Dap-Admin', 'name': 'Daddy', 'suff': 'Administrator'} """
        if data:
            versions[name[:6]] = {'ver': '.'.join([str(data['version']), str(data['build']), str(data['rev'])]),
                                'files_list': data['update_file'],
                                'update_path': data['update_path'],
                                'name': name[:6]}
    return versions


def to_update(local_services, new_versions):
    dic_to_update = {}
    for svc in local_services:
        short_name = svc[:5].lower()
        if short_name == 'dapli':
            dapli_number = search(r'\d', svc)
            if dapli_number:
                short_name += dapli_number.group()
        logger.info(f"For service {svc} short_name: {short_name}")
        if short_name in new_versions:
            new_ver = new_versions[short_name]['ver']
            cur_ver = local_services[svc]['ver']
            if float(cur_ver[2:]) < float(new_ver[2:]) or int(cur_ver[0]) < int(new_ver[0]):
                logger.info(f"cur {cur_ver} < {new_ver} new")
                dic_to_update[svc] = new_versions[short_name]
                logger.info(f"To update added: {svc} - {short_name}")
            else:
                logger.info(f"cur {cur_ver} = {new_ver} new")
        else:
            logger.info(f"not found in new versions {svc} - {short_name}")
    return dic_to_update


def update(svc, local_services, new_version):
    update_path = new_version["update_path"].replace('\\', '')    #"/prod_setup/Dapli/Daxel/"
    app_path = local_services[svc]['path']
    url = f'http://prod.finexware.com/prod_setup/Dapli/{new_version["name"].capitalize()}/_setup.lst'
    response, error = request(url=url, json=False)
    if response.ok:
        data = response.text.split('\r\n')
        filtered_data = data[data.index('[files]')+1:data.index('[label]')]
        files_list = [line[line.rfind('\\')+1:] for line in filtered_data]
        try:
            # create a temporary directory
            tmpdir = tempfile.TemporaryDirectory()
            tmpdirname = tmpdir.name
            file_download_error = False
            # t = 1
            for file in files_list:
                # if t==6:
                #     file += 'dfdfd'
                if file:
                    # create a temporary file and write data to it
                    f_path = os.path.join(tmpdirname, file)
                    with open(f_path, 'wb') as f:
                        url = f'http://prod.finexware.com{update_path}{file}'
                        response, error = request(url=url, json=False)
                        if response.ok:
                            f.write(response.content)
                        else:
                            file_download_error = True
                            logger.error(f'downloading {file}, status: {response.status_code} \n {url}')
                # t +=1
        except Exception as e:
            logger.exception('Downloading to temp files Exception:')
        else:
            if not file_download_error:
                #4.1 - kill running admin-apps
                error = close_app(local_services[svc]['cfg_exe'])
                if error:
                    return
                #4.2 stop services
                handle = local_services[svc]['handle']
                result = stop_or_kill(svc, handle)
                if result:
                    #4.3 replace files
                    for file in os.listdir(tmpdirname):
                        logger.info(f'moving {file}...')
                        for i in range(3):
                            try:
                                os.replace(os.path.join(tmpdirname, file), os.path.join(app_path, file))
                                # os.replace(os.path.join(tmpdirname, file), os.path.join('c:\\scripts\\temp', file))
                            except PermissionError as e:
                                logger.exception(f'Replacing {file} Exception:')
                                logger.warning(f'try #{i} to stop service {svc}')
                            except Exception as e:
                                logger.exception(f'Replacing {file} general Exception:')
                            else:
                                break
                            finally:
                                os.chdir(app_path)
                                cmd = 'ICACLS * /reset'
                                p = Popen(cmd, shell=True, stdout=PIPE, stderr=PIPE, encoding='cp866')
                                stdout, stderr = p.communicate()
                                logger.info(f'Permission correction results:\n    stdout: {stdout}\n    stderr: {stderr}')
                    #4.3 - start service
                    start(svc, handle)
                    logger.info(f'======================================= \n {svc} update finished.\n')
    else:
        logger.error(f'downloading _setup.lst, status: {response.status_code} \n {url}')


if __name__ == "__main__":
    logger.info('======================================= \n               START\n')
    
    #1 find local services 
    local_services = find_services()    #Dict s_name = {}
    logger.info(f'Found these services: {local_services.keys()}')
    
    #2 Get available version
    new_versions = get_versions()
    logger.info("Got new versions:")
    logger.info({f'    {i} = {v["ver"]}' for i, v in new_versions.items()})

    #3 compare versions and prepare list to update process
    dic_to_update = to_update(local_services, new_versions)
    logger.info(f"Going to update: {dic_to_update.keys()}")
    
    #4 Update app
    for svc, new_version in dic_to_update.items():
        update(svc, local_services, new_version)