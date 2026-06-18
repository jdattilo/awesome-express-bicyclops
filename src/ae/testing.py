import os
import sys
import datetime
import time
import traceback
from copy import deepcopy
import ae_errors
import ae_logger
import prepper
import loader
from lib import string_extensions, constants, presets
import tarfile
import httplib
import json
import base64



# time to sleep between test execution
TEST_EXEC_BUFFER = 5
TRIAGE_FILENAME  = "csi.log"
MAX_SU_MSG_LENGTH = 4096
ARCHIVE_CFG_FILENAME = 'ae2_cfgs_logs.tar.gz'

class Halt():
    Fail, Error, Any = range(3)


class TestRunner():
    """ 
     Helper class to facilitate test execution and 
     (local) results tracking.
    """
    
    def __init__(self, sut, suite, extra_args):
        
        self.suite          = suite
        self.sut            = sut
        self.log            = None
        self.test_summary   = "\n\nTEST EXECUTION SUMMARY\n-----------------\n\n"
        self.total_tests    = 0
        self.total_passed   = 0
        self.halt_level     = None
        self.extra_args     = extra_args
        self._abort_flag    = False
        self._results_file  = None
        self._triage_file   = None
        self._tmp_result    = None
        self._current_tc    = None
        self._run_complete  = False
        self._archive_cfgs  = False
        self._upload_results= False
        self.tr_uploader    = TestRailUploader(self.suite)
        self.tr_data        = TestRunData(self.sut)
        
        
    def _setup_log(self):
        if self.log == None:
            self.log = ae_logger.Log(self.sut.log_server, self.sut.log_port)
            
            
    def _set_results_file(self):
        """
         Sets our results filename using the convention of
         environment file _ timestamp . file
         
             example: atl3_20121019_155312.results
        """
        
        env_file = self.sut.get_env_conf_filename()
        env_file = os.path.basename(os.path.splitext(env_file)[0])
        ts = time.strftime("%Y%m%d_%H%M%S",time.gmtime())
        _file = "%s_%s.results"%(env_file, ts)
        log_path = "%s%slogs"%( prepper.find_ae_path() ,os.path.sep)
        
        self._results_file = os.path.join(log_path,_file)
        self._triage_file = os.path.join(log_path,TRIAGE_FILENAME)
        
    
    def _archive_configs(self, results_file):

        # archives env and suite configs
        env_cfg_file = self.sut.get_env_conf_filename()
        suite_cfg_file = self.suite._conf_file
        env_cfg_name = os.path.basename(env_cfg_file)
        log_path = "%s%slogs"%( prepper.find_ae_path(), os.path.sep)
        ae_log_file = 'ae_%s.log' %  ( os.path.splitext(env_cfg_name)[0])
        ae_log_debug_file = 'ae_%s_debug.log' %  ( os.path.splitext(env_cfg_name)[0])
        ae_results_file = os.path.basename(results_file)
        ae_log_file_path = os.path.join(log_path, ae_log_file) 
        ae_log_debug_file_path = os.path.join(log_path, ae_log_file)
        ae_results_file_path = os.path.join(log_path, results_file)
 
        cfg_tar_file = os.path.join(log_path, ARCHIVE_CFG_FILENAME)
        tar = tarfile.open(cfg_tar_file, 'w:gz')
        tar.add(ae_log_debug_file_path, arcname=ae_log_debug_file, recursive=False)
        tar.add(ae_log_file_path, arcname=ae_log_file, recursive=False)
        tar.add(env_cfg_file, arcname=env_cfg_name, recursive=False )
        tar.add(ae_results_file_path, arcname=ae_results_file, recursive=False )

        if isinstance(suite_cfg_file, basestring) == True:
            suite_cfg_name = os.path.basename(suite_cfg_file)
            tar.add(suite_cfg_file, arcname=suite_cfg_name, recursive=False )
        else:
            for i in range(len(suite_cfg_file)):
                suite_cfg_name = os.path.basename(suite_cfg_file[i])
                tar.add(suite_cfg_file[i], arcname=suite_cfg_name, recursive=False )

        tar.close()

    
    def _set_halt_level(self):
        
        if self.suite.halt_level == None:
            return
        
        if self.suite.halt_level.lower() == "error":
            self.halt_level = Halt.Error
        elif self.suite.halt_level.lower() == "fail":
            self.halt_level = Halt.Fail
        elif self.suite.halt_level.lower() == "any":
            self.halt_level = Halt.Any
        elif self.suite.halt_level.lower() == "none":
            self.halt_level = None
        else:
            msg = "Unsupported halt level [%s] so defaulting to None."%self.suite.halt_level
            self.log.warning(msg)


    def _import_testcase(self, test):
        s = os.path.sep
        name = test.filepath
        cls_name = os.path.basename(name).split('.')[0]
        cls_path = os.path.join(sys.path[0],"test_cases",test.filepath.split('.')[0])
        sys.path.append(cls_path)
        mod = __import__(cls_name)
        mod = getattr(mod, cls_name)
        
        tc = mod(self.sut, self.suite)
        return tc


    def _test_cleanup(self, tc):
        """
         Calls a set of cleanup tasks.
         This is called after each test execution (after the post-execute).
         
         It currently does a lookup on the pyro_sut services and terminates
         all child processes via the pyro_sut.kill_children_procs method.
         
         NOTE: This currently cycles thru the nodes synchronously. A nice 
         enhancement here would be use threads for each node to help speed
         up the cleanup process for multi-node testing.
        """
        import Pyro4
        
        #first we call the testcases stop all procedures method.
        tc.stop_all_tps()
    
        #next we go to each node and more assertively stop the processes.
        ns = Pyro4.locateNS(self.sut.pyro_ns_name, self.sut.pyro_ns_port)
        for node in self.sut.nodes:
            self.log.debug("Cleaning up node [%s]"%node)
            try:
                uri = ns.lookup("proc_caller_%s" % node.get_hostname_only())
                proxy = Pyro4.Proxy(uri)
                proxy.cleanup()
                proxy._pyroRelease()
            except Exception, ex:
                self.log.error("Error during testcase cleanup on %s:%s"%(node, ex))
        ns._pyroRelease()
    
    
    def get_suite_test_count(self):
        """
         Returns the number of tests in the suite object.
         This includes each instance of the test.
        """
        num_tests = 0
        for test in self.suite.test_cases:
            for i in range(test.iterations):
                if test.confs:
                    num_tests += len(test.confs)
                else:
                    num_tests += 1
                
        return num_tests
                
    def do_triage(self, start_time, end_time, **kwargs):
        """
         Calls whatever preset triage routine has been specified by
         the test case
        """
        from lib import presets
        
        if self.suite.triage_preset != None:
            preset = self.suite.triage_preset
            if preset.lower() == "disabled":
                return
            
            self.log.info("Starting triage routine %s"%preset)
            # need to import the presets module and preset class
            cls_path = sys.path[0] + os.path.sep + "lib" 
            sys.path.append(cls_path)
            mod = __import__("presets")
            mod = getattr(mod, "TriagePresets")
            mod = getattr(mod, preset)
            mod(self.sut, self.suite, start_time, end_time)
        elif self._current_tc.triage_preset != None:
            self.log.info("Starting test case triage routine")
            self._current_tc.triage_preset(self.sut, self.suite, start_time, end_time)
        else:
            self.log.info("Starting default triage routine")
            presets.TriagePresets.default_preset(self.sut, self.suite, start_time, end_time)


    def _exec_test(self, tc, testname, case_id=None, description = None, test_data=None, **test_args):
        """
         This method is called by _prep_test to execute a specific test 
         with it's data. The Halt option is handled here.
        """
        
        msg  = "%s with datafile - %s"%(testname, test_data)
        msg2 = None
        start_time = None
        end_time = None
        
        try:
            self.report_start(msg)
            self._current_tc = tc
            start_time = datetime.datetime.now()
            tc.Go(test_data, **test_args)
            self.total_passed += 1
            result = "PASSED"
            self.report_success(msg)
        except ae_errors.TestCaseFail, ex:
            result = "FAILED"
            if ex.message:
                if hasattr(ex, "run_data"):
                    ex.message ="%sTP Data:%s"%(ex.message,ex.run_data)
                result +=":%s"% string_extensions.left_pad_all_lines(ex.message, " ", 4)
                msg2 = ex.message
            
            self.report_failure(msg,msg2)
            
            if self.halt_level == Halt.Fail or self.halt_level == Halt.Any:
                self._abort_flag = True
        except ae_errors.TestCaseError, ex:
            result = "ERROR"
            if ex.message:
                if hasattr(ex, "run_data"):
                    ex.message ="%sTP Data:%s"%(ex.message,ex.run_data)
                result +=":%s"% string_extensions.left_pad_all_lines(ex.message, " ", 4)
                msg2 = ex.message
            self.report_failure(msg, ex.message)
                
            if self.halt_level == Halt.Error or self.halt_level == Halt.Any:
                self._abort_flag = True
        except BaseException:
            self.log.error(traceback.print_exc())
            result = "UNKOWN"
            self.report_failure(msg)
            if self.halt_level != None:
                self._abort_flag = True
        finally:
            self.total_tests += 1
            end_time = datetime.datetime.now()
            _dur = str(end_time.replace(microsecond=0)-start_time.replace(microsecond=0))
            self.test_summary += "    DURATION:%s\n" % _dur
            self.test_summary += "    RESULT:%s\n\n" % result
            self.test_summary += "<ENDTEST>\n"
            
            # upload the test results to Testrail
            if self._upload_results == True and case_id:
                # attempt to populate the TestRunData object and save update run info
                if self.tr_data.is_populated() == False:
                    self.tr_data = presets.find_test_run_data(self.sut, self.suite, self.tr_data)
                    self.log.debug("Run info %s"% self.tr_data)
                if self.tr_data.is_populated():
                    try:
                        self.tr_uploader.update_run(self.tr_data)
                    except:
                        self.log.error("Failed to update Testrail test run.")
                        self._upload_results = False
                else:
                    self.log.debug("Test run data is not populated.")
                
                # now save the test result information
                try:
                    if result == "PASSED":
                        _res = self.tr_uploader.TR_TEST_PASSED
                        _d = {"status_id":_res,
                              "comment":"%s:  %s\ntest_args:%s"%(test_data,
                                                               description,
                                                               tc.args),
                              "elapsed":_dur}
                    else:
                        _res = self.tr_uploader.TR_TEST_FAILED
                        _d = {"status_id":_res,
                              "comment":"%s:  %s\ntest_args:%s\n%s"%(test_data,
                                                                   description,
                                                                   tc.args,
                                                                   msg2),
                              "elapsed":_dur}
                    self.tr_uploader.add_result_for_case(case_id, _d)
                except Exception, ex:
                    self.log.warning("Failed to update Testrail for %s\n%s"%(testname, ex))
                    self._upload_results = False
            
            if result!="PASSED":
                try:
                    self.do_triage(start_time=start_time, end_time=end_time)
                except Exception, ex:
                    self.log.error("Triage routine experienced an error:%s"%ex)
                    exc_type, exc_value, exc_traceback = sys.exc_info()
                    lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
                
                    self.log.error("EXCEPTION TYPE:%s" % type(ex))
                    self.log.error("EXCEPTION MESSAGE:%s" % (ex))
                    self.log.error("CHILD EXCEPTION:%s" % str(lines))
            
            self._tmp_result = result
            self._test_cleanup(tc)
            time.sleep(TEST_EXEC_BUFFER)
        
        # check to see if the halt level was reached and we need to end the run
        if self._abort_flag == True:
            self.log.info("Halt level was reached. Aborting the test run...")
            self._abort_testrun()


    def _prep_test(self, test):
        """
         Prepares a test for execution by importing the testcase module
         and preparing the associative test data.
         Then calls _exec_test() to do the actual test execution.
        """
        
        # do our dynamic import of the test case file.
        # if this fails, we log the import exception
        # and either bail out or halt the test case run.
        def _safe_import(test):
            try:
                tc = self._import_testcase(test)
                self.suite.update_current_tc(test)
                return tc
            except:
                self.total_tests += 1
                _msg = "Failed to import Testcase: %s"%test
                self.log.error(_msg)
                self.log.error(traceback.print_exc())
                self.report_start(test.name)
                self.report_failure(test.name, "Failed to import test or test files.")
                self.test_summary += "    RESULT:ERROR\n"
                if self.halt_level == Halt.Error or self.halt_level == Halt.Any:
                    self._abort_testrun()
        
        tc = _safe_import(test)
        
        if test.args == None:
            test.args = {}
        
        # if we have extra args, update test.args giving precedence to xtras
        if self.extra_args != None:
            _xtra = deepcopy(self.extra_args)
            _xtra.update(test.args)
            test.args = _xtra

        i = 1
        if test.confs:
            for conf in test.confs:
                if not tc:
                    tc = _safe_import(test)
                
                self.log.info("Test [%s] Data [%s]" % (i, conf.test_data))
                self.log.info("Test [%s] Args [%s]" % (i, conf.test_args))
                self.log.info("Test [%s] CaseArgs [%s]" % (i, test.args))
                if not conf.case_id and test.case_id:
                    self.log.debug("Missing Testrail Case_id for %s:%s\nDefaulting to Case_id of %s" %
                                                             (test, 
                                                              conf.test_data,
                                                              test.case_id))
                    conf.case_id = test.case_id
                if conf.test_args != None:
                    self.test_summary += "    Data File:%s\n"% conf.test_data
                    conf.test_args.update(test.args)
                    self.test_summary += "    Args:%s\n"% conf.test_args
                    self._exec_test(tc, test.name, conf.case_id, conf.description, conf.test_data, **test.test_args)
                else:
                    self.test_summary += "    Data File:%s\n"% conf.test_data
                    self.test_summary += "    Args:%s\n"% test.args
                    self._exec_test(tc, test.name, conf.case_id, conf.description, conf.test_data, **test.args)
                tc = None
        elif test.args:
            self.log.info("Test [%s] CaseArgs [%s]" % (i, test.args))
            self.test_summary += "    Args:%s\n"% test.args
            self._exec_test(tc, test.name, test.case_id, None, **test.args)
        else:
            self.log.info("Test [%s] No Data" % (i))
            self._exec_test(tc, test.name, test.case_id)
        

    def _abort_testrun(self):
        self._do_summary_results()
        self.log_test_summary()
        self._run_complete = True
        raise ae_errors.FatalError("Aborting the test run.")


    def _do_summary_results(self):
        self.test_summary +="FINAL RESULTS"
        self.test_summary +=" %s of %s TESTS PASSED"%(str(self.total_passed), str(self.total_tests))
        self.test_summary += "\n\n\n"
        
        if self._archive_cfgs == True:
            results_file = self._results_file
            self._archive_configs(results_file)

    
    def run_tests(self):
        """
         Runs all the tests in the suite file.
        """
        # do some init stuff
        self._setup_log()
        self._set_halt_level()
        self._set_results_file()
        
        try:
            for k,v in self.extra_args.items():
                if k.lower() == 'archive_configs' and v.lower() == 'true':
                    self._archive_cfgs = True
                if k.lower() == 'testrail' and v.lower() == 'true':
                    self._upload_results = True
        except:
            pass
        
        # create the testrail test run
        if self.suite.suite_id and self._upload_results == True:
            try:
                self.tr_uploader.add_run()
            except Exception,ex:
                self.log.error("Failed to add new TestRail test run.")
                self.log.error("%s"%ex)
                self._upload_results = False
        
        if os.path.isfile(self._triage_file):
            try:
                os.remove(self._triage_file)
            except Exception, ex:
                self.log.warning("Failed to remove remote triage file:%s"%ex)
        
        self.report_number_tests(self.get_suite_test_count())
        
        for test in self.suite.test_cases:
            self.test_summary += "<TESTBLOCK>\n"
            self.test_summary += "%s : %s\n"% (test.filepath, test.name)     
            self.log.info("<TESTBLOCK>")
            self.log.info("Test Start %s : %s"%(test.filepath,test.name))
            for i in range(test.iterations):
                self._prep_test(test)
                self.log_test_summary()
                self.log.info("Test End %s : %s : %s"%(test.filepath,test.name, self._tmp_result))
                self.log.info("<ENDTEST>")
        self._do_summary_results()
        self.log_test_summary()
        self._run_complete = True

    
    def stop_tests(self):
        if self._run_complete == False:
            self._run_complete = True
            self._abort_testrun()
        
    
    def get_test_summary(self):
        """
         Returns a string of the test summary
        """
        return self.test_summary
    
    
    def log_test_summary(self):
        """
         Prints (or logs) the test details in a well-formatted
         manner pleasing to the eye. 
        """
        #create or truncate existing file and open for writing
        res_file = open(self._results_file, "w")
        res_file.write(self.test_summary)
        res_file.close()
        

    def to_sutext(self, message):
        """
         Strips away any characters which may break the subunit format
        """
        if message == None:
            return None
        else:
            import re
            return (re.sub('[\[\]]|', '', message))[:MAX_SU_MSG_LENGTH]
        
        
             
    def report_start(self, testname):
        """
         Record the beginning of a test.
         Logs a Subunit compatible test start message that is both human and
         computer readable.
        
         :param string testname: name of test that is starting
        """
        self.log.info("test: %s"%testname)
        return True


    def report_success(self, testname, successtext=None):
        """
         Record that a test has passed.
         Logs a Subunit compatible test success message that is both human and
         computer readable. *successtext* is an optional argument that can describe
         the conditions of the test passing. 
        
         :param string testname: name of test that passed
         :param string successtext: explanation of test success
        """
        if successtext:
            self.log.info("success: %s [\n%s\n]"%(testname, self.to_sutext(successtext)))
        else:
            self.log.info("success: %s"%testname)
    

    def report_failure(self, testname, failuretext=None):
        """
         Record that a test has failed.
         Logs a Subunit compatible test failure message that is both human and
         computer readable. *failuretext* is a required argument that describes
         the conditions of test failure. 
        
         :param string testname: name of test that failed
         :param string failuretext: explanation of test failure
        """
        if failuretext:
            self.log.info("failure: %s [\n%s\n]"%( testname, self.to_sutext(failuretext)))
        else:
            self.log.info("failure: %s"%testname)


    def report_retest(self, testname):
        """
         Record that a test is in retest state due to previous failures.
         :param string testname: name of the test that is in retest state
        """
        self.log.info("retest: %s"%testname)


    def report_number_tests(self, numtests):
        """
         Record the expected number of tests about to be run.
         Logs a Subunit compatible expected number of tests to run message that is
         both human and computer readable.    
         :param integer numtests: number of tests that will be run
        """
        self.log.info("progress: %d"%numtests)


