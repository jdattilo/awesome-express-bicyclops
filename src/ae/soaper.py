import os
import sys
import time
import suds
import traceback
import threading
import logging
import ae_logger
import ae_errors
import environment
from lib import constants, fldc_objects, string_extensions, network
import xml.dom.minidom
import BaseHTTPServer, SimpleHTTPServer
import ssl
import base64
from tempfile import mkstemp
from suds.xsd.sxbasic import Import
from suds.transport.http import HttpAuthenticated
from mhlib import PATH



#############   SOAPER  EXTERNAL  LOGGING   #########################
#
# Offers the ability enable all of the underlying SUDS module logging.
#  
# WARNING: All modules running at DEBUG will generate a lot of log
#          data.
#
#
# To enable logging, change this to a valid file name.
#SOAP_LOG_FILE ="c:\\rub-a-dub.log"
# No file or commented out means no extra logging

try:
    fh = logging.FileHandler(filename=SOAP_LOG_FILE)
except:
    fh = logging.NullHandler()

_log = logging.getLogger('suds')
_log.addHandler(fh)

# Here are the most-used loggers associated with SOAP calls
# If desired, the log level can be adjusted
_log.getChild('client').setLevel(logging.DEBUG)
_log.getChild('transport').setLevel(logging.DEBUG)
_log.getChild('suds.sax').setLevel(logging.DEBUG)
_log.getChild('xsd.schema').setLevel(logging.INFO)
_log.getChild('wsdl').setLevel(logging.INFO)
_log.getChild('resolver').setLevel(logging.INFO)
_log.getChild('xsd.query').setLevel(logging.INFO)
_log.getChild('xsd.basic').setLevel(logging.INFO)
_log.getChild('binding.marshaller').setLevel(logging.INFO)
#####################################################################



