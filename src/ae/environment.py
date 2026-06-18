#!usr/bin/python
"""
This module provides a set of objects which are built after 
reading in config data (YAML). These objects will be passed to
out test case/procedures so as to provide a way for them to 
easily get the information.   
"""
import os
import sys
from time import sleep
import ae_errors
import logging
import lib

try:
    import yaml
except ImportError:
    pass


class OS_TYPE:
    WINDOWS = "WINDOWS"
    LINUX = "LINUX"

class OS_NAME:
    UNSPECIFIED     = "UNSPECIFIED"
    CENT64          = "CENT64"
    RHEL63          = "RHEL63"
    RHEL64          = "RHEL64"
    SLES11SP2       = "SLES11SP2"
    WS2012          = "WS2012"      

class NodeOs():
    """
     Container class for OS definitions and deployment methods
    """
    def __init__(self,os_name,full_name,os_type,deploy_source,post_deploy):
        self.os_name = os_name
        self.full_name = full_name
        self.os_type = os_type
        self.deploy_source = deploy_source
        self.post_deploy=post_deploy
    
    def __str__(self):
        ret = "%s\n"%self.os_name
        ret+="OS Type: %s\n"%self.os_type
        return ret
    def __repr__(self):
        return self.os_type
    
    def __eq__(self, other):
        if other == None:
            return False
        return self.os_name == str(other)
    
    def __neq__(self,other):
        return not self.__eq__(other)
    

# static list of our 'supported' OS object definitions
OS_LIST = [
           NodeOs(OS_NAME.UNSPECIFIED,
                  "OS not specified",
                  OS_TYPE.LINUX,
                  "NA",
                  "NA"
                  ),
           NodeOs(OS_NAME.RHEL64,
                  "RHEL 6.4 x86_64",
                  OS_TYPE.LINUX,
                  "ks number 1",
                  "http://something_post_ks.sh"
                  ),
           NodeOs(OS_NAME.CENT64,
                  "CENTOS 6.4 x86_64",
                  OS_TYPE.LINUX,
                  "ks number 1",
                  "http://something_post_ks.sh"
                  ),
           NodeOs(OS_NAME.WS2012,
                  "Microsoft Server 2012",
                  OS_TYPE.WINDOWS,
                  "NA",
                  "NA"
                  ),
          ]
          

class NODE_ROLES:
    """
     Enumerate the node roles
    """
    CLIENT = "CLIENT"          # client (like a NFS client) role
    MD     = "MD"              # metadata server role
    CS     = "CS"              # cacheserver role
    BC     = "BC"              # block client role
    CFM    = "CFM"             # cfm role
    VSA    = "VSA"             # VSA
    
    @staticmethod    
    def get_fldc_roles():
        """
         Returns a list of FLDC roles
        """
        return[NODE_ROLES.MD,NODE_ROLES.CS,NODE_ROLES.BC,NODE_ROLES.CFM,NODE_ROLES.VSA]


class San:
    """
     Container class for our san object.
    """
    def __init__(self):
        self.ip     = None  # IP address of the SAN (or simulator)
        self.port   = None  # port of the SAN port
        self.id     = None  # SAN ID
        self.name   = None  # SAN name
        self.type   = None  # SAN type (CML or EQL)
        self.status = None  # SAN status (active or inactive (i think))
        self.vds    = []    # list of SAN VD objects
    
    def __str__(self):
        ret = "SAN\n ip:%s\n port:%s\n id:%s\n name:%s\n type:%s\n status:%s"%(
                                                                    self.ip,
                                                                    self.port,
                                                                    self.id,
                                                                    self.name,
                                                                    self.type,
                                                                    self.status)
        ret += "\n VDS:"
        for vd in self.vds:
            ret += "\n   volume_id:%s\n   wwn:%s"%(vd.volume_id,vd.wwn)
            
        return ret
    
    def get_vd(self, vd_id):
        """ 
         Returns the VD object based on the vd_id (volume id) given
        """
        for vd in self.vds:
            if vd.volume_id == vd_id:
                return vd
        return None
    
        
