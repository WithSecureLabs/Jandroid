import os
import copy
import json
import logging
from lxml import etree
from androguard.misc import *
from androguard.core import *
from code_analyser_search import CodeSearch
from code_analyser_trace import CodeTrace
from common import *


class CodeAnalyser:
    """The main code analysis class.
    
    Despite its name, this class doesn't actually perform any code analyses. 
    It invokes other classes (which perform the actual analyses) and 
    maintains variables to keep track of outcomes.
    """
    
    def __init__(self, base_dir):
        """Sets paths and initialises variables.
        
        :param base_dir: string specifying location of script base directory
        """
        # Set path.
        self.path_base_dir = base_dir
        
        # Initialise Androguard values for current APK.
        self.androguard_apk_obj = None
        self.androguard_d_array = None
        self.androguard_dx = None
        
        # Initialise other variables.
        self.apk_package_name = None
        self.bug_template = None
        self.code_requirements_satisfied = False
        self.current_returns = {}

    def fn_perform_code_analysis(self, apk_pkg, bug_template,
                                 a, d, dx, links=[]):
        """Analyses APK against bug template.
        
        :param apk_pkg: string representing APK package name
        :param bug_template: dictionary object describing the checks that 
            are to be performed
        :param a: androguard.core.bytecodes.apk.APK object
        :param d: array of androguard.core.bytecodes.dvm.DalvikVMFormat objects
        :param dx: androguard.core.analysis.analysis.Analysis object
        :param links: dictionary object containing linked items
        :returns: a list containing a boolean indicating whether the code 
            requirements were satisfied, and link objects.
        """
        self.apk_package_name = apk_pkg
        
        # We want to copy the bug template but only edit the copy.
        # That is, we don't want to modify the original template (which would
        #  happen even if we did new_bug_obj = old_bug_object and modified
        #  only the new_bug_obj).
        # For this, we do copy.deepcopy(bug template).
        # This is probably very inefficient.
        self.bug_template = copy.deepcopy(bug_template)

        # Androguard values for current APK.
        self.androguard_apk_obj = a
        self.androguard_d_array = d
        self.androguard_dx = dx
        
        # Reset output.
        self.code_requirements_satisfied = False
        
        # Create search and trace objects.
        self.inst_code_search = CodeSearch(
            self.path_base_dir
        )
        self.inst_code_trace = CodeTrace(
            self.path_base_dir
        )

        # Get any values that may have been passed from other analyses.
        self.current_links = links

        # Enumerate the number of elements that must be matched.
        self.total_elements_to_check = 0
        self.total_elements_satisfied = 0
        for element in self.bug_template['CODEPARAMS']:
            self.total_elements_to_check += 1
        if self.total_elements_to_check == 0:
            return

        # Perform the required action and identify matches.
        for element in self.bug_template['CODEPARAMS']:
            bool_satisfied = self.fn_determine_action(element)
            if bool_satisfied == True:
                self.total_elements_satisfied += 1

        # Check whether all elements have been satisfied.
        if self.total_elements_satisfied == self.total_elements_to_check:
            self.code_requirements_satisfied = True

        self.inst_code_search = None
        self.inst_code_trace = None
        
        return [self.code_requirements_satisfied, self.current_links]

    def fn_determine_action(self, object_key):
        """Depending on the key, decides the action to be performed.
        
        :param object_key: string indicating whether code search or trace 
            should be performed.
        :returns: boolean indicating whether the search or trace was satisfied.
        """        
        bool_satisfied = False
        object_template = self.bug_template['CODEPARAMS'][object_key]
        # The action can be one of SEARCH or TRACE.
        # Code searches and traces take the relevant bug template section
        #  and link object as inputs, and return a boolean indicating whether
        #  the search/trace was satisfied, as well as an updated link object.
        if object_key == 'SEARCH':
            [bool_satisfied, self.current_links] = \
                self.inst_code_search.fn_perform_code_search(
                    self.androguard_apk_obj,
                    self.androguard_d_array,
                    self.androguard_dx,
                    object_template,
                    self.current_links
                )
        elif object_key == 'TRACE':
            [bool_satisfied, self.current_links] = \
                self.inst_code_trace.fn_perform_code_trace(
                    self.androguard_apk_obj,
                    self.androguard_d_array,
                    self.androguard_dx,
                    object_template,
                    self.current_links
                )
        return bool_satisfied