import os
import copy
import json
import logging
from lxml import etree
from androguard.misc import *
from androguard.core import *
from analysis_utils import AnalysisUtils
from common import JandroidException, Conversions


class ManifestAnalyser:
    """Class to analyse a manifest XML file against a template."""
    
    def __init__(self, base_dir):
        """Sets paths, initialises variables, and instantiates classes.
        
        :param base_dir: string specifying location of script base directory
        """
        # Set paths.
        self.path_base_dir = base_dir
        
        # Start up utility helper.
        self.inst_analysis_utils = AnalysisUtils(self.path_base_dir)

        # Other variables.
        self.apk_package_name = None
        self.apk_manifest = None
        self.apk_manifest_root = None
        self.bug_template = None
        self.namespaces = {}
        self.manifest_requirements_satisfied = False
        self.all_returns = []

    def fn_perform_manifest_analysis(self, apk_pkg, bug_template,
                                     manifest_string, links={}):
        """Analyses a given manifest string against a template.
        
        :param apk_pkg: string representing APK package name
        :param bug_template: dictionary object describing the checks that 
            are to be performed
        :param manifest_string: XML string returned by Androguard, which will 
            be converted to lxml.etree
        :param links: dictionary object containing linked items
        :returns: a list containing a boolean indicating whether manifest 
            requirements were satisfied, and link objects.
        """
        # Initialise variables.
        self.manifest_requirements_satisfied = False
        self.current_links = links
        self.all_returns = []
        self.apk_package_name = apk_pkg
        self.apk_manifest_root = etree.fromstring(manifest_string)
        self.namespaces = self.apk_manifest_root.nsmap

        # We want to copy the bug template but only edit the copy.
        # That is, we don't want to modify the original template (which would
        #  happen even if we did new_bug_obj = old_bug_object and modified
        #  only the new_bug_obj).
        # For this, we do copy.deepcopy(bug template).
        # This is probably very inefficient.
        self.bug_template = copy.deepcopy(bug_template)

        # The manifest may specify a "basepath",
        #  i.e., a starting level within the XML.
        basepaths = ['']
        manifest_obj = self.bug_template['MANIFESTPARAMS']
        if 'BASEPATH' in manifest_obj:
            basepath_string = manifest_obj['BASEPATH']
            split_basepath = basepath_string.split(' OR ')
            basepaths = [basepath.strip().replace('manifest->','')
                for basepath in split_basepath]
            logging.debug(
                'Identified the following basepaths for '
                + 'manifest analysis:\n\t '
                + str(basepaths)
            )

        # Convert user-specified basepaths to a suitable format
        #  for ltree search.
        xml_parser_basepaths = ['./' + basepath.replace('->', '/')
            for basepath in basepaths]

        # Get all the paths that satisfy the basepath.
        #  e.g., a basepath of manifest->application->activity
        #  would result in a list of all activities declared within
        #  the manifest.
        starting_points = []
        for xml_parser_basepath in xml_parser_basepaths:
            starting_points = starting_points \
                + self.apk_manifest_root.findall(xml_parser_basepath)
        logging.debug(
            'Identified '
            + str(len(starting_points))
            + ' starting points within manifest.'
        )

        # Begin at a starting point and recursively search through
        #  manifest, matching it up against the bug template at each level.
        for starting_point in starting_points:
            self.current_returns = []
            self.bug_template = None
            self.bug_template = copy.deepcopy(bug_template)
            self.fn_recursive_analysis(
                self.bug_template['MANIFESTPARAMS'],
                starting_point
            )
            current_level = \
                self.fn_check_whether_all_reqs_are_satisfied()
            if current_level == True:
                self.manifest_requirements_satisfied = True
                self.current_links = \
                    self.inst_analysis_utils.fn_convert_returns_to_links(
                        self.current_returns,
                        self.current_links
                    )

        # Return a boolean indicating whether manifest requirements were
        #  satisfied, and the links.
        return [
            self.manifest_requirements_satisfied,
            self.current_links
        ]

    def fn_recursive_analysis(self, current_template, current_xml_tree):
        """Recursively checks manifest against bug template for matches.
        
        :param current_template: dictionary object containing current level 
            of bug template
        :param current_xml_tree: lxml Element
        """
        logging.debug(
            'Analysing '
            + str(current_xml_tree)
            + ' against template '
            + str(current_template)
            + '.'
        )

        # Analyse LOOKFORs.
        if ('LOOKFOR' in current_template):
            lookfor_output = self.fn_analyse_lookfor(
                current_template['LOOKFOR'],
                current_xml_tree
            )
            if lookfor_output == True:
                current_template['_IDENTIFIED_LOOKFOR'] += 1
                if (current_template['_IDENTIFIED_LOOKFOR'] \
                        >= current_template['_EXPECTED_LOOKFOR']):
                    current_template['_SATISFIED_LOOKFOR'] = True
            # If LOOKFOR fails, there is no point in proceeding further.
            else:
                return
                
        # Analyse RETURNs.
        if ('RETURN' in current_template):
            returnable_elements_string = current_template['RETURN']

            # First get each individual returnable element.
            # Multiple RETURNs can be specified in a list or in a
            #  comma-separated string.
            if type(returnable_elements_string) is list:
                returnable_elements = returnable_elements_string
            elif ',' in returnable_elements_string:
                returnable_elements = returnable_elements_string.split(',')
            else:
                returnable_elements = [returnable_elements_string]
                
            # Invoke return analysis for each returnable element.
            for returnable_element in returnable_elements:
                return_values = self.fn_analyse_return(
                    returnable_element.strip(),
                    current_xml_tree
                )
                # Add non-null/non-empty values to list of RETURNs.
                for return_value in return_values:
                    if ((return_value == None) or (return_value == {})):
                        continue
                    if return_value in self.current_returns:
                        continue
                    self.current_returns.append(return_value)

        # Analyse SEARCHPATH.
        if ('SEARCHPATH' in current_template):
            self.fn_recursive_analysis(
                current_template['SEARCHPATH'],
                current_xml_tree
            )

        # Recursive check at next level.
        for key in current_template.keys():
            # Ignore anything we've already checked.
            if key in ['BASEPATH', 'SEARCHPATH', 'RETURN', 'LOOKFOR']:
                continue
            # Ignore "private" keys.
            if key[0] == '_':
                continue

            logging.debug(
                'Currently looking at key "'
                + str(key)
                + '".'
            )

            # If the subsequent level is also a dictionary,
            #  then we need to do all this all over again.
            if type(current_template[key]) is dict:
                xml_search_results = current_xml_tree.findall(key)
                logging.debug(
                    str(len(xml_search_results))
                    + ' XML results found for key "'
                    + str(key)
                    + '".'
                )
                for xml_search_result in xml_search_results:
                    self.fn_recursive_analysis(
                        current_template[key],
                        xml_search_result
                    )
        logging.debug(
            'Finished Analysing '
            + str(current_xml_tree)
            + ' against template '
            + str(current_template)
            + '.'
        )

    def fn_analyse_return(self, returnable_elements_string,
                          manifest_location):
        """Analyses RETURN elements.
        
        :param returnable_elements_string: string specifying the element to 
            be returned
        :param manifest_location: the current level (tier) of the manifest
        :returns: a list of returnable values in {name: value} format
        """
        # Split the RETURN string into the
        #  RETURN and AS (i.e., element and label/name) parts.
        split_returnable_elements_string = \
            returnable_elements_string.split(' AS ')
        returnable_element_tag = \
            split_returnable_elements_string[0].strip()
        returnable_elements_name = \
            split_returnable_elements_string[1].strip()

        # If the tag has an identifier (denoting standardisation),
        #  then set a variable denoting this.
        convert_output_to_smali = False
        if '<smali>' in returnable_element_tag:
            returnable_element_tag = returnable_element_tag.replace(
                '<smali>:',''
            )
            convert_output_to_smali = True

        # Create a list of tags to look for. 
        # In the general way, there should be only one (corresponding to the
        #  "android" namespace). But we check, to be sure.
        returnable_elements_tags = \
            self.fn_generate_namespace_variants(returnable_element_tag)

        # Initialise a list to store all returnable values.
        all_returnables = []
        
        # Process each returnable element.
        for returnable_tag in returnable_elements_tags:
            if returnable_tag in manifest_location.attrib:
                output_value = str(manifest_location.attrib[returnable_tag])
                if convert_output_to_smali == True:
                    output_value = self.fn_standardise(output_value)
                logging.debug(
                    'Returnable tag found '
                    + str(returnable_tag)
                    + ' with value '
                    + output_value
                )
                all_returnables.append(
                    {returnable_elements_name: output_value}
                )
        return all_returnables

    def fn_analyse_lookfor(self, lookfor_object, current_xml_tree):
        """Analyses LOOKFOR elements.
        
        :param lookfor_object: dictionary object specifying the parameters 
            to look for
        :param current_xml_tree: lxml Element
        :returns: boolean indicating whether the LOOKFOR was satisfied
        """
        # Initialise variables to keep track of how many things we are
        #  supposed to bechecking and how many have been satisfied.
        expected_lookfors = 0
        satisfied_lookfors = 0

        # There are different LOOKFOR types, each with a corresponding function.
        fn_to_execute = None
        for lookfor_key in lookfor_object:
            expected_lookfors += 1
            if lookfor_key == 'TAGEXISTS':
                fn_to_execute = self.fn_analyse_tag_exists
            elif lookfor_key == 'TAGNOTEXISTS':
                fn_to_execute = self.fn_analyse_tag_not_exists
            elif lookfor_key == 'TAGVALUEMATCH':
                fn_to_execute = self.fn_analyse_tag_value_match
            elif lookfor_key == 'TAGVALUENOMATCH':
                fn_to_execute = self.fn_analyse_tag_value_no_match
            else:
                raise JandroidException(
                    {
                        'type': str(os.path.basename(__file__))
                                + ': IncorrectLookforKey',
                        'reason': 'Unrecognised LOOKFOR key.'
                    }
                )

            # A single LOOKFOR object may have a number of elements to
            #  satisfy (specified as a list).
            all_lookfors = self.fn_process_lookfor_lists(
                lookfor_object[lookfor_key]
            )
            # We have to keep track of these individual elements as well.
            expected_per_tag_lookfors = len(all_lookfors)
            satisfied_per_tag_lookfors = 0
            # Check each individual element.
            for single_lookfor in all_lookfors:
                lookfor_output = fn_to_execute(
                    single_lookfor,
                    current_xml_tree
                )
                if lookfor_output == True:
                    satisfied_per_tag_lookfors += 1
                # If even one fails, the whole thing fails.
                else:
                    break
            # Check if this one LOOKFOR check was fully satisfied.
            if expected_per_tag_lookfors == satisfied_per_tag_lookfors:
                satisfied_lookfors += 1
            # If even one fails, the whole thing fails.
            else:
                break

        # Finally, check if all expected lookfor elements were satisfied.
        if expected_lookfors == satisfied_lookfors:
            return True
        else:
            return False

    def fn_process_lookfor_lists(self, lookfor_item):
        """Generalises a LOOKFOR element as a list.
        
        :param lookfor_item: string denoting element(s) to look for
        :returns: list of LOOKFOR elements
        """
        if type(lookfor_item) is list:
            lookfor_values = lookfor_item
        elif type(lookfor_item) is str:
            lookfor_values = [lookfor_item]
        if '' in lookfor_values:
            lookfor_values.remove('')
        return lookfor_values
        
    def fn_analyse_tag_exists(self, lookfor_string, current_xml_tree):
        """Checks if a specific tag is present in current level of XML tree.
        
        This function merely checks for the presence of a tag. It does not 
        check the tag value.
        
        :param lookfor_string: string denoting item to look for
        :param current_xml_tree: lxml Element
        :returns: boolean with value True if the tag was present (else, False)
        """
        # Check if multiple items are separated by OR.
        all_tags = []
        if ' OR ' in lookfor_string:
            all_tags = lookfor_string.split(' OR ')
        else:
            all_tags = [lookfor_string]

        # Get all namespace variants.
        all_tag_variants = []
        for tag in all_tags:
            all_tag_variants.append(self.fn_generate_namespace_variants(tag))

        # Check for the presence of each tag. If even one is satisfied,
        #  return True (because it's an OR operator).
        for tag_name in all_tag_variants:
            if tag_name in current_xml_tree.attrib:
                return True
        return False
        
    def fn_analyse_tag_not_exists(self, lookfor_string, current_xml_tree):
        """Checks that a tag does not exist at the current XML tree level.
        
        :param lookfor_string: string denoting item to look for
        :param current_xml_tree: lxml Element
        :returns: boolean with value False if the tag was present (else, True)
        """
        tag = lookfor_string
            
        # Generate namespace variants.
        all_tag_variants = []
        for tag in all_tags:
            all_tag_variants.append(self.fn_generate_namespace_variants(tag))
        for tag_name in all_tag_variants: 
            if tag_name in current_xml_tree.attrib:
                return False
        return True
            
    def fn_analyse_tag_value_match(self, lookfor_string, current_xml_tree):
        """Checks that a tag (exists and) value matches a given value.
        
        :param lookfor_string: string denoting item to look for
        :param current_xml_tree: lxml Element
        :returns: boolean with value True if the tag value matched the 
            expected value. False otherwise
        """
        # Generate namespace variants.
        lookfor_tag = (lookfor_string.split('='))[0].strip()
        lookfor_tags = self.fn_generate_namespace_variants(lookfor_tag)
        
        lookfor_value = (lookfor_string.split('='))[1].strip()

        # If the tag is "exported", we analyse it separately.
        # An "exported" tag can't have multiple possible values specified
        #  in LOOKFOR, because it only has two possible values (True or False)
        #  and looking for both would be pointless.
        if lookfor_tag.split(':')[1] == 'exported':
            return self.fn_process_exported(
                lookfor_tags,
                lookfor_value,
                current_xml_tree,
                True
            )

        # Create a list of values we look for.
        # Multiple values can be specified using the OR operator.
        # Note that the AND operator is not recognised, as
        #  it could just be specified as a separate rule.
        lookfor_values = []
        if ' OR ' in lookfor_value:
            split_values = lookfor_value.split(' OR ')
            for split_value in split_values:
                if split_value.strip() == '':
                    continue
                lookfor_values.append(split_value.strip())
        else:
            lookfor_values = [lookfor_value]

        logging.debug(
            'Looking for tag(s) '
            + str(lookfor_tags)
            + ' with value(s) '
            + str(lookfor_values)
            + ' in XML attrib '
            + str(current_xml_tree.attrib)
        )

        # If the tag is present in the manifest, and the value
        #  matches what we expect, return True. Else, return False.
        for tag in lookfor_tags:
            if tag in current_xml_tree.attrib:
                if current_xml_tree.attrib[tag] in lookfor_values:
                    return True
        return False

    def fn_process_exported(self, lookfor_tags, lookfor_value,
                            current_xml_tree, is_match=True):
        """Processes the "exported" tag.
        
        :param lookfor_tags: a list of tags (namespace variants) to look for
        :param lookfor_value: string value (either "true" or "false")
        :param current_xml_tree: lxml Element
        :param is_match: boolean indicating whether the requirement is to 
            check for match or no-match
        """
        # Make sure we are at the correct level in the XML tree.
        # That is, the exported tag is only used with activities, services,
        #  receivers and providers.
        current_tag = current_xml_tree.tag            
        exported_tag_options = ['activity', 'activity-alias', 'receiver', 'service', 'provider']
        if current_tag not in exported_tag_options:
            raise JandroidException(
                {
                    'type': str(os.path.basename(__file__))
                            + ': InvalidTag',
                    'reason': 'Exported tag must belong to one of ['
                              + '"activity", "activity-alias", "receiver", '
                              + '"service", "provider"'
                              + '].'
                }
            )

        # First check if exported is explicitly defined.
        # If it is, then we needn't do much more processing.
        tag_present = False
        tag_value_in_manifest = None
        for tag in lookfor_tags:
            if tag in current_xml_tree.attrib:
                tag_present = True
                tag_value_in_manifest = current_xml_tree.attrib[tag]

        # If exported isn't explicitly defined, then consider default values.
        if tag_present == False:            
            # For activities, receivers and services, the presence of an
            #  intent-filter means exported defaults to True.
            # Else it defaults to False.
            if current_tag in ['activity', 'activity-alias', 'receiver', 'service']:
                intent_filters = current_xml_tree.findall('intent-filter')
                if intent_filters == []:
                    tag_value_in_manifest = 'false'
                else:
                    tag_value_in_manifest = 'true'

            # For providers, if sdkversion >= 17, defaults to False.
            # Else, defaults to True.
            elif current_tag in ['provider']:
                target_sdk_version = None
                uses_sdk = self.apk_manifest_root.findall('uses-sdk')
                if uses_sdk != []:
                    possible_targetsdktags = \
                        self.fn_generate_namespace_variants(
                            '<NAMESPACE>:targetSdkVersion'
                        )
                    for uses_sdk_element in uses_sdk:
                        for targetsdktag in possible_targetsdktags:
                            if targetsdktag in uses_sdk_element.attrib:
                                target_sdk_version = \
                                    int(uses_sdk_element.attrib[targetsdktag])
                if target_sdk_version != None:
                    if target_sdk_version >= 17:
                        tag_value_in_manifest = 'false'
                    else:
                        tag_value_in_manifest = 'true'
                # This is a non-ideal way to handle the situation where there
                #  is a provider with no explicit export, and no
                #  uses-sdk/targetSdkVersion element.
                if tag_value_in_manifest == None:
                    return False

        # If the values match, then if the goal was
        #  to have the values match, return True. Else, return False.
        if tag_value_in_manifest == lookfor_value:
            if is_match == True:
                return True
            else:
                return False
        # If the values match, and the goal was that they should *not* match,
        #  return False. Else, return True.
        else:
            if is_match == True:
                return False
            else:
                return True
        
    def fn_analyse_tag_value_no_match(self, lookfor_string, current_xml_tree):
        """Checks to make sure no tag value matches the given string pattern.
        
        :param lookfor_string: string denoting item to look for
        :param current_xml_tree: lxml Element
        :returns: boolean with value True if at least one tag value did not 
            match the given value. False otherwise
        """
        # Generate namespace variants.
        lookfor_tag = (lookfor_string.split('='))[0].strip()
        lookfor_tags = self.fn_generate_namespace_variants(lookfor_tag)

        lookfor_value = (lookfor_string.split('='))[1].strip()

        # If the tag is "exported", we analyse it separately.
        # An "exported" tag can't have multiple possible values specified
        #  in LOOKFOR, because it only has two possible values (True or False)
        #  and looking for both would be pointless.
        if lookfor_tag.split(':')[1] == 'exported':
            return self.fn_process_exported(
                lookfor_tags,
                lookfor_value,
                current_xml_tree,
                False
            )

        # If the tag is not present in the manifest, then return True.
        # If the tag is present, but value doesn't match, return True.
        # Else, return False.
        for tag in lookfor_tags:
            if tag in current_xml_tree.attrib:
                if current_xml_tree.attrib[tag] != lookfor_value:
                    return True
        return False

    def fn_generate_namespace_variants(self, tag):
        """Generates namespace variants for an XML tag.
        
        :param tag: string XML tag, for which namespace variants are to be 
            generated
        :returns: list of namespace variants
        """
        # Different namespaces may be used  instead of the default "android" 
        #  (although this is quite rare).
        # To handle this, the user specifies a placeholder
        #  "<NAMESPACE>". The script obtains all namespaces from
        #  the manifest and generates all possible tags.
        tags = []
        if '<NAMESPACE>' in tag:
            for namespace in self.namespaces:
                tag = tag.replace(
                    '<NAMESPACE>:',
                    ('{' + self.namespaces[namespace] + '}')
                )
                tags.append(tag)
        else:
            tags = [tag]
        return tags

    def fn_check_whether_all_reqs_are_satisfied(self):
        """Checks whether all bug elements are satisfied.
        
        This function calls a recursive check function to analyse all 
        LOOKFOR elements in the current bug template. If, at the end, 
        the number of satisfied LOOKFORs is equal to the number of expected 
        LOOKFORs, then it returns True. Else, it returns False.
        
        :returns: boolean with value True if all requirements are satisfied 
            and False if not
        """
        self.expected_lookfor = 0
        self.satisfied_lookfor = 0
        self.fn_recursively_check_lookfor(
            self.bug_template['MANIFESTPARAMS']
        )
        if self.expected_lookfor == self.satisfied_lookfor:
            return True
        else:
            return False

    def fn_recursively_check_lookfor(self, json_obj):
        """Recursively checks all LOOKFOR elements.
        
        This function checks a single LOOKFOR element. It checks whether 
        the '_SATISFIED_LOOKFOR' value is True at the same level, and if it 
        is, it increments the satisfied_lookfor count.
        
        :param json_obj: dictionary object representing one level of the 
            manifest analysis template
        """
        for key in json_obj:
            if key == 'LOOKFOR':
                self.expected_lookfor += 1
                if json_obj['_SATISFIED_LOOKFOR'] == True:
                    self.satisfied_lookfor += 1
                # If even one LOOKFOR is not satisfied,
                #  then the match fails.
                else:
                    return
            # If the child object is a dictionary,
            #  we have to repeat this process.
            if type(json_obj[key]) is dict:
                self.fn_recursively_check_lookfor(json_obj[key])

    def fn_standardise(self, element):
        """Converts a string from dotted (Java) representation to smali.
        
        :param element: string to convert (from Java to smali)
        :returns: modified string
        """
        if '.' in element:
            element = Conversions().fn_dotted_to_smali(element)
        return element