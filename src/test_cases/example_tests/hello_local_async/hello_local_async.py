import test_procedures
from test_cases import TestCase
import time

class hello_local_async(TestCase.TestCase):
    
        
    def pre_execute(self):
        pass     
    

    def main_execute(self):      
       
        wait_time = 30
        
        delayed_hello1 = test_procedures.example_procedures.hello_world.DelayedHelloWorld(self.sut, self.suite_config)
        delayed_hello1.run_asynch(**self.args)
        delayed_hello2 = test_procedures.example_procedures.hello_world.DelayedHelloWorld(self.sut, self.suite_config)
        delayed_hello2.run_asynch(**self.args)
        delayed_hello3 = test_procedures.example_procedures.hello_world.DelayedHelloWorld(self.sut, self.suite_config)
        delayed_hello3.run_asynch(**self.args)
        delayed_hello4 = test_procedures.example_procedures.hello_world.DelayedHelloWorld(self.sut, self.suite_config)
        delayed_hello4.run_asynch(**self.args)
        delayed_hello5 = test_procedures.example_procedures.hello_world.DelayedHelloWorld(self.sut, self.suite_config)
        delayed_hello5.run_asynch(**self.args)
        delayed_hello6 = test_procedures.example_procedures.hello_world.DelayedHelloWorld(self.sut, self.suite_config)
        delayed_hello6.run_asynch(**self.args)
        delayed_hello7 = test_procedures.example_procedures.hello_world.DelayedHelloWorld(self.sut, self.suite_config)
        delayed_hello7.run_asynch(**self.args)
        delayed_hello8 = test_procedures.example_procedures.hello_world.DelayedHelloWorld(self.sut, self.suite_config)
        delayed_hello8.run_asynch(**self.args)
        delayed_hello9 = test_procedures.example_procedures.hello_world.DelayedHelloWorld(self.sut, self.suite_config)
        delayed_hello9.run_asynch(**self.args)
        delayed_hello10 = test_procedures.example_procedures.hello_world.DelayedHelloWorld(self.sut, self.suite_config)
        delayed_hello10.run_asynch(**self.args)
        delayed_hello11 = test_procedures.example_procedures.hello_world.DelayedHelloWorld(self.sut, self.suite_config)
        delayed_hello11.run_asynch(**self.args)
        delayed_hello12 = test_procedures.example_procedures.hello_world.DelayedHelloWorld(self.sut, self.suite_config)
        delayed_hello12.run_asynch(**self.args)
        
        
        time.sleep(2)
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
        time.sleep(2)
        
    
    def post_execute(self):
        pass