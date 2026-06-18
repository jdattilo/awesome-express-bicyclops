"""
     Classes that interact with vmware via the VIM
     to do various useful things.... and stuff.
     
     Notes:
      This module has only been tested with a single datastore.
     
"""
import sys
import abc
import time
import threading
import os
import urllib2
import logging
from urlparse import urlparse
import tempfile
from shutil import rmtree
from ae import prepper, ae_logger
from lib import network, string_extensions,constants



from pysphere import MORTypes,VIMor
from pysphere import VIServer, VIProperty
from pysphere.resources import VimService_services as VI
from pysphere.resources.vi_exception import VIException as VimError
from pysphere.vi_virtual_machine import VMPowerState
from pysphere.vi_task import VITask 
from string import lower
from time import sleep


# time to wait during VM start for the VM Tools to be online
VM_TOOLS_TIMEOUT = 300

ISER_PORT = 3260
ISCSI_ADAPTER_MODEL = "iSCSI Software Adapter"

MELLANOX_DRIVER = "Mellanox iSCSI"
MELLANOX_VENDOR_ID = 5555
MELLANOX_DEVICE_IDS = [4099,4100]
MELLANOX_VF_PT_ID = 4100            #Mellanox Virtual Function ID device for passthru
MELLANOX_CARD_COUNT = 2             #Max Number of Mellanox cards (for MOR traversal efficiency)

VM_NETWORK = "VM Network"
VIRTUAL_NIC_NAMES = ["Network adapter 1","Network adapter 2","Network adapter 3"]
VIRTUAL_NIC_TYPES =["VirtualE1000", "VirtualE1000e", "VirtualPCNet32",
                    "VirtualVmxnet","VirtualVmxnet3"]

# Prefix strings for our AE2-created stuff
DATASTORE_PREFIX = "AE2_DS_"
VSWITCH_PREFIX = "AE2_VS_"
PORTGROUP_PREFIX = "AE2_PG_"
VMKG_PREFIX = "VMkernel for ISER FluidCache_Network_"


class PciDevice(object):
    """
     Container class for VMware PCI device information.
    """
    def __init__(self,
                 pci_id=None,
                 device_id=None,
                 device_name=None,
                 vendor_id=None,
                 vendor_name=None,
                 friendly_name=None):
        
        self.pci_id = pci_id                # PCI ID of the device (02:00:0)               
        self.device_id = device_id          # Assigned device in hex
        self.device_name = device_name      # Model of device (Dell PERC H710P Mini)
        self.vendor_id = vendor_id          # vendor ID (1000)
        self.vendor_name = vendor_name      # vendor name (LSI)
        self.friendly_name = friendly_name  # friendly name of device eg vmhba0, vmnic0, etc
        

class VirtualSwitch(object):
    """
     Helper class for working with ESX virtual switch information.
     This might need some more expanding if we're going to use multiple
     virtual nics per switch.
    """

    MGMT_NETWORK = "Management Network"
    VM_NETWORK = "VM Network"
    
    def __init__(self,
                 name,
                 vnic=None,
                 vmpg=[],
                 vmkg=[],
                 vmkernel_ip=None,
                 vmkernel_mask=None,
                 device=None
                 ):
        self.name = name                    # Name of the virtual switch (vSwitch0)
        self.vnic = vnic                    # Virtual NIC bound to switch (vmnic0
        self.vmpg = vmpg                    # List of VM portgroup names ([VM Network])
        self.vmkg = vmkg                    # List of VMkernel port names ([Management Networks])
        self.vmkernel_ip = vmkernel_ip      # IP of the VMkernel port (172.18.3.115)
        self.vmkernel_mask = vmkernel_mask  # Netmask of the VMKernel port (255.255.248.0)
        self.device = device                # List of network device names ([vmk0])
        
    def __str__(self):
        
        return" Name: %s\n Vnic: %s\n VM Portgroup: %s\n VM Kernel: %s\n IP: %s\n Mask: %s\n Device: %s\n"%(
                                                                                self.name,
                                                                                self.vnic,
                                                                                self.vmpg,
                                                                                self.vmkg,
                                                                                self.vmkernel_ip,
                                                                                self.vmkernel_mask,
                                                                                self.device)
        

class VimTool(object):
    """
     Abstract class that encapsulates the connection and cleanup tasks
     with connecting to a VMWare box. 
    """
    __metaclass__ = abc.ABCMeta
    
    def __init__(self,sut=None,server=None,username=None,password=None):
        self.sut = sut           # the SUT
        self.server = server     # IP or hostname of vSphere server
        self.username = username # username for connection
        self.password = password # password for connection
        self._s = None           # Server connection (vSphere / ESX Host / VMGuest)
        self._trace_file = None  # vim client trace-debug log file
        self.log = None
        
                
    def __del__(self):
        try:
            self._s.disconnect()
            self._s = None
        except:
            pass
    
    
    def _set_log(self):
        """
         Sets our logger. If a sut object is passed in,
         we configure AE2 logger client otherwise use a simple logger
        """
        if self.log:
            return
        elif self.sut:
            self.log = ae_logger.Log(self.sut.log_server,self.sut.log_port,'vimer')
        else:
            self.log = logging.getLogger('vimer_')

    
    def _set_trace_file(self):
        """
         Sets the filepath for the vimer trace file.
         This file captures all the SOAP requests/responses to
         the VMWare VIM API. 
        """
        if self._trace_file:
            return
        log_file = "%s%slogs"%(prepper.find_ae_path(),os.path.sep)
        if os.path.exists(log_file) == False:
                os.makedirs(log_file)
        log_file +="%svimer_%s.log"%(os.path.sep,
                                     string_extensions.get_host_only(network.get_local_hostname()))
        self._trace_file = log_file
    

    def _server_connect(self):
        """
         Connects to the vmware box we want to work with.
         This could be vSphere / ESX Host / VMGuest.
        """
        self._set_log()
        if self.username == None:
            self.log.warning("Attempting to use username 'root'.")
            self.username = 'root'
        
        #TODO: acquire the ESX information from the SUT object if the server is not specified
        
        # if we're defaulting to root, use the default lab password
        if self.password == None and (self.username=="root" or self.username=="Administrator"):
            self.log.warning("Attempting to use the lab default password.")
            import base64
            self.password = base64.b64decode(constants.DEFAULT_PASSWORD)
        
        self._set_trace_file()
        s = VIServer()
        self.log.debug("Connection to:%s with %s:%s"%(self.server,self.username,self.password))
        s.connect(self.server,self.username,self.password, trace_file=self._trace_file)
        self._s = s

    
    def get_datastore_mor(self, ds_name):    
        if self._s == None:
            self._server_connect()
        datastore = [k for k,v in self._s.get_datastores().items() if v==ds_name]
        if datastore == None or len(datastore) == 0:
            raise ValueError("Failed to find datastore:%s"%ds_name)            
        return datastore[0]
    
    
    def _find_resource_pool(self, host):
        dcmors = (self._s.get_datacenters()).keys()
        for dcmor in dcmors:
            dcprops = VIProperty(self._s, dcmor)
            hfmor = dcprops.hostFolder._obj
            crmors = self._s._retrieve_properties_traversal(property_names=['name','host'], from_node=hfmor, obj_type='ComputeResource')
            if not crmors:
                continue
            
            hostmor = [k for k,v in self._s.get_hosts().items() if v==host]
            if hostmor:
                hostmor = hostmor[0]
                self.host_mor = hostmor
            
            crmor = None
            for cr in crmors:
                if crmor:
                    break
                for p in cr.PropSet:
                    if p.Name == "host":
                        for h in p.Val.get_element_ManagedObjectReference():
                            if h == hostmor:
                                crmor = cr.Obj
                                break
                        if crmor:
                            break
            if crmor:
                break
        if not crmor:
            raise AttributeError("Failed to find ComputeResource MOR.")        
        crprops = VIProperty(self._s, crmor)
        resource_pool = crprops.resourcePool._obj
        return resource_pool


