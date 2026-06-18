import os
import sys
import time
from time import sleep
from lib import constants
from test_procedures import TestProcedure, sys_ops
from test_procedures.driver import reset_node, check_nodes_alive



class EnsureRecentReboot(TestProcedure.TestProcedure):
    """
     Ensures that the node has been rebooted recently
    """
    
    class GetServerUptime(TestProcedure.TestProcedure):
        
        def action(self):
            node = self.args.get("node")
            cmd = "ssh root@%s cat /proc/uptime " % node
            self._run_shell(cmd) 
        
        def checkpoint(self):
            pass

    
    def action(self):
        node = self.args.get("node")
        
        try:
            node = self.args.get("node")
            
            tp1 = self.GetServerUptime(self.sut, self.suite_config)
            pro = tp1.run(node=node)
            
            sec = pro.shell_stdout.split(" ")[0]
            minutes = float(sec)/60
            
            # if the server hasn't been down in the past two minutes,
            # we need to wait for it to go down
            if minutes > 3:
                tp3 = WaitForNodeDown(self.sut, self.suite_config)
                tp3.run_asynch(node=node)
                tp2 = reset_node.Reboot(self.sut, self.suite_config)
                tp2.run(node=node)
                tp3.wait(timeout=300)
                
        except:
            pass
        
    def checkpoint(self):
        pass
    

class WaitForNodeDown(TestProcedure.TestProcedure):
    """ 
        Waits for the node to go down.
        Only runs synchronous
    """
    
    def action(self):
        """
            Does an infinite echo loop and waits for the machine to go down
            and the command to fail ssh disconnection.
        """
        node = self.args.get("node")
        poll = self.args.get("poll", 5)
        timeout = self.args.get("timeout", 600)

        timeout=max(timeout,200)
        ping_node = sys_ops.network.PingNode(self.sut, self.suite_config)
        t=poll 
 

        while t < timeout:
            ping_node_pro = ping_node.run(ping_node=node)
            if ping_node_pro.shell_ret_code != 0 and ping_node_pro.shell_ret_code != None:
               self._ret_code = ping_node_pro.shell_ret_code
               break
            time.sleep(poll)
            t+=poll

        if self._ret_code == None or self._ret_code == 0:
           msg="node=[%s] did not go down" % node
           raise Exception(msg)

    def checkpoint(self):
        pass

class WaitForNodeAlive(TestProcedure.TestProcedure):
    """
     Waits for the node to reboot and come back online.
     Once back up, this  is set to automatically restart
     the Pyro service on the node.
     To disable this set::

         restart_pyro = "False"

    """ 
    
    def action(self):
        
        node = self.args.get("node")
        restart_pyro = self.args.get("restart_pyro", "True") 
        
        #tp3 = EnsureRecentReboot(self.sut, self.suite_config)
        #tp3.run(node=node)

        # run until the node comes back up
        while True:
            try:
                tp1 = check_nodes_alive.CheckNodesAlive(self.sut, self.suite_config)
                tp1.run(nodes=node)
                self.log.info("Node [%s] is alive"%node)
                #restart the pyro service on the node
                if restart_pyro != "False":
                    try:
                        from ae import pyro_driver
                        self.log.info("Starting pyro on [%s]"%node)
                        p = pyro_driver.Pyro(self.sut)
                        p.start_proc_caller_on_node(node)
                        wait_for_pyro = 30
                        self.log.info("Waiting %s seconds for Pyro to start"%wait_for_pyro)
                        sleep(wait_for_pyro)
                        self.log.info("Pyro started on [%s]"%node)
                    except Exception, ex:
                        self.log.error("Error starting pyro:%s"%ex)
                        raise ex
                return
            except:
                sleep(constants.REBOOT_INTERVAL)
            
        
    def checkpoint(self):
        pass

    
