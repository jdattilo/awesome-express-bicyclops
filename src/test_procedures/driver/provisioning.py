"""
 ...
"""
import os
import test_procedures
from lib import string_extensions, constants
from ae import vimer, ae_errors, prepper, pyro_driver
from ae.environment import NODE_ROLES
from test_procedures import TestProcedure
import ntpath
import platform
import posixpath
import shutil
import time
from ae.prepper import Prepper
from test_procedures.driver import vcenter
from ae.ae_errors import TestProcedureError

CLIENT_TEMPLATE = "atlvm050"

class DeployOva(TestProcedure.TestProcedure):
    """ 
     Downloads an OVA package and deploys it out to
     one or more ESX hosts. At the moment this happens
     serially because there may not be much of a performance
     gain to parallelize the file (ova) copy.
     
     :param vsa_nodes: a list of VSA nodes to create (via deployment)
     Optional
     :param ova_url: What ova package to download. Defaults to latest.
     
    """ 
    
    def action(self):
        
        ova_url = self.args.get("ova_url")
        
        if not ova_url:
            raise ae_errors.TestProcedureError(message="No ova_url specified.")
        vsa_nodes = self.args.get('vsa_nodes')
        if not vsa_nodes:
            raise ae_errors.TestProcedureError(message="No vsa_nodes specified.")
        
        o = vimer.OvaTool(self.sut)
        self.log.info('Downloading and unpacking OVA [%s]' % ova_url)
        ova_dir = o.download_ova(ova_url)
        
        #deploy to all VSA nodes in the sut
        for vsa in vsa_nodes:
            if vsa.is_vsa() == False:
                raise ae_errors.TestProcedureError(message="Node %s is not in VSA role."%vsa)
            self.log.info("Deploying OVF to %s"%vsa)
            o.deploy_ovf(vsa.esx_host, vsa.vm_name)
        
        self.log.debug("Removing the downloaded OVA files at %s"%ova_dir)
        shutil.rmtree(ova_dir, ignore_errors=True)
    
    def checkpoint(self):
        pass


class PrepareVsaForTest(TestProcedure.TestProcedure):
    """
     Configures the VSA after its been deployed.
     This is safe to call asynchronously.
      
    :param vsa_node: The VSA node we want to configure
    :param sim_url: HTTP location for the Simulator
    """
    
    def action(self):
        vsa = self.args.get('vsa_node')
        sim_url = self.args.get('sim_url')
        
        if vsa == None:
            raise ae_errors.TestProcedureError(message="No VSA specified.")
        if vsa.is_vsa() == False:
            raise ae_errors.TestProcedureError(message="%s is not a node with VSA role"%vsa)
        
        t = vimer.VmTool(vsa.vm_name,sut=self.sut)
        
        self.log.info("Powering off %s"%vsa)
        t.power_off()
        
        self.log.info("Setting the NICS to the VM Mgmt network on %s"%vsa)
        t.reset_network_labels()
        
        self.log.info("Setting MAC for %s to %s"%(vsa, vsa.mac))
        t.set_mac(vsa.mac)
              
        self.log.info("Adding PCI devices to %s"%vsa)
        
        if vsa.iscsi_san_ip:
            t.add_vsa_pcis(add_fc=False)
        else:
            t.add_vsa_pcis(add_fc=True)
        
        self.log.info("Powering on %s"%vsa) 
        t.power_on()
        
        self.log.info("Waiting for accessible shell on %s"%vsa)
        t.wait_for_shell()
        
        self.log.info("Installing post-deploy packages...")
        t.run_shell("yum -qy install make")
        t.run_shell("yum -qy install zlib-devel")
        
        #We're now using an updated openssl and openssl-devel packages from a different local repo 
        t.run_shell("wget -q -O /etc/yum.repos.d/CENTOS64-updates.repo http://titan.rnanetworks.com/ks/CENTOS64-updates.repo")
        t.run_shell("yum -qy clean all")
        t.run_shell("yum -qy update openssl")
        t.run_shell("yum -qy install openssl-devel")
        
        t.run_shell("yum -qy install python-devel")
        t.run_shell("yum -qy install libaio-devel")
        t.run_build_tools()
        t.run_shell("yum -qy install libxml2-devel")
        t.run_shell("yum -qy install libxslt-devel")
        t.run_shell("yum -qy install unzip")
        t.run_shell("yum -qy install rsync")            # Wont need rsync once zip method is done
        t.run_shell("yum -qy install ntpdate")
        

    def checkpoint(self):
        pass


