"""
    The pathing module provides a set of methods to help
    obtain path related values. Where possible paths will
    make use of contant values from /lib/constants.py to
    help make product-like name changes fairly easy to adapt.
    
    At this time 20120807 directory path separators assumed to
    be posix.
    
"""
import os
import sys
import posixpath
import constants
import string_extensions
from string import replace


def get_win_share(node):
    if sys.platform == 'linux2':
        #return "//%s\\\\c$" % string_extensions.get_host_only(node)
        return "//%s\\\\c$" % (node.ip)
    elif sys.platform == 'win32':
        #return "\\\\%s\\c$" % string_extensions.get_host_only(node)
        return "\\\\%s\\c$" % (node.ip)


def get_win_mp(node):
    if sys.platform == 'linux2':
        _p = posixpath.join(get_mountpoints_dir(),string_extensions.get_host_only(str(node)))
        return string_extensions.localize_path(_p)
    elif sys.platform == 'win32':
        return get_win_share(node)
        

def get_python_bin():  
    if sys.platform == 'win32':
        if os.path.exists(constants.PYTHON27_WIN32):
            return constants.PYTHON27_WIN32
    elif os.path.exists(constants.PYTHON27_LINUX):
            return constants.PYTHON27_LINUX
    else:
        return "python"
    

def get_home_dir():
    from os.path import expanduser
    return expanduser("~")


def get_tools_bin():
    try:
        from ae import prepper
        return (os.path.abspath(os.path.join(prepper.find_ae_path(),"..","tools","bin")))
    except ImportError:
        # just in case the ae package isn't found on the initial deploy
        pass

def get_tools_src():
    try:
        from ae import prepper
        return (os.path.abspath(os.path.join(prepper.find_ae_path(),"..","tools","src")))
    except ImportError:
        # just in case the ae package isn't found on the initial deploy
        pass


def get_testfiles():
    try:
        from ae import prepper
        return (os.path.abspath(os.path.join(prepper.find_ae_path(),"testfiles")))
    except ImportError:
        # just in case the ae package isn't found on the initial deploy
        pass



if __name__ == "__main__":
    print "Running checks..."
    import os
    