class OvaTool(VimTool):
    """
     Tool work working with and deploying an OVF.
    """
    def __init__(self,sut=None,server=None,username='Administrator',password=None):
        # Call the VimTool constructor
        if sut:
            super(OvaTool, self).__init__(sut=sut,
                                          server=sut.vsphere_server,
                                          username=sut.vsphere_username,
                                          password=sut.vsphere_password)
        else:
            super(OvaTool, self).__init__(server=server,username=username,password=password)
    
        self._host_mor = None


    def __del__(self):
        try:
            rmtree(self._ova_dir, ignore_errors=True)
            self._s.disconnect()
        except:
            pass


    def _get_ovf_from_ova(self, ova_file):
        """
         Unpacks the ova files and returns the path
         to the OVF file
        """
        import tarfile
        path = string_extensions.get_dir_from_path(ova_file)
        tf = tarfile.TarFile(ova_file)
        tf.extractall(path)
        for _file in os.listdir(path):
            if _file.endswith(".ovf"):
                return os.path.join(path,_file)

    
    def download_ova(self, ova_url):
        """
         Downloads the OVA from an http location and 
         places it in a temporary location for us to
         unpack and set the path to the OVF.
         
         Returns the directory where the OVA is located.
        """
        ### TEMP so we can skip the DL and unpack ###
        #self._ovf_file = "C:\\Users\\chris_powers\\AppData\Local\\Temp\\tmpwvxssn_ova\\Fluid-Cache-Dell_OVF10.ovf"
        #self._ova_dir = "C:\\Users\\chris_powers\\AppData\\Local\\Temp\\tmpwvxssn_ova"
        #return
        #####################################################################################################
        
        self._set_log()
        ova_file = (ova_url.split('/'))[-1]
        
        self._ova_dir = tempfile.mkdtemp("_ova")
        tmp_ova = os.path.join(self._ova_dir,ova_file)
        if tmp_ova[-3].lower() != ".ova":
            tmp_ova+=".ova"
            
        req = urllib2.urlopen(ova_url)
        self.log.debug("Starting OVA download to:%s"%tmp_ova)
        with open(tmp_ova, 'wb') as fp:
            while True:
                chunk = req.read(256 * 10240)
                if not chunk: 
                    break
                fp.write(chunk)
        self.log.debug( "Download complete.")
        self._ovf_file = self._get_ovf_from_ova(tmp_ova)
        self.log.debug("OVF located at:%s"%self._ovf_file)
        
        return self._ova_dir
        

    def _find_network_by_name(self,network_name):
        ret = None
        for dc in  self._s.get_datacenters().keys():
            dc_properties = VIProperty(self._s, dc)
            for nw in dc_properties.network:
                if nw.name == network_name:
                    ret = nw._obj
                    break
            if ret:
                break
        if not ret:
            raise ValueError("Couldn't find network '%s'" % (network_name))
        return ret


    def _find_vmfolder_by_name(self,folder_name='vm'):
        for k,v in self._s._get_managed_objects(MORTypes.Folder).items():
            if v==folder_name:
                return k
        raise ValueError("Couldn't find folder:%s"%folder_name)
  
  
    def _find_vmdks(self):
        ret = []
        for _file in os.listdir(self._ova_dir):
            if _file.endswith(".vmdk"):
                ret.append(os.path.join(self._ova_dir,_file))
        if len(ret) == 0:
            raise("Failed to find vmdk file in:%s"%self._ova_dir)  
        return ret
    
    def _find_datastore(self,host,ds_name=None):
        """
         Finds the datastore MOR. If the datatstore name is specified
         if will attempt to find it by name otherwise it will find and
         return the first datastore MOR it finds on the host.
        """
        if ds_name!=None:
            if VIMor.is_mor(ds_name):
                return ds_name
            datastore = [k for k,v in self._s.get_datastores().items() if v==ds_name]
            if datastore == None or len(datastore) == 0:
                raise ValueError("Failed to find datastore:%s"%ds_name)            
            return datastore[0]
        
        if self.host_mor == None:
            self.host_mor = [k for k,v in self._s.get_hosts().items() if v==host][0]
        for ds_mor, name in self._s.get_datastores().items():
            props = VIProperty(self._s, ds_mor)
            host_mounts = props.host
            for hm in host_mounts:
                if self.host_mor == hm._obj.Key:
                    self.log.debug('Located datastore %s' % name)
                    return ds_mor
        raise ValueError("Failed to find datastore on %s"%host)        
        





    def _create_import_spec(self,
                           resource_pool_mor,
                           datastore_mor,
                           name,
                           host=None,
                           network_mapping=None,
                           ip_allocation_policy="fixedPolicy",
                           ip_protocol="IPv4",
                           disk_provisioning="eagerZeroedThick"
                           ):
        
        # acquire the OVF file descriptor
        fh = open(self._ovf_file, "r")
        ovf_descriptor = fh.read()
        fh.close()
        
        #TODO: The piece for setting network mappings needs fixed.
        #get the network MORs:        
        networks = {}
        if network_mapping:
            for ovf_net_name, vmware_net_name in network_mapping.items():
                self.log.debug("net:%s v:%s"%(ovf_net_name,vmware_net_name))
                networks[ovf_net_name] = self._find_network_by_name(vmware_net_name)
                
    
        ovf_manager = self._s._do_service_content.OvfManager
        request = VI.CreateImportSpecRequestMsg()
        _this =request.new__this(ovf_manager)
        _this.set_attribute_type(ovf_manager.get_attribute_type())
        request.set_element__this(_this)
        request.set_element_ovfDescriptor(ovf_descriptor)
        rp = request.new_resourcePool(resource_pool_mor)
        rp.set_attribute_type(resource_pool_mor.get_attribute_type())
        request.set_element_resourcePool(rp)
        ds = request.new_datastore(datastore_mor)
        ds.set_attribute_type(datastore_mor.get_attribute_type())
        request.set_element_datastore(ds)
        cisp = request.new_cisp()    
        cisp.set_element_entityName(name)
        cisp.set_element_locale("")
        cisp.set_element_deploymentOption("")
        if host:
            h = cisp.new_hostSystem(host)
            h.set_attribute_type(host.get_attribute_type())
            cisp.set_element_hostSystem(h)
            
        if networks:
            networks_map = []
            for ovf_net_name, net_mor in networks.items():
                network_mapping = cisp.new_networkMapping()
                network_mapping.set_element_name(ovf_net_name)
                n_mor = network_mapping.new_network(net_mor)
                n_mor.set_attribute_type(net_mor.get_attribute_type())
                network_mapping.set_element_network(n_mor)
                networks_map.append(network_mapping)
            cisp.set_element_networkMapping(networks_map)
        if ip_allocation_policy:
            cisp.set_element_ipAllocationPolicy(ip_allocation_policy)
        if ip_protocol:
            cisp.set_element_ipProtocol(ip_protocol)
        if disk_provisioning:
            cisp.set_element_diskProvisioning(disk_provisioning)
        
        
        request.set_element_cisp(cisp)
        return self._s._proxy.CreateImportSpec(request)._returnval
    
    def _import_vapp(self, resource_pool, import_spec, host=None, folder=None):
        request = VI.ImportVAppRequestMsg()
        _this =request.new__this(resource_pool)
        _this.set_attribute_type(resource_pool.get_attribute_type())
        request.set_element__this(_this)
        
        request.set_element_spec(import_spec.ImportSpec)
        
        if host:
            h = request.new_host(host)
            h.set_attribute_type(host.get_attribute_type())
            request.set_element_host(host)
        if folder:
            f = request.new_folder(folder)
            f.set_attribute_type(folder.get_attribute_type())
            request.set_element_folder(folder)
        return self._s._proxy.ImportVApp(request).Returnval
    
    
    def deploy_ovf(self, host, vapp_name, datastore=None, networks=None):
        """
         Creates  a VmWare virtual appliance on the target ESX host.
         
         :param host: ESX host where the virtual appliance will be deployed/
         :param vapp_name: Name of the guest Virtual appliance.
         :param datastore: Datastore where the vApp will be created. Defaults to [host - Local Disk]
         :param networks: Network mapping for the guest vApp
         
        **Example**::
        
             o = OvaTool(server='ipaddr', username='username')
             o.download_ova("url")
             o.deploy_ovf("hostname", "password")
         
        """
        
        def _keep_lease_alive(lease):
            request = VI.HttpNfcLeaseProgressRequestMsg()
            _this =request.new__this(lease)
            _this.set_attribute_type(lease.get_attribute_type())
            request.set_element__this(_this)
            request.set_element_percent(10)
            while self._keepalive:
                self._s._proxy.HttpNfcLeaseProgress(request)
                time.sleep(5)

        self._keepalive = True  # flag to keep the http connection alive
        
        if self._s == None:
            self._server_connect()
        
        folder = self._find_vmfolder_by_name()
        resource_pool = self._find_resource_pool(host)
        datastore = self._find_datastore(host, ds_name=datastore)
            
        
        # TODO: is this the correct default for VSA?
        if networks==None:
            networks = {"OVF Network Name":"VM Network"}
        
        self.log.debug("Creating the VM import specifications...")
        ci = self._create_import_spec(resource_pool,datastore, vapp_name, network_mapping=networks)
        if hasattr(ci,"ImportSpec") == False:
            _m = "ImportSpec was malformed!"
            self.log.debug("ImportSpec was malformed!")
            msg = ci.Error[0].LocalizedMessage
            self.log.debug(msg)
            _m = "%s:%s"%(_m,msg)
            raise TypeError(_m)
        
        self.log.debug("Import spec completed. Starting vApp deployment.")
        http_nfc_lease = self._import_vapp(resource_pool, ci, folder=folder)
        lease = VIProperty(self._s, http_nfc_lease)
        lease._flush_cache()
        while True:
            try: 
                if lease.state == 'initializing':
                    time.sleep(1)
                    lease._flush_cache()
                else:
                    break
            except:
                time.sleep(1)
        
        if lease.state != 'ready':
            self.log.debug("Lease state not ready.")
            _msg = (lease._values['error']).LocalizedMessage
            self.log.debug(_msg)
            raise TypeError("Cannot deploy OVA:%s"%_msg)
        
        t = threading.Thread(target=_keep_lease_alive, args=(http_nfc_lease,))
        t.start()
        
        
        filenames = self._find_vmdks()
        i = 0
        for dev_url in lease.info.deviceUrl:
            self.log.debug("Device URL:%s"%dev_url)
            filename = filenames[i]
            self.log.debug("Found vmdk:%s"%filename)
            hostname = urlparse(self._s._proxy.binding.url).hostname
            upload_url = dev_url.url.replace("*", hostname)
            filename = os.path.join(self._ova_dir, filename)
            self.log.debug("Copying:%s"%filename)
            fsize = os.stat(filename).st_size
            
            with open(filename,'rb') as f:
                request = urllib2.Request(upload_url, f)          
                request.add_header("Content-Type", "application/x-vnd.vmware-streamVmdk")
                request.add_header("Connection", "Keep-Alive")
                request.add_header("Content-Length", str(fsize))
                opener = urllib2.build_opener(urllib2.HTTPHandler)
                resp = opener.open(request)
        
            i += 1

        self._keepalive = False
        t.join()
        
        request = VI.HttpNfcLeaseCompleteRequestMsg()
        _this =request.new__this(http_nfc_lease)
        _this.set_attribute_type(http_nfc_lease.get_attribute_type())
        request.set_element__this(_this)
        self._s._proxy.HttpNfcLeaseComplete(request)
        
        self.log.debug("OVF deployment complete.")
        