class Soaper:
    """ 
     Wrapper class that does some setup of SUDS such that 
     we can work with the SOAP API a little easier. When 
     the Soaper class is instantiated, it builds builds a SOAP
     client to the given service and can be used to make requests.
     
     Required Args:
         sut - the AE2 sut object.
         
     Optional Args:
         node         - the node that we want to connect to (where the SOAP request is sent)
         api_name     - the API we want to use (HCC, HCN, etc)
         port         - port number where the SOAP service is running
         encrypted    - Boolean flag indicating which protocol (HTTP or HTTPS)
         auth_token   - cluster authentication key
         user_pass    - user:password string base64 encoded
         timeout      - timeout limit for a SOAP requests.
     
     Encryption:
         Soaper determines which transport protocol (HTTP | HTTPS) to use with our
         SOAP client based on the Soaper encryption flag passed in or depending on
         whether the encryption flag is set in the environment file and sut object.

         The order of encryption flag precedence is:
             1. The optional "encrypted" flag is set during Soaper declaration.
             2. The set in the environment file (sut.is_encrypted_flag())
     
     FLDC Authentication:
         There are two mechanisms for authentication to the HCN/HCC API:
             1) Using the a base64 encoded "user:password" string.
             2) Passing the AuthToken (available after HCC creation).
             
         Both of these strings can be passed directly in to Soaper when initialized
         or if nothing is passed in and Soaper does not have an AuthToken, it will 
         query the cluster for the AuthToken automatically using the HCC.GetAuthToken
         operation. If the AuthToken is avaiable, the token will be used for any subsequent
         API calls. 
         
         If no token is available (maybe the cluster isn't created yet) the
         user:pass encoded string will be used instead. These credentials are specified
         in the environment file (USERNAME & PASSWORD). If no credentials are found,
         the lab default ones are used.
         
         So to summarize the default behavior of Soaper is to query and use
         the AuthToken for SOAP calls. If no token is available encoded creds
         are used.
     
     Note:
        If the the node, api_name, or port are not specified, the SOAP service defaults
        to connecting to the HCN API. 
        
        
     
    """
    # Set our default client timeout
    DEFAULT_TIMEOUT = 120
    
    def __init__(self, sut, 
                 node=None, 
                 api_name=None, 
                 port=None,
                 encrypted=None,
                 auth_token=None,
                 user_pass=None,
                 timeout=None):
        self.sut            = sut       # our SUT object
        self.node           = node      # node to query. If none, the pCFM is found and used  
        self.api_name       = api_name  # which API we're going to use, defaults to HCCAPI
        self.port           = port      # port for the SOAP server
        self._suds_client   = None      # internal suds client member
        self._service       = None      # suds client service
        self._auth_token    = auth_token# Authentication token to pass in the HCC header
        self._user_pass     = user_pass # Base64binary encoded user:password (for getAuthToken)
        self._timeout       = timeout   # timeout for requests
        # Encryption flag to denote HTTP or HTTPS protocol
        if encrypted == None:
            self._encrypted = self.sut.is_encrypted_flag()
        else:
            self._encrypted = encrypted 


    def _setup_suds(self):
        
        if self.api_name == None:
            self.api_name = constants.HCNAPI_NAME
        if self._timeout == None:
            self._timeout = self.DEFAULT_TIMEOUT
        if self.node == None:
            self._connect_to_pcfm()
        else:
            self._connect_to_node(self.node)


    def _determine_transport(self):
        """
         Returns a tuple of the protocol and transport class eg:
          ('http', HttpAuthenticated() )
        """
        # return the proper transport class
        if self._encrypted == True:
            return ('https',HttpAuthenticated(timeout=self._timeout))
        else:
            return ('http',HttpAuthenticated(timeout=self._timeout))


    def _get_auth_token(self):
        # if the token is set, it must have been passed in
        if self._auth_token != None:
            return
        
        # No auth token so we need to call HccApi.GetAuthToken
        # For a vsa we'll pass in the specific node's credentials otherwise
        # we'll use the environment credentials (for backwards compatibility).
        _up64 = None
        if self.node.is_vsa():
            _up64 = base64.b64encode("%s:%s"%(self.node.username,self.node.password))
        else:
            _up64 = base64.b64encode("%s:%s"%(self.sut.username,self.sut.password))
        
        s = Soaper(self.sut,
                   self.node,
                   api_name=constants.HCNAPI_NAME,
                   encrypted=self._encrypted,
                   user_pass=_up64)
        
        hcc_id = None
        _hostname = None
        svc = s.get_service()
        hcns = svc.GetDiscoveredHcns()
        
        if self.node.is_vsa():
            _hostname = string_extensions.get_host_only(self.node.esx_host)
        else:
            _hostname = self.node.get_hostname_only()

        for hcn in hcns:
            hcn_hostname = string_extensions.get_host_only(hcn['hostname'])
            if hcn_hostname == _hostname:
                try:
                    hcc_id = hcn['hccId']
                    if hcc_id == None or hcc_id == "":
                        return None
                    break
                except KeyError:
                    return None
                    
        if hcc_id != None:
            return str(svc.GetAuthToken(hccId=hcc_id))
        else:
            return None

            
    def _connect_to_node(self, node):
        
        # build the web service and WSDL file URLS and set the
        # appropriate transport object respective to the protocol
        (proto,transport) = self._determine_transport()
        
        # set our encryption ports
        if self._encrypted == True:
            if self.port == constants.HCNAPI_PORT:
                self.port = constants.HCNAPI_SPORT
            elif self.port == constants.HCCAPI_PORT:
                self.port = constants.HCCAPI_SPORT
            elif self.port == None:
                self.port = constants.HCNAPI_SPORT
        else:
            if self.port == None:
                self.port = constants.HCNAPI_PORT
        
        if isinstance(node, environment.Node) == True:
            node = node.ip
        svc_url = "%s://%s:%s/%s"%(proto, node, self.port, self.api_name)
        ws_file = "%s://%s:%s/%s.wsdl"%(proto, node, self.port, self.api_name)
        
        # bind the w3.org includes to local copies of the files
        #from lib import pathing
        #w3 =os.path.join(pathing.get_tools_src(),'w3_org')
        #xop = "file://%s" % os.path.join(w3,'2004_08_xop_include.xml')
        #mime = "file://%s" % os.path.join(w3,'2005_05_xmlmime.xml')
        #
        
        Import.bind("http://www.w3.org/2004/08/xop/include",
                    "suds://www.w3.org/2004/08/xop/include" )
        Import.bind("http://www.w3.org/2005/05/xmlmime",
                    "suds://www.w3.org/2005/05/xmlmime")

        
        self._suds_client = suds.client.Client(
                                               ws_file,
                                               location=svc_url,
                                               timeout=self._timeout,
                                               transport = transport
                                               )
    
        
        header = self._suds_client.factory.create('HccApiHeader')
        if self._auth_token != None:
            header.authToken = self._auth_token
        elif self._user_pass != None:
            header.userPass = self._user_pass
        else:
            self._auth_token = self._get_auth_token()
            if self._auth_token == None:
                if self.node.is_vsa():
                    header.userPass = base64.b64encode("%s:%s"%(self.node.username,self.node.password))
                else:
                    header.userPass=base64.b64encode("%s:%s"%(self.sut.username,self.sut.password))
            else:
                header.authToken = self._auth_token
            
        
        self._suds_client.set_options(soapheaders=header)    
        self._service = self._suds_client.service

    
    def _connect_to_pcfm(self):
        """
         Finds an available node within the cluster, determines
         who the primary CFM is and then connects to that node.
         
         NOTE: We're currently assuming IPv4 will be available
               and that the port will be the same on all nodes.
        """
        raise NotImplementedError("soaper._connect_to_pcfm is not for use.")
        for node in self.sut.nodes:
            self._connect_to_node(node)
            # TODO: We'll need to pass in the hccID
            addy_list = self._service.GetPrimaryCfmAddresses()
            for addy in addy_list:
                ipv4 = addy["ipAddress"]["ipv4Addr"]
                
                if ipv4 == node.ip or ipv4 == "127.0.0.1":
                    print "pCFM is [%s]"%node
                    return
        
        
    def get_service(self):
        """
         Returns a reference to the SUDS client service.
         SOAP calls can be made against this...
        """
        
        if self._service == None:
            self._setup_suds()
        
        return self._service
    
    
    def get_last_rcvd_doc(self):
        """
         Returns the last received SOAP XML document containing
         both the SOAP header and body. 
        """
        if self._suds_client == None:
            raise Exception("SUDS client not initialized")
        return self._suds_client.last_received()

    def get_last_sent_doc(self):
        """
         Returns the last sent SOAP XML document containing
         both the SOAP header and body. 
        """
        if self._suds_client == None:
            raise Exception("SUDS client not initialized")
        return self._suds_client.last_sent()


    
    

