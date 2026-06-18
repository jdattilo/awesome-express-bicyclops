import time
import test_procedures
from test_cases import TestCase


class crash_recovery(TestCase.TestCase):
    
        
    def pre_execute(self):
        pass     
    

    def main_execute(self):      
       
        # this is assigns n1 to be the first node in the SUT's node list 
        n1 = self.sut.nodes[0]
        
        # do a little io to the tmp directory
        
        fio = test_procedures.sys_ops.iogen.sample.CreateFioSample(self.sut, self.suite_config)
        filename = "/tmp/fio_test.file"
        output = "/tmp/fio_example.output"
        d = {"filename":filename, "output":output, "node":n1}
        self.args.update(d)

        fio.run(**self.args)
        
        tp_down = test_procedures.driver.wait_node_up_down.WaitForNodeDown(self.sut, self.suite_config)
        tp_down.run_asynch(**self.args)
        crash = test_procedures.cache.event.ungraceful_shutdown.QuickReboot(self.sut, self.suite_config)
        try:
            crash.run(**self.args)    
        except:
            self.log.info("CRASHED")
        tp_down.wait(timeout=600)
            
        # Wait for node to become alive
        tp_recover = test_procedures.driver.wait_node_up_down.WaitForNodeAlive(self.sut, self.suite_config)  
        tp_recover.run(**self.args)

        tp_hello = test_procedures.example_procedures.hello_world.HelloWorld(self.sut, self.suite_config)
        tp_hello.run(n1)
        
    
    def post_execute(self):
        pass
