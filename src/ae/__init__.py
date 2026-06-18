__all__ = ["ae_errors","ae_logger","environment","loader","prepper","pyro_driver","pyro_sut","soaper","testing","vimer"]

# set the Pyro HMAC key to suppress the security warnings
import os
os.environ["PYRO_HMAC_KEY"] = bytes("shhhhh")
os.environ["PYRO_THREADPOOL_MAXTHREADS"] = "200"

# avoid import errors during inital at-fork and lib imports
# by installing if needed when importing the ae package.
try:
    import psutil
except ImportError:
    from ae.prepper import Prepper
    Prepper.install_psutil()
try:
    import suds
except ImportError:
    from ae.prepper import Prepper
    Prepper.install_suds()
try:
    import lxml
except ImportError:
    from ae.prepper import Prepper
    Prepper.install_lxml()
try:
    import yaml
except ImportError:
    from ae.prepper import Prepper
    Prepper.install_yaml()
try:
    import pysphere
except ImportError:
    from ae.prepper import Prepper
    Prepper.install_pysphere()
try:
    import fast
except ImportError:
    from ae.prepper import Prepper
    Prepper.install_fast()


import ae_errors
import ae_logger
import environment
import loader
import prepper
import pyro_driver
import pyro_sut
import testing
import vimer



try:
    import soaper
except ImportError:
    pass