class EventListener():
    """
     The EventListener provides for starting a SOAP server and
     listening for events. This assumes that the any "event handler"
     registration takes place elsewhere.
     
     :param sut: The SUT object
     :param port: Port to listen on. A None value will use a dynamic port.
     :param ip: netif to listen on. None will use all local netifs.
     :param wsdl_url: location of the WSDL file. used for object destruction... IIRC
    """
    
    DEFAULT_NS = "http://api.hcc.fluidcache.dell.com/"
    
    def __init__(self, sut, port=None, ip=None, wsdl_url=None, ns=None):
        self.sut = sut
        self.ip = ip
        self.port = port
        self._events = []
        self._dispatcher = None
        self._httpd = None
        self._wsdl_url = wsdl_url
        self._ns = ns
        self.log = None
        self._encrypted = None
        self._server_cert = None
        self._error = None
        
        self._setup_log()
        self._do_ssl_prep()
        
    def __del__(self):
        try:
            self._httpd.shutdown()
            self._httpd = None
        except:
            pass
        try:
            os.remove(self._server_cert)
        except:
            pass

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
    
    def ReceiveEvent(self, events=None):
    
        if events == None:
            return

        for event in events:
            # Process event arguments into dictionary
            evt_args = {}
            for evt_arg in event['eventArgs'] if ('eventArgs' in event) else []:
                evt_arg_type = evt_arg['argType']
                evt_arg_value = evt_arg['argText']
                if evt_arg_type in evt_args:
                    # This log message and exception may be hidden
                    self.log.error('Event id[%s] arg [%s:%s] already has value [%s]' %
                                   (event['eventId'],
                                    evt_arg_type,
                                    evt_arg_value,
                                    evt_args[evt_arg_type]))
                    # Comment out till HRM-2633 is resolved
                    # raise Exception('Event contained duplicate argument types')
                else:
                    evt_args[evt_arg_type] = evt_arg_value

            if not evt_args:
                evt_args = None

            evt_obj = fldc_objects.Event(event["eventId"],
                                         evt_args=evt_args,
                                         catalog_number=event["catalogNumber"],
                                         sequence=event["eventSequence"],
                                         text=event["eventText"],
                                         severity=event["severity"],
                                         evt_time=event["time"]
                                         )
            self.log.debug("Received event:%s"%evt_obj)
            self._events.append(evt_obj)

    def _do_ssl_prep(self):
        """
         Performs some necessary work to setup the HTTPS
         server such as writing the server pem file out
         to a temporary file.
        """
        if self.sut.is_encrypted_flag():
            self._encrypted = True
            (_fd, self._server_cert) = mkstemp()
            _file = os.fdopen(_fd,'w')
            _file.write(SERVER_CERT_CONTENTS)
            _file.flush()
            _file.close
        else:
            self._encrypted = False

        
    def _prep_dispatcher(self):
        """
         Prepares and registers the the SOAP dispatcher such
         that it is available for requests.
        """
        
        if self._ns == None:
            self._ns = self.DEFAULT_NS 
        
        self._dispatcher = SoapDispatcher(
                                         'EventListener_dispatcher',
                                         location = self._wsdl_url,
                                         namespace=self._ns,
                                         ns=True
                                         )
        # the simpleSoap wsdl parsing and complex type translation doesn't work 
        # so we have to define the types in our own structure and register them
        # to the SOAP dispatcher along with the SOAP operation
        self._dispatcher.register_function('ReceiveEvent', self.ReceiveEvent,
                                          args={"events":[{
                                                           'eventObject':{
                                                                          'catalogNumber':int,
                                                                          'eventArgs':[{'eventArg':{
                                                                                                    'argText':'string',
                                                                                                    'argType':'eventArgType'
                                                                                                   }
                                                                                      }],
                                                                          'eventId':int,
                                                                          'eventSequence':int,
                                                                          'eventText':'string',
                                                                          'severity':'eventSeverity',
                                                                          'time': 'dateTime'
                                                                          }
                                                           }]
                                                }
                                            )        

    
    def start(self):
        """
         Start listening for events. 
         If the event listener fails to start (maybe the port is already
         in use) we wait a second and then attempt starting the server again.
        """
        retry_attempts = 5
        retry_sleep_time = 1
        
        while retry_attempts > 0:
            try:
                if self.port == None:
                   self.port = 0
                if self.ip == None:
                    self._httpd = BaseHTTPServer.HTTPServer(("", self.port), SOAPHandler)
                else:
                    self._httpd = BaseHTTPServer.HTTPServer((self.ip, self.port), SOAPHandler)
                """ get and set the new bind port """
                self.port=self._httpd.server_port
                if self.port == 0 or self.port == None:
                   self.log.error("no bind port yet retrying up to %d more times(s)" % retry_attempts)
                   retry_attempts -= 1
                   time.sleep(retry_sleep_time)
                else:
                   break
            except Exception as ex:
                self._error = ex
                exc_type, exc_value, exc_traceback = sys.exc_info()
                lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
                self.log.error("Exception when trying to start event listener: %s" % lines[2:])
                self.log.error("Retrying up to %s more times(s)" % retry_attempts)
                retry_attempts -= 1
                time.sleep(retry_sleep_time)
            else:
                # If the try succeeded, clear any prior logged errors
                self._error = None

        """ must have a bind port now """
        if self.port == 0 or self.port == None:
           raise ae_errors.TestProcedureError(message='no bind port')
        else:
           self.log.info("got bind port %d" % self.port)

        # If the retry loop failed to ever instantiate a HTTP server, raise the exception
        if self._error:
            raise self._error

        if self._encrypted == True:                    
            self._httpd.socket = ssl.wrap_socket (self._httpd.socket, certfile=self._server_cert, server_side=True)
            
        self._prep_dispatcher()
        self._httpd.dispatcher = self._dispatcher
        
        def _serve_forever():
            try:
                self._httpd.serve_forever()
            except Exception, ex:
                self._error = ex
            
        t = threading.Thread(target=_serve_forever)
        t.start()
        # re-raise any error that occurs during startup
        if self._error:
            raise self._error
    
    
    def stop(self):
        """ Stop listening for events """
        self._httpd.shutdown()
        if self._error:
            raise self._error
    
    
    def get_events(self):
        """ 
         Returns the list of events that the listener has received.
        """
        return self._events

    
    def wait(self, events, timeout=None):
        """
         Waits for a specific event to be received.
        """
        if not events:
            raise ae_errors.TestProcedureError(message='Events to wait for are required')

        if not isinstance(events, list):
            events = [events]
        
        WAIT_INTERVAL = 1
        time_waited = 0

        matching_events = []

        while timeout == None or time_waited < timeout:
            for e in self.get_events():
                if e in events:
                    matching_events.append(e)
                    break

            if matching_events:
                break

            time.sleep(WAIT_INTERVAL)
            time_waited += WAIT_INTERVAL

        if not matching_events:
            raise ae_errors.TestProcedureTimoutError(message='Timeout exceeded waiting for events')
        
        return matching_events
        
    def on_event(self, event_id, action):
        """ 
        Waits for a given and event and performs some action
        when the correct event is received.
        """
        raise NotImplementedError("Don't use me.")
        


