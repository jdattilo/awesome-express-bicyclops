import sys
import os
import time
import test_procedures
from ae import ae_errors
from test_cases import TestCase


class fw_test(TestCase.TestCase):
    """
     Test that exercises core framework functionality
    """
    
        
    def pre_execute(self):
        pass

    def main_execute(self):
        
        n1 = self.sut.nodes[0]
        
        #1 Hello world local
        hello = test_procedures.example_procedures.hello_world.HelloWorld(self.sut, self.suite_config)
        my_pro = hello.run()
        if not "Hello World" in my_pro.shell_stdout:
            raise ae_errors.TestCaseFail(message="Pro is incorrect:%s"%my_pro.shell_stdout)
        if hello.is_running() == True:
            raise ae_errors.TestCaseFail(message="Should not still be running!")
        
        #2 Hello world remote
        hello = test_procedures.example_procedures.hello_world.HelloWorld(self.sut, self.suite_config)
        my_pro = hello.run(node=n1)
        if not "Hello World" in my_pro.shell_stdout:
            raise ae_errors.TestCaseFail(message="Pro is incorrect:%s"%my_pro.shell_stdout)
        if hello.is_running() == True:
            raise ae_errors.TestCaseFail(message="Should not still be running!")
        
        #3 a synchronous local delayed hello world
        tps = []
        for i in range(16):
            dh = test_procedures.example_procedures.hello_world.DelayedHelloWorld(self.sut, self.suite_config)
            dh.run_asynch(**self.args)
            tps.append(dh)
        time.sleep(2)
        wait_time = 30
        for tp in dh:
            pro  = tp.wait(timeout=wait_time)
        
        #4 a synchronous remote delayed hello world
        for i in range(16):
            dh = test_procedures.example_procedures.hello_world.DelayedHelloWorld(self.sut, self.suite_config)
            dh.run_asynch(node=n1, **self.args)
            tps.append(dh)
        time.sleep(2)
        wait_time = 30
        for tp in dh:
            pro  = tp.wait(timeout=wait_time)
 
        long_job = test_procedures.example_procedures.hello_world.DelayedHelloWorld(self.sut, self.suite_config)
        long_job2 = test_procedures.example_procedures.hello_world.DelayedHelloWorld(self.sut, self.suite_config)
        long_job3 = test_procedures.example_procedures.hello_world.DelayedHelloWorld(self.sut, self.suite_config)
        
        some_args= {"sleep_time": 60}
        long_job.run_asynch(**some_args)

        self.log.info("Long job is off and running....")
        self.log.info("Sleeping 5 seconds...")
        time.sleep(5)
        
        if long_job.is_running() == True:
            self.log.info("Long job is verified running. Now stopping...")
            long_job.stop()

        _time = 0
        while long_job.is_running() == True:
            time.sleep(0.25)
            _time += 0.25
        if long_job.is_running() == True:
            raise ae_errors.TestCaseFail(message="The job was not stopped.")
        else:
            self.log.info("Long job was stopped successfully in [%s] seconds."%_time)
            pro = long_job.wait(30)
            if "stuff" in pro.shell_stdout:
                self.log.info("Partial PRO looked good for long_job1")
            else:
                raise ae_errors.TestCaseFail(message="PRO was missing a partial value.")
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
            raise ae_errors.TestCaseFail(message="The job was not stopped.")
        else:
            self.log.info("Long job2 was stopped successfully in [%s] seconds."%_time)
            pro = long_job2.wait(30)
            if "stuff" in pro.shell_stdout:
                self.log.info("Partial PRO looked good long_job2")
            else:
                raise ae_errors.TestCaseFail(message="PRO was missing a partial value.")
            
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
            raise ae_errors.TestCaseFail(message="The job was not stopped.")
        else:
            self.log.info("Long job3 was stopped successfully in [%s] seconds."%_time)
            pro = long_job3.wait(30)
            if "stuff" in pro.shell_stdout:
                self.log.info("Partial PRO looked good long_job3")
            else:
                raise ae_errors.TestCaseFail(message="PRO was missing a partial value.")       
        
    def post_execute(self):
        pass