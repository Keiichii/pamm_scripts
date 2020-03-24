from sqlalchemy import create_engine, text
from logger import logger, create_con_logger, create_file_logger, states
import argparse
from time import time
import logging

start_time = time()
logger2 = logging.getLogger(__name__)


parser = argparse.ArgumentParser(description='Check for unlinked to MA positions')
parser.add_argument('IP', help='MySQL IP address')
parser.add_argument('--PORT', help='MySQL port, default=3306', default=3306)
parser.add_argument('LOGIN', help='MySQL login')
parser.add_argument('PASSWORD', help='MySQL password')
parser.add_argument('DB', help='MySQL DB')
parser.add_argument('--log_file', help='full path to log file for output', default='C:\scripts\db_unlinked_poses_log.txt')
parser.add_argument('--debug', help='Print all debug information', action='store_true')
args = parser.parse_args()

if args.debug:
    log_level = 'DEBUG'
else:
    log_level = 'INFO'

create_file_logger(log_level, args.log_file, logger=logger2)
create_con_logger(log_level)

uri = f'mysql+mysqldb://{args.LOGIN}:{args.PASSWORD}@{args.IP}:{args.PORT}/{args.DB}'
engine = create_engine(uri, echo=args.debug) 
conn = engine.connect()

sql_deals = text("""SELECT login, id, deal, symbol, from_unixtime(time), comment, ma_pos_id, ma_login FROM deal 
                    where login not in (SELECT ma_login FROM link group by ma_login)
                        and ma_pos_id=0  
                        and comment regexp "@[0-9]"
                        and time >= unix_timestamp(now())-3600
                    order by deal.id desc;""")

r = conn.execute(sql_deals).fetchall()
count = len(r)
if count > 0:
    logger.warning('WARNING')
    from prettytable import PrettyTable
    t_deals = PrettyTable(['IA login', 'ID', 'IA deal #', 'Symbol', 'Time', 'Comment', 'MA pos_id', 'MA login'])
    t_count = f'Number of poses without link to master: {count}'
    i = 0
    for row in r:
        if i < 100:
            t_deals.add_row(row)
        i += 1
    logger.info(t_count)
    logger2.warning(t_deals)
else:
    logger.info('PASSED')

logger.debug(f'>>> Time: {time() - start_time}')