###############################################################################
#
# Below are the heavily modified classes from pySimpleSoap v1.05
# These classes are used by EventListener to do great things.
#
###############################################################################


from decimal import Decimal
TYPE_MAP = {str:'string',unicode:'string',
            bool:'boolean', int:'short',
            int:'int', long:'long', int:'integer', 
            float:'float', Decimal:'decimal'
            }

REVERSE_TYPE_MAP = dict([(v,k) for k,v in TYPE_MAP.items()])




class SoapDispatcher(object):
    """Simple Dispatcher for SOAP Server"""
    
    def __init__(self, name, documentation='', action='', location='', 
                 namespace=None, prefix=False, 
                 soap_uri="http://schemas.xmlsoap.org/soap/envelope/", 
                 soap_ns='soap',
                 **kwargs):
        self.methods = {}
        self.name = name
        self.documentation = documentation
        self.action = action # base SoapAction
        self.location = location
        self.namespace = namespace # targetNamespace
        self.prefix = prefix
        self.soap_ns = soap_ns
        self.soap_uri = soap_uri
    
    def register_function(self, name, fn, returns=None, args=None, doc=None):
        self.methods[name] = fn, returns, args, doc or getattr(fn,"__doc__","")
        
    def dispatch(self, xml, action=None):
        """Receive and proccess SOAP call"""
        # default values:
        prefix = self.prefix
        ret = fault = None
        soap_ns, soap_uri = self.soap_ns, self.soap_uri
        soap_fault_code = 'VersionMismatch'
        name = None

        try:
            request = SimpleXMLElement(xml, namespace=self.namespace)

            # detect soap prefix and uri (xmlns attributes of Envelope)
            for k, v in request[:]:
                if v in ("http://schemas.xmlsoap.org/soap/envelope/",
                                  "http://www.w3.org/2003/05/soap-env",):
                    soap_ns = request.attributes()[k].localName
                    soap_uri = request.attributes()[k].value
            
            soap_fault_code = 'Client'
            
            
            #import xml.dom.minidom as foo
            #_xml = foo.parseString(xml)
            #print _xml.toprettyxml()
            
            # parse request message and get local method            
            method = request('Body', ns=soap_uri).children()(0)
            if action:
                # method name = action 
                name = action[len(self.action)+1:-1]
                prefix = self.prefix
            if not action or not name:
                # method name = input message name
                name = method.get_local_name()
                prefix = method.get_prefix()

            function, returns_types, args_types, doc = self.methods[name]
        
            # de-serialize parameters (if type definitions given)
            if args_types:
                #print "arg_types:%s"%args_types
                args = method.children()._from_xml(args_types)
            elif args_types is None:
                args = {'request':method} # send raw request
            else:
                args = {} # no parameters
 
            soap_fault_code = 'Server'
            # execute function
            ret = function(**args)

        except Exception, e:
            import sys
            etype, evalue, etb = sys.exc_info()
            import traceback
            detail = ''.join(traceback.format_exception(etype, evalue, etb))
            detail += '\n\nXML REQUEST\n\n' + xml
            fault = {'faultcode': "%s.%s" % (soap_fault_code, etype.__name__), 
                     'faultstring': unicode(evalue), 
                     'detail': detail}

        # build response message
        if not prefix:
            xml = """<%(soap_ns)s:Envelope xmlns:%(soap_ns)s="%(soap_uri)s"/>"""  
        else:
            xml = """<%(soap_ns)s:Envelope xmlns:%(soap_ns)s="%(soap_uri)s"
                       xmlns:%(prefix)s="%(namespace)s"/>"""  
            
        xml = xml % {'namespace': self.namespace, 'prefix': prefix,
                     'soap_ns': soap_ns, 'soap_uri': soap_uri}

        response = SimpleXMLElement(xml, namespace=self.namespace,
                                    prefix=prefix)
    
        response['xmlns:xsi'] = "http://www.w3.org/2001/XMLSchema-instance"
        response['xmlns:xsd'] = "http://www.w3.org/2001/XMLSchema"

        body = response.add_child("%s:Body" % soap_ns, ns=False)
        if fault:
            raise TypeError("A fault occurred while receiving the event:\n%s"%fault)
        else:
            # return normal value
            res = body.add_child("%sResponse" % name, ns=prefix)
            if not prefix:
                res['xmlns'] = self.namespace # add target namespace

            # serialize returned values (response) if type definition available
            if returns_types:
                if not isinstance(ret, dict):
                    res._to_xml(returns_types.keys()[0], ret, )
                else:
                    for k,v in ret.items():
                        res._to_xml(k, v)
            elif returns_types is None:
                # merge xmlelement returned
                res.import_node(ret)

        return response.as_xml()

    # Introspection functions:

    def list_methods(self):
        """Return a list of aregistered operations"""
        return [(method, doc) for method, (function, returns, args, doc) in self.methods.items()] 

    def help(self, method=None):
        """Generate sample request and response messages"""
        (function, returns, args, doc) = self.methods[method]
        xml = """
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
<soap:Body><%(method)s xmlns="%(namespace)s"/></soap:Body>
</soap:Envelope>"""  % {'method':method, 'namespace':self.namespace}
        request = SimpleXMLElement(xml, namespace=self.namespace, prefix=self.prefix)
        if args:
            items = args.items()
        elif args is None:
            items = [('value', None)]
        else:
            items = []
        for k,v in items:
            request(method)._to_xml(k, v, add_comments=True, ns=False)

        xml = """
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
<soap:Body><%(method)sResponse xmlns="%(namespace)s"/></soap:Body>
</soap:Envelope>"""  % {'method':method, 'namespace':self.namespace}
        response = SimpleXMLElement(xml, namespace=self.namespace, prefix=self.prefix)
        if returns:
            items = returns.items()
        elif args is None:
            items = [('value', None)]
        else:
            items = []
        for k,v in items:
            response('%sResponse'%method)._to_xml(k, v, add_comments=True, ns=False)

        return request.as_xml(pretty=True), response.as_xml(pretty=True), doc


   

