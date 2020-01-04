cd c:\scripts\pamm_scripts
..\PortableGit\bin\git reset --hard
..\PortableGit\bin\git pull
del c:\scripts\logger.py
mklink c:\scripts\logger.py c:\scripts\pamm_scripts\logger.py