from sqlalchemy import create_engine, text
from logger import logger, create_con_logger, create_file_logger, states
import argparse
from time import time
import logging

start_time = time()
logger2 = logging.getLogger(__name__)


parser = argparse.ArgumentParser(description='Check positions time difference between MA and IA')
parser.add_argument('IP', help='MySQL IP address')
parser.add_argument('--PORT', help='MySQL port, default=3306', default=3306)
parser.add_argument('LOGIN', help='MySQL login')
parser.add_argument('PASSWORD', help='MySQL password')
parser.add_argument('DB', help='MySQL DB')
parser.add_argument('--log_file', help='full path to log file for output', default='C:\scripts\db_time_diff_log.txt')
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

sql_deals = text("""SELECT m.login as 'IA login', m.ma_login as 'MA login', m.pos_id, m.ma_pos_id, m.symbol, m.action, m.entry, m.volumext, from_unixtime(m.time_pos) as 'IA open time', 
        (select from_unixtime(m2.time_pos) from deal as m2 where m.ma_pos_id=m2.pos_id and m2.entry=1 limit 1) as 'MA open time', 
        m.time_pos-(select m2.time_pos from deal as m2 where m.ma_pos_id=m2.pos_id and m2.entry=1 limit 1) as open_diff_sec, 
        from_unixtime(m.time) as 'IA close time', (select from_unixtime(m2.time) from deal as m2 where m.ma_pos_id=m2.pos_id and m2.entry=1 limit 1) as 'MA close time', 
        m.time-(select m2.time from deal as m2 where m.ma_pos_id=m2.pos_id and m2.entry=1 limit 1) as close_diff_sec 
        FROM deal as m 
        WHERE m.time_pos >= unix_timestamp(now())-3600 and 
        m.ma_pos_id <>0 and m.entry=1 
        and (m.time_pos-(select m2.time_pos from deal as m2 where m.ma_pos_id=m2.pos_id and m2.entry=1 limit 1)  >=5
            or m.time-(select m2.time from deal as m2 where m.ma_pos_id=m2.pos_id and m2.entry=1 limit 1) >=5) 
        order by open_diff_sec desc, close_diff_sec desc""")


r = conn.execute(sql_deals).fetchall()
count = len(r)
if count >50:
    logger.warning('WARNING')
    from prettytable import PrettyTable
    t_deals = PrettyTable(['IA login', 'MA login', 'IA pos_id', 'MA pos_id', 'Symbol', 'Action', 'Entry', 'Volume', 'IA open time', 'MA open time', 'open_diff_sec', 'IA close time', 'MA close time', 'close_diff_sec'])
    t_count = PrettyTable(['Number of poses', 'MAX open time diff', 'MAX close time diff'])
    max_open_diff = 0
    max_close_diff = 0
    i = 0
    for row in r:
        if i < 100:
            t_deals.add_row(row)
        max_open_diff = max(max_open_diff, row[10])
        max_close_diff = max(max_close_diff, row[13])
        i += 1
    t_count.add_row([count, max_open_diff, max_close_diff])
    logger.info(t_count)
    logger2.warning(t_deals)
else:
    logger.info('PASSED')

logger.debug(f'>>> Time: {time() - start_time}')