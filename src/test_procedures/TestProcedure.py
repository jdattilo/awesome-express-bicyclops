import abc
import copy
import copy_reg
import datetime
import logging
import multiprocessing
import os
import pickle
import socket
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import types
import uuid

import psutil
import Pyro4

from sys import platform
from ae import ae_errors
from lib import constants, network, string_extensions
from ae import ae_logger
from ae.environment import Node, Sut
from Pyro4.errors import NamingError

fwlog = logging.getLogger('AE2_FRAMEWORK')

# length of time to wait for the PRO to be enqueued after
# the action completes. So the PRO is done but waiting to be put.
RETVAL_PUT_TIMEOUT = 15

# length of time to wait for the PRO or error to be gotten from queue
RETVAL_GET_TIMEOUT = 10

# Interval period while waiting for the PRO to be enqueued.
RETVAL_PUT_INTERVAL = 0.5

# Interval between querying the remote node for a
# procedure return value 
REMOTE_RET_INTERVAL = 5

# Amount of time to wait when querying the node for
# status or PID type information 
REMOTE_QUERY_TIMEOUT = 5

# Maximum amount of time to wait (in seconds) for 
# a process to end after a signal is sent before elevating 
# to the the next signal. These values are cumulative from
# zero.If MAX_SIGKILL_WAIT is exceeded, an error is raised.
MAX_SIGINT_WAIT = 60
MAX_SIGTERM_WAIT = 120
MAX_SIGKILL_WAIT = 360

# amount time to wait between checking for
# process completion
WAIT_INTERVAL = 1

# subprocess join timeout
JOIN_TIMEOUT = 6

# amount of time to wait for the child process to start
DEADLOCK_TIMEOUT = 10


# custom pickling methods so we can serialize TP instance methods
def _pickle_method(method):
    func_name = method.im_func.__name__
    obj = method.im_self
    cls = method.im_class
    return _unpickle_method, (func_name, obj, cls)

def _unpickle_method(func_name, obj, cls):
    for cls in cls.mro():
        try:
            func = cls.__dict__[func_name]
        except KeyError:
            pass
        else:
            break
        return func.__get__(obj, cls)

# register our mangling methods.
copy_reg.pickle(types.MethodType, _pickle_method, _unpickle_method)


class Pro():
        """
         Procedure Return Object. We'll use this as a container
         class to store data from our procedure
         
        """ 
        
        MAX_PRINT_SIZE = 1024
        LAST_PAGE = 640
        
        def __init__(self):
            self.output = None
            self.shell_stdout = None
            self.shell_stderr = None
            self.shell_ret_code = None
        def __str__(self):
            _output=_stdout=_stderr="[Too large. Printing last %s characters.]"%self.LAST_PAGE
            if self.output == None or sys.getsizeof(str(self.output)) < self.MAX_PRINT_SIZE:
                _output = self.output
            else:
                _output += " ... %s\n"%(str(self.output))[-self.LAST_PAGE:]
            if self.shell_stdout == None or sys.getsizeof(str(self.shell_stdout)) < self.MAX_PRINT_SIZE:
                _stdout = self.shell_stdout
            else:
                _stdout += " ... %s\n"%(str(self.shell_stdout))[-self.LAST_PAGE:]
            if self.shell_stderr == None or sys.getsizeof(str(self.shell_stderr)) < self.MAX_PRINT_SIZE:
                _stderr = self.shell_stderr
            else:
                _stderr += " ... %s\n"%(str(self.shell_stderr))[-self.LAST_PAGE:]
            return "\n Output:%s\n Stdout:%s Stderr:%s RetCode:%s\n" % (_output,
                                                                        _stdout,
                                                                        _stderr,
                                                                        str(self.shell_ret_code))
            
        def is_empty(self):
            return self.output == None and self.shell_ret_code == None and \
                self.shell_stderr==None and self.shell_stdout==None
                
                