class TestRunData():
    
   
    def __init__(self, sut):
        self.sut = sut
        self.hostnames   = []    # list of node hostnames
        self.os_name     = None  # OS name
        self.os_version  = None  # OS-kernel version
        self.revision    = None  # build revision
        self.build_type  = None  # build type (debug, retail)
        self.options     = {}    # optional testrun qualifiers
        
        self._populate()
    
    def _populate(self):
        """
         Populates the "static" data from the 
         SUT object.
        """
        _hosts = []
        for _node in self.sut.get_fldc_nodes():
            _hosts.append(_node.get_hostname_only())
        self.hostnames = _hosts
        
    def is_populated(self):
        """
         Returns True or False based on all TestRunData members
         (except options) being populated
        """
        for k,v in self.__dict__.items():
            if k == "options" or k == "sut":
                continue
            if not v or len(v)==0:
                return False
        return True
    
    def __str__(self):
        _str = ""
        for k,v in self.__dict__.items():
            _str += "%s:%s\n"%(k,v)
        return _str

class TestRailUploader():
    """ 
     Test results uploader for testrail using their JSON API.
     
     The python json module seems to be explicitly typed and data 
     types are not implicitly converted so things like trailing commas 
     will be treated as tuples.
    """ 
    
    PROJECT_ID = 18 # 19 experimental
                    # 18 Hermes2
    
    MILESTONE =  23   # 23 Hermes2 AutoReg

    #TR_TEST_UNTESTED = 3 # but doesnt seem to work
    TR_TEST_PASSED = 1
    TR_TEST_BLOCKED = 2
    TR_TEST_RETEST = 4
    TR_TEST_FAILED = 5  
    
    # Operation POST-GET mappings
    PG = {"add_run":"POST",
          "update_run":"POST",
          "add_result_for_case":"POST",
          "delete_run":"POST",
          "get_test":"GET",
          "get_case":"GET",
         }
    
    
    def __init__(self, suite, username="chris_powers@dell.com", password="password"):
        self.suite = suite
        self.username = username
        self.password = password
        base64string = base64.encodestring('%s:%s' % (self.username, self.password)).replace('\n', '')
        self.header = {'Content-Type': 'application/json',
                       'Authorization': "Basic %s" % base64string,
                       'Accept':'*/*'}
        
        self.run_id = None      # test run ID that we'll add results
        self.run_data = None    # reference to TestRunData object
        self._run_updated= False # flag denoting run was updated

        
    def _make_request(self, operation, my_id, my_id2=None, data=None):
        """
            Makes a request to testrail. Note that we have to avoid
            using the handy urllib2 connection methods because they
            will default to POSTs and some testrail operations (queries)
            require a GET.
        """
        if not operation:
            raise AttributeError("Make request requires an operation")
        if not my_id:
            raise AttributeError("Make request requires an id")
        
        h = httplib.HTTPConnection(constants.TESTRAIL)
        #h.debuglevel = 1
        if data:
            data="%s"%json.dumps(data)
            if my_id2 == None:
                h.request(self.PG.get(operation),
                          '/index.php?/api/v2/%s/%s'%(operation, my_id),
                          body=data,
                          headers=self.header)
            else:
                h.request(self.PG.get(operation),
                          '/index.php?/api/v2/%s/%s/%s' % (operation, my_id, my_id2),
                          body=data,
                          headers=self.header)
        else:
            h.request(self.PG.get(operation), '/index.php?/api/v2/%s/%s'%(operation,my_id), headers=self.header)
            
        resp = h.getresponse()
        if resp.status!=200:
            raise TypeError("error:%s:%s"%(resp.status, resp.reason))
        
        return resp

            
    def get_case(self,case_id):
        """
         Returns the specific test
        """
        return self._make_request("get_case", case_id)


    def get_test(self,test_id):
        """
         Returns the specific test
        """
        return self._make_request("get_test", test_id)
    
    
    def get_tests_in_run(self, run_id):
        """
            Returns a list of tests associated with the run.
        """
        pass
    

    def add_run(self, project_id=PROJECT_ID, run_desc = None):
        """
         Creates a new test run in the given project.
            suite_id    int    The ID of the test suite for the test run (required)
            name    string    The name of the test run
            
            description    string    The description of the test run
             NOTE: we can use a uuid to the AE2 run to do future lookups.
        """
        name = None
        if run_desc:
            name = "%s %s"%(self.suite.name, run_desc)
        else:
            name = self.suite.name
        self.run_name = name
        data = {"suite_id":self.suite.suite_id,
                "name":name,
                "description":self.suite.description,
                "milestone_id":self.MILESTONE}
        res = self._make_request("add_run", project_id, data=data) 
        res = json.load(res)
        self.run_id = res["id"]


    def update_run(self, run_data):
        if not self.run_id:
            AttributeError("Cannot update test run without a run_id.")
        if self._run_updated:
            return
        
        self.run_data = run_data
        self.run_name +=" %s%s %s %s"%(run_data.os_name,
                                      run_data.os_version,
                                      run_data.revision,
                                      run_data.build_type)
        data = {"name":self.run_name}
        self._make_request("update_run", self.run_id, data=data)
        self._run_updated = True
        

    def delete_run(self, run_id):
        """
         Deletes the test run
        """
        return self._make_request("delete_run", run_id)


    def add_result_for_case(self, case_id, data=None):
        """ 
         Adds a test result for the given test case occurin the run.
        """
        if not self.    run_id:
            raise AttributeError("Missing Testrail run_id.")
        if self.run_data:
            if not data:
                data = {}
            data.update({"version":self.run_data.revision,
                         "custom_hostname":",".join(self.run_data.hostnames),
                         "custom_os":"%s%s"%(self.run_data.os_name,self.run_data.os_version)
                         })
        print data
        self._make_request("add_result_for_case",self.run_id, case_id, data)
    
    
