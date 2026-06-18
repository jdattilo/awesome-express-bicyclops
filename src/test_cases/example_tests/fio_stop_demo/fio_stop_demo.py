import os
import sys
import time
import test_procedures
from ae import ae_errors
from test_cases import TestCase



class fio_stop_demo(TestCase.TestCase):
    """
        A 2-node test where concurrent FIO loads are started on the
        nodes and the procedures stopped with the partial return 
        values (PRO's) returned back.
    """
    
        
    def pre_execute(self):
        
        if len(self.sut.nodes) < 2:
            msg = "We need at least two nodes for this test"
            raise ae_errors.TestCaseError(self.sut, message=msg)
        

    def main_execute(self):      
        
        files = []
        n1 = self.sut.nodes[0]
        n2 = self.sut.nodes[1]
        
        # set our data files, fio output will be piped to stdout
        file1 = '/tmp/fio_1.file'
        file2 = '/tmp/fio_2.file'
        files.append(file1)
        files.append(file2)
        stdout = 'stdout'
        
        
        # start a large, long-running FIO process on each node
        self.log.debug("Starting the long FIO jobs")
        fio1 = test_procedures.sys_ops.iogen.generate.RunFIO(self.sut, self.suite_config) 
        fio1.run_asynch(node=n1,
                        size=500,
                        block_size='4k',
                        filename=file1,
                        output=stdout,
                        rw='rw')
        
        fio2 = test_procedures.sys_ops.iogen.generate.RunFIO(self.sut, self.suite_config)
        fio2.run_asynch(node=n2,
                        size=500,
                        block_size='4k',
                        filename=file1,
                        output=stdout,
                        rw='rw')
                
        
        # Now we start a smaller, quick FIO jobs on the nodes
        self.log.debug("Starting the quick FIO jobs")
        fio3 = test_procedures.sys_ops.iogen.generate.RunFIO(self.sut, self.suite_config)
        fio3.run_asynch(node=n1,
                        size=50,
                        block_size='8k',
                        filename=file2,
                        output=stdout,
                        rw='rw')
        
        fio4 = test_procedures.sys_ops.iogen.generate.RunFIO(self.sut, self.suite_config)
        fio4.run_asynch(node=n2,
                        size=50,
                        block_size='8k',
                        filename=file2,
                        output=stdout,
                        rw='rw')
        
        
        # wait for the quick jobs to end
        while fio3.is_running() or fio4.is_running():
            self.log.debug("Waiting for quick FIO jobs to stop...")
            time.sleep(5)
            
        # let's stop the long-running jobs
        self.log.info("Now stopping the long running FIO jobs.")
        pro1 = fio1.stop()
        pro2 = fio2.stop()
        
        self.log.info("Return value from [%s]: %s"%(n1,pro1))
        self.log.info("Return value from [%s]: %s"%(n2,pro2))
        
        setattr(self, "files",files)
        
        
    def post_execute(self):
        
        # Remove the FIO data files
        for i in [0, 1]:
            n = self.sut.nodes[i]
            # remove all the data and output files FIO created 
            rem = test_procedures.sys_ops.fs.RemoveFiles(self.sut, self.suite_config)
            rem.run(node=n,files=self.files)