class StartAe2OnVsa(TestProcedure.TestProcedure):
    """
     Starts AE2 on the VSA using the vimer rather than
     SSH for remote execution.
    """
    
    def action(self):

        vsa = self.args.get('vsa')
        if not vsa:
            raise ae_errors.TestProcedureError(message="Missing parameter: vsa")
                
        t = vimer.VmTool(vsa.vm_name,sut=self.sut)
        _python = constants.PYTHON27_LINUX 
        pyro_sut = "%s/ae/pyro_sut.py" % self.sut.ae_base_linux.rstrip('/')
        cmd = "%s %s -n %s -p %s"%(_python, pyro_sut,self.sut.pyro_ns_name,self.sut.pyro_ns_port)
        t.start_shell(cmd)
        
        self.log.debug("Checking that AE2 is running on %s..."%vsa)
        pyro_driver.Pyro.wait_for_node_up(self.sut, vsa, 2)
        self.log.debug("AE2 is running on %s."%vsa)

    def checkpoint(self):
        pass



class DeployAe2(TestProcedure.TestProcedure):
    """
     Deploys and starts AE2 on the remote node. 
     :param nodes: a node or list of nodes to deploy to
    """
    def action(self):
        
        nodes = self.args.get('nodes')
        if not nodes:
            raise ae_errors.TestProcedureError(message="No nodes specified.")
        
        if isinstance(nodes,list) == False:
            nodes = [nodes]
            
        self.log.info('Deploying AE2 to %s' % nodes)
            
        prepper.Prepper.deploy_ae_files(self.sut,nodes)
        prepper.Prepper.remote_setup(self.sut,nodes)
        prepper.Prepper.timesync(self.sut,nodes)

        # start pyro on our new VSA's
        p = pyro_driver.Pyro(self.sut)
        for _node in nodes:
            p.start_proc_caller_on_node(_node)
            time.sleep(1)
        time.sleep(3)
        
    
    def checkpoint(self):
        pass


class SetupClients(TestProcedure.TestProcedure):
    """
     ...doc me
     
     The source virtual machine or template needs to 'clone friendly'
     such that the network configuration information has been removed
     and the cloned VM will pickup the correct config when it powers up.
     
     See http://confluence.rnanetworks.com/display/SQA/AE2+support+of+VMware
     
    """
    
    def action(self):

        clients = self.sut.get_nodes_by_role(NODE_ROLES.CLIENT)
        
        if not clients:
            _msg = "No clients specified in the environment. Something about this "
            _msg+= "test or SUT configuration is likely incorrect."
            self.log.warning(_msg)
            return

        # find which VM clients need to be deployed
        exists = vcenter.DoesVmExist(self.sut, self.suite_config)        
        to_deploy = []
        for _client in clients:
            if exists.run(vm_name=_client.vm_name).output == False:
                to_deploy.append(_client)
                continue
            ht = vimer.HostTool(_client.esx_host, sut=self.sut)
            if ht.is_vm_on_host(_client.vm_name):
                continue
            else:
                # The VM on a different ESX host.
                # Seems a little rude to just delete it, so stop the test.
                _msg = "VM %s exists but on a different host."%_client.vm_name
                raise TestProcedureError(message=_msg)
        
        # deploy the needed clients
        for target_vm in to_deploy:
            ht = vimer.HostTool(target_vm.esx_host, sut=self.sut)
            self.log.debug("Finding DS on %s for %s."%(target_vm.esx_host,target_vm))
            
            # TODO: We're assuming the first found DS is the best/correct choice... :( 
            (ds_mor,name,wwn) = ht.find_local_datastores()[0]
            if not ds_mor:
                raise TestProcedureError(message="No valid datastores on %s"%target_vm.esx_host)
            
            clone_tp = CloneNodeToDatastore(self.sut, self.suite_config)
            clone_tp.run(source_vm=CLIENT_TEMPLATE,target_node=target_vm,ds_mor=ds_mor,start_ae2=False)
        
        # if cloning a single node, we need to wait a few seconds
        if len(to_deploy) == 1:
            time.sleep(15)
        
        power_on = test_procedures.driver.vcenter.PowerOnVms(self.sut,self.suite_config)
        power_on.run(vms=clients)
        
        # deploy ae2 to them and start the pyro service
        dep_tp = DeployAe2(self.sut, self.suite_config)
        dep_tp.run(nodes=clients)
            
        # remove any disk mappings
        for _client in clients:
            self.log.info("Removing virtual disks from %s."%_client)
            rm_disks = test_procedures.driver.vcenter.RemoveVirtualDisksFromNode(self.sut,self.suite_config)
            rm_disks.run(vm=_client)
        
        # We'll add all cached luns to all clients 
        # giving each client and equal partition of the datastore.        
        _host = self.sut.get_vsa_nodes()[0].esx_host
        _clients = self.sut.get_nodes_by_role(NODE_ROLES.CLIENT)
        
        for vd in self.sut.san.vds:
            self.log.info("Creating datastore (if needed) on %s"%vd.wwn)
            ds = test_procedures.driver.vcenter.CreateDatastore(self.sut, self.suite_config)
            ds_name = ds.run(host=_host,wwn=vd.wwn,error_on_existing=False).output
            
            #need to grab a new HostTool so it queries the latest host info
            ht = vimer.HostTool(_host, sut=self.sut)
            ds_size = ht.get_datastore_size(wwn=wwn)
            client_size = ds_size/len(_clients)
            
            for _client in clients:
                self.log.info("Adding part of %s as a virtual disk to %s"%(ds_name,_client.vm_name))
                add_disk = test_procedures.driver.vcenter.AddVirtualDiskToNode(self.sut, self.suite_config)
                add_disk.run(vm=_client, datastore=ds_name, size=client_size)
        
        power_on = test_procedures.driver.vcenter.PowerOnVms(self.sut,self.suite_config)
        power_on.run(vms=clients)
    
    def checkpoint(self):
        pass


