import sys
import os
import inspect
import pickle
import logging
import logging.handlers
import re
import SocketServer
import struct
import socket
import time
from multiprocessing import Process
import prepper

try:
    from lib import network
except ImportError:
    pass

MAX_LOG_MSG_LENGTH = 16384   
SU_LOG_FILENAME = "ae-run.log"
SU_DEBUG_LOG_FILENAME = "ae-run_debug.log"

CU_LOG_FILENAME = "cow-ae-run.log"
CU_DEBUG_LOG_FILENAME = "cow-ae-run_debug.log"

def get_host_only():
    tmp = socket.gethostname()
    return (tmp.split('.'))[0]

def get_fw_logger():
    """
     Configures a simple local logger with rotating log
     files that can be used for lots of framework chatter.
     If the Python system debug flag (-d) is not present, no 
     logging will be captured.
     
     :returns: the logger instance
    """
    
    log_file = "%s%slogs"%(prepper.find_ae_path(),os.path.sep)
    if os.path.exists(log_file) == False:
        os.makedirs(log_file)
    log_file += "%sae_fw_%s.log"%(os.path.sep,get_host_only())
    file_size = 1024*1024*10 # 10MB 
    n_files = 5
    
    my_logger = logging.getLogger('AE2_FRAMEWORK')
    my_logger.setLevel(logging.DEBUG)
    handler = logging.handlers.RotatingFileHandler(log_file, maxBytes=file_size, backupCount=n_files)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(process)d \t%(message)s")
    handler.setFormatter(formatter)
    
    if len(my_logger.handlers) == 0:
        my_logger.addHandler(handler)
    
    return my_logger        


fwlog = logging.getLogger('AE2_FRAMEWORK')


class MySocketHandler(logging.handlers.SocketHandler):
    """
     Our own socketHandler class to override the createSocket
     method to trap makeSocket errors like we want and not
     block until the connection can be made.
     
     Note: We currently only log the makeSocket failure. I'm
     not sure how to best handle the failure condition.
    """
    def createSocket(self):
        now = time.time()
        # Either retryTime is None, in which case this
        # is the first time back after a disconnect, or
        # we've waited long enough.
        if self.retryTime is None:
            attempt = 1
        else:
            attempt = (now >= self.retryTime)
        if attempt:
            try:
                self.sock = self.makeSocket()
                self.retryTime = None # next time, no delay before trying
            except socket.error:
                fwlog.error("Create socket failed. Retrying...")
                #Creation failed, so set the retry time and return.
                if self.retryTime is None:
                    self.retryPeriod = self.retryStart
                else:
                    self.retryPeriod = self.retryPeriod * self.retryFactor
                    if self.retryPeriod > self.retryMax:
                        self.retryPeriod = self.retryMax
                self.retryTime = now + self.retryPeriod
            



