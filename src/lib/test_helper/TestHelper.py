import sys
import os
import abc

from ae import ae_logger

class TestHelper(object):
    """ Abstract base class for helper classes
    
    TestHelper enables the creation of objects that are not TestProcedures
    but that can still access the sut, suite_config, and logger.
    
    """
    __metaclass__ = abc.ABCMeta

    def __init__(self, sut, suite_config):
        """ 
        """
        self.sut = sut                      # the environment (SUT) object
        self.suite_config = suite_config    # suite config object
        self.log = None                     # our local/remote log

        self._setup_log()

    def _setup_log(self):
        """ Initialize an AE2 logger for the object
        """
        force = False

        debug_flag = False
        if sys.flags.debug:
            debug_flag = True

        name = '%s%s' % (self.__class__.__name__,os.getpid())

        self.log = ae_logger.Log(self.sut.log_server,
                                 self.sut.log_port,
                                 name,
                                 debug_flag=debug_flag,
                                 force=force)

