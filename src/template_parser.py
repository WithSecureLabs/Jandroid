import os
import json
import logging
from common import JandroidException

class TemplateParser:
    """Parses templates to create 'master template object'.
    
    Templates specify patterns against which applications are matched. 
    This file contains functions that parse .template files (in JSON format)  
    and creates an object, referred to as a "master template object", 
    which will be used by the matching function. 
    A separate parser class is defined for each analysis platform.
    """
    
    def __init__(self, arg_base_dir, arg_mode):
        """Sets paths and modes."""
        # Set paths.
        self.path_to_templates = os.path.join(
            arg_base_dir,
            'templates',
            arg_mode
        )
        # Set mode.
        self.analysis_mode = arg_mode
        # Variable to hold list of template paths.
        self.list_of_template_files = None        

    def fn_create_master_template_object(self):
        """Creates a "master template object" from templates.
        
        This function doesn't actually create the template object. 
        It determines the appropriate parser class to use based on 
        the analysis platform, and then calls the template object 
        creation function within that class.
        
        :returns: object (typically dictionary) of all templates.
        """
        logging.info('Creating template object.')
        # Create a list of templates.
        self.__fn_enumerate_templates()
        # Instantiate relevant class, based on analysis mode.
        class_name = self.analysis_mode.capitalize() + 'TemplateParser'
        class_inst = globals()[class_name]()
        output_template_object = class_inst.fn_parse_templates(
            self.list_of_template_files
        )
        return output_template_object

    def __fn_enumerate_templates(self):
        """Creates a list of template files.
        
        Templates are present within the <root>/templates/ folder, inside 
        a subfolder that has the same name as the analysis platform.  
        This function simply enumerates all .template files within that 
        folder and stores the filepaths to them as a list in a class property.
        """
        # Essentially, just look for files with the .json extension
        #  within the templates folder and
        #  add (paths to) them to a list.
        self.list_of_template_files = [
            os.path.join(self.path_to_templates, name)
            for name in os.listdir(self.path_to_templates)
                if ((os.path.isfile(
                    os.path.join(self.path_to_templates, name)
                )) and (name.endswith('.template')))
        ]
        logging.info(
            str(len(self.list_of_template_files))
            + ' potential template(s) found.'
        )