class HostTool(VimTool):
    """
     Performs queries and operations pertaining ESX hosts.
     
     Note: We're sending all host requests thru the vSphere server
     to avoid having to disassociate the host from vSphere for management
     changes.
    """
    def __init__(self,host_name,sut=None,server=None,username='root',password=None):
        # Call the VimTool constructor
        if sut:
            super(HostTool, self).__init__(sut=sut,
                                           server=host_name,
                                           username=sut.username,
                                           password=sut.password)
        else:
            super(HostTool, self).__init__(server=server,username=username,password=password)
        
        self.host_name = host_name
        self._host_mor = None
        self._pci_system_id = None


    def _get_host(self):
        """
         Acquires the pySphere VIServer object
        """
        if self._s == None:
            self._server_connect()
        if self._host_mor != None:
            return self._host_mor
        else:
            for h,v in self._s.get_hosts().items():
                if v == self.host_name:
                    self._host_mor = h
                    return self._host_mor
        _msg = "Failed to find ESX Host MOR. Is %s managed by %s?"%(self.host_name, self.server)
        raise AttributeError(_msg)
               
        
    def is_vm_on_host(self, vm_name):
        """
         Checks if the virtual machine is currently in host's resource 
         pool (eg.the vm is being hosted from the given ESX host).
        """
        self._get_host()
        
        vms = self._s._get_managed_objects(MORTypes.VirtualMachine,from_mor=self._host_mor)
        for k,v in vms.iteritems():
            if v == vm_name:
                return True
        return False
    
    
    def deploy_node(self,node):
        """
         Deploys a node to the ESX host
        """
        # massages the node-vm data and calls deploy_vm
        pass
    
    
    def deploy_vm(self, template, vm_name):
        """
         Deploys a template to specified ESX host.
        """
        pass

    
    def reboot(self, wait_for_connected=True):
        """
         Initiates a reboot request to the ESX host. This includes the Force flag
         such that the host does not need to be put in maintenance mode prior to shutdown.
         
         :param wait_for_connected: If True (default), it waits for the host to 
                                    boot back up and reconnect to vsphere.
        """
        self._get_host()
        
        request = VI.RebootHost_TaskRequestMsg()
        request.set_element__this(self._host_mor)
        request.set_element_force(True)
        self._s._proxy.RebootHost_Task(request)
        
        while True:
            try:
                if self.is_connected(): 
                    sleep(10)
                else:
                    raise
            except:
                self.log.debug("The host %s has gone down."%self.host_name)
                break
        
        # Don't care if it's still down so we bail.
        if wait_for_connected == False:
            return
            
        while True:
            try:
                self._server_connect()
                if self.is_connected():
                    break
                else:
                    self.log.debug("Host %s is up but not connected to vsphere."%self.host_name)
                    sleep(10)
            except Exception, ex:
                self.log.debug("Waiting for %s to come back online."%self.host_name)
                #self.log.debug("The error: %s"%ex)
                sleep(10)


    def is_connected(self):
        self._get_host()
        
        properties = VIProperty(self._s, self._host_mor)
        rt = properties.runtime
        if rt.connectionState == "connected":
            return True
        
        return False


    def get_ssd_devices(self):
        """
         Queries the ESX host for available SSD's.
         
         Returns a list of PciDevice objects 
             
        """
        # White list of device IDs we want to add.
        # These Device IDs are displayed in the GUI as 
        # hex but we need the decimal values.
        SSD_DEV_IDS = [20816,   # Micron
                       -22496]   # Samsung NVMe
        
        self._get_host()
        
        properties = VIProperty(self._s, self._host_mor)
        pci_devs = properties.hardware.pciDevice
        ret = []
        for dev in pci_devs:
            #DeviceId against the list available at:http://pci-ids.ucw.cz/read/PC/
            if dev.deviceId in SSD_DEV_IDS:
                _dev = PciDevice(dev.id,
                                 dev.deviceId,
                                 dev.deviceName,
                                 dev.vendorId,
                                 dev.vendorName)
                ret.append(_dev)
        return ret
    
    def get_fc_adapters(self):
        """ 
         Queries for a list of FibreChannel adapters.
         
         Returns a list of PciDEvice objects
         
         """
        # white list of Fibre Channel adapters.
        # These are displayed as hex in the GUI (like the SSD's)
        # but the hex Emulex deviceID is not a straight decimal conversion.
        # Its 0xE200 and instead of being 57856 but its value is (-7680).
        PC_DEV_IDS = [-7680, # Emulex
                      9522]  # Qlogic
        
        self._get_host()
        
        properties = VIProperty(self._s, self._host_mor)
        pci_devs = properties.hardware.pciDevice
        ret = []
        for dev in pci_devs:
            if dev.deviceId in PC_DEV_IDS:
                _dev = PciDevice(dev.id,
                                 dev.deviceId,
                                 dev.deviceName,
                                 dev.vendorId,
                                 dev.vendorName)
                ret.append(_dev)
        return ret
    
    
    def get_storage_adapters(self):
        """
        """
        self._get_host()
        
        properties = VIProperty(self._s, self._host_mor)
        hbas = properties.configManager.storageSystem.storageDeviceInfo.hostBusAdapter
        return hbas


    def get_iscsi_luns(self):
        self._get_host()
        
        ret = []
        properties = VIProperty(self._s, self._host_mor)
        luns = properties.configManager.storageSystem.storageDeviceInfo.scsiLun
        for lun in luns:
            if lun.deviceType == 'disk' and str(lun.displayName).lower().find('local') == -1:
                ret.append(lun)
        return ret
    
    
    def get_iscsi_wwns(self, luns=None):
        self._get_host()
        
        if not luns:
            luns = self.get_iscsi_luns()
        ret = []
        for lun in luns:
            try:
                wwn = lun.canonicalName.split('naa.')[1]
                ret.append(wwn)
            except IndexError:
                pass
        return ret
    

    def find_datastore_by_wwn(self, wwn):
        """
         Finds the datastore MOR residing on the disk with given WWN
        """
        self._get_host()
        
        if not wwn:
            raise AttributeError("WWN not specified.")
        wwn = wwn.lower()
        
        for ds_mor, name in self._s.get_datastores().items():
            props = VIProperty(self._s, ds_mor)
            host_mounts = props.host
            for hm in host_mounts:
                if self._host_mor == hm._obj.Key:
                    extents = props.info.vmfs.extent
                    for extent in extents:
                        try:
                            disk = extent.diskName.split('naa.')[1]
                            if disk == wwn:
                                return ds_mor
                        except:
                            continue
        self.log.debug("Did not find datastore with WWN %s"%wwn)
        return None
            
    def get_datastore_size(self, wwn=None, ds_mor=None):
        """ 
         Returns the size of the datastore in Megabytes
         
         :param wwn: The WWN of the datastore
         :param ds_more: The datastore MOR.
        """
        #When instantiating the host tool, it's more accurate
        #to specify the server as the vsphere server for this operation.
        if self.sut:
            self._s = None
            self.server = self.sut.vsphere_server
        self._get_host()
        
        if not wwn and not ds_mor:
            raise AttributeError("Requires either a wwn or ds_mor parameter.")
        if not ds_mor:
            ds_mor=self.find_datastore_by_wwn(wwn)
        
        if not ds_mor:
            raise AttributeError("Failed to find datastore with wwn %s"%wwn)
        
        props = VIProperty(self._s, ds_mor)
        return props.info.vmfs.capacity / (1024*1024)
                                

    def find_local_datastores(self):
        """
         Finds a list of local datastores and returns a list of 
         tuples containing (ds_mor, name, wwn).
        
        """
        #When instantiating the host tool, it's more accurate
        #to specify the server as the vsphere server for this operation.
        if self.sut:
            self._s = None
            self.server = self.sut.vsphere_server
        self._get_host()
        
        ret = []
        for ds_mor, name in self._s.get_datastores().items():
            props = VIProperty(self._s, ds_mor)
            host_mounts = props.host
            for hm in host_mounts:
                if self._host_mor == hm._obj.Key:
                    if props.summary.multipleHostAccess == False:
                        extents = props.info.vmfs.extent
                        for extent in extents:
                            if 'naa.' in extent.diskName:
                                wwn = extent.diskName.split('naa.')[1]
                                ret.append((ds_mor,name,wwn))
                            else:
                                ret.append((ds_mor,name,""))
        return ret

    
    def create_datastore(self, datastore_name, lun_wwn, error_on_existing=True):
        """
            Creates a datastore on a given LUN. This will currently consume
            the entire LUN for the datastore. That is to say this does not
            support partitions.
            
            Notes
                This operation has changed(?) since 5.0 and the vmware VIM API
                documentation is incredibly misleading about the operation types.
                
                Avoid the specs around VmfsDatastoreCreateSpec and refer to
                VmfsDatastoreOption at (http://pubs.vmware.com/vsphere-50/topic
                /com.vmware.wssdk.apiref.doc_50/vim.host.VmfsDatastoreOption.html)
                
                VFMS Version 5 only supports a blocksize of 1MB so that option
                is being omitted from this method.
            
            :param datastore_name: Human name to assign the the datastore.
            :param lun_wwn: WWN of the LUN where we want to create the datastore
            :param error_on_existing: Raises an error if a datastore already exists.
        """
        self._get_host()
        VMFS_VERSION = 5
        
        lun_wwn = lun_wwn.lower()
        # the canonical name is expected to begin with "naa."
        if str(lun_wwn).startswith("naa.") == False:
            lun_wwn = "naa.%s"%lun_wwn
        
        if self.find_datastore_by_wwn(lun_wwn) and error_on_existing == False:
            self.log.debug("Datastore already exists on %s"%lun_wwn)
            return
        
        # create the CreateVmfsDatastoreRequestMsg request message
        request = VI.CreateVmfsDatastoreRequestMsg()

        # Find our datastore system manager MOR
        result = self._s._retrieve_properties_traversal(['configManager.datastoreSystem'],
                                                        from_node=self._host_mor,
                                                        obj_type=MORTypes.HostSystem)[0]
        for prop in result.PropSet:
            if prop.Name == 'configManager.datastoreSystem':
                hds = request.new__this(prop.Val)
                hds.set_attribute_type(MORTypes.HostDatastoreSystem)
                request.set_element__this(hds)

        spec = request.new_spec()
        
        # Query for the specification for creating the datastore on disk
        req = VI.QueryVmfsDatastoreCreateOptionsRequestMsg()
        req.set_element__this(hds)
        req.set_element_devicePath("/vmfs/devices/disks/%s"%lun_wwn)
        req.set_element_vmfsMajorVersion(VMFS_VERSION)
        resp = self._s._proxy.QueryVmfsDatastoreCreateOptions(req)
        try:
            spec = resp._returnval[0].Spec
        except:
            if error_on_existing:
                _s = "No datastore create specs found. Datastore already exists on %s?"%lun_wwn
                raise TypeError(_s)
            else:
                self.log.debug("Datastore already exists on %s. Not raising an error."%lun_wwn)
                return
            
        spec.Vmfs.VolumeName=datastore_name
        request.set_element_spec(spec)
        self._s._proxy.CreateVmfsDatastore(request)
        
        
    def delete_datastore(self, datastore_mor, retry_on_error=True):
        """
            Deletes a datastore. Calling this on a non-existent or inactive
            datastore will result an error being raised.
            
            :param datastore_mor: MOR ID of the datastore to be deleted.
            :param retry_on_error: Will retry the delete opeation if it fails.
        """
        ATTEMPTS = 8
        ATTEMPT_INTERVAL = 15
        
        self._get_host()
        
        if not datastore_mor:
            raise TypeError("Delete_datastore requires a datastore MOR.")
        
        request = VI.RemoveDatastoreRequestMsg()
        result = self._s._retrieve_properties_traversal(['configManager.datastoreSystem'],
                                                        from_node=self._host_mor,
                                                        obj_type=MORTypes.HostSystem)[0]
        for prop in result.PropSet:
            if prop.Name == 'configManager.datastoreSystem':
                hds = request.new__this(prop.Val)
                hds.set_attribute_type(MORTypes.HostDatastoreSystem)
                request.set_element__this(hds)
        request.set_element_datastore(datastore_mor)
        
        attempt = 0
        while attempt < ATTEMPTS:
            try:
                self.log.debug("Attempt %s to remove datastore %s"%(attempt,datastore_mor))
                self._s._proxy.RemoveDatastore(request)
                self.log.debug("Datastore was deleted.")
                break
            except Exception, ex:
                if not retry_on_error:
                    raise ex
                self.log.debug("Attempt %s failed. %s"%(attempt, ex))
                sleep(ATTEMPT_INTERVAL)
                attempt += 1
    
        
    def rescan_hbas(self):
        """
         Issues an HBA rescan on the host.
        """
        self._get_host()
        
        request = VI.RescanAllHbaRequestMsg()
        result = self._s._retrieve_properties_traversal(['configManager.storageSystem'],
                                                        from_node=self._host_mor,
                                                        obj_type=MORTypes.HostSystem)[0]
        for prop in result.PropSet:
            if prop.Name == 'configManager.storageSystem':
                hss = request.new__this(prop.Val)
                hss.set_attribute_type(MORTypes.HostStorageSystem)
                request.set_element__this(hss)
                break
        
        self.log.debug('Host [%s] HBA Rescan All' % self.host_name)
        self._s._proxy.RescanAllHba(request)
    
    def rescan_vmfs(self):
        """
          Issues VMFS rescan on host.
        """
        self._get_host()

        request = VI.RescanVmfsRequestMsg()
        result = self._s._retrieve_properties_traversal(['configManager.storageSystem'],
                                                        from_node=self._host_mor,
                                                        obj_type=MORTypes.HostSystem)[0]

        for prop in result.PropSet:
            if prop.Name == 'configManager.storageSystem':
                hss = request.new__this(prop.Val)
                hss.set_attribute_type(MORTypes.HostStorageSystem)
                request.set_element__this(hss)
                break
        
        self.log.debug('VMFS [%s] Rescan VMFS' % self.host_name)
        self._s._proxy.RescanVmfs(request)


    def get_iser_hba_names(self):
        """
         Queries the host for Mellanox ISER HBAs and returns a list
         of tuples of (HBA name, pNic name).
        """
        self._get_host()
        
        iser_names = []
        hbas = self.get_storage_adapters()
        for hba in hbas:
            if hba.model.find(MELLANOX_DRIVER) > -1:
                iser_names.append((str(hba.device), hba.iScsiAlias.split("-")[1]))
        self.log.debug("Host [%s] has ISER HBAs:%s"%(self.host_name,iser_names))
        return iser_names
    
    
    def get_iscsi_software_adapter(self):
        """
         Returns the HBA name (eg. vmhba40) of the iSCSI Software Adapter 
         if it exists. If not, None is returned.
        """
        self._get_host()
        
        hbas = self.get_storage_adapters()
        for hba in hbas:
            if hba.model == ISCSI_ADAPTER_MODEL:
                return hba.device
        return None
        
    
    def bind_vnic(self, hba_name, vnic):
        """ 
         binds the virtual nic that will 
         be used as an iscsi adapter
         
         :param hba_name: Name of the HBA
         :param vnic: Name of the virtual NIC
        """
        self._get_host()
        
        request = VI.BindVnicRequestMsg()
        result = self._s._retrieve_properties_traversal(['configManager.iscsiManager'],
                                                        from_node=self._host_mor,
                                                        obj_type=MORTypes.HostSystem)[0]
        for prop in result.PropSet:
            if prop.Name == 'configManager.iscsiManager':
                imgr = request.new__this(prop.Val)
                imgr.set_attribute_type(MORTypes.IscsiManager)
                request.set_element__this(imgr)
                break
        request.set_element_iScsiHbaName(hba_name)
        request.set_element_vnicDevice(vnic)

        self._s._proxy.BindVnic(request)

    
    def unbind_vnic(self, hba_name, vnic):
        """
         Unbinds a vmk from an HBA.
          
         :param hba_name: Name of the HBA (vmhba47563)
         :param vnic: Name of the virtual NIC portgroup (vmk1)
        """
        self._get_host()
                
        request = VI.UnbindVnicRequestMsg()
        result = self._s._retrieve_properties_traversal(['configManager.iscsiManager'],
                                                        from_node=self._host_mor,
                                                        obj_type=MORTypes.HostSystem)[0]
        for prop in result.PropSet:
            if prop.Name == 'configManager.iscsiManager':
                imgr = request.new__this(prop.Val)
                imgr.set_attribute_type(MORTypes.IscsiManager)
                request.set_element__this(imgr)
                break
        request.set_element_iScsiHbaName(hba_name)
        request.set_element_vnicDevice(vnic)
        request.set_element_force(True)

        self._s._proxy.UnbindVnic(request)
    
    
    def unbind_iser_hbas(self):
        """
         Queries the hoststorage system for any bound HBA's
         and unbinds them from the ISER vnics.
        """
        self._get_host()
        
        switches = self.get_vswitches() 
        hbas = self.get_storage_adapters()
        
        for hba in hbas:
            try:
                if hba.iScsiAlias.split("-")[0] != 'iser':
                    continue
                
                vnic = hba.iScsiAlias.split("-")[1]
                for switch in switches:
                    if switch.vnic == vnic:
                        _m="Unbinding %s from %s"%(hba.device, switch.device[0])
                        self.log.debug(_m)
                        self.unbind_vnic(hba.device, switch.device[0])
            except:
                continue
        

    def enable_iscsi(self):
        """
         Enables software iscsi
        """
        self._get_host()
        
        request = VI.UpdateSoftwareInternetScsiEnabledRequestMsg()
        result = self._s._retrieve_properties_traversal(['configManager.storageSystem'],
                                                        from_node=self._host_mor,
                                                        obj_type=MORTypes.HostSystem)[0]
        for prop in result.PropSet:
            if prop.Name == 'configManager.storageSystem':
                hss = request.new__this(prop.Val)
                hss.set_attribute_type(MORTypes.HostStorageSystem)
                request.set_element__this(hss)
                break
        request.set_element_enabled("True")
        self._s._proxy.UpdateSoftwareInternetScsiEnabled(request)   

    
    def enable_passthru(self, pci_ids):
        """ 
         Enables PCI passthru on the ESX host's given PCI devices.
         Note - a host reboot is required before passthru is active.
         
         :param pci_ids: The list of PCI device ID's to enable passthru.  
        """
        self._get_host()

        request = VI.UpdatePassthruConfigRequestMsg()
        result = self._s._retrieve_properties_traversal(['configManager.pciPassthruSystem'],
                                                        from_node=self._host_mor,
                                                        obj_type=MORTypes.HostSystem)[0]
        
        for prop in result.PropSet:
            if prop.Name == 'configManager.pciPassthruSystem':
                pci_pts = request.new__this(prop.Val)
                pci_pts.set_attribute_type(MORTypes.HostPciPassthruSystem)
                request.set_element__this(pci_pts)
                break

        f = []
        for pci_id in pci_ids:
            conf = request.new_config()
            conf.set_element_id(pci_id)
            conf.set_element_passthruEnabled("True")
            f.append(conf)

        self.log.debug("Enabling passthru on PCI devices %s."%f)
        request.set_element_config(f)
        self._s._proxy.UpdatePassthruConfig(request)
    
    
    def configure_vsa_passthru(self, fc_passthru=False):
        """
         High-level method that queries for all the 
         appropriate PCI devices for the VSA and enables
         PCI passthru on them. The host is automatically
         rebooted if any of the devices need to be enabled.
         
         If the devices are already configured for passthru,
         no errors are raised and the host is not rebooted.
        """
        self._get_host()
        prop = VIProperty(self._s, self._host_mor)
        pci_ids = []
        
        nics = self.get_mellanox_devices()
        for nic in nics:
            pci_ids.append(nic.pci_id)
        
        ssds = self.get_ssd_devices()
        for ssd in ssds:
            pci_ids.append(ssd.pci_id)
        
        if fc_passthru:
            fcs = self.get_fc_adapters()
            for fc in fcs:
                pci_ids.append(fc.pci_id)
            
        pci_info = prop.config.pciPassthruInfo
                
        enabled = True
        for pci_id in pci_ids:
            for pci_dev in pci_info:
                if pci_id == pci_dev.id: 
                    if pci_dev.passthruActive == True:
                        break
                    else:
                        self.log.debug("%s is not active"%pci_id)
                        enabled = False
                        break
            if enabled == False:
                break
        
        if enabled == False:
            self.log.debug("Enabling PCI passthru on %s and REBOOTING."%self.host_name)
            self.enable_passthru(pci_ids)
            self.reboot()
            
            
    def get_vswitches(self):
        """
         Queries the ESX host for configured virtual switches and
         returns a list of VirtualSwitch objects populated with the info.
         Raises an AttributeError if no switches are found on the host. 
         
         Will probably want to add a search_list param so we can look for
         mellanox switchs/vnics and remove those methods.
        """
        self._get_host()
        
        ret = []
        prop = VIProperty(self._s, self._host_mor)
        
        # First we acquire the vswitch names, the physical nic they
        # use, and the port groups associated with the vswitch.
        for _vs in prop.configManager.networkSystem.networkInfo.vswitch:
            self.log.debug("Switch: %s"%_vs.name)
            vs = VirtualSwitch(_vs.name,str(_vs.pnic[0].split('-')[2]))
            
            # put all port groups in the vm portgroup slot for now.
            _list =[]
            for pg in _vs.portgroup:
                # the attribute is a string like: key-vim.host.PortGroup-[the name we want]
                _list.append(str(pg.split("PortGroup-")[1]))
                vs.vmpg=_list
            ret.append(vs)
        
        
        # and add the network information.
        for vs in ret:
            vs.vmkg=[]
            vs.device=[]
            # now we cruise vnics looking for VMkernel group associatatd with vswitch
            for vnic in prop.configManager.networkSystem.networkInfo.vnic:
                if vnic.portgroup in vs.vmpg:
                    vs.vmkernel_ip = vnic.spec.ip.ipAddress
                    vs.vmkernel_mask= vnic.spec.ip.subnetMask
                    vs.vmkg.append(vnic.portgroup)
                    vs.vmpg.remove(vnic.portgroup)
                    vs.device.append(vnic.device)
        
        for _s in ret:
            self.log.debug("Found switch: %s"%_s)
        return ret
    
    
    def find_mellanox_vnics(self):
        """
         CP - Do we still need this?
                 
         Finds the vnics
        """
        vSwitch_names = ["FluidCache_Network","MLNXvSwitch"]
        self._get_host()
        prop = VIProperty(self._s, self._host_mor)
        
        ret = []
        for vnic in prop.configManager.networkSystem.networkInfo.vnic:
            switch = None
            for name in vSwitch_names:
                if vnic.portgroup.find(name) > -1:
                    ret.append(vnic.device)
                    
        return ret
        
        
    def find_mellanox_pnics(self):
        """
         CP - Do we still need this?
                 
         Finds the mellanox NIC connected to the vSwitch.
         Returns a list of pnics associated with the host mellanox cards.
        """
        self._get_host()
        
        prop = VIProperty(self._s, self._host_mor)
        vSwitch_names = ["FluidCache_Network","MLNXvSwitch"]
        
        ret = []
        vss = []
        for _vs in prop.configManager.networkSystem.networkInfo.vswitch:
            self.log.debug("Switch: %s"%_vs.name)
            for name in vSwitch_names:
                if name in _vs.name:
                    vss.append((_vs.pnic[0],(_vs.name.split('_'))[1]))
        if len(vss) == 0:
            raise AttributeError("No Mellanox vSwitches found on %s"%self.host_name)
        
        for vs,ip in vss:
            for pnic in prop.configManager.networkSystem.networkInfo.pnic:
                self.log.debug("NIC:%s"%pnic.key)
                if pnic.key == vs:
                    setattr(pnic, 'ip',ip)
                    ret.append(pnic)
        if len(ret) == 0:
            raise AttributeError("No Mellanox NICs found.")
        return ret
    
        
    def get_mellanox_devices(self):
        """
         Queries the ESX host for available Mellanox devices.
         Returns a list of PciDevice objects
        """ 
        self._get_host()
        
        properties = VIProperty(self._s, self._host_mor)
        pci_devs = properties.hardware.pciDevice
        ret = []
        for dev in pci_devs:
            if dev.deviceId == MELLANOX_VF_PT_ID:
                _dev = PciDevice(dev.id,
                                 dev.deviceId,
                                 dev.deviceName,
                                 dev.vendorId,
                                 dev.vendorName)
                ret.append(_dev)
            if len(ret) == MELLANOX_CARD_COUNT:
                break
        if len(ret) == 0:
            _msg = "Failed to find a Mellanox Virtual Function Device."
            raise AttributeError(_msg)
        return ret


    def find_unassigned_nics(self, find_mellanox=False):
        """
         Returns the physical NICs that are not assigned to
         a vSwitch as a list of PCI device objects.
        
        """
        self._get_host()
        
        prop = VIProperty(self._s, self._host_mor)
         
        # Query for all NICs and remove the ones attached to a vSwitch
        unused_nics = []
        nics =  prop.configManager.networkSystem.networkInfo.pnic
        for nic in nics:
            _msg = "Device: %s  Key:%s PCI_ID:%s"%(nic.device, nic.key, nic.pci)
            used = False
            for vs in prop.configManager.networkSystem.networkInfo.vswitch:
                if nic.key in vs.pnic:
                    used = True
                    break
                
            if not used or find_mellanox:
                unused_nics.append(nic)
                    
        
        pci_devs = prop.hardware.pciDevice
        ret = []
        for nic in unused_nics:
            for dev in pci_devs:
                if nic.pci == dev.id:
                    # we find only the mellanox cards if the flag is set
                    if find_mellanox:
                        if dev.deviceId in MELLANOX_DEVICE_IDS:
                            _dev = PciDevice(dev.id,
                                             dev.deviceId,
                                             dev.deviceName,
                                             dev.vendorId,
                                             dev.vendorName,
                                             nic.device)
                            
                            # if the device has no linkspeed, skip it since it's down
                            try:
                                ls = nic.linkSpeed
                                ret.append(_dev)
                            except AttributeError:
                                pass
                            break
                        else:
                            continue
                        if len(ret) == MELLANOX_CARD_COUNT * 2:
                            return ret
                    else:
                        if dev.deviceId not in MELLANOX_DEVICE_IDS:
                            _dev = PciDevice(dev.id,
                                             dev.deviceId,
                                             dev.deviceName,
                                             dev.vendorId,
                                             dev.vendorName,
                                             nic.device)
                            # if the device has no linkspeed, skip it since it's down
                            try:
                                ls = nic.linkSpeed
                                ret.append(_dev)
                            except AttributeError:
                                pass
                            break
        
        # The mellanox cards are inventoried as two devices per card 
        # and so we will incorrectly have two NIC's per card and we remove
        # the duplicates (every other item) in our list..
        if find_mellanox and len(ret) > MELLANOX_CARD_COUNT:
            ret = ret[1::2]
        
        return ret            
        

    def add_vswitch(self, 
                       nic,
                       vswitch_name = "",
                       group_name = "",
                       vmkernel_ip = None,
                       vmkernel_mask = None,
                       skip_vmpg = False, 
                       error_on_existing = False):
        """
         Create a virtual switch on the host machine.
         
         NOTE We're assuming any switches created will be assigned a freshly
         create virtual nic.
         
        REQUIRED PARAMETERS
        :param nic: Name of NIC that the virtual switch is created on. Example "vmnic1"
    
        OPTIONAL PARAMETERS
        :param vswitch_name: Switch name. Defaults to "vSwitch_AE2_[nic name]"
        :param group_name: Network label for port group. Defaults to "VMkernel_$vswitch_name".
        :param vmkernel_ip: IP for the SR-IOV virtual NIC.
        :param vmkernel_mask: Network mask for the SR-IOV virtual NIC.
        :param skip_vmpg: Skips the creation of VMPortgroup when a VMKernel is created (for ISER)
        :param error_on_existing: If set to True, a pre-existing switch will raise an error
         
        """
        
        self._get_host()
        
        def add_virtual_switch(network_system, name, num_ports=120, bridge_nic="vmnic6"):    
            request = VI.AddVirtualSwitchRequestMsg()
            _this = request.new__this(network_system)    
            _this.set_attribute_type(network_system.get_attribute_type())    
            request.set_element__this(_this)    
            request.set_element_vswitchName(name) 
            spec = request.new_spec()
            spec.set_element_numPorts(num_ports) 
            #spec.set_element_mtu(mtu)
             
            if bridge_nic:
                bridge = VI.ns0.HostVirtualSwitchBondBridge_Def("bridge").pyclass() 
                bridge.set_element_nicDevice([bridge_nic])        
                spec.set_element_bridge(bridge) 
            request.set_element_spec(spec)    
        
            try:
                self._s._proxy.AddVirtualSwitch(request)
            except Exception, ex:
                if error_on_existing and not "already exists" in ex.message:
                    raise ex         
        
        
        def add_port_group(network_system, group_name, vlan_id, vswitch):
            self.log.debug("Adding portgroup [%s] to switch[%s]"%(vswitch,group_name))
            request = VI.AddPortGroupRequestMsg()    
            _this = request.new__this(network_system)    
            _this.set_attribute_type(network_system.get_attribute_type())    
            request.set_element__this(_this) 
            portgrp = request.new_portgrp()
            portgrp.set_element_name(group_name)
            portgrp.set_element_vlanId(vlan_id)    
            portgrp.set_element_vswitchName(vswitch)    
            portgrp.set_element_policy(portgrp.new_policy())    
            request.set_element_portgrp(portgrp)
            
            self._s._proxy.AddPortGroup(request)
            
        
        def add_virtual_nic(network_system, group_name, vnic_spec):
            request = VI.AddVirtualNicRequestMsg()
            _this = request.new__this(network_system)
            _this.set_attribute_type(network_system.get_attribute_type())    
            request.set_element__this(_this)
            request.set_element_portgroup(group_name)
            request.set_element_nic(vnic_spec)
            
            self._s._proxy.AddVirtualNic(request)
              
            
        def create_vnic_spec(ip, mask):
            hic = VI.ns0.HostIpConfig_Def("hic").pyclass()
            hic.set_element_dhcp(False)
            hic.set_element_ipAddress(ip)
            hic.set_element_subnetMask(mask)
            
            hvns = VI.ns0.HostVirtualNicSpec_Def("hvns").pyclass()
            hvns.set_element_ip(hic)
            return hvns
        
        # Default values for vSwitch configuration
        vlan_id = 0
        num_ports = 120

        prop = VIProperty(self._s, self._host_mor) 
        network_system = prop.configManager.networkSystem._obj
        
        if not vswitch_name:
            vswitch_name = "%s%s"%(VSWITCH_PREFIX,nic)
        if not group_name:
                group_name = "%s%s"%(PORTGROUP_PREFIX,nic)         
        
        self.log.debug("Creating new vSwitch %s on NIC: %s"%(vswitch_name, nic))        
        add_virtual_switch(network_system, vswitch_name, num_ports, bridge_nic=nic)
        self.log.debug("Adding the portgroup")
        
        vmkg = None
        if vmkernel_ip:
            _gp = "%s_VMkernel"%(group_name)
            add_port_group(network_system, _gp, vlan_id, vswitch_name)
            vnic_spec = create_vnic_spec(vmkernel_ip, vmkernel_mask)
            self.log.debug("Adding the vNic to the vSwitch")
            add_virtual_nic(network_system, _gp, vnic_spec)
            vmkg = _gp
            if not skip_vmpg:
                add_port_group(network_system, group_name, vlan_id, vswitch_name)
            self.log.debug("vSwitch %s created successfully."%vswitch_name)
        else:
            add_port_group(network_system, group_name, vlan_id, vswitch_name)
        
        # Return a switch object so the caller knows what was created
        created = VirtualSwitch(
                                vswitch_name,
                                nic,
                                [group_name],
                                [vmkg],
                                vmkernel_ip,
                                vmkernel_mask)
        return created
    
    
    def remove_vnic(self, vnic):
        """
            Removes a virtual NIC device from a the host vSwitch.
        """
        
        self._get_host()
        
        prop = VIProperty(self._s, self._host_mor) 
        network_system = prop.configManager.networkSystem._obj
        request = VI.RemoveVirtualNicRequestMsg()
        _this = request.new__this(network_system)
        _this.set_attribute_type(network_system.get_attribute_type())    
        request.set_element__this(_this)
        request.set_element_device(vnic)
        self._s._proxy.RemoveVirtualNic(request)
    
    
    def remove_vswitch(self, name):
        """ 
         Removes a vSwitch. 
         
         This operation will fail with a FaultException if the vSwitch
         still has VM's mapped to the VM Portgroup or if a VM Kernel port
         is still (vNIC) is still active.
         
         NOTE: If this turns out to be slow-ish (I question how efficient the
         HostNetworkSystem lookup is...) we should change this to take a list
         of switch names so as to avoid the TP repeatedly calling this and 
         redundant HostNetworkSystem lookups.
         
         :param name: The name (fiendly name) of the switch to remove.
        """
        self._get_host()
        
        if not name:
            raise AttributeError("Missing parameter: name")
        
        prop = VIProperty(self._s, self._host_mor) 
        network_system = prop.configManager.networkSystem._obj
        request = VI.RemoveVirtualSwitchRequestMsg()    
        _this = request.new__this(network_system)    
        _this.set_attribute_type(network_system.get_attribute_type())    
        request.set_element__this(_this)
        request.set_element_vswitchName(name)
        
        self.log.debug("Removing vSwitch %s"%name)
        self._s._proxy.RemoveVirtualSwitch(request)
        self.log.debug("Switch removed.")

    
    def connect_iser(self, send_targets, port=None, hba_name=None, bind_vnic=True):
        """
         Connects the iSER initiator to the target in VSA
         
         TODO We're currently binding only one (the first)  Mellanox NIC
         that we find. 
                            
        """
        self._get_host()
        
        if not send_targets:
            raise AttributeError("No send targets specified")
        if not hba_name:
            hba_name = self.get_iser_hba_names()
            if len(hba_name) == 0:
                raise AttributeError("Failed to find ISER HBA on %s"%self.host_name)
            hba_name = hba_name[0]
            
        if not port:
            port = ISER_PORT
        
        if bind_vnic:
            nics = self.find_mellanox_vnics()
            if len(nics)==0:
                raise AttributeError("Failed to find Mellanox vNICs")
            vnic = nics[0]
            self.bind_vnic(hba_name, vnic)
        
        ######## Skip adding the sendtargets
        request = VI.AddInternetScsiSendTargetsRequestMsg()
        result = self._s._retrieve_properties_traversal(['configManager.storageSystem'],
                                                        from_node=self._host_mor,
                                                        obj_type=MORTypes.HostSystem)[0]
        for prop in result.PropSet:
            if prop.Name == 'configManager.storageSystem':
                hss = request.new__this(prop.Val)
                hss.set_attribute_type(MORTypes.HostStorageSystem)
                request.set_element__this(hss)
                break
        
        request.set_element_iScsiHbaDevice(hba_name)
        t = []
        for send_target in send_targets:
            st = request.new_targets()
            st.set_element_port(port)
            st.set_element_address(send_target)
            t.append(st)
        request.set_element_targets(t)
        self._s._proxy.AddInternetScsiSendTargets(request)
    
    
    def add_target_to_iscsi_swadapter(self, send_target):
        """
         Adds a sendtarget to the iSCSI Software Adapter on the 
         ESX host.
         
         This seems to be the equivalent of adding the target to the 
         Dynamic Discovery list in the GUI which is to say that each
         lun is automatically discovered and added to the static list.
        """
        self._get_host()
        
        if not send_target:
            raise AttributeError("Parameter send_target incorrect. Cannot be None or empty.")
        
        hba_name = self.get_iscsi_software_adapter()
        if len(hba_name) == 0:
            raise AttributeError("Failed to find iSCSI Software Adapter HBA on %s"%self.host_name)
                
        request = VI.AddInternetScsiSendTargetsRequestMsg()
        result = self._s._retrieve_properties_traversal(['configManager.storageSystem'],
                                                        from_node=self._host_mor,
                                                        obj_type=MORTypes.HostSystem)[0]
        for prop in result.PropSet:
            if prop.Name == 'configManager.storageSystem':
                hss = request.new__this(prop.Val)
                hss.set_attribute_type(MORTypes.HostStorageSystem)
                request.set_element__this(hss)
                break
        
        request.set_element_iScsiHbaDevice(hba_name)
        t = []
        st = request.new_targets()
        st.set_element_port(ISER_PORT)
        st.set_element_address(send_target)
        t.append(st)
    
        request.set_element_targets(t)
        self._s._proxy.AddInternetScsiSendTargets(request)        


