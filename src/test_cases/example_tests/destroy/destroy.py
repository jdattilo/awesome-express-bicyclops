import sys
import os
import test_procedures
from test_cases import TestCase

class destroy(TestCase.TestCase):
        
    def pre_execute(self):
        pass     

    def main_execute(self):
                
        destroy = test_procedures.cluster.destroy_cluster.DestroyCluster(self.sut, self.suite_config)
        destroy.run(node=self.sut.nodes[0])
        
    def post_execute(self):
        pass
    

if __name__ == "__main__":
    pass
