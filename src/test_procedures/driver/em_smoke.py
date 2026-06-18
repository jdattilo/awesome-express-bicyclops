import sys
import os
import subprocess
from lib import constants
from lib import pathing
from lib import network

from test_procedures import TestProcedure

class EmDCReset(TestProcedure.TestProcedure):
    """
            Procedure to launch psexec from windows box to another windows box and reset
            In this case very hardcoded to login to data collector and run bat file which
             Stop Data Collector service
             Waits 100 secs to allow service to stop
             Deletes db files
             Starts Data Collector service
             Waits 100 secs to allow service to start
    """

    def action(self):
        self.log.info('Resetting Data Collector')
        dcnode = self.args.get("dcnode")
        smokerun= "%s\\PSTools\\psexec -d \"%s\\cml_smoke\\reset.bat\""%(pathing.get_tools_bin(),pathing.get_tools_src())
        cmd = "%s"%(smokerun)
        self._run_shell(cmd, auto_check=False)

    def checkpoint(self):
        pass

class EmDebugCollect(TestProcedure.TestProcedure):
    """
        Procedure to run & debuglogs 
        Very hardcoded  
    -    
    """

    def action(self):
        
        self.log.info('Running EM DC Debug Logs collection')
        emnode = self.args.get("node")
        cmd = "c:\\buildslave\\logs.bat %s"%(emnode)
        self._run_shell(cmd)
    
    def checkpoint(self):
        pass
    
