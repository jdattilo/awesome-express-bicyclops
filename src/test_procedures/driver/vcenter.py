"""
 A  collection of test procedures that interact with vCenter
 to manipulate ESXi hosts and guest VM's. Some of the procedures
 are generic - that is to say there is nothing specific about them
 that involves FLDC/VSA. And some procedures are very tailored to 
 to our FLDC and/or how the VSA is expected to be configured. 
"""
import sys
import test_procedures
from lib import network, string_extensions, pathing
from ae import vimer, ae_errors, environment
from test_procedures import TestProcedure
from time import sleep
from ae import prepper, pyro_driver
from ae.vimer import VmTool
from ae.ae_errors import TestProcedureError
from pysphere.resources import vi_exception




VM_NETWORK = "VM Network"
DEFAULT_NETMASK ="255.255.255.0"
DEFAULT_NUM_ISCSI = 1
DEFAULT_NUM_ISER = 1
EXPECTED_VSA_NICS = 3


class AutoSetupVsa(TestProcedure.TestProcedure):
    """
    High-level procedfure that handles the deploy and setup of 
    VSA machines. The workflow is that the VM's are deployed,
    the network configuration performed on both the VM and ESX host, 
    necessary AE2 software is installed, and if the iSCSI setup (if needed)
    is performed.
    
    There is an optional redeploy flag that will delete any pre-existing VSA's
    otherwise the current VSA's are checked to see if they meet the requirments
    and can be reused. 
     
    :param ova_url: Location of the OVA package for the VSA
    :param vsas: List of the nodes to setup. If none, all VSA's in sut are used.
    :param redeploy: If True, will delete any existing VSA's regardless of state.
    :param skip_cluster_setup: optional, if not set will create a cluster
    
    """
    def action(self):
        
        redeploy=self.args.get('redeploy', False)
        skip_cluster_setup=self.args.get('skip_cluster_setup', False)
        ova_url = self.args.get("ova_url", None)
        if not ova_url:
            raise ae_errors.TestProcedureError(message="Missing parameter: ova_url")
            
        vsas = self.args.get("vsas", None)
        if not vsas:
            vsas = self.sut.get_vsa_nodes()
        else:
            for vsa in vsas:
                if isinstance(vsa,environment.Node) == False or vsa.is_vsa() == False:
                    raise ae_errors.TestProcedureError(message="%s is not a node with VSA role"%vsa)
        self.log.info("CHECK: VSAs to for deploy = %s" % vsas)

        self.log.info("Configuring ESX hosts for passthru and adding iSCSI Software Adapter.")
        for vsa in vsas:
            tp = ConfigureHostPassthruAndIscsi(self.sut, self.suite_config)
            tp.run(host=vsa.esx_host, iscsi_san_ip=vsa.iscsi_san_ip)
        
        if not redeploy:
            self.log.info("Redeploy is false. Checking if VSAs are configured.")
            do_config = False
            for vsa in vsas:
                self.log.info("VSA to check for deploy = %s" % vsa)
                conf_check = IsVsaConfigured(self.sut,self.suite_config)
                if conf_check.run(vsa=vsa).output == False:
                    do_config = True
                    self.log.info("Not all VSA's are configured. Starting redeployment.")
                    redeploy=True
            if do_config == False:
                self.log.info("VSAs appear to be already be configured. Not deploying VSAs..")
        
        if redeploy:
            self.log.info("Deleting VSA's : %s." % vsas)
            rm_vms = test_procedures.driver.vcenter.DeleteVms(self.sut, self.suite_config)
            if vsas:
                rm_vms.run(vms=vsas)
            else:
                rm_vms.run(vms=self.sut.get_vsa_nodes())
            
            sleep(15)
            
            self.log.info("Rescanning the HBAs.")
            rescan = test_procedures.driver.vcenter.RescanHbas(self.sut, self.suite_config)
            rescan.run(timeout=2700)
            
            self.log.info("Removing stale SSH keys")
            hosts = []
            for vsa in vsas:
                hosts.extend([str(vsa.ip),str(vsa),string_extensions.get_host_only(str(vsa))])
            rm = test_procedures.sys_ops.os_util.RemoveKnownHostKeys(self.sut,self.suite_config)
            rm.run(host=hosts)
            
            self.log.info("Beginning VSA deployment...")
            deploy_tp = test_procedures.driver.provisioning.DeployOva(self.sut,self.suite_config)
            deploy_tp.run(vsa_nodes=vsas, ova_url=ova_url, timeout=1800)
            self.log.info("VSA deployment complete.")
            
            tps = []
            for vsa in vsas:
                config_tp = test_procedures.driver.provisioning.PrepareVsaForTest(self.sut,self.suite_config)
                config_tp.run_asynch(vsa_node=vsa)
                tps.append(config_tp)
            for tp in tps:
                tp.wait(timeout=900)
        
        num_iscsi = len(self.sut.get_vsa_nodes()[0].iscsi_ips)
        
        # do the network configuration on the host and guest
        for vsa in vsas:
            cn = ConfigureNetworks(self.sut,self.suite_config)
            cn.run(vsa=vsa, num_iscsi=num_iscsi)
        
        # Deploys AE2 to the VSAs
        self.log.info("Beginning AE2 deployment to VSAs : %s" % vsas)
        prepper.Prepper.deploy_to_vsa(self.sut, vsas)
        
        # Start AE2 on the VSAs
        self.log.info("Beginning AE2 deployment to VSAs : %s" % vsas)
        for vsa in vsas:
            dep_ae2_tp = test_procedures.driver.provisioning.StartAe2OnVsa(self.sut,self.suite_config)
            dep_ae2_tp.run(vsa=vsa)
        
        # register the VSA with it's specified vcenter (according to the env file)
        # and call the procedure to set the boot configuration for the vsa.
        for vsa in vsas:
            reg_tp = test_procedures.cluster.hrm_config.vsa.RegisterVSA(self.sut, self.suite_config)
            reg_tp.run(node=vsa)
            bc = test_procedures.cluster.hrm_config.vsa.SetVSABootConfig(self.sut, self.suite_config)
            bc.run(node=vsa)

        # if its an iscsi cluster we need to do have the vsa configure the 
        # initiator and logon to the targets. It would be nice to have 
        # ConfigureNetworks do this but we need AE2 running on the nodes first.
        if num_iscsi > 0:
            for vsa in vsas:
                config_iscsi = test_procedures.cluster.hrm_config.vsa.ConfigureIscsiInitiator(self.sut, self.suite_config)
                config_iscsi.run(node=vsa, iscsi_san_ip=vsa.iscsi_san_ip)
                iscsi_on = test_procedures.cluster.control.ChkConfigOn(self.sut, self.suite_config)
                iscsi_on.run(node=vsa,service='iscsi')
                iscsid_on = test_procedures.cluster.control.ChkConfigOn(self.sut, self.suite_config)
                iscsid_on.run(node=vsa,service='iscsid')
                
        # Set the VM boot order so the VSA is #1.
        # would be nice to start leveraging the hermes_menu code...
        
        if not skip_cluster_setup:
            setup_vsa_tp = test_procedures.cluster.hrm_config.setup.AutoSetupCluster(self.sut, self.suite_config)
            setup_vsa_tp.run(as_reset_cluster='hard_all',
                             as_start_if_stopped=True, 
                             as_autoprovisioning='all',
                             **self.args)
        
        
            self.log.info("Issuing a rescan of all HBAs.")
            rescan_hbas = RescanHbas(self.sut, self.suite_config)
            rescan_hbas.run(timeout=2700)
        
            #TODO: Replace all of this with a wait_for_luns procedure
            # 
            # The VIM rscan operation are asynchronous so we have to keep  
            # trying to create the datastore so as to to avoid an issue where 
            # the lun isn't available after caching.
            sleep(60)
            for vd in self.sut.san.vds:
                i = 1
                while True:
                    try:
                        create_ds = CreateDatastore(self.sut, self.suite_config)
                        _pro = create_ds.run(host=vsas[0].esx_host,wwn=vd.wwn, error_on_existing=False)
                        self.log.info("Datastore %s created on %s"%(_pro.output,vd.wwn))
                        break
                    except Exception, ex:
                        self.log.info("Create datastore attempt %s failed."%i)
                        if i == 20:
                            raise ex
                        sleep(10)
        else:
            self.log.info("Skipping cluster setup and datastore create")

        
    def checkpoint(self):
        pass


