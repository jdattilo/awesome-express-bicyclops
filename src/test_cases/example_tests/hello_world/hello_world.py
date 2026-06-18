import test_procedures
from test_cases import TestCase
from test_procedures import cluster
from ae import ae_errors
import time

class hello_world(TestCase.TestCase):
    
        
    def pre_execute(self):
        self.log.info('Auto Setup cluster setup')

        tp_down = test_procedures.driver.wait_node_up_down.WaitForNodeDown(self.sut, self.suite_config)
        tp_down.run_asynch(self.sut.nodes[0])
        tp_down.wait()

    def main_execute(self):      
       
        # this is assigns n1 to be the first node in the SUT's node list 
        n1 = self.sut.nodes[0]
        
        # whenever we initialize a new test procedure, we pass in the SUT and suite objects
        hello = test_procedures.example_procedures.hello_world.HelloWorld(self.sut, self.suite_config)
        my_pro = hello.run(node=n1)
        
        if not "Hello World" in my_pro.shell_stdout:
            raise ae_errors.TestCaseFail(message="Pro is incorrect:%s"%my_pro.shell_stdout)
        
        if hello.is_running() == True:
            raise ae_errors.TestCaseFail(message="Should not still be running!")
        else:
            self.log.info("Yay - it's not running.")
        
    def post_execute(self):
        pass
