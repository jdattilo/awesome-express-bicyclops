import os
import sys
import time
import platform
import socket
import subprocess
import threading
import ae_errors
import ae_logger
from environment import Sut
from lib import network, constants, pathing
from environment import OS_TYPE
import psutil
import multiprocessing
try:
    import Pyro4
except ImportError:
    from ae.prepper import Prepper
    Prepper.install_pyro()
    

NODE_QUERY_ATTEMPTS = 10

class Pyro(object):
    """ Our Pyro wrapper class that will help us setup the Pyro
        name server, register proxies and publish our AE objects
        for remote execution. 
        For the most part these are all functions that should be
        executed on the test driver.
    """ 
    
    def __init__(self, sut):
        
        self.sut = sut
        self.pyro_daemon = None
        self.pyro_bcs = None
        self.ns_thread = None
        self.log = None
        self.parent_conn = None
        
        # DEPRECATED remove remote_pids when rkill_proc_caller_on_node is removed
        self.remote_pids = []       #list of windows only pyro_sut pids       



    def _start_ns(self, conn):
        """
         Attempts to start the Pyro nameserver
        """
        
        def _t():
            nsUri, daemon, bcserver = Pyro4.naming.startNS(host=self.sut.pyro_ns_name,
                                                   port=self.sut.pyro_ns_port,
                                                   enableBroadcast=False)
            self.pyro_daemon = daemon
            self.pyro_bcs = bcserver
            self.pyro_daemon.requestLoop()
            
        t = threading.Thread(target=_t)
        t.start()
        try:
            msg = conn.recv() 
            if  msg == "stop":
                self.pyro_daemon.shutdown()
                del self.pyro_bcs
                del self.pyro_daemon
                t.join()
            else:
                raise TypeError("Unknown message received: %s"% msg)        
        except EOFError:
            time.sleep(1)
        conn.close()
        sys.exit()

    
    def startup_pyro(self, nodes):
        """
         Starts Pyro on our driver and SUTs. This starts the Pyro nameserver
         on the test driver and then registers & publishes our test procedures
         on the SUTs.
        """
        self.start_threaded_ns()
        self.log = ae_logger.Log(self.sut.log_server, self.__class__.__name__)

        secs_to_wait = 30
        while secs_to_wait > 0:
            if self.is_ns_running():
                break
            time.sleep(1)
            secs_to_wait =- 1
        self.log.info("Pyro nameserver started with PID [%s]"% self.ns_thread.pid)
        #  Registers the objects on the nodes
        for node in nodes:
            self.log.info("Registering Pyro on [%s]"%node)
            self.start_proc_caller_on_node(node, sys.flags.debug)
            time.sleep(1)        
    
    
    def _kill_old_ns(self):
        import psutil
        pid = network.find_ports_pid(self.sut.pyro_ns_port)
        pc = psutil.Process(pid)
        pc.terminate()
    
    
    def start_threaded_ns(self):
        """ 
            Starts the name server daemon in a separate thread.
            
            NOTE:  This creates a separate nameserver "daemon" for 
            each AE test run by firing up a new thread for the 
            nameserver. This makes management of the service easier 
            since Pyro is a little clunky.
        """
        
        import signal
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        
        if self.is_ns_running() == True:
            print "Detected old nameserver process running"
            self._kill_old_ns()
            print "Previous nameserver has been terminated"
            time.sleep(5)
            
        # Check to make sure that we're starting the Pyro NS on the same machine
        # as specified in the env file.
        hostname = network.get_local_hostname()
        ip = network.get_local_ips()
        ip.append(hostname)
        if not self.sut.pyro_ns_name in ip:
            raise ae_errors.FatalError("The Pyro nameserver needs to be started locally.")
        
        parent_conn, child_conn = multiprocessing.Pipe()
        network.wait_for_port(self.sut.pyro_ns_name,self.sut.pyro_ns_port)
        self.ns_thread = multiprocessing.Process(target=self._start_ns, args=(child_conn,))
        self.ns_thread.start()
        time.sleep(1)
        self.parent_conn = parent_conn

        if self.log == None:
            self.log = ae_logger.Log(self.sut.log_server, self.__class__.__name__)
        
    
    def shutdown_pyro(self):
        """
            Shutdown Pyro stops the Pyro proc_caller objects
            on all nodes and stops the Pyro nameserver running
            on the test driver.
        """
        ns = None
        try:
            ns = Pyro4.locateNS(self.sut.pyro_ns_name, self.sut.pyro_ns_port)
        except:
            return
            print "Could not locate Pyro nameserver."
            
        for node in self.sut.nodes:
            try:
                if Pyro.is_node_up(self.sut, node) == True:
                    self.log.info("Stopping Pyro publishing on [%s]"%node)
                    #self.rkill_proc_caller_on_node(node)
                    self.stop_proc_caller_on_node(node)
                    time.sleep(0.5)
                else:
                    self.log.info("Skipping Pyro shutdown on down node [%s]"%node)
            except Exception, ex:
                self.log.warning("Pyro did not shutdown cleanly on node %s \n%s"%(node, ex))
        try:
            self.log.info("Stopping the Pyro nameserver daemon")
            if ns:
                names = ns.list()
                for name in names:
                    self.log.debug("Removing %s"%name)
                    time.sleep(0.25)
            self.kill_ns()
            ns._pyroRelease()
        except Exception, ex:
            self.log.error("Failed to stop the Pyro nameserver daemon: %s" % ex)
        
        # kills any background processes that may have issued a remote command
        # to start the proc caller (the winexe will typically hang around)
        for proc in psutil.process_iter():
            try:
                p = psutil.Process(proc.pid)
                if str(p.cmdline).find(os.path.basename('pyro_sut.py')) > 0:
                    p.kill()
            except:
                pass
        time.sleep(5)
        
        
    def kill_ns(self):
        """ Kills the nameserver daemon. Oddly enough, the Pyro nsd module doesn't have
            a STOP command.
        """
        import psutil
        
        if self.pyro_bcs != None:
            self.log.debug("Pyro BCS close...")
            self.pyro_bcs.close()
        if self.pyro_daemon != None:
            self.log.debug("Pyro Daemon shutdown....")
            self.pyro_daemon.shutdown()
        
        try:
            self.parent_conn.send("stop")
            self.ns_thread.join(30) 
        except:
            _msg = "Failed to terminate Pyro NS"
            sys.stderr.write(_msg)
        
            
    def is_ns_running(self):
        """
            Returns true or false depending on if the nameserver is running"
        """
        try:
            ns = Pyro4.locateNS(self.sut.pyro_ns_name, self.sut.pyro_ns_port)
            ns.ping()
            ns._pyroRelease()
            return True
        except BaseException:
            return False

    
    @staticmethod
    def is_node_up(sut, node):
        """
         Attempts to ping the node's Pyro proxy to determine
         if the node is up and available for remote calls.
         
        :returns: True or False

        **Example**::
            from ae.pyro_driver import Pyro
            
            if Pyro.is_node_up(self.sut, n1):
                # node is up
                do something
            else:
                #node is down
                do something else
        """
        try:
            ns = Pyro4.locateNS(sut.pyro_ns_name, sut.pyro_ns_port)
            uri = ns.lookup("proc_caller_%s" % node.get_hostname_only())
            pc = Pyro4.Proxy(uri)
            pc.__pyroTimeout = 10
        except Pyro4.errors.NamingError:
            time.sleep(1)
            return False
        try:
            pc.is_alive()
            return True
        except Pyro4.errors.CommunicationError:
            return False
        
    
    @staticmethod
    def wait_for_node_up(sut, node, attempts=None):
        """
         Waits for our our Proc Caller service to start
         on the node. Note that the timeout value here
         is going to be much longer than the value passed
         in because the a Pyro connection timeout is going
         take several seconds.
        """
        if attempts == None:
            attempts = NODE_QUERY_ATTEMPTS
        
        while attempts > 0:
            if Pyro.is_node_up(sut, node) == True:
                return
            else:
                attempts -= 1
                time.sleep(3)
        msg = "Pyro failed to start on [%s] due to ns lookup or communication error " % node
        raise Pyro4.errors.CommunicationError (msg)
    
    
    def stop_proc_caller_on_node(self, node):
        """
          Calls the proc_caller's stop method which terminates
          all chilren processes and then stops the proc_caller.
        """
        ns = Pyro4.locateNS(self.sut.pyro_ns_name, self.sut.pyro_ns_port)
        uri = ns.lookup("proc_caller_%s" % node.get_hostname_only())
        pc = Pyro4.Proxy(uri)
        try:
            pc.shutdown()
        except Pyro4.errors.ConnectionClosedError:
            #This is expected
            pass
        finally:
            ns._pyroRelease()

         
    def rkill_proc_caller_on_node(self, node):
        """ 
         Remotely stops the proc caller on the nodes and removes
         the URI from the nameserver. For linux nodes a pkill -9 
         via ssh is used. Windows nodes have the proc_caller's pid
         stored and use pskill to terminate the process.
        """
        if node.os.os_type == OS_TYPE.LINUX:
            cmd = "ssh %s@%s \"pkill -9 -f pyro_sut\"" % (self.sut.username, node.ip)
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, shell=True)
            self.log.info(" on [%s] stopping PID [%s]"%(node, p.pid))
            p.wait()
            
            if p.returncode != 0:
                self.log.warning("Failed to kill the Proc Caller daemon on [%s]"%node)
        elif node.os.os_type == OS_TYPE.WINDOWS:
            if platform.system() == 'Windows':
                pskill = os.path.join(pathing.get_tools_bin(),"psTools","pskill.exe")
                for pid in self.remote_pids:
                    cmd = "%s -t \\\\%s  -u %s\\%s -p %s %s" % (pskill, node.ip,
                                                               self.sut.domain,
                                                               self.sut.username,
                                                               self.sut.password,
                                                               pid)
                    p = subprocess.Popen(cmd, 
                                         stderr=subprocess.PIPE, 
                                         stdout=subprocess.PIPE, 
                                         shell=True)
                    self.log.info(" on [%s] stopping PID [%s]"%(node, p.pid))
                    p.wait()
                    if p.returncode != 0:
                        self.log.warning("Failed to kill the Proc Caller daemon on [%s]"%node)
            elif platform.system() == 'Linux':
                # TODO: How do we want to kill the AE@ processes?
                # probably invoke winexe to call pskill locally on the windows node
                raise NotImplementedError
            else:
                raise TypeError("Unsupported OS")
            
        # if its an ip address, we'll lookup the hostname
        if node.name[0].isdigit():
            node = socket.gethostbyaddr(node)   
        
        # acquire the NS (use the args) and remove the URI on it.
        ns = Pyro4.locateNS(self.sut.pyro_ns_name, self.sut.pyro_ns_port)
        proc_caller = "proc_caller_%s"%node
        ns.remove(proc_caller)
        ns._pyroRelease()
        
    
    def start_proc_caller_on_node(self, node, debug=False):
        """ 
            Registers and starts the procedure caller daemon on the node.
        """
        if self.log == None:
            self.log = ae_logger.Log(self.sut.log_server, self.__class__.__name__)
            
        if debug == True:
            debug = "-d"
        else:
            debug= ""
        
        cmd = ""
        
        if node.is_vsa():
            import vimer    
            self.log.debug("Starting AE2 on [%s]"%node)
            t = vimer.VmTool(node.vm_name,sut=self.sut)
            _python = constants.PYTHON27_LINUX 
            pyro_sut = "%s/ae/pyro_sut.py" % self.sut.ae_base_linux.rstrip('/')
            cmd = "%s %s -n %s -p %s"%(_python, pyro_sut,self.sut.pyro_ns_name,self.sut.pyro_ns_port)
            self.log.debug(cmd)
            t.start_shell(cmd)        
        elif node.os.os_type == OS_TYPE.LINUX:
            _python = constants.PYTHON27_LINUX 
            pyro_sut = "%s/ae/pyro_sut.py" % self.sut.ae_base_linux.rstrip('/')
            # builds this behemoth of a command:
            # ssh root@atl3 "nohup python /root/ae_dev/botweiser/src/ae/pyro_sut.py
            # -n 10.100.2.1 -p 9099 &>/dev/null < /dev/null &"

            """ first do a few pings to make sure """
            cmd="ping -c 3 %s" % self.sut.pyro_ns_name         
            self.log.debug(cmd)
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, shell=True)
            p.wait()
            if p.returncode != 0:
                raise TypeError("Unable to shell cmd [%s]" % (cmd))
            cmd = "ssh %s@%s \"nohup " % (self.sut.username, node.ip)
            cmd += "%s %s %s -n %s -p %s" % (_python,
                                             debug,
                                             pyro_sut,
                                             self.sut.pyro_ns_name, 
                                             self.sut.pyro_ns_port)
            cmd +=" &>/dev/null < /dev/null &\""
            self.log.debug(cmd)
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, shell=True)
            self.log.info("Starting proc_caller on node [%s] PID [%s]"%(node, p.pid))
            p.wait()
            if p.returncode != 0:
                raise TypeError("Unable to shell cmd [%s] on  node [%s]" % (cmd, node))
        elif node.os.os_type == OS_TYPE.WINDOWS:
            _python = constants.PYTHON27_WIN32
            import ntpath
            ps_exec = ntpath.abspath(os.path.join(self.sut.ae_base_win32,
                                                  "..","tools","bin","psTools","PsExec.exe"))
            pyro_sut = "%s/ae/pyro_sut.py" % self.sut.ae_base_win32.rstrip('\\')
            pyro_cmd = "%s %s %s -n %s -p %s" % (_python,
                                                 debug,
                                                 pyro_sut,
                                                 self.sut.pyro_ns_name, 
                                                 self.sut.pyro_ns_port)
            if platform.system() == 'Windows':
                cmd = "%s -d \\\\%s -u %s\\%s -p %s  cmd /c %s" % (ps_exec, node.ip,
                                                                   self.sut.domain,
                                                                   self.sut.username,
                                                                   self.sut.password,
                                                                   pyro_cmd)
                self.log.debug(cmd)
                p = subprocess.Popen(cmd,stderr=subprocess.PIPE,stdout=subprocess.PIPE, shell=True)
                self.log.info("Starting proc_caller on node [%s] PID [%s]"%(node, p.pid))
                p.wait()

                # psexec will return the PID of the new process.
                if p.returncode == 0:
                    raise ae_errors.FatalError("Failed to start the Proc Caller daemon on [%s]"%node)
            elif platform.system() == 'Linux':
                python_cmd = "\"%s\" %s %s -n %s -p %s" % (_python,
                                                           debug,
                                                           pyro_sut,
                                                           self.sut.pyro_ns_name, 
                                                           self.sut.pyro_ns_port)
                cmd = "(winexe -U %s/%s%%%s //%s '%s') &>/dev/null < /dev/null &"%(
                                                                            self.sut.domain,
                                                                            self.sut.username,
                                                                            self.sut.password,
                                                                            node.ip,
                                                                            python_cmd)
                self.log.debug(cmd)
                p = subprocess.Popen(cmd,stderr=subprocess.PIPE,stdout=subprocess.PIPE, shell=True)
                self.log.info("Starting proc_caller on node [%s] PID [%s]"%(node, p.pid))
                p.wait()
            else:
                raise TypeError("Driver is not a supported OS")
        else:
            raise TypeError("Unsupported OS type [%s] for node [%s]"%(node.os.os_type, node))
        # wait for the Pyro service on the node to respond
        time.sleep(2)
        Pyro.wait_for_node_up(self.sut, node)
         
if __name__ == "__main__":
    pass