from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
class SOAPHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        """User viewable help information and wsdl"""
        args = self.path[1:].split("?")
        if self.path != "/" and args[0] not in self.server.dispatcher.methods.keys():
            self.send_error(404, "Method not found: %s" % args[0])
        else:
            if self.path == "/":
                # return wsdl if no method supplied
                response = self.server.dispatcher.wsdl()
            else:
                # return supplied method help (?request or ?response messages)
                req, res, doc = self.server.dispatcher.help(args[0])
                if len(args)==1 or args[1]=="request":
                    response = req
                else:
                    response = res                
            self.send_response(200)
            self.send_header("Content-type", "text/xml")
            self.end_headers()
            self.wfile.write(response)

    def do_POST(self):
        """SOAP POST gateway"""
        self.send_response(200)
        self.send_header("Content-type", "text/xml")
        self.end_headers()
        request = self.rfile.read(int(self.headers.getheader('content-length')))
        try:
            response = self.server.dispatcher.dispatch(request)
            self.wfile.write(response)
        except TypeError, ex:
            if ex.message.find('NewPrimaryCfmAddresses') > -1:
                pass
            else:
                raise ex

    def log_message(self, format, *args):
        _log.debug(format%args)


def get_nested_type(d, my_key):
    """
     Parses some python nested dictionary-list structure
     and returns the type associated with key my_key.
    """
    if my_key in d:
        if isinstance(d[my_key],dict):
            return {}
        return (d[my_key])
    
    for k in d:
        try:
            if isinstance(d[k], dict):
                return get_nested_type(d[k],my_key)
            else:
                if isinstance(d[k], list):
                    for item in d[k]:
                        if isinstance(item, dict):
                            return get_nested_type(item,my_key)
        except:
            return get_nested_type(k,my_key)
    return None