class VmTool(VimTool):
    """
     Wrapper class around the pySphere VIVirtualMachine object
     
     TODO The guest credentials should probably be required.
         we can probably pick these out of the sut using the 
         vm_name and just check that they are speicified.
    """    
    def __init__(self,
                 vm_name,
                 sut=None,
                 server=None,
                 username=None,
                 password=None,
                 guest_username=None,
                 guest_password=None):
        
        # Call the VimTool constructor
        if sut:
            super(VmTool, self).__init__(sut=sut,
                                         server=sut.vsphere_server,
                                         username=sut.vsphere_username,
                                         password=sut.vsphere_password)
        
        else:
            if not username:
                raise AttributeError("VmTool requires either a SUT or username and password parameters.")
            super(VmTool, self).__init__(server=server,username=username,password=password)
        
        if guest_username and guest_password:
            self.guest_username = guest_username
            self.guest_password = guest_password
            
        self.sut = sut
        self.vm_name = vm_name
        self.guest_username = guest_username
        self.guest_password = guest_password
        self._vm = None
        self._authenticated = False
        self._pid = None
        self._pci_system_id = None

    
    def _get_vm(self):
        """
         Acquires the pySphere VIVirtualMachine object
        """
        if self._s == None:
            self._server_connect()
        if self._vm == None:
            self._vm = self._s.get_vm_by_name(self.vm_name,datacenter=None)
            
    def _do_authentication(self):
        
        if self._authenticated == True:
            return
        self._get_vm()
        try:
            if self.guest_username != None:
                self.log.debug("%s:%s"%(self.guest_username, self.guest_password))
                self._vm.login_in_guest(self.guest_username, self.guest_password)
                self._authenticated = True
            elif self.sut:
                _node = self.sut.get_node_by_vmname(self.vm_name)
                self.guest_username = _node.username
                self.guest_password = _node.password
                self.log.debug("%s:%s"%(self.guest_username, self.guest_password))
                self._vm.login_in_guest(self.guest_username, self.guest_password)
                self._authenticated = True
            else:
                _msg = "If no SUT object is available, authentication requires "
                _msg+= "credentials to both vCenter and guest."
                raise ValueError("No credentials to authenticate.\n%s"%_msg)
        except VimError, ex:
            msg = "Failed to authenticate to: %s.\n" % self.vm_name
            msg+= "VimError:%s\n" % ex
            msg+= "Or possibly VmTools or vmware-tools-plugins-vix is not installed."
            raise ValueError(msg)              


    def get_nics(self):
        """
         Queries for a list of network cards on the guest machine.
         Returns a list of adapter objects:
         
          nics[n]
                 .MacAddress => 00:50:56:94:06:8f
                 .Backing.DeviceName => Vm Network
                 .Network => network-34 (the network MOR ID)
                 .DeviceInfo.Label => Network adapter 1
                 .DeviceInfo.Summary => VM Networks             
        """
        
        self._get_vm()
        
        nics = [] 
        for dev in self._vm.properties.config.hardware.device: 
            if dev._type in VIRTUAL_NIC_TYPES:
                nics.append(dev._obj)                 
        return nics

        
    def reset_network_labels(self):
        """
         Resets the VM's network mappings such that each
         NIC is mapped to the default VM Network label.
        """
        self._get_vm()
        
        nics = self.get_nics()
        for nic in nics:
            dev = nic.DeviceInfo.Label
            self.log.debug("Setting adapter %s to %s"%(dev, VM_NETWORK))
            self.set_network(VM_NETWORK, dev)
            sleep(1) 
    

    def set_mac(self, mac, nic=None):
        """
         Sets the MAC address on the guest machines NIC.
         If you need to find the MAC address dynamically,
         use vimer.lookupmac() on the hostname.
         
         :param nic: Name of the virtual NIC (defaalts to the first)
         :param mac: MAC address the NIC will be assigned.
         """
        
        self._get_vm()
        
        # Here for backwards compatibility
        # If the NIC is not specified, use the first one
        if not nic:
            nic = VIRTUAL_NIC_NAMES[0]
        
        net_device = None 
        for dev in self._vm.properties.config.hardware.device: 
            if dev._type in VIRTUAL_NIC_TYPES:
                net_device = dev._obj 
                break 
        if net_device == None:
            raise ValueError ("Failed to find virtual NIC on guest.")

        net_device.set_element_addressType("Manual") 
        net_device.set_element_macAddress(mac)
        
        #Invoke ReconfigVM_Task 
        request = VI.ReconfigVM_TaskRequestMsg()
        _this = request.new__this(self._vm._mor) 
        _this.set_attribute_type(self._vm._mor.get_attribute_type()) 
        request.set_element__this(_this) 
        spec = request.new_spec()
        dev_change = spec.new_deviceChange() 
        dev_change.set_element_device(net_device) 
        dev_change.set_element_operation("edit")
        spec.set_element_deviceChange([dev_change]) 
        request.set_element_spec(spec)
        ret = self._s._proxy.ReconfigVM_Task(request)._returnval 
        
        #Wait for the reconfigure task to finish 
        task = VITask(ret, self._s) 
        
        status = task.wait_for_state([task.STATE_SUCCESS, task.STATE_ERROR]) 
        if status == task.STATE_SUCCESS: 
            self.log.debug("MAC address on %s has been changed to:%s"% (self.vm_name,mac)) 
        else: 
            raise ValueError("Error changing the MAC address:%s"%task.get_error_message())
    
    def set_network(self, label, nic):
        """
         Sets the network label for a NIC. In other words, this
         binds the guest NIC to a virtual switch.
         
         :param label: The vswtich label we want to bind.
         :param nic: Name of the virtual NIC eg. "Network adapter 1"
        """

        self._get_vm()
        
        net_device = None
        for dev in self._vm.properties.config.hardware.device: 
            if dev._type in VIRTUAL_NIC_TYPES and dev.deviceInfo.label == nic:
                net_device = dev._obj 
        if not net_device:
            raise ValueError("Failed to find NIC: %s"%nic)
        
        net_device.Backing.set_element_deviceName(label)

        request = VI.ReconfigVM_TaskRequestMsg()
        _this = request.new__this(self._vm._mor)
        _this.set_attribute_type(self._vm._mor.get_attribute_type())
        request.set_element__this(_this)
        spec = request.new_spec()
        dev_change = spec.new_deviceChange()
        dev_change.set_element_device(net_device)
        dev_change.set_element_operation("edit")
        spec.set_element_deviceChange([dev_change])
        request.set_element_spec(spec)
        ret = self._s._proxy.ReconfigVM_Task(request)._returnval

        #Wait for the task to finish
        task = VITask(ret, self._s)

        status = task.wait_for_state([task.STATE_SUCCESS, task.STATE_ERROR])
        if status == task.STATE_SUCCESS:
            self.log.debug("VM %s network %s successfully reconfigured" % (self.vm_name,label))

        elif status == task.STATE_ERROR:
            raise ValueError("Error reconfiguring vm: %s" %task.get_error_message()) 
   
    def _get_pci_system_id(self):

        if self._pci_system_id == None:
            self._get_vm()
            hostmor = self._vm.properties.runtime.host._obj
            dcmors = (self._s.get_datacenters()).keys()
            for dcmor in dcmors:
                dcprops = VIProperty(self._s, dcmor)
                hfmor = dcprops.hostFolder._obj
                crmors = self._s._retrieve_properties_traversal(property_names=['name','host'], from_node=hfmor, obj_type='ComputeResource')
                if not crmors:
                    continue
                crmor = None
                for cr in crmors:
                    if crmor:
                        break
                    for p in cr.PropSet:
                        if p.Name == "host":
                            for h in p.Val.get_element_ManagedObjectReference():
                                if h == hostmor:
                                    crmor = cr.Obj
                                    break
                            if crmor:
                                break
                if crmor:
                    break
            if not crmor:
                raise AttributeError("Failed to find ComputeResource mor.")
    
            crprops = VIProperty(self._s, crmor)
            request = VI.QueryConfigTargetRequestMsg()
            _this = request.new__this(crprops.environmentBrowser._obj)
            _this.set_attribute_type(crprops.environmentBrowser._obj.get_attribute_type ())
            request.set_element__this(_this)
            h = request.new_host(hostmor)
            h.set_attribute_type(hostmor.get_attribute_type())
            request.set_element_host(h)
            config_target = self._s._proxy.QueryConfigTarget(request)._returnval
            
            try:
                self._pci_system_id = config_target.PciPassthrough[0].SystemId
            except AttributeError:
                _msg = "Failed to find PCI Passthru SystemID. Are there any PCI Passthru devices on the host?"
                raise AttributeError(_msg)
            
        return self._pci_system_id

    
    def add_pci(self, pci):
        """
          Adds a host PCI device to the guest VM. If the
          device already exists on the VM, no action is
          taken and no error raised.
         
         :param pci: A PciDevice object
        """
        
        self._get_vm()
        
        if type(pci) != PciDevice:
            raise TypeError("Parameter pci should be PciDevice object")
        if type(pci.vendor_id) != int:
            raise TypeError("vendor_id must be integer value.")
        
        if type(pci.device_id) == int:
            pci.device_id = hex(pci.device_id)
        
        # If the PCI device is already added, we bail
        # Note that pySpheres VIVirtualMachine class does a terrible job of of itemizing
        # the VM's PCI devices in dictionary rather than a list of zsi objects
        pci_devs = self._vm._devices
        for k, pci_dev in pci_devs.items():
            try:
                if pci_dev["_obj"]._obj.Backing.Id == pci.pci_id:
                    self.log.debug("%s already has PCI device %s"%(self.vm_name,pci.pci_id))
                    return
            except:
                continue
        
        request = VI.ReconfigVM_TaskRequestMsg()
        _this = request.new__this(self._vm._mor)
        _this.set_attribute_type(self._vm._mor.get_attribute_type())
        request.set_element__this(_this)
            
        spec = request.new_spec()
        dc = spec.new_deviceChange()
        dc.Operation = "add"
        hd = VI.ns0.VirtualPCIPassthrough_Def("hd").pyclass()
        hd.Key = -100
        
        backing = VI.ns0.VirtualPCIPassthroughDeviceBackingInfo_Def("backing").pyclass()
        backing.Id = pci.pci_id 
        backing.DeviceName = pci.device_name
        backing.DeviceId = pci.device_id
        backing.SystemId = self._get_pci_system_id() 
        backing.VendorId = pci.vendor_id
        
        hd.Backing = backing  
        dc.Device = hd
        spec.DeviceChange = [dc]
        request.Spec = spec
        
        task = self._s._proxy.ReconfigVM_Task(request)._returnval
        vi_task = VITask(task, self._s)
        status = vi_task.wait_for_state([vi_task.STATE_SUCCESS,
                                         vi_task.STATE_ERROR])
        if status == vi_task.STATE_SUCCESS: 
            self.log.debug("PCI device %s[%s] added to %s" % (pci.device_name, 
                                                              pci.device_id, 
                                                              self.vm_name))
        else:
            raise AttributeError("Error adding PCI device:%s"%vi_task.get_error_message())
    
    
    def add_vsa_pcis(self, add_fc=True):
        """
         High-level method that queries for and adds the appropriate
         PCI devices to the VSA guest machine.
        """
        self._get_vm()
        self.power_off()
        h = HostTool(self.get_esx_hostname(),sut=self.sut,server=self.server, username=self.username, password=self.password)
        
        
        # Query for the mellanox devices and add the virtual function devices        
        nics = h.get_mellanox_devices()
        for nic in nics:
            if nic.device_id == MELLANOX_VF_PT_ID:
                self.add_pci(nic)
        
        ssds = h.get_ssd_devices()                                                 
        for ssd in ssds:
            self.add_pci(ssd)
        if add_fc:
            for fc in h.get_fc_adapters():
                self.add_pci(fc)
        del h
    
    
    def get_file_contents(self, remote_path, timeout=5):
        """
         Downloads a file from the VM, reads the contents and
         returns a list of the file contents.
        """
        self._get_vm()
        
        name = tempfile.mktemp()
        i = 0
        while i < timeout: 
            try:
                self._vm.get_file('/tmp/ifconfig.stdout', name)
                break
            except Exception:
                time.sleep(1)
            i+=1
        _file = open(name)
        lines = _file.readlines()
        _file.close()
        os.remove(name)
        return lines

    
    def netif_up(self, eth):
        """ 
         Brings an interface up.
        """
        cmd = "ifup %s"%eth
        self.run_shell(cmd)
        
    
    def netif_down(self, eth):
        """ 
         Brings an interface down.
        """
        cmd = "ifdown %s"%eth
        self.run_shell(cmd)
    
            
    def enable_netif(self, nic, ip, mask):
        """
         Enables a static network interface on the VM.
         
         :param nic: The name of the adapter on the machine (eth0).
         :param iP: The IP address we're assigning to the NIC.
         :param mask: Network mask that will be assigned to the NIC.
        """
        cmd = "echo -e \""
        cmd +="DEVICE=%s\\n" % nic
        cmd +="BOOTPROTO=static\\n"
        cmd +="ONBOOT=yes\\n" 
        cmd +="TYPE=Ethernet\\n"
        cmd +="IPADDR=%s\\n"%ip 
        cmd +="NETMASK=%s"%mask
        cmd +="\" > /etc/sysconfig/network-scripts/ifcfg-%s"%nic
        
        self.log.debug("Enabling the NIC...\n%s"%cmd)
        self.run_shell(cmd) 
        
        self.netif_down(nic)
        self.netif_up(nic)
        
    
    def enable_cache_netif(self, cache_ip, mask, num_iser):
        """
         A VSA-specific method that configures and enables the
         network interfaces associated with the mellanox cards 
         for the cache network.
         
         :param cache_ip: The network address for the cache network.
         :param mask: Cache network mask.
         :param num_iser: The number of ISER switches (mellanox cards). 
        """
        BOND0 = 'bond0'
        SLAVE_NETIFS=['eth3','eth4','eth5','eth6']
        
        def _config_slave_netif(eth):
            """
             Writes out the ifcfg file for the slave netifs.
            """
            cmd = "echo -e \""
            cmd +="DEVICE=%s\\n" % eth
            cmd +="BOOTPROTO=none\\n"
            cmd +="ONBOOT=yes\\n" 
            cmd +="NM_CONTROLLED=yes\\n"
            cmd +="SLAVE=yes\\n" 
            cmd +="MASTER=bond0\\n"
            cmd +="\" > /etc/sysconfig/network-scripts/ifcfg-%s"%eth
            self.run_shell(cmd)

        # Write out the bond0 netif
        cmd = "echo -e \""
        cmd+= "DEVICE=bond0\\n"
        cmd+= "BOOTPROTO=static\\n"
        cmd+= "ONBOOT=yes\\n"
        cmd+= "IPADDR=%s\\n"%cache_ip
        cmd+= "NETMASK=%s\\n"%mask
        cmd+= "NAME=bond0\\n"
        cmd+= "BONDING_OPTS=\"mode=1 fail_over_mac=1 miimon=100 downdelay=300 updelay=300\"\\n"
        cmd +="\" > /etc/sysconfig/network-scripts/ifcfg-%s"%BOND0
        self.run_shell(cmd)
        
        # configure the slave netifs and take them down        
        for i in range(num_iser):
            _eth = SLAVE_NETIFS[i]
            _config_slave_netif(_eth)
            self.netif_down(_eth)
  
        # bring bond0 netif up
        self.netif_up(BOND0)
          
        # bring the slave netifs up
        for i in range(num_iser):
            _eth = SLAVE_NETIFS[i]
            self.netif_up(_eth)
        
    
    def get_esx_hostname(self):
        """
         Returns this VM's ESX host name.
        """
        self._get_vm()
        return self._vm.properties.runtime.host.name


    def get_esx_ip(self):
        """
         Returns this VM's ESX host IP.
        """
        self._get_vm()
        return self._vm.properties.runtime.host.config.network.vnic[0].spec.ip.ipAddress


    def power_on(self, wait_for_tools=True):
        """
         Starts the virtual machine
        """
        self._get_vm()
        if self._vm.get_status() == VMPowerState.POWERED_ON:
            return
        self._vm.power_on()
        self._vm.properties._flush_cache()
        if wait_for_tools == True:
            self._vm.wait_for_tools(timeout=VM_TOOLS_TIMEOUT) 
        
        #there still seems to be a need for a few seconds 
        time.sleep(5)
        self.log.debug("%s has been powered on."%self.vm_name)

    
    def power_off(self):
        """
         Stops the virtual machine
        """
        self._get_vm()
        if self._vm.get_status() == VMPowerState.POWERED_OFF:
            return
        self._vm.power_off()
        self.log.debug("%s has been powered off."%self.vm_name)
        
    
    def delete(self):
        """
         Unregisters the VM from host and removes the guest VM 
         from the host disk (equivalent to 'Delete From Disk'). 
        """
        self._get_vm()
        
        self.power_off()
        # delete the vm from disk 
        request = VI.Destroy_TaskRequestMsg() 
        _this = request.new__this(self._vm._mor) 
        _this.set_attribute_type(self._vm._mor.get_attribute_type()) 
        request.set_element__this(_this) 
        ret = self._s._proxy.Destroy_Task(request)._returnval 

        task = VITask(ret, self._s) 
        
        status = task.wait_for_state([task.STATE_SUCCESS, task.STATE_ERROR]) 
        if status == task.STATE_ERROR: 
            raise TypeError("Error removing vm:", task.get_error_message()) 
        self.log.debug("%s has been deleted."%self.vm_name)


    def migrate(self, target_host, priority='high'):
        """
         Migrates (vMotion) the VM to another host.
         
         :param target_host: The ESX host (host_mor) where we want to migrate the VM.
         :param priority: Task priority of the migration request.
        """
        self._get_vm()
        if not target_host:
            raise AttributeError("Migrating a VM requires a target_host.")
        
        # lookup the target_host's MOR if its not a MOR ID
        if VIMor.is_mor(target_host) == False:
            target_host = [k for k,v in self._s.get_hosts().items() if v==target_host][0]
        
        self._vm.migrate(host=target_host)


    def relocate(self, target_host, datastore, priority='default'):
        """
         relocate(self, sync_run=True, priority='default', datastore=None, 
                 resource_pool=None, host=None, transform=None):
         :param target_host: The ESX host (host_mor) where we want to migrate the VM.
         :param datastore: The datastore MOR where the VM disks will be located.
         :param priority: Task priority of the migration request.
        """
        self._get_vm()
        if not target_host:
            raise AttributeError("Relocating a VM requires a target_host.")
        if not datastore:
            raise AttributeError("Relocating a VM requires a datastore")
        
        if VIMor.is_mor(target_host) == False:
            target_host = [k for k,v in self._s.get_hosts().items() if v==target_host][0]
        if VIMor.is_mor(datastore) == False:
            datastore = self.get_datastore_mor(datastore)
        
        self._vm.relocate(host=target_host, datastore=datastore)
    
    
    def clone(self, target_host, datastore, new_vm_name):
        """
         Clones the virtual machine to the target host and datastore.
         
         :param target_host: The ESX host (host_mor) where we want to migrate the VM.
         :param datastore: The datastore MOR where the VM disks will be located.
         :param new_vm_name: The name of the new VM to be created.
        """
        self._get_vm()
        if not target_host:
            raise AttributeError("Cloning a VM requires parameter: target_host.")
        if not datastore:
            raise AttributeError("Cloning a VM requires parameter: datastore.")
        if not datastore:
            raise AttributeError("Cloning a VM requires parameter: new_vm_name.")
        
        #Lookup the target ESX host's Resource Pool because it may not be the same
        #as the source VM's resource pool (unless it's the same cluster, it wont be). 
        rp = self._find_resource_pool(target_host)
        
        if VIMor.is_mor(target_host) == False:
            target_host = [k for k,v in self._s.get_hosts().items() if v==target_host][0]
        if VIMor.is_mor(datastore) == False:
            datastore = self.get_datastore_mor(datastore)
        
        self.log.debug("Beginning clone for %s..."%new_vm_name)
        self._vm.clone(new_vm_name,host=target_host,datastore=datastore,resourcepool=rp,power_on=False)
        

    def run_shell(self, cmd, cwd=None):
        """
         Runs the shell cmd on the virtual machine in a synchronous fashion
        """
        self._get_vm()
        self._do_authentication()
        
        # PySphere expects the args to be in a list so
        # it can use list2cmdline to escape most characters.
        #TODO: prefix commands to windows guests
        _bin = "/bin/bash"
        _cmd = ['-c']
        _cmd.append(cmd)
        self.log.debug("Executing on %s:%s"%(self.vm_name,_cmd))
        self._pid = self._vm.start_process(_bin,_cmd,cwd=cwd)
        
        while True:
            procs = self._vm.list_processes()
            for proc in procs:
                if proc['pid'] == self._pid:
                    if proc['exit_code'] == None:
                        time.sleep(2)
                        continue
                    elif proc['exit_code'] == 0:
                        return
                    else:
                        raise TypeError("Shell command failed:%s"%cmd)
    
    
    def start_shell(self, cmd, cwd=None):
        """
         Starts a shell process asynchronously and returns the PID.
        """
        self._get_vm()
        self._do_authentication()
        _bin = "/bin/bash"
        _cmd = ['-c']
        _cmd.append(cmd)
        self.log.debug("Starting [%s] on %s"%(_cmd,self.vm_name))
        return self._vm.start_process(_bin,_cmd,cwd=cwd)
    
    
    def kill_shell(self):
        """
         Kills the shell process that may be running on the guest.
        """
        self._get_vm()
        self._do_authentication()
        if self._pid:
            self._vm.terminate_process(self._pid)


    def run_build_tools(self):
        BUILD_TOOLS_SCRIPT_URL = "url"
        self.log.debug("Running %s"%BUILD_TOOLS_SCRIPT_URL)
        script = BUILD_TOOLS_SCRIPT_URL.split('/')[-1]
        self._get_vm()
        self._do_authentication()
        
        ps_cmd = "wget %s; chmod +x ./%s; ./%s" % (BUILD_TOOLS_SCRIPT_URL,script,script)
        self.run_shell(ps_cmd)
    
       
    def upgrade_vm_tools(self, tools_location=None):
        """
         Upgrades the VM Tools on the guest VM to latest version.
         This does not install Vm Tools if they are missing.
         
         TODO pass the tools location into the params.
        """ 
        self._get_vm()
        
        self.log.debug("Upgrading VM Tools...")
        self._vm.upgrade_tools()
        self.log.debug("Upgrading VM Tools complete.")
    
    
    def add_remove_cdrom(self, operation):
        """
         Adds/removes a CD/DVD drive to the guest machine.
         
         :param opereation: Either 'add' or 'remove'
         
         Note that this does not handle the power manipulation of the 
         guest machine and that attempting to add/remove the drive 
         with the guest down or the drive mounted may result in errors.
        """
        self._get_vm()
        
        operation= lower(operation)
        if operation != 'add' and operation != 'remove':
            raise TypeError("Parameter operation needs to be 'add' or 'remove'.")
        
        request = VI.ReconfigVM_TaskRequestMsg()
        _this = request.new__this(self._vm._mor)
        _this.set_attribute_type(self._vm._mor.get_attribute_type())
        request.set_element__this(_this)
        
        # start forming our add/remove request with correct operation
        spec = request.new_spec()
        dc = spec.new_deviceChange()
        dc.Operation = operation
        
        hd = VI.ns0.VirtualCdrom_Def("hd").pyclass()
        hd.ControllerKey = 200
        hd.Key = 3000
        hd.UnitNumber = 0
        
        if operation =='add':
            backing = VI.ns0.VirtualCdromRemotePassthroughBackingInfo_Def("backing").pyclass()
            backing.DeviceName = ""
            backing.Exclusive = False
            backing.UseAutoDetect = True
            hd.Backing = backing
        
        dc.Device = hd
        spec.DeviceChange = [dc]
        request.Spec = spec
        
        task = self._s._proxy.ReconfigVM_Task(request)._returnval
        vi_task = VITask(task, self._s)
        
        status = vi_task.wait_for_state([vi_task.STATE_SUCCESS,
                                         vi_task.STATE_ERROR])
        if status == vi_task.STATE_ERROR:
            raise AttributeError("Failed to %s CDROM to guest: %s"%(operation,
                                                                    vi_task.get_error_message()))
    
    
    def remove_all_virtual_disks(self):
        """
         Removes all virtual disks from the VM except the first
         disk which is assumed to the system disk for the VM.
         
         TODO: Need a better way to identify the AE2-created disks.
        """
        self._get_vm()
        
        disks = self._vm._disks
        if len(disks) <= 1:
            return
        self.log.debug("Found %s disks to remove."%(len(disks)-1))
        for disk in disks[1:]: 
            self.remove_virtual_disk(disk['device']['key'])
        
    
    def remove_virtual_disk(self, key):
        """
         Removes a new virtual disk from the VM. 
         If the operation fails an error is raised.
         
         :param key: The Device Key for the device.
        """
        self._get_vm()
        self.log.debug("Removing virtual disks with key: %s"%key)
        request = VI.ReconfigVM_TaskRequestMsg()
        _this = request.new__this(self._vm._mor)
        _this.set_attribute_type(self._vm._mor.get_attribute_type())
        request.set_element__this(_this)
            
        spec = request.new_spec()
        dc = spec.new_deviceChange()
        dc.Operation = "remove"
        
        hd = VI.ns0.VirtualDisk_Def("hd").pyclass()
        hd.Key = key
        hd.CapacityInKB = 1       #required but value doesn't seem to matter
        dc.Device = hd
        
        spec.DeviceChange = [dc]
        request.Spec = spec
        
        task = self._s._proxy.ReconfigVM_Task(request)._returnval
        vi_task = VITask(task, self._s)
        
        status = vi_task.wait_for_state([vi_task.STATE_SUCCESS,
                                         vi_task.STATE_ERROR])
        if status == vi_task.STATE_ERROR:
            raise AttributeError("Failed to remove virtual disk %s"%vi_task.get_error_message())
    

    def create_virtual_disk(self, datastore_name, size, thin=True):
        """
         Creates (adds) a new virtual disk to the VM. 
         If the operation fails an error is raised.
         
         :param datastore_name: Canonical (human friendly) name of datastore
         :param size: Size of disk in MB.
         :param thin: Boolean of whether the disk is thin provisioned.
        """
        #
        # There's a bug (I think its intentional undocumented misbehavior) where we
        # cannot label the hardware devices during creation. One workaround offered
        # was to reconfigure the device after it had been created and added to the VM
        # where we could give it the desired label and summary. But even that doesn't work.
        #
        # The request complies with the vim API...No errors raised... 
        # vCenter silently ignores the request and makes me sad.
        #
        def _label_disk():
            _disk = self._vm.properties.config.hardware.device[-1]._obj
            
            _disk.DeviceInfo.set_element_label("Gatekeeper")
            _disk.DeviceInfo.set_element_summary("Keymaster")
            request = VI.ReconfigVM_TaskRequestMsg()
            _this = request.new__this(self._vm._mor)
            _this.set_attribute_type(self._vm._mor.get_attribute_type())
            request.set_element__this(_this)
            spec = request.new_spec()
            dev_change = spec.new_deviceChange()
            dev_change.set_element_device(_disk)
            dev_change.set_element_operation("edit")
            spec.set_element_deviceChange([dev_change])
            request.set_element_spec(spec)
            ret = self._s._proxy.ReconfigVM_Task(request)._returnval
    
            task = VITask(ret, self._s)
            status = task.wait_for_state([task.STATE_SUCCESS,
                                          task.STATE_ERROR])
            if status == task.STATE_ERROR:
                raise AttributeError("Failed to add virtual disk %s"%task.get_error_message())
        self._get_vm()
        
        request = VI.ReconfigVM_TaskRequestMsg()
        _this = request.new__this(self._vm._mor)
        _this.set_attribute_type(self._vm._mor.get_attribute_type())
        request.set_element__this(_this)
            
        spec = request.new_spec()
        
        dc = spec.new_deviceChange()
        dc.Operation = "add"
        dc.FileOperation = "create"
        
        hd = VI.ns0.VirtualDisk_Def("hd").pyclass()
        
        hd.Key = -100
        hd.UnitNumber = len(self._vm._disks)    # places the new disk next
        hd.CapacityInKB = int(size) * 1024
        hd.ControllerKey = 1000
        
        backing = VI.ns0.VirtualDiskFlatVer2BackingInfo_Def("backing").pyclass()
        backing.FileName = "[%s]" % datastore_name
        backing.DiskMode = "persistent"
        backing.Split = False
        backing.WriteThrough = False
        backing.ThinProvisioned = thin
        backing.EagerlyScrub = False
        hd.Backing = backing
        dc.Device = hd
        
        spec.DeviceChange = [dc]
        request.Spec = spec
        
        task = self._s._proxy.ReconfigVM_Task(request)._returnval
        vi_task = VITask(task, self._s)
        
        status = vi_task.wait_for_state([vi_task.STATE_SUCCESS,
                                         vi_task.STATE_ERROR])
        if status == vi_task.STATE_ERROR:
            raise AttributeError("Failed to add virtual disk %s"%vi_task.get_error_message())
        
        # Tag the disk with prefix so we can look it up later.
        #_label_disk()  

        
    def copy_file(self, src, dest, overwrite=True):
        """
         Copies a directory to the virtual machine.
         
         :param src: The source filepath (on the driver)
         :param dest: The destination path on the virtual machine.
         :param overwrite: Overwrite existing files on target.
        """    
        self._get_vm()
        self._do_authentication()
        self.log.debug("Sending file [%s] to [%s]"%(src, dest))
        self._vm.send_file(src,dest, overwrite)
        
    
    def remove_directory(self, path):
        """
         Removes a directory on the VM. This does not raise
         an error if the directory to be removed does not exist.
        """
        self._get_vm()
        self._do_authentication()
        self.log.debug("Removing [%s] on [%s]"%(path, self.vm_name))
        try:
            self._vm.delete_directory(path, True)
        except VimError, ex:
            self.log.debug("Ex:%s"%ex)
        
    
    def wait_for_shell(self):
        """
         Waits for the VM's GuestOperations agent to be 
         ready to accept requests to invoke shell commands.
        """
        while True:
            try:
                self._get_vm()
                self._do_authentication()
            except ValueError, ex:
                self.log.debug("Failed to Authenticate to Client Agent.")
                self.log.debug("The error:%s"%ex)
                time.sleep(5)
                continue
            try:
                self.run_shell('echo yolo')
                return
            except VimError, ex:
                self.log.debug("Failed to run_shell: %s"%ex)
                time.sleep(5)            
        
        
