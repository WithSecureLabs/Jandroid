import os
import configparser

GRAPH_NODES = 'nodes'
GRAPH_RELATIONSHIP = 'rel'
GRAPH_RELATIONSHIPS = 'relationships'
GRAPH_RELATIONSHIP_FROM = 'from'
GRAPH_RELATIONSHIP_TO = 'to'
GRAPH_RELATIONSHIP_NAME = 'relationship_name'
GRAPH_RELATIONSHIP_SPECIAL = 'special'
GRAPH_NODE_START = 'Start'
GRAPH_NODE_END = 'End'


class GraphHelperWorker:
    """Class providing graphing helper functions for the worker analysis."""
    
    def __init__(self, base_dir):
        """Sets paths, reads configurations and initialises graph object.
        
        :param base_dir: string specifying location of script base directory
        """
        # Get node identifier from config file.
        # The node identifier is a string that we use as the "primary"
        #  attribute for a node.
        self.path_config_file = os.path.join(
            base_dir,
            'config',
            'jandroid.conf'
        )
        config = configparser.ConfigParser()
        config.read(self.path_config_file)        
        self.node_identifier = 'nodename'
        if config.has_section('NEO4J'):
            if config.has_option('NEO4J', 'NODE_IDENTIFIER'):
                self.node_identifier = config['NEO4J']['NODE_IDENTIFIER']
        
    def fn_analyse_graph_elements(self, template_graph_object,
                                  links, app_name, bug_name):
        """Analyses linked items against a graph template.
        
        This function actually only performs some checks and initialisation. 
        The actual analysis is performed by a called function.
        
        :param template_graph_object: string value referenced by the GRAPH
            key in the bug template
        :param links: dictionary object containing linked items
        :param app_name: string name of the application or package
        :param bug_name: string name of the bug
        :returns: a dictionary object of graphable nodes and relationships
        """
        # The graphable element must be a string.
        if type(template_graph_object) is not str:
            raise JandroidException(
                {
                    'type': str(os.path.basename(__file__))
                            + ': InvalidElementType',
                    'reason': 'Graph template key must have string value.'
                }
            )

        # Add links as a property.
        self.current_links = links

        # Initialise an object that will hold graph elements.
        # The object will have two keys: one for nodes, one for relationships.
        self.current_graph_elements = {
            GRAPH_NODES: [],
            GRAPH_RELATIONSHIPS: []
        }

        # Perform the actual analysis.
        self.fn_analyse_individual_graph_element(
            template_graph_object,
            app_name,
            bug_name
        )
        
        # The analysis will update the current_graph_elements object.
        return self.current_graph_elements

    def fn_analyse_individual_graph_element(self, template_graph_object,
                                            app_name, bug_name):
        """Analyses a graphable template string.
        
        A graphable template string is of the format 
        `x WITH a AS attribute=p, b as label, c as attribute=r ...`
        x is the element to be graphed. This must be a linked item. 
        The remaining are attributes and labels.
        Attributes are specified as <value> AS attribute=<attribute_name>. 
        Labels are specified as <value> as label. 
        
        p is a special type of attribute. It is the node identifier, 
        which is an attribute that must be present for every node. 
        The node identifier can be thought of as being similar to a 
        primary key in a SQL database.
        
        :param template_graph_object: string value referenced by the GRAPH
            key in the bug template
        :param links: dictionary object containing linked items
        :param app_name: string name of the application or package
        :param bug_name: string name of the bug
        """
        # Initialise lists to hold nodes and relationships.
        node_collection = []
        relationship_collection = []
        
        # First populate properties.
        # These will be needed for creating node objects.
        node_properties = {
            'attributes': {},
            'labels': []
        }

        # Add the bug name as a label.
        node_properties['labels'].append(bug_name)

        # Populate the remaining properties.
        properties_string = template_graph_object.split(' WITH ')[1]
        # The properties are separated using commas.
        split_properties_string = properties_string.split(',')
        for individual_property_string in split_properties_string:
            individual_property_string = individual_property_string.strip()
            property_value = individual_property_string.split(' AS ')[0]
            property_value = property_value.strip()
            if property_value[0] == '@':
                property_value = self.fn_get_all_link_elements(property_value)
                if property_value == []:
                    property_value = 'NA'

            # Get the property type.
            property_type = individual_property_string.split(' AS ')[1]
            property_type = property_type.strip()
            # A property can be either a label or an attribute. An attribute
            #  will be specified as "attribute=<attribute_name>, while a 
            #  label will simply be "label".
            # Therefore, if there is a "=" in the property type string,
            #  we would take it to be an attribute.
            if '=' in property_type:
                if property_type.split('=')[0] != 'attribute':
                    raise JandroidException(
                        {
                            'type': str(os.path.basename(__file__))
                                    + ': InvalidPropertyType',
                            'reason': 'Node property must be attribute '
                                      + 'or label.'
                        }
                    )
                attribute_name = property_type.split('=')[1]
                if attribute_name in node_properties['attributes']:
                    existing_value = \
                        node_properties['attributes'][attribute_name]                    
                    if (type(existing_value) is str):
                        # If the value we are adding is equal to the existing
                        #  value, then move to the next property.
                        if existing_value == property_value:
                            continue
                        # If the value we are adding is not equal to the
                        #  existing value, then convert the existing value to
                        #  a list, so that we can append the new value instead
                        #  of overwriting the existing value.
                        node_properties['attributes'][attribute_name] = \
                            [existing_value]
                    # If the value to be added is a string, then we just
                    #  append it to the existing list.
                    if type(property_value) is str:
                        node_properties['attributes'][attribute_name].append(
                            property_value
                        )
                    # If the value to be added is a list, then we concatenate
                    #  the two lists and remove duplicates.
                    elif type(property_value) is list:
                        concatenated_list = \
                            list(set(
                                node_properties['attributes'][attribute_name]
                                + property_value
                            ))
                        node_properties['attributes'][attribute_name] = \
                            concatenated_list
                    # We don't support a property that is not a list or string.
                    else:
                        raise JandroidException(
                            {
                                'type': str(os.path.basename(__file__))
                                        + ': InvalidElementType',
                                'reason': 'Property value must be list '
                                          + 'or string.'
                            }
                        )
                # If the attribute name doesn't exist already, then we just
                #  create a new key and assign it the property value as value.
                else:
                    node_properties['attributes'][attribute_name] = \
                        property_value
            # If there was no "=" in the property type string, then it must
            #  be a label.
            else:
                if property_type != 'label':
                    raise JandroidException(
                        {
                            'type': str(os.path.basename(__file__))
                                    + ': InvalidPropertyType',
                            'reason': 'Node property must be attribute '
                                      + 'or label.'
                        }
                    )
                # A label value can't be anything other than a string.
                if type(property_value) is not str:
                    raise JandroidException(
                        {
                            'type': str(os.path.basename(__file__))
                                    + ': InvalidElementType',
                            'reason': 'Label must be string value.'
                        }
                    )
                if property_value not in node_properties['labels']:
                    node_properties['labels'].append(property_value)

        # Get the element to be graphed.
        element_to_graph = template_graph_object.split(' WITH ')[0]        
        # There are a few special types of elements that can be graphed.
        # A trace path is an entire chain, as output by the trace function.
        if '@tracepath' in element_to_graph:
            # We will get a list of nodes and a list of relationships.
            [nodes_from_tracepath, relationships_from_tracepath] = \
                self.fn_get_nodes_from_tracepath(
                    element_to_graph,
                    node_properties,
                    bug_name
                )
            node_collection = node_collection + nodes_from_tracepath
            relationship_collection = relationship_collection \
                                      + relationships_from_tracepath
        # "app" simply indicates that the primary node attribute should be the
        #  (package) name of any app that satisfied a bug template.
        elif element_to_graph == '@app':
            node_object = self.fn_create_node_object(
                app_name,
                node_properties
            )
            node_collection.append(node_object)
        # All other types. Note that they must be linked items.
        elif element_to_graph[0] == '@':
            all_links = self.fn_get_all_link_elements(element_to_graph)
            for link_element in all_links:
                if type(link_element) is str:
                    node_object = self.fn_create_node_object(
                        link_element,
                        node_properties
                    )
                    node_collection.append(node_object)
                elif type(link_element) is list:
                    for single_element in link_element:
                        node_object = self.fn_create_node_object(
                            single_element,
                            node_properties
                        )
                        node_collection.append(node_object)
        # If something is not a linked item, then raise an error.
        else:
            raise JandroidException(
                {
                    'type': str(os.path.basename(__file__))
                            + ': NoValidGraphElement',
                    'reason': 'Graph element must be a linked object.'
                }
            )

        # Add nodes and relationships to graphable element object.
        for node_element in node_collection:
            if node_element in self.current_graph_elements[GRAPH_NODES]:
                continue
            self.current_graph_elements[GRAPH_NODES].append(node_element)
        for relationship_element in relationship_collection:
            if (relationship_element in 
                    self.current_graph_elements[GRAPH_RELATIONSHIPS]):
                continue
            self.current_graph_elements[GRAPH_RELATIONSHIPS].append(
                relationship_element
            )
        
    def fn_get_nodes_from_tracepath(self, link_key,
                                    node_properties, bug_name):
        """Generate node and relationship objects from tracepath strings.
        
        A tracepath string is simply a string containing the methods that 
        were traversed when performing a trace. These methods are separated 
        by commas, and the order in which they appear is the order in which 
        the method calls take place.
        
        :param link_key: the key into the linked element object, which will 
            return a list of trace paths
        :param node_properties: the other properties that will be added to 
            the method nodes
        :param bug_name: string name of the bug
        :returns: a list containing a list of node objects and a list of 
            relationship objects
        """
        # Initialise lists to hold the nodes and relationships.
        individual_nodes = []
        chain_relationships = []

        # Get the list of tracepaths from the linked items object.
        all_tracepaths = self.fn_get_all_link_elements(link_key)
        
        # Analyse each tracepath
        for single_tracepath_string in all_tracepaths:
            split_path = single_tracepath_string.split(',')
            for idx, node_element in enumerate(split_path):
                node_object = self.fn_create_node_object(
                    node_element.strip(),
                    node_properties
                )
                # If it is the first or last node, then add a label to
                #  denote this.
                # First node in chain.
                if idx == 0:
                    node_object = self.fn_add_label_to_node_object(
                        node_object,
                        bug_name + GRAPH_NODE_START
                    )
                # Last node in chain.
                last_node_index = len(split_path)-1
                if idx == last_node_index:
                    node_object = self.fn_add_label_to_node_object(
                        node_object,
                        bug_name + GRAPH_NODE_END
                    )
                individual_nodes.append(node_object)

                # Next, create relationship objects.
                # Note that if we are at the last node, we can't create a
                #  relationship object, (because there is no "next" element).
                if idx >= last_node_index:
                    break
                # Create relationship elements.
                relationship_element = {
                    GRAPH_RELATIONSHIP_FROM: node_element,
                    GRAPH_RELATIONSHIP_TO: split_path[idx+1]
                }
                rel_object = self.fn_create_relationship_object(
                    relationship_element,
                    node_properties,
                    bug_name
                )
                chain_relationships.append(rel_object)
                
        return [individual_nodes, chain_relationships]
    
    def fn_add_label_to_node_object(self, object, label):
        """Adds label to a node object.
        
        :param object: dictionary object representing a node
        :param label: string label to be added to the list of node labels
        :returns: updated dictionary object
        """
        if 'labels' not in object:
            object['labels'] = [label]
        else:
            if label not in object['labels']:
                object['labels'].append(label)
        return object

    def fn_create_node_object(self, node_element, node_properties):
        """Creates a node object from node values and properties.
        
        :param node_element: string value to be used as node identifier 
            (typically a combination of class/method/descriptor
        :param node_properties: dictionary object containing label list and 
            attribute object to be included with the main node value
        :returns: dictionary object with keys for attributes and labels
        """
        # Initialise an output object.
        node_object = {
            'labels': [],
            'attributes': []
        }

        # Add labels to the object. Labels don't need any processing.
        for label in node_properties['labels']:
            node_object['labels'].append(label)

        # Add attributes.
        for element_identifier in node_properties['attributes']:
            # The node identifier may require some processing.
            if element_identifier == self.node_identifier:
                element_value = self.fn_get_node_id_value(
                    node_element,
                    node_properties['attributes'][element_identifier]
                )
            # All other types of attributes are added as-is.
            else:
                element_value = \
                    node_properties['attributes'][element_identifier]
            # Add the attribute value.
            node_object['attributes'].append(
                {element_identifier: element_value}
            )       
        return node_object
        
    def fn_create_relationship_object(self, rel_element,
                                      node_properties, bug_name):
        """Creates a relationship object from node elements and properties.
        
        :param rel_element: dictionary object with one key containing the 
            node id value of the FROM node, and another key containing the 
            node id of the TO node
        :param node_properties: dictionary object containing label list and 
            attribute object to be included with the main node value
        :param bug_name: string name of the bug
        :returns: dictionary object representing a relationship between two 
            nodes; the object will have two keys representing the FROM and TO 
            nodes (whose values will be node objects), and one key holding 
            a dictionary object with the name and other attributes of 
            the relationship
        """
        # Initialise the output object.
        out_object = {}
        
        # Process the FROM node, create a node object for it,
        #  and add to output object.
        from_element = rel_element[GRAPH_RELATIONSHIP_FROM]        
        from_node_obj = self.fn_create_node_object(
            from_element,
            node_properties
        )
        out_object[GRAPH_RELATIONSHIP_FROM] = from_node_obj
        
        # Process the TO node, create a node object for it,
        #  and add to output object.
        to_element = rel_element[GRAPH_RELATIONSHIP_TO]
        to_node_obj = self.fn_create_node_object(
            to_element,
            node_properties
        )
        out_object[GRAPH_RELATIONSHIP_TO] = to_node_obj
        
        # Create an object representing the relationship.
        relationship_obj = {
            GRAPH_RELATIONSHIP_NAME:':CALLS',
            'attributes': [{'bug': bug_name}]
        }
        out_object[GRAPH_RELATIONSHIP] = relationship_obj
        
        return out_object

    def fn_get_node_id_value(self, node_element, id_pattern):
        """Processes a node id pattern and returns a node id value.
        
        A node ID pattern specifies the way in which a node should should 
        be named. There is an assumption here that every node represents a  
        method and will therefore have class/method/descriptor components.
        
        If the id pattern is "<self>", then the node_element is returned as-is.
        
        For any other pattern, the node id string is created by replacing the 
        "<class>", "<method>", "<desc>" strings with their actual values.
        
        Example:
        Considering a node_element `Lcom/aaa/bbb;->myMethod(arg1)V`, below 
        are some sample node patterns and the outputs this function will 
        generate for them:
            ID PATTERN                  OUTPUT
            <self>                      Lcom/aaa/bbb;->myMethod(arg1)V
            <class>                     Lcom/aaa/bbb;
            <method>                    myMethod
            <desc>                      (arg1)V
            <class>:<method>:<desc>     Lcom/aaa/bbb;:myMethod:(arg1)V
            <method>-<class>-<desc>     myMethod-Lcom/aaa/bbb;-(arg1)V
        
        :param node_element: string representation of a method in smali format
        :param id_pattern: string representing the format/pattern of the 
            node id value
        :returns: formatted node id value
        """
        # Using "self" as the id pattern will simply return the value as-is.
        if id_pattern == '<self>':
            return node_element
        
        # Get the class/method/descriptor parts from the input string.
        [class_part, method_part, desc_part] = \
            self.fn_get_class_method_desc_from_string(node_element)
        # We essentially replace the relevant portions of the id pattern
        #  with the corresponding values. That is, we replace the string
        #  "class" with the class_part of the node value, we replace 
        #  the string "method" with the method part, and we replace "desc"
        #  (or "descriptor") with the descriptor part.
        output_value = id_pattern
        if '<class>' in id_pattern:
            output_value = output_value.replace('<class>', class_part)
        if '<method>' in id_pattern:
            output_value = output_value.replace('<method>', method_part)
        if '<descriptor>' in id_pattern:
            output_value = output_value.replace('<descriptor>', desc_part)
        if '<desc>' in id_pattern:
            output_value = output_value.replace('<desc>', desc_part)
        
        return output_value

    def fn_get_all_link_elements(self, link_key):
        """Retrieves linked items, given a key.
        
        :param link_key: key to search for within linked items object
        :returns: linked items, or empty list if not found
        """
        link_elements = []
        if link_key in self.current_links:
            link_elements = self.current_links[link_key]
        return link_elements
        
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