if __name__== '__main__':
    s=os.path.sep
    p = "..%ssuite_files%sautoreg%svsa_full.cfg"%(s,s,s)
    suite_cfg = (os.path.abspath(p))
    s = loader.Suite(suite_cfg)
    s.load()
    
    print "suite id :%s"%s.suite_id
    exit()
    
    print "Start"
    tr = TestRailUploader(s)

    _d = {
          "name":"test"}
    tr.add_run(run_desc="fancy")
    _tests = s.test_cases
    for _t in _tests:
        _d = {"name":"test",
              "status_id":5,
              "comment":"woohhoooo2",
              "elapsed":"0:04:38"}
        tr.add_result_for_case(_t.case_id, _d)
    
    
    #steps = [
    #         {
    #          "status_id": 1,
    #          "content": "Step 1", 
    #          "expected": "Result 1",
    #          "actual": "Actual Result 1"
    #          },
    #         {
    #          "status_id": 5,
    #          "content": "Step 2",
    #          "expected": "Result 2",
    #          "actual": "Actual Result 2"
    #          }
    #         ]
    #
    #for _t in _tests:
    #    _d = {"name":"test",
    #          "status_id":5,
    #          "comment":"woohhoooo2",
    #          "elapsed":"0:04:38",
    #          "custom_step_results" : steps 
    #    }
    #    tr.add_result_for_case(_t.case_id, _d)
    
    print "Done"
    
    
    
    