class Vd:
    """ Container class for VD objects
    """
    def __init__(self, volume_id, uid, wwn, wwn_alias, iqn, serial):
        self.volume_id = volume_id       # some volume ID string
        self.uid = uid                   # UUID - DEPRECATED
        self.wwn = wwn                   # The WWN of the device
        self.wwn_alias = wwn_alias       # the WWN alias of the device
        self.iqn = iqn                   # a list of IQN's if specified
        self.serial = serial             # some serial number string
        
        if uid == None and wwn != None:
            self.uid = wwn
        elif wwn == None and uid != None:
            self.wwn = uid
        if wwn_alias == None:
            self.wwn_alias = self.wwn
        if isinstance(iqn, str):
            self.iqn = [iqn]
        

    def __str__(self):
        return " volume_id:%s\n iqns:%s\n serial:%s  \n wwn:      %s\n wwn_alias:%s"%(
                                                                            self.volume_id,
                                                                            self.iqn,
                                                                            self.serial,
                                                                            self.wwn,
                                                                            self.wwn_alias
                                                                            )
    def __repr__(self):
        return self.__str__()


class Switch:
    """
     Container class for a network or SAN switch. This class
     will be used in context of a node.
    """ 
    def __init__(self, hostname, ip, vendor, username, password, ports):
        self.hostname = hostname
        self.ip = ip
        self.vendor = vendor
        self.username = username
        self.password = password
        self.ports = ports              # list of ports
        
    
    def __str__(self):
        return " Switch hostname:%s\n ip:%s\n vendor:%s\n username:%s\n password:xxxxxx\n ports:%s\n"%(
                                                                                 self.hostname,
                                                                                 self.ip,
                                                                                 self.vendor,
                                                                                 self.username,
                                                                                 self.ports)
    def __repr__(self):
        return self.__str__()

