import os
import sys
import random
from test_procedures import TestProcedure
import ae
import test_procedures
from ae import  ae_errors

class HelloWorld(TestProcedure.TestProcedure):
    
    # The "action" method is executed by AE.
    def action(self):
        
        # the log can be referenced as self.log
        # there are 4 levels (info, debug, warning,e rror)
        self.log.info("This is my first test procedure")
        
        #Let's run a shell command
        some_cmd = " echo 'Hello World!'"
        self._run_shell(some_cmd)
        
        self.log.info("STUFF FROM THE PROCEDURE")
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
        
        # The action method stores it's results in the Procedure Return Object
        # also known as the PRO. The PRO has four members
        #    output          -- Can be used for return values from the procedure     
        #    shell_stdout    -- STDOUT of the shell command (if used)
        #    shell_stderr    -- STDERR of the shell command (if used)
        #    shell_ret_code  -- Return code of the shell command
        
        
        # We can access the PRO from the action method like this
        my_pro = self.get_pro()
        
        # The PRO has a __string__ method so we can print it directly
        self.log.info("Printing the PRO from the procedure checkpoint: %s"% my_pro)
        # perhaps we want to double check the stdout
        if "Hello World!" in my_pro.shell_stdout:
            self.log.info("The STDOUT looks great!")
        
        # or if there was a problem, we can raise a failure
        else:
            raise ae_errors.TestProcedureFail(message="Hello World was missing. Goodbye.")
        


   
class DelayedHelloWorld(TestProcedure.TestProcedure):
    
    def action(self):
        self.log.debug("We're in DelayedHelloWorld")
        
        # lets see if there's a sleep_time arg
        sleep_time = self.args.get("sleep_time")

        self._run_shell("echo 'some stuff'")        
        if sleep_time ==None:
            sleep_time = random.randint(5,15)
        
        import time
        self.log.info("Sleeping for %s seconds."%sleep_time)
        time.sleep(sleep_time)
        
        

        return "Delayed Hello World is done!" 
        
    def checkpoint(self):
        my_pro = self.get_pro()
        
        # The PRO has a __string__ method so we can print it directly
        self.log.info("Printing the PRO from the procedure [%s] checkpoint: %s"% (os.getpid(),my_pro))
        # perhaps we want to double check the stdout
        if my_pro.shell_stdout != None:
            self.log.info("The STDOUT is okay")
        else:
            raise ae_errors.TestProcedureFail(message="Stuff was missing.")


class DelayedHelloWithRemote(TestProcedure.TestProcedure):
    
    def action(self):
        self.log.debug("We're in DelayedHelloWithRemote")
        
        # lets see if there's a sleep_time arg
        sleep_time = self.args.get("sleep_time",2)

        import time
        time.sleep(sleep_time)
        
        self._run_shell("echo 'You are number one!'")
        
        n1 = self.sut.nodes[0]
        tp = test_procedures.example_procedures.hello_world.WhoAmI(self.sut, self.suite_config)
        self.log.debug("Calling WhoAmI from [%s]" % os.getpid())
        
        my_pro = tp.run(node=n1, _pid=os.getpid())
        self.log.info("pro from WhoAmI from [%s] :%s"%(os.getpid(), my_pro))
        
        return "Delayed Hello World With Remote call is done!" 
        
    def checkpoint(self):
        my_pro = self.get_pro()
        
        # The PRO has a __string__ method so we can print it directly
        self.log.info("Printing the PRO from the procedure [%s] checkpoint: %s"% (os.getpid(),my_pro))
        # perhaps we want to double check the stdout
        if my_pro.shell_stdout != None:
            self.log.info("The STDOUT is okay")
        else:
            raise ae_errors.TestProcedureFail(message="Stuff was missing.")


    
class WhoAmI(TestProcedure.TestProcedure):
    
    # The "action" method is executed by AE.
    def action(self):
        self.log.info("INSIDE WhoAmI")
        #Let's run a shell command
        import time
        time.sleep(3)
        some_cmd = "hostname"
        self._run_shell(some_cmd)
        
        return "YES!"
        
    # The checkpoint method is called automatically b
    def checkpoint(self):
        my_pro = self.get_pro()
        self.log.info("Printing the PRO in WhoAmI[%s] checkpoint: %s"% (os.getpid(),my_pro))
        

class HelperExample(TestProcedure.TestProcedure):
    
    
    def post_config(self):
        self.add_pro_method(self.helper_to_lower)
        self.add_pro_method(self.helper_to_upper)        
    
    def helper_to_upper(self):
        """
         Helper method to first  convert the output string
         to lowercase and then convert to upper.
        """
        return self.helper_to_lower().upper()
    
    
    def helper_to_lower(self):
        """ 
         Trivial helper method that will convert the pro.output 
         string to lower case characters
        """
        return self.pro.output.lower()
    
    def action(self):
        
        return "The best STRING ever."
    
    def checkpoint(self):
        pass

