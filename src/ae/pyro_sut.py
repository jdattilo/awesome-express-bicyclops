"""pyro_sut.py
Assists with registering and starting the pyro daemon on SUT machines.

Usage: pyro_sut.py -n <nameserver hostname or IP> -p <nameserver port>
"""
atfork_warning = False
try:
    import atfork
    atfork.monkeypatch_os_fork_functions()
    import atfork.stdlib_fixer
    atfork.stdlib_fixer.fix_logging_module()
except:
    atfork_warning=True

# set the Pyro HMAC key to suppress the security warnings
import os
os.environ["PYRO_HMAC_KEY"] = bytes("shhhhh")
os.environ["PYRO_THREADPOOL_MAXTHREADS"] = "200"

import sys
import getopt
import threading
import traceback
import time
import Pyro4
import ae_logger
import ae_errors
import uuid
from lib import constants, network, string_extensions

try:
    import psutil
except ImportError:
    from prepper import Prepper
    Prepper.install_psutil()

# we need to import these when the module is loaded
# such that when the proc_caller is called, they will
# not be imported to unpickle the sut and suite objects
# and potentially cause an import error
from environment import Sut
from loader import Suite

fwlog = ae_logger.get_fw_logger()

class ProcCaller(object):
    """ A wrapper class which will be published as a Pyro remote object
        on the SUT and will call our test procedures.
    """
    def __init__(self):
        self.sut = None
        self.suite = None
        self.suppress_errors = False
        self.stop_flag = False
        
        self._tlock = threading.RLock()
        
        self._uuid_tp_dict = {}               # uuid mapped dict of test procedure (tp) references
        self._uuid_result__dict = {}          # uuid mapped dict of tp results               
        self.log = None 
        
        
    def is_alive(self):
        return True
    
    
    def call_async(self, procedure, sut, suite_config, **kwargs):
        
        self.sut = sut
        self.suite = suite_config
        tp = None
        
        if self.log == None:
            self.log = ae_logger.Log(self.sut.log_server, self.sut.log_port, name="ProcCaller")
        
        def my_import(name):
            mod = __import__(name)
            components = name.split('.')
            for comp in components[1:]:
                mod = getattr(mod, comp)
            return mod    
        
        # split the module path from the class name
        cls_path = str(procedure)
        cls_name = cls_path[cls_path.rfind('.'):].lstrip('.')
        cls_path = cls_path[:cls_path.rfind('.')]
        
        try:
            if atfork_warning:
                self.log.warning("Failed to import atfork.")
            self.log.debug("Starting execution of [%s]"%procedure)
            # do our import of the test procedure module
            mod = my_import(cls_path)
            # get a reference to the procedure class
            mod = getattr(mod,cls_name)
            tp = mod(sut, suite_config)
            fwlog.debug("Imported [%s.%s]"% (cls_path, cls_name))
            
            # generate a unique ID to be used to map our procedure stuff
            _id = uuid.uuid4() 
            _pid = kwargs.get("__CALLING_PID__")
            
            def _do_run(**kwargs):
                try:
                    fwlog.debug("New thread started [%s] via driver PID [%s]"%( _id,_pid))
                    pro = tp.run(**kwargs)
                    
                    # strip the pro of instance methods
                    #for attr, value in pro.__dict__.iteritems():
                    #    _log.debug("%s : %s" % (attr,value))
                    #    #if isinstance(attr, method):
                    #    #    _log.debug("%s is method"% attr)
                    
                    fwlog.debug("Thread updating results dict [%s]"% _id)
                    self._tlock.acquire()
                    self._uuid_result__dict.update({_id:pro})
                    
                    try:
                        del self._uuid_tp_dict[_id]
                    except:
                        pass
                    finally:
                        self._tlock.release()
                    fwlog.debug("Updated remote value for [%s] with Pro"%_id)
                except Exception, ex:
                    fwlog.debug("Error detected for [%s]"%_id)
                    self._tlock.acquire()
                    try:
                        self._uuid_result__dict.update({_id:ex})
                        self._tlock.release()
                    except Exception, ex:
                        self._tlock.release()
                        raise ex
                    try:
                        self._tlock.acquire()
                        del self._uuid_tp_dict[_id]
                    except:
                        pass
                    finally:
                        self._tlock.release() 
                        

            try:
                p = threading.Thread(target=_do_run, kwargs=kwargs)
                p.setDaemon(False)
                p.start()
                
                _time = 0
                # TODO:  may also need to check that the tp.local pid is running
                while p == None or p.isAlive() == False:
                    time.sleep(0.1)
                    _time += 0.1
                    if _time % 5 == 0:
                        self.log.debug("TP with uuid [%s] not started after 5 seconds."%_id)

                
                self.log.debug("TP with uuid [%s] started with local PID [%s]"%(_id,tp.get_pid()))
                # update our tp reference dict so we can access the tp later on
                #  if we need to - like to stop the tp and collect the pro.                
                self._tlock.acquire()
                self._uuid_tp_dict.update({_id:tp})
                self._tlock.release()
                
                self._tlock.acquire()
                self._uuid_result__dict.update({_id:None})
                self._tlock.release()
                
                return _id
                
            except Exception as ex:
                fwlog.debug("Remote exception occurred:%s"%ex)
                fwlog.debug("Remote traceback:%s"%traceback.print_exc())
        except Exception, ex:
            fwlog.debug("Remote exception2 occurred:%s"%ex)
            
            
    def get_remote_result(self, proc_uuid):
        """
         Waits for the result of a given process to be set in the 
         shared dictionary. 
         Note that no timeout value can be given here. This is because
         timeouts will be handled from the calling machines (driver) 
         side.
        """
        self._tlock.acquire()
        value = self._uuid_result__dict.get(proc_uuid)
        self._tlock.release()

        fwlog.debug("id [%s] returning %s"%(proc_uuid,value))
        return value
    
    
    def is_proc_running(self, proc_uuid):
        """ 
         Determines if the procedure (the action method)
         is still running
        """
        self._tlock.acquire()
        tp = self._uuid_tp_dict.get(proc_uuid)
        self._tlock.release()
        
        if tp != None and tp.get_pid() != None:
            return self.is_pid_running(tp.get_pid())
        else:
            return False
        
    
    def is_local_stop_complete(self, proc_uuid):
        """
         Returns the procedure flag indicating if the 
         local process stop sequence has been completed.
        """
        self._tlock.acquire()
        tp = self._uuid_tp_dict.get(proc_uuid)
        self._tlock.release()
        
        if tp != None:
            return tp.is_local_stop_complete()
        else:
            #if the uid is gone we have to assume TP was done
            return True
         
        
    def is_pid_running(self, pid):
        """
         Return True or False depending on if the PID
         is running on the machine.
         NOTE: Defunct (zombie) processes will return a False value.
        """
        ret = None
        try:
            p = psutil.Process(pid)
            fwlog.debug("PID [%s]- %s"% (pid, str(p.status)))
            if p.is_running() and p.status != psutil.STATUS_ZOMBIE:
                ret = True
            else:
                ret = False
        except:
            ret = False
        finally:
            return ret
        

    def stop_procedure(self, thread_id):
        
        fwlog.debug("Stopping Thread ID [%s]"%thread_id)
        
        if thread_id == None:
            return
        
        # grab our TP reference from the dictionary
        self._tlock.acquire()
        tp = self._uuid_tp_dict.get(thread_id)
        self._tlock.release()
        
        if tp == None:
            fwlog.warning("No reference to Test Procedure with ID[%s]" % thread_id)
            return
        
        fwlog.debug("Calling tp.stop()")
        self.stop_flag = True
        
        # Call tp.stop and eat any errors except when a process wont stop.
        # We'll save that error to the results dict so the caller will retrieve it.
        val = None
        try:
            val = tp.stop()
        except Exception, ex:
            if constants.PROCESS_IS_UNINTERRUPTIBLE in ex.message:
                self._tlock.acquire()
                self._uuid_result__dict.update({thread_id:ex})
                self._tlock.release()
            fwlog.warning("An error was raised while stopping [%s]" % thread_id)
            fwlog.warning("Error: %s" % ex)
        
        # first we want to check if the procedure enqueued it's pro
        # or an uninterruptible process error.        
        self._tlock.acquire()
        value = self._uuid_result__dict.get(thread_id)
        self._tlock.release()
        if value and value != 0:
            # nothing to do, get_remote_result will return the pro when its polled
            pass
        elif val:
            fwlog.info("Stop returned a PRO for ID[%s]" % thread_id)
            self._tlock.acquire()
            self._uuid_result__dict.update({thread_id:val})
            self._tlock.release()
        elif tp.return_values == None or tp.return_values.empty():
            fwlog.info("No partial PRO found for ID[%s]" % thread_id)
            self._tlock.acquire()
            value = self._uuid_result__dict.get(thread_id)
            if value == None:    
                self._uuid_result__dict.update({thread_id:0})
            self._tlock.release()
        else:
            pro = tp.return_values.get()
            fwlog.debug("Thread [%s] has Partial PRO: %s"% (thread_id, pro))
            self._tlock.acquire()
            self._uuid_result__dict.update({thread_id:pro})
            self._tlock.release()
        
        # we want to remove the tp uid thread if it exists
        try:
            fwlog.debug("Removing reference to [%s]"%thread_id)
            self._tlock.acquire()
            del self._uuid_tp_dict[thread_id]
        except:
            pass
        finally:
            self._tlock.release()
        
    
    def kill_process(self, pid):
        fwlog.debug("Killing PID [%s]"%pid)
        if pid == None:
            return
        
        proc = psutil.Process(pid)
        if proc.is_running() == False:
            return
        proc.kill()
    
                
    def kill_children_procs(self):
        """
         Kills all children procedures which may be running. 
        """
        self.suppress_errors = True
        pc = psutil.Process(os.getpid())
        kids = pc.get_children()
        for kid in kids:
            self.term_then_stop(kid.pid)
        self.suppress_errors = True
    
    
    def term_then_stop(self, pid, term_time=5):
        proc = psutil.Process(pid)

        if proc.is_running() == False:
            return
        
        proc.terminate()
        
        while proc.is_running() == True and term_time > 0:
            time.sleep(0.5)
            term_time -= 0.5
        
        fwlog.debug("Stopping PID % via SIGKILL..."%pid)
        try:
            proc.kill()
        except:
            return
        
        # something prevented the process from stopping s
        if proc.is_running() == True:
            raise ae_errors.TestProcedureError(self.sut, message="Failed to kill PID [%s]"%pid)

        
    def cleanup(self):
        """
         Cleans the node by stopping any test procedures
         and terminating any children processes by sending 
         SIGINT followed by SIGTERM.
        """
        
        # Phase 1 - call stop on all tp's
        for tp in self._uuid_tp_dict.values():
            try: 
                tp.stop()
            except:
                pass
        
        # Phase 2 - terminate the children using our best Ahnold voice
        self.kill_children_procs()
        
        self._uuid_tp_dict.clear()
        
    
    def shutdown(self):
        """
         Stops the Proc Caller process on the node. This is used by AE2
         during the final steps of the AE2 shutdown sequence and should
         not be called by any tests or test procedures.
        """
        _pid = os.getpid()
        proc = psutil.Process(_pid)
        proc.kill()
        
        
