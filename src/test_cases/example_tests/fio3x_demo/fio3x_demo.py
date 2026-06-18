import sys
import os
import test_procedures
from ae import ae_errors
from test_cases import TestCase


class fio3x_demo(TestCase.TestCase):
    """
        A 2-node test where we setup start concurrent IO loads (using FIO)
        a 
        
    """
    
        
    def pre_execute(self):
        
        if len(self.sut.nodes) < 2:
            msg = "We need at least two nodes for this test"
            raise ae_errors.TestCaseError(self.sut, message=msg)
        
    

    def main_execute(self):      
        files = []
        
        setattr(self, "n1",self.sut.nodes[0])
        setattr(self, "n2",self.sut.nodes[1])
        
        # our lists of FIO output and data file names        
        ofiles = ["/tmp/fio_1.out", "/tmp/fio_2.out", "/tmp/fio_3.out"]
        ffiles = ["/tmp/fio_1.file","/tmp/fio_2.file","/tmp/fio_3.file"]

        # build a comprehensive file list for cleanup and persist lists to class
        files.extend(ofiles)
        files.extend(ffiles)
        setattr(self, "files",files)
        setattr(self, "ofiles",ofiles)
        
        self.args.update({"output":ofiles[0], "filename":ffiles[0]})
        fio1 = test_procedures.sys_ops.iogen.generate.RunFIO(self.sut, self.suite_config) 
        fio1.run_asynch(node=self.n1, **self.args)
        fio2 = test_procedures.sys_ops.iogen.generate.RunFIO(self.sut, self.suite_config)
        fio2.run_asynch(node=self.n2, **self.args)
        
        self.args.update({"output":ofiles[1], "filename":ffiles[1]})
        
        fio3 = test_procedures.sys_ops.iogen.generate.RunFIO(self.sut, self.suite_config)
        fio3.run_asynch(node=self.n1, **self.args)
        
        fio4 = test_procedures.sys_ops.iogen.generate.RunFIO(self.sut, self.suite_config)
        fio4.run_asynch(node=self.n2, **self.args)
        
        self.args.update({"output":ofiles[2], "filename":ffiles[2]})
        fio5 = test_procedures.sys_ops.iogen.generate.RunFIO(self.sut, self.suite_config)
        fio5.run_asynch(node=self.n1, **self.args)
        fio6 = test_procedures.sys_ops.iogen.generate.RunFIO(self.sut, self.suite_config)
        fio6.run_asynch(node=self.n2, **self.args)
        
        p1 = fio1.wait()
        p2 = fio2.wait()
        p3 = fio3.wait()
        p4 = fio4.wait()
        p5 = fio5.wait()
        p6 = fio6.wait()
        
        self.log.info("PRO from P1: %s"%p1)

        
    def post_execute(self):
        
        # read the contents of our FIO output files
        for i in [0, 1]:
            for ofile in self.ofiles:
                n = self.sut.nodes[i]
                rtp = test_procedures.sys_ops.fs.ReadFile(self.sut, self.suite_config) 
                content = rtp.run(node=n, target=ofile)
                self.log.info("NODE [%s]FIO OUTPUT:%s"%(n,content.output))
            
            # remove all the data and output files FIO created 
            rem = test_procedures.sys_ops.fs.RemoveFiles(self.sut, self.suite_config)
            rem.run(node=n,files=self.files)
        
        
        
        
