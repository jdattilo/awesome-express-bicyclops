import time
import test_procedures
from test_cases import TestCase
from ae.environment import NODE_ROLES


class vsa_init(TestCase.TestCase):
    
        
    def pre_execute(self):
        pass


    def main_execute(self):
        
        LATEST_OVA = "http://nfs5.rnanetworks.com/exports/build_n_test/HERMES20/vsa/pdbg/44980/Fluid-Cache-Dell-3.0.0.44980_pdbg.ova"
        ova_url = self.args.get("ova_url", LATEST_OVA)
        
        #Does the deploy, vsa setup, starts AE2 on the vsa
        setup_tp = test_procedures.driver.vcenter.AutoSetupVsa(self.sut, self.suite_config)
        setup_tp.run(ova_url=ova_url, redeploy=True, timeout=7200)

        
        # runs our trusty AutoSetup procedure suite to configure FDLDC
        #setup_vsa_tp = test_procedures.cluster.hrm_config.setup.AutoSetupCluster(self.sut, self.suite_config)
        #setup_vsa_tp.run(as_reset_cluster='hard_all',
        #                 as_start_if_stopped=True, 
        #                 as_autoprovisioning='all',
        #                 **self.args)
        
        # Setup the clients nodes
        #setup_clients = test_procedures.driver.provisioning.SetupClients(self.sut, self.suite_config)
        #setup_clients.run()

        
        # Do some simple io on the clients
    
    def post_execute(self):
        pass      
