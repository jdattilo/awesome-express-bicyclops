"""
A collection of useful general purpose string methods.

Depending on how much is needed here, we may want to start
our own string class which inherits off the base string type.

"""
import os
import sys



def get_host_only(my_string):
    if my_string == None or len(my_string) == 0:
        return my_string
    else:
        return (my_string.split('.'))[0]


def left_pad(my_string, char, n_char):
    """ 
        Pads the string on the left (leading) with the character of 
        choice N(n_char) number of times.
        Returns the padded String
    """
    if my_string == None or char == None or n_char == 0:
        return my_string
    
    tmp = ""
    
    for i in range(n_char):
        tmp += char

    return tmp + my_string


def left_pad_all_lines(my_string, char, n_char):
    """
     Pads all of the new lines in the string.
    """
    ret_str = ""
    my_lines = my_string.split("\n")
    for line in my_lines:
        if line == "":
            ret_str +="\n"
        else:
            ret_str +="%s\n"%left_pad(line, char, n_char)
    return ret_str


def string_to_list(string_or_list):
    """ 
     If necessary, converts the string to a single item list
     otherwise it just returns the list back
    """
    
    if type(string_or_list) == list:
        return string_or_list
    else:
        tmp = []
        tmp.append(string_or_list)
        return tmp


def get_dir_from_path(some_path):
    """
     Determines the directory name for some_path based purely
     on the format of some_path. This does not actually check
     that the files/directories actually exist on the machine.
     Returns the path minus any trailing slashes.
    """
    
    if some_path == None:
        return None
    
    # It's a linux path
    if '/' in some_path:
        import posixpath
        if some_path.endswith('/'):
            return some_path.rstrip('/')
        if '.' in  posixpath.split(some_path)[1]:
            return os.path.dirname(some_path)
        else:
            return some_path
    # its a win32 path
    elif '\\' in some_path:
        import ntpath
        if some_path.endswith('\\'):
            return some_path.rstrip('\\')
        if '.' in  ntpath.split(some_path)[1]:
            return os.path.dirname(some_path)
        else:
            return some_path
    
    # if we're here, complain
    raise Exception("Failed to determine directory from [%s]"% some_path)

def remove_drive_letter(some_path):
    """
     Takes some path and removes the drive letter (if it has one).
    """
    if some_path == None:
        return None
    if some_path[1] == ':':
        return some_path[2:]
    else:
        return some_path

def localize_path(some_path):
    """
     Takes some_path and localizes it to the current OS.
     This includes fixing the path seperator character.
     TODO:: 

         1. What else to add here? Localizing the special dirs
            like (home, temp, etc)?
         2. Stripping off fs letters and what not?

    """
    
    if some_path == None:
        return None
    
    ret_path = ""
    if 'linux' in sys.platform:
        ret_path = some_path.replace('\\\\',os.path.sep)
        ret_path = ret_path.replace('\\', os.path.sep)
    elif sys.platform == 'win32':
        ret_path = some_path.replace('/', os.path.sep)
    else:
        raise Exception("OS:%s appears unsupported (Not linux or win32)"%sys.platform)
     
    return ret_path

def edit_ip(ip, octet, value):
    """
     Edits an IP address
     
     Example: 
         edit_ip("10.11.12.13",1,"255")
         returns 10.255.12.13
    """
    octs = ip.split(".")
    octs[int(octet)]=str(value)
    ret = ".".join(octs)

    return ret

if __name__ == "__main__":
    
    print "start"
    
    str = "line 1\n\nline2\n"
    print str
    print left_pad_all_lines(str, " ", 4)
    print "done"
    