class ConfigureNetworks(TestProcedure.TestProcedure):
    """
     The top-level tp to do *all* the host-guest network stuff.
     If the redeploy flag is set (by default) all virtual switches
     created by AE2 are removed from the host. New switches are 
     created as needed for the iSCSI and iSER networks and the
     VSA guest configuration performed. This sets the NIC network
     labels for the VM's and configures the ethernet scripts on
     the VM.
     
     :param vsa: The VSA node we are configuring.
     :param reconfig: If set to True, will remove all non-mgmt vSwitches and recreate them.
     :param num_iscsi: The number of expected iScsi switches 
     :param num_iser: The number of expected iSER switches
     
    """

    def action(self):
        
        vsa = self.args.get("vsa", None)
        num_iscsi = self.args.get("num_iscsi", DEFAULT_NUM_ISCSI)
        num_iser = self.args.get("num_iser", None)
        reconfig = self.args.get("reconfig", True)

        if not vsa:
            raise ae_errors.TestProcedureError(message="Missing parameter: vsa")
        
        host = vsa.esx_host
        
        vm = VmTool(vsa.vm_name,
                    sut=self.sut,
                    server=self.sut.vsphere_server)
        
        # find the VSA NICs and sanity check
        nics = vm.get_nics()
        if len(nics) != EXPECTED_VSA_NICS:
            raise TypeError("Unexpected number of NICs on VSA.")
        
        if reconfig:
            self.log.info("Reconfiguration flag is set. Removing all AE2-created switches.")
            #Set all the NICS to the mgmt network
            vm.reset_network_labels()
            
            rm_tp = RemoveAllSwitches(self.sut, self.suite_config)
            rm_tp.run(host=host)
        
        
        # TODO: Handle non-reconfig deployments or is okay to always reconfig
        #       when deploying out a VSA?
        
        # Make sure the first adapter is set to the Mgmt group
        self.log.debug("Setting adapter %s to %s"%(nics[0].DeviceInfo.Label,VM_NETWORK)) 
        vm.set_network(VM_NETWORK, nics[0].DeviceInfo.Label)
        
        # If the iscsi_ips list in the env file, this is a noop.
        if num_iscsi > 0:
            for i in range(num_iscsi):
                
                if len(vsa.iscsi_ips) < num_iscsi:
                    _msg="The VSA requires %s ISCSI_IPs in the environment file."%num_iscsi
                    raise ae_errors.TestProcedureError(message=_msg)
                
                host_ip = vm.get_esx_ip()
                self.log.debug("Host IP is %s"%host_ip)
                _net = vsa.iscsi_ips[i].split(":")[0]
                _ip = string_extensions.edit_ip(_net,3,host_ip.split('.')[3])
                _mask = vsa.iscsi_ips[i].split(":")[1]
                
                
                h = vimer.HostTool(host,
                                   sut=self.sut,
                                   server=self.sut.vsphere_server,
                                   username=self.sut.vsphere_username,
                                   password=self.sut.vsphere_password)
                switches = h.get_vswitches()
                
                # check to see if a iscsi switch in the specified iscsi subnet already exists
                created_switch = None
                for s in switches:
                    if network.is_ip_in_network(s.vmkernel_ip,_net,_mask):
                        _msg = "A switch with IP %s exists in the cache network %s."%(s.vmkernel_ip,vsa.iscsi_ips[i])
                        self.log.debug(_msg)
                        created_switch = s
                        break
                if not created_switch:
                    create_tp = CreateVswitch(self.sut, self.suite_config)
                    created_switch = create_tp.run(host=host, vmkernel_ip=_ip, vmkernel_mask=_mask).output
                self.log.info("Created switch: %s"%created_switch)
                
                # Now we need to set the the VSA network adapter(s) to the new vSwitch            
                if num_iscsi == 1:
                    # we add the second and third VSA network adapters to the switch
                    for j in range(1,3):
                        dev = nics[j].DeviceInfo.Label
                        self.log.debug("Setting adapter %s to %s"%(dev,created_switch.vmpg[0]))
                        vm.set_network(created_switch.vmpg[0], dev)
                else:
                    # we add the 1+N VSA network adapter to the switch we just created
                    dev = nics[i+1].DeviceInfo.Label
                    self.log.debug("Setting adapter %s to %s"%(dev,created_switch.vmpg[0]))
                    vm.set_network(created_switch.vmpg[0], dev)
                
            # Need to login to the vsa and configure the iscsi nics
            # The nics should have the IP of the switch with the VSA's
            # fourth public IP octet
            vm.power_on()
            ip = created_switch.vmkernel_ip
            ip = string_extensions.edit_ip(ip, 3, vsa.ip.split('.')[3])
            mask = created_switch.vmkernel_mask
            nic = "eth%s"%str(i+1)
            self.log.info("Configuring NIC %s with %s:%s"%(nic,ip,mask))
            vm.enable_netif(nic, ip, mask)
        
        # create the iSER vswitches
        create_iser = test_procedures.driver.vcenter.CreateIserVswitches(self.sut,self.suite_config)
        create_iser.run(vsa=vsa, num_iser=num_iser)
 
    
    def checkpoint(self):
        pass
    

