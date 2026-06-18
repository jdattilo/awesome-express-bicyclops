#!/usr/bin/python
"""
This is a collection of custom exceptions which can be used in a 
variety of ways to help with consolidated error handling and
program flow.
"""
import os
import sys
import pickle
import tempfile
from ae.ae_logger import Log
from lib import network


class FatalError(Exception):
    """ Our most serious exception.
        This should be used when an unrecoverable condition
        exists within the Test Run and it cannot continue.
    """
    def __init__(self, message=None):
        
        # Do some error-specific logging
        
        # logger.fatal(self.__class__.__name__,":",self.message)
        self.message = "%s: %s" % (self.__class__.__name__, message)   
        Exception.__init__( self, self.message )
        
        # TODO: any extra stuff specific to this error level
        
        # Finally, this is a fatal error so we will want to re-raise
        # some exception to terminate the run.  
        # For now we will just use the BaseException.
        raise BaseException(self.message)
    
    def __str__(self):
        return self.value

class TestCaseFail(Exception):
    """
        Is raised during the test run to indicate a test failure.
    """
    def __init__(self, sut=None, message=None, ex=None, pro=None, auto_recover=True):
        
        if message == None:
            self.message = "%s" % (self.__class__.__name__)   
        else:
            self.message = message
            
        if pro != None:
            self.message += str(pro)
        try:
            if sut != None:
                log = Log(sut.log_server, sut.log_port, self.__class__.__name__)
                import traceback
                if ex:
                    log.error("Exception Information:\n%s"%ex)
                elif message:
                    log.error("Exception Message:\n%s"%message)

            if(auto_recover == True):
                pass
        except Exception, ex:            
            raise FatalError()
        
    def __str__(self, *args, **kwargs):
        return self.message
        

class TestCaseError(Exception):
    """
        Is raised during test case (main) execution and an error occurs.
        This error will cause the test result to be flagged as an error
        and the test re-attempted or the post execution sequence will begin.
    """
    def __init__(self, sut=None, message=None, ex=None):
        
        try:
            if message:
                self.message = message
            else:
                self.message = "%s: %s" % (self.__class__.__name__, message)    
            if sut != None:
                log = Log(sut.log_server, sut.log_port)
                import traceback
                ex_msg=""
                if ex:
                    exc_type, exc_value, exc_traceback = sys.exc_info()
                    lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
                    my_ex = lines[2:]
                    for line in my_ex:
                        ex_msg += str(line)          
                    log.error("TCE Exception Information:\n%s"%ex_msg)
                if not message:
                    self.message = ex_msg
        except Exception, ex:            
            raise FatalError()
        
    def __str__(self):
        return self.message
        


class TestCasePreExecuteError(Exception):
    """
        Is raised during the test case pre-execute sequence if an error occurs.
        This is to be a recoverable error where the cluster can be be rebuilt and
        the test attempted again.
    """
    def __init__(self, sut, message=None, ex=None):
        try:
            log = Log(sut.log_server, sut.log_port, self.__class__.__name__)
            import traceback
            if ex:
                exc_type, exc_value, exc_traceback = sys.exc_info()
                lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
                my_ex = lines[2:]          
                log.error("Exception Information:\n%s"%my_ex)
            elif message:
                log.error("Exception Message:\n%s"%message)
        finally:
            # We need to call some kind of recover method
            raise TestCaseError(sut, message=self.message, ex=ex)
    
    def __str__(self):
        return self.value
        
    
class TestCasePostExecuteError(Exception):
    """
        Is raised during the test case post-execute sequence if an error occurs.
        This is to be a recoverable error where the rebuilt happens prior to the
        next test case's start.
    """
    
    def __init__(self, sut, message=None, ex=None):
        try:
            log = Log(sut.log_server, sut.log_port, self.__class__.__name__)
            import traceback
            if ex:
                exc_type, exc_value, exc_traceback = sys.exc_info()
                lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
                my_ex = lines[2:]          
                log.error("Exception Information:\n%s"%my_ex)
            elif message:
                log.error("Exception Message:\n%s"%message)
        except Exception, ex:
            # We need to call some kind of recover method
            raise TestCaseError(sut, message=self.message, ex=ex)
    
    def __str__(self):
        return self.value
    
    
class TestProcedureFail(Exception):
    """
     This error can be raised by the test procedure child classes if a 
     failure condition occurs. This error is also raised by TestProcedure
     if a shell command fails with auto_check and faile_on_error set.
     TestProcedureFail is handled by TestCase and re-raised as TestCaseFail
     to indicate a test failure.
    """
    def __init__(self, sut=None, message=None,ex=None, pro=None):
        if sut != None and pro != None:
            _log = Log(sut.log_server, sut.log_port, self.__class__.__name__, force=True)
            if (sys.getsizeof(str(pro.output)) > pro.MAX_PRINT_SIZE) \
                or (sys.getsizeof(str(pro.shell_stdout)) > pro.MAX_PRINT_SIZE) \
                or (sys.getsizeof(str(pro.shell_stderr)) > pro.MAX_PRINT_SIZE):
                _tmp = os.path.join(tempfile.gettempdir(),"saved_pros")
                if os.path.exists(_tmp) == False:
                    os.mkdir(_tmp)
                pro_loc = tempfile.mktemp(suffix='.pro', dir=_tmp)
                _log.debug("Dumping pro to: %s"%pro_loc)
                pickle.dump(pro, open(pro_loc, "w+"))
                _msg = "The PRO associated with this Failure can be found at:%s %s"%(
                                                                    network.get_local_hostname(),
                                                                    pro_loc)
                message = "%s\n%s"%(_msg,message) 
        raise TestCaseFail(sut, message=message, ex=ex, pro=pro)

    def __str__(self):
        return self.value


class TestProcedureError(Exception):
    """
     TODO: comment...
    """
    def __init__(self, sut=None, message=None, pro=None, ex=None):
        try:
            pass
        except:
            pass
        finally:
            raise TestCaseError(sut, message=message, ex=self)
    def __str__(self):
        return "TestProcedureError message:%s"%self.message
    
    
class TestProcedureTimoutError(Exception):
    """ 
        A test procedure timeout has been exceeded and this error
        raised.
        
        This error should be handled (if possible) by TestProcedureError.
    """
    def __init__(self, sut=None,  message=""):
        raise TestProcedureError(sut=sut,message=message,ex=self)
    
    def __str__(self):
        return "TestProcedureTimoutError:%s"%self.message
    
    
    
class TestProcedureExecutionError(Exception):
    """ 
        A test procedure execution error has occurred. This could be something
        like a malformed command or where the procedure terminated unexpectedly.
        
        This error should be handled (if possible) by TestProcedureError.
    """
    def __init__(self, message=""):
        #TODO: more error-specific logging
        self.message = "%s: %s" % (self.__class__.__name__, message)   
        raise TestProcedureError(message=self.message)

    def __str__(self):
        return self.value

    
if __name__ == "__main__":
    raise FatalError(" Something bad happened.")