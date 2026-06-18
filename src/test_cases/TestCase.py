import sys
import os
import abc
import datetime
import yaml
import ae
from ae.loader import Loader
from ae import ae_logger
import __builtin__


__builtin__.tp_refs = []               # We use this as a x-module global
                                       # for the testcase tp references 

class TestCase(object):
    __metaclass__ = abc.ABCMeta

    def __init__(self, env_config, suite_config):
        self.sut            = env_config        # the environment object
        self.suite_config   = suite_config      # suite config object
        self.data_file      = None              # test data file
        self.args           = {}                # dict of args used for execution
        self.kwargs         = {}                # dict of args (prolly overide args)
        self.log            = None              # our logger reference
        self.triage_preset  = None              # hanger for a triage preset routine
        
        self._pre_start_time    = None          # pre-execution start time
        self._pre_end_time      = None          # pre-execution stop                        
        self._main_start_time   = None          # main-execution start                
        self._main_end_time     = None          # main-execution stop
        self._post_start_time   = None          # post-execution start
        self._post_end_time     = None          # post-execution stop
        
        self._PRE_EXEC_TRIES = 1                # pre-exec tries(will repeat N-1 times)
        self._MAIN_EXEC_TRIES = 1               # main TC tries 
        self._POST_EXEC_TRIES = 1               # post-exec tries
        
    
    @abc.abstractmethod
    def pre_execute(self):
        """
         Test pre-execution step. This is automatically executed prior to the
         execution step and can be used for calling test procedures to both
         check the state of the cluster as well as do any setup manipulation
         required for the actual test.
        """
        pass    
    
    
    @abc.abstractmethod
    def main_execute(self):
        """
         Main execution aspect of the Test case e.g. the interesting part of the test case.
        """
    
    @abc.abstractmethod
    def post_execute(self):
        """
         Test post-execution step. Automatically executed after the test is complete.
         This is where we want to do any post test inspections to verify the state of
         the cluster and any cleanup to restore the cluster to a known, good state.
        """
        pass

        
    def stop_all_tps(self):
        """
         Iterates thru the TP reference list and calls stop().
         This should help keep the test driver clean for each test.
        """
        STOP_ALL_ITERATIONS = 10
        
        i = 0
        while True:
            i += 1
            tp_refs = __builtin__.tp_refs
            
            # reference count is zero, we're done here
            if len(tp_refs) == 0:
                break
            
            # we've hit are max tries so we log a warning and try to clear
            # our the reference list so we don't pollute the next test
            if i == STOP_ALL_ITERATIONS:
                self.log.warning("Failed to stop all TPs. Still running: %s"%tp_refs)
                tp_refs = None
                try:
                    del __builtin__.tp_refs[:]
                except:
                    pass
                break
            cant_stops = []
            for tp in tp_refs:
                try:
                    tp.stop()
                    self.log.debug("done stopping [%s]"%tp)
                except:
                    self.log.warning("Failed to stop still running TP [%s]"%tp)
                    cant_stops.append(tp)
            
            # Now we remove any TP's that raise an error during stop 
            for cant_stop in cant_stops:
                try:
                    tp_refs.remove(cant_stop)
                except ValueError:
                    continue

        
    def _load_and_override_args(self):
        """ Loads the test data file and saves the args to be
            used for the test case. Then looks at any args specified
            in the suite file and if needed, overrides the testcase
            args with the suite ones.
        """   
        # open the data file and load those args.
        if self.data_file:
            p = os.path.dirname(sys.modules[self.__module__].__file__)
            self.data_file = p+os.path.sep+self.data_file
            
            
            if os.path.exists(self.data_file) == False:
                msg = "Datafile does not exist:%s" % self.data_file
                raise ae.ae_errors.TestCaseError(self.sut, message=msg)
            
            self.log.debug("Reading data file:[%s]"% self.data_file)
            try:
                file_stream = file(self.data_file, 'r')
            except Exception, e:
                msg = "Failed to read data file."
                raise ae.ae_errors.TestCaseError(self.sut, message=msg, ex=e)
            try:
                tmp_dict = yaml.load(file_stream)
            except (yaml.parser.ParserError, yaml.scanner.ScannerError) as e:
                msg = "YAML file is malformatted:%s\n%s" % (self.data_file,str(e))
                raise ae.ae_errors.TestCaseError(self.sut, message=msg, ex=e)
        
            if not tmp_dict:
                self.log.warning("No data in %s"%self.data_file)
            if isinstance(tmp_dict,dict) == False:
                msg = "Data was not found to be a dictionary"
                raise ae.ae_errors.TestCaseError(self.sut, message=msg, ex=e)
            
            self.args =  tmp_dict
            self.log.debug("Data file contents:%s"%self.args)
        
        # override the args with kwargs where needed
        try:
            if self.kwargs:
                self.args.update(self.kwargs)
        except Exception, e:
            msg = "An error occurred while updating the args"
            raise ae.ae_errors.TestCaseError(sut=self.sut, message=msg, ex=e)
        
    
    def Go(self, data_file = None, **kwargs):
        
        
        self.log = ae_logger.Log(self.sut.log_server,self.sut.log_port,self.__class__.__name__,force=True)
        
        if data_file:
            self.data_file = data_file
            
        if kwargs:
            self.kwargs = kwargs
        
        # prepare our arg dictionary
        self._load_and_override_args()
        
        # attempt the pre-execute sequence. It will re-attempt the sequence on
        # error as specified by _PRE_EXEC_TRIES
        pre_attempts = 0
        while pre_attempts < self._PRE_EXEC_TRIES:
            try:
                pre_attempts += 1
                self._pre_start_time = datetime.datetime.now() 
                self.pre_execute()
                self._pre_stop_time = datetime.datetime.now()
                break
            except Exception, ex:
                if pre_attempts == self._PRE_EXEC_TRIES:
                    raise ae.ae_errors.TestCasePreExecuteError(self.sut, ex=ex)

        
        # Do our main "test" sequence.
        # Note that an error will allow the test to be re-attempted but
        # a test failure will NOT be re-attempted.
        main_attempts = 0
        while main_attempts < self._MAIN_EXEC_TRIES:
            try:
                main_attempts += 1
                self._main_start_time = datetime.datetime.now() 
                self.main_execute()
                break
            except ae.ae_errors.TestCaseFail, ex:
                self._main_stop_time = datetime.datetime.now()
                import traceback
                self.log.error(traceback.print_exc())
                self._test_fail(ex)
                break
            except Exception, ex:
                self._main_stop_time = datetime.datetime.now()
                if main_attempts == self._MAIN_EXEC_TRIES:
                    self._test_error(ex)
        # do our post test sequence.
        self.log.info("Starting Post Execution")
        post_attempts = 0
        while post_attempts < self._POST_EXEC_TRIES:
            try:
                post_attempts += 1
                self._post_start_time = datetime.datetime.now() 
                self.post_execute()
                self._post_stop_time = datetime.datetime.now()
                break
            except Exception, ex:
                if post_attempts == self._POST_EXEC_TRIES:
                    raise ae.ae_errors.TestCasePostExecuteError(self.sut, ex=ex)
        
                
    def _test_fail(self, ex):
        """
         A failure condition has been hit and we need to 
         fire off the on_failure methods (if set).
         Re-raise the failure exception up to the main script.
         TODO: Test rail reporting?
        """
        try:
            if hasattr(self, "on_failure"):
                self.on_failure()
            elif hasattr(self, "on_abort"):
                self.on_abort()
            else:
                pass
        except Exception, the_ex:
            self.log.warning("Error occurred in on_failure(): %s"%the_ex)
        raise ex
        
    def _test_error(self, ex):
        """
         A error condition has been hit and we need to fire off 
         the on_error methods (if set) then re-raise the error. 
        """
        try:
            if hasattr(self, "on_error"):
                self.on_error()
            elif hasattr(self, "on_abort"):
                self.on_abort()
            else:
                pass
        except Exception, the_ex:
            self.log.warning("Error occurred in on_error(): %s"%the_ex)
        raise ae.ae_errors.TestCaseError(self.sut, ex=ex, message=ex.message)
    

    #def on_failure(self):
    #    """
    #     Triggered upon a testcase failure event. 
    #     This method can be used to trigger cleanup (or other) routines
    #     after a failure has been detected.
    #    """


    #def on_error(self):
    #    """
    #     Triggered upon a testcase error event. 
    #     This method can be used to help cleanup the test environment or something.
    #    """


    #def on_abort(self):
    #    """
    #     Triggered upon both a testcase failure or an error event. This method only
    #     runs if the respective on_failure or on_error method is not implemented. 
    #     This method can be used to help cleanup the test environment or something.
    #    """