class CreateVswitch(TestProcedure.TestProcedure):
    """
     Creates a vSwitch. 
     
     Suggested use is to only provide the host parameter. 
     If no optional parameters are specified, the host
     information will be queried dynamically and new vSwitch data
     provided based on the ESX host's Management Network 
     switch and information from the env file.
     The new vSwtich will have a virtual NIC created 
     (from an available physical NIC) and assigned to it's kernel
     portgroup that is one octet from the management switch. 
     The vSwitch name and portgroup labels will be prefixed 
     and contain the physical NIC's friendly name.
     
     For example if the ESX host has vSwitch for the Management Network
     with an network of 172.18.1.150 bound to vmnic0 and the env file
     specifies 172.19.0.0, the new switch is assigned 172.19.0.150 
     on vmnic1 (or the first available NIC) and will have the switch
     name AE2_VS_vmnic1.
     
     If no physical NIC is available, an error will be raised.   
     
     REQUIRED PARAMETERS
     :param host: The ESX host where we will create the vSwitch
     
     OPTIONAL PARAMETERS
     :param label: The network label for the switch (aka port group label)       
     :param vmkernel_ip: The IP address for the SR-IOV virtual NIC. 
     :param vmkernel_mask: Network mask for the SR-IOV virtual NIC.
     :param nic: Physical NIC we will use (will use first unassigned NIC)
     :param name: The vSwitch name (will default to AE2_VS_$NIC)
     :param skip_vmpg: Skip creation of the VM Portgroup
    
    """
    
    def action(self):
        host = self.args.get("host", None)
        label = self.args.get("label", None)
        vmkernel_ip = self.args.get("vmkernel_ip", None)
        vmkernel_mask = self.args.get("vmkernel_mask", DEFAULT_NETMASK)
        nic = self.args.get("nic", None)
        name = self.args.get("name", None)
        skip_vmpg = self.args.get("skip_vmpg", False)
        
        
        if not host:
            raise ae_errors.TestProcedureError(message="Missing parameter: host")
        
        h = vimer.HostTool(host,
                           sut=self.sut,
                           server=self.sut.vsphere_server,
                           username=self.sut.vsphere_username,
                           password=self.sut.vsphere_password)
        switches = h.get_vswitches()
        self.log.debug("We found %s switches"% len(switches))
        
        
        for s in switches:
            self.log.debug("Switch:\n%s"%s)
        
        # if no vmkernel IP specified, so we'll transpose the host 
        # mgmt network we find the mgmt networks second octect and 
        # add to it by the number of switches. So if the mgmt switch 
        # is 172.18.1.150, the next switch is 172.19.1.150
        mgmt_switch = None
        if not vmkernel_ip:
            for switch in switches:
                if switch.MGMT_NETWORK in switch.vmkg:
                    mgmt_switch = switch
                    self.log.debug("Management Switch:%s"%mgmt_switch)
                    break
            if not mgmt_switch:
                _msg = "Failed to find the Management Network switch."
                raise ae_errors.TestProcedureError(message=_msg)

            mgmt_ip = mgmt_switch.vmkernel_ip
            _inc = int(mgmt_ip.split(".")[1]) + len(switches)
            vmkernel_ip = string_extensions.edit_ip(mgmt_ip, 1, _inc)
            self.log.debug("New switch kernel port IP: %s"%vmkernel_ip)
        
        # if no NIC is specified, we'll find an unused, non-mellanox
        # physical NIC to use for the virtual nic.
        
        if not nic:
            avaliable_nics = h.find_unassigned_nics()
            if len(avaliable_nics) == 0:
                _msg = "Failed to find any unassigned NICs available."
                raise ae_errors.TestProcedureError(message=_msg)
            
            nic = avaliable_nics[0].friendly_name
        
        self.log.debug("Creating new vSwitch on %s with %s:%s"%(nic,vmkernel_ip,vmkernel_mask))
        sw = h.add_vswitch(nic, 
                           vswitch_name=name,
                           group_name=label,
                           vmkernel_ip=vmkernel_ip,
                           vmkernel_mask=vmkernel_mask,
                           skip_vmpg=skip_vmpg)
        
        return sw

        
    def checkpoint(self):
        pass


