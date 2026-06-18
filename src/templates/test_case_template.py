'''
Created on Jan 29, 2013

@author: jd
'''
import test_procedures
from test_cases import TestCase
from ae import ae_errors


class test_case_template(TestCase.TestCase):
    """ 
    Description: 
        Brief description of the test case.  
    
    Test Case Summary: 
        Set up a one-node cluster with one cache device and one mapped volume. 
        Start I/O and concurrently send two identical snapshot prepare calls. 
        The second 'stacked' snapshot prepare returns an error that is caught by the test. 

    Prerequisites: 
        The product is installed. 
        There is 1 cache device available.
        There is 1 volume available. 

    Documents: 
      Documents that help give context to this test case. 
      Below are some examples by no means comprehensive that may/may not apply in you specific case.
      The tags 'clearspace' and 'jira' indicate links to documents in those repositories. 
      
        Test plan: 
            Test plan title that originates this test case (if any) with link. 
              :clearspace:`DOC-###` 
    
        Implements: 
            Name of the test(s) the test case implements. This could be out of the test plan or Test Rail. 
                - Test Case 1: 
                    :clearspace:`DOC-###`
                - Test Case 2: 
                    :clearspace:`DOC-###`
        
        User story: 
            Name of the user story the test case is testing (if any) and link. 
              :jira:`AUTO-###`
        
        Task: 
            Name of the task the test case is testing (if any) and link. 
            :jira:`AUTO-###`
        
        Other: 
            Other relevant document(s) and links.
            :clearspace:`DOC-###` 

    """

    def pre_execute(self):
        """Brief overview of the pre_execute actions. Typically, setup actions. 
        
        """
        pass


    def main_execute(self):
        """Brief overview of the main actions. Test case execution normally goes here. 
        
        """
        return
        


    def post_execute(self):
        """Brief overiview of post execute actions. Typically, validation is done here. 
        
        """
        pass

    