class Node:
    """ An object to represent a node in the environment
    
    Container class to store node-specific information
    pertaining to the test nodes.
    
    **Node attributes**
    
    * :py:attr:`name` - Hostname
    * :py:attr:`cache_devices` - List of cache device WWNs
    
    **Example**::
    
        for cd_wwn in cs_node.cache_devices:
            pass
    
    """
    def __init__(self, hostname, valid_roles=[]):
        self.name               = hostname
        self.os                 = None          # OS object of the node
        self.ip                 = None          # public IP (may double as management IP) address
        self.mgmt_ip            = None          # specific mgmt IP address
        self.ip_mask            = None          # mgmt IP netmask
        self.mac                = None          # public MAC address of our node
        self.cache_ips          = []            # private  IP (cache IP) addresses
        self.iscsi_ips          = []            # private addresses for the iscsi network
        self.iscsi_san_ip       = None          # IP address of the ISCSI storage
        self.roles              = valid_roles   # list of potential node roles
        self.cache_devices      = []            # list of potential cache devices
        self.san_ip             = None          # IP address of the SAN
        self.san_port           = None          # port of SAN
        self.vds                = []            # list of virtual disks
        self.san_switches       = []            # list of SAN switches and ports for this node
        self.net_switches       = []            # list of network switches and ports
        self.power_switch       = None          # bus power switch
        self.drac               = None          # drac IP
        self.esx_host           = None          # VSA's ESX host
        self.vm_name            = None          # VM name of the VSA
        self.username           = None          # specific user for the node
        self.password           = None          # password associated with username


    def __str__(self):
        return self.name
    
    def __repr__(self):
        return self.name

    def __key(self):
        return (self.name, self.ip)
    
    def __eq__(self, other):
        if not isinstance(other, Node):
            return False
        return self.__key() == other.__key()
    
    def __ne__(self, other):
        return not self.__eq__(other)    
    
    def __hash__(self):
        return hash(self.__key())

    def get_info(self):
        """
         Returns a string representation of the node members
         which can be used to print or log useful node info.
        """
        ret = "Node: %s\n"%self.name
        ret+= "IP: %s\n"%self.ip
        if self.mgmt_ip:
            ret+= "MGMT_IP: %s\n"%self.mgmt_ip
        ret+= "IP_MASK: %s\n"%self.ip_mask
        ret+= "OS: %s\n"%self.os
        ret+= "MAC: %s\n"%self.mac
        ret+= "CACHE_IPS: %s\n"%self.cache_ips
        ret+= "ISCSI_IPS: %s\n"%self.iscsi_ips
        ret+= "Roles: %s\n"%self.roles
        ret+= "Cache Devices: %s\n"%self.cache_devices
        ret+= "SAN IP: %s\n"%self.san_ip
        ret+= "SAN PORT: %s\n"%self.san_port
        ret+= "S:\n"
        for vd in self.vds:
            ret += repr(vd)
            ret +="\n"
        for san_sw in self.san_switches:
            ret += "SAN%s"%str(san_sw)
        for net_sw in self.net_switches:
            ret += "Network%s"%str(net_sw)
        if self.power_switch:
            ret += "Power%s"%str(self.power_switch)
        if self.vm_name:
            ret+="ESX_HOST: %s\n"%self.esx_host
            ret+="VM_NAME: %s\n"%self.vm_name
        return ret
         

    def is_valid_role(self, node_role):
        """ Determine if the node is indicated to be valid for a role
        
        :param: One of the valid :py:class:`NODE_ROLES`

        :returns: True if the role is valid for this node

        **Example**::
        
            if cs_node.is_valid_role('BC'):
                pass
 
        """
        if node_role in self.roles:
            return True
        else:
            return False
    

    def is_fldc_role(self):
        """
         Dertermines if the node is serving a role which is
         a FLDC role
        """
        for fldc_role in NODE_ROLES.get_fldc_roles():
            if self.is_valid_role(fldc_role):
                return True    
        return False
    
    def is_vsa(self):
        """
         Returns whether or not the node is indicated as serving
         a VSA role.
        """
        if self.is_valid_role(NODE_ROLES.VSA):
            return True
        else:
            return False
    
        
    def get_hostname_only(self):
        """ Get only the hostname of a node

        :returns: hostname of the node

        **Example**::
        
            if cs_node.get_hostname_only() == 'jfk10':
                pass
 
        """
        return lib.string_extensions.get_host_only(str(self))
    
    
    def get_vd_volume_ids(self):
        """ Get a list of volume ID's associated with this node

        :returns: list of volume IDs

        **Example**::
        
            vd_id_list = cs_node.get_vd_volume_ids()
 
        """
        ids = []
        for vd in self.vds:
            ids.append(vd.volume_id)
        return ids
    
    
    def get_vd_uids(self):
        """ Get a list of VD UIDs associated with this node
         
         NOTE: The UID field has been deprecated in favor of 
         using WWN and IQN fields. 

        :returns: list of volume uids 

        **Example**::
        
            vd_uid_list = cs_node.get_vd_uids()
 
        """        
        uids = []
        for vd in self.vds:
            if vd.uid:
                uids.append(vd.uid)
        return uids
    

    def get_vd_wwns(self):
        """ Get a list of VD WWNs associated with this node
         
        :returns: list of volume WWNs
        
        **Example**::
        
            vd_wwn_list = cs_node.get_vd_wwns()
        """        
        wwns = []
        for vd in self.vds:
            if vd.wwn:
                wwns.append(vd.wwn)
        return wwns


    def get_vd_iqns(self):
        """ Get a list of VD IQNs associated with this node
         
        :returns: list of volume IQNs
        
        **Example**::
        
            vd_iqn_list = cs_node.get_vd_iqns()
        """        
        iqns = []
        for vd in self.vds:
            if vd.iqn:
                iqns.append(vd.iqn)
        return iqns

    
    def get_vd_serials(self):
        """ Get a list of VD Serial numbers associated with this node

        :returns: list of volume serial numbers

        **Example**::
        
            vd_serial_list = cs_node.get_vd_serials()
 
        """
        serials = []
        for vd in self.vds:
            serials.append(vd.serial)
        return serials