class CreateIserVswitches(TestProcedure.TestProcedure):
    """
      Creates virtual switches to be used for iSER. The
      number of switches created depends on the num_iser
      value (defaults to DEFAULT_NUM_ISER).
      
      This also configures the VSA NICs to use the cache network.
     
     :param vsa: The VSA node. (We automatically look up it's ESX host).
     :param ip: Optional (defaults to the cache IP in sut)
     :param mask: Optional (defaults to the mask in sut)
     :param num_iser: The number of switches to create. 
    """
    
    def action(self):
        vsa = self.args.get("vsa", None)
        ip = self.args.get("ip", None)
        mask = self.args.get("mask", None)
        num_iser = self.args.get("num_iser", None)
        
        if not vsa:
            raise ae_errors.TestProcedureError(message="Missing parameter: vsa")
        
        host = vsa.esx_host
        h = vimer.HostTool(host,
                           sut=self.sut,
                           server=self.sut.vsphere_server,
                           username=self.sut.vsphere_username,
                           password=self.sut.vsphere_password)
        
        vm = VmTool(vsa.vm_name,
                    sut=self.sut,
                    server=self.sut.vsphere_server)
        host_ip = vm.get_esx_ip()
        
        # If not specified, we'll use the number of cache networks 
        # specified in the sut.
        if not num_iser:
            num_iser = len(vsa.cache_ips)
        
        # Find the mellanox cards and sanity check
        mellanox_devs = h.find_unassigned_nics(find_mellanox=True)
        if len(mellanox_devs) == 0:
            raise ae_errors.TestProcedureError(message="No Mellanox cards available.")
        if len(mellanox_devs) < num_iser:
            _msg = "Not enough Mellanox cards. Found %s but expected %s"%(len(mellanox_devs),num_iser)
            raise ae_errors.TestProcedureError(message=_msg)
        
        cache_nics_configured = False
        i = 0
        param_ip = ip           
        for i in range(num_iser):
            if not param_ip:
                #If not specified, use the cache IP from the env file
                # and the final octect of the host IP
                cip = vsa.cache_ips[i].split(':')[0]
                ip = string_extensions.edit_ip(cip,3,host_ip.split('.')[3])                                           
            if not mask:
                mask = vsa.cache_ips[i].split(':')[1]

            nic = mellanox_devs[i].friendly_name
            label = "%s%s"%(vimer.VMKG_PREFIX, nic)
            
            create_tp = CreateVswitch(self.sut,self.suite_config)
            vswitch = create_tp.run(host=host,
                                   nic=nic,
                                   label=label,
                                   vmkernel_ip=ip,
                                   vmkernel_mask=mask,
                                   skip_vmpg=True).output
            
            device = None
            switches = h.get_vswitches()
            for _switch in switches:
                if _switch.name == vswitch.name:
                    device = _switch.device[0]
                    break
            self.log.debug("Device for iser switch %s"%device)
            
            #Login to the VSA and configure the cachenet nics
            cip = vsa.cache_ips[i].split(':')[0]
            ip = string_extensions.edit_ip(cip, 3, vsa.ip.split('.')[3])
            mask = vsa.cache_ips[i].split(':')[1]
            
            if cache_nics_configured == False:
                vm.enable_cache_netif(ip, mask, num_iser)
                cache_nics_configured = True
            
            iser_hbas = h.get_iser_hba_names()
            for hba_name, vnic in iser_hbas:
                if vnic == nic:
                    self.log.info("Binding %s to %s(%s)"%(hba_name,vnic,device))
                    h.bind_vnic(hba_name, device)
                    break
            i+=1
                
    def checkpoint(self):
        pass


