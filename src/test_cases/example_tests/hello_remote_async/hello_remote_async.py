import test_procedures
from test_cases import TestCase
from ae import ae_errors
import time

class hello_remote_async(TestCase.TestCase):
    """
     A quick test that executes the simple HelloWorld procedure 
     synchronously on each node in the SUT
    """
        
    def pre_execute(self):
        pass     
    
    def main_execute(self):      
        
        # this is assigns n1 to be the first node in the SUT's node list 
        n1 = self.sut.nodes[0]
        wait_time = 60
        
        self.args.update({"node":n1})
        t = 1
        
        delayed_hello1 = test_procedures.example_procedures.hello_world.DelayedHelloWorld(self.sut, self.suite_config)
        delayed_hello1.run_asynch(**self.args)
        time.sleep(t)
        if delayed_hello1.is_running() == False:
            raise ae_errors.TestCaseFail(message="Proc is not running.")
        
        delayed_hello2 = test_procedures.example_procedures.hello_world.DelayedHelloWorld(self.sut, self.suite_config)
        delayed_hello2.run_asynch(**self.args)
        time.sleep(t)
        delayed_hello3 = test_procedures.example_procedures.hello_world.DelayedHelloWorld(self.sut, self.suite_config)
        delayed_hello3.run_asynch(**self.args)
        time.sleep(t)
        delayed_hello4 = test_procedures.example_procedures.hello_world.DelayedHelloWorld(self.sut, self.suite_config)
        delayed_hello4.run_asynch(**self.args)
        time.sleep(t)
        delayed_hello5 = test_procedures.example_procedures.hello_world.DelayedHelloWorld(self.sut, self.suite_config)
        delayed_hello5.run_asynch(**self.args)
        time.sleep(t)
        
        # if there are >1 nodes, lets fire off some procs on the other node as well
        if len(self.sut.nodes) >1:
            n = self.sut.nodes[1]
            self.args.update({"node":n})
        
        delayed_hello6 = test_procedures.example_procedures.hello_world.DelayedHelloWorld(self.sut, self.suite_config)
        delayed_hello6.run_asynch(**self.args)
        delayed_hello7 = test_procedures.example_procedures.hello_world.DelayedHelloWorld(self.sut, self.suite_config)
        delayed_hello7.run_asynch(**self.args)
        time.sleep(t)
        delayed_hello8 = test_procedures.example_procedures.hello_world.DelayedHelloWorld(self.sut, self.suite_config)
        delayed_hello8.run_asynch(**self.args)
        time.sleep(t)
        delayed_hello9 = test_procedures.example_procedures.hello_world.DelayedHelloWorld(self.sut, self.suite_config)
        delayed_hello9.run_asynch(**self.args)
        delayed_hello10 = test_procedures.example_procedures.hello_world.DelayedHelloWorld(self.sut, self.suite_config)
        delayed_hello10.run_asynch(**self.args)
        time.sleep(t)
        delayed_hello11 = test_procedures.example_procedures.hello_world.DelayedHelloWorld(self.sut, self.suite_config)
        delayed_hello11.run_asynch(**self.args)
        time.sleep(t)
        delayed_hello12 = test_procedures.example_procedures.hello_world.DelayedHelloWorld(self.sut, self.suite_config)
        delayed_hello12.run_asynch(**self.args)
        
        
        time.sleep(10)
        self.log.info("Starting the wait sequence...")

        my_pro1 = delayed_hello1.wait(wait_time)
        self.log.debug("my_pro1: %s"%my_pro1)
        
        my_pro2 = delayed_hello2.wait(wait_time)
        self.log.debug("my_pro2: %s"%my_pro2)
        
        my_pro3 = delayed_hello3.wait(wait_time)
        self.log.debug("my_pro3: %s"%my_pro3)
        
        my_pro4 = delayed_hello4.wait(wait_time)
        self.log.debug("my_pro4: %s"%my_pro4)
        
        my_pro5 = delayed_hello5.wait(wait_time)
        self.log.debug("my_pro5: %s"%my_pro5)
        
        my_pro6 = delayed_hello6.wait(wait_time)
        self.log.debug("my_pro6: %s"%my_pro6)
        
        my_pro7 = delayed_hello7.wait(wait_time)
        self.log.debug("my_pro7: %s"%my_pro7)
        
        my_pro8 = delayed_hello8.wait(wait_time)
        self.log.debug("my_pro8: %s"%my_pro8)
        
        my_pro9 = delayed_hello9.wait(wait_time)
        self.log.debug("my_pro9: %s"%my_pro9)
        
        my_pro10 = delayed_hello10.wait(wait_time)
        self.log.debug("my_pro10: %s"%my_pro10)
        
        my_pro11= delayed_hello11.wait(wait_time)
        self.log.debug("my_pro11: %s"%my_pro11)
        
        my_pro12 = delayed_hello12.wait(wait_time)
        self.log.debug("my_pro12: %s"%my_pro12)

        
        self.log.info("Wait sequence complete")
        
        
        if delayed_hello1.is_local_proc_running() == True:
            raise ae_errors.TestCaseFail(message="Proc is still running.")
        if delayed_hello2.is_local_proc_running() == True:
            raise ae_errors.TestCaseFail(message="Proc is still running.")
        if delayed_hello3.is_local_proc_running() == True:
            raise ae_errors.TestCaseFail(message="Proc is still running.")
        if delayed_hello4.is_local_proc_running() == True:
            raise ae_errors.TestCaseFail(message="Proc is still running.")
        if delayed_hello5.is_local_proc_running() == True:
            raise ae_errors.TestCaseFail(message="Proc is still running.")
        if delayed_hello6.is_local_proc_running() == True:
            raise ae_errors.TestCaseFail(message="Proc is still running.")
        if delayed_hello7.is_local_proc_running() == True:
            raise ae_errors.TestCaseFail(message="Proc is still running.")
        if delayed_hello8.is_local_proc_running() == True:
            raise ae_errors.TestCaseFail(message="Proc is still running.")
        if delayed_hello9.is_local_proc_running() == True:
            raise ae_errors.TestCaseFail(message="Proc is still running.")
        if delayed_hello10.is_local_proc_running() == True:
            raise ae_errors.TestCaseFail(message="Proc is still running.")
        if delayed_hello11.is_local_proc_running() == True:
            raise ae_errors.TestCaseFail(message="Proc is still running.")
        if delayed_hello12.is_local_proc_running() == True:
            raise ae_errors.TestCaseFail(message="Proc is still running.")
        
                
    def post_execute(self):
        pass