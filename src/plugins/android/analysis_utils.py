import os
import re
import copy
import json
import logging
import configparser
from androguard.misc import *
from androguard.core import *
from common import Conversions, JandroidException


class AnalysisUtils:
    """Utility functions to be used for app analysis."""

    def __init__(self, base_dir, a=None, d=None, dx=None):
        """Sets/initialises variables and reads/sets relevant configuration.
        
        :param base_dir: string specifying location of script base directory
        :param a: androguard.core.bytecodes.apk.APK object
        :param d: androguard.core.bytecodes.dvm.DalvikVMFormat object
        :param dx: androguard.core.analysis.analysis.Analysis object
        """
        # Androguard variables for this APK.
        self.androguard_apk_obj = a
        self.androguard_d_array = d
        self.androguard_dx = dx
        
        # Keep track of super/sub classes,
        #  to prevent searching for them multiple times.
        self.superclasses = {}
        self.subclasses = {}
        
        # Check whether to keep user interaction elements.
        #  For pwn2own, we normally don't want interaction.
        self.keep_user_interaction = False

        # Read config file.
        self.path_config_file = os.path.join(
            base_dir,
            'config',
            'jandroid.conf'
        )
        config = configparser.ConfigParser()
        config.read(self.path_config_file)
        if config.has_section('SEARCHPARAMS'):
            if config.has_option('SEARCHPARAMS', 'KEEP_INTERACTIVE_ELEMENTS'):
                self.keep_user_interaction = \
                    config['SEARCHPARAMS']['KEEP_INTERACTIVE_ELEMENTS']
        if self.keep_user_interaction not in [True, False]:
            logging.warning(
                'Invalid value for KEEP_INTERACTIVE_ELEMENTS. '
                + 'Defaulting to False.'
            )
            self.keep_user_interaction = False
    
    def fn_find_subclasses(self, class_name, recursion=True):
        """Recursively finds subclasses for a given class.
        
        :param class_name: name (as string) of the class for which subclasses 
            are to be identified
        :param recursion: boolean indicating whether the search should be 
            recursive or not
        :returns: list of all unique subclasses
        """
        # If we have previously identified subclasses for this input class,
        #  then retrieve the list from the subclass object and return.
        if class_name in self.subclasses:
            return self.subclasses[class_name]

        # If we haven't previously identified subclasses for this class,
        #  then we need to use Androguard methods.
        subclasses = []
        logging.debug('Looking for subclasses of ' + class_name)
        
        # Get all internal classes within the app.
        # External classes will not allow for operations such as
        #  get_vm_class().
        all_internal_classes = self.androguard_dx.get_internal_classes()
        for internal_class in all_internal_classes:
            classdefitem = internal_class.get_vm_class()
            superclass_name = classdefitem.get_superclassname()
            # If the superclass of the internal class has the same name
            #  as the class of interest, then the internal class
            #  is a subclass of the class of interest.
            if superclass_name == class_name:
                subclass_name = classdefitem.get_name()
                subclasses.append(subclass_name)
                # Recursively get subclasses.
                if recursion == True:
                    nextlevel_subclasses = self.fn_find_subclasses(
                        subclass_name
                    )
                    subclasses = subclasses + nextlevel_subclasses

        # Convert to set to remove duplicates and back to list again.
        # This is probably very inefficient.
        subclasses = list(set(subclasses))

        # Add the list of subclasses to a subclass object,
        #  so we don't have to repeat the search for
        #  previously identified classes.
        self.subclasses[class_name] = subclasses
        return subclasses
        
    def fn_find_superclasses(self, class_name, recursion=True):
        """Recursively finds superclasses for a given class.
        
        :param class_name: name (as string) of the class for which 
            superclasses are to be identified
        :param recursion: boolean indicating whether the search should be 
            recursive or not
        :returns: list of all unique superclasses
        """
        # If we have previously identified superclasses for this input class,
        #  then retrieve the list from the superclass object and return.
        if class_name in self.superclasses:
            return self.superclasses[class_name]

        # If we haven't previously identified superclasses for this class,
        #  then we need to use Androguard methods.
        superclasses = []
        logging.debug('Looking for superclasses of ' + class_name)

        # Get all the classes that match the input class name.
        # There should only be one, really.
        class_analysis_objs = self.androguard_dx.find_classes(
            class_name
        )
        # For each class, get all superclasses.
        for class_analysis_obj in class_analysis_objs:
            # External classes aren't going to have operations such
            #  as get_vm_class().
            if class_analysis_obj.is_external() == True:
                continue
            classdefitem = class_analysis_obj.get_vm_class()
            superclass_name = classdefitem.get_superclassname()
            superclasses.append(superclass_name)
            # Recursively get superclasses.
            if recursion == True:
                nextlevel_superclasses = self.fn_find_superclasses(
                    superclass_name
                )
                superclasses = superclasses + nextlevel_superclasses

        # Convert to set to remove duplicates and back to list again.
        superclasses = list(set(superclasses))

        # Add the list of superclasses to a superclass object,
        #  so we don't have to repeat the search for
        #  previously identified classes.
        self.superclasses[class_name] = superclasses
        return superclasses
        
    def fn_get_methods(self, class_part, method_part, desc_part):
        """Gets all methods that satisfy a certain signature.
        
        :param class_part: name of the method class as string
        :param method_part: name of the method as string
        :param desc_part: descriptor as string
        :returns: list of Androguard MethodAnalysis objects
        """
        method_objs = []
        if desc_part != '.':
            desc_part = re.escape(desc_part)
        class_part = re.escape(class_part)
        method_part = re.escape(method_part)
        
        for method in self.androguard_dx.find_methods(
            class_part,
            method_part,
            desc_part
        ):
            method_objs.append(method)
        return method_objs
        
    def fn_get_calls_to_method(self, class_part, method_part, desc_part):
        """Gets all methods that call a method of interest.
        
        :param class_part: name of the method class as string
        :param method_part: name of the method as string
        :param desc_part: descriptor as string
        :returns: list of unique methods that call the method of interest
        """
        # First get all methods that match the given signature.
        method_objs = self.fn_get_methods(
            class_part,
            method_part,
            desc_part
        )

        # Now check the xref_from (i.e., calls to) for the method(s).
        calling_methods = []
        for method_obj in method_objs:
            for xref_from_elem in method_obj.get_xref_from():
                # The xref_from_elem is a tuple where the second element
                #  is the EncodedMethod object.
                method_name = xref_from_elem[1].get_name()
                # If we don't want anything with user interaction.
                if self.keep_user_interaction == False:
                    is_user_interaction = \
                        self.fn_check_for_user_interaction_element(
                            method_name
                        )
                    # If the method is to do with user interaction,
                    #  don't include it.
                    if is_user_interaction == True:
                        continue
                if xref_from_elem[1] not in calling_methods:
                    calling_methods.append(xref_from_elem[1])
        return calling_methods
        
    def fn_get_calls_from_method(self, class_part, method_part, desc_part, 
                                 exclude_external=False):
        """Gets all methods that get called by a method of interest.
        
        :param class_part: name of the method class as string
        :param method_part: name of the method as string
        :param desc_part: descriptor as string
        :param exclude_external: boolean indicating whether calls to external 
            methods should be excluded
        :returns: list of unique methods that get called by the method 
            of interest
        """
        desc_part = desc_part.replace('[','\[')
        # First get all methods that match the given signature.
        method_objs = self.fn_get_methods(
            class_part,
            method_part,
            desc_part
        )

        # Now check the xref_to (i.e., calls from) for the method(s).
        called_methods = set()
        for method_obj in method_objs:
            for xref_to_elem in method_obj.get_xref_to():
                # The xref_to_elem is a tuple where the first element is
                #  a ClassAnalysis object and the second element
                #  is the EncodedMethod/ExternalMethod object.
                # If we don't want external methods.
                if exclude_external == True:
                    if xref_to_elem[0].is_external() == True:
                        continue
                # If we don't want anything with user interaction.
                method_name = xref_to_elem[1].get_name()
                if self.keep_user_interaction == False:
                    is_user_interaction = \
                        self.fn_check_for_user_interaction_element(
                            method_name
                        )
                    # If the method is to do with user interaction,
                    #  don't include it.
                    if is_user_interaction == True:
                        continue
                called_methods.add(xref_to_elem[1])
        return list(called_methods)
        
    def fn_get_strings(self, string):
        """Gets all strings within an app that satisfy the given pattern.
        
        :param string: the string to search for
        :returns: Iterator[androguard.core.analysis.analysis.StringAnalysis]
        """
        string_objs = self.androguard_dx.find_strings(search_string)
        return string_objs
        
    def fn_get_calls_to_string(self, string):
        """Gets all methods that "call" a string of interest.
        
        :param string: the string to search for
        :returns: list of unique methods that "call" (or more accurately, 
            contain) the string of interest
        """
        # First get all matching strings.
        string_objs = self.fn_get_strings(string)
        
        # Now check the xref_from (i.e., calls to) for the string(s).
        calling_methods = set()
        for string_obj in string_objs:
            for xref_from_elem in string_obj.get_xref_from():
                # The xref_from_elem is a tuple where the second element
                #  is the EncodedMethod object.
                # If we don't want anything with user interaction.
                method_name = xref_from_elem[1].get_name()
                if self.keep_user_interaction == False:
                    is_user_interaction = \
                        self.fn_check_for_user_interaction_element(
                            method_name
                        )
                    # If the method is to do with user interaction,
                    #  don't include it.
                    if is_user_interaction == True:
                        continue
                calling_methods.add(xref_from_elem[1])
        return list(calling_methods)

    def fn_get_classes(self, class_part):
        """Gets all classes that satisfy a certain signature.
        
        :param class_part: class name (as string) to search for
        :returns: Iterator[androguard.core.analysis.analysis.ClassAnalysis]
        """
        class_objs = self.androguard_dx.find_classes(class_part)
        return class_objs
        
    def fn_get_calls_to_class(self, class_part):
        """Gets all methods that call a class of interest.
        
        :param class_part: class name (as string) to search for
        :returns: list of unique methods that call the class of interest
        """
        # First get all matching classes.
        class_objs = self.fn_get_classes(class_part)
        
        # Now check the xref_from (i.e., calls to) for the class(es).
        calling_methods = set()
        for class_obj in class_objs:
            for xref_from_elem in class_obj.get_xref_from():
                # The xref_from_elem is a tuple where the second element
                #  is the EncodedMethod object.
                # If we don't want anything with user interaction.
                method_name = xref_from_elem[1].get_name()
                if self.keep_user_interaction == False:
                    is_user_interaction = \
                        self.fn_check_for_user_interaction_element(
                            method_name
                        )
                    # If the method is to do with user interaction,
                    #  don't include it.
                    if is_user_interaction == True:
                        continue
                calling_methods.add(xref_from_elem[1])
        return list(calling_methods)
        
    def fn_check_for_user_interaction_element(self, method_name):
        """Checks whether the provided method involves user interaction.
        
        This function checks whether a given method involves user 
        interaction (e.g., onClick will only be triggered if a user clicks 
        something). The checks are based purely on method name.
        Any Android method that is indicated as being related to user 
        interaction (based on the Android Developer Guides) will result in 
        an output of True.
        
        :param method_name: method name as string
        :returns: boolean value indicating whether the method involves user 
            interaction (True) or not (False)
        """
        is_interactive_method = False
        
        # List of possible interactive methods.
        user_interaction_events = [
            'onBackPressed',
            'onClick',
            'onContextClick',
            'onContextItemSelected',
            'onContextMenuClosed',
            'onCreateContextMenu',
            'onDrag',
            'onFocusChange',
            'onHover',
            'onKey',
            'onKeyDown',
            'onKeyUp',
            'onLocalVoiceInteractionStarted',
            'onLocalVoiceInteractionStopped',
            'onLongClick',
            'onMenuItemClick',
            'onMenuItemSelected',
            'onMenuOpened',
            'onNavigateUp',
            'onOptionsItemSelected',
            'onOptionsMenuClosed',
            'onProvideAssistContent',
            'onProvideAssistData',
            'onSearchRequested',
            'onTouch',
            'onTouchEvent',
            'onTrackballEvent',
            'onUserInteraction'
        ]

        for user_interaction_event in user_interaction_events:
            if method_name == user_interaction_event:
                is_interactive_method = True
        return is_interactive_method
        
    def fn_get_class_method_desc_from_string(self, input_string):
        """Gets class/method/descriptor parts from a string.
        
        A method call in smali is of the format
            classname->methodname descriptor (without the space)
        For example:
            Landroid/util/ArrayMap;->get(Ljava/lang/Object;)Ljava/lang/Object;
        In the above example:
            The class part is           Landroid/util/ArrayMap;
            The method part is          get
            The descriptor part is      (Ljava/lang/Object;)Ljava/lang/Object;
            
        The method part is separated from the class by "->" and from the 
        descriptor by an opening parenthesis.
        
        This function takes as input a string in the smali format and splits 
        it into the class, method and descriptor parts. If "->" is not present 
        in the string, then the entire string is assumed to be the class name 
        and the method and descriptor are assigned values of ".*" (which is 
        considered in Androguard as "any" or "don't care".
        If an opening parenthesis is not present, then it is assumed that 
        there is no descriptor part, and only the descriptor is assigned ".*".
        
        :param input_string: a string representation of a class/method
        :returns: a list containing (in order) the class, method and 
            descriptor parts obtained from the string
        """
        # Assign default values of "don't care" to method and descriptor.
        method_part = '.*'
        desc_part = '.*'
        
        # In a smali method specification, the class and method must be
        #  separated using '->'.
        if '->' in input_string:
            # There must be some string fragment after the '->'.
            split_string = input_string.split('->')
            if ((len(split_string) != 2) or (split_string[1] == '')):
                raise JandroidException(
                    {
                        'type': str(os.path.basename(__file__))
                                + ': IncorrectMethodCall',
                        'reason': 'Call to method specified incorrectly in '
                                  + 'string: "'
                                  + input_string
                                  + '". Ensure that correct smali format is used.'
                    }
                )

            # The class part is easy: it's the part preceding the '->'.
            class_part = split_string[0]

            # The part following the '->' may comprise the method *and* descriptor.
            method_desc_part = split_string[1]

            # However, it's possible that the descriptor part is not specified.
            # If the descriptor *is* included, it will begin with an
            #  opening parenthesis.
            if '(' in method_desc_part:
                method_part = method_desc_part.split('(')[0]
                desc_part = '(' + method_desc_part.split('(')[1]
            # If no opening parenthesis exists, we assume the descriptor hasn't
            #  been provided, i.e., the entire string is the method name.
            else:
                method_part = method_desc_part
                desc_part = '.'
        # If there is no "->" then assume that the entire string is the
        #  class name.
        else:
            class_part = input_string
        return [class_part, method_part, desc_part]
        
    def fn_get_class_method_desc_from_method(self, encoded_method):
        """Retrieves the class/method/descriptor strings from EncodedMethod.
        
        This function uses standard Androguard methods to get the class, 
        method and descriptor strings from an Androguard EncodedMethod object. 
        It then processes the descriptor part to remove access strings and 
        whitespaces.
        
        :param encoded_method: androguard.core.bytecodes.dvm.EncodedMethod
        :returns: a list containing (in order) the class, method and 
            descriptor parts obtained from the EncodedMethod
        """
        # Use Androguard methods to get class/method/descriptor parts.
        class_part = encoded_method.get_class_name()            
        method_part = encoded_method.get_name()
        desc_part = encoded_method.get_descriptor()

        # Process the descriptor part returned by Androguard.
        # Get rid of the whitespaces.
        desc_part = desc_part.replace(' ', '')
        # Just in case access specifiers are returned, get rid of those.
        desc_part = desc_part.split('[access')[0]
        return [class_part, method_part, desc_part]
        
    def fn_convert_returns_to_links(self, current_returns, current_links):
        """Converts a list of returnable items to links.
        
        Returnable items are items specified as RETURN within a template. 
        Such an item consists of a value and an identifier. 
        If a returnable item's identifier begins with an "@", then that means 
        it will be output as a "link", which can be used by a different part 
        of the code. This function processes an object containing all 
        returnable items, extracts those that are to be used as links, 
        and then updates a links object with the values.
        
        If the identifier from the return item is already present in the 
        links object, then the return value is appended to the list 
        corresponding to that key (unless it turns out that the return *value* 
        is also already present in the list.
        
        If the identifier from the return item is not present in the links 
        object, then a new key is created in the links object with the name 
        of the identifier, and having as its value a list containing the 
        return value.        
        
        :param current_returns: list of dictionary objects of the format 
            {identifier:value}
        :param current_links: dictionary object containing "links"
        :returns: updated links object (dictionary)
        """
        for return_object in current_returns:
            for object_key in return_object:
                return_value = return_object[object_key]
                # Links are identified by @.
                if object_key[0] != '@':
                    continue
                # If the link key is already present, then
                #  don't overwrite. Instead, append to list.
                if object_key in current_links:
                    if (return_value in current_links[object_key]):
                        continue
                    current_links[object_key].append(return_value)
                # If the link key is not present, then create 
                #  a new key and assign it a list containing one value.
                else:
                    current_links[object_key] = [return_value]
        return current_links

    def fn_get_linked_items(self, current_links, link_key):
        """Gets items from a dictionary of linked items.
        
        This function essentially returns the value corresponding to 
        a given key from a dictionary. 
        e.g., if the current_links object is
            current_links = {
                "a": ["x", "y", "z"],
                "b": ["p", "q", "r"]
            }
        then self.fn_get_linked_items(current_links, "a") would return
            ["x", "y", "z"]
        and self.fn_get_linked_items(current_links, "c") would return
            []

        :param current_links: dictionary object containing linked items
        :param link_key: key (string) to search for within dictionary keys
        :returns: list (typically of strings) of values corresponding to the 
            given key; an empty list if the key was not found
        """
        # If the key isn't present, return empty list.
        if link_key not in current_links:
            return []
        # If key is present, return items.
        link_items = current_links[link_key]
        return link_items
    
    def fn_get_all_annotations(self):
        """Get annotations for methods.
        
        Code almost directly from 
        https://github.com/androguard/androguard/issues/175
        """
        output_object = {}
        for dvm in self.androguard_d_array:
            annotations = \
                dvm.map_list.get_item_type("TYPE_ANNOTATIONS_DIRECTORY_ITEM")
            if annotations == None:
                continue
            for adi in annotations:
                if adi.get_method_annotations() == []:
                    continue

                # Each annotations_directory_item contains
                #  many method_annotation
                for mi in adi.get_method_annotations():
                    method_idx = (dvm.get_method_by_idx(mi.get_method_idx()))
                    [class_part, method_part, desc_part] = \
                        self.fn_get_class_method_desc_from_method(method_idx)
                    method_signature = class_part + '->' + method_part + desc_part
                    output_object[method_signature] = []

                    # Each method_annotation stores an offset to
                    #  annotation_set_item
                    ann_set_item = dvm.CM.get_obj_by_offset(
                        mi.get_annotations_off()
                    )

                    # a annotation_set_item has an array of annotation_off_item
                    for aoffitem in ann_set_item.get_annotation_off_item():

                        # The annotation_off_item stores the offset to an
                        #  annotation_item
                        annotation_item = \
                            dvm.CM.get_obj_by_offset(
                                aoffitem.get_annotation_off()
                            )

                        # The annotation_item stores the visibility and a 
                        #  encoded_annotation
                        # this encoded_annotation stores the type IDX, 
                        #  and an array of annotation_element
                        # these are again name idx and encoded_value's
                        encoded_annotation = annotation_item.get_annotation()

                        # Print the class type of the annotation
                        annotation_class_type = \
                            dvm.CM.get_type(encoded_annotation.get_type_idx())
                        if (annotation_class_type not in 
                                output_object[method_signature]):
                            output_object[method_signature].append(
                                annotation_class_type
                            )
        return output_object               
