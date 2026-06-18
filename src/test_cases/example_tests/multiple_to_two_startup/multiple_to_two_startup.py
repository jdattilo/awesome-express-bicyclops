import sys
import os
import lib
import time
import random
import test_procedures
from ae import ae_errors
from datetime import datetime
from test_cases import TestCase


class multiple_to_two_startup(TestCase.TestCase):
        
    def pre_execute(self):
        pass     
    

    def main_execute(self):      


        # Get io_size
        # Need to do some more calculation here for io_size.
        io_size = self.args.get("io_size")

        # Randomly pick IO size.
        io_size = random.choice(io_size)

        # Config cache.
        tp_config = test_procedures.cache.config.config_prep.ConfigCacheDev(self.sut, self.suite_config)
        tp_config.run(**self.args)
        
        # Config Back Device.
        tp_config = test_procedures.cache.config.config_prep.ConfigBackend(self.sut, self.suite_config)
        tp_config.run(**self.args)

        # Get the cache status.
        tp_blk = test_procedures.cache.control.status_cache.status_cache(self.sut, self.suite_config)
        pro = tp_blk.run(node=self.sut.nodes[0], verbose=True)
        status_cache_list = tp_blk.get_status_list(pro.shell_stdout)

        # Get block device list from cache status.
        block_device_list = tp_blk.get_available_blk_device(status_cache_list)

        # Choose a block device to use.
        cache_blk_dev = random.choice(block_device_list)
        if cache_blk_dev in pro.shell_stdout:
            back_dev = pro.shell_stdout.replace("\n", "").split(" ")[-4]

        # Get the lun mode and check if it matches the required lun mode.
        mode = pro.shell_stdout.replace("\n", "").split(" ")[-1]
        if mode == "write_back":
            compare_mode = "wb"
        else:
            compare_mode = "wt"
        # If the lun mode is not the required lun_mode for the test, reconfigure.
        lun_mode = self.args.get("lun_mode")
        if not compare_mode == lun_mode:
            tp_config = test_procedures.cache.config.config_prep.ChangeMode(self.sut, self.suite_config)
            param = {"backend":back_dev, "mode":lun_mode}
            self.args.update(param)
            tp_config.run(**self.args)

        # Check if cache devices and backend exist if not create them.
        tp_ssd = test_procedures.cache.control.list.ListSsd(self.sut, self.suite_config)
        pro = tp_ssd.run(node=self.sut.nodes[0])
        ssd_list = tp_ssd.get_list_ssds(pro.shell_stdout)
        cache_devices = tp_ssd.get_list_pooled_ssds(ssd_list)

        # Randomly pick a cache device to fail.
        fail_dev = random.choice(cache_devices)

        # Device name.
        dev = fail_dev.split("/")[-1]
        
        # Get WWN for device and correspondig slot number
        tp= test_procedures.sys_ops.dev.DevToWwn(self.sut, self.suite_config)
        pro = tp.run(node=self.sut.nodes[0], device=fail_dev)
        wwn_dev = pro.shell_stdout.replace("\n", "")

        # Get Slot number.
        tp_GetSSDSlot = test_procedures.sys_ops.dev.GetSSDSlot(self.sut, self.suite_config)
        pro_tp_GetSSDSlot = tp_GetSSDSlot.run(node=self.sut.nodes[0], ssd=dev)
        fail_slot = pro_tp_GetSSDSlot.shell_stdout.rstrip()

        # FS vs Raw device (To be added)
        filesystem = self.args.get("filesystem")
        if filesystem:
            # Test procedure to prepare filesystem (create, mount, etc. TOBEADDED)
            self.log.info("File system will be used for testing")    
        else:
            self.log.info("Raw device will be used for testing")    
            
        # Set I/O output file.
        out_file = "/tmp/fio" #io_tool
        out_file += ".%s" %(str(datetime.now()).replace(' ',':').replace(':','.')) 

        # Note: For now do I/O that completes. It will change later to I/O that is running continuously"
        # Test procedure to start
        tp_io_create = test_procedures.sys_ops.iogen.sample.CreateFioSample(self.sut, self.suite_config)

        # For now create two sample data start.
        param = {"io_size":io_size, "offset":0, "filename":cache_blk_dev, "output":out_file}
        args = self.args.update(param)
        tp_io_create.run(**self.args)
     
        tp_down = test_procedures.driver.wait_node_up_down.WaitForNodeDown(self.sut, self.suite_config)
        tp_down.run_asynch(test_node=self.sut.nodes[0])
        # Reboot system
        tp_reboot = test_procedures.driver.reset_node.Reboot(self.sut, self.suite_config)
        tp_reboot.run(node=self.sut.nodes[0])
        
        # Wait for node to go down
        tp_down.wait(timeout=300)

        # Wait for node to become alive
        tp_recover = test_procedures.driver.wait_node_up_down.WaitForNodeAlive(self.sut, self.suite_config)  
        tp_recover.run(test_node=self.sut.nodes[0], timeout=180)

        # Restart pyro...
        from ae import pyro_driver
        restart = pyro_driver.Pyro(self.sut)
        restart.start_proc_caller_on_node(self.sut.nodes[0])
        time.sleep(5) # To get things settle
    
        # Fail device.
        tp_dev_fail = test_procedures.cache.event.fail_device.PowerDownSsd(self.sut, self.suite_config)
        tp_dev_fail.run(node=self.sut.nodes[0], slot_num=fail_slot)

        # Start the cache 
        tp_start = test_procedures.cluster.control.StartCache(self.sut, self.suite_config)
        tp_start.run(node=self.sut.nodes[0])
        time.sleep(10) # To get things settle

        # Check device failure detection (This will change to test procedure).
        # It looks like we don't have event trigger for missing device (commenting out for now)
        #while True:
        #    try:
        #        tp_event1 = test_procedures.cache.control.rnacmd_helper.EventCheck(self.sut, self.suite_config)
        #        tp_event1.run(node=self.sut.nodes[0], event_id="TBD")
        #        break
        #    except:
        #        time.sleep(60) # To get things settle

        # Check recovery status(this need to change, need to find out what is a reasonable waiting time).
        #while True:
        #    try:
        #        tp_event2 = test_procedures.cache.control.rnacmd_helper.EventCheck(self.sut, self.suite_config)
        #        tp_event2.run(node=self.sut.nodes[0], event_id="TBD")
        #        break
        #    except:
        #        time.sleep(60) # To get things settle

        # Check device is not in cache.
        tp_ssd = test_procedures.cache.control.list.ListSsd(self.sut, self.suite_config)
        pro = tp_ssd.run(node=self.sut.nodes[0])
        ssd_list = tp_ssd.get_list_ssds(pro.shell_stdout)
        cache_devices = tp_ssd.get_list_pooled_ssds(ssd_list)
        if fail_dev in cache_devices:
            raise ae_errors.TestProcedureExecutionError("device %s is still in cache" % fail_dev)

        # THIS NEED TO CHANGE ONCE WE STOP FLUSHING AT SHUTDOWN
        # For now shutdown the cache (Replace with flush dirty data tp here)
        # Since flushing happen at shutdown currently, stop cache to verify 
        # data consistency on the backend storage.
        tp_stop = test_procedures.cluster.control.StopCache(self.sut, self.suite_config)
        tp_stop.run(node=self.sut.nodes[0])
        time.sleep(5) # To get things settle

        # Need to verify product shutdown is done here. 
        
        # Verify the sample data on the backend.
        tp_io_verify = test_procedures.sys_ops.iogen.sample.VerifyFioSample(self.sut, self.suite_config)
        param = {"io_size":io_size, "offset":0, "filename":back_dev, "output":out_file}
        self.args.update(param)
        tp_io_verify.run(**self.args)

        # Start cache
        tp_start = test_procedures.cluster.control.StartCache(self.sut, self.suite_config)
        tp_start.run(node=self.sut.nodes[0])
        time.sleep(10) # To get things settle
    
        # Power up failed device.
        tp_device_add = test_procedures.cache.event.recover_device.PowerUpSsd(self.sut, self.suite_config)
        tp_device_add.run(node=self.sut.nodes[0], slot_num=fail_slot)

        # Get the device name using the WWN (to avoid name slippage issue).
        tp_dev_name= test_procedures.sys_ops.dev.WwnToDev(self.sut, self.suite_config)
        pro = tp_dev_name.run(node=self.sut.nodes[0], wwn=wwn_dev)
        dev_name = pro.shell_stdout.replace("\n", "")

        # Add back to the cache.
        tp_add = test_procedures.cache.control.rnacmd_helper.ReactivateDev(self.sut, self.suite_config)
        tp_add.run(node=self.sut.nodes[0], device=dev_name)
        
        # Check device is back in cache. 
        tp_ssd = test_procedures.cache.control.list.ListSsd(self.sut, self.suite_config)
        pro = tp_ssd.run(node=self.sut.nodes[0])
        ssd_list = tp_ssd.get_list_ssds(pro.shell_stdout)
        cache_devices = tp_ssd.get_list_pooled_ssds(ssd_list)
        if not fail_dev in cache_devices:
            self.log.error("%s is not back in cache" % fail_dev)

        # Create and verify another data.
        offset = int(io_size) * 2
        param = {"io_size":io_size, "offset":offset, "filename":cache_blk_dev, "output":out_file}
        self.args.update(param)
        tp_io_create.run(**self.args)
         

    def post_execute(self):
        pass