class SimpleXMLElement(object):
    
    def __init__(self, text = None, elements = None, document = None, namespace = None, prefix=None):
        self.__ns = namespace
        self.__prefix = prefix
        if text:
            try:
                self.__document = xml.dom.minidom.parseString(text)
            except:
                raise
            self.__elements = [self.__document.documentElement]
        else:
            self.__elements = elements
            self.__document = document
    
    def add_child(self,name,text=None,ns=True):
        if not ns or not self.__ns:
            element = self.__document.createElement(name)
        else:
            if self.__prefix:
                element = self.__document.createElementNS(self.__ns, "%s:%s" % (self.__prefix, name))
            else:
                element = self.__document.createElementNS(self.__ns, name)
        # don't append null tags!
        if text is not None:
            if isinstance(text, unicode):
                element.appendChild(self.__document.createTextNode(text))
            else:
                element.appendChild(self.__document.createTextNode(str(text)))
        self._element.appendChild(element)
        return SimpleXMLElement(
                    elements=[element],
                    document=self.__document,
                    namespace=self.__ns,
                    prefix=self.__prefix)
    
    def __setattr__(self, tag, text):
        """Add text child tag node (short form)"""
        if tag.startswith("_"):
            object.__setattr__(self, tag, text)
        else:
            self.add_child(tag,text)

    def __delattr__(self, tag):
        """Remove a child tag (non recursive!)"""
        elements=[__element for __element in self._element.childNodes
                          if __element.nodeType == __element.ELEMENT_NODE
                         ]
        for element in elements:
            self._element.removeChild(element)

    def add_comment(self, data):
        """Add an xml comment to this child"""
        comment = self.__document.createComment(data)
        self._element.appendChild(comment)

    def as_xml(self,filename=None,pretty=False):
        """Return the XML representation of the document"""
        if not pretty:
            return self.__document.toxml('UTF-8')
        else:
            return self.__document.toprettyxml(encoding='UTF-8')

    def __repr__(self):
        """Return the XML representation of this tag"""
        return self._element.toxml('UTF-8')

    def get_name(self):
        """Return the tag name of this node"""
        return self._element.tagName

    def get_local_name(self):
        """Return the tag loca name (prefix:name) of this node"""
        return self._element.localName

    def get_prefix(self):
        """Return the namespace prefix of this node"""
        return self._element.prefix

    def get_namespace_uri(self, ns):
        """Return the namespace uri for a prefix"""
        element = self._element
        while element is not None and element.attributes is not None:
            try:
                return element.attributes['xmlns:%s' % ns].value
            except KeyError:
                element = element.parentNode



    def attributes(self):
        """Return a dict of attributes for this tag"""
        #TODO: use slice syntax [:]?
        return self._element.attributes

    def __getitem__(self, item):
        """Return xml tag attribute value or a slice of attributes (iter)"""
        if isinstance(item,basestring):
            if self._element.hasAttribute(item):
                return self._element.attributes[item].value
        elif isinstance(item, slice):
            # return a list with name:values
            return self._element.attributes.items()[item]
        else:
            # return element by index (position)
            element = self.__elements[item]
            return SimpleXMLElement(
                    elements=[element],
                    document=self.__document,
                    namespace=self.__ns,
                    prefix=self.__prefix)
            
    def add_attribute(self, name, value):
        """Set an attribute value from a string"""
        self._element.setAttribute(name, value)
 
    def __setitem__(self, item, value):
        """Set an attribute value"""
        if isinstance(item,basestring):
            self.add_attribute(item, value)
        elif isinstance(item, slice):
            # set multiple attributes at once
            for k, v in value.items():
                self.add_attribute(k, v)

    def __call__(self, tag=None, ns=None, children=False, root=False,
                 error=True, ):
        """Search (even in child nodes) and return a child tag by name"""
        try:
            if root:
                # return entire document
                return SimpleXMLElement(
                    elements=[self.__document.documentElement],
                    document=self.__document,
                    namespace=self.__ns,
                    prefix=self.__prefix
                )
            if tag is None:
                # if no name given, iterate over siblings (same level)
                return self.__iter__()
            if children:
                # future: filter children? by ns?
                return self.children()
            elements = None
            if isinstance(tag, int):
                # return tag by index
                elements=[self.__elements[tag]]
            if ns and not elements:
                for ns_uri in isinstance(ns, (tuple, list)) and ns or (ns, ):
                    elements = self._element.getElementsByTagNameNS(ns_uri, tag)
                    if elements: 
                        break
            if self.__ns and not elements:
                elements = self._element.getElementsByTagNameNS(self.__ns, tag)
            if not elements:
                elements = self._element.getElementsByTagName(tag)
            if not elements:
                if error:
                    raise AttributeError(u"No elements found")
                else:
                    return
            return SimpleXMLElement(
                elements=elements,
                document=self.__document,
                namespace=self.__ns,
                prefix=self.__prefix)
        except AttributeError, e:
            raise AttributeError(u"Tag not found: %s (%s)" % (tag, unicode(e)))

    def __getattr__(self, tag):
        """Shortcut for __call__"""
        return self.__call__(tag)
        
    def __iter__(self):
        """Iterate over xml tags at this level"""
        try:
            for __element in self.__elements:
                yield SimpleXMLElement(
                    elements=[__element],
                    document=self.__document,
                    namespace=self.__ns,
                    prefix=self.__prefix)
        except:
            raise

    def __dir__(self):
        """List xml children tags names"""
        return [node.tagName for node 
                in self._element.childNodes
                if node.nodeType != node.TEXT_NODE]

    def children(self):
        """Return xml children tags element"""
        elements=[__element for __element in self._element.childNodes
                          if __element.nodeType == __element.ELEMENT_NODE]
        if not elements:
            return None
            #raise IndexError("Tag %s has no children" % self._element.tagName)
        return SimpleXMLElement(
                elements=elements,
                document=self.__document,
                namespace=self.__ns,
                prefix=self.__prefix)

    def __len__(self):
        """Return elements count"""
        return len(self.__elements)
        
    def __contains__( self, item):
        """Search for a tag name in this element or child nodes"""
        return self._element.getElementsByTagName(item)
    
    def __unicode__(self):
        """Returns the unicode text nodes of the current element"""
        if self._element.childNodes:
            rc = u""
            for node in self._element.childNodes:
                if node.nodeType == node.TEXT_NODE:
                    rc = rc + node.data
            return rc
        return ''
    
    def __str__(self):
        """Returns the str text nodes of the current element"""
        return unicode(self).encode("utf8","ignore")

    def __int__(self):
        """Returns the integer value of the current element"""
        return int(self.__str__())

    def __float__(self):
        """Returns the float value of the current element"""
        try:
            return float(self.__str__())
        except:
            raise IndexError(self._element.toxml())    
    
    _element = property(lambda self: self.__elements[0])



    def _from_xml(self, types, strict=True):
        """
         Convert to python values the current serialized xml element
         types is a dict of {tag name: convertion function}
         strict=False to use default type conversion if not specified
         example:: types={'p': {'a': int,'b': int}, 'c': [{'d':str}]}
           expected xml:: <p><a>1</a><b>2</b></p><c><d>hola</d><d>chau</d>
           returnde value:: {'p': {'a':1,'b':2}, `'c':[{'d':'hola'},{'d':'chau'}]}
        """
        d = {}
        
        for node in self():
            #fn=None
            name = str(node.get_local_name())
            #print ("_from_xml %s"%name)
            try:
                #print "Checking for type:",name
                fn = types[name]
                #print "fn is set :%s"% types[name]
            except Exception, e:
                if 'xsi:type' in node.attributes().keys():
                    #print "checking xsi:type"
                    xsd_type = node['xsi:type'].split(":")[1]
                    try:
                        #print"looking up %s"%xsd_type
                        fn = REVERSE_TYPE_MAP[xsd_type]
                    except:
                        try:
                            #print"name:%s"%name
                            fn = get_nested_type(types,name)
                            #print "fn is now",fn
                        except:
                            pass
                            #print"failed to get nested type"

                elif strict:
                    raise TypeError(u"Tag: %s invalid (type not found)" % (name,))
                else:
                    # if not strict, use default type conversion
                    fn = unicode
            if isinstance(fn,list):
                
                value = d.setdefault(name, [])
                try:
                    _key = fn[0].keys()[0]
                    _d = get_nested_type(types,_key)
                    children = node.children()
                    value.append(children._from_xml(fn, strict))
                except:
                    #print "Was not a dict"
                    children = node.children()
                    for child in children and children() or []:
                        #print "child:%s"%child
                        #print "fn:%s"%fn
                        value.append(child._from_xml(fn, strict))
            elif isinstance(fn,dict):
                #print "fn is dict"
                children = node.children()
                value = children and children._from_xml(fn, strict)
            else:
                if fn is None:
                    #print "fn is None"
                    value = node
                elif str(node) or fn == str:
                    #print "fn is str"
                    try:
                        if fn == str:
                            value = unicode(node)
                        else:
                            value = fn(unicode(node))
                    except Exception:
                        value = unicode(node)
                else:
                    #print "fn is somthing else%s"%fn
                    value = None
            d[name] = value
        return d

    def _to_xml(self, name, value, add_child=True, add_comments=False, 
                 ns=False, add_children_ns=True):
        """
         Converts some python data structure to XML. 
         
         This method is from the pysimplesoap.simplexml module and
         originally named 'marhsall'.
         
         *****   This has not been thoroughly tested   ****
         
         Given how many changes were necessary to the "unmashalling" method, 
         there is certainly going to be some work required should we ever
         want to use this to have the service generate some response back...
         and if that day ever comes - just shove me out the window.
        """
        if isinstance(value, dict):  # serialize dict (<key>value</key>)
            child = add_child and self.add_child(name,ns=ns) or self
            for k,v in value.items():
                if not add_children_ns:
                    ns = False
                child._to_xml(k, v, add_comments=add_comments, ns=ns)
        elif isinstance(value, tuple):  # serialize tuple (<key>value</key>)
            child = add_child and self.add_child(name,ns=ns) or self
            if not add_children_ns:
                ns = False
            for k,v in value:
                getattr(self,name)._to_xml(k, v, add_comments=add_comments, ns=ns)
        elif isinstance(value, list): # serialize lists
            child=self.add_child(name,ns=ns)
            if not add_children_ns:
                ns = False
            if add_comments:
                child.add_comment("Repetitive array of:")
            for t in value:
                child._to_xml(name,t, False, add_comments=add_comments, ns=ns)
        elif isinstance(value, basestring): # do not convert strings or unicodes
            self.add_child(name,value,ns=ns)
        elif value is None: # sent a empty tag?
            self.add_child(name,ns=ns)
        elif value in TYPE_MAP.keys():
            # add commented placeholders for simple tipes (for examples/help only)
            child = self.add_child(name,ns=ns) 
            child.add_comment(TYPE_MAP[value])
        else: # the rest of object types are converted to string 
            # get special serialization function (if any)
            fn = basestring
            self.add_child(name,fn(value),ns=ns) 

    def import_node(self, other):
        try:
            x = self.__document.importNode(other._element, True)  # deep copy
            self._element.appendChild(x)
        except:
            pass