class RemoveAllSwitches(TestProcedure.TestProcedure):
    """
     Removes all vSwitches on the ESX host except for the 
     default Management switch. This will also remove any
     virtual NIC's assigned to the switch. 
     
     This assumes that all guest network adapters are not 
     set to the switche's VM portgroup. If there are guests
     still bound to the VM portgroup, an "In use" error will
     be raised.
     
     An error is raised (whatever vimer encountered) if a 
     switch cannot be deleted.
    """
    
    def action(self):
        
        host = self.args.get("host", None)
        if not host:
            raise ae_errors.TestProcedureError(message="Missing parameter: host")
        
        h = vimer.HostTool(host,
                           sut=self.sut,
                           server=self.sut.vsphere_server,
                           username=self.sut.vsphere_username,
                           password=self.sut.vsphere_password)
        switches = h.get_vswitches()
        
        self.log.info("Unbinding any iSCSI vNICs from Mellanox HBAs.")
        h.unbind_iser_hbas()
        
        # Only remove switches with the AE2 prefix so as to avoid
        # wrongly removing the MGMT switch or iscsiBoot switches
        for switch in switches:
            if vimer.VSWITCH_PREFIX in switch.name:
                # Need to remove any kernel portgroups prior to removing the switch
                if switch.device and len(switch.device):
                    for dev in switch.device:
                        self.log.debug("Removing vNIC: %s"%dev)
                        h.remove_vnic(dev)
                
                self.log.debug("Removing vSwitch: %s"%switch.name)
                h.remove_vswitch(switch.name)
            else:
                self.log.debug("Not removing switch %s"%switch.name)
    
    
    def checkpoint(self):
        pass


