import test_procedures
from test_cases import TestCase
import time

class hello_local_sync_remote_sync(TestCase.TestCase):
    
        
    def pre_execute(self):
        pass     
    

    def main_execute(self):      
       
        # this is assigns n1 to be the first node in the SUT's node list 
        n1 = self.sut.nodes[0]
        wait_time = 30
        
        delayed_hello1 = test_procedures.example_procedures.hello_world.DelayedHelloWithRemote(self.sut, self.suite_config)
        delayed_hello1.run(**self.args)
        delayed_hello2 = test_procedures.example_procedures.hello_world.DelayedHelloWithRemote(self.sut, self.suite_config)
        delayed_hello2.run(**self.args)
        delayed_hello3 = test_procedures.example_procedures.hello_world.DelayedHelloWithRemote(self.sut, self.suite_config)
        delayed_hello3.run(**self.args)
        delayed_hello4 = test_procedures.example_procedures.hello_world.DelayedHelloWithRemote(self.sut, self.suite_config)
        delayed_hello4.run(**self.args)
        delayed_hello5 = test_procedures.example_procedures.hello_world.DelayedHelloWithRemote(self.sut, self.suite_config)
        delayed_hello5.run(**self.args)
        delayed_hello6 = test_procedures.example_procedures.hello_world.DelayedHelloWithRemote(self.sut, self.suite_config)
        delayed_hello6.run(**self.args)
        delayed_hello7 = test_procedures.example_procedures.hello_world.DelayedHelloWithRemote(self.sut, self.suite_config)
        delayed_hello7.run(**self.args)
        delayed_hello8 = test_procedures.example_procedures.hello_world.DelayedHelloWithRemote(self.sut, self.suite_config)
        delayed_hello8.run(**self.args)
        delayed_hello9 = test_procedures.example_procedures.hello_world.DelayedHelloWithRemote(self.sut, self.suite_config)
        delayed_hello9.run(**self.args)
        delayed_hello10 = test_procedures.example_procedures.hello_world.DelayedHelloWithRemote(self.sut, self.suite_config)
        delayed_hello10.run(**self.args)
        delayed_hello11 = test_procedures.example_procedures.hello_world.DelayedHelloWithRemote(self.sut, self.suite_config)
        delayed_hello11.run(**self.args)
        delayed_hello12 = test_procedures.example_procedures.hello_world.DelayedHelloWithRemote(self.sut, self.suite_config)
        delayed_hello12.run(**self.args)
        
        
    
    def post_execute(self):
        pass