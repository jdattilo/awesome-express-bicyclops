import test_procedures
from test_cases import TestCase


class memory_tracker(TestCase.TestCase):
    """
     Quick test that starts a memory tracking procedure and
     infinitly runs little fio jobs.
     
     This test was used on a 5-day run to investigate
     any AE2 memory leak issues on the driver and SUT.
    """  
        
    def pre_execute(self):
        pass     
    

    def main_execute(self):      
       
        # this is assigns n1 to be the first node in the SUT's node list 
        n1 = self.sut.nodes[0]
        file1 = '/tmp/fio_1.file'
        stdout = 'stdout'

        mem = test_procedures.example_procedures.sys_info.MemoryLogger(self.sut, self.suite_config)
        mem.run_asynch(node=n1)

        i = 1
        while True:
            self.log.debug("Starting the long FIO job. Cycle: [%s]"%i)        
            fio1 = test_procedures.sys_ops.iogen.generate.RunFIO(self.sut, self.suite_config) 
            fio1.run(node=n1,
                            size=1000,
                            block_size='4k',
                            filename=file1,
                            output=stdout,
                            rw='rw')
            
            rem = test_procedures.sys_ops.fs.RemoveFiles(self.sut, self.suite_config)
            rem.run(node=n1,files=file1)
            
            i += 1
        
        # we'll never get here...
        mem.stop
    
    def post_execute(self):
        pass