class DoesVmExist(TestProcedure.TestProcedure):
    """ 
     Checks to see if the VM exists in the vspshere
     environment specified by the environment file.
    """
    ERROR_MSG = "Could not find a VM named"
    
    def action(self):
        vm_name = self.args.get("vm_name")
        if not vm_name:
            raise TestProcedureError(message="Missing parameter: vm_name")
        
        try:
            t = VmTool(vm_name,sut=self.sut)
            t._get_vm()
            self.log.debug("VM exists with name %s"% vm_name)
            return True
        except vi_exception.VIException, ex:
            if self.ERROR_MSG in ex.message:
                self.log.debug("Did not find a VM with name %s"%vm_name)
                return False
            else:
                self.log.debug("Unexpected error while querying for VM.")
                raise ex


    def checkpoint(self):
        pass


class PowerOnVms(TestProcedure.TestProcedure):
    """
     Turns on the power to a list of Virtual Machines.
     This iterates thru the list powering on the machines
     and waits (by default) for them be available.
     
     :param vms: A list of nodes (VSAs) or strings (virtual 
                 machine name) that we want to power up.
     :param wait: If True, waits for the vm's VmWare Tools
                  to start and the client service module to start.
    
    """
    
    def action(self):
        
        vms = self.args.get("vms", None)
        wait = self.args.get("wait", True)
        
        if not vms:
            self.log.warning("No VM's specified to power on.")
            return
        if type(vms) != list:
            vms = [vms]
        
        for vm in vms:
            if type(vm) == str:
                t = VmTool(vm,sut=self.sut)                
            elif isinstance(vm, environment.Node):
                t = VmTool(vm.vm_name,sut=self.sut)
            else:
                raise TestProcedureError(message="Unsupported vm parameter type:%s"%type(vm))
            self.log.info("Powering on %s"%t.vm_name)
            t.power_on(wait)
            if wait:
                t.wait_for_shell()
            del t
    
    def checkpoint(self):
        pass
    
    
class PowerOffVms(TestProcedure.TestProcedure):
    """
     Turns off the power to a list of Virtual Machines. Note
     that this is a synchronous opertation that waits for the
     machine power state to be off. Historically its been pretty
     reliable (unlike power on).
     
     :param vms: A list of nodes (VSAs) or strings (virtual 
                 machine name) that we want to power up.
    """
    
    def action(self):
        
        vms = self.args.get("vms", None)
        
        if not vms:
            self.log.warning("No VM's specified to power off.")
            return
        if type(vms) != list:
            vms = [vms]
        
        for vm in vms:
            if type(vm) == str:
                t = VmTool(vm,sut=self.sut)                
            elif isinstance(vm, environment.Node):
                t = VmTool(vm.vm_name,sut=self.sut)
            else:
                raise TestProcedureError(message="Unsupported vm parameter type:%s"%type(vm))
            self.log.info("Powering off %s"%t.vm_name)
            t.power_off()
            del t
    
    def checkpoint(self):
        pass


