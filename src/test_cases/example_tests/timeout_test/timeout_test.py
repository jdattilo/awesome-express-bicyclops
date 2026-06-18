import test_procedures
from test_cases import TestCase
import ae
import time
from ae import ae_errors

class timeout_test(TestCase.TestCase):
    
        
    def pre_execute(self):
        pass     
    

    def main_execute(self):      
       
        # this is assigns n1 to be the first node in the SUT's node list 
        n1 = self.sut.nodes[0]
        
        # create an arg list with the node and sleep time of 60
        # the timeout is set to 10 seconds to force a procedure timeout error
        
        some_args= {"sleep_time": 60, "timeout":5}
        
        # 1. is a local synchronous test
        self.log.info("TEST 1: Starting the local synch timeout test")
        long_job = test_procedures.example_procedures.hello_world.DelayedHelloWorld(self.sut, self.suite_config)
        got_timeout_error = False
        try:
            long_job.run(**some_args)
        except ae.ae_errors.TestCaseError:
            got_timeout_error = True
        if got_timeout_error == False:
            raise ae_errors.TestProcedureFail(message="We didn't receive a timeout error.")    
        
        
        # 2. a local asynchronous running timeout
        self.log.info("TEST 2: Starting the local asynch timeout test")
        long_job2 = test_procedures.example_procedures.hello_world.DelayedHelloWorld(self.sut, self.suite_config)
        try:
            long_job2.run_asynch(**some_args)   # the error is raised in the asynch process
            time.sleep(5)
            long_job2.wait()                    # but it doesn't affect the main thread until wait()
            time.sleep(5)
        except ae.ae_errors.TestCaseError:
            got_timeout_error = True
        if got_timeout_error == False:
            raise ae_errors.TestProcedureFail(message="We didn't receive a timeout error.")    
        
        
        # 3. is a local asynchronous wait timeout
        self.log.info("TEST 3: Starting the local asynch wait timeout test")
        long_job3 = test_procedures.example_procedures.hello_world.DelayedHelloWorld(self.sut, self.suite_config)
        
        # new args - NOTE: We're not setting a proc run timeout
        some_args= {"sleep_time": 60}
        try:
            long_job3.run_asynch(**some_args)       # no error will be raised this time
            long_job3.wait(5)                       # but wait will timeout
        except ae.ae_errors.TestCaseError:
            got_timeout_error = True
        if got_timeout_error == False:
            raise ae_errors.TestProcedureFail(message="We didn't receive a timeout error.")
        
        
        # 4. is a remote synchronous test
        self.log.info("TEST 4: Starting the remote synch timeout test")
        long_job4 = test_procedures.example_procedures.hello_world.DelayedHelloWorld(self.sut, self.suite_config)
        
        some_args= {"node":n1,"sleep_time": 60, "timeout":5}
        try:
            long_job4.run(**some_args)       # no error will be raised this time
        except ae.ae_errors.TestCaseError:
            got_timeout_error = True
        if got_timeout_error == False:
            raise ae_errors.TestProcedureFail(message="We didn't receive a timeout error.")
       
        some_args= {"node":n1,"sleep_time": 60, "timeout":5}
        # 5. a remote asynchronous running timeout
        self.log.info("TEST 5: Starting the remote asynch timeout test")
        long_job5 = test_procedures.example_procedures.hello_world.DelayedHelloWorld(self.sut, self.suite_config)
        try:
            long_job5.run_asynch(**some_args)   # the error is raised in the asynch process
            time.sleep(5)
            long_job5.wait()                    # but it doesn't affect the main thread until wait()
            time.sleep(5)
        except ae_errors.TestCaseError:
            got_timeout_error = True
        if got_timeout_error == False:
            raise ae_errors.TestProcedureFail(message="We didn't receive a timeout error.")    

        
        # 6. is a remote asynchronous wait timeout
        self.log.info("TEST 6: Starting the remote asynch wait timeout test")
        long_job6 = test_procedures.example_procedures.hello_world.DelayedHelloWorld(self.sut, self.suite_config)
        some_args= {"node":n1,"sleep_time": 60}
        try:
            long_job6.run_asynch(**some_args)       # no error will be raised this time
            time.sleep(5)
            long_job6.wait(5)                       # but wait will timeout
        except ae.ae_errors.TestCaseError:
            got_timeout_error = True
        if got_timeout_error == False:
            raise ae_errors.TestProcedureFail(message="We didn't receive a timeout error.")
        
        while long_job6.is_running() == True:
            self.log.info("Waiting for long_job6 to stop")
            time.sleep(3)

        self.log.info("--- ALL DONE ---")
    def post_execute(self):
        pass