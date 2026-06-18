import test_procedures
from test_cases import TestCase
from ae import ae_errors
import time

class helper_method(TestCase.TestCase):
    """
     A quick test that executes the simple HelloWorld procedure 
     synchronously on each node in the SUT
    """
        
    def pre_execute(self):
        pass     
    
    def main_execute(self):      
        
        tp1 = test_procedures.example_procedures.hello_world.HelperExample(self.sut, self.suite_config)
        res = tp1.run().helper_to_lower()
        self.log.info("Local Result:%s"%res)
        
        tp2 = test_procedures.example_procedures.hello_world.HelperExample(self.sut, self.suite_config)
        res = tp2.run(node=self.sut.nodes[0]).helper_to_lower()
        self.log.info("Remote Result:%s"%res)
        
        tp3 = test_procedures.example_procedures.hello_world.HelperExample(self.sut, self.suite_config)
        tp3.run_asynch()
        res = tp3.wait().helper_to_lower()
        self.log.info("Local asynch Result:%s"%res)
        
        tp4 = test_procedures.example_procedures.hello_world.HelperExample(self.sut, self.suite_config)
        tp4.run_asynch(node=self.sut.nodes[0])
        res = tp4.wait()
        self.log.info("Remote asynch lower Result:%s"%res.helper_to_lower())
        self.log.info("Remote asynch upper Result:%s"%res.helper_to_upper())
        
                
    def post_execute(self):
        pass