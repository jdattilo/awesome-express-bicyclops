import os
import ae_errors
import environment
import prepper

try:
    import yaml
except ImportError:
    pass

class Loader:
    
    def __init__(self):

        _isTestCasesRandom = False
        _isTestConfsRandom = False
                        
    @staticmethod
    def parse_yaml_file(conf_file):
        """ 
         Parses a YAML config file containing interesting data.
         Raises a AE fatal exception if an error occurs and passes
         the underlying exception along for logging/debugging.
         
         Returns the root tmp_dict
        """
        
        if os.path.exists(conf_file) == False:
            raise ae_errors.FatalError("Config file does not exist:%s" % conf_file)
        
        file_stream = file(conf_file, 'r')
        
        try:
            tmp_dict = yaml.load(file_stream)
        except (yaml.parser.ParserError, yaml.scanner.ScannerError), ex:
            msg = ("YAML file is malformatted:%s\n%s" % (conf_file,str(ex)))
            raise ae_errors.FatalError(msg)
        
        if not tmp_dict:
            print "WARNING: Dictionary from file was empty:[%s]" % conf_file
            

        return tmp_dict
    
    @staticmethod
    def get_run_info(suite_config_file, env_conf_file):
        """
         This is the external method that would be called by something like
         ae.py to provide the suite(testcase, test config, config variables)
         and the environment(sut, test driver, etc) for the test suite run.
        """
        suite = Suite(suite_config_file)
        suite.load()
        
        sut = environment.Sut(env_conf_file)
        sut.load()
        
        return (suite, sut)
        


class Suite:
    def __init__(self, suite_file):
        self.name = None                    # the name of this suite
        self.suite_id = None                # testrail suite_id
        self.description = None             # description of the suite
        self._conf_file = suite_file        # path to our suite config file
        self.test_cases = []                # list of testcases in the suite
        self.proc_timeout = None             # timeout for test procedures
        self.halt_level = None              # test run halt level (Fail|Error|Any) 
        self.triage_preset = None           # suite-level default triage override
        self._current_test_case = None      # reference to the testcase running


    def load(self):
        
        conf_dict = {}
        test_list = []
        if isinstance(self._conf_file, list) == True:
            first = True
            for _file in self._conf_file:
                conf_dict.update(Loader.parse_yaml_file(_file))
                if first == True:
                    self.name = conf_dict["SUITE"]
                    self.suite_id = conf_dict.get("SUITE_ID")
                    self.description = conf_dict["DESCRIPTION"]
                    self.halt_level = conf_dict.get("HALT_LEVEL")
                    self.triage_preset = conf_dict.get("TRIAGE_PRESET")
                    self.proc_timeout = conf_dict.get("PROCEDURE_TIMEOUT")
                    first = False
                for _test in conf_dict["TESTLIST"]:
                    test_list.append(_test)
        else:
            conf_dict = Loader.parse_yaml_file(self._conf_file)
            self.name = conf_dict["SUITE"]
            self.suite_id = conf_dict.get("SUITE_ID")
            self.description = conf_dict["DESCRIPTION"]
            self.halt_level = conf_dict.get("HALT_LEVEL")
            self.triage_preset = conf_dict.get("TRIAGE_PRESET")
            self.proc_timeout = conf_dict.get("PROCEDURE_TIMEOUT")
            test_list = conf_dict["TESTLIST"]
        
        
        #
        # TODO  this really needs re-worked
        # CP20131025
        # 
        for test_case in test_list:
            
            tests = []
            case_name = test_case["TESTCASE"]
            case_id = test_case.get("TESTCASE_ID")
            
            # iterate thru the test list and for each testcase we
            # create a new test case object with the test case name or 
            # ID (it just needs to be unique) and a list of test configs
            # and optional override parms.
            try:
                case_confs = test_case["CONFS"]
            except KeyError:
                case_confs = None
            try:
                case_args = test_case["CASE_ARGS"][0]
            except (KeyError,TypeError):
                case_args = {}
            try:
                iterations = test_case["ITERATIONS"]
            except (KeyError,TypeError):
                iterations = 1
            
            if case_confs:
                for conf in case_confs:
                    overs = None
                    conf_id = None
                    test_data = None
                    description = None
                    try:
                        overs = conf["VARS"]
                    except KeyError:            # no override variables specified
                        pass                    # so we eat the exception
    
                    # take the test case conf block information and build 
                    # our test list to be added to the test case
                    for k,v in conf.items():
                        if k == "TESTCASE_ID":
                            conf_id = v
                        elif k != "VARS": 
                            test_data = k
                            description = v
                    new_test = Test(test_data,description, conf_id, overs)
                    tests.append(new_test)
            
            test_set = test_case.get("TESTSET")
            if test_set:
                filepath = os.path.join(test_set,test_case["TESTGROUP"],test_case["TESTFILE"])
            else:
                filepath = os.path.join(test_case["TESTGROUP"],test_case["TESTFILE"])
            self.test_cases.append(TestCase(case_name, filepath, iterations, tests, case_id=case_id, **case_args))
    
    
    def update_current_tc(self, tc):
        """
         Updates the current test case to reflect where we are
         currently are in the test case list.
         NOTE: The TestCase is a loader.TestCase instance
        """
        self._current_test_case = tc
        
    
    def get_current_tc_dir(self):
        return self._current_test_case.get_dir_path()
        
        
