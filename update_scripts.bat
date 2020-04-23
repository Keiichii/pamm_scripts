cd c:\scripts\pamm_scripts
..\PortableGit\bin\git reset --hard
..\PortableGit\bin\git pull
REM del c:\scripts\copy_test_pos.txt
mklink c:\scripts\zabbix_sender.py c:\scripts\pamm_scripts\zabbix_sender.py