class AndroidTemplateParser:
    """Class for parsing Android-specific template files."""
    
    def __init__(self):
        """Initialises the output dictionary object."""
        self.output_template_object = {}
        
    def fn_parse_templates(self, template_file_list):
        """Calls template parsing function for each template in the list.
        
        :param template_file_list: list<string> of paths to .template files
        :returns: dictionary object containing data from all templates
        """
        for template_file in template_file_list:
            try:
                self.__fn_parse_template_file(template_file)
            except JandroidException as e:
                # We don't want to break on one error.
                # Just log and then continue to process
                #  next template.
                logging.error(
                    'Error parsing template '
                    + template_file
                    + ': '
                    + '['
                    + e.args[0]['type']
                    + '] '
                    + e.args[0]['reason']
                    + ' Skipping...'
                )
                continue
            except Exception as f:
                logging.error(
                    'Error parsing template '
                    + template_file
                    + ': '
                    + str(f)
                    + '. Skipping...'
                )
                continue
        return self.output_template_object
        
    def __fn_parse_template_file(self, template_file):
        """Parses a single template file and adds to template object.
        
        :param template_file: filepath to template file
        :raises JandroidException: exception raised if template cannot 
            be loaded as JSON, if template is empty object, or if required 
            keys are not present
        """
        logging.debug(
            'Parsing '
            + str(template_file)
        )
        template_file_object = {}
        # Open and load JSON file into dictionary object.
        try:
            with open(template_file, 'r') as template_file_input:
                template_file_object = json.load(template_file_input)
        except Exception as e:
            raise JandroidException(
                {
                    'type': str(os.path.basename(__file__))
                            + ': JSONError',
                    'reason': 'Error loading JSON template: '
                              + str(e)
                }
            )

        # There should never be a case of an empty template file.
        # But check, just in case.
        if template_file_object == {}:
            raise JandroidException(
                {
                    'type': str(os.path.basename(__file__))
                            + ': EmptyTemplate',
                    'reason': 'Empty template.'
                }
            )

        # Make sure all required (main) sections exist.
        required_sections = ['METADATA']
        template_file_keys = template_file_object.keys()
        for required_section in required_sections:
            if required_section not in template_file_keys:
                raise JandroidException(
                    {
                        'type': str(os.path.basename(__file__))
                                + ': MissingRequiredSection',
                        'reason': 'Required section '
                                  + required_section
                                  + ' not present.'
                    }
                )

        # Check METADATA section.
        self.__fn_check_metadata_section(template_file_object['METADATA'])

        # Make sure at least one of MANIFEST or CODE sections is present
        #  and not an empty object.        
        manifest_section_present = True              
        if 'MANIFESTPARAMS' not in template_file_object:
            manifest_section_present = False
        else:
            if template_file_object['MANIFESTPARAMS'] == {}:
                manifest_section_present = False
        code_section_present = True  
        if 'CODEPARAMS' not in template_file_object:
            code_section_present = False
        else:
            if template_file_object['CODEPARAMS'] == {}:
                code_section_present = False
        # If neither is present (or both are empty), there's nothing to check.
        if ((manifest_section_present == False) and 
                (code_section_present == False)):
            raise JandroidException(
                {
                    'type': str(os.path.basename(__file__))
                            + ': MissingRequiredSection',
                    'reason': 'Neither MANIFESTPARAMS nor '
                              + 'CODEPARAMS sections present'
                }
            )

        # Check the "MANIFESTPARAMS" section.
        if 'MANIFESTPARAMS' in template_file_object:
            self.__fn_check_manifestparams(
                template_file_object['MANIFESTPARAMS']
            )

        # Check the "CODEPARAMS" section.
        if 'CODEPARAMS' in template_file_object:
            self.__fn_check_codeparams(
                template_file_object['CODEPARAMS']
            )

        # Check the "GRAPH" section.
        if 'GRAPH' in template_file_object:
            self.__fn_check_graph(
                template_file_object['GRAPH']
            )

        # Now that all checks are complete,
        #  add the current template to the master template object.
        # There is more processing to be done, but those will
        #  be done recursively on the master template object itself.
        template_name = template_file_object['METADATA']['NAME']
        self.output_template_object[template_name] = template_file_object
        if 'NAME' in self.output_template_object[template_name]['METADATA']:
            del self.output_template_object[template_name]['METADATA']['NAME']

        # For any LOOKFOR elements within the template,
        #  add a key at the same level, indicating how many
        #  elements need to be found.
        if 'MANIFESTPARAMS' in template_file_object:
            self.__fn_recursively_create_lookfor_sums(
                self.output_template_object[template_name]['MANIFESTPARAMS']
            )

    def __fn_check_metadata_section(self, metadata_object):
        """Checks METADATA section within a template object.
        
        This function checks the METADATA section within a template object 
        to make sure all required keys are present and that all values are 
        of the expected format. It also checks for duplicate template names.
        
        :param metadata_object: METADATA dictionary object
        :raises JandroidException: exception raised if required keys are not 
            present, or if values are of incorrect format, or if duplicate 
            template names are present
        """
        # Make sure all required metadata keys exist.
        required_metadata_keywords = [
            'NAME'
        ]
        metadata_keys = metadata_object.keys()
        for required_metadata_keyword in required_metadata_keywords:            
            if required_metadata_keyword not in metadata_keys:
                raise JandroidException(
                    {
                        'type': str(os.path.basename(__file__))
                                + ': MissingRequiredKeys',
                        'reason': 'Required metadata section '
                                    + required_metadata_keyword
                                    + ' not present in template.'
                    }
                )
        
        # Make sure template name is a string.
        template_name = metadata_object['NAME']
        if type(template_name) is not str:
            raise JandroidException(
                {
                    'type': str(os.path.basename(__file__))
                            + ': BadElementType',
                    'reason': 'Template name must be string.'
                }
            )

        # Check for duplicate template names.
        if template_name in self.output_template_object:
            raise JandroidException(
                {
                    'type': str(os.path.basename(__file__))
                            + ': DuplicateTemplate',
                    'reason': 'Template name '
                                + template_name
                                + ' already exists.'
                }
            )

    def __fn_check_manifestparams(self, manifest_json_object):
        """Recursively checks MANIFESTPARAMS section within a template object.
        
        :param metadata_object: MANIFESTPARAMS dictionary object
        :raises JandroidException: exception raised if required keys are 
            not present, if keys are used incorrectly, if values are of 
            incorrect format, or if invalid operators are used
        """
        #================================
        def fn_recursive_manifest_checks(json_object):
            """Performs checks at each level of the MANIFESTPARAMS object.
            
            A MANIFESTPARAMS can have nested objects, corresponding to the 
            structure of an Android Manifest XML file. Each nested level 
            can have LOOKFOR and RETURN objects (i.e., patterns or tags to 
            look for, or values to return).
            
            :param json_object: a sub-object of the MANIFESTPARAMS object
            """
            if 'LOOKFOR' in json_object:
                self.__fn_check_lookfor(json_object['LOOKFOR'])
            if 'RETURN' in json_object:
                self.__fn_check_return(json_object['RETURN'])
            for element in json_object:
                # We already checked LOOKFOR and RETURN in previous step.
                if ((element == 'LOOKFOR') or (element == 'RETURN')):
                    continue
                if type(json_object[element]) is dict:
                    fn_recursive_manifest_checks(json_object[element])
        #================================
        # Start at manifest object root.
        if 'BASEPATH' in manifest_json_object:
            if type(manifest_json_object['BASEPATH']) is not str:
                raise JandroidException(
                    {
                        'type': str(os.path.basename(__file__))
                                + ': BadElementType',
                        'reason': 'BASEPATH must be string.'
                    }
                )
            # You can't have multiple options separated by the AND 
            #  operator within BASEPATH.
            if ' AND ' in manifest_json_object['BASEPATH']:
                raise JandroidException(
                    {
                        'type': str(os.path.basename(__file__))
                                + ': BadOperator',
                        'reason': 'AND operator cannot be used with '
                                  + 'BASEPATH.'
                    }
                )
        if 'SEARCHPATH' in manifest_json_object:
            if type(manifest_json_object['SEARCHPATH']) is not dict:
                raise JandroidException(
                    {
                        'type': str(os.path.basename(__file__))
                                + ': BadElementType',
                        'reason': 'SEARCHPATH must be string.'
                    }
                )
            # You can't have multiple options separated by the AND 
            #  operator within SEARCHPATH.
            if ' AND ' in manifest_json_object['SEARCHPATH']:
                raise JandroidException(
                    {
                        'type': str(os.path.basename(__file__))
                                + ': BadOperator',
                        'reason': 'AND operator cannot be used with'
                                  + ' SEARCHPATH.'
                    }
                )
        # Check sub-sections.
        fn_recursive_manifest_checks(manifest_json_object)

    def __fn_check_lookfor(self, lookfor_object):
        """Checks LOOKFOR sections of the template.
        
        LOOKFOR objects denote the actual check(s) to be made. 
        This could be checking for the presence (or absence) of a 
        particular XML tag, or checking the value associated with 
        the tag. A LOOKFOR object must be a dictionary, and must have 
        at least one valid sub-key from the list 
            ['TAGEXISTS', 
            'TAGNOTEXISTS',
            'TAGVALUEMATCH',
            'TAGVALUENOMATCH'].
        
        :param lookfor_object: a LOOKFOR object structure
        :raises JandroidException: exception raised if LOOKFOR object 
            is not a dictionary, at least one valid sub-key is not 
            present, if values are of the wrong type or contain 
            invalid operators
        """
        # LOOKFOR element must be object/dictionary.
        if type(lookfor_object) is not dict:
            raise JandroidException(
                {
                    'type': str(os.path.basename(__file__))
                            + ': BadElementType',
                    'reason': 'LOOKFOR element must be '
                              + 'object/dictionary.'
                }
            )

        # We need to check that at least one of the tags is present.
        lookfor_option_present = False
        lookfor_options = [
            'TAGEXISTS',
            'TAGNOTEXISTS',
            'TAGVALUEMATCH',
            'TAGVALUENOMATCH'
        ]
        for lookfor_tag in lookfor_object:
            if lookfor_tag not in lookfor_options:
                raise JandroidException(
                    {
                        'type': str(os.path.basename(__file__))
                                + ': IncorrectKey',
                        'reason': 'Unrecognised LOOKFOR key.'
                    }
                )
                    
        for lookfor_option in lookfor_options:                    
            if lookfor_option in lookfor_object:
                type_manifest_option = type(
                    lookfor_object[lookfor_option]
                )
                if ((type_manifest_option is not str) and
                        (type_manifest_option is not list)):
                    raise JandroidException(
                        {
                            'type': str(os.path.basename(__file__))
                                    + ': BadElementType',
                            'reason': lookfor_option
                                      + ' must be list or string.'
                        }
                    )
                lookfor_option_present = True

        # Make sure invalid operators are not used.
        if 'TAGEXISTS' in lookfor_object:
            if ' ' in lookfor_object['TAGEXISTS']:
                raise JandroidException(
                    {
                        'type': str(os.path.basename(__file__))
                                + ': BadTagSpecifier',
                        'reason': 'TAGEXISTS must only specify name of tag.'
                    }
                )
        if 'TAGVALUEMATCH' in lookfor_object:
            lookfor_tag = \
                (lookfor_object['TAGVALUEMATCH'].split('='))[0].strip()
            if lookfor_tag.split(':')[1] == 'exported':
                if ' OR ' in lookfor_object['TAGVALUEMATCH']:
                    raise JandroidException(
                        {
                            'type': str(os.path.basename(__file__))
                                    + ': BadTagSpecifier',
                            'reason': 'Exported tag cannot match on more ' 
                                      + 'than one value.'
                        }
                    )
        if 'TAGVALUENOMATCH' in lookfor_object:
            lookfor_tag = \
                (lookfor_object['TAGVALUENOMATCH'].split('='))[0].strip()
            if lookfor_tag.split(':')[1] == 'exported':
                if ' OR ' in lookfor_object['TAGVALUENOMATCH']:
                    raise JandroidException(
                        {
                            'type': str(os.path.basename(__file__))
                                    + ': BadTagSpecifier',
                            'reason': 'Exported tag cannot match on more ' 
                                      + 'than one value.'
                        }
                    )
                    
        # "OR" cannot be used with TAGNOTEXISTS and TAGVALUENOMATCH.
        or_disallowed_lookfor_options = [
            'TAGNOTEXISTS',
            'TAGVALUENOMATCH'
        ]
        for or_disallowed_lookfor_option in or_disallowed_lookfor_options:
            if or_disallowed_lookfor_option in lookfor_object:
                lookfor_option_string = str(
                    lookfor_object[or_disallowed_lookfor_option]
                )
                if ' OR ' in lookfor_option_string:
                    raise JandroidException(
                        {
                            'type': str(os.path.basename(__file__))
                                    + ': BadOperator',
                            'reason': or_disallowed_lookfor_option
                                    + ' cannot have "OR".'
                        }
                    )

        # If none of the keywords are present as subkeys.
        if lookfor_option_present == False:
            raise JandroidException(
                {
                    'type': str(os.path.basename(__file__))
                            + ': AbsentKey',
                    'reason': 'No valid LOOKFOR keyword(s).'
                }
            )

        # Make sure RETURN isn't a key within the LOOKFOR object.
        if 'RETURN' in lookfor_object:
            raise JandroidException(
                {
                    'type': str(os.path.basename(__file__))
                            + ': IncorrectKey',
                    'reason': 'LOOKFOR object cannot have RETURN sub-key.'
                }
            )

    def __fn_check_return(self, return_object):
        """Checks the RETURN section of template.
        
        RETURNs denote values that are to be returned by the 
        manifest analysis. Every RETURN value must have an associated 
        identifier, specified using the AS keyword.
        
        :param return_object: list<string> or string of 
            returnable values
        :raises JandroidException: exception raised if RETURN object 
            is not a list or string, or if a RETURN element does not 
            have an AS identifier
        """
        # Check that the element is the correct type.
        if ((type(return_object) is not list) and
                (type(return_object) is not str)):
            raise JandroidException(
                {
                    'type': str(os.path.basename(__file__))
                            + ': BadElementType',
                    'reason': 'RETURN element must be list or string.'
                }
            )
        # RETURN must have an AS identifier.
        if type(return_object) is str:
            if ' AS ' not in return_object:
                raise JandroidException(
                    {
                        'type': str(os.path.basename(__file__))
                                + ': MissingIdentifier',
                        'reason': 'RETURN element must have unique "AS"'
                                  + ' identifier.'
                    }
                )
            return_id = return_object.split(' AS ')
            if len(return_id) != 2:
                raise JandroidException(
                    {
                        'type': str(os.path.basename(__file__))
                                + ': MissingIdentifier',
                        'reason': 'RETURN element must have unique "AS"'
                                  + ' identifier.'
                    }
                )
            # Return identifiers must begin with "@".
            if not return_id[1].startswith('@'):
                raise JandroidException(
                    {
                        'type': str(os.path.basename(__file__))
                                + ': MissingIdentifier',
                        'reason': 'RETURN "AS" identifier must begin with "@".'
                    }
                )
                
        # If RETURNs are specified as list, make sure each individual element 
        #  within the list has an AS identifier.
        if type(return_object) is list:
            for return_element in return_object:
                if ' AS ' not in return_element:
                    raise JandroidException(
                        {
                            'type': str(os.path.basename(__file__))
                                    + ': MissingIdentifier',
                            'reason': 'RETURN element must have unique "AS"'
                                      + ' identifier.'
                        }
                    )
                return_id = return_element.split(' AS ')
                if len(return_id) != 2:
                    raise JandroidException(
                        {
                            'type': str(os.path.basename(__file__))
                                    + ': MissingIdentifier',
                            'reason': 'RETURN element must have unique "AS"'
                                      + ' identifier.'
                        }
                    )
                if not return_id[1].startswith('@'):
                    raise JandroidException(
                        {
                            'type': str(os.path.basename(__file__))
                                    + ': MissingIdentifier',
                            'reason': 'RETURN "AS" identifier must begin with "@".'
                        }
                    )

    def __fn_check_codeparams(self, code_json_object):
        """Checks the CODEPARAMS template section.
        
        This function checks for the presence of the SEARCH and TRACE 
        keywords and invokes the corresponding checking functions.
        
        :param code_json_object: dictionary object representing code search
        """
        if 'SEARCH' in code_json_object:
            self.__fn_check_code_search(code_json_object['SEARCH'])
        if 'TRACE' in code_json_object:
            self.__fn_check_code_trace(code_json_object['TRACE'])

    def __fn_check_code_search(self, code_search_obj):
        """Checks the CODEPARAMS->SEARCH template section for correctness.
        
        A code search object can have multiple different search options, 
        such as searching for the presence of or calls to strings, methods 
        or classes. Each type of search may have its own requirements that 
        need to be specified in the search template. This function checks 
        that such requriements are met.
        
        :param code_search_obj: dictionary object or list<dictionary>
            representing code search
        :raises JandroidException: exception raised if search object structure
            is not valid
        """
        # Initialise variable to keep track of whether any valid searches
        #  are present.
        bool_search_structure_satisfied = False

        # Convert object to list, to generalise.
        if type(code_search_obj) is not list:
            if type(code_search_obj) is not dict:
                raise JandroidException(
                    {
                        'type': str(os.path.basename(__file__))
                                + ': BadElementType',
                        'reason': 'Search item must be dictionary or list of '
                                  + 'dictionaries.'
                    }
                )
            code_search_obj = [code_search_obj]

        # Define the expected SEARCH structure.
        search_keywords_expected_structure = {
            'SEARCHFORMETHOD': {
                'Required': False,
                'Type': str
            },
            'SEARCHFORCALLTOMETHOD': {
                'Required': False,
                'Type': dict,
                'Subkeys': {
                    'METHOD': {
                        'Required': True,
                        'Type': str
                    },
                    'SEARCHLOCATION': {
                        'Required': False,
                        'Type': str
                    },
                    'RETURN': {
                        'Required': False,
                        'Type': str
                    }
                }
            },
            'SEARCHFORCLASS': {
                'Required': False,
                'Type': str
            },
            'SEARCHFORCALLTOCLASS': {
                'Required': False,
                'Type': dict,
                'Subkeys': {
                    'CLASS': {
                        'Required': True,
                        'Type': str
                    },
                    'SEARCHLOCATION': {
                        'Required': False,
                        'Type': str
                    },
                    'RETURN': {
                        'Required': False,
                        'Type': str
                    }
                }
            },
            'SEARCHFORSTRING': {
                'Required': False,
                'Type': str
            },
            'SEARCHFORCALLTOSTRING': {
                'Required': False,
                'Type': dict,
                'Subkeys': {
                    'STRING': {
                        'Required': True,
                        'Type': str
                    },
                    'SEARCHLOCATION': {
                        'Required': False,
                        'Type': str
                    },
                    'RETURN': {
                        'Required': False,
                        'Type': str
                    }
                }
            },
        }

        # Check that the structure of the template matches the
        #  expected structure. A valid structure will return True.
        for individual_code_search_obj in code_search_obj:
            if type(individual_code_search_obj) is not dict:
                raise JandroidException(
                    {
                        'type': str(os.path.basename(__file__))
                                + ': BadElementType',
                        'reason': 'Individual search item must be dictionary.'
                    }
                )
            for primary_search_type in individual_code_search_obj:
                individual_search_obj = \
                    individual_code_search_obj[primary_search_type]
                if ('SEARCHLOCATION' in individual_search_obj):
                    if ((primary_search_type == 'SEARCHFORMETHOD') or 
                            (primary_search_type == 'SEARCHFORCLASS') or 
                            (primary_search_type == 'SEARCHFORSTRING')):
                        raise JandroidException(
                            {
                                'type': str(os.path.basename(__file__))
                                        + ': IncorrectKey',
                                'reason': primary_search_type + ' cannot have '
                                          + 'SEARCHLOCATION.'
                            }
                        )

                    location = individual_search_obj['SEARCHLOCATION']
                    if ':' in location:
                        location_split = location.split(':')
                        # Location type has limited options.
                        location_type = location_split[0]
                        if location_type not in ['<class>', '<method>']:
                            raise JandroidException(
                                {
                                    'type': str(os.path.basename(__file__))
                                            + ': IncorrectLocationType',
                                    'reason': 'Location must be either '
                                              + '<class> or <method>.'
                                }
                            )

                if 'RETURN' in individual_search_obj:
                    if ((primary_search_type == 'SEARCHFORMETHOD') or 
                            (primary_search_type == 'SEARCHFORCLASS') or 
                            (primary_search_type == 'SEARCHFORSTRING')):
                        raise JandroidException(
                            {
                                'type': str(os.path.basename(__file__))
                                        + ': IncorrectKey',
                                'reason': primary_search_type 
                                          + ' cannot have RETURN.'
                            }
                        )
                    returnables = individual_search_obj['RETURN']
                    if type(returnables) is list:
                        returnable_elements = returnables
                    elif ',' in returnables:
                        returnable_elements = returnables.split(',')
                    else:
                        returnable_elements = [returnables]
                        
                    # Process each returnable item.
                    for return_element in returnable_elements:
                        split_return = return_element.split(' AS ')
                        if len(split_return) != 2:
                            raise JandroidException(
                                {
                                    'type': str(os.path.basename(__file__))
                                            + ': IncorrectReturnType',
                                    'reason': 'RETURN must have AS identifier.'
                                }
                            )
                        return_type = split_return[0]
                        if return_type not in ['<class>', '<method>']:
                            raise JandroidException(
                                {
                                    'type': str(os.path.basename(__file__))
                                            + ': IncorrectReturnType',
                                    'reason': 'SEARCH RETURNs must be either'
                                              + '<class> or <method>.'
                                }
                            )
                        return_id = split_return[1]
                        if not return_id.startswith('@'):
                            raise JandroidException(
                                {
                                    'type': str(os.path.basename(__file__))
                                            + ': IncorrectReturnType',
                                    'reason': 'RETURN identifier must begin '
                                              + 'with "@".'
                                }
                            )
                        
            bool_search_structure_satisfied = \
                self.__fn_check_object_against_expected_structure(
                    individual_code_search_obj,
                    search_keywords_expected_structure
                )
        
        # If no search keywords are present.
        if bool_search_structure_satisfied != True:
            raise JandroidException(
                {
                    'type': str(os.path.basename(__file__))
                            + ': InvalidStructure',
                    'reason': 'SEARCH object structure is invalid.'
                }
            )

    def __fn_check_code_trace(self, code_trace_obj):
        """Checks the CODEPARAMS->TRACE section of template for correctness.
        
        :param code_trace_obj: dictionary object or list<dictionary>
            representing code trace
        :raises JandroidException: exception raised if trace structure is not
            valid or if RETURN is not of expected format.
        """
        # Keep track of whether trace requirements were satisfied.
        bool_trace_structure_satisfied = False
        
        # Convert object to list, to generalise.
        if type(code_trace_obj) is not list:
            if type(code_trace_obj) is not dict:
                raise JandroidException(
                    {
                        'type': str(os.path.basename(__file__))
                                + ': BadElementType',
                        'reason': 'Trace item must be dictionary or list of '
                                  + 'dictionaries.'
                    }
                )
            code_trace_obj = [code_trace_obj]
        
        # Expected structure for traces.
        trace_keywords_expected_structure = {
            'TRACEFROM': {
                'Required': True,
                'Type': str
            },
            'TRACETO': {
                'Required': True,
                'Type': str
            },
            'TRACEDIRECTION': {
                'Required': False,
                'Type': str
            },
            'TRACELENGTHMAX': {
                'Required': False,
                'Type': int
            },
            'RETURN': {
                'Required': False,
                'Type': str
            }
        }
        
        # Check each trace object.
        for individual_code_trace_obj in code_trace_obj:
            if type(individual_code_trace_obj) is not dict:
                raise JandroidException(
                    {
                        'type': str(os.path.basename(__file__))
                                + ': BadElementType',
                        'reason': 'Individual trace item must be dictionary.'
                    }
                )
            
            # The essentials. We must have somewhere to trace from and to.
            if 'TRACEFROM' not in individual_code_trace_obj:
                raise JandroidException(
                    {
                        'type': str(os.path.basename(__file__))
                                + ': BadElementType',
                        'reason': 'Trace object must have TRACEFROM key.'
                    }
                )
            if 'TRACETO' not in individual_code_trace_obj:
                raise JandroidException(
                    {
                        'type': str(os.path.basename(__file__))
                                + ': BadElementType',
                        'reason': 'Trace object must have TRACETO key.'
                    }
                )
            
            # Check RETURNs.
            if 'RETURN' in individual_code_trace_obj:
                returnables = individual_code_trace_obj['RETURN']
                return_type = returnables.split(' AS ')[0]
                if return_type not in ['<tracepath>']:
                    raise JandroidException(
                        {
                            'type': str(os.path.basename(__file__))
                                    + ': BadReturnType',
                            'reason': 'Trace RETURN AS must be <tracepath>.'
                        }
                    )
                return_id = returnables.split(' AS ')[1]
                if not return_id.startswith('@tracepath_'):
                    raise JandroidException(
                        {
                            'type': str(os.path.basename(__file__))
                                    + ': BadReturnType',
                            'reason': 'Trace RETURN identifier must begin '
                                      + 'with "@tracepath_".'
                        }
                    )
            
            # Check and set TRACEDIRECTION.
            if 'TRACEDIRECTION' in individual_code_trace_obj:
                trace_direction = individual_code_trace_obj['TRACEDIRECTION']
                if trace_direction not in ['FORWARD', 'REVERSE']:
                    raise JandroidException(
                        {
                            'type': str(os.path.basename(__file__))
                                    + ': BadTraceDirection',
                            'reason': 'TRACEDIRECTION must be either '
                                      + 'FORWARD or REVERSE.'
                        }
                    )
            else:
                trace_direction = 'REVERSE'
                
            # Check TRACETYPE, particularly ADVANCED options.
            if 'TRACETYPE' in individual_code_trace_obj:
                trace_type = individual_code_trace_obj['TRACETYPE']
                if trace_type not in ['BASIC', 'ADVANCED']:
                    raise JandroidException(
                        {
                            'type': str(os.path.basename(__file__))
                                    + ': BadTraceType',
                            'reason': 'TRACETYPE must be either '
                                      + 'BASIC or ADVANCED.'
                        }
                    )
                trace_from_string = individual_code_trace_obj['TRACEFROM']
                trace_to_string = individual_code_trace_obj['TRACETO']
                if trace_type == 'BASIC':
                    if (('RESULTOF' in trace_from_string) or 
                            ('RESULTOF' in trace_to_string)):
                        raise JandroidException(
                            {
                                'type': str(os.path.basename(__file__))
                                        + ': BadTraceParams',
                                'reason': 'BASIC TRACETYPE cannot have '
                                          + 'RESULTOF.'
                            }
                        )
                    if (('ARGTO' in trace_from_string) or 
                            ('ARGTO' in trace_to_string)):
                        raise JandroidException(
                            {
                                'type': str(os.path.basename(__file__))
                                        + ': BadTraceParams',
                                'reason': 'BASIC TRACETYPE cannot have '
                                          + 'ARGTO.'
                            }
                        )
                    if (('ARGINDEX' in trace_from_string) or 
                            ('ARGINDEX' in trace_to_string)):
                        raise JandroidException(
                            {
                                'type': str(os.path.basename(__file__))
                                        + ': BadTraceParams',
                                'reason': 'BASIC TRACETYPE cannot have '
                                          + 'ARGINDEX.'
                            }
                        )
                else:
                    if (('ARGINDEX' in trace_from_string) and 
                            ('ARGTO' not in trace_from_string)):
                        raise JandroidException(
                            {
                                'type': str(os.path.basename(__file__))
                                        + ': BadTraceParams',
                                'reason': 'Cannot have ARGINDEX without ARGTO.'
                            }
                        )
                    if (('ARGINDEX' in trace_to_string) and 
                            ('ARGTO' not in trace_to_string)):
                        raise JandroidException(
                            {
                                'type': str(os.path.basename(__file__))
                                        + ': BadTraceParams',
                                'reason': 'Cannot have ARGINDEX without ARGTO.'
                            }
                        )
                    if (('RESULTOF' in trace_from_string) and 
                            (trace_direction == 'REVERSE')):
                        raise JandroidException(
                            {
                                'type': str(os.path.basename(__file__))
                                        + ': BadTraceParams',
                                'reason': 'RESULTOF for TRACEFROM can only '
                                          + 'be used with FORWARD tracing.'
                            }
                        )
                    if (('ARGTO' in trace_from_string) and 
                            (trace_direction == 'FORWARD')):
                        raise JandroidException(
                            {
                                'type': str(os.path.basename(__file__))
                                        + ': BadTraceParams',
                                'reason': 'ARGTO for TRACEFROM can only be '
                                          + 'used with REVERSE tracing.'
                            }
                        )
                    if (('RESULTOF' not in trace_from_string) and 
                            (trace_direction == 'FORWARD')):
                        raise JandroidException(
                            {
                                'type': str(os.path.basename(__file__))
                                        + ': BadTraceParams',
                                'reason': 'TRACEFROM can only start from '
                                          + 'RESULTOF with FORWARD tracing.'
                            }
                        )
                    if (('RESULTOF' in trace_to_string) and 
                            (trace_direction == 'FORWARD')):
                        raise JandroidException(
                            {
                                'type': str(os.path.basename(__file__))
                                        + ': BadTraceParams',
                                'reason': 'RESULTOF for TRACETO can only be '
                                          + 'used with REVERSE tracing.'
                            }
                        )
                    if (('ARGTO' in trace_to_string) and 
                            (trace_direction == 'REVERSE')):
                        raise JandroidException(
                            {
                                'type': str(os.path.basename(__file__))
                                        + ': BadTraceParams',
                                'reason': 'ARGTO for TRACETO can only be '
                                          + 'used with FORWARD tracing.'
                            }
                        )
                    
            # Check general structure.
            bool_trace_structure_satisfied = \
                self.__fn_check_object_against_expected_structure(
                    individual_code_trace_obj,
                    trace_keywords_expected_structure
                )
        
        # If no valid trace was identified.
        if bool_trace_structure_satisfied != True:
            raise JandroidException(
                {
                    'type': str(os.path.basename(__file__))
                            + ': InvalidStructure',
                    'reason': 'TRACE object structure is not valid.'
                }
            )

    def __fn_check_object_against_expected_structure(self, template_obj,
                                                   expected_structure):
        """Checks a template against an expected structure.
        
        :param template_obj: actual search template as dictionary object
        :param expected_structure: expected search structure
        :returns: True if all requirements are satisfied
        :raises JandroidException: exception raised if template doesn't 
            contain required keywords or if template doesn't match expected 
            structure/format. We raise exceptions instead of returning False 
            because the issues need to be fixed for the code to progress to 
            the next level
        """
        for expected_structure_keyword in expected_structure:
            # If a required sub-key is not present, then the check fails.
            if expected_structure[expected_structure_keyword]['Required'] == True:
                if expected_structure_keyword not in template_obj:
                    raise JandroidException(
                        {
                            'type': str(os.path.basename(__file__))
                                    + ': MissingKey',
                            'reason': expected_structure_keyword
                                    + ' subkey required in SEARCHPARAMS.'
                        }
                    )

            # If a non-required sub-key is not present, move onto the next.
            if expected_structure_keyword not in template_obj:
                continue

            # The type of data held in the sub-key.
            actual_type = type(template_obj[expected_structure_keyword])
            # The type of data that *should be held* in the sub-key.
            expected_type = expected_structure[expected_structure_keyword]['Type']
            # If there is a mismatch between expected and actual data types,
            #  raise an error.
            if (actual_type is not expected_type):
                raise JandroidException(
                    {
                        'type': str(os.path.basename(__file__))
                                + ': BadElementType',
                        'reason': expected_structure_keyword
                                  + ' must be '
                                  + expected_type
                                  + '.'
                    }
                )

            # If the object held within the sub-key itself has subkeys,
            #  we will need to check the sub-object as well.
            if 'Subkeys' in expected_structure[expected_structure_keyword]:
                self.__fn_check_object_against_expected_structure(
                    template_obj[expected_structure_keyword],
                    expected_structure[expected_structure_keyword]['Subkeys']
                )
        # If everything evaluated ok, then return True.
        return True

    def __fn_check_graph(self, graphable_element):
        """Checks the GRAPH section of template for correctness.
        
        A graphable element is of the structure 
            x WITH p AS attribute=r, q AS label, ...
        where 
            x is the element to graph (will be either a node or tracepath)
            p, q are values used as an attribute or label
            r is the attribute name
        
        :param graphable_element: string representing graphable element(s)
        :raises JandroidException: exception raised if GRAPH section is 
            not a string, or if graphable element does not contain 
            a "WITH" section, or if the attribute/labels aren't specified 
            using "AS"
        """
        # The graphable element must be specified by a string.
        if type(graphable_element) is not str:
            raise JandroidException(
                {
                    'type': str(os.path.basename(__file__))
                            + ': BadElementType',
                    'reason': 'GRAPH element must be string.'
                }
            )
        
        if not graphable_element.startswith('@'):
            raise JandroidException(
                {
                    'type': str(os.path.basename(__file__))
                            + ': BadElementType',
                    'reason': 'Only previous RETURNs (identified by "@" '
                              + 'can be graphed.'
                }
            )
            
        # Make sure the graphable element has a "WITH" section.
        if ' WITH ' not in graphable_element:
            raise JandroidException(
                {
                    'type': str(os.path.basename(__file__))
                            + ': BadElementType',
                    'reason': 'GRAPH element must have "WITH" keyword.'
                }
            )

        # Make sure the attribute/labels have the "AS" keyword.
        attribute_labels = graphable_element.split(' WITH ')[1].split(',')
        for attribute_label in attribute_labels:
            if ' AS ' not in attribute_label:
                raise JandroidException(
                    {
                        'type': str(os.path.basename(__file__))
                                + ': BadElementType',
                        'reason': 'Attributes/labels must be specified '
                                  + 'using the "AS" keyword.'
                    }
                )
            if (('attribute' not in attribute_label) and 
                    ('label' not in attribute_label)):
                raise JandroidException(
                    {
                        'type': str(os.path.basename(__file__))
                                + ': BadElementType',
                        'reason': 'Attributes/labels must be identified '
                                  + 'via the "attribute"/"label" strings.'
                    }
                )
    
    def __fn_recursively_create_lookfor_sums(self, json_object):
        """Recursively adds check keys for each LOOKFOR element.
        
        A MANIFEST search is specified using LOOKFOR objects, which 
        essentially tell the code what to look for. When a LOOKFOR key exists
        within part of the template, we add additional keys to the same level,
        indicating the number of expected elements to be "looked for", as well
        as the number of LOOKFORs that have been satisfied. We use these
        additional keys during manifest analysis, to determine whether a
        manifest does satisfy a template. 
        Modifies object in place. Does not return anything.
        
        :param json_object: template object which may contain LOOKFOR element
        """
        # Do NOT modify the code to exit
        #  if the LOOKFOR key is not in json_object.
        #  This is a recursive test, so sub-keys may have LOOKFOR.
        if 'LOOKFOR' in json_object:
            # The additional keys will be used by the analysis script,
            #  to check whether the required elements have
            #  all been satisfied.
            json_object['_EXPECTED_LOOKFOR'] = 1
            json_object['_IDENTIFIED_LOOKFOR'] = 0
            json_object['_SATISFIED_LOOKFOR'] = False
        # Check any sub-objects.
        for obj_key in json_object:
            if type(json_object[obj_key]) is dict:
                self.__fn_recursively_create_lookfor_sums(
                    json_object[obj_key]
                )