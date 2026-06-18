import sys
import os
import test_procedures
from test_cases import TestCase


class fio_example(TestCase.TestCase):
    
        
    def pre_execute(self):
        pass     
    

    def main_execute(self):      
        
        
        tp = test_procedures.sys_ops.iogen.generate.RunFIO(self.sut, self.suite_config)
        
        # Check to see if we have any test case data from the suite file          
        # Data can be .dat files and/or other VARS from the suite file 
        if self.args:
            
            # Option 1: 
            # Pass in all the args from the suite file
            # print "Running as data-driven..."
            # tp.run(**self.args)
            
            
            # Option 2:
            # Pass in the args  as data but update (hardcode) some of them.
            #
            # NOTE: This will stomp the specific args if they were included in the suite file.
            #
            # So in this example, we are hardcoding filename and output parameters
            # regardless of they are specified as in the suite file
            #
            filename = "/tmp/fio_test.file"
            output = "/tmp/fio_example.output"
            d = {"filename":filename, "output":output}
            self.args.update(d)
            
            self.log.debug("Running as data-driven with updated output")
            tp.run(node=self.sut.nodes[0],**self.args)
            
        else:
            # Option 3:
            # Or we can hardcode all the fio parameters like this
            #self.log.debug("Running with hardcoded options....")
            #tp.run(size="100", block_size="4k", filename="/tmp/fio.data", output="/tmp/fio_example.output")
            
            # if we want do this, and need these values later, they can be "saved" 
            # to the testcase object like this
            setattr(self, "filename","/tmp/fio.data" )
            setattr(self, "output","/tmp/fio_example.output" )            
            #and then referenced like just another member like so
            self.log.debug( "My saved filename [%s]"%self.filename)
            self.log.debug( "My saved output [%s]"%self.output)
        
        
    def post_execute(self):
        pass
