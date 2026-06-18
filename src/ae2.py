#!/usr/bin/python
"""
.. module:: ae
    :synopsis: Top level AwesomeExpress wrapper tool v.2
"""

try:
    import atfork
except ImportError:
    import sys
    from ae.prepper import Prepper
    try:
        if Prepper.install_atfork() == 0:
            print "Success. Please restart AE2."
            sys.exit(0)
        else:
            raise 
    except Exception,ex:
        print "Atfork installation failed. Please install manually."
        print ex
        sys.exit(1)

atfork.monkeypatch_os_fork_functions()
import atfork.stdlib_fixer
atfork.stdlib_fixer.fix_logging_module()

import os
import sys
import logging
import signal
import time
import subprocess
from optparse import OptionParser
import traceback
import ae
from ae.prepper import Prepper
from ae import ae_logger, ae_errors
from string import lower

try:
    import yaml
except:
    Prepper.install_yaml()
    import yaml


        
        
def processcommandline(argv):
    """
     Parses the command line. We actually go old school to check for
     keyword=value options first and then grab the required args.
    """
    xargs = {}
    
    # find where extra args start
    xd_start = None
    for arg in sys.argv:
        if '=' in arg:
            xd_start = sys.argv.index(arg)
            break
    
    # we want to process any extra options and add those to a 
    # kwarg dict that will initial populate the testing data dict
    myargs = sys.argv[xd_start:]
    for arg in myargs:
        try:
            key, value = arg.split('=', 1)
            xargs[key] = value
        except:
            pass
    
    # Parse the args prior to the extra data args
    argv = sys.argv[1:xd_start]
    parser = OptionParser()
    parser.add_option("-p", "--procedure_only", 
                      type="string", 
                      default=None,
                      action="store", 
                      dest="proc", 
                      help="Specify a test procedure to run")
    parser.add_option("-i", "--install_only", 
                      default=False,
                      action="store_true", 
                      dest="prep_only", 
                      help="Performs the AE2 deployment and installation on remote nodes only.")
    parser.add_option("-s", "--skip_deploy", 
                      default=False,
                      action="store_true", 
                      dest="skip_prep", 
                      help="Skips AE2 deployment, install, and starting services on remote nodes.")
    (options, args) = parser.parse_args(argv)
    (suite_file, env_file) = args
    
    print "options:%s" % options
    
    if "," in suite_file:
        suite_file = suite_file.split(",")
    else: 
        tmp = suite_file
        suite_file = []
        suite_file.append(tmp)

    # do some sanity checking on our args
    env_file = os.path.abspath(env_file)
    
    for _file in suite_file:
        _file = os.path.abspath(_file)
        if os.path.exists(_file) == False:
            parser.error("Suite file does not exist:%s"%_file)
    if os.path.exists(env_file) == False:
        parser.error("Environment file does not exist:%s"%env_file)

    return (suite_file, env_file, options, xargs)


def add_ae_path():
    """ 
     Adds our AE base path to the Python lib if needed.
    """
    ae_base = sys.path[0]
    perm_path = sys.path[1:]
    if ae_base in perm_path:
        return
    
    from distutils.sysconfig import get_python_lib
    python_lib = get_python_lib() 
    cmd = " echo %s > %s"%(ae_base, os.path.join(python_lib,"ae.pth"))
    os.system(cmd)