class DeleteVms(TestProcedure.TestProcedure):
    """
     Deletes a list of Virtual Machines. If the VM is not 
     found, no error is raised.
     
     :param vms: A list of nodes (VSAs) or strings (virtual 
                 machine name) that we want to power up.
    """
    
    def action(self):
        
        vms = self.args.get("vms", None)
        
        if not vms:
            self.log.warning("No VM's specified to power on.")
            return
        if type(vms) != list:
            vms = [vms]
        
        for vm in vms:
            name = None
            if type(vm) == str:
                name = vm                
            elif isinstance(vm, environment.Node):
                name = vm.vm_name 
            else:
                raise TestProcedureError(message="Unsupported vm parameter type:%s"%type(vm))
            
            t = None
            try:
                t = VmTool(name,sut=self.sut)
                t.delete()
                self.log.info("VM was deleted: %s"%name)
            except vi_exception.VIException, ex:
                if ex.fault == vi_exception.FaultTypes.OBJECT_NOT_FOUND:
                    self.log.debug("VM not found %s"%name)
                    continue
            
    
    def checkpoint(self):
        pass
    

class RescanHbas(TestProcedure.TestProcedure):
    """
     Rescans all HBA's on (one or more) ESX host.
     
     :param vsa: OptionalVSA we are interested in (not the ESX host). If nothing
                 is specified, all ESX hosts will be rescanned.
    """
    def action(self):
        
        vsa = self.args.get("vsa")
        hosts=[]
        if not vsa:
            hosts = self.sut.get_esx_hosts()
        elif isinstance(vsa, environment.Node):
            hosts.append(vsa.esx_host)
        else:
            raise TestProcedureError(message="Unsupported vsa parameter type: %s"%type(vsa))
        
        for _host in hosts:
            h = vimer.HostTool(_host, sut=self.sut)
            h.rescan_hbas()
            del h
        
    def checkpoint(self):
        pass


class RescanVmfs(TestProcedure.TestProcedure):
    """
     Rescans the ESX host for VMFS changes.
     
     :param vsa: OptionalVSA we are interested in (not the ESX host). If nothing
                 is specified, all ESX hosts will be rescanned.
    """
    def action(self):
        
        vsa = self.args.get("vsa")
        hosts=[]
        if not vsa:
            hosts = self.sut.get_esx_hosts()
        elif isinstance(vsa, environment.Node):
            hosts.append(vsa.esx_host)
        else:
            raise TestProcedureError(message="Unsupported vsa parameter type: %s"%type(vsa))
        
        for _host in hosts:
            h = vimer.HostTool(_host, sut=self.sut)
            h.rescan_vmfs()
            del h
        
    def checkpoint(self):
        pass


class ConfigureHostPassthruAndIscsi(TestProcedure.TestProcedure):
    """
     Configures the ESX host PCI devices to be used by the 
     VSA as passthru devices. If the devices were not configured,
     for passthru, it enables software iSCSI, configures
     the devices such that they have passthru enabled, and the ESX 
     host will automatically reboot. This procedure waits for the
     host to reboot and reconnect to it's managing
     vsphere server.
     
     :param host: The hostname of the ESX host being configured.
    """
    
    def action(self):
        host = self.args.get("host")
        iscsi_san_ip = self.args.get("iscsi_san_ip") 
        if not host:
            raise TestProcedureError(message="Missing parameter: host")
        
        h = vimer.HostTool(host, sut=self.sut)
        
        if iscsi_san_ip:
            h.configure_vsa_passthru(fc_passthru=False)
            h.enable_iscsi()
            h.add_target_to_iscsi_swadapter(iscsi_san_ip)
        else:
            h.configure_vsa_passthru(fc_passthru=True)
        
    def checkpoint(self):
        pass
    

class RebootHost(TestProcedure.TestProcedure):
    """
     Reboots the ESX host and waits for it to be available.
     
     :param host: The ESX host to reboot
    """
    
    def action(self):
        host = self.args.get("host")
        if not host:
            raise TestProcedureError(message="Missing parameter: host")
        h = vimer.HostTool(host, sut=self.sut)
        h.reboot()
        
    def checkpoint(self):
        pass
    

class IsVsaConfigured(TestProcedure.TestProcedure):
    """
     Checks to see if the VSA and host are configured correctly and ready to run FLDC.
     
     Things checked include
         Does the VSA exist on the host
         Is AE2 running on the VSA?
         Do a feasible number of switches exist on the host
         Are the VSA NICs configured
         
     :param vsa: The VSA we want to check
    """
    def action(self):
        vsa = self.args.get("vsa")
        if not vsa:
            raise TestProcedureError(message="Missing parameter:vsa")
        
        h = vimer.HostTool(vsa.esx_host, sut=self.sut)
        if h.is_vm_on_host(vsa.vm_name) == False:
            self.log.debug("VM %s is not on ESX host %s"% (vsa.vm_name, vsa.esx_host))
            return False
            
        #2....
        
        #3....
        return True
        
    def checkpoint(self):
        pass