def main():
    
    ns_name = None
    ns_port = None
    
    fwlog.debug("%s" %  (os.path.basename(__file__)))
    # parse the args    
    try:
        opts, args = getopt.getopt(sys.argv[1:], "hn:p:", ["help","ns_name","ns_port"])
    except getopt.error, msg:
        print "for help use --help"
        sys.exit(2)
    # process options
    for o, a in opts:
        if o in ("-h", "--help"):
            print __doc__
            sys.exit(1)
        elif o in ("-n", "--ns_name"):
            ns_name = a
        elif o in ("-p", "--ns_port"):
            ns_port = int(a)
        
    
    if not ns_name or not ns_port:
        print __doc__
        sys.exit(1)
    
    
    this_pid = os.getpid()
    fwlog.debug("%s pid=%d" %  (os.path.basename(__file__),this_pid))
    
    # kill any previous running pyro_sut processes
    for proc in psutil.process_iter():
        p = psutil.Process(proc.pid)
        if str(p.cmdline).find(os.path.basename( __file__)) > 0 and p.pid != this_pid:
            p.kill()
    
    import prepper
    prepper.set_rlimits()

    # setup the pyro daemon using the sut hostname
    host = string_extensions.get_host_only(network.get_local_hostname())
    netifs = network.get_local_ips()
    daemon = Pyro4.Daemon(host=netifs[0])
    
    fwlog.debug("%s netif=%s" %  (os.path.basename(__file__),netifs[0]))
    # register the proc caller on the daemon
    uri = daemon.register(ProcCaller())
    
    fwlog.debug("%s uri=%s" %  (os.path.basename(__file__),uri))
    # acquire the NS (use the args) and register the URI on it.
    ns = Pyro4.locateNS(ns_name, ns_port)
    proc_caller = "proc_caller_%s"%host
    ns.register(proc_caller,uri)
    
    fwlog.debug("%s ns_name=%s ns_port=%d" %  (os.path.basename(__file__),ns_name,ns_port))
    # fire off the daemon and wait for some action
    daemon.requestLoop()
    
    fwlog.debug("%s exit" %  (os.path.basename(__file__)))
    sys.exit(0) 
    
   
if __name__ == "__main__":
    main()
