

# Default procedure timeout will be set to N seconds.
# This can be overidden by the suite file or when proc runs.
DEFAULT_PROCEDURE_TIMOUT = 600

# Amount of seconds between queries to the remote proc_caller
# to ensure it is still alive.
HEARTBEAT_INTERVAL = 5

# Interval between querying a node while waiting for
# it to be up and responsive.
REBOOT_INTERVAL = 20

# Message raised in a ProcedureError that we can treat
# as a flag that the process was not responding to signals
PROCESS_IS_UNINTERRUPTIBLE = "PROCESS_IS_UNINTERRUPTIBLE"


#  --------      PRODUCT CONSTANTS      --------


#  -------       MACHINE CONSTANTS      -------
PYTHON27_LINUX = "/opt/python2.7/bin/python2.7"
PYTHON27_WIN32 = "C:\\Python27\\python.exe"



# -------     LAB CONSTANTS      -------