class TestProcedure(object):
    __metaclass__ = abc.ABCMeta
    
    def __init__(self, env_config, suite_config):
        self.sut = env_config                       # the environment (SUT) object
        self.suite_config = suite_config            # suite config object
        self._checkpoint_flag = True                # flag for performing checkpoint
        self._thread = None                         # thread (if asynch)
        
        self.timeout = None                         # execution timeout value
        self.log = None                             # our local/remote log
                
        self._shell_process = None                  # ref to shell process - DEPRECATE
        self._shell_pid = None                      # shell subprocess PID
        self._stderr = None                         # tmp stderr for PRO
        self._stdout = None                         # tmp stdout for PRO
        self._ret_code = None                       # shell ret code
        
        self._start_time = None                     # action start time                
        self._end_time = None                       # action stop time
        
        self._async = False                         # flag for remote asysnc
        self._local_stop_complete = False           # flag indicating local stop completion
        self._remote_stop = False                   # flag for remote stop
        self._stop_flag = False                     # flag indicating procedure is stopping
        self._is_deadlocked = False                 # flag denoting we're in a deadlock
        self._tmp_pro = None                        # temp pro for remote call
        
        self.args = None                            # internal data dictionary
        self.return_values = multiprocessing.Queue()# return queue for PRO
        self._calling_pid = None                    # pid of procedure that invoked me
        self._local_error = multiprocessing.Queue() # local error from action
        self._local_pid = None                      # locally executed pid
        self._remote_heartbeat = None               # flag to do heartbeat
        self._remote_node = None                    # Remote node procedure is running on
        self._remote_error = None                   # member for a remote error
        self._remote_pid = None                     # pid of remote procedure
        self._remote_thread = None                  # thread used to invoke the proc_caller
        self._pc_proxy = None                       # only used for the action and to kill-stop
        self._remote_uri = None                     # remote node uri
        self._wait_on_checkpoint = None             # simple flag indicating the ckpt is in-process
        self._mlock = multiprocessing.RLock()       # reentrant lock (mostly used around pro)
        
        self.pro = None                             # final return pro
        self._pro_methods = []                      # list of "helper" methods to attache to pro
        
        self._pro_file = os.path.join(tempfile.gettempdir(),"%s.pro"%uuid.uuid4())         


    @abc.abstractmethod
    def action(self):
        pass
    
    
    @abc.abstractmethod
    def checkpoint(self):
        pass    
        

    def pre_config(self):
        """
         Extra method that is called prior to procedure execution.
         Typical operations to do here in child procedure class would be::

             1) TODO: Specify procedure data requirements.

        """
        pass
    
    def post_config(self):
        """
         Extra method that is called post procedure execution and (if needed) 
         after the return value has been returned to the calling node.
         Typical operations to do here in child procedure class would be::

             1) Attach helper methods to the PRO via calling add_pro_method()

        """
        pass
    
            
    def _setup_log(self, name=None, debug_flag=False, force=False):
        
        if self.log != None:
            return
        if name == None:
            name = "%s%s"%(self.__class__.__name__,os.getpid())
        else:
            name ="%s%s"%(name,os.getpid())
        self.log = ae_logger.Log(self.sut.log_server,
                                     self.sut.log_port,
                                     name,
                                     debug_flag=debug_flag,
                                     force=force)


    def _dump_pro(self, pro):
        """
         Dumps the pickled PRO to a file so it can
         be loaded by the parent process.
        """        
        # This may be acceptable and just have an empty file(?) but not sure
        # under when this might ever happen
        if pro == None:
            raise Exception("Trying to dump a PRO that is None")
        try:
            fwlog.debug("Pickling the PRO [%s]..."%pro)
            fwlog.debug("Pickling the PRO to file [%s]..."%self._pro_file)
            pickle.dump(pro, open(self._pro_file, "w+"))
            fwlog.debug("Pickling complete.")
        except Exception, ex:
            fwlog.error("Failed to dump the pro to file[%s]"%self._pro_file)
            raise ex
        

    def _load_pro(self):
        """
         Loads a pickled PRO from a file
        """
        if os.path.exists(self._pro_file) == False:
            fwlog.warning("Missing PRO file [%s]"%self._pro_file)
        elif os.stat(self._pro_file)[6]==0:
            fwlog.warning("Empty PRO file [%s]"%self._pro_file)
        else:
            _pro = pickle.load(open(self._pro_file, "r"))
            if isinstance(_pro, Pro):
                os.remove(self._pro_file)
                self._put_pro(_pro)
            else:
                #TODO: we may want to raise an error here
                fwlog.log.warning("The object loaded from the PRO file [%s] may not be a PRO"%self._pro_file)
                self._put_pro(_pro)

    
    def _add_tp_reference(self):
        """
         Adds a TP reference to the builtins
        """
        ip = network.get_local_ips()  
        if self.sut.pyro_ns_name in ip:
            import __builtin__
            if hasattr(__builtin__,"tp_refs") == False:
                __builtin__.tp_refs = []
            __builtin__.tp_refs.append(self)
            
        
    
    def _remove_tp_reference(self):
        """
         Removes the reference to ourselves from the
         the testcase's tp reference list.
        """
        try:
            ip = network.get_local_ips()
            if self.sut.pyro_ns_name in ip:
                import __builtin__
                __builtin__.tp_refs.remove(self)
        except Exception, ex:
            pass


    def _put_pro(self, pro=None):

        while True:
            try:
                self._mlock.acquire()
                self.return_values.get_nowait()
                self._mlock.release()
            except multiprocessing.queues.Empty:
                self._mlock.release()
                break
        self.log.debug("put_pro [%s]"%os.getpid())
        if pro != None:
            self._mlock.acquire()
            self.return_values.put(pro)
            _time = 0
            while self.return_values.empty() == True:
                time.sleep(RETVAL_PUT_INTERVAL)
                _time += RETVAL_PUT_INTERVAL
                if _time > RETVAL_PUT_TIMEOUT:
                    msg = "Failed to enqueue the PRO within timeout"
                    self._mlock.release()
                    raise ae_errors.TestProcedureError(message=msg)
            self._mlock.release()
            return
        else:
            pro = Pro()
            
        self._mlock.acquire()    
        if self._stderr != None:
            pro.shell_stderr = self._stderr
        if self._stdout != None:
            pro.shell_stdout = self._stdout
        if self._ret_code != None :
            pro.shell_ret_code = self._ret_code
        self.return_values.put(pro)
        _time = 0
        
        while self.return_values.empty() == True:
            time.sleep(RETVAL_PUT_INTERVAL)
            _time += RETVAL_PUT_INTERVAL
            if _time > RETVAL_PUT_TIMEOUT:
                msg = "Failed to enqueue the PRO within timeout"
                self._mlock.release()
                raise ae_errors.TestProcedureError(message=msg)
        
        self._mlock.release()
        self.log.debug("PRO put<instance>[%s]:%s QUEUE LENGTH: %s" % (os.getpid(), pro, self.return_values.qsize()))
    
    
    def add_pro_method(self, the_method):
        """
         Adds a helper method to our list that will
         be attached to the PRO before it is returned.
        """
        if the_method in self._pro_methods:
            return
        else: 
            self._pro_methods.append(the_method)
    
    
    def _attach_methods(self):
        """
         Attaches our helper methods to the pro
         object
        """
        for m in self._pro_methods:
            try:
                self.log.debug("Attaching %s" % m.func_name)
                setattr(self.pro, m.func_name, m)
            except:
                self.log.error("Failed to attach method [%s] to PRO" % m.func_name)
            
        
    def get_pid(self):
        return self._local_pid

    
    def get_pro(self):
        """
         Returns the PRO.
         This is here for backwards compitibility.
        """
        self.log.debug("get_pro [%s]"%os.getpid())
        if self.pro == None:
            self._mlock.acquire()
            _orig = self.return_values.get_nowait()
            pro = copy.deepcopy(_orig)
            self.return_values.put(pro)
            _time = 0
            while self.return_values.empty() == True:
                time.sleep(RETVAL_PUT_INTERVAL)
                _time += RETVAL_PUT_INTERVAL
                if _time > RETVAL_PUT_TIMEOUT:
                    msg = "Failed to enqueue the PRO within timeout"
                    self._mlock.release()
                    raise ae_errors.TestProcedureError(message=msg)
            self._mlock.release()
            return pro
        else:
            return self.pro
    

    def is_running(self):
        """
         Return True or False depending on if the procedures is still running
        """
        
        if self._remote_thread == None:
            return self.is_local_proc_running()
        elif self._stop_flag == True:
            return False
        else:
            try:
                return self._remote_thread.isAlive()
            except:
                return False


    def _pretty_args(self, **kwargs):
        """
         Returns a dictionary (our args) in a way that is prettier to log.
             Slicing out any Sut objects.
             String representation of node objects (hostname only)
        """
        _dict = {}
        items = kwargs.items()
        hide = ["debug_flag","__REMOTE_FLAG__","__CALLING_PID__"]
        
        for k,v in items:
            if k in hide:
                continue
            if isinstance(v, Node) == True:
                _dict.update({k:str(v)})
            elif isinstance(v, Sut) == False:
                _dict.update({k:v})
        return str(_dict)


    def _is_node_in_sut(self, target_node):
        
        # node object comparison
        if target_node in self.sut.nodes:
            return True
        
        # compares target_node to sut hostnames
        for node in self.sut.nodes:
            if target_node == str(node):
                return True
        
        return False
    
    
    def _is_local_error(self):
        """
         Evaluates the error queue and determines if an error
         has been stored in it.
        """
        if (self._local_error == None or 
            self._local_error.empty() == True or 
            self._local_error.qsize() == 0):
            return False
        else:
            return True
    
    
    def _save_local_error(self, the_ex):
        
        if self._local_error == None:
            self._local_error = multiprocessing.Queue()
        self._local_error.put(the_ex)


    def _get_uri_for_node(self, target_node):
        if self._remote_uri == None:
            ns = Pyro4.locateNS(self.sut.pyro_ns_name, self.sut.pyro_ns_port)
            self._remote_uri = ns.lookup("proc_caller_%s" % (target_node.split('.'))[0])
            ns._pyroRelease()  
        return self._remote_uri
    
    
    def _set_pc_proxy(self, target_node):  
        pc = Pyro4.Proxy(self._get_uri_for_node(target_node))
        return pc
    
    
    def _remote_run(self, target_node):
        """
         Will be be called when we need to execute the procedure on 
         a remote node. It looks up the Pyro nameserver and remote
         object (proc_caller...) on the target node and then invokes 
         the test procedure.
        """

        # raise an error if the target node is not in the SUT node list
        if self._is_node_in_sut(target_node) == False:
            msg = "Node %s is not in SUT" % target_node
            raise ae_errors.TestCaseError(message=msg)
        
        self._get_uri_for_node(target_node)
        
        # We need to explicitly abspath the filename because running
        # from cmd will return the filename only. 
        # Eclipse will return the full filepath as will linux and cygwin.
        proc_file = sys.modules[self.__module__].__file__
        proc_file = os.path.abspath(proc_file)

        # find our module path under test procedures to our file and 
        # append the class name        
        #self.log.debug("Procedure File: [%s] Classname: [%s]" % (proc_file, self.__class__.__name__))  
        proc_file_no_ext = os.path.splitext(proc_file)[0]
        mod = proc_file_no_ext[proc_file_no_ext.find('test_procedures'):].replace(os.path.sep, '.')
        cls_path = "%s.%s" % (mod, self.__class__.__name__)


        def _pc_heartbeat(my_uri):
            """
             Proc_caller heartbeat task that calls is_alive()
             to verify the remote pyro service is still up (along)
             with the node.
            """
            stopped = False
            my_pc = Pyro4.Proxy(my_uri)            
            while self._remote_heartbeat == True:
                try:
                    if my_pc.is_alive() != True:
                        raise
                    time.sleep(constants.HEARTBEAT_INTERVAL)
                except:
                    self.log.debug("[%s]HB exception" % threading.current_thread().name)
                    stopped = True
                    break
            
            my_pc._pyroRelease()
            
            if stopped == True and self._stop_flag == False:
                ex =  Pyro4.errors.ConnectionClosedError("Heartbeat has stopped on %s"%self._remote_node)
                self._save_local_error(ex)
                self._remote_pid = 0
                raise ex
              

        def _pc_invoke():
            """
             Proc caller invocation method which establishes
             the remote node proxy connection and calls the 
             the procedure execution method.
            """
            _proxy = Pyro4.Proxy(self._get_uri_for_node(target_node))
            
            if self._pc_proxy == None:
                #self.log.debug("Initializing a new Pyro proxy to [%s]" % target_node)
                self._pc_proxy = self._set_pc_proxy(target_node) 

            try:
                # start the remote process and save the PID
                
                self._remote_pid = _proxy.call_async(cls_path, self.sut, self.suite_config, **self.args)
                
                
                # call the proxy and confirm we get a remote PID back. This way the 
                #  caller will wait for the actual remote procedure to start
                _time = 0
                while  self._remote_pid == None or self._remote_pid == 0:
                    msg = "Waiting for remote PID to be set properly. Currently [%s]" % self._remote_pid
                    self.log.warning(msg)
                    time.sleep(1)
                    _time += 1
                    
                    if _time > REMOTE_QUERY_TIMEOUT:
                        raise ae_errors.TestProcedureError(sut=self.sut, message=msg)
                    
                self.log.debug("Thread [%s] has remote id [%s]" % (threading.current_thread().name, self._remote_pid))
                
                wait_time = 0
                tmp = None
                while True:
                    tmp = _proxy.get_remote_result(self._remote_pid)
                    
                    # break and avoid an unnecessary sleep interval
                    if tmp or self._stop_flag == True:    
                        break
                    time.sleep(REMOTE_RET_INTERVAL)
                    msg = "Waiting for remote procedure result with UID [%s] on [%s]"%(self._remote_pid, self._remote_node)
                    self.log.debug(msg)
                    
                # if we got a "0" - so no partial queue, so make it an empty PRO
                if tmp == 0:
                    tmp = Pro()
                
                self.log.debug("[%s] Result is: %s" % (threading.current_thread().name, tmp))    
                
                # determine if the remote call returned an exception or PRO
                if isinstance(tmp, Pro) == True:
                    self.log.debug("A PRO was returned to [%s]" % self._remote_pid)
                    self._tmp_pro = tmp
                    return 
                elif tmp == None:
                    self.log.debug("None was returned to [%s]" % self._remote_pid)
                    return
                else:
                    self.log.debug("Something else (maybe an error) was returned to [%s]." % self._remote_pid) 
                    self._remote_error = tmp
                    self._remove_tp_reference()
                    _proxy._pyroRelease()
                    return
            
            
            # check for the stop flag and exception type to see if we
            # should eat it and query for a partial PRO  return value
            except (socket.error, IOError) as ex:
                if self._remote_stop == True:
                    self.log.debug("Remote procedure stopped. Querying for partial PRO")
                    tmp = _proxy.get_remote_result(self._remote_pid)
                    if isinstance(tmp, Pro) == True:
                        self.log.debug("A Partial PRO was returned")
                        self._tmp_pro = tmp
                    elif tmp == None:
                        self.log.debug("None was returned")
                    else:
                        self.log.debug("Something else (maybe an error) was returned.") 
                        self._remote_error = tmp
                else:
                    raise ex
            
            # catch all other exceptions
            except Exception, ex:
                self.log.debug("pc_invoke error of type:%s" % type(ex))
                self.log.debug("self._tmp_pro:%s" % self._tmp_pro)
                self._remote_error = ex
            finally:
                _proxy._pyroRelease()
        
        conn_fail = False
        
        hb = None
        try:
            #update the dict to include the calling PID
            self.args.update({"__CALLING_PID__":os.getpid()})
            self._calling_pid = os.getpid()
            
            pro = Pro()
            self._tmp_pro = None
            
            self.log.debug("Going to execute %s remotely on [%s]" % (self.__class__.__name__, target_node))
            #self.log.debug("With args:%s" % self._pretty_args(**self.args))
            self._remote_thread = threading.Thread(target=_pc_invoke)
            self._remote_thread.start()
            while self._remote_thread.isAlive() != True:
                time.sleep(0.25)

            # startup the remote pc heartbeat so we know if the node crashes
            self.log.debug("Starting the PC heartbeat")
            self._remote_heartbeat = True
            uri = self._get_uri_for_node(target_node)
            hb = threading.Thread(target=_pc_heartbeat, kwargs={"my_uri":uri})
            hb.start()
            
            # we wait for either the remote call to finish or the heartbeat to die
            while self._remote_thread.isAlive() == True and hb.isAlive() == True:
                time.sleep(constants.HEARTBEAT_INTERVAL)
            # the remote procedure finished, kill the heartbeat and use the tmp_pro
            if hb.isAlive() == True:
                self.log.debug("Joining the remote thread")
                self._remote_thread.join(timeout=JOIN_TIMEOUT)
                pro = self._tmp_pro
                self._remote_heartbeat = False
                self.log.debug("Tmp PRO is saved for remote_pid [%s]" % self._remote_pid)
            else:
                # Pyro connection died :(
                conn_fail = True
                
        except Pyro4.errors.ConnectionClosedError:
            conn_fail = True
        finally:
            #end the proc_caller heartbeat
            self.log.debug("[%s][%s]Stopping the HB for [%s]" % (os.getpid(), hb.name, self._remote_pid))
            self._remote_heartbeat = False
            
            if hb != None:
                hb.join(timeout=JOIN_TIMEOUT)
            
        self.log.debug("[%s]Procedure finished: %s" % (os.getpid(), self.__class__.__name__))
        if conn_fail == True:
            msg = "Procedure terminated with Pyro connection error on [%s]" % target_node
            raise ae_errors.TestProcedureFail(message=msg)
        elif self._remote_error != None:
            self.log.error("Remote error of type %s" % type(self._remote_error))
            # if async, we keep the exception for later.
            if self._async == False:
                self.log.error(self._remote_error)
                raise self._remote_error
        else:
            self.log.debug("Remote PID [%s] returned %s " % (self._remote_pid, pro))
            return pro
    
    
    

    
    def _run_local(self, **kwargs):
        
        try:
            debug_flag = kwargs.get('debug_flag')
            if debug_flag:
                self._setup_log(name="%s"%self.__class__.__name__,debug_flag=True, force=True)
            else:
                self._setup_log(name="%s"%self.__class__.__name__,debug_flag=False,force=True)
            fwlog.debug("log done...")
            self.log.debug("Executing locally as [%s] with %s" % (os.getpid(), self._pretty_args(**kwargs)))
            pro = Pro()
            f = open(self._pro_file,'w+')
            f.close()
        except Exception,ex:
            try:
                fwlog2 = ae_logger.get_fw_logger()
                fwlog2.error("Failed to initialize the action process with PID:%s"%os.getpid())
                fwlog2.error("The error:%s"%ex)
                self._save_local_error(ex)
            except:
                # traditional logging failed so splat the error out to a file
                _f = open("wedge.log", mode='a')
                _f.write("PID:%s"%os.getpid())
                _f.write("The error:%s"%ex)
                _f.flush()
                _f.close()

            sys.exit()
        
        try:
            self._wait_on_checkpoint = True
            
            output = self.action()

            _time = 0
            msg = "This is likely an error pickling the PRO"
            if self.return_values.empty() == True:
                self.log.debug("Return values was empty.")
                pro = Pro()
                pro.output = output
                
                self.pro = pro
                self._dump_pro(pro)
                
            else:
                self._mlock.acquire()
                pro = self.return_values.get_nowait()
                self._mlock.release()
                pro.output = output
                self.pro = pro
                self._dump_pro(pro)
                self.log.debug("Value was queued by [%s]:%s" % (os.getpid(), pro))
            
            self._checkpoint_flag = self.args.get('do_checkpoint', True)
            if self._checkpoint_flag != False:
                self.checkpoint()            
            self._wait_on_checkpoint = False
        
        except Exception, ex:
            self.log.debug("Local Error encountered in[%s] : %s" % (os.getpid(), type(ex)))
            
            # This grabs the latest exception object, strips away all the (mostly)
            # not helpful base class traceback and re-raises a new exception of 
            # the original type with a child class stack trace as the message. 
            exc_type, exc_value, exc_traceback = sys.exc_info()
            lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
            
            self.log.error("EXCEPTION TYPE:%s" % type(ex))
            self.log.error("EXCEPTION MESSAGE:%s" % (ex))
            
            # form the exception into a pretty multiline block
            msg = ""
            for line in str(lines[2:]):
                msg+= line[:-1]
            self.log.error("CHILD EXCEPTION:%s" % msg)    

            self.log.error("CHILD MESSAGE:%s" % str(lines[-1]))
            
            try:
                last_tb_line = str(lines[2:3][0])
            except:
                last_tb_line = ""
            try:
                last_message = str(lines[-1])
            except:
                last_message = ""
            h= string_extensions.get_host_only(network.get_local_hostname())
            helpful_msg = "%s\nNode:%s\nTraceback:%s%s"%(ex.message,h,last_tb_line,last_message)
            
            # Some extra logging around soap fault (suds webfault) errors
            try:
                self.log.error("SUDS WEBFAULT:%s" % (ex.fault))
                self.log.error("FAULT DOCUMENT:%s" % (ex.document))
                helpful_msg +="\n%s"%ex.fault    
            except:
                pass
            
            try:
                if isinstance(ex, ae_errors.TestCaseFail): 
                    raise ae_errors.TestCaseFail(self.sut, message=helpful_msg)
                else:
                    raise ae_errors.TestCaseError(self.sut, message=helpful_msg)
            except Exception, my_ex:
                setattr(my_ex, "run_data", self._pretty_args(**self.args))
                self._save_local_error(my_ex)

            self.log.debug("RAISING %s" % my_ex)
            self.log.close()
            raise my_ex
        finally:
            self.log.close()
            sys.exit()


    def _do_action(self):
        """
         Checks to see if the node argument is set and if we need to
         execute on a remote machine. If so, it we call the _remote_run
         method that builds our class path to the child test procedure
         and passes it the whole module namespace.
         
         Note: this method is invoked in two different ways depending on
         whether the test driver or the node (sut) is invoking it.
         
         If we're on the driver, it removes the "node" arg from the data dict
         and calls the _remote_run procedure.
         If we're on the SUT, it executes the action() method and passes the 
         pro back.
        """
        self._start_time = datetime.datetime.now()
        my_file = sys.modules[self.__module__].__file__
        
        # if the node parameter is a Node object, grab the hostname
        node = self.args.get("node")
        if isinstance(node, Node) == True:
            node = node.name
        elif node != None and isinstance(node, str) == False:
            msg = "Node object is incorrect type: %s"%type(node)
            raise ae_errors.TestProcedureError(message=msg)
            
            
        # run our procedure pre-config method
        self.pre_config()
        
        
        # this is executed locally the remote node (or driver)         
        if (node == None 
             or self.args.get('__REMOTE_FLAG__') == True
             or node == socket.gethostname() 
             or (node.split('.'))[0] == socket.gethostname() 
             or 'driver' in my_file
             ):
            
            self.p = None
            
            try:
                _dict = self.args
                if sys.flags.debug:
                    _dict.update({'debug_flag':True})
                if _dict.has_key('__REMOTE_FLAG__'):
                    del _dict['__REMOTE_FLAG__']
                # We start the action() method in it's own local process
                # if it fails to create the PRO file within a few seconds,
                # the process is likely deadlocked and so it is killed and 
                # restarted. This is a workaround to python issue 6721
                while True:
                    self.p = multiprocessing.Process(target=self._run_local, kwargs=_dict)
                    self.p.start()
                    time.sleep(0.25)
                    while not self.p or not self.p.pid:
                        #fwlog.debug("Waiting for local process PID...")
                        time.sleep(0.25)

                    self._local_pid = self.p.pid
                    try:
                        _p = psutil.Process(self._local_pid)
                        fwlog.debug("Local process PID is %s. Status:%s"%(self._local_pid,_p.status))
                    except psutil.error.NoSuchProcess:
                        fwlog.debug("Local process is already done(?)")
                        
                    
                    _time = 0
                    while os.path.exists(self._pro_file) == False:
                        time.sleep(0.25)
                        _time += 0.25
                        if _time > DEADLOCK_TIMEOUT:
                            fwlog.warn("Local process PID appears deadlocked.")
                            self._is_deadlocked = True
                            _p.terminate()
                            fwlog.debug("Terminating process %s"%self._local_pid)
                            self.p = None
                            self._local_pid = None
                            time.sleep(1)
                            break
                    if os.path.exists(self._pro_file) == True:
                        self._is_deadlocked = False
                        fwlog.debug("TP is running: %s"%self._local_pid)
                        break
                
                self._setup_log(name=self.__class__.__name__, force=True)
                self.log.debug("Local procedure execution started with PID [%s]" % self._local_pid)
                self.log.debug("Procedure timeout is [%s] seconds" % self.timeout)
                self._add_tp_reference()
                
            except Exception, ex:
                exc_type, exc_value, exc_traceback = sys.exc_info()
                lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
                fwlog.error("do_action exception:%s\n"%lines)

                self._setup_log(name=self.__class__.__name__, force=True)
                self.log.error("do_action exception:%s\n"%lines)
                
                self._save_local_error(ex)
        
            _time = 0
            _timed_out = False
            while self.p and self.p.is_alive() == True:
                
                if self.timeout > 0 and _time > self.timeout and _timed_out == False:
                    msg = "TP [%s] with PID [%s] has timed out on [%s] after [%s] seconds."%(
                                                                 self.__class__.__name__,
                                                                 self._local_pid,
                                                                 network.get_local_hostname(),
                                                                 self.timeout)
                    try:
                        raise ae_errors.TestProcedureTimoutError(self.sut, message=msg)
                    except Exception, ex:
                        exc_type, exc_value, exc_traceback = sys.exc_info()
                        lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
                        fwlog.error("do_action exception:%s\n"%lines)
                        
                        self._setup_log(name=self.__class__.__name__, force=True)
                        self.log.error("do_action exception:%s\n"%lines)
                        
                        self._save_local_error(ex)
                        self.stop_local()
                        _timed_out = True
                else:
                    if _time % 10 == 0:
                        self.log.debug("Procedure [%s] running with State:[%s]" % (self._local_pid, repr(self.p)))
                    time.sleep(1)
                    _time += 1
            
            self.log.debug("Local procedure PID [%s] finished." % self._local_pid)
            self._load_pro()
            
            
                     
            if self._async == False:
                try:
                    self.p.join(timeout=JOIN_TIMEOUT)
                    self.p = None
                    self.log.debug("Join complete")
                except:
                    self.log.warning("Process join failed")
                
                # Check for an action process error and re-raise if needed.
                # Note that if the procedure is running asynchronously, the
                # error will be raised when the wait() is called.
                if self._is_local_error() == True:
                    error = self._local_error.get(True, RETVAL_GET_TIMEOUT)
                    self.log.error("Received an error of type %s" % type(error))
                    self._remove_tp_reference()
                    raise error
        
        # we're executing a remote procedure
        else:
            # the log setup should be grabbing a child of the existing logger
            # but there can be issues with duplicate logging if this is called 
            # directly via the test case and not another procedure
            self._setup_log(name=self.__class__.__name__, force=True)
            
            self._remote_node = node
            self._add_tp_reference()
            
            # set our flag for running on the remote node
            self.args['__REMOTE_FLAG__'] = True

            if self.return_values == None:
                self.return_values = multiprocessing.Queue()
            
            # call remote run and put the pro from the remote proc
            try:
                pro = self._remote_run(node)
            except NamingError, ex:
                if self._stop_flag == False:
                    msg="Failed to communicate with: %s"%node
                    self.log.warning(msg)
                    try:
                        raise ae_errors.TestProcedureError(message=msg)
                    except ae_errors.TestCaseError, yx:
                        self._remote_error = yx
                        self.stop()
                        raise yx
            # Put the pro in.
            # if the procedure has been stopped we may need to eat an exception
            # unless it's an error from a wedged process.
            try:
                self._put_pro(pro)
                self._remove_tp_reference()
            except Exception, ex:
                self._remove_tp_reference()
                if self._stop_flag == False:
                    raise ex
                elif constants.PROCESS_IS_UNINTERRUPTIBLE in ex.message:
                    raise ex
        
        # TODO: This may need to be moved to be more accurate.    
        self._end_time = datetime.datetime.now()
        

        
    def _set_timeout(self, timeout):
        if timeout or timeout == 0:
            self.timeout = int(timeout)
        elif self.timeout == None:
            try:
                self.timeout = int(self.suite_config.proc_timeout)
            except Exception:
                self.timeout = int(constants.DEFAULT_PROCEDURE_TIMOUT)
                
    
    def _set_args(self, args):
        """
          Sets our instance args for the process.
        """
        # if the timeout is passed
        try:
            self._set_timeout(args.get("timeout"))
        except Exception:
            msg = "Failed to set timeout value."
            raise ae_errors.TestProcedureError(sut=self.sut, message=msg)

        # if the proc instance has already initialized, call the constructor 
        if self.args != None:
            self.__init__(self.sut,self.suite_config)

        #Set and remove the __CALLING_PID__ if passed in
        cp = args.get("__CALLING_PID__")
        if cp != None:
            self._calling_pid = cp
            del args["__CALLING_PID__"]
        
        try:        
            self.args = args
        except Exception as ex:
            #self.log.error("Failed to set args.")
            raise ae_errors.TestCaseError(ex=ex)


    def run_on_nodes(self, nodes, wait_timeout=None, **kwargs):
        """
         Invokes the procedure to run on multiple nodes asynchronously
        
         :param nodes: the list of nodes to execute the procedure
         :param wait_timeout: Amount of time (seconds) to wait before timing 
                              out. Note that this timeout is specific to the
                              procedure (not all of them put together). So a 
                              value of 10 will wait for up to 10 seconds for 
                              the procedure on nodeA and then wait for up to 
                              10 seconds on nodeB.
          
         :param kwargs: Whatever data dictionary the procedure requires.
         
         :returns: dictionary of results d[node]=>pro
         
         **Example**::
         
             n1 = self.sut.nodes[0]
             hello = example_procedures.hello_world.HelloWorld(self.sut, self.suite_config)
             pro_dict = hello.run_on_nodes(self.sut.nodes)
        
             my_pro = my_pro[n1]
         
        """
        def my_import(name):
            mod = __import__(name)
            components = name.split('.')
            for comp in components[1:]:
                mod = getattr(mod, comp)
            return mod
        tps_nodes = []
        results = {}
        for node in nodes:
            mod = my_import(self.__module__)
            mod = getattr(mod, self.__class__.__name__)
            tp = mod(self.sut, self.suite_config)
            tps_nodes.append((tp,node))
            tp.run_asynch(node=node,**kwargs)
            
        for tp,node in tps_nodes:
            results.update({node:tp.wait(timeout=wait_timeout)})
        del tps_nodes
        return results


    def run(self, do_checkpoint=True, **kwargs):
        """
         Runs the procedure synchronously (waits for completion).
        """
        kwargs.update({'do_checkpoint':do_checkpoint})
        self._set_args(kwargs)
        self._do_action()
        
        if self.return_values == None:
            self.log.error("The return queue is NONE.")
        elif self.return_values.empty() and self.return_values.qsize() == 0 and self._stop_flag == False:
            msg = "The return queue is EMPTY."
            self.log.error(msg)
            # check to see if there is an error
            if self._is_local_error():
                le = self._local_error.get_nowait()
                raise le
            else:
                raise ae_errors.TestProcedureError(message=msg)
        else:
            self._mlock.acquire()
            self.pro = self.return_values.get(True, RETVAL_GET_TIMEOUT)
            self._mlock.release()
            if self.log:
                self.log.debug("Returning %s" % self.pro) 
                
            # for remotely executed procedures, we only want to run 
            # the post-config methods back at the calling node
            self.log.debug("Remote_node:[%s]\n Calling PID: [%s]"%(self._remote_node,self._calling_pid))
            if (self._remote_node == None and self._calling_pid == None)\
                or (self._remote_node != None and self._calling_pid != None):
                self.post_config()
                self._attach_methods()
            
            self._remove_tp_reference()
            return self.pro
       
        
    def run_asynch(self, do_checkpoint=True, **kwargs):
        """
         Runs the procedure asynchronously - does not wait for completion
         but does an implicit join to the calling function.
         
         timeout: This sets the timeout value for the procedure in seconds.
                  If the procedure fails to complete, a procedure timeout
                  exception is raised.
        """
        kwargs.update({'do_checkpoint':do_checkpoint})
        
        # if no timeout value was specified, create one of "0"
        tmp = kwargs.get("timeout", 0)
        if tmp == 0:
            kwargs.update({"timeout": 0})
        
        self._set_args(kwargs)
        self._async = True
        
        t = threading.Thread(target=self._do_action)
        t.start()
         
        #Without this here we get a pickling error (from trying to fork the logger)
        # TODO: Find a dynamic way of determining of doing this... 
        time.sleep(1)
        
        # give the thread time to start
        while t == None or t.isAlive() != True:
            time.sleep(1)

        self._thread = t

       
    def run_always(self, **kwargs):
        """
          This thread will run as a Python "daemon" and not implicitly
          block the caller. Use this if you want some background task
          running but probably wont care about the results of the task.
          
          TODO: DEPRECATE THIS? 
          finish 'error_on_stop' flag monitor.
          error_on_stop: use this flag to throw an execution error if the 
          thread stops. This allows you to assume the thread is always running
          without checking.
        """
        
        if kwargs.get("error_on_stop"):
            raise NotImplementedError("run_always() error_on_stop flag not implemented.")
        
        t = threading.Thread(target=self._action_asynch)
        t.setDaemon(True)
        self._thread = t
        self._set_args(kwargs)
        t.start()
        
    
    def wait(self, timeout=None):
        """
        Waits for the thread to complete and returns the appropriate return value.
        TestProcedureExecutionError is raised for an improper thread termination.
        TestProcedureTimoutError is raised if the timeout is exceeded.
        
        This will also re-raise any errors that happened during the execution.
        
        timeout: Waits (n) seconds then raises a timeout error if the procedure
                 is not completed. A timeout value specified here will not alter 
                 the original timeout value of the procedure specified in the 
                 run_asynch call.
                 
                 If no timeout is specified, it will wait (indefinitely) until
                 the procedure completes. 
                 
                 A timeout of "0" expects the Procedure to be done immediately.
                 If it is not, a TestProcedureTimoutError is raised.
        """
        self._setup_log()
        self.log.debug("Waiting for %s seconds." % timeout)
        
        error = None
        time_waited = 0
        pid = 0
        
        if self._remote_error:
            self.log.warning("Remote error found:%s"%self._remote_error)
            raise self._remote_error
        
        # wait for local procedure completion
        if self._remote_node == None:
            pid = self._local_pid
            while self.is_local_proc_running() == True or self._wait_on_checkpoint == True:
                # timout is None we will wait forever for the proc to stop
                if timeout == None:
                    time.sleep(WAIT_INTERVAL)
                elif timeout == 0 or time_waited > timeout:
                    # We've timed out so stop the local procedure
                    msg = "TP [%s] with PID [%s] has timed out on [%s] after [%s] seconds."%(
                                                                 self.__class__.__name__,
                                                                 self._local_pid,
                                                                 network.get_local_hostname(),
                                                                 timeout)
                    
                    # if a timeout occurs because of an uninterruptible process,
                    # we need to log the even and eat the error so the timeout error
                    # can be raised.
                    try:
                        self.stop_local()
                    except Exception, ex:
                        if constants.PROCESS_IS_UNINTERRUPTIBLE in ex.message:
                            self.log.debug("This timeout might be caused by an uninterruptible process.")
                    
                    # raise and trap a timeout exception so we can 
                    #report it after pro collection 
                    try:
                        raise ae_errors.TestProcedureTimoutError(sut=self.sut, message=msg)
                    except Exception, ex:
                        error = ex
                        break
                else:
                    time_waited += WAIT_INTERVAL
                    time.sleep(WAIT_INTERVAL)
                    if self._wait_on_checkpoint == True:
                        self.log.debug("[%s] Waiting on checkpoint completion." % (pid))
                    else:
                        if time_waited % 5 == 0:
                            self.log.debug("Procedure with PID [%s] still running." % (pid))
            self.log.debug("Done waiting on local procedure [%s]..." % (pid))
            try:
                self.p.join(timeout=JOIN_TIMEOUT)
                self.p = None
                self.log.debug("Subprocess join complete.")
            except:
                self.log.warning("Process join failed")
             
        else:
            while self._remote_pid == None:
                time.sleep(WAIT_INTERVAL)
                time_waited += WAIT_INTERVAL
                
                # make sure we've receiver a remote PID back from SUT
                # TODO: We can time out here on the calling side but
                # how do we handle killing the remote PID if/when it
                # ever spawns?
                if timeout != None and  time_waited > timeout:
                    try:
                        msg = "Timed out waiting on remote procedure to start."
                        raise ae_errors.TestProcedureTimoutError(sut=self.sut, message=msg)
                    except Exception, ex:
                        error = ex
                        break
            
            pid = self._remote_pid    
            while self.is_remote_proc_running() == True:
                time.sleep(WAIT_INTERVAL)
                time_waited += WAIT_INTERVAL
                if time_waited % 5 == 0:
                    self.log.debug("TP [%s] on [%s] still running" % (pid,self._remote_node))
                if timeout != None and  time_waited > timeout:
                    self.stop_remote()
                    self.stop_local()
                    self._stop_flag = True
                    try:
                        msg = "TP [%s] with PID [%s] has timed out on [%s] after [%s] seconds."%(
                                                                 self.__class__.__name__,
                                                                 pid,
                                                                 self._remote_node,
                                                                 timeout)
                        raise ae_errors.TestProcedureTimoutError(sut=self.sut, message=msg)
                    except Exception, ex:
                        error = ex
                        break
            self.log.debug("Done waiting on remote procedure [%s] on [%s]" % (pid, self._remote_node))
            
        
        try:
            self.log.debug("Joining the asynch thread")
            self._thread.join()
            self.log.debug("Join complete.")
            try:
                if self._is_local_error() == False:
                    self.log.debug("Local error is empty for [%s]" % pid)
                else:
                    if error == None:
                        self.log.debug("A local error was found for [%s]" % pid)
                        error = self._local_error.get(True, RETVAL_GET_TIMEOUT)
            except:
                self.log.debug("Failed to get from local error dict")
                pass
            
            _time = 0
            
            # check for and save a remote error if we don't already have one
            if self._remote_pid > 0 and self._remote_error != None:
                self._remote_heartbeat = False
                self.stop_remote()
                if error == None:
                    error = self._remote_error
            
            # wait for the remote pro to populate
            while self.return_values.empty() == True and error == None:
                self.log.debug("Return Values is empty, waiting for local[%s] or remote [%s]"%
                               (self._local_pid, 
                                self._remote_pid))

                time.sleep(RETVAL_PUT_INTERVAL)
                _time += RETVAL_PUT_INTERVAL
                if _time > RETVAL_PUT_TIMEOUT:
                    msg = "Procedure is finished but without a return value."
                    self._remote_heartbeat = False
                    self.log.error(msg)
                    self._remove_tp_reference()
                    if error == None:
                        raise ae_errors.TestProcedureExecutionError(message=msg)
                    else:
                        raise error
                  
            self._mlock.acquire()
            try:
                self.pro = self.return_values.get_nowait()
                self._mlock.release()
            except multiprocessing.queues.Empty:
                self._mlock.release()
            
            self.log.debug("Retrieved the PRO for [%s]" % (pid))
            if error != None:
                self.log.error("A PRO exists for [%s] but a [%s] error was also found." % (pid, type(error)))
                self.log.error("Here is the PRO:%s" % self.pro)
                self._remove_tp_reference()
                raise error
            else:
                if (self._remote_node == None and self._calling_pid == None)\
                    or (self._remote_node != None and self._calling_pid != None):
                    self.post_config()
                    self._attach_methods()
                    self._remove_tp_reference()
                
                return self.pro 

        except Exception, ex:
            self._remove_tp_reference()
            raise ex
                
    
    def _run_shell(self, cmd, auto_check=True, fail_on_error=True, expect_failure=False, close_fds=True):
        """
         Executes a shell command and saves the outputs into the PRO.
         Note that this means the child procedure class cannot access
         the PRO values until the action() method has ran. So if you
         need to run a shell command as part of the procedure before
         doing other stuff, use the _run_shell_now method.
         
         Raised a TestProcedureFail if the command fails (ret code) or 
             is an error occurs with the fail_or_error flag set.
         Raises a TestProcedureExecutionError if the command fails.
        """
         
        
        # NOTE: This is problematic when trying to terminate shell processes...
        # Commenting this out for now... as long as the cygwin bins are installed 
        # we may not even need it.
        #
        #if platform == "win32":
        #    cmd = "c:\\cygwin\\bin\\bash -c \""+cmd+"\""
            
        # do the command and add the return info to the pro
        self.log.debug("Running command [%s]" % cmd)
        
        # Linux has some strange issue (at least wuth Python 2.6) 
        # where the subprocess.PIPE gets trashed when the process runs with
        # shell=False in a background thread.
        _shell_process = None
        
        if platform == "win32":
            try:
                _shell_process = subprocess.Popen(cmd,
                                                 stdout=subprocess.PIPE,
                                                 stderr=subprocess.PIPE,
                                                 shell=True)
                
            except BaseException, ex:
                self._stderr = str(ex)
        else:
            _shell_process = subprocess.Popen(cmd,
                                             stdout=subprocess.PIPE,
                                             stderr=subprocess.PIPE,
                                             shell=True,
                                             close_fds=close_fds)
        
        if _shell_process:
            self._shell_pid = _shell_process.pid
            self.log.debug("Started shell process with PID [%s]" % _shell_process.pid)
            (self._stdout, self._stderr) = _shell_process.communicate()
            self._ret_code = _shell_process.returncode
                
        self.log.debug("[%s]Going to call _put_pro()" % os.getpid())
        self._put_pro()
        
        # no checking or we're stopping so we bail
        if auto_check == False or self._stop_flag == True:
            return
        
        if expect_failure == False:
            if not _shell_process or _shell_process.returncode != 0:
                if fail_on_error == True:
                    msg = "Shell command failed [%s]" % (cmd)
                    self.log.debug(msg)
                    pro = self.get_pro()
                    raise ae_errors.TestProcedureFail(sut=self.sut, message=msg, pro=pro)
                else:
                    raise ae_errors.TestProcedureExecutionError("Command failed [%s]" % cmd)
        else:
            if _shell_process and _shell_process.returncode == 0:
                if fail_on_error == True:
                    msg = "Shell command failed [%s]" % (cmd)
                    pro = self.get_pro()
                    raise ae_errors.TestProcedureFail(sut=self.sut, message=msg, pro=pro)
                else:
                    raise ae_errors.TestProcedureExecutionError("Command failed [%s]" % cmd)
        
    
    def is_local_proc_running(self):
        """
        Returns True or False depending on if the procedure's
        LOCAL procedure's action component method is still running. 
        
        NOTE: If you're after a way to evaluate if a (local or remote)
              test procedure is still running, use is_running() instead.
        """
        try:
            # if we're running locally check the proc status
            if self._local_pid != None:
                p = psutil.Process(self._local_pid)
                if p.is_running() and p.status != psutil.STATUS_ZOMBIE:
                    return True
                else:
                    return False
            elif self._is_deadlocked == True:
                return True
            else:
                return False
        except:
            return False
    
    
    def is_local_stop_complete(self):
        """
         Returns the flag indicating if the local stop of all 
         children processes is complete or not.
        """
        return self._local_stop_complete
        
    
    def is_remote_proc_running(self):
        """
         Returns True or False depending on if the procedure's
         LOCAL procedure's action component method is still running. 
        
         NOTE: If you're after a way to evaluate if a (local or remote)
               test procedure is still running, use isning() instead.
        """
        
        _proxy = Pyro4.Proxy(self._get_uri_for_node(self._remote_node))
        ret = None
        try:
            ret = _proxy.is_proc_running(self._remote_pid)
        except:
            ret = False
        finally:
            _proxy._pyroRelease()
        
        return ret
        
    def _interupt(self, pid):
        """
         Sends the SIGINT signal to the specified process.
        """
        try:
            p = psutil.Process(pid)
            self.log.debug("Sending SIGINT to [%s]" % pid)
            p.send_signal(psutil.signal.SIGINT)
        except Exception, ex:
            self.log.debug("Skipped sending SIGINT to [%s] : %s"%(pid, ex))


    def _terminate(self, pid):
        """
         Sends the SIGTERM signal to the specified process.
        """
        try:
            p = psutil.Process(pid)
            self.log.debug("Sending SIGTERM to [%s]" % pid)
            p.send_signal(psutil.signal.SIGTERM)
        except Exception, ex:
            self.log.debug("Skipped sending SIGTERM to [%s] : %s"%(pid, ex))


    def _kill(self, pid):
        """
         Sends the SIGKILL signal to the specified process.
        """
        try:
            p = psutil.Process(pid)
            self.log.debug("Sending SIGKILL to [%s]" % pid)
            p.send_signal(psutil.signal.SIGKILL)
        except Exception, ex:
            self.log.debug("Skipped sending SIGKILL to [%s] : %s"%(pid, ex))


    def _int_then_term_then_kill(self, pid):
        """
         Sends SIGINT to the process and waits for it
         to stop. If it does not, it tries SIGTERM.  If
         that doesn't work, then SIGKILL used.  A message
         is printed if the process exited of if it failed
         to stop.
        """
        try:
            pc = psutil.Process(pid)
        except:
            return

        _time = 0
        while pc.is_running() and pc.status != psutil.STATUS_ZOMBIE:
            if _time == 0:
                if sys.platform == "win32":
                    self._terminate(pc.pid)
                    _time = MAX_SIGINT_WAIT + 1
                else:
                    self.log.debug("Interrupting [%s]" % pc.pid)
                    self._interupt(pc.pid)
            if _time == MAX_SIGINT_WAIT:
                self.log.debug("Terminating [%s]" % pc.pid)
                self._terminate(pc.pid)
            if _time == MAX_SIGTERM_WAIT:
                self.log.warning("Killing  [%s]" % pc.pid)
                self._kill(pc.pid)
            if _time == MAX_SIGKILL_WAIT:
                _msg = "Process [%s] is still running %s seconds after SIGKILL"%(pc.pid, MAX_SIGTERM_WAIT)
                self.log.error(_msg)
                _msg = "%s PID [%s]"%(constants.PROCESS_IS_UNINTERRUPTIBLE,pc.pid) 
                raise ae_errors.TestProcedureError(message=_msg)

            time.sleep(1)
            _time += 1

        self.log.debug("[%s] Exited after [%s] seconds." %(pc.pid, _time))
        time.sleep(0.5)

    def _wait_for_remote_term(self, max_wait_time=0):
        """
         Waits for the thread monitoring the remote process to finish.
         This does not actually query the status of the remote PID because 
         psutil will consider defunct processes as still running.
        """
        
        _proxy = Pyro4.Proxy(self._get_uri_for_node(self._remote_node))
        _time = 0
        try:
            self.log.debug("Waiting for remote proc to stop [%s]" % self._remote_pid)
            while True:
                if _proxy.is_local_stop_complete(self._remote_pid) == True:
                    self.log.debug("Remote proc has stopped [%s]"%self._remote_pid)
                    break
                
                time.sleep(3)
                max_wait_time+=3
                self.log.debug("Waiting for local procedures to stop on [%s]"%self._remote_node)
                if max_wait_time > 0 and _time > max_wait_time:
                    self.log.warning("Remote proc has not terminated in [%s] seconds." % max_wait_time)
                    raise ae_errors.TestProcedureTimoutError()
        finally:
            _proxy._pyroRelease()
    
    
    def stop(self):
        """
         Comprehensive stop procedure which will end all local and remote
         actions and return a copy of the PRO if there is one.
         
         There are a few timeouts at work here:
             
             MAX_SIGINT_WAIT      Time to wait on the procedure children
                                  to end via SIGINT.
             
             RETVAL_PUT_TIMEOUT - Time to wait for the a return value to be
                                  be enqued after the procedure has stopped.
         
        """
        self._setup_log(name="%s"%self.__class__.__name__,debug_flag=True, force=True)
        
        self.log.debug("Starting stop...")
        error = None
        if self._is_local_error() == True:
            error = self._local_error.get(True, RETVAL_GET_TIMEOUT)
            self.stop_remote()
        else:
            error = self.stop_remote()
        self._stop_flag = True
        self.stop_local()
        
        if error: 
            raise error
        
        ret = None
        _time = 0
        while self.return_values.empty() == True and _time < RETVAL_PUT_TIMEOUT:
            _time += 1
            time.sleep(1)
            if _time % 5 == 0:
                self.log.debug("Waiting for a final PRO...")

        if self.return_values.empty() == True:
            self.log.debug("No return value after stop.")
        else:
            try:
                self._mlock.acquire()
                ret = self.return_values.get(True, RETVAL_GET_TIMEOUT)
                pro = copy.deepcopy(ret)
                self.return_values.put(pro, block=True, timeout=RETVAL_PUT_TIMEOUT)
                self._mlock.release()
                self.log.debug("We have a return value after stop:%s"%ret)
            except multiprocessing.queues.Empty:
                self._mlock.release()
        
        self._remove_tp_reference()
        return ret


    def _term_children(self, pid, recursive=True):
        """
         Recursiveely terminates children processes by SIGINT
         and then SIGTERM if the interrupt fails to stop the 
         process in the time allowe by MAX_SIGINT_WAIT.
        """
        self.log.debug("Finding child procs for [%s]" % pid)
        try:
            pc = psutil.Process(pid)
        except:
            self.log.debug("No child procs found for [%s]" % pid)
            return
        
        kids = pc.get_children(recursive=recursive)
        for kid in kids:
            self._term_children(kid.pid, recursive)
            self.log.debug("Stopping child proc [%s] from local PID [%s]" % (kid.pid, self._local_pid))
            self._int_then_term_then_kill(kid.pid)


    def stop_local(self):
        
        # but the shell_pid is probably not set pre-fork so we will
        # want to also just flat out kill any child processes as well.
        # the local proc may (but hopefully is not) already be gone.
        try:
            self._setup_log(name="%s"%self.__class__.__name__,debug_flag=True, force=True)
            self.log.debug("Stopping local proc with PID [%s]" % self._local_pid)
            self._term_children(self._local_pid)
            self._int_then_term_then_kill(self._local_pid)
            self._local_stop_complete = True
        # If the error was an uninterruptible process, we want to
        # re-raise it and fail the test.
        except Exception,ex:
            if constants.PROCESS_IS_UNINTERRUPTIBLE in ex.message:
                raise ex
            else:
                return
            
    
    def stop_remote(self, wait_for_stop=True, max_wait_time=0):
        """
         Stops the remote procedure by sending the remote ProcCaller
         a stop_procedure call.
        """
        self._setup_log(name="%s"%self.__class__.__name__,debug_flag=True, force=True)
        if self._remote_pid == None or self._remote_node == None:
            self.log.debug("Nothing to do with PID [%s] on [%s]" % (self._remote_pid, self._remote_node))
            return
        
        _proxy = Pyro4.Proxy(self._get_uri_for_node(self._remote_node))
        
        error = None
        tmp = _proxy.get_remote_result(self._remote_pid)
        if tmp and isinstance(tmp, Pro) == False:
            error = tmp
        
        self.log.debug("Stopping PID [%s] on [%s]" % (self._remote_pid, self._remote_node))
        self._remote_stop = True
        _proxy.stop_procedure(self._remote_pid)
        
        # if we're waiting for the stop, we need to re-query
        # the results dictionary for a remote result.
        if wait_for_stop == True:
            self._wait_for_remote_term(max_wait_time)
            tmp = _proxy.get_remote_result(self._remote_pid)
            if tmp and isinstance(tmp, Pro) == False:
                error = tmp

        _proxy._pyroRelease()
        
        while self._tmp_pro == None and self.return_values.empty():
            self.log.debug("Waiting for the remote result...")
            time.sleep(3)
        return error
    
    
    def kill_remote(self, wait_for_stop=True, max_wait_time=0):
        """
         Kills the remote procedure by sending the SIGKILL signal.
        """
        if self._remote_pid == None or self._remote_node == None:
            return
        
        self.log.debug("Killing PID [%s] on %s" % (self._remote_pid, self._remote_node))
        if self._pc_proxy == None:
            self._pc_proxy = self._set_pc_proxy(self._remote_node)
        self._pc_proxy.kill_process(self._remote_pid)
        
        if wait_for_stop == True:
            self._wait_for_remote_term(max_wait_time)

