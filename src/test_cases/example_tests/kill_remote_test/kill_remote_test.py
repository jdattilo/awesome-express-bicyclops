import test_procedures
from test_cases import TestCase
import ae
import time

class kill_remote_test(TestCase.TestCase):
    
        
    def pre_execute(self):
        pass     
    

    def main_execute(self):      
       
        # this is assigns n1 to be the first node in the SUT's node list 
        n1 = self.sut.nodes[0]
        
        long_job = test_procedures.example_procedures.hello_world.DelayedHelloWorld(self.sut, self.suite_config)
        long_job2 = test_procedures.example_procedures.hello_world.DelayedHelloWorld(self.sut, self.suite_config)
        long_job3 = test_procedures.example_procedures.hello_world.DelayedHelloWorld(self.sut, self.suite_config)
        
        some_args= {"node":n1, "sleep_time": 60}
        long_job.run_asynch(**some_args)

        self.log.info("Long job is off and running....")
        self.log.info("Sleeping 5 seconds...")
        time.sleep(5)
        
        if long_job.is_running() == True:
            self.log.info("Long job is verified running. Now stopping...")
        else:
            raise ae.ae_errors.TestCaseFail(message="Long job is NOT running. ")
        
        long_job.stop()

        _time = 0
        while long_job.is_running() == True:
            time.sleep(0.25)
            _time += 0.25
        if long_job.is_running() == True:
            raise ae.ae_errors.TestCaseFail(message="The job was not stopped.")
        else:
            self.log.info("Long job was stopped successfully in [%s] seconds."%_time)
            pro = long_job.wait(30)
            if "stuff" in pro.shell_stdout:
                self.log.info("Partial PRO looked good for long_job1")
            else:
                raise ae.ae_errors.TestCaseFail(message="PRO was missing a partial value.")
            
        
        long_job2.run_asynch(**some_args)
        self.log.info("Long job2 is off and running....")
        self.log.info("Sleeping 5 seconds...")
        time.sleep(5)
        if long_job2.is_running() == True:
            self.log.info("Long job is verified running. Now stopping...")
            long_job2.stop()

        _time = 0
        while long_job2.is_running() == True:
            time.sleep(0.25)
            _time += 0.25
        if long_job2.is_running() == True:
            raise ae.ae_errors.TestCaseFail(message="The job was not stopped.")
        else:
            self.log.info("Long job2 was stopped successfully in [%s] seconds."%_time)
            pro = long_job2.wait(30)
            if "stuff" in pro.shell_stdout:
                self.log.info("Partial PRO looked good long_job2")
            else:
                raise ae.ae_errors.TestCaseFail(message="PRO was missing a partial value.")
            
        long_job3.run_asynch(**some_args)
        time.sleep(2)
        if long_job3.is_running() == True:
            self.log.info("Long job is verified running. Now stopping...")
            long_job3.stop()

        _time = 0
        while long_job3.is_running() == True:
            time.sleep(0.25)
            _time += 0.25
        if long_job3.is_running() == True:
            raise ae.ae_errors.TestCaseFail(message="The job was not stopped.")
        else:
            self.log.info("Long job3 was stopped successfully in [%s] seconds."%_time)
            pro = long_job3.wait(30)
            if "stuff" in pro.shell_stdout:
                self.log.info("Partial PRO looked good long_job3")
            else:
                raise ae.ae_errors.TestCaseFail(message="PRO was missing a partial value.")
        
    def post_execute(self):
        pass