def deploy_new_ova(vsphere,ova_url,vsa_name,host,mac,network=None,username=None,password=None):
    """
     Deploys a VSA from URL to an ESX host, configures the VSA and prepares
     it for testing tasks.
     This method is suitable when the ESX host already has been configured to
     host a VSA.
     
    REQUIRED PARAMETERS
    :param vsphere: The vSphere server managing the host configuration
    :param ova_url: Some HTTP location where a pre-built OVA lives
    :param vsa_name: The name of the guest machine (VSA)
    :param host: The ESX host where the VSA will be deployed
    :param mac: MAC address of the guest machine
    
    OPTIONAL PARAMETERS
    :param network: Guest machine network configuration defaults 'OVF Network Name'.
    :param username: vSphere server username (defaults to Administrator)
    :param password: vSphere server password (defaults to lab standard)
    """
    
    
    # remove the old VSA if one exists on the host
    h = HostTool(host, server=vsphere, username=username,password=password)
    if h.is_vm_on_host(vsa_name) == True:
        t = VmTool(vsa_name,server=vsphere, username=username,password=password)
        t.delete()
        del t

    o = OvaTool(server=vsphere, username=username,password=password)
    o.download_ova(ova_url) 
    o.deploy_ovf(host, vsa_name)
    
    t = VmTool(vsa_name,server=vsphere, username=username,password=password)
    
    # map the PCI devices (micron and mellanox) to the guest
    
    t.set_mac(mac)
    t.power_on()
    time.sleep(15) # TODO: Find a way to query for idle (power state isn't accurate)
    t.run_post_ks()



