import test_procedures
from test_cases import TestCase
from time import sleep

class perc(TestCase.TestCase):
    
        
    def pre_execute(self):
        pass     
    

    def main_execute(self):      
       
        # this is assigns n1 to be the first node in the SUT's node list 
        n1 = self.sut.nodes[0]
        # ctrlid = 0 
        # whenever we initialize a new test procedure, we pass in the SUT and suite objects
         
        # run() is how we execute the test procedure synchronously (waits for completion).
        # passing in a node parameter will instruct AE to execute the 
        # procedure on that node. 

        #Get CRTL and VD ID
        vds_list = test_procedures.cluster.perc.Dev2VD.Dev2VD(self.sut, self.suite_config)
        my_pro5 = vds_list.run(node=n1, dev="/dev/sdb")
        my_vd = my_pro5.output
        print my_vd['ctrl_id']
        print my_vd['vd_id']
        print "--------------------------------------------"
        """
        get_ctr = test_procedures.cluster.perc.listControllers.ControllerList(self.sut, self.suite_config)
        my_pro = get_ctr.run(node=n1)
        mydict = my_pro.output
        for dict in mydict:
            if dict['controller_id'] == 0:
                ctrlid = dict['controller_id']
        print dict
        print "--------------------------------------------"
        
        #list pd 
        pd = test_procedures.cluster.perc.listControllerPDs.GetPDList(self.sut, self.suite_config)
        my_pro1 = pd.run(node=n1, ctrlid=my_vd['ctrl_id'])
        mydict1 = my_pro1.output
        for dict1 in mydict1:
            print dict1
        print "--------------------------------------------"

        # free pd
        freepd = test_procedures.cluster.perc.listControllerFreePDs.GetFreePDList(self.sut, self.suite_config)
        my_pro2 = freepd.run(node=n1, ctrlid=my_vd['ctrl_id'])
        mydict2 = my_pro2.output
        for dict2 in mydict2:
            print dict2
        print "--------------------------------------------"
        
        # print VD PD
        vd_pd = test_procedures.cluster.perc.listVDPDs.GetVDPDs(self.sut, self.suite_config)
        my_pro4 = vd_pd.run(node=n1, ctrlid=my_vd['ctrl_id'], vd_id=1)
        mydict4 = my_pro4.output
        
        #vd list
        vd = test_procedures.cluster.perc.listControllerVDs.GetVDList(self.sut, self.suite_config)
        my_pro3 = vd.run(node=n1, ctrlid=my_vd['ctrl_id'])
        mydict3 = my_pro3.output
        for dict3 in mydict3:
            print dict3
        print "--------------------------------------------"

        vd_pd = test_procedures.cluster.perc.listVDPDs.GetVDPDs(self.sut, self.suite_config)
        my_pro4 = vd_pd.run(node=n1, ctrlid=my_vd['ctrl_id'], vd_id=1)
        mydict4 = my_pro4.output
        for dict4 in mydict4:
            print dict4
        print "--------------------------------------------"
        """        
        # Take VD Offline
        vdoffline = test_procedures.cluster.perc.VDStateOffline.VDOffline(self.sut, self.suite_config)
        vdoffline.run(node=n1, ctrlid=my_vd['ctrl_id'], vd_id=my_vd['vd_id'])
        print "--------------------------------------------"
        
        sleep(50)
        # Take VD Offline
        vdonline = test_procedures.cluster.perc.VDStateOnline.VDOnline(self.sut, self.suite_config)
        vdonline.run(node=n1, ctrlid=my_vd['ctrl_id'], vd_id=my_vd['vd_id'])
        print "--------------------------------------------"
        """        
        # Delete VD
        vddelete = test_procedures.cluster.perc.Delete_VDs.DeleteVDs(self.sut, self.suite_config)
        vddelete.run(node=n1, ctrlid=my_vd['ctrl_id'], vd_id=1)
        print "--------------------------------------------"
        
        # Create VD
        vdcreate = test_procedures.cluster.perc.Create_VDs.CreateVDs(self.sut, self.suite_config)
        pd_list = [1, 2, 3]
        vdcreate.run(node=n1, ctrlid=my_vd['ctrl_id'], pd_list=pd_list, raid_level = 0)
        print "--------------------------------------------"
        """    
    def post_execute(self):
        pass
