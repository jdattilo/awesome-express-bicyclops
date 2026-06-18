import os
import time
from ae import prepper, ae_logger
from test_procedures import cache, cluster, sys_ops
from test_procedures.cluster import parse_journal
from test_procedures.cluster import parse_events
from dis import dis

TRIAGE_FILENAME = 'csi.log'
fwlog = ae_logger.get_fw_logger()



class TriagePresets():
    """
     A collection of preset triage routines that can be assigned 
     to a given test case to be be executed when AE2 detects a 
     test case failure/error. 
     
     When developing a preset, arguments are expected include the 
     suite and sut objects.
     
     **triage preset prototype example**::
         @staticmethod
         def fancy_preset(sut, suite, start_time=None, end_time=None):
             
             ... do stuff ...
     
     
     **test case usage example**::
         class hello_world(TestCase.TestCase):
         
             def pre_execute(self):
                pass     

             def main_execute(self):      
                 
                 # Assign the triage preset
                 from lib.presets import TriagePresets
                 self.triage_preset = TriagePresets.default_preset
                 
                 ... other cool stuff...
                 
             def post_execute(self):
                pass
    """     

    @staticmethod
    def _get_triage_path():
        log_path = "%s%slogs"%(prepper.find_ae_path() ,os.path.sep)
        return os.path.join(log_path,TRIAGE_FILENAME)
    
    @staticmethod
    def _remove_triage_file():
        _file = TriagePresets._get_triage_path()
        if os.path.exists(_file):
            try:
                os.remove(_file)
            except:
                fwlog.warn("Failed to remove triage log file:%s"%_file)

    @staticmethod    
    def csi_log(msg):
        
        triage_file = TriagePresets._get_triage_path()
        with open(triage_file,mode='a+') as csi:
            csi.write(msg+"\n")
            csi.flush()
            csi.close()


    @staticmethod
    def default_preset(sut, suite, start_time=None, end_time=None):
        # removes the old triage log file
        TriagePresets._remove_triage_file()
        
        from test_procedures.cluster.hrm_state.search import LogSearch, LocateCoreFiles
        triage_tps = {}
        msg = " *****  FILE SEARCH  ******\n\n"
        for _node in sut.get_fldc_nodes():
            triage_tps[_node] = LogSearch(sut, suite)

            triage_tps[_node].run_asynch(node=_node,
                                   start_time=start_time,
                                   end_time=end_time)

        while any([tp.is_running() for tp in triage_tps.values()]):
            time.sleep(1)


        for fldc_node, triage_tp in triage_tps.items():
            core_files_pro = triage_tp.wait()
            _files =  core_files_pro.matches(sort_by='time', group_by='search_file')

            for k in _files:
                msg+="\n\n%s\n"%str(k)
                for v in _files[k]:
                    msg+=("  %s\n"%str(v[4]))
            
        
        # Write our message out to the csi log file 
        TriagePresets.csi_log(msg)
            
            
        msg = "\n\n\n *****  CORE SEARCH  ******\n"
        loc_core_tps = {}
        for _node in sut.get_fldc_nodes():
            loc_core_tps[_node] = LocateCoreFiles(sut, suite)
        
            loc_core_tps[_node].run_asynch(node=_node,
                                    start_time=start_time,
                                    end_time=end_time)

        while any([tp.is_running() for tp in loc_core_tps.values()]):
            time.sleep(1)

        for fldc_node, triage_tp in loc_core_tps.items():
            core_file_pro = triage_tp.wait()
            if core_file_pro.output is not None:
                for line in core_file_pro.output:
                    msg += "%s\n"%line
            else:
               msg += "No core files found.\n"
        
        TriagePresets.csi_log(msg)

        try: 
            pcfm_tp = cluster.hrm_state.search.GetPrimaryCfmNode(sut, suite)
            pcfm_pro = pcfm_tp.run(timeout=300)
            pcfm_node = pcfm_pro.primary_cfm()
        
            if pcfm_node is not None:
                msg = '\n\n Primary cfm node: %s'  % pcfm_node
                cluster_state_tp = cluster.hrm_state.report.ClusterState(sut, suite)
                cluster_state_pro = cluster_state_tp.run(node=pcfm_node )
                cluster_state = cluster_state_pro.state()      
                msg += '\n\n ****** CLUSTER STATE ****** \n %s' % cluster_state
                TriagePresets.csi_log(msg)

                collect_tp = cluster.hrm_state.gather.FluidCacheCollect(sut, suite)
                collect_pro = collect_tp.run(node=pcfm_node)
                file = collect_pro.output_file()
                msg = '\n\n ****** FLUID CACHE COLLECT ****** \n File: %s' % file
                TriagePresets.csi_log(msg)

                msg = "\n\n\n ***** JOURNAL DUMP  ******\n"
                jdump_tp = cluster.parse_journal.DumpJournal(sut, suite)
                jdump_pro = jdump_tp.run(node=pcfm_node)
                journal_dump_lines = jdump_pro.jdump_lines()
                for line in journal_dump_lines:
                    msg += '%s\n' %line
                TriagePresets.csi_log(msg)

                msg = "\n\n\n ***** EVENTS  DUMP  ******\n"
                dump_event_tp = cluster.parse_events.DumpEvents(sut, suite)
                dump_pro = dump_event_tp.run(node=pcfm_node)
                parse_event_tp = cluster.parse_events.ParseEventCatalog(sut, suite)
                parse_event_tp.run(node=pcfm_node)
                parsed_events = parse_event_tp.parseeventcatalog(dump_pro.eventlog())
                for eventlist in parsed_events:
                    msg += 'Event id: %s \n' % eventlist[0]
                    msg += 'Event time: %s \n' % eventlist[1]
                    msg += 'Event number: %s \n' % eventlist[2] 
                    msg += 'Event msgid: %s \n' % eventlist[3] 
                    msg += 'Event name: %s \n' % eventlist[4]
                    msg += 'Event severity: %s \n' % eventlist[5]
                    msg += 'Event description: %s \n' % eventlist[6]
                    msg += 'Event cause: %s \n' % eventlist[7]
                    msg += '===========================================\n'

                TriagePresets.csi_log(msg)
        
            else:
                msg = 'Cannot determine primary cfm...unable to get cluster state and collect fluid cache data'

        except:
            msg =  'not a multinode cluster...unable to determine primary cfm'
        

def find_test_run_data(sut, suite, test_run_data):
    
    
    os_abbr = {"Red Hat Enterprise Linux Server":"RHEL",
               "SUSE Linux Enterprise Server" : "SLES",
               "CentOS" : "CENT",
               "VSA" : "VSA"
              }
    
    for _node in sut.get_fldc_nodes():
        try:
            if not test_run_data.os_name or not test_run_data.os_version:
                tp = sys_ops.os_info.OSDistro(sut, suite)
                (distro, version, blah) = tp.run(node=_node).output
                test_run_data.os_name = os_abbr.get(distro.strip(),"Unknown")
                test_run_data.os_version = version
            if not test_run_data.revision:
                tp = cache.hrm_control.hcn.GetFldcVersion(sut, suite)
                rev = tp.run(node=_node, target_node=_node, lookup_node=_node).build_number()
                test_run_data.revision = rev
            if not test_run_data.build_type:
                tp = sys_ops.os_info.KernelRevision(sut, suite)
                if tp.run(node=_node).debug:
                    test_run_data.build_type ="Debug"
                else:
                    test_run_data.build_type ="Retail"
            break
        except:
            continue
    
    return test_run_data

