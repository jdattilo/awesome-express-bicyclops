import test_procedures
from ae import ae_errors


def module_function(first_argument):
    """ Brief overview of functionality
    
    :param first_argument: first argument description
    
    :return: return value description
    
    :raises: LookupError

    """
    if first_argument:
        return [1, 2, 3]
    else:
        raise LookupError('Could not find it!')


class TestProcedureTemplate(test_procedures.TestProcedure.TestProcedure):
    """ Short description of the test procedure
    
    Optional longer description of the test procedure that can go into greater
    detail about overall procedure requirements, behavior, and anything else
    that may be relevant to explain to a future user.

    :param first_arg: first argument explanation
    :param second_arg: second argument explanation
    :param third_arg: third argument explanation
        
    :returns: If the test procedure returns something useful via pro.output
    
    .. note:: A way to call out some useful information about behavior
    
    .. warning:: A way to call out a serious potential pitfall in behavior
    
    .. todo:: A way to call out unfinished work
    
    .. note:: Doubles of note, warning, and todo are possible
    
    **Example**::
    
        template_tp = templates.TestProcedureTemplate(self.sut, self.suite_config)
        template_pro = template_tp.run(node=das_node)
        
        if template_tp.class_function(template_pro):
            self.log.info("Log message")

    **Another Example**::
    
        # Doubles of examples are possible
        # An example .dat file section can be presented here

    """
    
    def action(self):
        """ Overview of behavior of the action command
        
                - Lists
                - Are
                - Easy
        
        """
        return True
    
    
    def checkpoint(self):
        """ Overview of validation within checkpoint if implemented   
        OR  
        Checkpoint not implemented
        """
        pass


    def class_function(self, template_pro):
        """ Brief overview of functionality
        
        :param template_pro: PRO from the Template Test Procedure
        
        :returns: The output member of the PRO
    
        """
        return template_pro.output
