import os
import sys 
from lib import constants
from test_procedures import TestProcedure
from test_procedures.driver import check_nodes_alive
import test_procedures
import copy

class Init6(TestProcedure.TestProcedure):
    """ 
    """ 
    
    def action(self):
        
        node = self.args.get("node")
        cmd = "ssh -o ConnectTimeout=%s root@%s init 6 "%(self.timeout, node)
        self._run_shell(cmd)
    
    
    def checkpoint(self):
        pass
    
class Reboot(TestProcedure.TestProcedure):
    """ 
    """ 
    
    def action(self):
        
        node = self.args.get("node")
        cmd = "ssh -o ConnectTimeout=%s root@%s reboot "%(self.timeout, node)
        self._run_shell(cmd)
    
    
    def checkpoint(self):
        pass
        
class FluidCacheReboot(TestProcedure.TestProcedure):
    """ 
    """ 
    
    def action(self):
        
        node = self.args.get("node")
       # Disabling chkconfig on temporarily to avoid breaking of the tests 
       # chkconfig_tp = test_procedures.cluster.control.ChkConfigOn(self.sut, self.suite_config)
       # chkconfig_tp.run(node=node,
       #                           service=constants.AGENT_DAEMON)
                                  
        reboot_tp = test_procedures.driver.reset_node.Reboot(self.sut, self.suite_config)
        reboot_tp.run(node=node)  

  
    
    def checkpoint(self):
        pass

class SbinHardReboot(TestProcedure.TestProcedure):
    """ 
    """ 
    
    def action(self):
        
        node = self.args.get("node")
        cmd = "ssh -o ConnectTimeout=%s root@%s /sbin/reboot -f -n"%(self.timeout, node)
        self._run_shell(cmd)
    
    
    def checkpoint(self):
        pass

class IdracPowerCycle(TestProcedure.TestProcedure):
    """ 
    """ 
    
    def action(self):
        
        node = self.args.get("node") 
        if isinstance(node, str): 
            node_c = node
            node_c1 = copy.copy(node)
            node_fields = node_c1.split('.')
            node_fields[0] = node_fields[0] + ('c')
            node_c = node_fields[0] + '.' + node_fields[1] + '.' + node_fields[2] 
        else:
            node_c = node.get_hostname_only()
            node_c += 'c'
        #node_c1 = copy.copy(node)
        #node_c1.split('.')
        #node_c1[0].append('c')
        #node_c = node_c1[0] + '.' + node_c1[1] + '.' + node_c1[2] 
        cmd = "ssh -o ConnectTimeout=%s root@%s racadm serveraction powercycle"%(self.timeout, node_c)
        self._run_shell(cmd)
    
    
    def checkpoint(self):
        pass

class IdracHardReset(TestProcedure.TestProcedure):
    """ 
    """ 
    
    def action(self):
        
        node = self.args.get("node") 
        if isinstance(node, str): 
            node_c = node
            node_c1 = copy.copy(node)
            node_fields = node_c1.split('.')
            node_fields[0] = node_fields[0] + ('c')
            node_c = node_fields[0] + '.' + node_fields[1] + '.' + node_fields[2] 
        else:
            node_c = node.get_hostname_only()
            node_c += 'c'
        #node_c1 = copy.copy(node)
        #node_c1.split('.')
        #node_c1[0].append('c')
        #node_c = node_c1[0] + '.' + node_c1[1] + '.' + node_c1[2] 
        cmd = "ssh -o ConnectTimeout=%s root@%s racadm serveraction hardreset"%(self.timeout, node_c)
        self._run_shell(cmd)
    
    
    def checkpoint(self):
        pass
