import os
import sys
import time
import test_procedures

from lib import pathing
from lib import constants
from test_procedures import TestProcedure
from test_procedures import cluster 
from test_procedures import driver 
from test_cases import TestCase
from ae import ae_errors

class em_test(TestCase.TestCase):
    def pre_execute(self):
        pass

    def main_execute(self):
        autosetup_cluster_tp = cluster.hrm_config.setup.AutoSetupCluster(self.sut, self.suite_config)
        autosetup_cluster_tp.run(as_reset_cluster='hard_all',
                                 as_start_if_stopped=True,
                                 as_autoprovisioning='ssds_only')

        #tp = driver.em_smoke.StartEMSmoke(self.sut,self.suite_config)
        #tp.run(**self.args)
    
    def post_execute(self):
        pass      