class Sut:
    """ 
    An object to represent the environment that contains systems under test
    Contains attributes pertaining to our Systems Under Test (SUT)
    such as cluster nodes and storage information 

    """
    def __init__(self, env_conf_file):
        self._conf_file = env_conf_file     # file path to the config file
        self.san = None                     # san object in sut
        self.nodes = []                     # list of node objects in SUT
        self._sut_dict = {}                 # root dictionary from YAML file
        self.conf_dir = ""                  # DEPRECATED where we want to put the RNA conf file
        self.build_machine = None           # DEPRECATED node(hostname) where we want to build the product
        self.build_dir = None               # DEPRECATED where the produce will be built
        self.build_src = None               # DEPRECATED location of the build
        self.ae_base_win32 = None           # absolute path to ae.py on windows
        self.ae_base_linux = None           # absolute path to ae.py on linux 
        self.pyro_ns_name = None            # hostname or IP of the Pyro nameserver
        self.pyro_ns_port = None            # port number for the Pyro nameserver
        self.log_server = None              # IP of remote log server (likely the test driver)              
        self.log_port = None                # Port to use on the log server
        self.username = None
        self.password = None
        self.log_level = None               # FLDC log level setting
        self.log_size = None                # FLDC log size setting
        self.vsphere_server = None          # managing vSphere server
        self.vsphere_username = None        # vSphere administrative username
        self.vsphere_password = None        # vSphere administrative password
        
        
    def __str__(self):
        ret = "SUT Object Information:\n"
        ret += "Domain:%s\n"%self.domain
        ret += "Username:%s\n"%self.username
        for node in self.nodes:
            ret += node.get_info()
            ret +="\n"
            
        return ret
    
    def load(self, env_conf_file=""):
        """
         Starts the process of parsing the YAML files and 
         loading the data into our config objects.
         This can also be used to re-load the config objects
         by passing in a new environment config file thereby 
         allowing rest runs to modify the environment information
         mid-run. 
        """
        
        if env_conf_file:
            self._conf_file = env_conf_file 
                    
        self._parse_config_file()
        self._set_san()
        self._set_nodes()
        self._set_ae_info()
        self._set_pyro_ns_info()
        self._set_log_server_info()
        self._set_user_info()
        self._set_log_level()
        self._set_log_size()
        self._set_vmware_info()
        
        if self.is_vsa_cluster():
            self.validate_vsa_info()

    
    def _parse_config_file(self):
        """ 
         Parses a YAML config file containing interesting data.
         Raises a AE fatal exception if an error occurs and passes
         the underlying exception along for logging/debugging.
            
         TODO: This could(?) use the static method in the loader class.
               
        """
        
        if os.path.exists(self._conf_file) == False:
            raise ae_errors.FatalError("Config file does not exist:%s"%self._conf_file)
        
        file_stream = file(self._conf_file, 'r')
        
        try:
            conf = yaml.load(file_stream)
        except (yaml.parser.ParserError, yaml.scanner.ScannerError), ex:
            msg = ("Config file is malformatted YAML:%s\n%s"%(self._conf_file,str(ex)))
            raise ae_errors.FatalError(msg)
        
        if not conf:
            raise ae_errors.FatalError("Config file dictionary is empty:%s"% self._conf_file)
        
        self._sut_dict = conf        
        

    
    def _set_san(self):
        """
         Builds our SAN object using the env dictionary
        """
        self.san = San()
        _san = {}
        try:
            _san = self._sut_dict["SAN"]
        except Exception, ex:
            print "Failed to parse the SAN information."
            print "You may need to update your environment file format(?)"
            print "Look at the example format under src/templates/environment_ex.cfg"
            raise ex
        
        self.san.ip = _san.get("IP")
        _port = _san.get("PORT")
        
        if _port == lib.constants.HCC_SIM_PORT and self.is_encrypted_flag():
            self.san.port = lib.constants.HCC_SIM_SPORT
        else:
            self.san.port = _port
        
        self.san.id = _san.get("ID","AE2_SAN_ID")
        self.san.name =_san.get("NAME","AE2_SAN_NAME")
        self.san.type = _san.get("TYPE","GEN")
        self.san.status = _san.get("STATUS","Active")
        
        # build the vd objects and append them to the san.vd list
        _vds = _san.get("VDS")
        if _vds:
            for vd in _vds:
                try:
                    _vd = Vd(vd['VD'],
                             vd.get('UID'),
                             vd.get('WWN'),
                             vd.get('WWN_ALIAS'),
                             vd.get('IQN'),
                             vd.get('SERIAL'))
                    self.san.vds.append(_vd)
                except:
                    continue
        
        
    def _set_nodes(self):
        """
         Finds the node names within our root environment dict and
         sets our hostname and other attributes for the node object
        """
        # if our dict is empty we want to parse the YAML file to get it.
        if self._sut_dict == None or len(self._sut_dict) == 0: 
            self._parse_config_file()
        
        node_list = self._sut_dict["SUT_NODES"]
        for node_dict in node_list:
            #initial a new node with our hostname and other required attributes
            node = Node(node_dict["HOSTNAME"],node_dict["VALID_ROLES"])                        
            node.ip = node_dict["IP"]
            node.mac = node_dict.get("MAC")
            
            # if it's a VSA the mgmt IP is defaulted to w.x.y.0 and ip mask 255.255.255.0
            if NODE_ROLES.VSA in node_dict.get("VALID_ROLES"):
                _ip = lib.string_extensions.edit_ip(node.ip, 3, "0")
                node.mgmt_ip = node_dict.get("MGMT_IP",_ip)
                node.ip_mask = node_dict.get("IP_MASK", "255.255.255.0")
            else:
                node.ip_mask = node_dict.get("IP_MASK", "255.255.248.0")
                node.mgmt_ip = node_dict.get("MGMT_IP",node.ip)
            
            # set our NodeOS member
            _os = node_dict.get("OS")
            if _os:
                for _o in OS_LIST:
                    if _os == _o:
                        node.os = _o
            # if the no os was set, use the default
            if node.os == None:
                node.os = OS_LIST[0]
            
            _cips = self._sut_dict.get("CACHE_IPS")
            if _cips:
                if isinstance(_cips, str):
                    node.cache_ips = [_cips]
                else:
                    node.cache_ips = []
                    for _ip in _cips:
                        node.cache_ips.append(_ip)
            _iips = self._sut_dict.get("ISCSI_IPS")
            if _iips:
                if isinstance(_iips, str):
                    node.iscsi_ips = [_iips]
                else:
                    node.iscsi_ips = []
                    for _ip in _iips:
                        node.iscsi_ips.append(_ip)
            isi = _iips = self._sut_dict.get("ISCSI_SAN_IP")
            if isi:
                node.iscsi_san_ip = isi
            
            # builds our switch objects and appends them to
            # the node's san_switch list.
            _switches = self._sut_dict.get("SWITCHES")
            if _switches:
                for _switch in _switches:
                    # find the SAN switches in the node
                    _node_ssps = node_dict.get("SAN_SWITCH_PORTS")
                    if _node_ssps:
                        for k,v in _node_ssps.items():
                            if k == _switch.get("HOSTNAME"):
                                # build the switch object
                                # append the obj to the nodes switch_list
                                _s = Switch(_switch.get("HOSTNAME"),
                                            _switch.get("IP"),
                                            _switch.get("VENDOR"),
                                            _switch.get("USERNAME"),
                                            _switch.get("PASSWORD"),
                                            v)
                                node.san_switches.append(_s)
                    # find the network switches in the node
                    _node_nsps = node_dict.get("NET_SWITCH_PORTS")
                    if _node_nsps:
                        for k,v in _node_nsps.items():
                            if k == _switch.get("HOSTNAME"):
                                # build the switch object
                                # append the obj to the nodes switch_list
                                _s = Switch(_switch.get("HOSTNAME"),
                                            _switch.get("IP"),
                                            _switch.get("VENDOR"),
                                            _switch.get("USERNAME"),
                                            _switch.get("PASSWORD"),
                                            v)
                                node.net_switches.append(_s)
                    # take care of the power switch information
                    _node_pwr_switch = node_dict.get("PWR_SWITCH_PORTS")
                    if _node_pwr_switch:
                        for k,v in _node_pwr_switch.items():
                            if k == _switch.get("HOSTNAME"):
                                    _s = Switch(_switch.get("HOSTNAME"),
                                                _switch.get("IP"),
                                                _switch.get("VENDOR"),
                                                _switch.get("USERNAME"),
                                                _switch.get("PASSWORD"),
                                                v)
                                    node.power_switch = _s
            
            # add our extra (optional) node attributes
            try:
                node.drac = node_dict["DRAC"]
                pass
            except KeyError:
                # TODO: DRYRUN: this needs to be some kind of custom exception 
                # which should probably be treated more as a warning(?). 
                pass
            
            self.nodes.append(node)
            
        
        # iterates thru our FLDC nodes and adds
        # their NVM devices to the node objects
        for node in self.get_fldc_nodes():  
            for item in node_list:
                if item["HOSTNAME"] == node.name:
                    stores = item["STORES"]
                    for store in stores:
                        node.cache_devices.append(store["NVM"]["WWN"])
                        
                    _vd_ids = item.get("VDS")
                    # do the lookup
                    if _vd_ids:
                        for id in _vd_ids:
                            try:
                                vd = self.san.get_vd(id)
                                node.vds.append(vd)
                            except:
                                continue
        
        # grab the information about the block client
        for node in self.get_nodes_by_role(NODE_ROLES.BC):
            for item in node_list:
                if item["HOSTNAME"] == node.name:
                    # here is where we do anything that is BC specific
                    pass

        for node in self.nodes:
            for item in node_list:
                if item["HOSTNAME"] == node.name:
                    node.esx_host = item.get("ESX_HOST")
                    node.vm_name = item.get("VM_NAME")
                    node.username = item.get("USERNAME")
                    node.password = item.get("PASSWORD")
        
    def get_nodes(self):
        """ Get all the nodes in the environment
        
        :returns: a list of nodes

        **Example**::
        
            cs_node = self.sut.get_nodes()
 
        """
        if len(self.nodes) <= 0:
            raise SutInfoError()
        return self.nodes


    def get_env_conf_filename(self):
        """ Returns the filepath to our environment config file
        
        :returns: path to conf file

        """
        return self._conf_file


    def get_nodes_by_role(self, node_role, only_one = False):
        """ Get a list of nodes that can perform a specific role
        
        Returns a list of nodes which have been indicated as capable
        of performing a role. If only_one is true, only the first node
        in the list will be returned.
        
        :param: One of the valid :py:class:`NODE_ROLES`
        :param only_one: If True, only the first node that matches is returned

        :returns: a list of nodes or a single node

        **Example**::
        
            cs_node = self.sut.get_nodes_by_role('CS', only_one=True)
 
        """
        node_list = []
        
        for node in self.nodes:
            if node.is_valid_role(node_role):
                if only_one == True:
                    return node
                else:
                    node_list.append(node)
        
        return node_list


    def get_all_cache_devs(self):
        """
         Returns a list of all cache device WWN's in SUT
        """
        cds = []
        for node in self.nodes:
            cds.extend(node.cache_devices)
        return cds


    def get_fldc_nodes(self):
        """
         Returns a list of nodes which are serving a FLDC role.
         That is to say that the nodes that have been specified
         in the environment file as *capable* of performing one of
         the roles associated with a FLDC role.
         
         :returns: a list of nodes serving a FLDC role
        """
        fldc_nodes = []
        
        for role in NODE_ROLES.get_fldc_roles():
            tmp = self.get_nodes_by_role(role)
            fldc_nodes.extend(tmp)
        
        return list(set(fldc_nodes))
    

    def get_current_node(self):
        """
         Gets the node where execution is taking place... eg. where
         we are currently at.
        """
        _node = self.get_node_by_hostname(lib.network.get_local_hostname()) 
        if _node == None:
            msg = "Get current node being called on a non-node machine (probably the test driver)"
            raise ae_errors.TestProcedureError(message=msg)
        return _node


    def get_node_by_hostname(self, hostname):
        """ Get the node that matches a hostname
        
         Returns the node from node list having the given hostname. 
         If no node is found having that hostname, None is returned.
        
        :param: hostname to lookup node by
        
        :returns: the matching node

        **Example**::
        
            found_node = self.sut.get_node_by_hostname('jfk10')
 
        """
        if hostname == None or len(hostname) == 0:
            return None
        
        hostname = lib.string_extensions.get_host_only(hostname)
        
        for node in self.nodes:
            if hostname.lower() == node.get_hostname_only().lower():
                return node
        return None
    
    
    def get_node_by_vmname(self, vm_name):
        """
         Gets the node whos virtual machine name matches vm_name.
         
         :param vm_name: The name of the virtual machine node we're seeking.
         :returns: The node object of the found machine.
        """
        if vm_name == None or len(vm_name) == 0:
            return None
        
        for node in self.nodes:
            if vm_name.lower() == node.vm_name.lower():
                return node
        return None


    def get_node_by_ip(self, ip):
        """ Get the node that matches an IP address
        
         Returns the node from node list having the given IP address. 
         If no node is found having that IP address, None is returned.
        
        :param: IP address to lookup node by
        
        :returns: the matching node

        **Example**::
        
            found_node = self.sut.get_node_by_ip('172.18.1.42')
 
        """
        if ip == None or len(ip) == 0:
            return None
        
        for node in self.nodes:
            if ip == node.ip:
                return node
        return None


    def get_vsa_nodes(self):
        """
         Returns a list of VSA nodes in the SUT object
        """
        return self.get_nodes_by_role(NODE_ROLES.VSA)


    def get_esx_hosts(self):
        """
         Returns a list of the ESX hosts that are specified for a VSA cluster.
        """
        
        ret = []
        vsas = self.get_nodes_by_role(NODE_ROLES.VSA)
        for vsa in vsas:
            ret.append(vsa.esx_host)
            
        return ret
        
    
    def is_encrypted_flag(self):
        """
         Returns True or False depending on if the SOAP_ENCRYPTION
         value is set to True/
         
         :returns: Boolean of whether the encryption flag is set.
        """
        _encrypt_flag = self._sut_dict.get("SOAP_ENCRYPTION")
        if _encrypt_flag == None:
            return True
        elif str(_encrypt_flag).lower() == "true":
            return True
        else:
            return False
    
    
    def is_auto_discovery_flag(self):
        """
         Returns True or False depending on if the AUTO_DISCOVERY
         value is set to False
         
         :returns: Boolean of whether the auto discovery flag is set.
        """
        _ad_flag = self._sut_dict.get("AUTO_DISCOVERY")
        if _ad_flag == None:
            return True
        elif str(_ad_flag).lower() == "false":
            return False
        else:
            return True
    
    
    def is_vsa_cluster(self):
        """
         Returns True or False depending on if any of the nodes
         are denoted as serving in the VSA role.
        """
        if len(self.get_nodes_by_role(NODE_ROLES.VSA)) > 0:
            return True
        else:
            return False
        
    
    def _set_user_info(self):
        """
            Checks for username in the env file. If no name is
            specified, it will be defaulted to 'root'.
            We'll probably add more stuff here in the future.
        """
        import base64

        self.username = self._sut_dict.get("USERNAME")
        if self.username == None:
            self.username = lib.constants.DEFAULT_USER
            print "WARNING: No username specified. Defaulting to '%s'."%self.username

        self.password =self._sut_dict.get("PASSWORD")
        if self.password == None:
            print "WARNING: No password specified. Defaulting to the lab standard"
            self.password = base64.b64decode(lib.constants.DEFAULT_PASSWORD)

        self.domain = self._sut_dict.get("DOMAIN")
        if self.domain == None:
            self.domain = lib.constants.DEFAULT_DOMAIN
            print "WARNING: No domain specified. Defaulting to: %s"%self.domain


    def _set_pyro_ns_info(self):
        """
            Sets our Pyro nameserver information
        """
        try:
            self.pyro_ns_name = self._sut_dict["PYRO_NS_NAME"]
            self.pyro_ns_port = self._sut_dict["PYRO_NS_PORT"]
        except:
            print "WARNING: No Pyro nameserver information in Environment file."
            print "The Pyro Nameserver is most likely the machine driving the tests."
            print "Add these lines like this to your env file: "
            print "PYRO_NS_NAME: <IP of log server> "
            print "PYRO_NS_PORT: <port number> "
    
    
    def _check_ae2_path_mismatch(self):
        from ae import prepper
        if sys.platform =='win32' and \
           self.ae_base_win32.lower() != str(prepper.find_ae_path()).lower():
            print "WARNING: AE2 base path does not match env file."
            print "  -->AE2 base:%s"%prepper.find_ae_path()
            print "  -->Env base:%s"% self.ae_base_win32
            sleep(10)
        elif sys.platform =='linux' and self.ae_base_linux != prepper.find_ae_path():
            print "WARNING: AE2 base path does not match env file."
            print "  -->AE2 base:%s"%prepper.find_ae_path()
            print "  -->Env base:%s"% self.ae_base_win32
            sleep(10)
    
            
    def _set_ae_info(self):
        """
            Sets our ae information (base path, tools path, etc)
            
            Note: This is going to require that the pathing on the SUTs
            be the same as the driver. If we're deploying stuff from the driver
            this is fine but  if/when there is a need for a mixture of 
            linux/windows machines in our SUT this will need to be enhanced.
        """
        try:
            tmp = self._sut_dict["AE_BASE_LINUX"]
            self.ae_base_linux = lib.string_extensions.get_dir_from_path(tmp)
        except:
            print "WARNING: Linux AE Base path not found in the Environment file"
            print "Add a line like this to your env file: "
            print "AE_BASE_LINUX:  ... full path to ae.py..."
        try:
            tmp = self._sut_dict["AE_BASE_WIN32"]
            self.ae_base_win32 = lib.string_extensions.get_dir_from_path(tmp)
        except:
            print "WARNING: Win32 AE Base path not found in the Environment file"
            print "Add a line like this to your env file: "
            print "AE_BASE_WIN32:  ... full path to ae.py..."
        
        try:
            self._check_ae2_path_mismatch()   
        except:
            pass
            

    def _set_log_server_info(self):
        """
           Sets our remote log server information from the environment 
           config file. 
        """
        try:
            self.log_server = self._sut_dict["LOG_SERVER"]
        except:
            print "WARNING: Log server not specified in the Environment file."
            print "The log server is most likely the machine driving the tests."
            print "Add a line like this to your env file: "
            print "LOG_SERVER: <IP of log server> "
        try:
            self.log_port = self._sut_dict["LOG_PORT"]
        except:
            self.log_port = 9020
            print "WARNING: Log server PORT not specified in the Environment file."
            print "Add a line like this to your env file: "
            print "LOG_SERVER: <port number> "
            print "Defaulting to port 9020." 
            
    def _set_log_level(self):
        """
            Checks for log_level in the env file. If no log_level is
            specified, it will be defaulted to very lowest level.
        """
        try:
            self.log_level = self._sut_dict["LOG_LEVEL"]
        except:
            self.log_level = int("0x3", 0)
            print "Defaulting to log level 0x3." 
            
    def _set_log_size(self):
        """
            Checks for a specific log size (LOG_SIZE) setting in
            the environment file.
        """
        try:
            self.log_size = self._sut_dict["LOG_SIZE"]
        except:
            self.log_size = str(32*1024*1024)
            print "Defaulting to log size to %s bytes"%self.log_size
            
    def _set_vmware_info(self):
        """
         Sets the pertinent information regarding the vmware layout
         of our sut.
         For now, we'll just store the managing vSphere server and 
         admin credentials as the host information is already associated
         with the relevant VSA nodes.
        """
        vmware = self._sut_dict.get("VMWARE")
        if vmware:
            self.vsphere_server = vmware.get("VSPHERE_SERVER")
            self.vsphere_username = vmware.get("USERNAME")
            self.vsphere_password = vmware.get("PASSWORD")
            if self.vsphere_password == None:
                import base64
                self.vsphere_password = base64.b64decode(lib.constants.DEFAULT_PASSWORD)
                
    def validate_vsa_info(self):
        """
         If any of the nodes are VSA's, we validate the SUT object
         to ensure that all vmware required information 
         (vsphere, ESX, extra credentials) are present and seem
         correct.
        """
        
        pass
        
        
        _error = ""
        for _node in self.nodes:
            if not _node.username or not _node.password:
                _error += "Node %s is missing USERNAME or PASSWORD\n"%_node
            if _node.iscsi_ips == None:
                _error += "Node %s is missing ISCSI_IPS (use an empty list for a Fibre Channel).\n"%_node
            if not _node.mgmt_ip:
                _error += "Node %s is missing MGMT_IP\n"%_node
            if not _node.esx_host:
                _error += "Node %s is missing ESX_HOST\n"%_node
            if not _node.vm_name:
                _error += "Node %s is missing VM_NAME\n"%_node
            
        if not self.vsphere_server:
                _error += "SUT is missing VSPHERE_SERVER\n"
        if not self.vsphere_username:
            _error += "SUT is missing VSPHERE_USERNAME\n"
        if not self.vsphere_password:
            _error += "SUT is missing VSPHERE_PASSWORD\n"
        
        if _error:
            raise ae_errors.FatalError(_error)
        
                                        


