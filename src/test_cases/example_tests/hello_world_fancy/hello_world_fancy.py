import test_procedures
from test_cases import TestCase


class hello_world_fancy(TestCase.TestCase):
    
        
    def pre_execute(self):
        pass     
    

    def main_execute(self):      
       
        # this is assigns n1 to be the first node in the SUT's node list 
        n1 = self.sut.nodes[0]
        
        # whenever we initialize a new test procedure, we pass in the SUT and suite objects
        delayed_hello = test_procedures.example_procedures.hello_world.DelayedHelloWorld(self.sut, self.suite_config)
        
        # run_aynch will fire off the procedure and return immediately while the 
        # test procedure is running in the background.
        # we can pass the test case arg data into the procedure like this
        delayed_hello.run_asynch()        
        self.log.info("Delayed_hello is off and running")
        
        # if we're bored, we can do other stuff like call the immediate
        self.log.info("Calling regular Hello World which will finish quickly")
        asap_hello = test_procedures.example_procedures.hello_world.HelloWorld(self.sut, self.suite_config)
        asap_hello.run(node=n1)
        
        # maybe we want to fire off another delayed hello on the remote node
        delayed_hello2 = test_procedures.example_procedures.hello_world.DelayedHelloWorld(self.sut, self.suite_config)
        
        # and pass the test case data to it
        # this data is specified in the suite file via dat file, case_args, or override vars
        delayed_hello2.run_asynch(node=n1, **self.args)
        self.log.info("Delayed_hello2 is off and running with data %s" % self.args)
        
        
        # Lets wait for the first delayed to finish
        my_pro = delayed_hello.wait(timeout=30)
        self.log.info("Delayed Hello returned %s"%my_pro)
        
        my_pro2 = delayed_hello2.wait(timeout=30)
        self.log.info("Delayed Hello 2 returned %s"%my_pro)
        
        
    
    def post_execute(self):
        pass