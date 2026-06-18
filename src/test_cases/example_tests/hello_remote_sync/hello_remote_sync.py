import test_procedures
from test_cases import TestCase
from ae import ae_errors
from lib import string_extensions

class hello_remote_sync(TestCase.TestCase):
    """
     A quick test that executes the simple HelloWorld procedure 
     synchronously on each node in the SUT
    """
        
    def pre_execute(self):
        pass     
    

    def main_execute(self):      
        
        
        hello = test_procedures.example_procedures.hello_world.WhoAmI(self.sut, self.suite_config)
        hello2 = test_procedures.example_procedures.hello_world.WhoAmI(self.sut, self.suite_config)
        hello3 = test_procedures.example_procedures.hello_world.WhoAmI(self.sut, self.suite_config)
        
        for n in self.sut.nodes:
            hostname = n.get_hostname_only()
            my_pro = hello.run(node=n)
            if hostname == string_extensions.get_host_only(my_pro.shell_stdout.rstrip("\r\n")):
                self.log.info("Pro looks good!")
            else:
                raise ae_errors.TestCaseFail(message="Pro stdout is incorrect:[%s]\nexpected:[%s] "%(my_pro.shell_stdout, hostname))
            if hello.is_running() == True:
                raise ae_errors.TestCaseFail(message="Should not still be running!")
            my_pro = hello2.run(node=n)
            if hostname == string_extensions.get_host_only(my_pro.shell_stdout.rstrip("\r\n")):
                self.log.info("Pro looks good!")
            else:
                raise ae_errors.TestCaseFail(message="Pro stdout is incorrect:[%s]\nexpected:[%s] "%(my_pro.shell_stdout, hostname))
            if hello2.is_running() == True:
                raise ae_errors.TestCaseFail(message="Should not still be running!")
            my_pro = hello3.run(node=n)
            if hostname == string_extensions.get_host_only(my_pro.shell_stdout.rstrip("\r\n")):
                self.log.info("Pro looks good!")
            else:
                raise ae_errors.TestCaseFail(message="Pro stdout is incorrect:[%s]\nexpected:[%s] "%(my_pro.shell_stdout, hostname))
            if hello3.is_running() == True:
                raise ae_errors.TestCaseFail(message="Should not still be running!")

            
    def post_execute(self):
        pass