class SutInfoError(Exception):
    """
     Custom exception class to be raised when SUT information
     is not found.
     This affords some error handling flexibility in the future 
     if we want to setup the framework to also look at the test 
     configs for missing information.
    """
    def __init__(self,message=""):        
        raise BaseException("SutInfoError not fully implemented!")



###############################################################################



if __name__ == "__main__":
    from ae.loader import Loader

    suite_file1 = "..%ssuite_files%sexamples%ssuite_ex.cfg" % (os.path.sep, os.path.sep,os.path.sep)
    env_file1 = "..%senv_files%susers%scpowers%satlvm034_to_atl2-4.cfg" % ( os.path.sep,os.path.sep, os.path.sep,os.path.sep,)

    (suite,sut) = Loader.get_run_info(suite_file1,env_file1)
    
    print sut.is_vsa_cluster()
    
    print sut.nodes[0].iscsi_ips[0].split(":")[0]
    
    """
    vsas = sut.get_nodes_by_role(NODE_ROLES.VSA)
    client_vms = sut.get_nodes_by_role(NODE_ROLES.CLIENT)
    for vd in sut.san.vds:
        for vsa in vsas:
            for client in client_vms:
                print client
                if client.esx_host != vsa.esx_host or hasattr(client, "lun"):
                        continue
                else:
                    print "cloning...."
                    src_vm = "vsa_client_do_not_delete"
                    setattr(client, "lun", vd.wwn)       
    """