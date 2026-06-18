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
from ae.environment import NODE_ROLES

class em_dc_reset(TestCase.TestCase):
    
    cluster_nodes = []

    def pre_execute(self):

        VALID_HRM_CLUSTER_ROLES = set([NODE_ROLES.BC, NODE_ROLES.CFM, NODE_ROLES.CS, NODE_ROLES.MD])
        for possible_cluster_node in self.sut.nodes:
            node_roles = set(possible_cluster_node.roles)
            if node_roles & VALID_HRM_CLUSTER_ROLES:
                self.cluster_nodes.append(possible_cluster_node)
                
    def main_execute(self):

        files = []
        files.append('/opt/dell/fluidcache/agent/RECV.log')
        files.append('/opt/dell/fluidcache/agent/SENT.log')
        files.append('/opt/dell/fluidcache/agent/TEST.log')
        files.append('/opt/dell/fluidcache/cfm/RECV.log')
        files.append('/opt/dell/fluidcache/cfm/SENT.log')
        files.append('/opt/dell/fluidcache/cfm/TEST.log')


        self.log.info("Resetting DC and removing DC files")
        tp = driver.em_dc_reset.EmDCReset(self.sut,self.suite_config)
        tp.run()

        self.log.info("Remove TEST RECV SENT log files")
        for cluster_node in self.cluster_nodes:
            rm = test_procedures.sys_ops.fs.RemoveFiles(self.sut, self.suite_config)
            rm.run(node=cluster_node, files=files)
            
    def post_execute(self):
        pass      
