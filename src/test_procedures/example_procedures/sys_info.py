import ae
from test_procedures import TestProcedure
import psutil
from time import sleep

class MemoryLogger(TestProcedure.TestProcedure):
    """
     Quick little procedure to sit and log the memory usage
     every 5 seconds.
    """
    def action(self):
        while True:
            (total, used, free,percent) = psutil.phymem_usage()
            self.log.info("Memory info:\nTotal:%s\nUsed:%s\nFree:%s\nPercent:%s\n\n"%(total,used,free,percent))
            sleep(5)
        
    def checkpoint(self):
        pass
    