SERVER_CERT_CONTENTS="""-----BEGIN PRIVATE KEY-----
MIICdQIBADANBgkqhkiG9w0BAQEFAASCAl8wggJbAgEAAoGBAJZAFqY1XgWf0vfW
L1udYmLey/3HD8CjmBBcVKPwNTBfhuRHkb+/02b07aJ13TzKvwovas2gyXodBGVe
1iGEg6su+Josi+BIGeIb/vhpNZeSbZ5sXxurDtszFCGqCXYk5H8t9qB6WCH+pBZ0
b2O914u14kx/vy72YSNy26LiugcvAgMBAAECgYBpQOAc8wm4euu5PkvSq//+LwFL
+CTq2C9wVp3ccitwhZrjU9egMesQFshZpKOlMIp/whPZlKdPagBoWvU6abAqKlxA
qEW/NVYrKlV5jalcfon2Z0S8LjqfPqY0uLp1HnDhTAKxIJaXXA60+qz3zoZcCDeh
NDgo+Fp/JZMt+4iaoQJBAMe0Ghnh65Zt0RQ9ntFQlNG99+AAPkdFmX/CNpIBOCKI
nqRnzte0K2MCPIz1561OLpIPfkP+wmuXjPTeK6t9S+kCQQDAmyAVIFQplauFCT/K
tdX6GGu2m+Scb2ULyGGPHtwe8S9YaPNdHnAKjVvU1uSqF05+akSA/+KE24BMe8Gb
xYNXAkAuA/zjq9/6CJHdpRk8R+IStkAweD3hdFMbUif62pcRtgNABL9vio9YwAIt
xNe+Yj5u320Lw98OpZwQLEVJvZRJAkAt9VYEdIBgo9wXlItqPVVfpfAd1LkKMvJz
i07sLbrsjzRy7igT8i1d9zkQYm6Rv5n1RDowZd6RQScuGOGr38dlAkB0wx8SkeVM
F95oFfA5ny6yIeDREHF73PNSWm2IuHDruDTUhrpl/iKoaVsgI/xr8czWzPwzzNBx
6goMjsOH4NWu
-----END PRIVATE KEY-----
-----BEGIN CERTIFICATE-----
MIICWDCCAcGgAwIBAgIJALtmLk4+gQv1MA0GCSqGSIb3DQEBBQUAMEUxCzAJBgNV
BAYTAkFVMRMwEQYDVQQIDApTb21lLVN0YXRlMSEwHwYDVQQKDBhJbnRlcm5ldCBX
aWRnaXRzIFB0eSBMdGQwHhcNMTMwNjI3MjM0NTIwWhcNMTQwNjI3MjM0NTIwWjBF
MQswCQYDVQQGEwJBVTETMBEGA1UECAwKU29tZS1TdGF0ZTEhMB8GA1UECgwYSW50
ZXJuZXQgV2lkZ2l0cyBQdHkgTHRkMIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKB
gQCWQBamNV4Fn9L31i9bnWJi3sv9xw/Ao5gQXFSj8DUwX4bkR5G/v9Nm9O2idd08
yr8KL2rNoMl6HQRlXtYhhIOrLviaLIvgSBniG/74aTWXkm2ebF8bqw7bMxQhqgl2
JOR/Lfagelgh/qQWdG9jvdeLteJMf78u9mEjctui4roHLwIDAQABo1AwTjAdBgNV
HQ4EFgQU+yfYmst86KdnmfUhw2KxxmO9s+AwHwYDVR0jBBgwFoAU+yfYmst86Kdn
mfUhw2KxxmO9s+AwDAYDVR0TBAUwAwEB/zANBgkqhkiG9w0BAQUFAAOBgQAp/O+C
PUlFbLTJkSDoSwUxlL8+zRUEZMO8PjmG2U3MvghYuyC/MC3SW58z6N+kRHji5e3W
R0vTXGLsiAhew4rRtJVQfq6rdyhmCjiquGsf8gnVDdHyrEfwpSwocgwtztpbOlEt
chnyzCW5WUFnoA0TKlnNuswO8mUnqNHvVniDnQ==
-----END CERTIFICATE-----"""