class CloneNodeToDatastore(TestProcedure.TestProcedure):
    """
     Clones a VM to given wwn with a datastore or a given
     datastore MOR and optionally deploys and starts AE2 
     on the new client node. 
     
     NOTE The source VM can be on any host however the source VM,
     ESX host and target datastore need to be managed by the same
     vsphere specified in the env file. 
     
     NOTE2 The source VM needs to be setup in way that it's network
     configuration is "clean" such that when it is cloned, the new
     VM consumes the new MAC address and behaves correctly.
    
     See: [link]
     
     :param source_vm: The source VM to be cloned
     :param target_node: the target node generated by the clone.
     :param wwn: The WWN where the target datastore is located.
     :param ds_mor: The datastore MOR of the target datastore
     
    """
    def action(self):
        
        source_vm = self.args.get("source_vm")
        if not source_vm:
            raise ae_errors.TestProcedureError(message="Missing parameter: source_vm")
        target_node = self.args.get("target_node")
        if not target_node:
            raise ae_errors.TestProcedureError(message="Missing parameter: target_node")
        if not target_node.esx_host or not target_node.vm_name:
            _m = "Target node is not valid. Requires esx_host and vm_name."
            raise ae_errors.TestProcedureError(message=_m)
        wwn = self.args.get("wwn")
        ds_mor = self.args.get("ds_mor")
        if not wwn and not ds_mor:
            raise ae_errors.TestProcedureError(message="Require either parameter: wwn or ds_mor")
        
        self.log.info("Cloning target node %s"%target_node)
        h = vimer.HostTool(target_node.esx_host, 
                           server=self.sut.vsphere_server,
                           username=self.sut.vsphere_username,
                           password=self.sut.vsphere_password)
        if wwn:
            datastore = h.find_datastore_by_wwn(wwn)
            if not datastore:
                _m = "Failed to find datastore for device %s" % wwn
                raise ae_errors.TestProcedureError(message=_m)
        else:
            datastore = ds_mor
        self.log.debug("Cloning to datastore with MOR: %s"%datastore)
        
        source_vm = vimer.VmTool(source_vm,sut=self.sut)
        source_vm.clone (target_node.esx_host, datastore, target_node.vm_name)        

        self.log.info("Clone complete. Setting the MAC address for %s" % target_node.vm_name)
        macaddy = vimer.lookup_mac(target_node.get_hostname_only())
        new_vm = vimer.VmTool(target_node.vm_name,
                              sut=self.sut,
                              server=self.sut.vsphere_server,
                              username=self.sut.vsphere_username,
                              password=self.sut.vsphere_password)
        new_vm.set_mac(macaddy)
        
        self.log.info("Powering on %s" % target_node.vm_name)
        new_vm.power_on()     
        
        self.log.info("Waiting for the VM Client Agent to start on %s" % target_node.vm_name)               
        new_vm.wait_for_shell()

        self.log.info("VM clone success for %s" % target_node.vm_name)
    
    
    def checkpoint(self):
        pass
