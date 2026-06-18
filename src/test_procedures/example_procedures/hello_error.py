import os
import sys
from test_procedures import TestProcedure
import ae
from ae import ae_errors

class HelloError(TestProcedure.TestProcedure):
    
    # The "action" method is executed by AE.
    def action(self):
        
        # the log can be referenced as self.log
        # there are 4 levels (info, debug, warning,e rror)
        self.log.info("This is my first test procedure")
        
        
        #Let's run a shell command
        some_cmd = " echo 'Hello World Error!'"
        self._run_shell(some_cmd)
        
        # the return code of some_cmd was automatically
        # evaluated to see if it was zero. If it wasn't, 
        # a TestProcedureFailure would be raised and then
        # elevated to TestCaseFailure 
        #
        # Also, shell output is stored in the PRO object (see below in action()
    
    
        # We can also add some additional data to the pro output member
        # by returning a value from the action method
        some_data = ["this", "is", "serious"]
        return some_data
        
    
    # The checkpoint method is called automatically b
    def checkpoint(self):
        pass