class TestCase:
    def __init__(self,test_case_id,filepath,iterations=1,test_configs=[],case_id=None,**kwargs):
        self.name = test_case_id        # name.
        self.case_id = case_id          # testrail id
        self.filepath = filepath        # testcase filepath under /test_cases
        self.confs = test_configs       # list of test configs (Test objs not data files)
        self.args = kwargs              # list of args for the test case (not test conf)
        self.iterations = iterations
    
    def __str__(self):
        return "Name:%s\nTestrail_ID:%s\nFilepath:%s\nConfs:%s\nArgs:%s\n"%(self.name,
                                                                            self.case_id,
                                                                            self.filepath,
                                                                            self.confs,
                                                                            self.args)
        
    def get_dir_path(self):
        from lib import string_extensions
        rel_path = string_extensions.localize_path(self.filepath)
        dir_path = os.path.join(prepper.find_ae_path(),
                                "test_cases",
                                rel_path.split('.')[0])
        return dir_path
        
        
        
class Test:
    """
        Test container object containing test configuration information:
            
            test_config: can either be a path to a config file or a dict.
            It's really going to be up to the tests/proc scripts to handle 
            the config. 
            TODO: Decide which way makes more sense in the testcase/proc layout.
                
            description: string describing the test configuration 
            
            ovverides: an optional (list/dict) of parameters which will
            override the respective parameters in the config file. 
            These override parms will be specified by the user in suite_ex.cfg 
            
        TODO: Decide how to handle no config (like where we want to fallback 
        to a "default" or "parent" config?
    """
    def __init__(self, test_data, description='',case_id=None, test_args=None):
        self.test_data = test_data      # test data file name
        self.description = description  # description of test config
        self.test_args = test_args      # optional dict of args for the test conf
        self.case_id = case_id
            

    
        
        
        
###############################################################################

    
def Run_Loader_tests():
    print "--- Starting Loader Tests ---"
    
    #parse_suite_test()
    get_test_info()
    
    print "--- Ending Loader Tests ---"

def parse_suite_test():
    msg = "parse_suite_test()"
    s = os.path.sep
    p = "..%ssuite_files%sexamples%ssuite_ex.cfg"%(s,s,s)
    suite_cfg = os.path.abspath(p)
    
    s = Suite(suite_cfg)
    s.load()
    
    print msg + "...OK"
        
def get_test_info():
    msg = "get_test_info()"
    s = os.path.sep
    p = "..%ssuite_files%sautoreg%scheck_in_regression.cfg"%(s,s,s)
    suite_cfg = (os.path.abspath(p))
    s = Suite(suite_cfg)
    s.load()
    print " Halt Level:%s" %s.halt_level 
    print " Triage preset:%s" %s.triage_preset
    
    for tc in s.test_cases:
        print "Test Case: %s" % tc
        print "full path: %s" %tc.get_dir_path()
        for conf in tc.confs:
            print " Test Configs:%s" % conf.test_data
            print " Overrides:%s" % conf.test_args
            print " Case_id:%s"%conf.case_id
            
    print msg + "...OK"
    
    

if __name__ == "__main__":
    Run_Loader_tests()