class Log():
    """
     Our 'client' logging code. On the server (the test driver)
     we call our configure logger code to setup the logging module
     with console and file handlers.
     On the remote node, we just add the network socket handler.  
    """
    
    def __init__(self, 
                 log_server, 
                 log_port=9020, 
                 name="AE", 
                 debug_flag=False,
                 force=False,
                 truncate=True):
         
        self.rootLogger     = None          # member for the python logger
        self.log_server     = log_server    # IP of the log server
        self.log_port       = log_port      # log port of the log server (9020 by default)
        self.name           = name          # name of the logger (usually module or class)
        self.debug_flag     = debug_flag    # flag to set log level to debug
        self.force          = force         # force new socket handlers to be attached
        self.truncate       = truncate      # flage to truncate excessively long messages.
        self.hostname       = None          # hostname of the log client
        self.netifs         = None          # list of netifs on the log client
        try:
            self._set_local_info()
            self._add_log_handle()
        except:
            #fwlog.error("Failed to add log handle for %s"%self.name)
            import traceback
            print traceback.print_exc()


    def _set_local_info(self):
        """
         Sets our hostname and netif list if neccessary.
        """
        if self.hostname == None:
            #fwlog.debug("Determining local hostname")
            self.hostname = get_host_only()
        if self.netifs == None:
            #fwlog.debug("Determining local netif information.")
            self.netifs = network.get_local_ips()
        fwlog.debug("Done setting local hostname and netif info.")


    def _add_log_handle(self):
        
        if not self.log_server:
            #fwlog.debug("No log server specified. Skipping log configuration for %s"%self.name)
            return
        
        pid = os.getpid()
        self.rootLogger = logging.getLogger(self.name)

        if not hasattr(logging, "configured"):
            #fwlog.debug("Adding logging sockethandler for %s"%self.name)
            socketHandler = MySocketHandler(str(self.log_server),self.log_port)
            self.rootLogger.addHandler(socketHandler)
            self.rootLogger.setLevel(logging.DEBUG)
            logging.configured = True
        else:
            # add the socket handler if the logger has no handlers, 
            # we're not running on the driver 
            if len(self.rootLogger.handlers) == 0:
                #fwlog.debug("Logger has no handles for %s"%self.name)
                # if the parent logger has handlers, we done't need to add more
                if (self.rootLogger.parent and len(self.rootLogger.parent.handlers) > 0) or self.rootLogger.parent.parent:
                    #fwlog.debug("Logging already configured for %s"%self.name)
                    logging.configured = True
                    return
                
                # only add more handlers on the driver if we're forcing them.
                if (self.log_server == self.hostname or self.log_server in self.netifs) or self.force == True:
                    #fwlog.debug("Adding logging sockethandler for %s"%self.name)
                    socketHandler = MySocketHandler(str(self.log_server),self.log_port)
                    self.rootLogger.addHandler(socketHandler)
                    self.rootLogger.setLevel(logging.DEBUG)
                    logging.configured = True
            else:
                pass
                #fwlog.debug("ae_logger %s already has %s log handles"%(self.name,len(self.rootLogger.handlers)))
    
    
    def _truncate_msg(self, msg):
        msg = str(msg)
        if self.truncate and len(msg) > MAX_LOG_MSG_LENGTH:
            return msg[:MAX_LOG_MSG_LENGTH]+"..."
        else:
            return msg
    

    def info(self, msg):
        try:
            msg = self._truncate_msg(msg)
            d = {'hostname':self.hostname,'caller':inspect.stack()[1][3]}
            self.rootLogger.info(msg, extra=d)
        except Exception, ex:
            fwlog.error("Log [info] failure: %s" %ex)

    def debug(self, msg):
        try:
            msg = self._truncate_msg(msg)
            if len(self.rootLogger.handlers) == 0:
                fwlog.warn("Attempting to log without handlers: %s"%inspect.stack()[1][3])
            d = {'hostname':self.hostname,'caller':inspect.stack()[1][3]}
            self.rootLogger.debug(msg, extra=d)
        except Exception, ex:
            fwlog.error("Log [debug] failure: %s" %ex)
        
    def warning(self, msg):
        try:
            msg = self._truncate_msg(msg)
            d = {'hostname':self.hostname,'caller':inspect.stack()[1][3]}
            self.rootLogger.warning(msg, extra=d)
        except Exception, ex:
            fwlog.error("Log [warn] failure: %s" %ex)
    
    def error(self, msg):
        try:
            msg = self._truncate_msg(msg)
            d = {'hostname':self.hostname,'caller':inspect.stack()[1][3]}
            self.rootLogger.error(msg, extra=d)
        except Exception, ex:
            fwlog.error("Log [error] failure: %s" %ex)
    
    
    def close(self):
        """
         Closes the socketandler attached to our logger.
        """
        if self.rootLogger == None:
            return
        try:
            handlers = self.rootLogger.handlers
            for hand in handlers:
                if isinstance(hand,logging.handlers.SocketHandler) == True:
                    try:
                        hand.flush()
                        hand.close()
                        self.rootLogger.handlers.remove(hand)
                    except:
                        pass
            
        except:
            pass
    

class SubunitFilter(logging.Filter):

    def filter(self, record):
        logmessage = record.getMessage()
        subunitmessage = re.match("^(test|success|failure|error|progress):\ ",logmessage)
        
        if subunitmessage:
            return True
        else:
            return False

        
