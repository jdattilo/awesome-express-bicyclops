import os
import sys
import time
import test_procedures
from ae import ae_errors
from test_cases import TestCase



class simple_api_request(TestCase.TestCase):
    """
       A simple api request test
    """
    
    def pre_execute(self):
        pass

    def main_execute(self):      
        
        tp = test_procedures.example_procedures.hcc_api.SimpleRequest(self.sut, self.suite_config)
        tp.run()
                
        
    def post_execute(self):
        pass