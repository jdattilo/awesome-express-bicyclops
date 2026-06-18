import sys
import os
import test_procedures
from test_cases import TestCase
#import ae_errors

import logging
logging.basicConfig()


def verify_list_ssd_stdout(diskL, num_expected_disks):
    #print "diskL: ", diskL
    ret_code = False
    len_disk_entriesL = len(diskL)
    #Verify the number of disks found is as expected:
    if (len_disk_entriesL != num_expected_disks):
        print "\n\nERROR: Found a different number of disks: %i than expected: %i. Found: %s "\
                     % (len_disk_entriesL, num_expected_disks, diskL)
    else:
        ret_code = True
    return ret_code


class list_ssd2(TestCase.TestCase):
    #make an argument to object? Or test data in data.cfg?
    num_expected_disks = 7 
    test_success = True
    test_count = 0

    def pre_execute(self):
        pass



    def main_execute(self):
        diskL = []
        tp = test_procedures.cache.control.list.ListSsd(self.sut, self.suite_config)
        
        #TEST: /opt/rnanetworks/bin/rnacmd   --list --disk
        
        if self.args:
            print "Running with data from dat file"
            print "Data file args:", self.args
            
            opt_str = self.args.get("opt_str")
            print "Data file opt_str: %s" %opt_str
            
            pro = tp.run(optionStr=opt_str)
        else:
            print "No data... we won't do anything for this example."
            return
            
         
        diskL = tp.get_list_ssds(pro.shell_stdout)
        ret = verify_list_ssd_stdout(diskL, self.num_expected_disks)
        if ret:
            print "TEST: /opt/rnanetworks/bin/rnacmd   --list --disk : +PASSED"
        else:
            self.test_success = False
            print "TEST: /opt/rnanetworks/bin/rnacmd   --list --disk : +FAILED"
        
        


    def post_execute(self):
        print "INFO: list_disk: number of tests: %i" % self.test_count
        if self.test_success:
            print "INFO: TEST: list_disk =PASSED."
        else:
            print "ERROR: TEST: list_disk =FAILED"





if __name__ == "__main__":

    from ae import loader
    der = os.path.dirname(sys.path[0])
    sys.path.append(os.path.join(der, '..'))
    suite_config_file = os.path.abspath(os.path.join(der, '..','..', 'suite_files','list_ssd2.cfg'))
    env_conf_file = os.path.abspath(os.path.join(der, '..','..', 'env_files','cp_atl3.cfg'))

    def testing_list_disk():

        suite,sut = loader.Loader.get_run_info(suite_config_file, env_conf_file)

        tc = list_ssd2(sut, suite)
        tc.Go()

    testing_list_disk()