def config_logger(logger,
                  logfile_name = None, 
                  debug = False,
                  log_server = None,
                  log_port = None,
                  clean_log = False,
                  su_log = False):
    
    if not hasattr(logging, "configured"):
        print "CONFIGURING LOGGER %s with [%s]" %( logger.name,os.getpid())
        # find our ae base path and create a log directory if necessary        
        log_path = "%s%slogs"%( prepper.find_ae_path() ,os.path.sep)
        if not os.path.exists(log_path):
            os.makedirs(log_path)
               
        # if no logfile name was passed in
        if logfile_name == None:
            logfile_name = ""
        
        run_log = "%s%sae_%s.log"% (log_path, os.path.sep, logfile_name)
        debug_log = "%s%sae_%s_debug.log"% (log_path, os.path.sep, logfile_name)
        
        consolehandler = logging.StreamHandler(sys.stdout)
        tr_filehandler = logging.handlers.RotatingFileHandler(run_log, 
                                                              maxBytes=62914560, 
                                                              backupCount=16)
        fw_filehandler = logging.handlers.RotatingFileHandler(debug_log, 
                                                              maxBytes=62914560, 
                                                              backupCount=16)
                                                              
        formatter = logging.Formatter(
            "%(asctime)s:%(levelname)s:%(hostname)s:%(name)s.%(caller)s: %(message)s", "%b %d %X")
        fw_filehandler.setFormatter(formatter)
        tr_filehandler.setFormatter(formatter)
        consolehandler.setFormatter(formatter)
        
        if clean_log == True:
            fw_filehandler.doRollover()
            tr_filehandler.doRollover()
            
            # info level filehandler for cow
            cu_filehandler = logging.FileHandler(log_path+os.path.sep+CU_LOG_FILENAME, mode='w')
            cu_filehandler.setLevel(logging.INFO)
            cu_filehandler.setFormatter(formatter)
            logger.addHandler(cu_filehandler)
            
            # debug level filehandler for cow
            cud_filehandler = logging.FileHandler(log_path+os.path.sep+CU_DEBUG_LOG_FILENAME, mode='w')
            cud_filehandler.setLevel(logging.DEBUG)
            cud_filehandler.setFormatter(formatter)
            logger.addHandler(cud_filehandler)


        logger.setLevel(logging.DEBUG)
        # the framework logfile will always be set to debug        
        fw_filehandler.setLevel(logging.DEBUG)
        # the test run log level will be info
        tr_filehandler.setLevel(logging.INFO)
        
        # check for the debug switch and adjust the console logging level
        if sys.flags.debug == True or debug == True:
            consolehandler.setLevel(logging.DEBUG)
        else:
            consolehandler.setLevel(logging.INFO)
        
        #formatter = logging.Formatter(
        #    "%(asctime)s:%(levelname)s:%(hostname)s:%(name)s.%(caller)s: %(message)s", "%b %d %X")
        #fw_filehandler.setFormatter(formatter)
        #tr_filehandler.setFormatter(formatter)
        #consolehandler.setFormatter(formatter)

        # subunit logging setup for buildbot integration
        if su_log == True:
            subunitformatter = logging.Formatter("time: %(asctime)s\n%(message)s", "%Y-%m-%d %X")
            sufilter = SubunitFilter()
            consolehandler.addFilter(sufilter)
            consolehandler.setFormatter(subunitformatter)
            # info level filehandler
            sufilehandler = logging.FileHandler(log_path+os.path.sep+SU_LOG_FILENAME, mode='w')
            sufilehandler.setLevel(logging.INFO)
            sufilehandler.setFormatter(formatter)
            # debug level filehandler
            sudfilehandler = logging.FileHandler(log_path+os.path.sep+SU_DEBUG_LOG_FILENAME, mode='w')
            sudfilehandler.setLevel(logging.DEBUG)
            sudfilehandler.setFormatter(formatter)
            
            logger.addHandler(sudfilehandler)
            logger.addHandler(sufilehandler)
        
        logger.addHandler(consolehandler)
        logger.addHandler(tr_filehandler)
        logger.addHandler(fw_filehandler)
        
        logging.configured = True
        


#####    Below is our log server (test driver) logging code    #####
  
