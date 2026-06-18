import sys
import os
import test_procedures
from test_cases import TestCase

class setup(TestCase.TestCase):
    
        
    def pre_execute(self):
        pass     
    

    def main_execute(self):      

        tp0 = test_procedures.cluster.setup_cluster.CheckClusterNotRunning(self.sut, self.suite_config)
        tp0.run(node=self.sut.nodes[0])

        build_source = self.sut.build_src.rstrip('/') # Remove trailing slashes

        # Make sure BUILD_DIR: exists
        tpMakeBuildDir = test_procedures.cluster.setup_cluster.MakeBuildDir(self.sut, self.suite_config)
        tpMakeBuildDir.run(node=self.sut.nodes[0])

        if build_source.endswith(".tar.gz"):
            # Download and unpack
            tpDownload = test_procedures.cluster.setup_cluster.DownloadTgz(self.sut, self.suite_config)
            tpDownload.run(node=self.sut.nodes[0])
            tpUnpack = test_procedures.cluster.setup_cluster.UnpackTgz(self.sut, self.suite_config)
            tpUnpack.run(node=self.sut.nodes[0])

        #tp1 = test_procedures.cluster.setup_cluster.CheckoutRNA(self.sut, self.suite_config)        
        #tp1.run(node=self.sut.nodes[0])
        
        #tp2 = test_procedures.cluster.setup_cluster.BuildRNA(self.sut, self.suite_config)        
        #tp2.run(node=self.sut.nodes[0])

        tp3 = test_procedures.cluster.setup_cluster.InstallRNA(self.sut, self.suite_config)        
        tp3.run(node=self.sut.nodes[0])

        tpCheckClusterID = test_procedures.cluster.setup_cluster.CheckClusterID(self.sut, self.suite_config)
        temp_pro = tpCheckClusterID.run(node=self.sut.nodes[0])
        if temp_pro.shell_ret_code == 0:
            pass
        else:
            tpClusterInit = test_procedures.cluster.setup_cluster.ClusterInit(self.sut, self.suite_config)
            tpClusterInit.run(node=self.sut.nodes[0])

        tp4 = test_procedures.cluster.control.StartCache(self.sut, self.suite_config)        
        tp4.run(node=self.sut.nodes[0])

        # configure
        
        
    def post_execute(self):
        pass
    

if __name__ == "__main__":
    pass
