import os
import copy
import json
import logging
from androguard.misc import *
from androguard.core import *
from analysis_utils import AnalysisUtils
from common import *


class CodeSearch:
    def __init__(self, base_dir):
        """Sets paths and initialises variables.
        
        :param a: androguard.core.bytecodes.apk.APK object
        :param d: array of androguard.core.bytecodes.dvm.DalvikVMFormat objects
        :param dx: androguard.core.analysis.analysis.Analysis object
        :param base_dir: string indicating script base path
        """
        # Set paths.
        self.path_base_dir = base_dir

    def fn_reset(self):
        """Resets objects to free up memory."""
        self.androguard_apk_obj = None
        self.androguard_d_array = None
        self.androguard_dx = None
        self.inst_analysis_utils = None
        
    def fn_perform_code_search(self, a, d, dx, code_search_template, links):
        """Search through an APK code for template matches.
        
        :param code_search_template: dictionary object corresponding to the 
            search part of a bug template
        :param links: dictionary object containing linked items
        :returns: list containing boolean value indicating whether the search 
            was satisfied, and a dictionary object of updated links
        """
        logging.debug('Performing code search.')
        # Androguard values for current APK.
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
        
        # The SEARCH-relevant part of the bug template.
        self.search_template = code_search_template
        
        # Linked elements from checking previous parts of the template.
        self.current_links = links
        
        # A list to hold returnable elements (which will be
        #  converted to links).
        self.current_returns = []
        
        # Variables to determine how many searches to perform and 
        #  to keep track of how many have been satisfied.
        total_searches_to_perform = 0
        satisfied_searches = 0
        # Variable to determine whether the overall SEARCH is satisfied.
        bool_satisfied = False
        
        # The search template can either be a dictionary or a list of
        #  dictionaries.
        if type(self.search_template) is dict:
            bool_satisfied = self.fn_process_individual_search_item(
                self.search_template
            )
        # If the search is a list, then all individual sub-searches
        #  must be satisfied.
        elif type(self.search_template) is list:
            for search_item in self.search_template:
                total_searches_to_perform += 1
                bool_one_satisfied = \
                    self.fn_process_individual_search_item(search_item)
                if bool_one_satisfied == True:
                    satisfied_searches += 1
            if satisfied_searches == total_searches_to_perform:
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
        
    def fn_process_individual_search_item(self, search_dictionary):
        """Process an individual search object.
        
        :param search_dictionary: individual search object (dictionary)
        :returns: boolean indicating whether all parameters within search 
            object have been specified
        """
        # Initialise output.
        bool_satisfied = False
        total_searches_to_perform = 0
        satisfied_searches = 0
        # Determine the specific type of search to perform.
        # Each type will increment the search-to-be-performed count.
        # If the outcome is True, then the satisfied searches count
        #  will also be incremented.
        for search_item in self.search_template:
            total_searches_to_perform += 1
            bool_search_satisfied = \
                self.fn_determine_search_type(
                    search_item,
                    self.search_template[search_item]
                )            
            if bool_search_satisfied == True:
                satisfied_searches += 1

        # If the number of searches equals the number that returned True,
        #  then the overall result is True.
        if total_searches_to_perform == satisfied_searches:
            bool_satisfied = True
        return bool_satisfied        
    
    def fn_determine_search_type(self, search_type, search_object):
        """Executes appropriate function based on search type.
        
        :param search_type: string value indicating the type of search
        :param search_object: dictionary object containing search parameters
        :returns: boolean output from executing the relevant function
        """
        fn_to_execute = None
        items_to_search = []
        # Determine the correct function to execute.
        # -------------------------------------
        # Search for the presence of a string.
        if search_type == 'SEARCHFORSTRING':
            fn_to_execute = self.fn_search_for_presence_of_string
            items_to_search = self.fn_identify_search_items(
                'STRING',
                search_object['STRING']
            )
        # Search for "calls" to a string.
        elif search_type == 'SEARCHFORCALLTOSTRING':
            fn_to_execute = self.fn_search_for_calls_to_string
            items_to_search = self.fn_identify_search_items(
                'STRING',
                search_object['STRING']
            )
        # Search for the presence of a method.
        elif search_type == 'SEARCHFORMETHOD':
            fn_to_execute = self.fn_search_for_presence_of_method
            items_to_search = self.fn_identify_search_items(
                'METHOD',
                search_object['METHOD']
            )
        # Search for calls to a method.
        elif search_type == 'SEARCHFORCALLTOMETHOD':
            fn_to_execute = self.fn_search_for_calls_to_method
            items_to_search = self.fn_identify_search_items(
                'METHOD',
                search_object['METHOD']
            )
        # Search for the presence of a class.
        elif search_type == 'SEARCHFORCLASS':
            fn_to_execute = self.fn_search_for_presence_of_class
            items_to_search = self.fn_identify_search_items(
                'CLASS',
                search_object['CLASS']
            )
        # Search for calls to a class.
        elif search_type == 'SEARCHFORCALLTOCLASS':
            fn_to_execute = self.fn_search_for_calls_to_class
            items_to_search = self.fn_identify_search_items(
                'CLASS',
                search_object['CLASS']
            )
        # -------------------------------------
        # Execute the function.
        return fn_to_execute(search_object, items_to_search)

    def fn_identify_search_items(self, type, input):
        """Identify the specific items to search for.
        
        :param type: 'STRING', 'METHOD', or 'CLASS'
        :param input: input search string (from template)
        :returns: a list of strings/classes/methods to search for
        """
        search_class_or_method = '<class>'
        if ':' in input:
            search_class_or_method = input.split(':')[0]                       
            input = input[len(search_class_or_method)+1:]
        else:
            if '->' in input:
                search_class_or_method = '<method>'
                
        if type == 'STRING':
            if ' OR ' in input:
                search_strings = input.split(' OR ')
            else:
                search_strings = [input]
            return search_strings
        elif type == 'CLASS':
            if ' OR ' in input:
                split_classes = input.split(' OR ')
            else:
                split_classes = [input]
            all_classes = []
            for one_class in split_classes:
                if one_class[0] == '@':
                    linked_classes = self.fn_get_linked_items(
                        one_class,
                        search_class_or_method
                    )
                    for linked_class in linked_classes:
                        if linked_class in all_classes:
                            continue
                        all_classes.append(linked_class)
                else:
                    all_classes.append(one_class)
            return all_classes 
        elif type == 'METHOD':
            if ' OR ' in input:
                split_methods = input.split(' OR ')
            else:
                split_methods = [input]
            all_methods = []
            for one_method in split_methods:
                if one_method[0] == '@':
                    linked_methods = self.fn_get_linked_items(
                        one_method,
                        search_class_or_method
                    )
                    for linked_method in linked_methods:
                        if linked_method in all_methods:
                            continue
                        all_methods.append(linked_method)
                else:
                    all_methods.append(one_method)
            return all_methods
    
    def fn_get_linked_items(self, string, search_class_or_method):
        """Get items from link list.
        
        :param string: key into link list
        :param search_class_or_method: string (one of <class> or <method>), 
            indicating whether the search should be at the class level or 
            method level
        :returns: list of linked items (or sub-parts, as specified 
            by search_class_or_method)
        """
        output_items = []
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
                if search_class_or_method == '<class>':
                    return_string = return_string.split('->')[0]
                output_items.append(return_string)
        elif link_subpart == '<class>':
            for linked_item in linked_items:
                class_part_only = linked_item.split('->')[0]
                return_string = class_part_only + remaining_string
                if search_class_or_method == '<class>':
                    return_string = return_string.split('->')[0]
                output_items.append(return_string)
        elif link_subpart == '<method>':
            for linked_item in linked_items:
                if '->' not in linked_item:
                    continue
                return_string = linked_item + remaining_string
                if search_class_or_method == '<class>':
                    return_string = return_string.split('->')[0]
                output_items.append(return_string)
        return list(set(output_items))
    
    def fn_search_for_presence_of_string(self, string_search_object,
                                         search_strings):
        """Searches for a string within code.
        
        :param string_search_object: object containing search parameters
        :param search_strings: list of strings to search for
        :returns: boolean indicating whether the string was present within APK
        """
        # Output
        all_strings = []
        for search_string in search_strings:
            logging.debug('Searching for string: "' + search_string + '".')
            all_strings.extend(
                self.inst_analysis_utils.fn_get_strings(search_string.strip())
            )
            
        # If at least one string is present.
        if len(all_strings) == 0:
            return False
        else:
            return True
            
    def fn_search_for_presence_of_method(self, method_search_object,
                                         methods_to_search):
        """Searches for a method within code.
        
        :param method_search_object: object containing search parameters
        :param methods_to_search: list of methods to search for
        :returns: boolean indicating whether the method was found within APK
        """        
        for method_to_search in methods_to_search:
            # Get the class, method and descriptor parts.
            # Note that the method MUST be specified in smali format.
            [class_part, method_part, desc_part] = \
                self.inst_analysis_utils.fn_get_class_method_desc_from_string(
                    method_to_search
                )
            # We consider subclasses as well.
            classes_inc_sub = [class_part]
            classes_inc_sub.extend(
                self.inst_analysis_utils.fn_find_subclasses(class_part)
            )
            
            # Search for all class/method combinations.
            for one_class in classes_inc_sub:
                logging.debug(
                    'Searching for method: '
                    + one_class
                    + '->'
                    + method_part
                    + desc_part
                )
                all_methods.extend(
                    self.inst_analysis_utils.fn_get_methods(
                        one_class,
                        method_part,
                        desc_part
                    )
                )
        
        # If at least one method is present.
        if len(all_methods) == 0:
            return False
        else:
            return True

    def fn_search_for_presence_of_class(self, class_search_object,
                                        classes_to_search):
        """Searches for a class within code.
        
        :param class_search_object: object containing search parameters
        :param search_strings: list of classes to search for
        :returns: boolean indicating whether the class was found within APK
        """        
        for class_to_search in classes_to_search:
            # We consider subclasses as well.
            classes_inc_sub = [class_to_search]
            classes_inc_sub.extend(
                self.inst_analysis_utils.fn_find_subclasses(class_to_search)
            )
            
            for one_class in classes_inc_sub:
                logging.debug('Searching for class: ' + one_class)
                all_classes.extend(
                    self.inst_analysis_utils.fn_get_classes(one_class)
                )
                
        # If at least one class is present.
        if len(all_classes) == 0:
            return False
        else:
            return True
        
    def fn_search_for_calls_to_string(self, string_search_object,
                                      search_strings):
        """Searches for the presence of "calls" to a string of interest.
        
        This is actually just the same as searching for the presence of 
        a string. Unlike classes or methods, a string can't be present within 
        code without being called. However, this method allows us to get the 
        calling class or method.
        
        :param string_search_object: object containing search parameters
        :param search_strings: list of strings to search for
        :returns: boolean indicating whether "calls" to the string were present
        """
        bool_search_satisfied = False
        for search_string in search_strings:
            logging.debug('Searching for string: "' + search_string + '".')
            
            # Get calls to string (will be a list of EncodedMethod objects).
            calling_methods = self.inst_analysis_utils.fn_get_calls_to_string(
                search_string
            )
        
            # If no results were returned, then we needn't waste any more time.
            if len(calling_methods) == 0:
                continue
        
            # Check search locations and RETURNs.
            bool_one_search_satisfied = \
                self.fn_process_search_location_and_returns(
                    string_search_object,
                    calling_methods
                )   
            if bool_one_search_satisfied == True:
                bool_search_satisfied = True
        return bool_search_satisfied
     
    def fn_search_for_calls_to_method(self, method_search_object,
                                      methods_to_search):
        """Searches for the presence of calls to a method of interest.
        
        :param method_search_object: object containing search parameters
        :param search_strings: list of methods to search for
        :returns: boolean indicating whether calls to the method were found
        """
        bool_search_satisfied = False
        for method_to_search in methods_to_search:
            logging.debug(
                'Searching for calls to method: "'
                + method_to_search 
                + '".'
            )
            # Get the class, method and descriptor parts.
            # Note that the method MUST be specified in smali format.
            [class_part, method_part, desc_part] = \
                self.inst_analysis_utils.fn_get_class_method_desc_from_string(
                    method_to_search
                )
            # We consider subclasses as well.
            all_classes = [class_part]
            all_classes.extend(
                self.inst_analysis_utils.fn_find_subclasses(class_part)
            )
            # Get a set of methods that call the method of interest.
            calling_methods = []
            for one_class in all_classes:
                calling_methods.extend(
                    self.inst_analysis_utils.fn_get_calls_to_method(
                        one_class,
                        method_part,
                        desc_part
                    )
                )
            # If there were no methods calling the method of interest,
            #  then return.
            if len(calling_methods) <= 0:
                continue
        
            # Check search locations and RETURNs.
            bool_one_search_satisfied = \
                self.fn_process_search_location_and_returns(
                    method_search_object,
                    calling_methods
                )
            if bool_one_search_satisfied == True:
                bool_search_satisfied = True
        return bool_search_satisfied       
        
    def fn_search_for_calls_to_class(self, class_search_object,
                                     classes_to_search):
        """Searches for the presence of calls to a class of interest.
        
        :param class_search_object: object containing search parameters
        :param search_strings: list of classes to search for
        :returns: boolean indicating whether calls to the the class were found
        """
        bool_search_satisfied = False
        for class_to_search in classes_to_search:
            # We consider subclasses as well.
            classes_inc_sub = [class_to_search]
            classes_inc_sub.extend(
                self.inst_analysis_utils.fn_find_subclasses(class_to_search)
            )
            # Get a set of methods that call the class of interest.
            calling_methods = []
            for one_class in classes_inc_sub:
                logging.debug('Searching for calls to class: ' + one_class)
                calling_methods.extend(
                    self.inst_analysis_utils.fn_get_calls_to_class(one_class)
                )

            # If no results were returned, then we needn't waste any more time.
            if len(calling_methods) == 0:
                continue
            
            # Check search locations and RETURNs.
            bool_one_search_satisfied = \
                self.fn_process_search_location_and_returns(
                    class_search_object,
                    calling_methods
                )       
            if bool_one_search_satisfied == True:
                bool_search_satisfied = True
        return bool_search_satisfied
        
    def fn_process_search_location_and_returns(self, search_object,
                                               calling_methods):
        """Filters methods for search location criteria, and process RETURNs.
        
        :param search_object: dictionary object for a single search type
        :param calling_methods: list of EncodedMethod objects
        :returns: boolean indicating whether any of the calling methods 
            correspond to the search location specified in the search object
        """
        bool_search_satisfied = False
        # If no search location was specified in the template, then 
        #  we assume code-wide search, and the location search part is done.
        if 'SEARCHLOCATION' not in search_object:
            bool_search_satisfied = True
        
        # If a search location *was* specified,
        #  then further filtering is needed.
        if 'SEARCHLOCATION' in search_object:
            methods_satisfying_location_requirements = \
                self.fn_get_methods_satisfying_location_reqs(
                    calling_methods,
                    search_object['SEARCHLOCATION']
                )
            if len(methods_satisfying_location_requirements) > 0:
                bool_search_satisfied = True
                calling_methods = methods_satisfying_location_requirements
        
        # If there are no RETURNs to process, then we're done.
        if 'RETURN' not in search_object:
            return bool_search_satisfied

        self.fn_analyse_returns(
            search_object,
            calling_methods
        )
        return bool_search_satisfied

    def fn_get_methods_satisfying_location_reqs(self, methods, location):
        """Checks which input methods satisfy location criteria.
        
        :param methods: list of EncodedMethod objects
        :param location: string describing search location (in smali)
        :returns: list of EncodedMethod objects that satisfy the search 
            location criteria
        """
        output_methods = []
        location_type = '<class>'
        location_exclusion = False
        if 'NOT ' in location:
            location_exclusion = True
            location = location.replace('NOT ', '')
        if ':' in location:
            location_split = location.split(':')
            # Location type has limited options.
            location_type = location_split[0]
            # Location value could be a fixed value or a link value.
            location_value = location_split[1]
        else:
            location_value = location
        location_values = []
        if location_value[0] == '@':
            location_values = self.inst_analysis_utils.fn_get_linked_items(
                self.current_links,
                location_value
            )
        else:
            location_values = [location_value]
        
        # Check each calling method against each expected location value.
        for input_method in methods:
            for location_value in location_values:
                is_satisfied = self.fn_check_callers_against_expectation(
                    input_method,
                    location_value,
                    location_type,
                    location_exclusion
                )                
                if is_satisfied == True:
                    output_methods.append(input_method)
        return output_methods

    def fn_check_callers_against_expectation(self, method, location_value,
                                             location_type, exclude_match):
        """Checks a method against an expected pattern.
        
        :param method: EncodedMethod object to check
        :param location_value: string denoting the location to match against
        :param location_type: string value of either "<class>" or "<method>", 
            indicating which part of the location to match against. Note that 
            "<method>" will match against the composite class->method, while 
            "<class>" will match against only the class part.
        :returns: boolean indicating whether the method satsifies the location 
            criteria
        """
        is_satisfied = False
        # Available signature, as class/method/descriptor.
        [class_part, method_part, desc_part] = \
                self.inst_analysis_utils.fn_get_class_method_desc_from_method(
                    method
                )
        # Expected signature, as class/method/descriptor.
        [exp_class_part, exp_method_part, exp_desc_part] = \
                self.inst_analysis_utils.fn_get_class_method_desc_from_string(
                    location_value
                )
        # Perform the checks.
        # If the location type is class, then we only compare the class parts.
        #  Otherwise, we compare class, method and descriptor parts.
        if location_type == '<class>':
            if exp_class_part.endswith('*'):
                if class_part.startswith(exp_class_part.replace('*', '')):
                    is_satisfied = True
            else:
                if class_part == exp_class_part:
                    is_satisfied = True
        elif location_type == '<method>':
            if ((class_part == exp_class_part) and
                    (method_part == exp_method_part) and
                    (desc_part == exp_desc_part)):
                is_satisfied = True
        if exclude_match == True:
            is_satisfied = not is_satisfied
        return is_satisfied

    def fn_analyse_returns(self, return_object,
                           return_candidates):
        """Analyses the returns list against the expected returns.
        
        :param return_object: dictionary object containing returnable items
        :param return_candidates: list of EncodedMethod objects to process 
            according to the rules specified in the return_object
        """
        # Returnable items.
        returnables = return_object['RETURN']
        # Generalise the returnables to a list.
        if type(returnables) is list:
            returnable_elements = returnables
        elif ',' in returnables:
            returnable_elements = returnables.split(',')
        else:
            returnable_elements = [returnables]
            
        # Process each returnable item.
        for return_element in returnable_elements:
            returnable_element_name = return_element.split(' AS ')[1]
            return_type = return_element.split(' AS ')[0]
            for return_candidate in return_candidates:
                self.fn_process_returnable_item(
                    return_candidate,
                    return_type,
                    returnable_element_name
                )

    def fn_process_returnable_item(self, return_candidate,
                                   return_type, element_name):
        """Creates a return object and appends to current returns.
        
        This function will process the EncodedMethod object, extract the 
        relevant parts of information from it, and create an output object, 
        which it will append to the list of returns.
        
        :param return_candidate: EncodedMethod object to be processed as 
            a returnable element
        :param return_type: string value of either "<class>" or "<method>", 
            indicating which part of the method to append to returns. Note 
            that "<method>" will retain the composite class->method, while 
            "<class>" will return only the class part.
        :param element_name: string name under which to store the return item
        """
        [class_name, method_name, desc_name] = \
            self.inst_analysis_utils.fn_get_class_method_desc_from_method(
                return_candidate
            )
        output_obj = {}
        if return_type == '<class>':
            output_obj[element_name] = class_name
        elif return_type == '<method>':
            full_method = class_name + '->' + method_name + desc_name
            output_obj[element_name] = full_method
        self.current_returns.append(output_obj)