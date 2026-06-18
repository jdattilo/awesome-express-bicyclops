import os
import sys
import time
import inspect
from test_procedures import TestProcedure
from lib import string_extensions


class CheckNodesAlive(TestProcedure.TestProcedure):
    """ Test procedure that does a arbitrary ssh command to the nodes
        to verify that they are alive.
        
    """ 
    
    def action(self):
        
        # if nodes is being passed in, we set it to those
        # otherwise set it to all the nodes in the SUT
        nodes = self.args.get("nodes",self.sut.nodes)
        nodes = string_extensions.string_to_list(nodes)
        
        for node in nodes:
            cmd = "ssh root@%s \"echo \"foo\" > /dev/null\"" % node
            self._run_shell(cmd)
    
    
    def checkpoint(self):
        pass


if __name__ == "__main__":
    
    from ae import loader
    
    der = os.path.dirname(sys.path[0])
    sys.path.append(os.path.join(der, '..'))
    suite_config_file = os.path.abspath(os.path.join(der, '..','suite_files','suite_ex.cfg'))
    env_conf_file = os.path.abspath(os.path.join(der, '..', 'env_files','---YOUR SUT FILE---'))
    
    
    def test_node():
        suite, sut = loader.Loader.get_run_info(suite_config_file, env_conf_file)
        
        proc3 = CheckNodesAlive(sut, suite)
        proc3.run()
        
    test_node()