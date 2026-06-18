import os
import random
import time
import test_procedures
from ae import ae_errors, soaper
from test_cases import TestCase
from lib import constants



class soap_event_listener(TestCase.TestCase):
    """
       An example on how soaper's EventListener class can be used
       to receive events.
       
       This example assumes FLDC is installed.
       
    """
    
    def pre_execute(self):

        pass
        

    def main_execute(self):   
        n1 = self.sut.nodes[0]
        
        # Set the hccId if to skip the HCC setup stuff 
        hccId = None
        hccId = "a70575c4-67d3-47e8-a424-cf0c8a7142a7"
        
        if hccId == None:
            setup_tp = test_procedures.cluster.setup_cluster.ResetRNA_SAN(self.sut, self.suite_config)
            setup_tp.run(node=n1, **self.args)
            
            create_hcc = test_procedures.cluster.setup_cluster.CreateHccApi(self.sut, self.suite_config)
            create_hcc.run(target_node=n1)
            
            #Get HCC Id to pass to the GetEvents API call:
            getHcc = test_procedures.cluster.setup_cluster.GetHccId(self.sut,self.suite_config)
            hccId = getHcc.run(target_node=n1).output
        
        # ip of test driver
        endpoint_ip = self.sut.pyro_ns_name  
        endpoint_port = 9050
        
        self.log.info("Registering the event handler to %s:%s"%(endpoint_ip,endpoint_port))
        registerEH = test_procedures.cluster.TAevents.RegisterEventHandler(self.sut, self.suite_config)
        registerEH.run(target_node=n1, hccId=hccId, endpoint_ip=endpoint_ip, endpoint_port=endpoint_port)
        
        # Start the soaper event listener
        self.log.info("Starting soaper event listener on port:%s"%endpoint_port)
        listener = soaper.EventListener(self.sut, endpoint_port)
        listener.start()
        
        self.log.info("Generating test event")
        testEV = test_procedures.cluster.TAevents.CreateTestEventRequest(self.sut, self.suite_config)
        CriticalCookie = random.randint(1, 999999)
        testEV.run(target_node=n1, hccId=hccId, severity=1, cookie=CriticalCookie)
        
        self.log.info("Stopping listener")
        listener.stop()
        
        self.log.info("Here are the events the listener received:")
        
        events = listener.get_events()
        self.log.info("We received %s events"%len(events))
        i = 1
        for event in events:
            self.log.info("%s:%s"%(i,event))
            i+=1
        
    def post_execute(self):
        pass