if __name__ == "__main__":
    
    from loader import Loader
    from lib import constants
    
    s = os.path.sep
    suite_file1 = "..%ssuite_files%sexamples%ssuite_ex.cfg" % ( os.path.sep, os.path.sep,os.path.sep)
    env_file1 = "..%senv_files%susers%scpowers%satlvm034_to_atl2-4.cfg" % ( s,s,s,s)

    (suite,sut) = Loader.get_run_info(suite_file1,env_file1)
    print sut
    
    s = Soaper(sut,node=sut.nodes[0], api_name=constants.HCNAPI_NAME)
    svc = s.get_service()
    print "making request...."
    svc.GetDiscoveredHcns()
    print "request done"
    try:
        #svc.GetDiscoveredHcns()
        
        #client = s._suds_client
        #hcnArgsL = []
        #hcnArgumentObject = client.factory.create("hcnArgumentObject")
        #hcnArgumentObject.hcnId = "ad48f992-d56f-46f0-8985-a6bbfc1eaa3f"
        #hcnArgumentObject.cfmEligible = True
        #hcnArgsL.append(hcnArgumentObject)
        #create_response = svc.CreateHcc(userToken="tok", hccName="foo",hcnArgs=hcnArgsL )
        #svc.CreateHcc(hcnId="ad48f992-d56f-46f0-8985-a6bbfc1eaa3f")
        
        svc.GetCacheDevices(hccId="044f8103-ab76-40d2-bff3-99e2cad21e32")
        print "LAST SENT:\n%s"%s.get_last_sent_doc()
        print "LAST RCVD:\n%s"%s.get_last_rcvd_doc()
    except Exception,ex:
        print "LAST SENT:\n%s"%s.get_last_sent_doc()
        print "LAST RCVD:\n%s"%s.get_last_rcvd_doc()
        raise
        