def lookup_mac(hostname):
    
    DHCP_CONF = 'url'
    lines = []
    try:
        request = urllib2.urlopen(DHCP_CONF)
        lines = request.readlines()
    except:
        raise AttributeError("Failed to read %s"%DHCP_CONF)
    
    hostname = hostname.split('.')[0]
    for i in range(len(lines)):
        if len(lines[i].split())>2 and lines[i].split()[1] == hostname:
            return str(lines[i+1].split()[2]).rstrip(';')
    raise AttributeError("Failed to find MAC for %s"%hostname)


if __name__ == '__main__':
    
    print "Starting"
    vsphere = "hostname"
    ova = "url"
    host = "hostname"
    #vm_name = "vm"
    vm_name = "vm"
    guest_hostname = "powervm1"

    h = HostTool(host, server=vsphere, username='username')
    #print h.get_datastore_size(wwn="6000d31000f02d00000000000001531")
    print h.get_datastore_size(wwn="6000D31000F02D000000000000001531")
    
    #print h.get_datastore_size(wwn="6000d31000f02d000000000080001536")
    
    #foo = h.get_storage_adapters()
    #print h.get_iscsi_software_adapter()
    
    #h.add_target_to_iscsi_swadapter("ipaddr")
    
    #h.get_mellanox_devices()
    #h.unbind_iser_hbas()
    #h.get_vswitches()
    #h.bind_vnic("vmhba458752", "vmk1")
    #h.unbind_vnic("vmhba458752", "vmk1")
    #h.create_datastore("foo", "6000d31000eeb9000000000000000087", False)
    
    
    #print "adapters %s" % adpt
    #h.get_mellanox_devices()
    #h.configure_vsa_passthru()
    #vm = VmTool(vm_name, server=vsphere, username='root')
    #vm.create_virtual_disk('ds1_atl4', 1024, True)
    
    #disks = vm._vm._disks
    #print "We found [%s] disks"%len(disks)
    
    #cip = "172.18.3.2"
    #mask = "255.255.248.0."
    #t.enable_cache_netif(cip, mask, 1)
    
    print "done!"
    sys.exit()


    usage = """
    
USAGE: $python vimer.py [-d][-o][-t] <vSphere server> <ESX_host_1:vsa_name, host_2:vsa_name, ...>

    Options:
    -d        : Deletes the pre-existing VSA's if they exist on the host.
    -o        : The OVA URL we want to deploy. Defaults to latest build.
    -t        : Perform extra tool installation after deployment. Includes 
                Python, test tools, AE2 dependencies, etc.
                
"""
    
            
    from optparse import OptionParser
    
    PREP_SCRIPT_URL = "url"
    LATEST_OVA = "url"
    
    ova_url = LATEST_OVA
    install_tools =False
    delete_vsa = False
    
    
    if len(sys.argv) < 3:
        print usage
        sys.exit(1)
    
    parser = OptionParser()
    parser.add_option("-d", "--delete_vsa", 
                      default=False,
                      action="store_true", 
                      dest="delete_vsa") 
    parser.add_option("-o", "--ova_url", 
                      type="string", 
                      default=LATEST_OVA,
                      action="store", 
                      dest="ova_url")
    parser.add_option("-t", "--install_tools", 
                      default=False,
                      action="store_true", 
                      dest="install_tools")    
    
    vsphere = sys.argv[1]
    
    esx_vsas = {}
    for entry in sys.argv[2].split(','):
        host = str(entry.split(':')[0])
        if host.find('.')==-1:
            host = "%s.hostname.com"%host
        esx_vsas.update({host:entry.split(':')[1]})
    
    # setup a simple local logger to stdout and a file (vimer.log)   
    my_logger = logging.getLogger('vimer')
    my_logger.setLevel(logging.DEBUG)
    filehandler = logging.FileHandler(filename=os.path.join(os.getcwd(),'vimer.log'))
    conhandler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s %(levelname)s  %(message)s")
    msg_only = logging.Formatter("%(message)s")
    filehandler.setFormatter(formatter)
    conhandler.setFormatter(msg_only)
    #conhandler.setLevel(logging.INFO)
    my_logger.addHandler(filehandler)
    my_logger.addHandler(conhandler)
       
    o = OvaTool(server=vsphere, username='root')
    my_logger.info("Downloading %s"%ova_url)
    o.download_ova(ova_url)
        
        
    if delete_vsa==True:
        for host,vsa in esx_vsas.items():
            print host
            print vsa
            h = HostTool(host, server=vsphere, username='Administrator')
            vm_name = "FluidCache_VSA_%s_%s"%(host,vsa)
            if h.is_vm_on_host(vm_name) == True:
                my_logger.info("Deleting VM %s"%vm_name)
                t = VmTool(vm_name, server=vsphere, username='Administrator')
                t.delete()
                del t
            else:
                my_logger.info("Did not find VSA to delete %s"%vm_name)
            del h
    
    
    for host,vsa in esx_vsas.items():
        vm_name = "FluidCache_VSA_%s_%s"%(host,vsa)
        my_logger.info("Deploying OVA to %s"%host)
        #o.deploy_ovf(host, vm_name)
    
        #configure the guest (mac and pci devs)
        t = VmTool(vm_name,server=vsphere, username='root')
        t.set_mac(lookup_mac(host))
        t.add_vsa_pcis()
        my_logger.info("Powering on %s"%vsa)
        t.power_on()
        
        # removes the old host keys from the driver
        #rm = test_procedures.sys_ops.os_util.RemoveKnownHostKeys(self.sut,self.suite_config)
        
        if install_tools == True:
            my_logger.info("Installing tools...")
            t.run_shell("yum -qy install zlib-devel")
            t.run_shell("yum -qy install openssl-devel")
            t.run_shell("yum -qy install python-devel")
            t.run_shell("yum -qy install libaio-devel")
            t.run_post_ks()
            t.run_shell("yum -qy install libxml2-devel")
            t.run_shell("yum -qy install libxslt-devel")
            t.run_shell("yum -qy install rsync")
            t.run_shell("yum -qy install ntpdate")

    exit(0)
    """    

    print "Starting to clone..."
    
    VSPHERE="vsphere1.hostname.com"
    VM = "qavm52"
    
    #         (     ESX host,                 datastore,      VM name),
    targets = [
               ("sea5.hostname.com", "password", "host"),
              ]
               
    source_vm = VmTool(VM, server=VSPHERE, username="username", password="password")
    i = 1
    for target_host, datastore, new_vm_name in targets:
        print "%s Cloning to %s %s %s" % (i, target_host, datastore, new_vm_name)
        source_vm.clone(target_host, datastore, new_vm_name)
        
        print "    Setting the MAC address for %s" % new_vm_name
        try:
            _macaddy = lookup_mac(new_vm_name)
            _temp = VmTool(new_vm_name, server=VSPHERE, username="username", password="password")
            _temp.set_mac(_macaddy)
            _temp.power_on(wait_for_tools=False)
            print "    Powererd on."
            del _temp
        except AttributeError:
                print "!!! Failed to find MAC address for %s"%new_vm_name
        i+=1
        
    print "All done."
"""
        
        
        