class LogRecordStreamHandler(SocketServer.StreamRequestHandler):
    """
     Handler for a streaming logging request.
     This basically logs the record using whatever logging policy is
     configured locally.
    """
    def handle(self):
        """
         Handle multiple requests - each expected to be a 4-byte length,
         followed by the LogRecord in pickle format. Logs the record
         according to whatever policy is configured locally.
        """
        while True:
            try:
                chunk = self.connection.recv(4)
                if len(chunk) < 4:
                    break
            except:
                break
     
            slen = struct.unpack('>L', chunk)[0]
            chunk = self.connection.recv(slen)
            while len(chunk) < slen:
                chunk = chunk + self.connection.recv(slen - len(chunk))
            
            obj = self.unPickle(chunk)
            record = logging.makeLogRecord(obj)
            self.handleLogRecord(record)


    def unPickle(self, data):
        return pickle.loads(data)

    
    def handleLogRecord(self, record):
        # if a name is specified, we use the named logger 
        # rather than the one implied by the record.
        if self.server.logname is not None:
            name = self.server.logname
        else:
            name = record.name
        logger = logging.getLogger(name)
        logger.handle(record)
        


class LogSocketReceiver(SocketServer.ThreadingTCPServer):
    """
     Our logging socket receiver.
    """
    
    def __init__(self,  
                 host,
                 port=logging.handlers.DEFAULT_TCP_LOGGING_PORT,
                 filename = None,
                 debug = False,
                 handler=LogRecordStreamHandler):        
        try:
            SocketServer.ThreadingTCPServer.__init__(self, (host, port), handler)
        except:
            print "WARNING: Failed to initialize logging TCP Server."
            print "Verify that Env_file specifies the test driver as the LOG_SERVER."
            return
                    
        self.abort = 0
        self.timeout = 1
        self.logname = None
        self.filename = filename
        self.debug = debug

    def serve_until_stopped(self):
        import select, errno
        abort = 0
        try:
            while not abort:
                rd, wr, ex = select.select([self.socket.fileno()],
                                           [], 
                                           [],
                                           self.timeout)
                if rd:
                    self.handle_request()
                abort = self.abort
        except select.error, v:
            if v[0] != errno.EINTR: raise
        

class LogServer():
    """
        LogServer wrapper class that facilitates starting and
        stopping of the logserver daemon process on the test driver.
    """
    
    def __init__(self, host=None, port=9020, filename=None, debug=False, clean_log=False, su_log=False):
        
        if not host:
            self.log_server = socket.gethostname()
        else:
            self.log_server = host
        
        self.port = port
        self._log_process = None
        self._tcpserver = None
        self.filename = filename
        self.debug = debug
        self.pid = None
        self.clean_log = clean_log
        self.su_log = su_log

    
    def _target(self):
        
        import signal
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        
        rl = logging.getLogger()
        
        config_logger(
                      rl,logfile_name=self.filename,
                      log_server = self.log_server,
                      log_port = self.port,
                      debug = self.debug,
                      clean_log = self.clean_log,
                      su_log = self.su_log
                      )
        self._tcpserver = LogSocketReceiver(self.log_server, 
                                            self.port, 
                                            self.filename, 
                                            self.debug)
        self._tcpserver.serve_until_stopped()        
    
    
    def start_log_server(self):
        """
         Starts the log server in a background thread.
        """
        # if the log thread is already running we will just return
        if self._log_process and self._log_process.is_alive() == True:
            return
            
        print "Starting log on %s:%s" % (self.log_server,self.port)
        self._log_process = Process(target=self._target)
        self._log_process.daemon = True
        self._log_process.start()
        self.pid = self._log_process.pid
        print "Logserver PID [%s]"% self.pid
        
        
    def stop_log_server(self):
        """
         Stops the log server process. 
        """
        import time
        import psutil
        
        try:
            pc = psutil.Process(self.pid)
            pc.send_signal(psutil.signal.SIGINT)
            self._log_process.join(timeout=5)
        except:
            print "Joining logger process failed"
            try:
                print "Terminating logger process"
                _t = self._log_process.terminate()
                self._log_process.join(timeout=5)
            except:
                print "Joining logger process failed again."
                pass
            try:
                del self._log_process
            except:
                pass


if __name__ == '__main__':
    pass
