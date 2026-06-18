""" The prepper is a framework module which will assist in 
    the preparation of the sut to run the automation. This includes 
    copying files, installing stuff, etc
""" 
import sys
import os
import platform
import ntpath
import posixpath
import time
import zipfile
from distutils.sysconfig import get_python_lib
from datetime import datetime, timedelta
import subprocess

try:    
    import ae_logger
    import ae_errors
    from ae.environment import OS_TYPE
    from lib import pathing, string_extensions, constants
except ImportError, ex:
    import traceback
    print "WARNING %s"%ex
    print traceback.print_exc()
    


class Prepper():
    """The Prepper class contains the functionality to prepare the SUT for AE 
    """

    @staticmethod
    def _rsync(sut, local_ae_base_path, node, ae_base_path):
        
        log = ae_logger.Log(sut.log_server, sut.log_port)
        log.info("Deploying AE to [%s:%s]" % (node, ae_base_path))
        # This will not be windows compatible without some work
        # Make base directory       
        cmd = "ssh %s@%s mkdir -p %s" % (sut.username, node, ae_base_path)
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        p.wait()
    
        if p.returncode != 0:
            log.error("Failed to create [%s] on [%s]" % (ae_base_path, node))          
           
        # Rsync files over to the remote node
        cmd = "rsync -ave ssh --exclude 'src/logs' src externals tools %s@%s:%s" % (sut.username, node, ae_base_path)
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, cwd=local_ae_base_path)
        (stdout, stderr) = p.communicate()
    
        if p.returncode != 0:
            log.error("Failed to rsync from [%s] to [%s:%s] err [%d] stdout [%s] stderr [%s]" % 
                      (local_ae_base_path, node, ae_base_path, p.returncode, stdout, stderr))
    
    @staticmethod
    def _win_deploy(sut, node, local_ae_base_path):
        node = node
        mount_cmd =""
        copy_cmd = ""
        _dirs =["externals","src","tools"]
        _suf = string_extensions.remove_drive_letter(local_ae_base_path)

        log = ae_logger.Log(sut.log_server, sut.log_port)
        log.debug("Deploying AE to %s [Windows]" % node)
        if platform.system() == 'Linux':
            log.debug("Deploying from a Linux node")
            
            _node_mp = pathing.get_mountpoints_dir()+os.path.sep+string_extensions.get_host_only(str(node))
            mount_cmd = "mount -t cifs -o user=%s,password=%s %s %s"%(sut.username, sut.password,
                                                                      pathing.get_win_share(node), 
                                                                      pathing.get_win_mp(node))
            if os.path.exists(pathing.get_win_mp(node)) == False:
                os.makedirs(pathing.get_win_mp(node))
            elif os.path.ismount(pathing.get_win_mp(node)) == False:
                log.debug("Mounting remote node %s: %s" % (node, mount_cmd))
                p = subprocess.Popen(mount_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
                (stdout, stderr) = p.communicate(mount_cmd)
                if p.returncode != 0:
                    raise ae_errors.FatalError("Failed to mount admin share on [%s]\nStdout:%s\nStderr:%s"
                                               %(node,stdout,stderr))
            else:
                pass # its already mounted
        elif platform.system() == 'Windows':
            log.debug("Deploying from a Windows node")
            mount_cmd = "net use  %s /user:%s\\%s %s"%(pathing.get_win_share(node),sut.domain,sut.username,sut.password)
            log.debug("Mounting remote node %s: %s" % (node, mount_cmd))
            p = subprocess.Popen(mount_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
            (stdout, stderr) = p.communicate(mount_cmd)
            if p.returncode != 0:
                raise ae_errors.FatalError("Failed to mount admin share on [%s]\n%s\n%s"%(node, stdout,stderr))
        else:
            raise ae_errors.FatalError("Unsupported driver OS")
    
        for _dir in _dirs:
            if platform.system() == 'Linux':
                linux_path = posixpath.split(sut.ae_base_linux)[0]
                frm = linux_path+os.path.sep+_dir
                dst = pathing.get_win_mp(node)+os.path.sep+string_extensions.localize_path(_suf)
                if os.path.exists(dst) == False:
                    os.makedirs(pathing.get_win_mp(dst))
                copy_cmd = "cp -u -R %s %s"%(frm, dst)
            else:
                frm = local_ae_base_path+os.path.sep+_dir
                dst = pathing.get_win_mp(node)+os.path.sep+_suf+os.path.sep+_dir
                copy_cmd = "xcopy /D/C/R/E/S/Y/Q/I/O %s %s"%(frm, dst)
            log.debug("Executing copy: %s" % copy_cmd)
            p = subprocess.Popen(copy_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
            (stdout, stderr) = p.communicate()

            if p.returncode != 0:
                raise ae_errors.FatalError("Failed to sync files to admin share on [%s]\nStdout:%s\nStderr:%s"
                                           %(node,stdout,stderr))
    
    
    @staticmethod
    def deploy_to_vsa(sut,nodes):
        """
         Deploys AE2 to a VSA (linux virtual machine) using 
         an alternative method to the prepper's rsync.
     
         :param nodes: A list of nodes to deploy 
        """
        import vimer
        AE2_ZIPFILE = "/tmp/ae2.zip"
        AE2_TMP = "/tmp/ae2"
        
        if not nodes or len(nodes)==0:
            raise ae_errors.TestProcedureError(message="No VSA nodes specified.")
        if isinstance(nodes,list) == False:
            nodes = [nodes]
        
        log = ae_logger.Log(sut.log_server, sut.log_port)
        ae2_zipfile = Prepper.zip_ae2(sut)
        log.info("AE2 ZIP archive at %s"%ae2_zipfile)
        for node in nodes:
            log.info("Deploying to %s."%(node))
            t = vimer.VmTool(node.vm_name,sut=sut)
            t.copy_file(ae2_zipfile, AE2_ZIPFILE)        
            
            remote_repo = posixpath.split(sut.ae_base_linux)[0]
            
            # clean out the remote repo location
            log.debug("Deleting directory %s on %s"%(remote_repo,t.vm_name))
            cmd = "rm -rfd %s"%remote_repo            
            t.run_shell(cmd)
            
            log.debug("Unzipping AE2 archive to %s on %s"%(AE2_TMP,t.vm_name))
            cmd = "rm -rfd %s;unzip %s -d %s"%(AE2_TMP,AE2_ZIPFILE,AE2_TMP)
            t.run_shell(cmd)
            
            # find the project path (one above src) in the new unpacked directory structure
            # we'll swizzle this path to a linux path and append it to the unpacked location
            project = string_extensions.remove_drive_letter(Prepper.get_ae2_basepath(sut))
            project = project.replace(os.path.sep, posixpath.sep)
            if project.startswith(posixpath.sep):
                project = project[1:]
            project = posixpath.join(AE2_TMP,project)
            
            # now we copy the project path from under /tmp to the desired AE2 base path
            # project = project[:project.rfind(posixpath.sep)]
            log.debug("Moving %s to %s on %s"%(project,remote_repo,t.vm_name))
            t._vm.move_directory(project,remote_repo)
            # delete remote archive and temp directory
            cmd = "rm -rfd %s %s"%(AE2_ZIPFILE, AE2_TMP)
            t.run_shell(cmd)
            
            log.info("Running the prepper on %s"%node.vm_name)
            _python = constants.PYTHON27_LINUX
            prepper_path = "%s/ae/prepper.py" % sut.ae_base_linux.rstrip('/')
            cmd = "%s %s"%( _python, prepper_path)
            t.run_shell(cmd)
            
        # remove the local archive on the test driver
        log.debug("Removing AE2 archive at %s"%ae2_zipfile)
        os.remove(ae2_zipfile)
    
    @staticmethod
    def deploy_ae_files(sut, nodes):
        """Deploy the AE files to the SUT
        
        Use SSH to create the AE_BASE directory on all nodes and then
        use RSYNC to copy the local AE_BASE directory to the remote nodes
        
        :param sut: SUT Object
        :type sut: :class:`ae.environment.Sut`
        
        .. warning:: ae_base path info in the SUT object must end in 'src'
        """
        
        log = ae_logger.Log(sut.log_server, sut.log_port)
        log.debug("my pid [%s]"%os.getpid())
        local_os = platform.system()
        
        # strip out any VSA nodes and call a different
        # deployment method for that list subset
        vsa_nodes = []
        iron_nodes = []
        for _node in nodes:
            if _node.is_vsa():
                vsa_nodes.append(_node)
            else:
                iron_nodes.append(_node)
        if len(vsa_nodes) > 0:
            Prepper.deploy_to_vsa(sut, vsa_nodes)
        
        # Expects SUT path definition in environment to end in src
        # Normalize the path to be root of AE where doc, externals, and src are located
        try:
            split_path = posixpath.split(sut.ae_base_linux)
            linux_path = split_path[0]
        except Exception, ex:
            log.warning("Could not resolve linux pathing [%s]" % ex)
            linux_path = ""
        try:
            split_path = ntpath.split(sut.ae_base_win32)
            win32_path = split_path[0]
        except Exception, ex:
            log.warning("Could not resolve Win32 pathing [%s]" % ex)
            win32_path = ""
        
        
        # Determine local path to root of AE
        if local_os == "Linux":
            local_ae_base_path = linux_path
        elif local_os == "Windows":
            local_ae_base_path = win32_path
        else:
            log.error("Local OS is unsupported")
            
        log.debug("Local Base AE path [%s]" % local_ae_base_path)
        
        for node in iron_nodes:
            if node.os.os_type == OS_TYPE.WINDOWS:
                Prepper._win_deploy(sut, node, win32_path)
            elif node.os.os_type == OS_TYPE.LINUX:
                Prepper._rsync(sut, local_ae_base_path, node, linux_path)
            else:
                raise ae_errors.FatalError("No os_type specified for %s" % node)
            
    
    @staticmethod
    def get_ae2_basepath(sut):
        """
         Returns the basepath (one up from src) of the local AE2 repository.
        """
        if "Linux" == platform.system():
            return posixpath.split(sut.ae_base_linux)[0]
        elif "Windows" == platform.system():
            return ntpath.split(sut.ae_base_win32)[0]
        else:
            _msg = "Unsupported OS type: %s"%platform.system() 
            raise ae_errors.TestProcedureError(message=_msg)

    
    @staticmethod
    def zip_ae2(sut):
        """
         Uses the zipfile module to zip up the local AE2 repository
         and place the the archive in a temporary location where it
         can be deployed out to remote machines.
         
         Returns the temporary file location of the archive.
        """
        import tempfile
        archive = tempfile.mktemp()
        ae2_base = Prepper.get_ae2_basepath(sut)
        
        black_list = [".svn",
                      os.path.join(ae2_base,"logs"),
                      os.path.join(ae2_base,"doc"),
                      ]
        
        zf = zipfile.ZipFile(archive, "w")
        for dirname, subdirs, files in os.walk(ae2_base):
            for _dir in black_list:
                if _dir in subdirs:
                    subdirs.remove(_dir)
            zf.write(dirname)
            for filename in files:
                zf.write(os.path.join(dirname, filename))
        zf.close()
        
        return archive
         
    
    @staticmethod
    def timesync(sut, nodes):
        """
         Trigger a time synchronization on the nodes
        
        :param sut: SUT Object
        :type sut: :class:`ae.environment.Sut`
        """
        log = ae_logger.Log(sut.log_server, sut.log_port)
        
        if platform.system() == 'Linux':
            cmd = "ntpdate -u %s" % constants.NTP_SERVER
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
            (stdout, stderr) = p.communicate()
            if p.returncode !=0:
                log.warning("Failed to trigger timesync on driver.")
        
        for node in nodes:
            if node.is_vsa():
                continue
            elif node.os.os_type == OS_TYPE.WINDOWS:
                cmd = "W32tm.exe /resync"
            else:
                cmd = "ntpdate -u %s" % constants.NTP_SERVER
            cmd = get_remote_cmd(sut, node, cmd)
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
            (stdout, stderr) = p.communicate()
            if p.returncode !=0:
                log.warning("Failed to trigger timesync on %s"%node)
            
            ## our check timesync query
            #cmd = "ssh %s@%s date +%%s" % (sut.username, node)
            #p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
            #(stdout, stderr) = p.communicate()
            #local_datetime = datetime.now()
            #
            #if p.returncode != 0:
            #    log.error("Failed to get node[%s] date information due to [%d]:[%s]:[%s]" % 
            #              (node, p.returncode, stdout, stderr))
            #else:
            #    node_datetime = datetime.fromtimestamp(float(stdout))
            #    time_difference = abs(node_datetime - local_datetime)
            #    if time_difference > max_time_delta:
            #        log.warning("Time difference [%ss] from driver to node [%s] beyond max [%ss]" % (
            #                    time_difference.seconds, 
            #                    str(node).split('.')[0], 
            #                    MAX_TIME_DELTA_SECS))
            #
                    
    @staticmethod
    def remote_setup(sut, nodes):

        """
         Ssh's to all the nodes in the sut and calls a sequence of 
         setup steps to ensure the remote machine is ready to run.
         
         Setup steps:
         
         Prepper.install_yaml()     -- Installs PyYAML if needed.
         
         Prepper.setup_pth_files()  -- adds an AE PTH file in python lib
                                       to add the AE path to Python path.

         Prepper.install_pyro()     -- Installs Pyro4 package.

         Prepper.install_psutil()   -- Installs psutil API.
         
        """       
        log = ae_logger.Log(sut.log_server, sut.log_port)
        
        try:            
            linux_path = "%s/ae/prepper.py" % sut.ae_base_linux.rstrip('/')
        except Exception, ex:
            log.warning("%s"%ex)
        try:
            win32_path = "%s\\ae\\prepper.py" % sut.ae_base_win32.rstrip('\\')
        except Exception, ex:
            log.warning("%s"%ex)
        
        for node in nodes:
            if node.is_vsa():
                import vimer
                vm = vimer.VmTool(node.vm_name, sut=sut)
                _python = constants.PYTHON27_LINUX
                prepper_path = "%s/ae/prepper.py" % sut.ae_base_linux.rstrip('/')
                cmd = "%s %s"%( _python, prepper_path)
                vm.run_shell(cmd)
                continue
            elif node.os.os_type == OS_TYPE.WINDOWS:
                prepper_path = win32_path
                _python = constants.PYTHON27_WIN32
            elif node.os.os_type == OS_TYPE.LINUX:
                prepper_path = linux_path
                _python = constants.PYTHON27_LINUX
            else:
                raise ae_errors.FatalError(message="Unsupported node os_type:%s"%node.os_type)
            
            cmd = "%s %s"%( _python, prepper_path)
            
            cmd = get_remote_cmd(sut, node, cmd)
            log.debug("Running [%s]"%cmd)
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
            p.wait()
            (stdout,stderr) = p.communicate()
        
            if p.returncode != 0:
                log.error("Remote setup failed on [%s]"%node)    
                log.error("STDOUT:%s\nSTDERR:%s"%(stdout,stderr))
    
    
    @staticmethod
    def setup_pth_files():
        """
         Sets up the PTH file on the local machine only so that the 
         base ae project path is added to the python sys path
         
         NOTE: The PTH doesn't affect the sys.path until the next
               time the interpreter is ran so we need to add to
               do a one time add to sys.path to satisfy the initial
               condition.
        """
        
        ae_base = find_ae_path()
        # if the AE base path is already there, we bail        
        if ae_base in sys.path:
            print "AE is already in sys.path"
            return 0
        
        
        
        python_lib = get_python_lib() 
        cmd = " echo %s > %s"%(ae_base, os.path.join(python_lib,"ae.pth"))
        add_ae_base_path()
        
        return os.system(cmd)


    @staticmethod
    def install_yaml():
        """Install PyYAML from the externals directory
        """
        try:
            import yaml
            if str(yaml.__version__) != "3.10":
                raise ImportError("Incorrect version of YAML found.")
            return 0 
        except ImportError:
            print "Installing PyYAML..."
            YAML = "PyYAML-3.10"
            if sys.platform == 'win32':
                INSTALLER = "PyYAML-3.10.win32-py2.7.msi"
                return Prepper._run_installer(INSTALLER)
            else:
                return Prepper._install_externals_package(YAML)


    @staticmethod
    def install_pyro():
        """Install Pyro from the externals directory
        """
        try:
            import Pyro4
            if str(Pyro4.__version__) != "4.17":
                raise ImportError("Incorrect version of Pyro4 found.")
            return 0 
        except ImportError:
            print "Installing Pyro..."
            PYRO= "Pyro4-4.17"
            return Prepper._install_externals_package(PYRO)
    
    
    @staticmethod
    def install_psutil():
        """Install Pyro from the externals directory
        """
        try:
            import psutil
            if not "0.5" in str(psutil.__version__):
                raise ImportError("Incorrect version of psutil found.")
            return 0
        except ImportError:
            print "Installing psutil..."
            PSUTIL= "psutil-0.5.1"
            if sys.platform == 'win32':
                INSTALLER = "psutil-0.5.1.win32-py2.7.msi"
                return Prepper._run_installer(INSTALLER)
            else:
                return Prepper._install_externals_package(PSUTIL)


    @staticmethod
    def install_pysphere():
        """Install pySphere from the externals directory
        """
        try:
            import pysphere
            return 0
        except ImportError:
            print "Installing pysphere..."
            PYSPHERE= "pysphere-0.1.7"
            return Prepper._install_externals_package(PYSPHERE)


    @staticmethod
    def install_atfork():
        """Install atfork from the externals directory
        """
        try:
            import atfork
            return 0
        except ImportError:
            print "Installing atfork..."
            ATFORK= "atfork-0.1.2"
            return Prepper._install_externals_package(ATFORK)


    @staticmethod
    def install_fast():
        """
         Install the FAST library if needed on Linux machines.
        """
        # FAST requires a number of Python Windows 
        # extensions modules such as win32api.
        # There will be some additional work if we ever
        # want/need to install FAST on Windows machines    
        #
        if sys.platform == 'win32':
            return 0
        
        try:
            import fast
            return 0
        except ImportError:
            print "Installing fast..."
            FAST = "FAST-2.0.3"
            return Prepper._install_externals_package(FAST)


    @staticmethod
    def install_lxml():
        """Install lxml from the externals directory
        
        This requires:
            libxml
            libxslt
        """       
        try:
            import lxml
            return 0
        except ImportError:
            LXML= "lxml-2.3.5"
            print "Installing lxml..."
            if sys.platform == 'win32':
                INSTALLER = "lxml-2.3.5.win32-py2.7.msi"
                return Prepper._run_installer(INSTALLER)
            else:
                return Prepper._install_externals_package(LXML)


    @staticmethod
    def install_suds():
        """
         Install Python Suds from the external directory
        """ 
        SUDS = "python-suds-0.4"
        
        # set our external source and lib path. These are non-standardized :(
        src_path = os.path.abspath(os.path.join(find_ae_path(),"..",'externals',SUDS))
        lib_path = os.path.abspath(os.path.join(get_python_lib(),"suds"))
        diff = None
        try:
            import suds
            if not "0.4" in str(suds.__version__):
                raise ImportError("Incorrect version of suds found.")
            
            try:
                egg = get_egg_file('suds')
                if egg:
                    diff = diff_egg_src(egg, src_path)
                else:
                    src_path = os.path.abspath(os.path.join(src_path,'suds'))
                    diff = diff_lib_src(lib_path, src_path)
                if diff:
                    print"Detected change in external module SUDS. Re-installing..."
                    try:
                        try:
                            os.remove(egg)
                        except:
                            pass
                        print "Reinstalling SUDS"
                        if Prepper._install_externals_package(SUDS) == 0:
                            try:
                                del sys.modules['suds']
                            except:
                                pass
                            return 0
                        else:
                            return 1
                    except:
                        print "Failed to reinstall SUDS."
                        time.sleep(3)
                        raise
            except Exception, ex:
                print "Failed to reinstall SUDS."
                print "Error:%s"%ex
                time.sleep(3)
            return 0
        except ImportError:
            print "Installing suds..."
            return Prepper._install_externals_package(SUDS)
    
    
    @staticmethod
    def _install_externals_package(package):
        from lib import pathing
        install_path = find_ae_path()
        tmp_dir = os.getcwd()
        os.chdir(os.path.abspath(os.path.join(install_path,"..","externals", package)))
        _python = pathing.get_python_bin()
        
        cmd = "%s setup.py -q install" % _python
        ret = os.system(cmd)
        os.chdir(tmp_dir)
        return ret
    
    @staticmethod
    def _run_installer(installer):
        install_path = find_ae_path()
        tmp_dir = os.getcwd()
        os.chdir(os.path.abspath(os.path.join(install_path,"..","externals","MSIs")))
        
        cmd = "msiexec /qn /i %s"%installer
        ret = os.system(cmd)
        os.chdir(tmp_dir)
        return ret


def install_winexe():
    WINEXE = "winexe-1.00-2.2.x86_64.rpm"
    if platform.system() == 'Linux':
        install_path = find_ae_path()
        tmp_dir = os.getcwd()
        os.chdir(os.path.abspath(os.path.join(install_path,"..","externals","RPMs")))
        cmd = "rpm --quiet -i %s"%WINEXE
        ret = os.system(cmd)
        os.chdir(tmp_dir)
        return ret
    else:
        return 0

def get_remote_cmd(sut, node, cmd):
    """
     Takes the cmd and modifies it accordingly to where 
     the cmd needs to execute.
     
     windows|linx     --> linux   performs an ssh cmd
     windows          --> windows uses psexec to invoke cmd
     linux            --> windows uses winexe to invoke cmd
    """
    
    if node.os.os_type == OS_TYPE.LINUX:
        #assume it's an ssh command with keys already installed
        cmd = "ssh %s@%s %s"%(sut.username, node.ip, cmd)
    elif platform.system() == 'Windows':
        # windows -> windows so we use psexec for execution
        ps_exec = os.path.join(pathing.get_tools_bin(),"psTools","PsExec.exe")
        cmd = "%s -is \\\\%s -u %s\\%s -p %s  cmd /c %s" % (ps_exec, node.ip,
                                                               sut.domain,
                                                               sut.username,
                                                               sut.password,
                                                               cmd)
    elif platform.system()=='Linux': 
        # linux -> windows so we'll use winexe for execution
        # Note: the stdout can be polluted by tangent samba messages
        # so it's written to a logfile in the src/logs directory
        _log = os.path.join(find_ae_path(),'logs','winexe.log')
        cmd = "(winexe --system -U %s/%s%%%s //%s \"%s\") 2>&1 >%s"%(sut.domain,
                                                                     sut.username,
                                                                     sut.password,
                                                                     node.ip, 
                                                                     cmd,
                                                                     _log)
    return cmd
 
    

def find_ae_path(): 
    """    
    Will traverse up some directories looking for the path with ae.py file
    and return the absolute path.
    
    :raises: Exception
        
    """
    cwd = sys.path[0]
    max_dirs = 3

    while max_dirs > 0:
        
        ae = os.path.abspath(os.path.join(cwd,"ae2.py"))
        
        if os.path.isfile(ae):
            return cwd
        else:
            cwd = os.path.abspath(os.path.join(cwd, '..'))
        max_dirs -= 1
    
    raise Exception("Failed to find ae path.")


def add_ae_base_path():
    """ 
    """
    
    new_path = find_ae_path()         
        
    if sys.platform == 'win32':
        new_path = new_path.lower()
        
    # check against all paths currently available
    for x in sys.path:
        x = os.path.abspath(x)
        if sys.platform == 'win32':
            x = x.lower()
        if new_path in (x, x + os.sep):
            return
       
    sys.path.append(new_path)
    print "DEBUG2: Added [%s] to python system path." % new_path


def test_ssh(node, login='root'):
    """
     Tests to ensure we can ssh to login@node.
    """
    try:
        cmd = "ssh %s@%s whoami > /dev/null" % (login,node)
        if sys.platform == 'win32':
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, shell=False)
        else:
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, shell=True)
        p.wait()
        (stdout) = p.communicate(cmd)
        if p.returncode == 0:
            return True
        else:
            return False
    except:
        return False


def find_up_nodes(sut):
    """
     Iterates through the nodes in our sut finding
     all that are accessible via the appropriate 
     remote execution mechanism for the node's OS.
    """
    import vimer
    up_nodes = []
    CMD = "whoami"
    for node in sut.nodes:
        try:
            if node.is_vsa():
                vm = vimer.VmTool(node.vm_name,sut=sut)
                vm.run_shell("echo foo /dev/null")
                up_nodes.append(node)
            else:
                cmd = get_remote_cmd(sut, node, CMD)
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
                p.wait()
                (stdout,stderr) = p.communicate(cmd)
                if p.returncode == 0:
                    up_nodes.append(node)
                else:
                    print cmd
                    print "stdout:%s"%stdout
                    print "stderr:%s"%stderr
        except:
            pass
    return up_nodes

    
def check_all_nodes_up(sut, login='root'):
    for node in sut.nodes:
        #
        # If we still want to do this we need a different method
        # other than ssh
        #if test_ssh(node, login) == False:
        #    raise Exception("Unable to ssh to node:%s"% node)
        pass



######   Methods to determine when an external needs reinstalled  #####
def get_egg_file(package_name):
    """
     Returns True or False based on whether the
     site package is packaged within an egg file.
     
     :param package_name: The name of the top level module (suds, psutil, etc)
    """
    from distutils.sysconfig import get_python_lib
    
    sp_files = os.listdir(get_python_lib())
    for f in sp_files:
        if package_name in f and f.endswith(".egg"):
            return os.path.abspath(os.path.join(get_python_lib(),f))
    return None
    
        
def diff_egg_src(egg_file, src_path):
    """
     Diffs the contents of an egg file and 
     src directory and Returns the first file 
     difference found or None if they are the same.
    """
    def is_ignored_dir(path):
        black_list = ["tests","examples","samples","benchmark"] 
        for sd in black_list:
            if sd in path:
                return True
        return False
    z = zipfile.ZipFile(egg_file)
    _list = z.namelist()
    for f in _list:
        if is_ignored_dir(f):
            continue
        if f.endswith('.py'):
            with open(os.path.join(src_path,f)) as src:
                if src.read() != z.read(f):
                    return f
    return None
        
    
def get_py_files(some_path):
    """
     Walks the directory and returns a list of
     all the non-empty .py files from relevant filepaths
     which are in our "ignore" list.
    """
    def is_ignored_dir(path):
        black_list = ["tests","examples","samples","benchmark"] 
        for sd in black_list:
            if sd in path:
                return True
        return False
 
    ret=[]
    for root,dir,files in os.walk(some_path):
        if is_ignored_dir(root):
            continue
        for f in files:
            ff=os.path.join(root,f)
            if f.endswith('.py') and os.path.getsize(ff) > 0:
                ret.append(ff)
    return ret


def diff_lib_src(lib_path, src_path):
    """
     Diffs the contents of a site-package lib path and 
     src directory. Rturns the first file difference found 
     or None if they are the same.
     
     Examples
         lib_path - C:\Python27\Lib\site-packages\lxml 
         src_path - C:\Users\chris_powers\workspace\ae2\externals\lxml-2.3.5\src\lxml
    """
    import filecmp
    src_files = get_py_files(src_path)
    lib_files = get_py_files(lib_path)
    if len(src_files) != len(lib_files):
        return "File count differs!\n Src files:%s\n lib files:%s"%(len(src_files, len(lib_files)))
    else:
        for i in range(len(src_files)):
            if filecmp.cmp(src_files[i],lib_files[i]) == False:
                return "Differing File:%s"% str(src_files[i])
    return None


def remove_suds_cache():
    import tempfile, shutil
    _suds_cache = os.path.join(tempfile.gettempdir(),'suds')
    print "Removing suds cache:%s"%_suds_cache
    shutil.rmtree(_suds_cache, ignore_errors=True)

def remove_pro_files():
    import tempfile
    for root, dirs, files in os.walk(tempfile.gettempdir()):
        for _file in files:
            if _file.lower().endswith('.pro') == True:
                os.remove(os.path.join(root, _file))

def set_rlimits():
    """
     Sets some resource limits for linux machines using the resource module.
    """
    if platform.system() == 'Linux':
        import resource
        from lib import constants
        resource.setrlimit(resource.RLIMIT_NOFILE, (constants.MAX_OPEN_FILES,
                                                    constants.MAX_OPEN_FILES))

def do_prep():    
    if Prepper.setup_pth_files() != 0:
        raise ae_errors.FatalError(message="Failed to setup PTH files.")
    if Prepper.install_yaml() != 0:
        raise ae_errors.FatalError(message="Failed to install PyYAML.")
    if Prepper.install_pyro() != 0:
        raise ae_errors.FatalError(message="Failed to install Pyro.")
    if Prepper.install_psutil() != 0:
        raise ae_errors.FatalError(message="Failed to install psutil.")
    if Prepper.install_fast() != 0:
        raise ae_errors.FatalError(message="Failed to install FAST Library.")
    if Prepper.install_lxml() != 0:
        raise ae_errors.FatalError(message="Failed to install lxml.")
    if Prepper.install_suds() != 0:
        raise ae_errors.FatalError(message="Failed to install suds.")
    if Prepper.install_pysphere() != 0:
        raise ae_errors.FatalError(message="Failed to install pySphere.")
    if Prepper.install_atfork() != 0:
        raise ae_errors.FatalError(message="Failed to install atfork.")
    remove_suds_cache()
    remove_pro_files()
    set_rlimits()


if __name__ == "__main__":   
    do_prep()    