def main(argv=None):
    
    tr_upload = False
    clean_logs = False
    subunit = False
    maniac = None
    log_svc = None
    tr = None
    ae_log = None
    
    usage ="""
USAGE: 
ae2.py <suite config file | CSV file list> <environment config file> [-p <procedure_filepath:class>] [keyword1=value1 keyword2=value2 ...]

OPTIONS:
-i                   : Performs the AE2 deployment and installation on 
                        remote nodes and skips testing.
-s                   : Skips AE2 deployment, installation, and starting services 
                        on remote nodes. This assumes the tests to be executed 
                        handle the appropriate deployment and installation actions
                        as well as starting the Pyro service on the nodes.
-p                   : Executes a specific test procedure only (runs synchronously)
clean_log=true       : Forces a log file rotate so the active log starts clean
subunit=true         : Creates a subunit logfile (used for buildbot)
archive_configs=true : Archives env and suite files
testrail=true        : Automatically uploads results to testrail
         
EXAMPLES:
 Normal test run:
 $python ae2.py my_suite.cfg my_env.cfg clean_log=true another_var=something
 
 Debu mode:
 $python -d ae2.py my_suite.cfg my_env.cfg clean_log=true another_var=something
 
 Test run on a list of suite files:
 $python ae2.py some_tests.cfg,more_tests.cfg my_env.cfg clean_log=true another_var=something
 
 Executing a procedure only
 $python ae2.py my_suite.cfg my_env.cfg -p test_procedures\example_procedures\hello_world.py:Hello_World another_var=something


"""

    def shutdown(ae_log=None, maniac=None, log_svc=None, tr=None):
        
        try:
            if tr:
                try:
                    tr.stop_tests()
                    ae_log.info(tr.get_test_summary())
                except:
                    return
            if maniac:
                maniac.shutdown_pyro()
                maniac = None
                           
            ae_log.info("---   AE FINISHED   ---")
            ae_log.close()
            time.sleep(1)
            log_svc.stop_log_server()
            logging.shutdown()
            ae_log = None
        except Exception, ex:
            print "Error during log server shutdown: %s" % ex
        finally:
            sys.exit(0)
            

    def signal_handler(signal, frame):
        msg = "Interrupt detected. Stopping modules..."
        try:
            ae_log.info(msg)
        except:
            pass
        shutdown(ae_log, maniac, log_svc, tr)
        
    try:
        (suite_file, env_config, options, xargs) = processcommandline(argv)
    except ValueError, ex:
        print usage
        sys.exit(1)

    # Check that we are running with Python27
    required_version = (2,7)
    current_version = sys.version_info
    if current_version <= required_version:
        print "Python27 is required to run AE2"
        sys.exit(1)
    
    # Test Driver setup stuff via the Prepper
    add_ae_path()
    ae.prepper.install_winexe()
    ae.prepper.do_prep()
    from ae.pyro_driver import Pyro
            
    try:
        # use the loader to build our suite and sut objects
        suite,sut = ae.loader.Loader.get_run_info(suite_file, env_config)
        if sys.flags.debug:
            print sut
    except:
        print traceback.print_exc()
        sys.exit(1)
        
    # Check our extra args for special variables
    try:
        for k,v in xargs.items():
            if lower(k) == "clean_log" and lower(v) == "true":
                clean_logs = True
            if lower(k) == "subunit" and lower(v) == "true":
                subunit = True
            if lower(k) == "node":
                try:
                    xargs[k]=eval(v)
                except:
                    ae_log.info("Using [%s] as the node."%v)
    except:
        pass
    
    # Start and configure the ae_logger tcp server for remote logging
    filename = os.path.basename(os.path.splitext(env_config)[0])
    log_svc = ae.ae_logger.LogServer(
                                     sut.log_server,
                                     sut.log_port,
                                     filename,
                                     sys.flags.debug,
                                     clean_log=clean_logs,
                                     su_log = subunit)
    log_svc.start_log_server()
    time.sleep(1)
    if sys.flags.debug:
        ae_log = ae_logger.Log(sut.log_server, sut.log_port, debug_flag=True, truncate=False)
    else:
        ae_log = ae_logger.Log(sut.log_server, sut.log_port, truncate=False)
   

    ae_log.info(" ---   AE STARTING   --- ")
    ae_log.debug("%s"%" ".join(sys.argv))
    ae_log.debug("AE2 PID: [%s]"%os.getpid())
    ae_log.debug("The SUT: %s"%sut)
        
    # Log the svn info of the working copy
    ae_log.debug("SVN info:")
    repo_dir = os.path.dirname(os.path.abspath(__file__))
    svn_proc = subprocess.Popen('svn info', cwd=repo_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    for line in svn_proc.communicate():
        ae_log.info(line)
    
    if options.skip_prep == True:
        ae_log.info("AE2 Mode: Skipping deploy and installation")
        maniac = Pyro(sut)
        maniac.start_threaded_ns()
    else:
        # finds our list of nodes which are up and accessible
        up_nodes = ae.prepper.find_up_nodes(sut)   
    
        # Deploy AE to the remote nodes
        ae_log.info("Deploying AE to all nodes in cluster")
        Prepper.deploy_ae_files(sut,up_nodes)
        
        # Report time skew between driver and suts
        ae_log.info("Triggering a NTP update on Nodes")
        Prepper.timesync(sut,up_nodes)    
        
        # Make sure our AE base path has been added to the python sys.path
        ae_log.info("Setting up the PTH files (for project pathing) on nodes")
        Prepper.remote_setup(sut,up_nodes)
        
        # Start the Pyro nameserver on the driver and 
        # begin publishing the proc_caller on the nodes
        ae_log.info("Starting Pyro")
        maniac = Pyro(sut)
        maniac.startup_pyro(up_nodes)

    if options.prep_only == True:
        ae_log.info("AE2 deployment and installation complete.")
        shutdown(ae_log, maniac, log_svc, tr)
        
    signal.signal(signal.SIGINT, signal_handler)
    
    
    # Here's where the magic happens...
    try:
        # Run AE in normal mode (runs a suite file)
        if options.proc == None:
            tr = ae.testing.TestRunner(sut, suite, xargs)
            tr.run_tests()
        
        # Execute a test procedure outside of a test
        else:
            ae_log.info("Running in TP stand-alone mode")
            
            # Finesse the data to make it as similar to a live run as possible
            for k,v in xargs.items():
                # See if we need to reference a sut.node
                if lower(k) == "node":
                    try:
                        xargs[k]=eval(v)
                    except:
                        ae_log.info("Using [%s] as the node."%v)
            
            
            # swizzle the [module filepath]:[TP class name] into
            # something importable by python.
            def my_import(name):
                mod = __import__(name)
                components = name.split('.')
                for comp in components[1:]:
                    mod = getattr(mod, comp)
                return mod
            
            # break apart the procedure file and class name
            proc = options.proc.split(":")
            if len(proc) != 2:
                msg =" Test procedure should be specified as procedure_file_path:class_name"
                raise ae_errors.TestProcedureError(message=msg)
            proc_file = proc[0] 
            cls_name = proc[1]
            proc_file_no_ext = os.path.splitext(proc_file)[0]
            mod = proc_file_no_ext[proc_file_no_ext.find('test_procedures'):].replace(os.path.sep,'.')
            # take the '.' module path and call the import method to
            # traverse the path, importing stuff as it goes
            cls_path = "%s.%s"%(mod,cls_name)
            cls_name = cls_path[cls_path.rfind('.'):].lstrip('.')
            cls_path = cls_path[:cls_path.rfind('.')]
            # we get a reference to the TP class module and instantiate one
            mod = my_import(cls_path)
            cls = getattr(mod,cls_name)
            tp = cls(sut, suite)
            
            #
            # execute the procedure
            ae_log.info("Executing [%s] with data: %s"%(cls_name,xargs))
            tp.run(**xargs)
             
            
    except BaseException, ex:
        ae_log.info("An error occurred during the test run:\n%s"%ex)
    
    shutdown(ae_log, maniac, log_svc, tr)
    
    
if __name__ == "__main__":
    sys.exit(main())
    
