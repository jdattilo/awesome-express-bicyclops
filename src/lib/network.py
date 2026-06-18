import socket
import struct
from time import sleep

GHN_TIMEOUT = 4     # GetHostname timeout before we give up
GHN_SLEEP = 0.25    # time to sleep between GetHostname attempts
PORT_TIMEOUT = 60   # seconds to wait for port to become available

def get_local_ips():
    """ Returns a list of the local IP addresses """
    _ips = []
    _time = 0
    _ex = None
    while _time < GHN_TIMEOUT:
        try:
            info = socket.getaddrinfo(socket.gethostname(), None)
            for i in info:
                if i[0]==2:
                    _ips.append(i[4][0])
            return _ips
        except socket.gaierror, ex:
            _ex = ex
        _time += GHN_SLEEP
        sleep(GHN_SLEEP)
    raise _ex
    

def get_local_hostname():
    """ Returns the local hostname """
    _time = 0
    _ex = None
    while _time < GHN_TIMEOUT:
        try:
            return socket.gethostname()
        except socket.gaierror, ex:
            _ex = ex
        _time += GHN_SLEEP
        sleep(GHN_SLEEP)
    raise _ex


def get_available_port():
    """
     Return an available port in the ephemeral range.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('localhost', 0))
    addr, port = s.getsockname()
    s.close()
    return port


def wait_for_port(interface, port):
    """
     Waits for the specified port to become availabe.
     If port is still in use after PORT_TIMEOUT seconds,
     a socketerror is raise.
    """
    _time = 0
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    while _time < PORT_TIMEOUT:
        try:
            s.bind((interface, port ))
            addr, port = s.getsockname()
            s.close()
            return
        except socket.error:
            _time+=3
            sleep(3)
    raise 
            

def find_ports_pid(port):
    """ 
     Finds the PID of the python process bound to the port.
    """
    import psutil
    for proc in psutil.process_iter():
        if proc.name == 'python' or proc.name == 'python.exe':
            for con in proc.get_connections():
                _port = con.local_address[1]
                if _port == port:
                    return proc.pid


def is_ip_in_network(ip, network, mask):
    """
     Returns True|False if a given IP exists within a subnet. 
     :param ip: The interesting IP address
     :param network: The IP of the subnetwork domain we are searching
     :param mask: The mask of the subnetwork.
     """
     
    ip = struct.unpack('=L',socket.inet_aton(ip))[0]
    mask = struct.unpack('=L',socket.inet_aton(mask))[0]
    network = struct.unpack('=L',socket.inet_aton(network))[0]
         
    if not ((ip & mask) == (network & mask)):
        return False
    else:
        return True


