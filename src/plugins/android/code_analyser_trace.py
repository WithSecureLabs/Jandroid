import os
import re
import copy
import json
import logging
import configparser
from androguard.misc import *
from androguard.core import *
from analysis_utils import AnalysisUtils
from code_analyser_trace_adv import CodeTraceAdvanced
from common import Conversions

TRACE_FORWARD = 'FORWARD'
TRACE_REVERSE = 'REVERSE'

TRACE_TYPE_BASIC = 'BASIC'
TRACE_TYPE_ADVANCED = 'ADVANCED'

STOP_CONDITION_TRUE = 'True'
STOP_CONDITION_FALSE = 'False'
STOP_CONDITION_MAYBE = 'Maybe'

class CodeTrace:
    """The main code tracing class."""
    
    def __init__(self, base_dir):
        """Sets paths and initialises variables.
        
        :param a: androguard.core.bytecodes.apk.APK object
        :param d: array of androguard.core.bytecodes.dvm.DalvikVMFormat objects
        :param dx: androguard.core.analysis.analysis.Analysis object
        :param base_dir: string indicating script base path
        """
        # Set paths.
        self.path_base_dir = base_dir
        self.path_config_file = os.path.join(
            self.path_base_dir,
            'config',
            'jandroid.conf'
        )
        
        # Set a default max trace length.
        self.default_trace_length_max = 25
        
        # Read config file.
        config = configparser.ConfigParser()
        config.read(self.path_config_file)
        if config.has_section('TRACEPARAMS'):
            if config.has_option('TRACEPARAMS', 'TRACE_LENGTH_MAX'):
                self.default_trace_length_max = \
                    int(config['TRACEPARAMS']['TRACE_LENGTH_MAX'])
        
        self.trace_length_max = self.default_trace_length_max

        # Initialise special case object.
        self.special_case_object_list_reverse = {
            'doInBackground': {
                'Landroid/os/AsyncTask;': [
                    'execute([Ljava/lang/Object;)Landroid/os/AsyncTask;', 
                    'execute(Ljava/lang/Runnable;)'
                ]
            }
        }
        self.special_case_object_list_forward = {
            'execute([Ljava/lang/Object;)Landroid/os/AsyncTask;': 'doInBackground',
            'execute(Ljava/lang/Runnable;)V': 'doInBackground'
        }
                                    
        # Store returns.
        self.current_returns = []
        
        # This is to let us know whether to perform a "lenient" stop check or not.
        self.hardcoded_traceto = False
        
        self.advanced_trace = CodeTraceAdvanced(self.path_base_dir)

    def fn_reset(self):
        """Resets objects to free up memory."""
        self.androguard_apk_obj = None
        self.androguard_d_array = None
        self.androguard_dx = None
        self.inst_analysis_utils = None
        self.current_returns = []
        
    def fn_perform_code_trace(self, a, d, dx, code_trace_template, links):
        """Traces within code based on a trace template.
        
        :param code_trace_template: dictionary object corresponding to the 
            trace part of a bug template
        :param links: dictionary object containing linked items
        :returns: list containing boolean value indicating whether the trace 
            was satisfied, and a dictionary object of updated links
        """
        logging.debug('Performing code trace.')
        # Androguard variables for this APK.
        self.androguard_apk_obj = a
        self.androguard_d_array = d
        self.androguard_dx = dx
        
        # Start up utility helper.
        self.inst_analysis_utils = AnalysisUtils(
            self.path_base_dir,
            self.androguard_apk_obj,
            self.androguard_d_array,
            self.androguard_dx
        )
        
        # The TRACE-relevant part of the bug template.
        self.trace_template = code_trace_template
        
        # Linked elements from checking previous parts of the template.
        self.current_links = links
        
        # Keep track of trace chains (to be converted to RETURN items).
        self.output_chains = []
        
        # Variables to determine how many traces to perform and 
        #  to keep track of how many have been satisfied.
        total_traces = 0
        satisfied_traces = 0
        # Variable to determine whether the overall TRACE is satisfied.
        bool_satisfied = False
        
        # The trace template can either be a dictionary or a list
        #  of dictionary objects.
        if type(self.trace_template) is dict:
            bool_satisfied = \
                self.fn_process_individual_trace_list_item(self.trace_template)
        # If the search is a list, then all individual sub-traces
        #  must be satisfied.
        elif type(self.trace_template) is list:            
            for trace_item in self.trace_template:
                total_traces += 1
                bool_one_satisfied = \
                    self.fn_process_individual_trace_list_item(trace_item)
                if bool_one_satisfied == True:
                    satisfied_traces += 1
            if satisfied_traces == total_traces:
                bool_satisfied = True

        # Process returns as links.
        if bool_satisfied == True:
            self.current_links = \
                self.inst_analysis_utils.fn_convert_returns_to_links(
                    self.current_returns,
                    self.current_links
                )
        
        self.fn_reset()
        
        # Return the outcome and the links, to be used by next code segment.
        return [bool_satisfied, self.current_links]
        
    def fn_process_individual_trace_list_item(self, trace_dictionary):
        """Processes an individual trace object.
        
        :param trace_dictionary: dictionary object containing details of an
            individual trace to perform
        :returns: boolean indicating whether the trace requirements were 
            satisfied
        """
        # Each item within the list must be a dictionary trace object.
        bool_satisfied = False
        # Get parameters such as trace direction, etc.
        self.fn_get_trace_parameters(trace_dictionary)
        if self.trace_type == TRACE_TYPE_ADVANCED:
            bool_adv_trace_output, output_chains = \
                self.advanced_trace.fn_start_adv_trace(
                    self.androguard_apk_obj,
                    self.androguard_d_array,
                    self.androguard_dx,
                    trace_dictionary,
                    self.current_links,
                    self.trace_direction,
                    self.trace_length_max
                )
            return bool_adv_trace_output
        # There may be a number of combinations, if the trace from/to
        #  have elements separated by OR.
        [trace_from_string_list, trace_to_string_list] = \
            self.fn_enumerate_trace_source_sinks(trace_dictionary)
        # For each combination, run trace.
        for trace_from_string_element in trace_from_string_list:
            for trace_to_string_element in trace_to_string_list:
                bool_single_trace_satisfied = self.fn_trace_through_code(
                    trace_from_string_element,
                    trace_to_string_element
                )
                if bool_single_trace_satisfied == True:
                    bool_satisfied = True
        if bool_satisfied == True:
            if 'RETURN' in trace_dictionary:
                self.fn_analyse_returns(trace_dictionary)
        return bool_satisfied

    def fn_get_trace_parameters(self, trace_template):
        """Sets trace parameters based on trace template.
        
        :param trace_template: dictionary object corresponding to a single
            trace, from which trace parameters are to be extracted
        """
        # Set max trace length, if available.
        if 'TRACELENGTHMAX' in trace_template:
            self.trace_length_max = int(trace_template['TRACELENGTHMAX'])
        else:
            self.trace_length_max = self.default_trace_length_max
            
        # Set trace direction.
        if 'TRACEDIRECTION' in trace_template:
            trace_direction = trace_template['TRACEDIRECTION']
            if trace_direction == TRACE_FORWARD:
                self.trace_direction = TRACE_FORWARD
            else:
                self.trace_direction = TRACE_REVERSE
        else:
            # Default is REVERSE.
            self.trace_direction = TRACE_REVERSE
        
        # Set trace type.
        if 'TRACETYPE' in trace_template:
            self.trace_type = trace_template['TRACETYPE']
        else:
            self.trace_type = TRACE_TYPE_BASIC

    def fn_enumerate_trace_source_sinks(self, trace_template):
        """Enumerates the (list of) trace start and end points from template.
        
        :param trace_template: dictionary object corresponding to a single 
            trace, from which trace end points are to be extracted
        :returns: list containing two lists - the first a list of possible 
            start points and the second, a list of possible end points
        """
        # Get the start points.
        trace_from_string = trace_template['TRACEFROM']        
        if ' OR ' in trace_from_string:
            trace_from_string_list = trace_from_string.split(' OR ')
        else:
            trace_from_string_list = [trace_from_string]
        # Get the end points.
        trace_to_string = trace_template['TRACETO']
        if ' OR ' in trace_to_string:
            trace_to_string_list = trace_to_string.split(' OR ')
        else:
            trace_to_string_list = [trace_to_string]
        return [trace_from_string_list, trace_to_string_list]
                
    def fn_trace_through_code(self, trace_from_string, trace_to_string):
        """Begins the actual trace.
        
        :param trace_from_string: string corresponding to a single start point
        :param trace_to_string: string corresponding to a single end point
        :returns: boolean indicating whether at least one path between the start 
            and end points was found
        """
        # Get trace types.
        [self.from_class_method, trace_from_string] = \
            self.fn_get_trace_type(trace_from_string)
        [self.to_class_method, trace_to_string] = \
            self.fn_get_trace_type(trace_to_string)
        # Get any linked items.
        trace_from_list = self.fn_get_trace_items(
            trace_from_string,
            self.from_class_method
        )
        trace_to_list = self.fn_get_trace_items(
            trace_to_string,
            self.to_class_method
        )
        if ((trace_from_list == []) or (trace_to_list == [])):
            logging.debug('Either TraceFrom or TraceTo evaluated to None.')
            return False
        self.trace_to_list = trace_to_list
        
        return self.fn_trace_handler(trace_from_list)
        
    def fn_get_trace_type(self, string):
        """Gets trace starting point type.
        
        :param string: string containing trace start point type (either 
            "<class>" or "<method>". The string may not directly contain 
            these values, in which case the type will have to be inferred.
        :returns: list containing the start point type and the modified string
            (within the "<class>" or "<method>" indication removed)
        """
        trace_type = '<class>'
        if ':' in string:
            trace_type = string.split(':')[0]                       
            string = string[len(trace_type)+1:]
        else:
            if '->' in string:
                trace_type = '<method>'
        return [trace_type, string]

    def fn_get_trace_items(self, string, trace_type):
        """Gets the actual strings to use as start/end points of trace.
        
        :param string: the string specified within the template
        :param trace_type: string (either "<class>" or "<method>"), indicating
            whether the trace should begin/end at the class level or method 
            level
        :returns: list of possible start/end points
        """
        output_items = [] 
        # If the string begins with @, then we need to find linked items.
        if string[0] == '@':
            self.hardcoded_traceto = False
            # If a sub-part has not been specified, then assume that the
            #  entire string is the link name.
            if ']' not in string:
                link_name = string
                link_subpart = ''
                remaining_string = ''
            # If a sub-part has been specified, then split the string to
            #  identify the link name, relevant sub-part, and remainder
            #  of string.
            else:
                split_for_link = string.split(']')
                remaining_string = split_for_link[1]
                second_split = split_for_link[0].split('[')            
                link_name = second_split[0]                
                link_subpart = second_split[1].replace(' ', '')
            # Get all linked items.
            linked_items = self.inst_analysis_utils.fn_get_linked_items(
                self.current_links,
                link_name
            )
            if link_subpart == '':
                for linked_item in linked_items:
                    return_string = linked_item + remaining_string
                    if trace_type == '<class>':
                        return_string = return_string.split('->')[0]
                    output_items.append(return_string)
            elif link_subpart == '<class>':
                for linked_item in linked_items:
                    class_part_only = linked_item.split('->')[0]
                    return_string = class_part_only + remaining_string
                    if trace_type == '<class>':
                        return_string = return_string.split('->')[0]
                    output_items.append(return_string)
            elif link_subpart == '<method>':
                for linked_item in linked_items:
                    if '->' not in linked_item:
                        continue
                    return_string = linked_item + remaining_string
                    if trace_type == '<class>':
                        return_string = return_string.split('->')[0]
                    output_items.append(return_string)
        # If the string doesn't begin with @, then it's a normal string.
        else:
            self.hardcoded_traceto = True
            if trace_type == '<class>':
                string = string.split('->')[0]
            output_items = [string]
        return output_items

    def fn_trace_handler(self, trace_from_list):
        """Starts the trace process and outputs the result.
        
        :param trace_from_list: list containing possible start points
            for trace
        :returns: boolean indicating whether at least one path was identified
            between the start and end points
        """
        for trace_from in trace_from_list:
            self.checked_methods = set()
            # Set a stop condition.
            self.stop_condition = STOP_CONDITION_FALSE
            
            # Get class/method/desc parts.
            [class_part, method_part, desc_part] = \
                self.fn_determine_class_method_desc(
                    trace_from,
                    self.from_class_method
                )
            # Start the forward or reverse tracers, based on template.
            if self.trace_direction == TRACE_REVERSE:
                self.fn_trace_reverse(
                    class_part,
                    method_part,
                    desc_part,
                    trace_from
                )
            else:
                self.fn_trace_forward(
                    class_part,
                    method_part,
                    desc_part,
                    trace_from
                )
        # If the output chain list is not empty, it means at least one path
        #  between the start and end points was identified.
        if self.output_chains != []:
            return True
        else:
            return False
    
    def fn_trace_reverse(self, class_part, method_part, desc_part,
                         trace_chain=''):
        """Performs the reverse tracing function.
        
        Reverse tracing starts from TRACEFROM and gets all xref_from at each 
        level. The collection of all xref_from's are stored in an 
        "ordered string".
        
        :param class_part: string denoting class part of trace start point
        :param method_part: string denoting method part of trace start point
        :param desc_part: string denoting descriptor part of trace start point
        :param trace_chain: string denoting ordered trace chain
        """
        # Get starting points.
        starting_points = \
            self.inst_analysis_utils.fn_get_calls_to_method(
                class_part,
                method_part,
                desc_part
            )
        # Include subclasses.
        all_subclasses = []
        all_subclasses.extend(
            self.inst_analysis_utils.fn_find_subclasses(class_part)
        )
        for subclass in all_subclasses:
            starting_points.extend(
                self.inst_analysis_utils.fn_get_calls_to_method(
                    subclass,
                    method_part,
                    desc_part
                )
            )
                
        # Reset.
        class_part = None
        method_part = None
        desc_part = None
        
        # Start trace for each starting point.
        for starting_point in starting_points:
            # Get class/method/desc parts.
            [class_part, method_part, desc_part] = \
                self.inst_analysis_utils.fn_get_class_method_desc_from_method(
                    starting_point
                )
            
            # If we want to consider subclasses as well.
            # Note that this is different to the step above. Above, we get
            #  subclasses of the class/method that is being called. Here, we
            #  get the subclasses for the class that is doing the calling.
            class_parts = [class_part]
            class_parts.extend(
                self.inst_analysis_utils.fn_find_subclasses(class_part)
            )

            # Handle any special cases (AsyncTask, etc).
            # The class name remains the same for these special cases.
            # Only the method/descriptor changes.
            if method_part in self.special_case_object_list_reverse:
                method_descriptors = \
                    self.fn_handle_special_case_reverse(
                        class_part,
                        method_part,
                        desc_part
                    )
            else:
                method_descriptors = [method_part + desc_part]
            
            # Go to the next step of the trace.
            for class_part in class_parts:
                for method_descriptor in method_descriptors:
                    method_part = method_descriptor.split('(')[0]
                    desc_part = '(' + method_descriptor.split('(')[1]
                    self.fn_analyse_trace_point(
                        class_part,
                        method_part,
                        desc_part,
                        trace_chain
                    )

    def fn_handle_special_case_reverse(self, class_part, method_part,
                                       desc_part):
        """Handles cases such as AsyncTask, where no direct link can be made.
        
        :param class_part: string name for class
        :param method_part: string name for method
        :param desc_part: string name for descriptor
        :returns: list of revised method_part+desc_part
        """
        relevant_object = self.special_case_object_list_reverse[method_part]
        new_method_to_search = []
        all_superclasses = \
            self.inst_analysis_utils.fn_find_superclasses(class_part)
        # Is this needed?
        #all_superclasses.append(class_part)
        for superclass in all_superclasses:
            superclass = superclass.strip()
            if superclass in relevant_object:
                return relevant_object[superclass]
        
    def fn_trace_forward(self, class_part, method_part, desc_part,
                         trace_chain=''):
        """Performs the forward tracing function.
        
        Forward tracing starts from TRACEFROM and gets all xref_to at each 
        level. The collection of all xref_to's are stored in an 
        "ordered string".
        
        :param class_part: string denoting class part of trace start point
        :param method_part: string denoting method part of trace start point
        :param desc_part: string denoting descriptor part of trace start point
        :param trace_chain: string denoting ordered trace chain
        """
        # Get starting points.
        # These will still be methods that call the method of interest
        #  (even though the trace direction is Forward).
        starting_points = \
            self.inst_analysis_utils.fn_get_calls_from_method(
                class_part,
                method_part,
                desc_part
            )
        
        # Reset.
        class_part = None
        method_part = None
        desc_part = None
        
        for starting_point in starting_points:
            # If the method is external, we won't get any further.
            # Get class/method/desc parts.
            [class_part, method_part, desc_part] = \
                self.inst_analysis_utils.fn_get_class_method_desc_from_method(
                    starting_point
                )
            class_parts = [class_part]
                
            # Special case handling.
            method_descriptor = method_part + desc_part
            if method_descriptor in self.special_case_object_list_forward:
                method_part = \
                    self.fn_handle_special_case_forward(method_descriptor)
                desc_part = '.'
            
            # Go to next step.
            for class_part in class_parts:
                self.fn_analyse_trace_point(
                    class_part,
                    method_part,
                    desc_part,
                    trace_chain
                )
    
    def fn_handle_special_case_forward(self, method_descriptor):
        """Handle special cases, such as AsyncTask, in forward traces.
        
        :param method_descriptor: string denoting combined method and 
            descriptor parts
        :returns: string for method part
        """
        return self.special_case_object_list_forward[method_descriptor]
        
    def fn_analyse_trace_point(self, class_part, method_part, desc_part,
                               trace_chain):
        """Checks current trace point against stop condition; else continues.

        :param class_part: string denoting class part of current trace point
        :param method_part: string denoting method part of current trace point
        :param desc_part: string denoting descriptor part of current trace point
        :param trace_chain: string denoting ordered trace chain
        """
        compound_name = class_part + '->' + method_part + desc_part
        if compound_name in self.checked_methods:
            return
        else:
            self.checked_methods.add(compound_name)

        # Check if stop condition is met.
        self.fn_check_stop_condition(compound_name)
        if self.stop_condition == STOP_CONDITION_TRUE:
            self.stop_condition = STOP_CONDITION_FALSE
            if trace_chain == '':
                trace_chain = compound_name
            else:
                trace_chain = trace_chain + ',' + compound_name
            # If somehow we have the same chain repeated:
            if trace_chain in self.output_chains:
                return
            self.output_chains.append(trace_chain)            
            return
        elif self.stop_condition == STOP_CONDITION_MAYBE:
            self.stop_condition = STOP_CONDITION_FALSE
            compound_name = '|MAYBE|' + compound_name
            if trace_chain == '':
                trace_chain = compound_name
            else:
                trace_chain = trace_chain + ',' + compound_name
            # If somehow we have the same chain repeated:
            if trace_chain in self.output_chains:
                return
            self.output_chains.append(trace_chain)
            
        # If the stop condition wasn't met,
        #  and we haven't exceeded the max chain length.
        trace_chain_as_list = trace_chain.split(',')
        if len(trace_chain_as_list) > self.trace_length_max:
            return
        if self.trace_direction == TRACE_FORWARD:
            self.fn_trace_forward(
                class_part,
                method_part,
                desc_part,
                trace_chain
            )
        else:
            self.fn_trace_reverse(
            class_part,
            method_part,
            desc_part,
            trace_chain
        )

    def fn_check_stop_condition(self, check_value):
        """Checks whether the stop condition has been satisfied for the trace.
        
        This does not return a value, but rather sets a variable to a pre-defined
        value if the stop condition is satisfied.
        
        :param check_value: string value to be checked against stop condition
        """
        if self.to_class_method == '<class>':
            check_value = check_value.split('->')[0]
        if check_value in self.trace_to_list:
            self.stop_condition = STOP_CONDITION_TRUE
            return
        
        # Special types of checks for when the traceto is hardcoded.
        if self.hardcoded_traceto == False:
            return
        # This should never be true. Hardcoded traceto's will only have one
        #  value in the list (even with ORs). 
        if len(self.trace_to_list) > 1:
            return
        trace_to_item = self.trace_to_list[0]
        
        # Check for wildcard classes.
        if ((self.to_class_method == '<class>') and ('*' in trace_to_item)):
            trace_to_item = trace_to_item.replace('*', '')
            if trace_to_item in check_value:
                self.stop_condition = STOP_CONDITION_TRUE
            else:
                self.stop_condition = STOP_CONDITION_FALSE
            return
        # Do a partial search for methods only. Do this only when the entire 
        #  trace-to is hardcoded.
        # If traceto is only a class, we can't do much.
        if '->' not in trace_to_item:
            return
        if '->' not in check_value:
            return
        # If traceto doesn't have descriptor, don't proceed.
        # Else, we might end up with way too many FPs.
        if '(' not in trace_to_item:
            return
        if '(' not in check_value:
            return
        if trace_to_item.split('->')[1] == check_value.split('->')[1]:
            self.stop_condition = STOP_CONDITION_MAYBE
            return
        
    def fn_determine_class_method_desc(self, trace_from, trace_from_type):
        """Determines the class/method/desc parts based on trace start point.
        
        :param trace_from: string denoting trace start point
        :param trace_from_type: string containing trace start point type 
            (either "<class>" or "<method>")
        :returns: list containing class, method, descriptor parts
        """
        [class_part, method_part, desc_part] = \
            self.inst_analysis_utils.fn_get_class_method_desc_from_string(
                trace_from
            )
        # If we care only about the class part, overwrite the method/desc
        #  parts with '.' (i.e., "don't care")
        if trace_from_type == '<class>':
            method_part = '.'
            desc_part = '.'
        return [class_part, method_part, desc_part]

    def fn_analyse_returns(self, trace_template):
        """Analyses the return object and appends items to returns list.
        
        :param trace_template: dictionary object containing RETURN element
        """
        returnables = trace_template['RETURN']
        returnable_elements_name = returnables.split(' AS ')[1]
        return_type = returnables.split(' AS ')[0]
        
        # Analyse each chain.
        for chain_string in self.output_chains:
            chain = chain_string.split(',')
            if self.trace_direction == TRACE_REVERSE:
                chain.reverse()            
            output_str = ''
            for chain_node in chain:
                chain_node = chain_node.strip()
                if output_str == '':
                    output_str = chain_node
                else:
                    output_str = output_str + ',' + chain_node
            self.current_returns.append({returnable_elements_name: output_str})        