class CreateDatastore(TestProcedure.TestProcedure):
    """
     Takes a wwn and creates a datastore on it.
     
     :param host: ESX host to create the datastore.
     :param wwn: WWN of the LUN to create the datastore.
     :param datastore_name: Optional name for the datastore (defaults to ae2_ds_[wwn]) 
    """
    
    def action(self):
        host = self.args.get("host",None)
        wwn = self.args.get("wwn",None)
        error_on_existing = self.args.get("error_on_existing",True)
        if not host:
            raise ae_errors.TestProcedureError("Missing parameter: host")
        if not wwn:
            raise ae_errors.TestProcedureError("Missing parameter: wwn")
        
        datastore_name = self.args.get("datastore_name",None)
        if not datastore_name:
            datastore_name = "ae2_ds_%s"%wwn
        h = vimer.HostTool(host,
                           sut=self.sut,
                           server=self.sut.vsphere_server,
                           username=self.sut.vsphere_username,
                           password=self.sut.vsphere_password)
        h.create_datastore(datastore_name, lun_wwn=wwn, error_on_existing=error_on_existing)
        
        return datastore_name
        
        
    def checkpoint(self):
        pass


class AddVirtualDiskToNode(TestProcedure.TestProcedure):
    """
      Adds a virtual disk to a given VM node
     
     :param vm: VM node to add the virtual disk.
     :param datastore: Name of datastore where disk will reside
     :param size: Size of disk in MBs)
     :param thin_provisiong: True or False on whether the disk is thin provisioned.
    """
    
    def action(self):
        vm = self.args.get("vm",None)
        datastore = self.args.get("datastore",None)
        size = self.args.get("size",None)
        thin_provisiong = self.args.get("thin_provisiong",True)
        if not vm:
            raise ae_errors.TestProcedureError("Missing parameter: vm")
        if not datastore:
            raise ae_errors.TestProcedureError("Missing parameter: datastore")
        if not size:
            raise ae_errors.TestProcedureError("Missing parameter: size")
        
        v = vimer.VmTool(vm.vm_name,
                         sut=self.sut,
                         server=self.sut.vsphere_server,
                         username=self.sut.vsphere_username,
                         password=self.sut.vsphere_password)
        v.create_virtual_disk(datastore, size, thin=thin_provisiong)
        
        
    def checkpoint(self):
        pass


class RemoveVirtualDisksFromNode(TestProcedure.TestProcedure):
    """
      Removes all non-system disks from the VM.
     
     :param power_off: If set to True, powers off the VM before removal.
    """
    
    def action(self):
        vm = self.args.get("vm",None)
        power_off = self.args.get("power_off",True) 
        
        if not vm:
            raise ae_errors.TestProcedureError("Missing parameter: vm")
        
        v = vimer.VmTool(vm.vm_name,
                         sut=self.sut,
                         server=self.sut.vsphere_server,
                         username=self.sut.vsphere_username,
                         password=self.sut.vsphere_password)
        if power_off:
            self.log.info("Powering down %s before removing disks."%vm.vm_name)
            v.power_off()
        v.remove_all_virtual_disks()
        self.log.info("All non-system disks have been removed from %s"%vm.vm_name)
        
    def checkpoint(self):
        pass


class DeleteDatastore(TestProcedure.TestProcedure):
    """
     Takes a datastore name deletes it.

     :param host: ESX host to delete data store
     :param datastore_name: datastore name to delete
    """

    def action(self):

        host = self.args.get("host",None)
        datastore_name = self.args.get("datastore_name",None)
        datastore_name = datastore_name
        self.log.info("host=%s  datastore=%s" %(host,datastore_name))

        if not host:
            raise ae_errors.TestProcedureError("Missing parameter: host")
        if not datastore_name:
            raise ae_errors.TestProcedureError("Missing parameter: datastore_name")

        h = vimer.HostTool(host,
                           server=self.sut.vsphere_server,
                           username=self.sut.vsphere_username,
                           password=self.sut.vsphere_password)
        datastore_mor = h.get_datastore_mor(datastore_name)
        self.log.info("datastore mor = %s" %(datastore_mor))

        h.delete_datastore(datastore_mor)

        self.log.info("DELETED:%s" %(datastore_name))

    def checkpoint(self):
        pass

