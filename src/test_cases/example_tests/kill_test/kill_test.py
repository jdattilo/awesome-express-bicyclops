import test_procedures
from test_cases import TestCase
import ae
import time

class kill_test(TestCase.TestCase):
    
        
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
        self.log.info("Sleeping 2 seconds...")
        time.sleep(2)
        
        if long_job.is_running() == True:
            self.log.info("Long job is verified running...")
            self.log.info("Long job is being stopped...")
            long_job.stop_remote()
            self.log.info("Sleeping 3 seconds...")
            time.sleep(3)
        
        if long_job.is_running() == True:
            raise ae.ae_errors.TestCaseFail(message="The job was not stopped.")
        else:
            self.log.info("Long job was stopped successfully.")
            
        time.sleep(60)
        """
        long_job2.run_asynch(**some_args)
        self.log.info("Long job2 is off and running....")
        self.log.info("Sleeping 2 seconds...")
        time.sleep(2)
        if long_job2.is_running() == True:
            self.log.info("Long job2 is verified running...")
            self.log.info("Long job2 is being killed...")
            long_job2.kill_remote()
            self.log.info("3 second sleep")
            time.sleep(3)
        if long_job2.is_running() == True:
            raise ae.ae_errors.TestCaseFail(message="The job2 was not killed.")
        else:
            self.log.info("Long job2 was killed successfully.")
            
        long_job3.run_asynch(**some_args)
        time.sleep(2)
        if long_job3.is_running() == True:
            self.log.info("Long job3 is verified running...")
            self.log.info("Long job3 is being killed and will wait until stopped...")
            long_job3.kill_remote(True, 30)
        if long_job3.is_running() == True:
            raise ae.ae_errors.TestCaseFail(message="The job2 was not killed.")
        else:
            self.log.info("Long job3 was killed successfully.")
        """
    def post_execute(self):
        pass